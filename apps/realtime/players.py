"""Public player view-models shared across game events.

Single source of truth for the per-player entries sent in `game_state`
(reconnect), `game_started` and `game_reset`. Keeping the shape identical
across all three means clients always have an id → name map while a game
is running, regardless of whether they saw the game start or reconnected
mid-game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.game.engine.constants import PlayerStatus

if TYPE_CHECKING:
    from apps.game.engine.session import GameSession
    from apps.room.session import RoomSession


async def build_public_players(
    room_session: RoomSession, game_session: GameSession
) -> list[dict[str, Any]]:
    """Build the public per-player entries for game events.

    Names are resolved from the room session members. Dead players also
    carry their revealed role (it is public information once they die).
    """
    member_names = {m.user_id: m.name for m in await room_session.list_members()}
    players: list[dict[str, Any]] = []
    for p in game_session.players:
        entry: dict[str, Any] = {
            'id': p.id,
            'code': p.code,
            'status': p.status.value,
            'name': member_names.get(p.id),
        }
        if p.status == PlayerStatus.DEAD and p.role is not None:
            # Role reveal persists in game state so reconnecting clients
            # keep dead players' roles.
            entry['role_code'] = p.role.code
            entry['role_name'] = p.role.name
        players.append(entry)
    return players
