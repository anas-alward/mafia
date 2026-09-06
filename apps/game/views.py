"""REST endpoints for game engine state.

The game itself is WebSocket-driven; these endpoints expose read-only
queries over the in-memory/Redis engine session. Views are NATIVELY async
so the shared async redis client always runs on the server's main event
loop (sync views would trap it on a throwaway loop via async_to_sync).
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.redis import redis_client
from apps.game.engine.session import GameSession
from apps.room.session import RoomSession

_jwt_auth = JWTAuthentication()


async def _authenticate(request: HttpRequest) -> Any | None:
    """Resolve the SimpleJWT user for a plain Django request, or None."""

    def _auth() -> Any | None:
        header = _jwt_auth.get_header(request)
        if header is None:
            return None
        raw = _jwt_auth.get_raw_token(header)
        if raw is None:
            return None
        validated = _jwt_auth.get_validated_token(raw)
        return _jwt_auth.get_user(validated)

    return await sync_to_async(_auth)()


async def _find_room_code_for_session(session_id: str) -> str | None:
    """Locate the room code whose current game session matches session_id.

    The engine keys sessions by room_id, and no reverse index exists, so
    scan the room hashes for a matching game_session_id.
    """
    async for key in redis_client.scan_iter(match='room:*'):
        key_str = key.decode() if isinstance(key, bytes) else key
        parts = key_str.split(':')
        if len(parts) != 2:
            continue  # skip suffixed keys (members, waiting, ...)
        val = await redis_client.hget(key_str, 'game_session_id')
        if val is None:
            continue
        stored = val.decode() if isinstance(val, bytes) else val
        if stored == session_id:
            return parts[1]
    return None


async def _collect_voters(
    session_id: str, player_id: int, user: Any
) -> list[int] | None:
    """Resolve the voters for one player, or None if not found/allowed."""
    room_code = await _find_room_code_for_session(session_id)
    if room_code is None:
        return None
    room_session = await RoomSession.from_code(room_code)
    if room_session is None or not await room_session.is_member(user.id):
        return None
    game_session = await GameSession.load(room_id=room_code)
    if game_session is None or game_session.id != session_id:
        return None
    if player_id not in {p.id for p in game_session.players}:
        return None
    return await game_session.current_round().voter_ids_for(player_id)


async def game_session_player_voters(
    request: HttpRequest, session_id: str, player_id: int
) -> JsonResponse:
    """GET /game-session/<session_id>/players/<player_id>/voters/

    Returns the IDs of players whose CURRENT vote targets the player.
    Respects revotes: only each actor's last vote in the round counts.
    """
    user = await _authenticate(request)
    if user is None:
        return JsonResponse(
            {'detail': 'Authentication credentials were not provided.'},
            status=401,
        )
    voter_ids = await _collect_voters(session_id, player_id, user)
    if voter_ids is None:
        return JsonResponse(
            {'detail': 'game session or player not found'},
            status=404,
        )
    return JsonResponse({'voter_ids': voter_ids})
