# Feature Specification: Lobby Creation & Room Management

**Feature Branch**: `001-lobby-room-management`

**Created**: 2026-06-22

**Status**: Draft

**Input**: User description: "Build a lobby creation and room management system for our Mafia game. A user should be able to create a room which makes them the host. The host can invite others by a link or from the friend list, a user should create an account before they can do anything. A user can make friend requests and accepts. Players should have real time update for status and game should managed by us, there won't be mediator. There are two phases day and night. Day where people can see each other and night where special actors or roles can do there job. In the room there will be controlling for voice and video, either by host or mediator. At the end of each game session there will be winners and losers whether and each participant will have their own aggregate result at the end."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Account Creation & Authentication (Priority: P1)

A new player creates an account with a username, email, and password. Once registered, they can log in and access the game lobby. No feature of the application is accessible without authentication.

**Why this priority**: Authentication is the gate for all other functionality. Without accounts, there are no rooms, friends, or games.

**Independent Test**: Register a new account, log in, and verify the user can see the main lobby screen. Attempt to access any feature without logging in and confirm redirection to login.

**Acceptance Scenarios**:

1. **Given** a new user on the registration page, **When** they submit valid username, email, and password, **Then** an account is created and they are logged in automatically.
2. **Given** a registered user on the login page, **When** they submit correct credentials, **Then** they are authenticated and redirected to the lobby.
3. **Given** a registered user on the login page, **When** they submit incorrect credentials, **Then** they see an error message and remain on the login page.
4. **Given** an unauthenticated visitor, **When** they attempt to access any page or feature, **Then** they are redirected to the login page.
5. **Given** a logged-in user, **When** their authentication token expires, **Then** they are prompted to re-authenticate.

---

### User Story 2 - Room Creation & Host Management (Priority: P1)

A logged-in user creates a game room, becoming its host. The host configures room settings (max players, which special roles are enabled for the eventual game) and can see the room lobby with joined members. The host can also schedule a room for a future date and time.

**Why this priority**: Rooms are the core unit of gameplay. Without rooms, no game can take place.

**Independent Test**: A user creates a room, verifies they are the host, checks the room has a unique invite code/link, and confirms the room appears in their hosted rooms list.

**Acceptance Scenarios**:

1. **Given** a logged-in user in the lobby, **When** they select "Create Room" and confirm settings, **Then** a new room is created with them as host and a unique invite code is generated.
2. **Given** a logged-in user in the lobby, **When** they select "Create Room" and set a future schedule date/time, **Then** the room is created with status "scheduled" and the schedule is displayed to the host.
3. **Given** a host with an active room, **When** they view the room, **Then** they see the invite link, member list, and room configuration controls.
4. **Given** a host with an active room, **When** they close or finish the room, **Then** the room status changes to finished and it no longer appears as joinable.
5. **Given** a host viewing their hosted rooms list, **When** they check the list, **Then** they see all rooms they have created with their current status.
6. **Given** an active room where the host disconnects, **When** the disconnection is detected, **Then** host role transfers to the player who joined the room second, and all members are notified.
7. **Given** a room where the original host reconnects after a disconnection, **When** they rejoin, **Then** they immediately regain the host role and control privileges.

---

### User Story 3 - Joining & Inviting to Rooms (Priority: P1)

The host can add members directly from their friend list — these members are added immediately with no approval needed. Other players can join via an invite link, but the host must accept or reject each link-join request. Once in the room, members see the lobby and other participants.

**Why this priority**: Rooms are useless if players cannot join them. This completes the core lobby loop.

**Independent Test**: Host adds a friend directly from the friend list — that friend appears in the room immediately. Another user clicks the invite link — the host sees a join request and accepts it.

**Acceptance Scenarios**:

1. **Given** a host viewing the room, **When** they select a friend from their friend list and add them, **Then** the friend is added directly to the room with no approval step, and appears in the member list.
2. **Given** a user with a valid invite link, **When** they open the link while logged in, **Then** a join request is sent to the host for approval.
3. **Given** a user with a valid invite link, **When** they open the link while not logged in, **Then** they are redirected to login first, then the join request is sent to the host.
4. **Given** a host with a pending join request, **When** they accept it, **Then** the requesting player joins the room and appears in the member list.
5. **Given** a host with a pending join request, **When** they reject it, **Then** the requesting player is notified they were not accepted and the request is dismissed.
6. **Given** a user attempting to join a full room, **When** they use the invite link, **Then** they see a "Room is full" message.
7. **Given** a user attempting to join a room that is already finished, **When** they use the invite link, **Then** they see a "Room is no longer available" message.

---

### User Story 4 - Friend System (Priority: P2)

Users can send friend requests to other users, accept or decline incoming requests, and maintain a friend list. The friend list enables direct invites to rooms.

**Why this priority**: Friends enhance the social experience and streamline room invites, but the core room loop works without it (invite links alone suffice).

**Independent Test**: User A sends a friend request to User B. User B receives the request, accepts it, and both users see each other in their friend lists.

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** they search for another user by username and send a friend request, **Then** the request is delivered to the recipient.
2. **Given** a user with a pending friend request, **When** they accept it, **Then** both users appear in each other's friend lists.
3. **Given** a user with a pending friend request, **When** they decline it, **Then** the request is dismissed and neither user is added.
4. **Given** a user viewing their friend list, **When** they remove a friend, **Then** that user is removed from their friend list.
5. **Given** a user searching for friends, **When** they type a partial username, **Then** matching users are shown in real time.

---

### User Story 5 - Real-Time Room Updates (Priority: P2)

Players in a room see real-time updates: members joining/leaving, room status changes, and host changes. Updates are pushed to all room members without requiring manual refresh.

**Why this priority**: Real-time updates are essential for a smooth multiplayer lobby experience but the core room functions with polling if needed.

**Independent Test**: Two users are in a room lobby. A third user joins. Both existing members see the new member appear instantly without refreshing.

**Acceptance Scenarios**:

1. **Given** a user in a room lobby, **When** another player joins or leaves, **Then** the member list updates in real time.
2. **Given** a user in a room, **When** the host closes the room, **Then** all members receive a room-closed event.
3. **Given** a user in a room, **When** host role transfers to another player, **Then** all members see the new host indicator in real time.
4. **Given** a user with a temporarily unstable connection, **When** they reconnect, **Then** they receive the current room state (members, host, status) without data loss.

---

### Edge Cases

- What happens when the host disconnects? Host role transfers to the player who joined the room second. If the original host reconnects, they immediately regain the host role.
- What happens when two users try to join a room with the last available slot at the same time?
- How does the invite link behave after a room is finished?
- What happens when a user receives a friend request from someone they have already sent a request to?
- How does the system handle duplicate accounts (same email)?
- What happens when a user attempts to join a room they are already a member of?
- What happens when a scheduled room's time arrives but the host is offline? The room auto-transitions to "waiting" regardless of host presence.
- What happens to pending link join requests when the room becomes full? They auto-expire with a "room full" notification.

### Out of Scope (Phase 2)

The following are explicitly deferred to future phases and are NOT part of this specification:

- Game sessions, phase management (day/night cycle), and voting
- Role assignment and role-specific abilities (including on_elimination hooks)
- Voice and video controls (mute/unmute, enable/disable video)
- Game results, winner/loser determination, and player statistics
- Game host confirmation of voting and tie-breaking rules

These items were discussed during clarification but are scoped out of this phase. They will be addressed in a subsequent game-engine specification.

**Bugfix**: 2026-06-23 — BUG-001 Clarified that "original host" in FR-010 / US2/AC7 means the room creator (`created_by`, immutable), distinct from the current `host` (mutable on transfer). Added `created_by` to the Room entity definition.
**Bugfix**: 2026-06-23 — BUG-002 Added `cloudflare_participant_id` to RoomMember entity. Removed `participant_ids` from Room entity (per-member data, not room-level).

## Requirements *(mandatory)*

### Functional Requirements

**Account & Authentication**
- **FR-001**: System MUST allow users to register with a unique username, email, and password.
- **FR-002**: System MUST authenticate users and issue a session token on successful login.
- **FR-003**: System MUST reject unauthenticated access to any feature beyond login and registration.
- **FR-004**: System MUST enforce unique usernames and emails across all accounts.

**Room Management**
- **FR-005**: System MUST allow any authenticated user to create a game room, becoming its host.
- **FR-006**: System MUST generate a unique invite code/link for each room upon creation.
- **FR-007**: System MUST allow the host to configure room settings: maximum players, and which special roles will be available in the eventual game (e.g., toggle Detective on/off, Doctor on/off, Vigilante on/off).
- **FR-008**: System MUST track room status: scheduled, waiting, finished.
- **FR-008a**: System MUST allow the host to schedule a room for a future date and time. Scheduled rooms show their scheduled time and auto-transition to "waiting" status at the scheduled time.
- **FR-009**: System MUST allow the host to finish/close a room manually.
- **FR-010**: System MUST transfer host role to the player who joined second when the host disconnects. If the original host (room creator, tracked via `created_by`) reconnects, they regain the host role immediately.

**Invites & Joining**
- **FR-011**: System MUST allow the host to add members directly from their friend list without requiring approval — the added member joins the room immediately.
- **FR-012**: System MUST allow users to request to join a room via a valid invite link. Join requests via link require host approval (accept/reject).
- **FR-013**: System MUST redirect unauthenticated users to login before processing their link-based join request.
- **FR-014**: System MUST notify the host of pending link-based join requests in real time.
- **FR-015**: System MUST notify the requesting user when their link-based join request is accepted or rejected.
- **FR-016**: System MUST prevent users from joining (or requesting to join) a room that is full or finished.

**Friend System**
- **FR-017**: System MUST allow users to search for other users by username.
- **FR-018**: System MUST allow users to send, accept, and decline friend requests.
- **FR-019**: System MUST allow users to remove friends from their friend list.
- **FR-020**: System MUST show pending friend requests separately from accepted friends.

**Real-Time Updates**
- **FR-021**: System MUST push member join/leave events to all room members in real time.
- **FR-022**: System MUST push room status changes (room closed, host changed) to all room members in real time.
- **FR-023**: System MUST deliver the current room state (members, host, status) to a reconnecting player.

### Key Entities *(include if feature involves data)*

- **User**: Represents a player account. Key attributes: username (unique), email (unique), password hash, friend list.
- **FriendRequest**: Represents a pending friend connection. Key attributes: sender, recipient, status (pending/accepted/declined), timestamp.
- **Room**: Represents a game lobby. Key attributes: host (current, mutable on transfer), created_by (original creator, immutable), invite code (unique), max players, current members (via RoomMember reverse FK), meeting_id (Cloudflare), status (scheduled/waiting/finished), scheduled_at (optional datetime), role configuration (which special roles are enabled).
- **RoomMember**: Represents a player's membership in a room. Key attributes: user, room, joined_at, added_by (host-direct or link-request), cloudflare_participant_id (optional, for WebRTC integration).
- **RoomJoinRequest**: Represents a pending link-based join request. Key attributes: user, room, status (pending/accepted/rejected), requested_at, resolved_at.

## Clarifications

### Session 2026-06-22

- Q: Host disconnect handling → A: Host role transfers to the second player who joined. Original host regains host role on reconnect.
- Q: Role distribution configuration → A: Host toggles which special roles are available (on/off per role). System handles distribution automatically in the future game phase.
- Q: Phase 1 scope → A: This phase is scoped to room management only (accounts, rooms, invites, friends, real-time lobby updates). Game engine logic (phases, voting, roles, voice/video, results) is deferred to Phase 2.
- Q: Host adding members vs link joining → A: Host can add members directly from friend list (auto-join, no approval). Users joining via invite link require host accept/reject approval.
- Q: Room scheduling → A: Host can schedule a room for a future date/time. Scheduled rooms auto-transition to "waiting" status at the scheduled time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can register and reach the lobby in under 2 minutes.
- **SC-002**: Room creation completes in under 3 seconds and the invite link is immediately available.
- **SC-003**: Players joining a room see their membership reflected for all other members in under 2 seconds.
- **SC-004**: Real-time room updates (join/leave, host change, room close) are delivered to all room members in under 1 second.
- **SC-005**: System supports at least 10 concurrent rooms with 12 members each without degradation.

## Assumptions

- The system uses token-based authentication (JWT) with refresh tokens for session management.
- The minimum player count and game start logic are deferred to the game-engine phase.
- The default maximum room size is 12 players.
- Users are expected to have a stable internet connection; graceful degradation for poor connections is limited to reconnection state recovery.
- Friend search returns partial matches in real time as the user types (debounced).
- Voice and video functionality will integrate with a third-party real-time communication service in a future phase.
- Role configuration (toggling roles on/off in room settings) is captured now because it affects the room data model, but the actual role assignment and game logic are Phase 2.
