# Quickstart Validation Guide: Lobby Creation & Room Management

**Feature**: [spec.md](./spec.md)
**Date**: 2026-06-23

## Prerequisites

- Docker and docker-compose installed
- Cloudflare account with Realtime Kit app configured (env vars: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_APP_ID`)
- Python 3.14+ (for local dev)

## Setup

```bash
# Clone and start services
docker-compose up -d

# Run migrations
docker-compose exec backend python manage.py migrate

# Create test users (via API or shell)
# Option A: Register via curl
curl -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@test.com","password":"testpass123"}'

curl -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","email":"bob@test.com","password":"testpass123"}'

curl -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"charlie","email":"charlie@test.com","password":"testpass123"}'
```

## Validation Scenarios

### SC-001: Registration → Lobby in <2 minutes

```bash
# Register and get tokens
TOKEN_ALICE=$(curl -s -X POST http://localhost:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"dave","email":"dave@test.com","password":"testpass123"}' | jq -r '.access')

# Verify authenticated access
curl -H "Authorization: Bearer $TOKEN_ALICE" http://localhost:8000/api/rooms/
# Expected: 200 with {"count":0,"results":[]}

# Verify unauthenticated access is blocked
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/rooms/
# Expected: 401
```

### SC-002: Room Creation in <3 seconds

```bash
# Create a room
ROOM_RESPONSE=$(curl -s -X POST http://localhost:8000/api/rooms/create/ \
  -H "Authorization: Bearer $TOKEN_ALICE" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Room","max_members":8}')

echo $ROOM_RESPONSE | jq '.room.code'
# Expected: 6-char uppercase code, response in <3s

ROOM_CODE=$(echo $ROOM_RESPONSE | jq -r '.room.code')

# Verify room appears in hosted rooms
curl -s -H "Authorization: Bearer $TOKEN_ALICE" http://localhost:8000/api/rooms/ | jq '.results[0].host'
# Expected: "alice"
```

### SC-003: Friend System

```bash
TOKEN_BOB=$(curl -s -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","password":"testpass123"}' | jq -r '.access')

# Alice sends friend request to Bob
curl -s -X POST http://localhost:8000/api/friends/requests/send/ \
  -H "Authorization: Bearer $TOKEN_ALICE" \
  -H "Content-Type: application/json" \
  -d '{"username":"bob"}'
# Expected: 201 {"id":1,"status":"pending"}

# Bob accepts
REQUEST_ID=$(curl -s -H "Authorization: Bearer $TOKEN_BOB" \
  http://localhost:8000/api/friends/requests/incoming/ | jq -r '.requests[0].id')

curl -s -X POST http://localhost:8000/api/friends/requests/$REQUEST_ID/accept/ \
  -H "Authorization: Bearer $TOKEN_BOB"
# Expected: 200 {"id":1,"status":"accepted"}

# Both see each other in friend list
curl -s -H "Authorization: Bearer $TOKEN_ALICE" http://localhost:8000/api/friends/ | jq '.friends'
# Expected: [{"id":2,"username":"bob"}]

curl -s -H "Authorization: Bearer $TOKEN_BOB" http://localhost:8000/api/friends/ | jq '.friends'
# Expected: [{"id":1,"username":"alice"}]
```

### SC-004: Room Joining (Friend Direct Add vs Link Request)

```bash
# Host (Alice) adds friend (Bob) directly
curl -s -X POST http://localhost:8000/api/rooms/$ROOM_CODE/add/ \
  -H "Authorization: Bearer $TOKEN_ALICE" \
  -H "Content-Type: application/json" \
  -d '{"user_id":2}'
# Expected: 200 with room data, Bob added immediately

# Charlie joins via invite link (not a friend)
TOKEN_CHARLIE=$(curl -s -X POST http://localhost:8000/api/accounts/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"charlie","password":"testpass123"}' | jq -r '.access')

curl -s -X POST http://localhost:8000/api/rooms/$ROOM_CODE/join/ \
  -H "Authorization: Bearer $TOKEN_CHARLIE"
# Expected: 200 {"request_id":...,"status":"pending"}

# Host sees pending request and accepts
JOIN_REQ_ID=$(curl -s -H "Authorization: Bearer $TOKEN_ALICE" \
  http://localhost:8000/api/rooms/$ROOM_CODE/join-requests/ | jq -r '.requests[0].id')

curl -s -X POST http://localhost:8000/api/rooms/$ROOM_CODE/join-requests/$JOIN_REQ_ID/accept/ \
  -H "Authorization: Bearer $TOKEN_ALICE"
# Expected: 200 with room data, Charlie added
```

### SC-005: Real-Time Updates via WebSocket

```bash
# Install a WebSocket client (if not available)
pip install websocket-client

# Connect to room WebSocket (requires token)
# Use a simple script or wscat:
# wscat -c "ws://localhost:8000/ws/room/$ROOM_CODE/?token=$TOKEN_ALICE"
# Expected: room_state event, then player_joined/player_left as users connect/disconnect
```

### Host Transfer

```bash
# 1. Alice (host) creates room
# 2. Bob joins
# 3. Alice disconnects → Bob becomes host (verify via WebSocket host_changed event)
# 4. Alice reconnects → Alice regains host role
```

### Room Finish

```bash
curl -s -X POST http://localhost:8000/api/rooms/$ROOM_CODE/finish/ \
  -H "Authorization: Bearer $TOKEN_ALICE"
# Expected: 200 with room.status="finished"

# Verify room no longer joinable
curl -s -X POST http://localhost:8000/api/rooms/$ROOM_CODE/join/ \
  -H "Authorization: Bearer $TOKEN_CHARLIE"
# Expected: 400 with error
```

## Running Tests

```bash
# Install test dependencies
uv pip install pytest pytest-django pytest-asyncio

# Run the test suite
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=apps --cov-report=term-missing
```
