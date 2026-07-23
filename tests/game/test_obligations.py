import pytest
from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    MafiaRoleblocker,
    TownDoctor,
    TownVanilla,
)
from apps.game.engine.round import DayRound, NightRound


class TestObligations:
    def test_night_obligations_godfather_and_doctor(self):
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
            Player(id=3, role=TownVanilla()),
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()

        assert ActionType.KILL in round_.obligations.get(1, [])
        assert ActionType.HEAL in round_.obligations.get(2, [])
        assert 3 not in round_.obligations

    def test_mafia_kill_priority_chain(self):
        players = [
            Player(id=1, role=MafiaMember()),       # priority 3
            Player(id=2, role=MafiaRoleblocker()),  # priority 2
            Player(id=3, role=MafiaGodfather()),    # priority 1
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()

        assert ActionType.KILL in round_.obligations.get(3, [])
        assert ActionType.KILL not in round_.obligations.get(2, [])
        assert ActionType.KILL not in round_.obligations.get(1, [])

    def test_mafia_kill_fallback_when_godfather_dead(self):
        players = [
            Player(id=1, role=MafiaMember(), status=PlayerStatus.ALIVE),
            Player(id=2, role=MafiaRoleblocker(), status=PlayerStatus.ALIVE),
            Player(id=3, role=MafiaGodfather(), status=PlayerStatus.DEAD),
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()

        assert ActionType.KILL in round_.obligations.get(2, [])
        assert ActionType.KILL not in round_.obligations.get(1, [])

    def test_day_all_alive_must_vote(self):
        players = [
            Player(id=1, role=TownVanilla()),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.DEAD),
            Player(id=3, role=TownDoctor()),
        ]
        round_ = DayRound(round_number=1, members=players, phase=Phase.DAY)
        round_.compute_obligations()

        assert ActionType.VOTE in round_.obligations.get(1, [])
        assert ActionType.VOTE in round_.obligations.get(3, [])
        assert 2 not in round_.obligations

    @pytest.mark.asyncio
    async def test_is_player_done(self):
        players = [
            Player(id=1, role=TownDoctor()),
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()

        assert not await round_.is_player_done(1)

        round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.HEAL))
        assert await round_.is_player_done(1)

    @pytest.mark.asyncio
    async def test_is_round_done(self):
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        assert not await round_.is_round_done()

        round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.KILL))
        assert not await round_.is_round_done()

        round_.night_actions.append(Action(actor_id=2, target_id=1, action_type=ActionType.HEAL))
        assert await round_.is_round_done()
