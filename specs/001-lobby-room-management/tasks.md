# Tasks: Lobby Creation & Room Management

**Input**: Design documents from `/specs/001-lobby-room-management/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: The Constitution §I mandates TDD for all production code. Tests are **required**.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Exact file paths in descriptions

## Path Conventions

Based on `plan.md` project structure:

- Django apps: `apps/<app>/`
- Utilities: `utils/`
- Tests: `tests/<app>/`
- Config: `config/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Testing configuration and shared utility scaffolding

- [x] T001 Configure pytest with pytest-django and pytest-asyncio in `pyproject.toml` and create `tests/conftest.py`
- [x] T002 [P] Create `utils/__init__.py`, `utils/errors.py`, `utils/pagination.py`, `utils/validators.py` package skeleton
- [x] T003 [P] Create `apps/friends/` Django app skeleton (`__init__.py`, `apps.py`, `models.py`, `serializers.py`, `services.py`, `views.py`, `urls.py`)
- [x] T004 Register `apps.friends` in `config/settings.py` INSTALLED_APPS and add `rest_framework_simplejwt.token_blacklist` for logout support

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can begin

**⚠️ CRITICAL**: No user story work starts until this phase passes

- [x] T005 Implement uniform error response helper (`api_error`, `api_validation_error`) in `utils/errors.py`
- [x] T006 [P] Implement standard pagination class in `utils/pagination.py` (DRF `PageNumberPagination` subclass)
- [x] T007 [P] Add `scheduled_at`, `role_configuration` fields and `SCHEDULED` status to Room model in `apps/room/models.py`
- [x] T008 Create `RoomMember` through model (replacing direct M2M on Room) with `joined_at` and `added_by` fields in `apps/room/models.py` ⚠️ Reopened — BUG-002: FK missing `related_name='members'`; also needs `cloudflare_participant_id` CharField (fixed 2026-06-23)
- [x] T009 Create `RoomJoinRequest` model in `apps/room/models.py`
- [x] T010 Create `FriendRequest` model in `apps/friends/models.py`
- [x] T011 Generate and apply migrations: `python manage.py makemigrations && python manage.py migrate`
- [x] T012 [P] Update `config/api.py` to include friends and room join-request URL prefixes

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Account Creation & Authentication (Priority: P1) 🎯 MVP

**Goal**: Users can register, log in, receive JWT tokens, refresh tokens, and log out. Unauthenticated access is blocked.

**Independent Test**: Register a new account → receive tokens. Log in with credentials → receive tokens. Access protected endpoint with token → success. Access without token → 401. Logout → refresh token blacklisted.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T013 [P] [US1] Unit tests for `AccountService` in `tests/accounts/test_services.py`
- [x] T014 [P] [US1] Integration tests for register, login, refresh, logout endpoints in `tests/accounts/test_views.py`

### Implementation for User Story 1

- [x] T015 [US1] Implement `AccountService` (`register`, `login`, `logout`) in `apps/accounts/services.py`
- [x] T016 [US1] Implement `RegisterView` and `LoginView` (calling AccountService) in `apps/accounts/views.py`
- [x] T017 [US1] Implement `LogoutView` (blacklists refresh token) and `TokenRefreshView` in `apps/accounts/views.py`
- [x] T018 [US1] Update `apps/accounts/urls.py` with login, logout, refresh paths
- [x] T019 [US1] Add complete type annotations to all accounts app code per Constitution §V

**Checkpoint**: Users can register, login, refresh, logout. Unauthenticated requests get 401.

---

## Phase 4: User Story 2 - Room Creation & Host Management (Priority: P1)

**Goal**: Authenticated users create rooms (becoming host), configure max players and role toggles, schedule rooms for the future, finish rooms, view hosted rooms list. Room model updated with new fields and through model.

**Independent Test**: Create a room → verify host, code, settings, Cloudflare meeting created. List hosted rooms → room appears. Finish room → status changes to finished, meeting ended.

### Tests for User Story 2

- [x] T020 [P] [US2] Unit tests for `RoomService` in `tests/room/test_services.py`
- [x] T021 [P] [US2] Integration tests for room create, list, finish endpoints in `tests/room/test_views.py`

### Implementation for User Story 2

- [x] T022 [US2] Implement `RoomService` (`create_room`, `get_hosted_rooms`, `finish_room`) in `apps/room/services.py`
- [x] T023 [US2] Update `CreateRoomSerializer` to accept `scheduled_at` and `role_configuration` in `apps/room/serializers.py`
- [x] T024 [US2] Update `RoomSerializer` to include `scheduled_at`, `role_configuration`, and member details in `apps/room/serializers.py`
- [x] T025 [US2] Refactor `CreateRoomView`, `HostedRoomListView`, `FinishRoomView` to use `RoomService` per Constitution §III in `apps/room/views.py`
- [x] T026 [US2] Add complete type annotations to all room app code per Constitution §V

**Checkpoint**: Room creation, listing, and finishing fully functional with service layer.

---

## Phase 5: User Story 4 - Friend System (Priority: P2)

**Goal**: Users search for other users, send friend requests, accept/decline incoming requests, remove friends. Friend list enables Phase 6 direct room adds.

**Why before US3**: US3 Scenario 1 (host adds friend directly) requires the friend list.

**Independent Test**: Alice sends friend request to Bob. Bob accepts. Both see each other in friend list. Alice removes Bob. Bob no longer in list.

### Tests for User Story 4

- [x] T027 [P] [US4] Unit tests for `FriendService` in `tests/friends/test_services.py`
- [x] T028 [P] [US4] Integration tests for friend endpoints in `tests/friends/test_views.py`

### Implementation for User Story 4

- [x] T029 [P] [US4] Implement `FriendService` (`send_request`, `accept_request`, `decline_request`, `remove_friend`, `search_users`, `get_friends`, `get_incoming_requests`, `get_outgoing_requests`) in `apps/friends/services.py`
- [x] T030 [P] [US4] Implement friend serializers (`FriendRequestSerializer`, `FriendSerializer`, `UserSearchSerializer`) in `apps/friends/serializers.py`
- [x] T031 [US4] Implement friend views (`FriendListView`, `IncomingRequestListView`, `OutgoingRequestListView`, `SendFriendRequestView`, `AcceptFriendRequestView`, `DeclineFriendRequestView`, `RemoveFriendView`, `UserSearchView`) in `apps/friends/views.py`
- [x] T032 [US4] Implement friend URL routing in `apps/friends/urls.py`
- [x] T033 [US4] Add complete type annotations to all friends app code per Constitution §V

**Checkpoint**: Full friend system functional — search, request, accept, decline, remove.

---

## Phase 6: User Story 3 - Joining & Inviting to Rooms (Priority: P1)

**Goal**: Host adds friends directly to room (auto-join). Users join via invite link (host approval required). Host accepts/rejects link join requests. Full room, member count, edge case handling.

**Independent Test**: Host adds friend → friend appears in room immediately. User clicks invite link → join request created → host accepts → user joins. Reject → user notified. Full room → rejected. Finished room → rejected.

### Tests for User Story 3

- [x] T034 [P] [US3] Unit tests for `RoomJoinService` in `tests/room/test_services.py` (extend)
- [x] T035 [P] [US3] Integration tests for add, join, accept, reject, list members endpoints in `tests/room/test_views.py` (extend)

### Implementation for User Story 3

- [x] T036 [US3] Implement room joining logic in `RoomService` (`add_friend_to_room`, `request_to_join`, `accept_join_request`, `reject_join_request`, `get_join_requests`, `get_members`) in `apps/room/services.py`
- [x] T037 [US3] Implement join request serializers in `apps/room/serializers.py`
- [x] T038 [US3] Refactor `JoinRoomView` to use RoomService and create join requests instead of auto-joining for link users in `apps/room/views.py`
- [x] T039 [US3] Refactor `AddMemberView`, `MemberListView`, `RemoveMemberView` to use RoomService in `apps/room/views.py`
- [x] T040 [US3] Implement join request accept/reject views (`AcceptJoinRequestView`, `RejectJoinRequestView`, `JoinRequestListView`) in `apps/room/views.py`
- [x] T041 [US3] Add join request URL routes to `apps/room/urls.py`
- [x] T042 [US3] Update `apps/room/views.py` edge case handling: full room, finished room, already member, host disconnect → host transfer

**Checkpoint**: Complete room joining flow — direct add, link request, accept/reject.

---

## Phase 7: User Story 5 - Real-Time Room Updates (Priority: P2)

**Goal**: Players see real-time member join/leave, host changes, join requests, room closure via WebSocket. Reconnected players receive full room state.

**Independent Test**: Two WebSocket clients in a room. Third joins → both see player_joined. Host disconnects → host_changed broadcast. Room finished → room_closed broadcast.

### Tests for User Story 5

- [ ] T043 [P] [US5] Integration tests for RoomConsumer in `tests/room/test_consumers.py` (Channels `Communicator`)

### Implementation for User Story 5

- [x] T044 [US5] Implement host transfer logic in `RoomConsumer.disconnect()` and original host regain in `connect()` in `apps/room/consumers.py` ⚠️ Reopened — BUG-001: `_was_original_host` checks `host_id` instead of `created_by_id`, allowing any reconnecting user to steal host
- [x] T045 [US5] Implement `room_state` event delivery on connect (full current state) in `apps/room/consumers.py`
- [x] T046 [US5] Add `host_changed`, `join_request_received`, `join_request_resolved`, `room_closed`, `member_removed` event handlers in `apps/room/consumers.py`
- [x] T047 [US5] Broadcast WebSocket events from RoomService (player_joined, player_left, etc.) via Channel layer in `apps/room/services.py`
- [x] T048 [US5] Add complete type annotations to RoomConsumer per Constitution §V

**Checkpoint**: All real-time events working end-to-end with reconnection state recovery.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Scheduling, validation, and final Constitution compliance

- [x] T049 [P] Implement room scheduling management command (`python manage.py transitionscheduledrooms`) in `apps/room/management/commands/transitionscheduledrooms.py`
- [ ] T050 [P] Verify all views, services, serializers have complete type annotations (mypy --strict passes)
- [ ] T051 [P] Run `ruff check` and `ruff format` across entire codebase — zero violations
- [ ] T052 Verify quickstart.md validation scenarios all pass end-to-end
- [ ] T053 [P] Code review: verify no business logic in views/consumers per Constitution §III; verify no duplicated logic per §II

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Stories (Phases 3-7)**: All depend on Foundational phase completion
  - US1 (Phase 3): Independent after Foundational
  - US2 (Phase 4): Independent after Foundational (uses accounts for auth)
  - US4 (Phase 5): Independent after Foundational (uses accounts for auth)
  - US3 (Phase 6): Depends on US2 (rooms exist) + US4 (friend list for direct add)
  - US5 (Phase 7): Depends on US3 (join/leave events source)
- **Polish (Phase 8)**: Depends on all user stories

### User Story Dependencies

```
Phase 1: Setup
    ↓
Phase 2: Foundational
    ↓
    ├─→ Phase 3: US1 (Auth) ──┐
    ├─→ Phase 4: US2 (Rooms) ──┤
    └─→ Phase 5: US4 (Friends)─┤
                                ↓
                    Phase 6: US3 (Joining)
                                ↓
                    Phase 7: US5 (Real-time)
                                ↓
                    Phase 8: Polish
```

### Within Each User Story

1. Tests MUST be written and FAIL before implementation (Constitution §I)
2. Models → Services → Views/Endpoints → URL routing → Type annotations
3. Story complete and validated before moving to next

### Parallel Opportunities

- Phases 3 (US1), 4 (US2), 5 (US4) can run in parallel after Foundational
- All [P] tasks within a phase can run in parallel
- Test tasks within a story can run in parallel (they fail without implementation)
- Setup and Foundational [P] tasks can run in parallel within their phases

---

## Parallel Example: Phase 3 (US1), Phase 4 (US2), Phase 5 (US4)

```bash
# After Foundational phase completes, launch all three stories:

# Developer A — Phase 3 (US1):
Task: "Unit tests for AccountService in tests/accounts/test_services.py"
Task: "Integration tests for account endpoints in tests/accounts/test_views.py"
Task: "Implement AccountService in apps/accounts/services.py"
...

# Developer B — Phase 4 (US2):
Task: "Unit tests for RoomService in tests/room/test_services.py"
Task: "Integration tests for room endpoints in tests/room/test_views.py"
Task: "Implement RoomService in apps/room/services.py"
...

# Developer C — Phase 5 (US4):
Task: "Unit tests for FriendService in tests/friends/test_services.py"
Task: "Integration tests for friend endpoints in tests/friends/test_views.py"
Task: "Implement FriendService in apps/friends/services.py"
...
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: User Story 1 (Auth)
4. Complete Phase 4: User Story 2 (Room CRUD)
5. **STOP**: Validate — users can register, login, create rooms, finish rooms
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. US1 (Auth) → Users can register and authenticate
3. US2 (Rooms) → Core room lifecycle works
4. US4 (Friends) → Social system online
5. US3 (Joining) → Complete lobby loop (invites + direct adds)
6. US5 (Real-time) → Full real-time experience
7. Polish → Production-ready

### MVP Scope

Minimum viable product = Phase 1 + 2 + 3 + 4 (US1 + US2). This delivers: account creation, authentication, room creation, room management. Users can create and manage rooms.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story independently completable and testable
- Verify tests fail before implementing (Constitution §I TDD cycle)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution §III: All business logic in services, not views/consumers
- Constitution §V: Full type annotations required, mypy --strict must pass

---

## Phase 9: Convergence

**Purpose**: Address gaps between spec/plan/contracts and the current task list identified by `/speckit-converge`.

- [x] T054 Implement data migration to populate RoomMember through model from existing Room.members M2M in `apps/room/migrations/` per Plan: data-model (missing) — N/A: old M2M removed, new FK model used
- [x] T055 [US1] Update RegisterView to include JWT access and refresh tokens in response per Contracts: rest-api §Register (partial)
- [x] T056 Wire StandardPagination into HostedRoomListView, FriendListView, and any other list endpoints in `apps/room/views.py` and `apps/friends/views.py` per Constitution §IV (missing)
- [x] T057 [US3] Add atomic join handling with `select_for_update` or `transaction.atomic` for concurrent last-slot race condition in `apps/room/services.py` per Spec: Edge Cases (missing)
- [x] T058 [US4] Add mutual friend request auto-accept logic when a pending request exists in the opposite direction in `apps/friends/services.py` per data-model.md §FriendRequest (missing)
- [x] T059 [US3] Implement join-request auto-expiration with "room full" notification when room reaches max members in `apps/room/services.py` per Spec: Edge Cases (missing)
- [x] T060 Refactor all existing views (AddMemberView, JoinRoomView, RemoveMemberView, etc.) to use uniform error response helper from `utils/errors.py` per Constitution §IV (partial)

**Bugfix**: 2026-06-23 — BUG-001 `_was_original_host` in RoomConsumer used `host_id` (mutable) instead of `created_by_id` (immutable) to identify original host. Reopened T044. Added T061 for the missing `created_by` field on Room model.

- [x] T061 [US2] [US5] Add `created_by` FK to Room model (immutable, set once in `create_room`), generate migration, update `RoomConsumer._was_original_host()` to compare against `created_by_id` in `apps/room/models.py`, `apps/room/services.py`, `apps/room/consumers.py` per BUG-001 (missing)

**Bugfix**: 2026-06-23 — BUG-002 RoomMember.room FK missing `related_name='members'`. `participant_ids` JSONField wrongly on Room instead of RoomMember. Reopened T008. Added T062 for migration + refactor.

- [x] T062 [US2] Add `related_name='members'` to RoomMember.room FK, add `cloudflare_participant_id` CharField to RoomMember, remove `participant_ids` JSONField from Room, update `_create_cloudflare_meeting()` to write to RoomMember, replace all `roommember_set` references with `members` in `apps/room/models.py`, `apps/room/views.py`, `apps/room/consumers.py`, `apps/room/services.py` per BUG-002 (implementation drift)
