# Data Model: Lobby Creation & Room Management

**Feature**: [spec.md](./spec.md)
**Date**: 2026-06-23

## Entity Relationship Diagram

```
User ──┬── Room (host)              [1:N]
       ├── RoomMember (member)      [1:N through Room]
       ├── RoomJoinRequest (joiner) [1:N]
       ├── FriendRequest (sender)   [1:N]
       ├── FriendRequest (recipient)[1:N]
       └── Friendship (friend)      [M:N]

Room ──┬── RoomMember               [1:N]
       ├── RoomJoinRequest          [1:N]
       └── GameSession              [1:1 — existing, Phase 2]
```

## Entities

### User (existing — `apps/accounts/models.py`)

Extends `AbstractUser`. No schema changes needed for this phase.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | auto | PK | |
| username | varchar(150) | unique, required | Search target |
| email | varchar(254) | unique, required | |
| password | varchar(128) | required | Hashed |
| date_joined | datetime | auto | |
| is_active | boolean | default=True | For soft-disable |

### FriendRequest (NEW — `apps/friends/models.py`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | auto | PK | |
| sender | FK → User | required, related_name='sent_requests' | |
| recipient | FK → User | required, related_name='received_requests' | |
| status | varchar(10) | pending / accepted / declined | |
| created_at | datetime | auto_now_add | |
| updated_at | datetime | auto_now | |

**Validation rules**:
- Cannot send request to self.
- Cannot send duplicate pending request to same recipient.
- If a pending request exists from recipient to sender, accept it automatically (mutual friendship).
- Status transitions: pending → accepted | pending → declined. Accepted/declined are terminal.

### Friendship (NEW — `apps/friends/models.py`)

Implicit through model. Representation: both users exist in each other's friend list. Query pattern: `User.friends.all()` via symmetrical M2M or derived from accepted FriendRequests.

**Design choice**: Use a derived query rather than a separate Friendship table. Friend list = `User.objects.filter(sent_requests__recipient=me, sent_requests__status='accepted') | User.objects.filter(received_requests__sender=me, received_requests__status='accepted')`.

### Room (EXISTING — needs updates)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | auto | PK | |
| host | FK → User | required | Can change (host transfer) |
| created_by | FK → User | required, related_name='created_rooms' | Set once on creation, never changes. Source of truth for "original host" (FR-010). |
| name | varchar(100) | required | |
| code | char(8) | unique, db_index | Auto-generated, URL-safe |
| max_members | smallint | default=8, 4–20 | Validated in serializer |
| meeting_id | varchar(64) | blank=True | Cloudflare Realtime Kit meeting ID |
| status | varchar(12) | WAITING / PLAYING / FINISHED | Add SCHEDULED |
| scheduled_at | datetime | null=True | NEW |
| role_configuration | JSONField | default=dict | NEW — e.g. `{"detective": true, "doctor": true, "vigilante": false}` |
| created_at | datetime | auto_now_add | |
| updated_at | datetime | auto_now | |

**Status transitions**:
```
SCHEDULED ──→ WAITING ──→ PLAYING ──→ FINISHED
                │                        ↑
                └────────────────────────┘ (host can finish directly)
```

- `SCHEDULED`: scheduled_at is in the future. Auto-transitions to WAITING at scheduled time.
- `WAITING`: Accepting members. Host can start game (→ PLAYING) or finish (→ FINISHED).
- `PLAYING`: Game in progress (Phase 2 game engine controls further transitions).
- `FINISHED`: Terminal. Room no longer joinable.

**New validation**:
- `scheduled_at` must be in the future if status is SCHEDULED.
- `role_configuration` keys must be valid role names (deferred to game app's Role enum).
- Host cannot be removed via RemoveMemberView (existing check).
- Members accessible via `room.members` (reverse FK `related_name='members'` on RoomMember.room), not an M2M field on Room.

### RoomMember (NEW through model — replaces direct M2M)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | auto | PK | |
| user | FK → User | required | |
| room | FK → Room | required | |
| joined_at | datetime | auto_now_add | Determines host transfer order |
| added_by | varchar(12) | host-direct / link-request | How the member was added |
| cloudflare_participant_id | varchar(128) | blank=True | Cloudflare Realtime Kit participant ID for this member |
| unique_together | (user, room) | | Prevents duplicate membership |

### RoomJoinRequest (NEW)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | auto | PK | |
| user | FK → User | required | The requesting player |
| room | FK → Room | required | |
| status | varchar(10) | pending / accepted / rejected / expired | |
| requested_at | datetime | auto_now_add | |
| resolved_at | datetime | null=True | Set on accept/reject/expire |

**Validation rules**:
- One pending request per user per room.
- Cannot request if already a member.
- Cannot request if room is full or finished.
- Expire pending requests when room becomes full.
- Status transitions: pending → accepted | pending → rejected | pending → expired.

## Indexes

| Model | Index | Purpose |
|-------|-------|---------|
| Room | (status, scheduled_at) | Find scheduled rooms ready to transition |
| RoomJoinRequest | (room, status) | List pending requests for a room |
| FriendRequest | (recipient, status) | List pending incoming requests |
| FriendRequest | (sender, recipient) | Check for existing requests |
| RoomMember | (room, joined_at) | Host transfer: find second joiner |

## Migration Strategy

1. Add `scheduled_at`, `role_configuration` to Room model via migration.
2. Add SCHEDULED status to Room.Status choices.
3. Create through model RoomMember with `joined_at` and `added_by`; data migration to populate from existing `Room.members` M2M.
4. Create RoomJoinRequest model.
5. Create FriendRequest model.
6. Create `apps/friends/` app and add to INSTALLED_APPS.

**Bugfix**: 2026-06-23 — BUG-001 Added `created_by` FK to Room entity to distinguish the original creator (immutable, used for host regain in FR-010) from the current `host` (mutable, changes on transfer).

**Bugfix**: 2026-06-23 — BUG-002 Removed incorrect `members` M2M row and `participant_ids` JSONField from Room entity table. Members are accessed via reverse FK `room.members` (not an M2M on Room). Per-member Cloudflare participant ID moved to `RoomMember.cloudflare_participant_id`.
