# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
at specs/002-auth-email-verification/plan.md
<!-- SPECKIT END -->

## Tech Stack

- **Django 6.x** with **Daphne** (ASGI server) and **Django Channels** for WebSockets
- **Django REST Framework** + **SimpleJWT** for API authentication
- **PostgreSQL** for persistence, **Redis** for channels + cache + game state
- **Celery** for async task processing (email sending)
- **Mailjet** for transactional email
- **Cloudflare** (Calls API) for WebRTC video meetings
- **uv** for package management and virtualenv

## Common Commands

```bash
# Dependencies (uses uv, configured in pyproject.toml)
uv sync                    # install dependencies
uv sync --group dev        # install with dev deps

# Run the server (ASGI via Daphne)
python manage.py runserver
# Or with file watching (as configured in docker-compose.yml)
watchfiles 'python manage.py runserver 0.0.0.0:8000' .

# Django management
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_test_data    # custom command for test data

# Tests (pytest-django)
pytest                      # run all tests
pytest tests/room/          # run a directory
pytest tests/room/test_services.py -v  # single file, verbose
pytest -k test_name         # run single test by name

# Lint & type-check
ruff check .                # lint
ruff check --fix .          # lint with auto-fix
ruff format .               # format
mypy .                      # type-check (django-stubs configured)
```

## High-Level Architecture

### App Organization

- **`apps/accounts/`** — Custom `User` model (email as username), JWT auth, email verification, password reset. Uses `AccountService`, `EmailService`, and `TokenService` in `services/`. Celery tasks for async email in `tasks/`.
- **`apps/room/`** — `Room` model (code, host, meeting_id). `RoomService` handles creation/finishing. `RoomSession` (in `session.py`) is the Redis-backed runtime state for a room.
- **`apps/game/`** — `GameSession` / `Participant` Django models for persistence. `apps/game/engine/` contains the in-memory game engine (session, round, player, role distribution) persisted to Redis as JSON.
- **`apps/friends/`** — Friend request lifecycle (send, accept, decline, remove, search).
- **`apps/realtime/`** — WebSocket consumer and event system. See below.
- **`apps/core/`** — Shared utilities: `redis_client`, pagination, error helpers, validators, WebRTC client.

### WebSocket Realtime Architecture

All real-time communication goes through a single WebSocket endpoint:

```
ws://host/ws/room/<code>/
```

Authenticated via `JWTAuthMiddleware` (reads `token` from query params). The SIP: the ASGI routing wires `RealtimeConsumer` to this path.

The consumer (`apps/realtime/consumers.py`) is intentionally thin. All event dispatch logic lives in a registry-based system:

**Inbound (client → server):**
- Events are dataclasses in `apps/realtime/events/` (`room.py`, `game.py`). Each defines `type` and `from_payload()`.
- Handlers are decorated with `@on(EventClass)` in `apps/realtime/handlers/room.py` and `game.py`.
- The consumer's `receive_json` → `dispatch_inbound` routes to the registered handler.

**Outbound (server → client):**
- Events are `OutboundEvent` dataclasses with `channel_type`.
- Handlers are decorated with `@trampoline('event_type_string')` in the same files.
- `EventDispatchMixin.__getattr__` intercepts Channels' lookup, so the consumer doesn't need methods for every event type.

To add a new event: define the dataclass in `apps/realtime/events/`, add `@on` and/or `@trampoline` handler in `apps/realtime/handlers/`, and import the module in `handlers/__init__.py`. The consumer does not need to change.

### Room State (Redis)

Room runtime state is stored in Redis, not the database:

- `room:{code}` — hash with room metadata (id, name, host_id, original_host_id, meeting_id)
- `room:{code}:members` — set of user IDs
- `room:{code}:member:{user_id}` — individual member data (status, name, etc.)
- `room:{code}:waiting` — set of user IDs awaiting approval
- `room:{code}:waiting:{user_id}` — waiting request details

`RoomSession` (`apps/room/session.py`) is the dataclass interface to this Redis state. It handles loading from cache (with DB fallback), host switching, member tracking, and join request management. The original host and current host are tracked separately so the original host can regain control on reconnect.

### Game Engine (Redis-backed)

Game sessions are ephemeral and stored in Redis under `mafia:session:{room_id}` as string as JSON. The `GameSession` dataclass (`apps/game/engine/session.py`) manages rounds, players, and actions. `RoleDistributor.distribute()` assigns roles (mafia, villager, detective, doctor, etc.) from `apps/game/engine/roles/type.py`.

### WebRTC Integration

`apps/core/webrtc.py` wraps the Cloudflare Calls API. On room creation, `RoomService` creates a meeting and stores the `meeting_id` on the `Room`. On WebSocket connect, the consumer fetches WebRTC credentials for the participant and includes them in the `RoomState` event sent to the client.

### Authentication

- Uses a custom `EmailAuthBackend` (checks email + password against `User`).
- JWT tokens via `djangorestframework-simplejwt` with rotation.
- `EMAIL_VERIFICATION_ENABLED` controls whether email verification is required (currently `False` in dev).
- The `token_blacklist` app is installed for JWT blacklisting on logout.
