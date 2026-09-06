"""Action-signal routing.

Standard interface for tile signals: every game action can emit an
ActionSignal — a transient visual on the target's tile — and THIS module
decides who receives it. Handlers never hand-pick recipients; they call
`emit_action_signal` and the ACTION_REGISTRY (apps/game/engine/constants.py)
owns the policy via each action's signal_audience / signal_actor_visible:

    VOTE     -> everyone in the game (actor shown)
    REVENGE  -> everyone in the game (actor shown)
    KILL     -> alive mafia members (actor hidden)
    HEAL     -> the healer only (verification)
    SHOOT    -> the shooter only (verification)
    SILENCE  -> the silencer only (verification)
    DETECT   -> no signal (result is sent as detect_result instead)
    LYNCH    -> no signal (death is broadcast via phase logs)

Adding a new action signal = add its ActionDefinition to ACTION_REGISTRY;
nothing else changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.game.engine.constants import (
    ACTION_REGISTRY,
    ActionType,
    PlayerStatus,
    SignalAudience,
)
from apps.game.engine.roles.type import RoleType

from .events.game import ActionSignal
from .groups import UserGroup

if TYPE_CHECKING:
    from apps.game.engine.session import GameSession

    from .consumers import RealtimeConsumer


def signal_recipients(
    action_type: ActionType,
    game_session: GameSession,
    actor_id: int,
) -> tuple[list[int], bool]:
    """Return (recipient_ids, include_actor_id) for an action signal."""
    definition = ACTION_REGISTRY.get(action_type)
    if definition is None or definition.signal_audience == SignalAudience.NONE:
        return [], False

    players = game_session.players
    if definition.signal_audience == SignalAudience.EVERYONE:
        return [p.id for p in players], definition.signal_actor_visible
    if definition.signal_audience == SignalAudience.MAFIA_ONLY:
        return (
            [
                p.id
                for p in players
                if p.status == PlayerStatus.ALIVE
                and p.role is not None
                and p.role.role_type == RoleType.MAFIA
            ],
            definition.signal_actor_visible,
        )
    # SignalAudience.ACTOR_ONLY
    return [actor_id], definition.signal_actor_visible


async def emit_action_signal(
    consumer: RealtimeConsumer,
    game_session: GameSession,
    action_type: ActionType,
    actor_id: int,
    target_id: int,
) -> None:
    """Send an ActionSignal to each recipient's personal channel."""
    recipients, include_actor = signal_recipients(
        action_type, game_session, actor_id
    )
    for uid in recipients:
        await consumer.groups.emit(
            UserGroup(uid),
            ActionSignal(
                action_type=action_type.value,
                target_id=target_id,
                actor_id=actor_id if include_actor else None,
            ),
        )
