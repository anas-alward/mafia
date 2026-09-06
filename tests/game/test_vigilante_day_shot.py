"""Vigilante day shot + Mafia King dying revenge.

Covers:
- shooting the Mafia King during the day: king dies, vigilante stays, the
  King's dying revenge triggers in vote-result
- shooting a Town player: both die
- ammo: two shots per game, the shot replaces the vote

Runs inside ONE event loop — the shared async redis client binds its
connections to the loop that first used them.
"""

import asyncio

from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    TownDoctor,
    TownVigilante,
    TownVanilla,
)
from apps.game.engine.session import GameSession
from apps.core.redis import redis_client

ROOM = 'DAYSHOT1'


def make_session(session_id: str) -> GameSession:
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=TownDoctor()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVigilante()),
        Player(id=5, role=MafiaMember()),
    ]
    return GameSession(id=session_id, room_id=ROOM, players=players)


def test_vigilante_day_shot_and_dying_revenge():
    async def flow():
        # Flush first — earlier crashed runs may have left stale state in
        # the test-settings redis db.
        await GameSession.flush_room(ROOM)
        session = make_session('dayshot1')
        try:
            day = await session.new_round(phase=Phase.DAY)

            # The vigilante's required actions include both vote and shoot.
            req = day.get_required_actions_for_player(4)
            types = [r['action_type'] for r in req]
            assert types == ['vote', 'shoot']
            shoot = next(r for r in req if r['action_type'] == 'shoot')
            assert set(shoot['target_options']) == {1, 2, 3, 5}

            # Shoot the Mafia King (mafia target -> vigilante stays).
            await day.add_action(
                Action(actor_id=4, target_id=1, action_type=ActionType.SHOOT)
            )
            logs = await day.resolve()

            shoot_logs = [
                log for log in logs if log['action_type'] == 'shoot'
            ]
            assert len(shoot_logs) == 1
            assert shoot_logs[0]['target_id'] == 1
            assert shoot_logs[0]['role_name'] == 'Mafia King'
            assert session.players[0].status == PlayerStatus.DEAD
            assert session.players[3].status == PlayerStatus.ALIVE

            # The King's dying revenge triggers in vote-result. The whole
            # world is a valid target, including the vigilante.
            assert session.pending_dying_revenge == [1]
            vr = await session.new_round(
                phase=Phase.VOTE_RESULT, lynch_target_id=None
            )
            assert ActionType.REVENGE in vr.obligations.get(1, [])
            req = vr.get_required_actions_for_player(1)
            assert set(req[0]['target_options']) == {2, 3, 4, 5}

            await vr.add_action(
                Action(actor_id=1, target_id=2, action_type=ActionType.REVENGE)
            )
            await vr.resolve()
            assert session.players[1].status == PlayerStatus.DEAD
            assert session.pending_dying_revenge == []

            # Ammo: one bullet spent — the shot is still offered.
            day2 = await session.new_round(phase=Phase.DAY)
            req = day2.get_required_actions_for_player(4)
            assert 'shoot' in [r['action_type'] for r in req]

            # Second (final) shot on the last mafia — vigilante survives.
            await day2.add_action(
                Action(actor_id=4, target_id=5, action_type=ActionType.SHOOT)
            )
            # A shoot replaces the vote for round completion.
            assert await day2.is_player_done(4) is True

            await day2.resolve()
            assert session.players[3].status == PlayerStatus.ALIVE
            assert session.players[1].status == PlayerStatus.DEAD

            # Ammo spent: the shot is no longer offered, and without a
            # vote the vigilante is no longer done on their own.
            day3 = await session.new_round(phase=Phase.DAY)
            req = day3.get_required_actions_for_player(4)
            assert 'shoot' not in [r['action_type'] for r in req]
            assert await day3.is_player_done(4) is False
        finally:
            await GameSession.flush_room(ROOM)
            # Close pooled connections so the next asyncio.run's fresh
            # event loop reconnects cleanly.
            await redis_client.aclose()

    asyncio.run(flow())


def test_vigilante_shooting_town_eliminates_both():
    async def flow():
        await GameSession.flush_room(ROOM)
        session = make_session('dayshot2')
        try:
            day = await session.new_round(phase=Phase.DAY)
            # Shoot the vanilla townie -> the vigilante goes down too.
            await day.add_action(
                Action(actor_id=4, target_id=3, action_type=ActionType.SHOOT)
            )
            logs = await day.resolve()

            assert session.players[2].status == PlayerStatus.DEAD
            assert session.players[3].status == PlayerStatus.DEAD
            died_logs = [log for log in logs if log['action_type'] == 'died']
            assert len(died_logs) == 1
            assert died_logs[0]['target_id'] == 4
            # No revenge: the victim has no vote-result revenge actions.
            assert session.pending_dying_revenge == []

            # The dead vigilante gets no further required actions.
            day2 = await session.new_round(phase=Phase.DAY)
            assert day2.get_required_actions_for_player(4) == []
        finally:
            await GameSession.flush_room(ROOM)
            # Close pooled connections so the next asyncio.run's fresh
            # event loop reconnects cleanly.
            await redis_client.aclose()

    asyncio.run(flow())
