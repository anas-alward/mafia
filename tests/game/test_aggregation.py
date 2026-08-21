from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase
from apps.game.engine.round import NightRound


def test_last_actions_keeps_last_occurrence():
    round_ = NightRound(round_number=1, members=[], phase=Phase.NIGHT)
    actions = [
        Action(actor_id=1, target_id=2, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=3, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=5, action_type=ActionType.ROLEBLOCK),
        Action(actor_id=2, target_id=4, action_type=ActionType.KILL),
    ]

    result = round_._last_actions(actions)

    by_key = {(a.actor_id, a.action_type): a.target_id for a in result}
    assert by_key == {
        (1, ActionType.KILL): 3,
        (1, ActionType.ROLEBLOCK): 5,
        (2, ActionType.KILL): 4,
    }
