import pytest

from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaSilencer,
    TownBomb,
    TownDoctor,
    TownVanilla,
)
from apps.game.engine.round import DayRound, NightRound, VoteResultRound


def test_last_actions_keeps_last_occurrence():
    round_ = NightRound(round_number=1, members=[], phase=Phase.NIGHT)
    actions = [
        Action(actor_id=1, target_id=2, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=3, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=5, action_type=ActionType.SILENCE),
        Action(actor_id=2, target_id=4, action_type=ActionType.KILL),
    ]

    result = round_._last_actions(actions)

    by_key = {(a.actor_id, a.action_type): a.target_id for a in result}
    assert by_key == {
        (1, ActionType.KILL): 3,
        (1, ActionType.SILENCE): 5,
        (2, ActionType.KILL): 4,
    }


@pytest.mark.asyncio
async def test_night_change_of_mind_kill():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))

    logs = await round_.resolve()

    assert players[1].status == PlayerStatus.ALIVE  # first target survives
    assert players[2].status == PlayerStatus.DEAD   # final target dies
    kill_logs = [entry for entry in logs if entry['action_type'] == 'kill']
    assert kill_logs == [
        {'target_id': 3, 'action_type': 'kill', 'role_code': 'vanilla', 'role_name': 'Vanilla Townie'}
    ]


@pytest.mark.asyncio
async def test_night_change_of_mind_heal():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=TownDoctor()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.HEAL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.HEAL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.DEAD   # A killed (heal on A discarded)
    assert players[3].status == PlayerStatus.ALIVE  # B healed
    heal_logs = [entry for entry in logs if entry['action_type'] == 'heal']
    assert heal_logs == [{'target_id': 4, 'action_type': 'heal'}]


@pytest.mark.asyncio
async def test_silencer_keeps_both_actions():
    players = [
        Player(id=1, role=MafiaSilencer()),
        Player(id=2, role=TownDoctor()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.SILENCE))
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=1, target_id=4, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.HEAL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.ALIVE  # abandoned kill target survives
    assert players[3].status == PlayerStatus.ALIVE  # healed — silence no longer blocks
    assert {'target_id': 2, 'action_type': 'silence'} in logs
    kill_logs = [entry for entry in logs if entry['action_type'] == 'kill']
    assert kill_logs == [{'target_id': 4, 'action_type': 'kill', 'result': 'healed'}]


@pytest.mark.asyncio
async def test_non_designated_killer_ignored():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=MafiaSilencer()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.KILL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.DEAD   # Godfather's target dies
    assert players[3].status == PlayerStatus.ALIVE  # Silencer's kill ignored
    kill_logs = [entry for entry in logs if entry['action_type'] == 'kill']
    assert kill_logs == [
        {'target_id': 3, 'action_type': 'kill', 'role_code': 'vanilla', 'role_name': 'Vanilla Townie'}
    ]


@pytest.mark.asyncio
async def test_day_vote_change_of_mind():
    players = [
        Player(id=1, role=TownVanilla()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = DayRound(round_number=1, members=players, phase=Phase.DAY)
    round_.compute_obligations()
    round_.day_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=3, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=4, target_id=2, action_type=ActionType.VOTE))

    logs = await round_.resolve()

    assert round_.lynch_target_id == 3
    vote_entries = [entry for entry in logs if entry['action_type'] == 'vote']
    assert vote_entries == [
        {'actor_id': 1, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 2, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 3, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 4, 'target_id': 2, 'action_type': 'vote'},
    ]


@pytest.mark.asyncio
async def test_revenge_dedup():
    players = [
        Player(id=1, role=TownVanilla()),
        Player(id=2, role=TownBomb()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = VoteResultRound(
        round_number=1, members=players, phase=Phase.VOTE_RESULT, lynch_target_id=2
    )
    round_.compute_obligations()
    round_.day_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.REVENGE))
    round_.day_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.REVENGE))

    logs = await round_.resolve()

    assert players[1].status == PlayerStatus.DEAD   # lynched
    assert players[2].status == PlayerStatus.ALIVE  # abandoned revenge target survives
    assert players[3].status == PlayerStatus.DEAD   # final revenge target dies
    revenge_logs = [entry for entry in logs if entry['action_type'] == 'revenge']
    assert revenge_logs == [
        {
            'actor_id': 2,
            'target_id': 4,
            'action_type': 'revenge',
            'role_code': 'vanilla',
            'role_name': 'Vanilla Townie',
        }
    ]


def test_silenced_target_ids():
    players = [
        Player(id=1, role=MafiaSilencer()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla(), status=PlayerStatus.DEAD),
    ]

    living = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    living.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.SILENCE))
    assert living.silenced_target_ids() == [2]

    dead = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    dead.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.SILENCE))
    assert dead.silenced_target_ids() == []
