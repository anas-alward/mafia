# WebSocket Event Contracts: Lobby Creation & Room Management

**Feature**: [spec.md](../spec.md)
**Date**: 2026-06-23

## Connection

**Endpoint**: `ws://<host>/ws/room/<code>/`

**Authentication**: JWT token via query string (`?token=<access_token>`) or `Authorization: Bearer <token>` header.

**Connection lifecycle**:
1. Client connects with token.
2. Server authenticates via `JWTAuthMiddleware`.
3. Server verifies room exists and status != FINISHED.
4. Server adds user to room members (if not already) and to the Channels group.
5. Server sends `room_state` event to the connecting client only.
6. Server broadcasts `player_joined` to the room group.
7. On disconnect: remove from group, broadcast `player_left`. If disconnected user was host, transfer host and broadcast `host_changed`.

**Error codes**:
- `4001`: Invalid or missing authentication
- `4002`: Room not found or room is finished

## Server → Client Events

### room_state

Sent to a client immediately after connection, before joining the group broadcast. Provides full current room state.

```json
{
  "type": "room_state",
  "room": {
    "code": "A1B2C3D4",
    "name": "Friday Night Mafia",
    "status": "waiting",
    "host": { "id": 1, "username": "alice" },
    "max_members": 12,
    "role_configuration": { "detective": true, "doctor": true, "vigilante": false },
    "scheduled_at": null
  },
  "members": [
    { "id": 1, "username": "alice", "joined_at": "2026-06-23T10:00:00Z", "is_host": true },
    { "id": 2, "username": "bob", "joined_at": "2026-06-23T10:00:05Z", "is_host": false }
  ],
  "member_count": 2
}
```

### player_joined

Broadcast to all room members when a player joins.

```json
{
  "type": "player_joined",
  "user_id": 2,
  "username": "bob",
  "member_count": 2
}
```

### player_left

Broadcast to all remaining room members when a player disconnects or is removed.

```json
{
  "type": "player_left",
  "user_id": 2,
  "username": "bob",
  "member_count": 1
}
```

### host_changed

Broadcast when host role transfers (host disconnects or original host reconnects).

```json
{
  "type": "host_changed",
  "previous_host_id": 1,
  "previous_host_username": "alice",
  "new_host_id": 2,
  "new_host_username": "bob",
  "reason": "host_disconnected"
}
```

`reason` values: `"host_disconnected"` — host disconnected, role transferred. `"host_reconnected"` — original host reconnected and regained role.

### join_request_received

Sent to host when a user requests to join via invite link.

```json
{
  "type": "join_request_received",
  "request_id": 42,
  "user_id": 3,
  "username": "charlie"
}
```

### join_request_resolved

Sent to the requesting user when their join request is accepted or rejected.

```json
{
  "type": "join_request_resolved",
  "room_code": "A1B2C3D4",
  "room_name": "Friday Night Mafia",
  "status": "accepted"
}
```

### room_closed

Broadcast to all members when host finishes/closes the room.

```json
{
  "type": "room_closed",
  "room_code": "A1B2C3D4"
}
```

### member_removed

Sent to the specific user when they are removed by the host (before disconnect).

```json
{
  "type": "member_removed",
  "room_code": "A1B2C3D4"
}
```

## Client → Server Events

### chat

Send a chat message to all room members.

```json
{
  "type": "chat",
  "message": "Hey everyone!"
}
```

Server broadcasts as:

```json
{
  "type": "chat_message",
  "user_id": 1,
  "username": "alice",
  "message": "Hey everyone!"
}
```

### start_game

Host starts the game. Server creates a GameSession, assigns roles, sets room status to PLAYING.

```json
{
  "type": "start_game"
}
```

Server broadcasts:

```json
{
  "type": "game_started",
  "session_id": 5,
  "host": "alice"
}
```

Error (if sender is not host): silently ignored on consumer side (no broadcast).

## Event Delivery Guarantees

- Events are delivered via Redis pub/sub through Django Channels layer.
- At-most-once delivery: no acknowledgment or retry. Disconnected clients receive current state on reconnect via `room_state`.
- Events are NOT persisted; they are ephemeral. The authoritative state is in PostgreSQL.
