# Implementation Plan: Lobby Creation & Room Management

**Branch**: `001-lobby-room-management` | **Date**: 2026-06-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-lobby-room-management/spec.md`

## Summary

Build the lobby creation and room management system for the Mafia game. This covers account creation/authentication (SimpleJWT), room CRUD with host management (Django REST Framework), friend system, room join requests via invite links, and real-time room updates (Django Channels). Video/voice is deferred to Phase 2 but the Cloudflare Realtime Kit integration points are prepared. The implementation must follow the Constitution: TDD (pytest), RESTful API design, thin controllers with business logic in services, strict type hinting, and DRY utilities.

## Technical Context

**Language/Version**: Python 3.14+

**Primary Dependencies**: Django 6.0.6, Django REST Framework, djangorestframework-simplejwt 5.5.1, Django Channels 4.3.2, Daphne 4.2.2, channels-redis 4.2.2, psycopg2-binary 2.9+, django-cors-headers 4.9+, cloudflare 5.4+

**Storage**: PostgreSQL (primary DB), Redis (Channels layer + cache)

**Testing**: pytest + pytest-django + pytest-asyncio (Constitution §I mandates TDD)

**Target Platform**: Linux server (Docker via docker-compose)

**Project Type**: web-service (REST API + WebSocket backend, no frontend)

**Performance Goals**: SC-001–SC-005 from spec: room creation <3s, real-time updates <1s, 10 concurrent rooms × 12 members

**Constraints**: JWT authentication on all endpoints (excluding register/login), WebSocket auth via JWT middleware, RESTful resource-oriented URLs per Constitution §IV

**Scale/Scope**: 23 functional requirements, 5 key entities, 5 user stories. Phase 1 of 2 (game engine deferred).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. TDD | ✅ PASS | Plan includes pytest setup; all implementation tasks will write tests first |
| II. Reusability Over Duplication | ✅ PASS | Shared validation, pagination, and error formatting will use utility modules |
| III. Separation of Concerns | ⚠️ CURRENT GAP | Existing `apps/room/views.py` mixes Cloudflare integration and DB queries in view layer; plan will extract service layer (`apps/room/services.py`, `apps/accounts/services.py`) |
| IV. RESTful API Design | ✅ PASS | URLs use resource-oriented patterns (`/rooms/`, `/friends/`, `/rooms/{code}/join-requests/`) |
| V. Code Styling & Quality | ⚠️ CURRENT GAP | No type annotations on existing consumers/views; plan will enforce full typing per Constitution |

**Gate Decision**: PASS (gaps are addressed in plan — service layer extraction and type annotations are part of the implementation scope)

## Project Structure

### Documentation (this feature)

```text
specs/001-lobby-room-management/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest-api.md      # REST endpoint contracts
│   └── websocket.md     # WebSocket event contracts
├── checklists/
│   ├── requirements.md  # Spec quality checklist
│   └── api.md           # API requirements quality checklist
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
config/
├── settings.py          # Django settings (JWT, Channels, DB, Redis)
├── urls.py              # Root URL conf (admin + /api/)
├── api.py               # API URL aggregator
├── asgi.py              # ASGI config (Daphne + Channels routing)
└── ws_urls.py           # WebSocket URL routing

apps/
├── accounts/
│   ├── models.py        # User (extends AbstractUser)
│   ├── serializers.py   # RegisterSerializer
│   ├── services.py      # Account business logic (NEW)
│   ├── views.py         # Registration, login, token refresh
│   └── urls.py          # /api/accounts/
├── room/
│   ├── models.py        # Room, RoomJoinRequest (updated)
│   ├── serializers.py   # Room serializers (updated)
│   ├── services.py      # Room business logic (NEW)
│   ├── consumers.py     # RoomConsumer (updated)
│   ├── views.py         # Room REST endpoints (updated)
│   └── urls.py          # /api/rooms/
├── friends/
│   ├── models.py        # FriendRequest, Friendship (NEW)
│   ├── serializers.py   # Friend-related serializers (NEW)
│   ├── services.py      # Friend business logic (NEW)
│   ├── views.py         # Friend REST endpoints (NEW)
│   └── urls.py          # /api/friends/ (NEW)
├── game/                # Existing — deferred changes for Phase 2
│   └── ...

utils/
├── pagination.py        # Standard pagination (NEW)
├── errors.py            # Uniform error response helper (NEW)
└── validators.py        # Shared validation utilities (NEW)

tests/
├── accounts/
│   ├── test_services.py
│   └── test_views.py
├── room/
│   ├── test_services.py
│   ├── test_views.py
│   └── test_consumers.py
└── friends/
    ├── test_services.py
    └── test_views.py
```

**Structure Decision**: Single backend project (Django). Pattern follows existing `apps/` layout with new `apps/friends/` app. New `utils/` for shared DRY utilities per Constitution §II. New `tests/` mirrors `apps/` structure.

## Complexity Tracking

**Bugfix**: 2026-06-23 — BUG-001 Room model requires a `created_by` FK (immutable) alongside the existing `host` FK (mutable). This is needed to correctly implement FR-010 original-host-regain: `_was_original_host` in RoomConsumer must compare against `created_by_id`, not `host_id`. Affects `apps/room/models.py`, `apps/room/services.py`, `apps/room/consumers.py`.

**Bugfix**: 2026-06-23 — BUG-002 RoomMember.room FK needs `related_name='members'` so members are accessible via `room.members` instead of `room.roommember_set`. Per-member `cloudflare_participant_id` moved from `Room.participant_ids` (JSONField) to `RoomMember.cloudflare_participant_id` (CharField). Affects `apps/room/models.py`, `apps/room/views.py`.

> No constitution violations to justify.
