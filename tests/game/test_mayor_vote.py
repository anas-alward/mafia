import pytest

from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase
from apps.game.engine.player import Player
from apps.game.engine.roles.type import ROLE_REGISTRY, BaseRole, TownMayor, TownVanilla
from apps.game.engine.round import DayRound


def test_only_mayor_has_weight_3():
    for role in ROLE_REGISTRY.values():
        expected = 3 if role.code == 'mayor' else 1
        assert role.vote_weight == expected, role.code


def test_mayor_in_registry():
    assert isinstance(ROLE_REGISTRY['mayor'], BaseRole)
    assert ROLE_REGISTRY['mayor'].vote_weight == 3


@pytest.mark.asyncio
async def test_mayor_vote_counts_as_three():
    players = [
        Player(id=1, role=TownMayor()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = DayRound(round_number=1, members=players, phase=Phase.DAY)
    round_.day_actions.append(Action(actor_id=1, target_id=4, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=3, target_id=3, action_type=ActionType.VOTE))

    await round_.resolve()

    # Mayor's 3 votes beat the two vanilla votes (2).
    assert round_.lynch_target_id == 4


@pytest.mark.asyncio
async def test_mayor_weight_applies_to_class_roles():
    # RoleDistributor assigns role classes, not instances.
    players = [
        Player(id=1, role=TownMayor),
        Player(id=2, role=TownVanilla),
        Player(id=3, role=TownVanilla),
    ]
    round_ = DayRound(round_number=1, members=players, phase=Phase.DAY)
    round_.day_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=2, target_id=2, action_type=ActionType.VOTE))

    await round_.resolve()

    assert round_.lynch_target_id == 3
