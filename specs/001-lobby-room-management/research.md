# Research: Lobby Creation & Room Management

**Feature**: [spec.md](./spec.md)
**Date**: 2026-06-23

## 1. Django Channels Host Transfer on Disconnect

**Decision**: Track join order via `RoomMember.joined_at` timestamp, broadcast host change on disconnect detection in RoomConsumer.

**Rationale**: The spec requires host role to transfer to the second player who joined. Using `RoomMember.joined_at` (sorted ascending, exclude current host) gives a deterministic next host. The Channels disconnect handler broadcasts the transfer event. Original host regains role on reconnect (checked in `connect()` before `add_member`).

**Alternatives considered**:
- Redis-set-based join order: Adds complexity without benefit; DB timestamp is authoritative.
- In-memory consumer tracking: Fails across multiple server instances.

**Implementation outline**:
- Add `RoomMember` through model with `joined_at` and `added_by` fields.
- `RoomConsumer.disconnect()`: detect if disconnecting user is host → find second joiner → update `Room.host` → broadcast `host_changed` event.
- `RoomConsumer.connect()`: if reconnecting user was the original host and room still exists → restore host role → broadcast.

## 2. Cloudflare Realtime Kit Integration

**Decision**: Keep existing `apps/room/realtime.py` as-is; wrap calls in service layer for testability.

**Rationale**: The existing integration (`create_meeting`, `add_participant`, `remove_participant`, `end_meeting`, `refresh_token`) covers the full meeting lifecycle. Phase 1 only uses meeting creation for room setup and cleanup on room finish. Voice/video UI is Phase 2. Wrapping in a service allows mocking in tests.

**Alternatives considered**:
- Ad-hoc direct calls from views (current approach): Violates Constitution §III (Separation of Concerns).
- Abstracting behind a generic real-time interface: Premature abstraction; Cloudflare is the only provider needed.

## 3. Room Scheduling Auto-Transition

**Decision**: Use a Django management command invoked by a periodic scheduler (Celery Beat or simple cron). The command transitions rooms where `scheduled_at <= now()` and `status = 'scheduled'` to `status = 'waiting'`.

**Rationale**: The project already has Redis (used by Channels), which supports Celery. A management command is testable, idempotent, and can be run manually during development. Alternative: pg_cron ties scheduling to PostgreSQL specifically; cron is simpler for this scope but harder to containerize.

**Alternatives considered**:
- Django-q / Huey: Lighter than Celery but adds a new dependency.
- Polling in consumer: Unreliable, wastes resources.
- PostgreSQL LISTEN/NOTIFY: Complex setup, Channels already handles real-time.

**Note**: Celery is NOT a current dependency; to keep scope minimal, recommend a simple management command + OS cron for Phase 1, with Celery migration path if needed.

## 4. SimpleJWT Token Configuration

**Decision**: Extend existing SimpleJWT configuration with token blacklist on logout.

**Rationale**: The spec requires "prompted to re-authenticate on token expiry" (US1-S5). SimpleJWT already provides access/refresh tokens with configurable lifetimes. Adding blacklist allows server-side logout (invalidate refresh token). Current config uses 60-day access tokens for development convenience; this should be reconsidered (typically 15-30 min access + 7-day refresh).

**Configuration needed**:
- Add `rest_framework_simplejwt.token_blacklist` to INSTALLED_APPS.
- Set `BLACKLIST_AFTER_ROTATION = True`.
- Add logout endpoint that blacklists the refresh token.
- Reduce `ACCESS_TOKEN_LIFETIME` to `timedelta(minutes=30)` for production.

**Alternatives considered**:
- Stateless-only JWT (no blacklist): Can't support force-logout; violates token-expiry UX.
- Session auth instead of JWT: Doesn't work well with WebSocket auth via query string.

## 5. Django Channels Reconnection State Delivery

**Decision**: On WebSocket connect, after authentication, send a `room_state` event containing full current state (members list, host, room status) before joining the group.

**Rationale**: Spec FR-023 requires delivering current room state to reconnecting players. The consumer's `connect()` method already fetches the room — extending it to serialize and send state before accepting the connection is straightforward.

**Implementation**:
- In `RoomConsumer.connect()`: after `accept()`, send `room_state` event with serialized member list, host info, room status.
- This ensures reconnecting clients can rebuild UI state without data loss.
- Member list includes join order for host transfer logic.

**Alternatives considered**:
- Separate HTTP endpoint for room state: Adds a round trip; Channels already has the data.
- Relying on event replay: Complex, requires event sourcing infrastructure.

## 6. Service Layer Extraction

**Decision**: Create `services.py` in each app for business logic; views and consumers call services only.

**Rationale**: Constitution §III mandates thin controllers. Current views in `apps/room/views.py` mix Cloudflare API calls, DB queries, and response formatting. The service pattern isolates business logic for unit testing.

**Services to create**:
- `apps/accounts/services.py`: `register_user()`, `login_user()`
- `apps/room/services.py`: `create_room()`, `join_room()`, `add_member()`, `remove_member()`, `finish_room()`, `transfer_host()`, `handle_join_request()`
- `apps/friends/services.py`: `send_friend_request()`, `accept_friend_request()`, `decline_friend_request()`, `remove_friend()`, `search_users()`

**Alternatives considered**:
- Django managers for all logic: Managers are fine for queries but shouldn't coordinate external API calls.
- Fat models: Violates Constitution §III (models are data, not behavior).
