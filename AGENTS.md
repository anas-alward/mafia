# AGENTS.md

## Project Overview

Mafia is a real-time multiplayer social deduction game built with **Django 6.x** and **Django Channels**. Players join rooms, get assigned roles (mafia, villager, detective, doctor), and play through rounds with WebRTC video meetings powered by Cloudflare Calls.

- **Backend:** Django 6.x + Daphne (ASGI) + Django Channels for WebSockets
- **API:** Django REST Framework + SimpleJWT for token auth
- **Database:** PostgreSQL for persistence, Redis for channels/cache/game state
- **Async tasks:** Celery (email sending via Mailjet)
- **WebRTC:** Cloudflare Calls API
- **Development environment:** Docker Compose (Python 3.14, dependencies managed by uv inside the container)

## Setup

Everything runs through Docker Compose. You never need to install Python, uv, or any dependencies locally.

```bash
# Create .env with required API keys (Mailjet, Cloudflare)
# See config/settings.py for all available variables
cp .env.example .env

# Build and start everything (PostgreSQL, Redis, app server)
docker compose up --build
```

The app server runs on `http://localhost:8000`. PostgreSQL and Redis start automatically as dependencies.

## Running Commands Inside the Container

All management commands, tests, and tooling run inside the `app` service:

```bash
docker compose exec app uv run <command>
```

Concrete examples:

```bash
# Django management
docker compose exec app uv run python manage.py migrate
docker compose exec app uv run python manage.py makemigrations
docker compose exec app uv run python manage.py createsuperuser
docker compose exec app uv run python manage.py shell
docker compose exec app uv run python manage.py setup_test_data

# Tests
docker compose exec app uv run pytest
docker compose exec app uv run pytest tests/room/
docker compose exec app uv run pytest tests/room/test_services.py -v
docker compose exec app uv run pytest -k test_create_room

# Lint and type-check
docker compose exec app uv run ruff check .
docker compose exec app uv run ruff check --fix .
docker compose exec app uv run ruff format .
docker compose exec app uv run mypy .
```

## Project Structure

```
mafia/
├── config/               # Django project config (settings, urls, asgi, celery)
│   ├── settings.py       # Main settings (DB, Redis, Channels, JWT, Celery, Mailjet, Cloudflare)
│   ├── urls.py           # Root URLconf: /admin/ and /api/
│   ├── api.py            # API URL aggregation (accounts, rooms, friends)
│   ├── asgi.py           # ASGI: HTTP + WebSocket with JWTAuthMiddleware
│   └── routing.py        # WebSocket route: ws/room/<code>/
├── apps/
│   ├── accounts/         # Custom User model, JWT auth, email verification, password reset
│   │   ├── models.py     # User model (email as username field)
│   │   ├── services/     # AccountService, EmailService, EmailAuthBackend
│   │   ├── tasks/        # Celery email tasks
│   │   ├── middleware.py # JWTAuthMiddleware for WebSocket auth
│   │   └── migrations/   # 0001_initial, 0002 verification fields
│   ├── room/             # Room management (lobby system)
│   │   ├── models.py     # Room model (code, host, meeting_id, status)
│   │   ├── services.py   # RoomService (create, finish, join request handling)
│   │   ├── session.py    # RoomSession — Redis-backed runtime room state
│   │   ├── management/   # setup_test_data, transitionscheduledrooms commands
│   │   └── migrations/   # 10 migrations tracking room schema evolution
│   ├── game/             # Game logic and engine
│   │   ├── models.py     # GameSession, Participant Django models
│   │   ├── roles.py      # Role types + BaseRole dataclass
│   │   ├── session.py    # Game session management
│   │   ├── engine/       # In-memory game engine (persisted to Redis as JSON)
│   │   │   ├── session.py   # GameSession dataclass
│   │   │   ├── round.py     # Round management
│   │   │   ├── player.py    # Player state
│   │   │   ├── action.py    # Game actions
│   │   │   ├── constants.py # Game constants
│   │   │   └── roles/       # RoleType enum, RoleDistributor
│   │   └── distributor.py   # Role distribution logic
│   ├── friends/          # Friend request system (send, accept, decline, remove)
│   │   ├── models.py     # FriendRequest model
│   │   └── services.py   # FriendService
│   ├── realtime/         # WebSocket event system (registry-based dispatch)
│   │   ├── consumers.py  # RealtimeConsumer (thin — delegates to dispatch)
│   │   ├── dispatch.py   # Inbound event dispatch + EventDispatchMixin
│   │   ├── events/       # Event dataclasses (room.py, game.py, errors.py, base.py)
│   │   ├── handlers/     # @on and @trampoline decorated handlers
│   │   ├── membership.py # Channel group membership management
│   │   ├── groups.py     # Channel group name helpers
│   │   └── error_codes.py
│   └── core/             # Shared utilities
│       ├── redis.py      # Redis client singleton
│       ├── webrtc.py     # Cloudflare Calls API wrapper
│       └── utils/        # UUID generation, pagination, error helpers, validators
└── tests/                # Test suite (pytest-django)
    ├── conftest.py       # Shared fixtures (api_client, test users)
    ├── test_settings.py  # Test config: SQLite :memory:, in-memory channels
    ├── accounts/         # Account service + view tests
    ├── room/             # Room service + view + joining tests
    └── friends/          # Friend service + view tests
```

## Testing

```bash
# Run all tests (uses SQLite in-memory via tests/test_settings.py)
docker compose exec app uv run pytest

# Run a specific directory or file
docker compose exec app uv run pytest tests/room/
docker compose exec app uv run pytest tests/room/test_services.py -v

# Run a single test by name pattern
docker compose exec app uv run pytest -k test_create_room

# Run with stdout shown (for debugging)
docker compose exec app uv run pytest -s

# Type checking
docker compose exec app uv run mypy .

# Lint and format
docker compose exec app uv run ruff check .
docker compose exec app uv run ruff check --fix .
docker compose exec app uv run ruff format .
```

### Test Configuration

- **Test settings:** `tests/test_settings.py` — uses SQLite `:memory:`, in-memory channel layer, eager Celery, email verification disabled
- Custom `api_client` fixture in `tests/conftest.py` provides an authenticated DRF test client
- Test files follow `test_*.py` naming convention

## Code Style

- **Python 3.14+** target
- **Line length:** 100 characters (ruff)
- **Quotes:** single quotes (ruff format)
- **Lint rules:** E, F, I, N, W, UP (ruff)
- **Type checking:** mypy with django-stubs plugin
- **Imports:** sorted with ruff (isort-compatible via "I" rule)
- **Migrations** excluded from linting

### Naming and Patterns

- Django apps under `apps/` use the app name as the module (e.g., `apps.accounts`)
- Business logic in `services.py` files, not in views or models
- Redis operations use `apps/core/redis.py` as the singleton client
- Dataclasses preferred for internal data structures (see RoomSession, GameSession, events)

## WebSocket Architecture

Single WebSocket endpoint: `ws://host/ws/room/<code>/?token=<jwt>`

### Adding a New Event

1. Define a dataclass in `apps/realtime/events/` with a `type` class attribute and `from_payload()` classmethod
2. Add an `@on(EventClass)` handler in `apps/realtime/handlers/` for inbound processing
3. Add a `@trampoline('event_type')` handler if the event is server-pushed (outbound)
4. Import the handler module in `apps/realtime/handlers/__init__.py`

The consumer (`apps/realtime/consumers.py`) does not need to be modified.

### Channel Groups

- `room_{code}` — all members in a room
- `user_{user_id}` — personal channel for a specific user

## Redis Key Schema

| Key Pattern | Type | Purpose |
|-------------|------|---------|
| `room:{code}` | Hash | Room metadata (id, name, host_id, original_host_id, meeting_id) |
| `room:{code}:members` | Set | Member user IDs |
| `room:{code}:member:{user_id}` | String (JSON) | Member data (status, name) |
| `room:{code}:waiting` | Set | Pending join request user IDs |
| `room:{code}:waiting:{user_id}` | String (JSON) | Join request details |
| `mafia:session:{room_id}` | String (JSON) | Game engine session state |

## Authentication

- Custom `User` model with email as the username field (`apps/accounts/models.py`)
- JWT authentication via SimpleJWT with token rotation (60-day access, 7-day refresh)
- Custom `EmailAuthBackend` authenticates by email + password
- WebSocket auth: pass JWT as `?token=` query parameter, validated by `JWTAuthMiddleware`
- `EMAIL_VERIFICATION_ENABLED` flag controls registration verification flow (defaults to `False`)
- DRF default permission is `IsAuthenticated` — all API endpoints require a valid token

## Build and Deployment

```bash
# Development
docker compose up --build

# Rebuild after dependency changes
docker compose build --no-cache
docker compose up
```

No CI/CD pipeline is configured in this repository.

## Pull Request Guidelines

- Lint and type-check must pass: `docker compose exec app uv run ruff check . && docker compose exec app uv run mypy .`
- All tests must pass: `docker compose exec app uv run pytest`
- Add or update tests for changed behavior
- Keep PRs focused — avoid bundling unrelated refactors
