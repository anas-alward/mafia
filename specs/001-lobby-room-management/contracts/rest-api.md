# REST API Contracts: Lobby Creation & Room Management

**Feature**: [spec.md](../spec.md)
**Date**: 2026-06-23

All endpoints use `/api/` prefix. Authentication via `Authorization: Bearer <access_token>` header.

## Accounts — `/api/accounts/`

### POST /api/accounts/register/

Register a new user account.

- **Auth**: None
- **Request**: `{ "username": string, "email": string, "password": string }`
- **Response 201**: `{ "id": int, "username": string, "email": string, "access": string, "refresh": string }`
- **Errors**: 400 (validation — username/email taken, weak password)

### POST /api/accounts/login/

Authenticate and receive tokens.

- **Auth**: None
- **Request**: `{ "username": string, "password": string }`
- **Response 200**: `{ "access": string, "refresh": string }`
- **Errors**: 401 (invalid credentials)

### POST /api/accounts/logout/

Invalidate refresh token.

- **Auth**: Bearer
- **Request**: `{ "refresh": string }`
- **Response 200**: `{}`
- **Errors**: 400 (invalid token)

### POST /api/accounts/refresh/

Obtain new access token from refresh token.

- **Auth**: None
- **Request**: `{ "refresh": string }`
- **Response 200**: `{ "access": string }`
- **Errors**: 401 (invalid/expired refresh token)

## Rooms — `/api/rooms/`

### GET /api/rooms/

List rooms hosted by authenticated user.

- **Auth**: Bearer
- **Response 200**: `{ "count": int, "next": string|null, "previous": string|null, "results": [Room] }`
- **Room object**: `{ "id": int, "name": string, "code": string, "host": string, "max_members": int, "member_count": int, "status": "scheduled"|"waiting"|"playing"|"finished", "scheduled_at": string|null, "role_configuration": object, "meeting_id": string, "created_at": string, "updated_at": string }`

### POST /api/rooms/create/

Create a new room. Authenticated user becomes host.

- **Auth**: Bearer
- **Request**: `{ "name": string, "max_members": int (4-20), "scheduled_at": string|null (ISO 8601), "role_configuration": object|null }`
- **Response 201**: `{ "room": Room, "participant_id": string, "token": string }`
- **Errors**: 400 (validation)

### POST /api/rooms/{code}/join/

Request to join a room via invite link.

- **Auth**: Bearer
- **Request**: (none)
- **Response 200**: `{ "request_id": int, "status": "pending" }` — join request sent to host for approval
- **Response 201**: `{ "room": Room, "participant_id": string, "token": string }` — if user was added directly
- **Errors**: 404 (room not found), 400 (full/finished/already member)

### GET /api/rooms/{code}/members/

List members of a room.

- **Auth**: Bearer (must be a member or host)
- **Response 200**: `{ "host": { "id": int, "username": string }, "member_count": int, "max_members": int, "members": [{ "id": int, "username": string, "joined_at": string }] }`
- **Errors**: 404, 403

### POST /api/rooms/{code}/add/

Host adds a friend directly to the room (no approval).

- **Auth**: Bearer (host only)
- **Request**: `{ "user_id": int }`
- **Response 200**: `{ "room": Room, "user_id": int, "username": string, "participant_id": string, "token": string }`
- **Errors**: 404, 403, 400 (full/playing/already member/not friend)

### POST /api/rooms/{code}/remove/

Host removes a member from the room.

- **Auth**: Bearer (host only)
- **Request**: `{ "user_id": int }`
- **Response 200**: `{ "room": Room, "removed_user_id": int, "removed_username": string }`
- **Errors**: 404, 403, 400 (cannot remove self)

### POST /api/rooms/{code}/finish/

Host finishes/closes the room.

- **Auth**: Bearer (host only)
- **Response 200**: `{ "room": Room }`
- **Errors**: 404, 403, 400 (already finished)

### GET /api/rooms/{code}/join-requests/

Host lists pending join requests for a room.

- **Auth**: Bearer (host only)
- **Response 200**: `{ "requests": [{ "id": int, "user_id": int, "username": string, "requested_at": string }] }`

### POST /api/rooms/{code}/join-requests/{request_id}/accept/

Host accepts a link-join request.

- **Auth**: Bearer (host only)
- **Response 200**: `{ "room": Room, "user_id": int, "username": string, "participant_id": string, "token": string }`
- **Errors**: 404, 403, 400 (room full/finished, request not pending)

### POST /api/rooms/{code}/join-requests/{request_id}/reject/

Host rejects a link-join request.

- **Auth**: Bearer (host only)
- **Response 200**: `{ "status": "rejected" }`
- **Errors**: 404, 403, 400 (request not pending)

## Friends — `/api/friends/`

### GET /api/friends/

List accepted friends.

- **Auth**: Bearer
- **Response 200**: `{ "friends": [{ "id": int, "username": string }] }`

### GET /api/friends/requests/incoming/

List pending friend requests sent to the authenticated user.

- **Auth**: Bearer
- **Response 200**: `{ "requests": [{ "id": int, "sender_id": int, "sender_username": string, "created_at": string }] }`

### GET /api/friends/requests/outgoing/

List pending friend requests sent by the authenticated user.

- **Auth**: Bearer
- **Response 200**: `{ "requests": [{ "id": int, "recipient_id": int, "recipient_username": string, "created_at": string }] }`

### GET /api/friends/search/?q={username}

Search users by partial username match.

- **Auth**: Bearer
- **Query**: `q` — partial username (min 1 char)
- **Response 200**: `{ "users": [{ "id": int, "username": string }] }`

### POST /api/friends/requests/send/

Send a friend request.

- **Auth**: Bearer
- **Request**: `{ "username": string }`
- **Response 201**: `{ "id": int, "status": "pending" }`
- **Response 201**: `{ "id": int, "status": "accepted" }` — if mutual pending request already existed (auto-accept)
- **Errors**: 404 (user not found), 400 (already friends, request already pending, cannot friend self)

### POST /api/friends/requests/{id}/accept/

Accept a pending friend request.

- **Auth**: Bearer (must be recipient)
- **Response 200**: `{ "id": int, "status": "accepted" }`
- **Errors**: 404, 403, 400 (not a pending request)

### POST /api/friends/requests/{id}/decline/

Decline a pending friend request.

- **Auth**: Bearer (must be recipient)
- **Response 200**: `{ "id": int, "status": "declined" }`
- **Errors**: 404, 403, 400 (not a pending request)

### DELETE /api/friends/{user_id}/

Remove a friend.

- **Auth**: Bearer
- **Response 204**: (no content)
- **Errors**: 404 (not friends)

## Error Format (Uniform — per Constitution §IV)

All error responses follow this structure:

```json
{
  "error": "Human-readable error message",
  "details": { "field_name": ["Validation error 1", "Validation error 2"] }
}
```

`details` is present only for validation errors (400).
