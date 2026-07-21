"""Game domain handlers.

All events that belong to game session lifecycle: start, night actions,
day voting, phase resolution. ~15 events expected here.

Each inbound handler: @on(EventClass), signature (consumer, event).
Each outbound trampoline: @trampoline('type_string'), signature (consumer, event_dict).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.roles.type import RoleType
from apps.game.engine.round import GRACE_SECONDS
from apps.game.engine.session import GameSession
from apps.core.utils.uuid import generate_code

from ..dispatch import on, trampoline
from ..error_codes import ErrorCode
from ..events.game import (
    Detect,
    GameEvents,
    GameStarted,
    Heal,
    Kill,
    Revenge,
    RoleAssigned,
    Roleblock,
    Shoot,
    Silent,
    StartGame,
    SubmitVoteResult,
    SubmitVotes,
    SunRise,
    SunSet,
    Vote,
    VoteCast,
    VoteResultStarted,
)
from ..groups import GameSessionGroup, RoomActive

if TYPE_CHECKING:
    from ..consumers import RealtimeConsumer


# =========================================================================
# INBOUND handlers (@on)
# =========================================================================


@on(StartGame)
async def handle_start_game(consumer: RealtimeConsumer, event: StartGame) -> None:
    session = consumer.session
    if not await session.is_host(consumer.user):
        return
    player_ids = event.player_ids
    if len(player_ids) < 6:
        await consumer.send_error(ErrorCode.INVALID_PAYLOAD, 'At least 6 players are required to start a game')
        return
    for pid in player_ids:
        if not await session.is_member(pid):
            raise ValueError('Players should be members of the room')

    game_id = generate_code(length=16)
    game_session = await GameSession.start_new(
        id=game_id, room_id=consumer.code, player_ids=player_ids,
    )
    await game_session.new_round(phase=Phase.DAY)
    await session.set_game_session_id(game_id)

    alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        GameStarted(
            player_ids=player_ids,
            session_id=game_id,
            host=consumer.user.id,
            alive_ids=alive_ids,
        ),
    )


@on(Vote)
async def handle_vote(consumer: RealtimeConsumer, event: Vote) -> None:
    if not await _guard_phase(consumer, Phase.DAY):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.VOTE)
    )
    await consumer.groups.emit(
        GameSessionGroup(room_code=consumer.code, session_id=game_session.id),
        VoteCast(actor_id=consumer.user.id, target_id=event.target_id),
    )


@on(Kill)
async def handle_kill(consumer: RealtimeConsumer, event: Kill) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.KILL)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Revenge)
async def handle_revenge(consumer: RealtimeConsumer, event: Revenge) -> None:
    if not await _guard_phase(consumer, Phase.VOTE_RESULT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.REVENGE)
    )


@on(Heal)
async def handle_heal(consumer: RealtimeConsumer, event: Heal) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.HEAL)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Shoot)
async def handle_shoot(consumer: RealtimeConsumer, event: Shoot) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.SHOOT)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Detect)
async def handle_detect(consumer: RealtimeConsumer, event: Detect) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.DETECT)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Silent)
async def handle_silent(consumer: RealtimeConsumer, event: Silent) -> None:
    """Player explicitly skips their night action."""
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.SILENT)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Roleblock)
async def handle_roleblock(consumer: RealtimeConsumer, event: Roleblock) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.ROLEBLOCK)
    )
    await _try_auto_transition_night(consumer, game_session)


@on(SubmitVotes)
async def handle_submit_votes(consumer: RealtimeConsumer, event: SubmitVotes) -> None:
    """Resolve the DAY voting round and transition to the next phase.

    DAY → resolve → if lynch target → VoteResultStarted → new round (vote_result)
                   → if no lynch target → SunSet → new round (night)
    """
    if not await consumer.session.is_host(consumer.user):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return

    round_ = game_session.current_round()

    if round_.phase != Phase.DAY:
        await consumer.send_error(
            ErrorCode.WRONG_PHASE,
            'SubmitVotes is only allowed during the day phase',
        )
        return

    alive = round_.alive_player_ids()
    voters = await round_.voter_ids()
    if alive != voters:
        missing = alive - voters
        await consumer.send_error(
            ErrorCode.NOT_ALL_VOTED,
            f'Not all alive players have voted. Missing: {sorted(missing)}',
        )
        return

    logs = await round_.resolve()
    session_id = game_session.id
    group = GameSessionGroup(room_code=consumer.code, session_id=session_id)

    # DAY with a lynch target → transition to VOTE_RESULT phase.
    if round_.phase == Phase.DAY and round_.lynch_target_id is not None:
        await game_session.new_round(phase=Phase.VOTE_RESULT)
        await consumer.groups.emit(
            group,
            VoteResultStarted(lynch_target_id=round_.lynch_target_id, logs=logs),
        )
        return

    await _transition_after_resolve(game_session, round_, logs, consumer, group)


@on(SubmitVoteResult)
async def handle_submit_vote_result(consumer: RealtimeConsumer, event: SubmitVoteResult) -> None:
    """Resolve the VOTE_RESULT phase: carry out lynch + revenge, then start night."""
    if not await consumer.session.is_host(consumer.user):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return

    round_ = game_session.current_round()
    if round_.phase != Phase.VOTE_RESULT:
        await consumer.send_error(
            ErrorCode.WRONG_PHASE,
            'This action is only allowed during the vote result phase',
        )
        return

    logs = await round_.resolve()
    group = GameSessionGroup(room_code=consumer.code, session_id=game_session.id)
    await _transition_after_resolve(game_session, round_, logs, consumer, group)


# =========================================================================
# OUTBOUND trampolines (@trampoline)
# =========================================================================


@trampoline(GameEvents.GAME_STARTED)
async def game_started(consumer: RealtimeConsumer, event: dict) -> None:
    if consumer.user.id in event['player_ids']:
        await consumer.groups.join(
            GameSessionGroup(room_code=consumer.code, session_id=event['session_id'])
        )
    await consumer.send_json(
        GameStarted(
            player_ids=event['player_ids'],
            session_id=event['session_id'],
            host=event['host'],
            alive_ids=event['alive_ids'],
        ).to_json()
    )
    # Send each player their assigned role privately, then the initial
    # SunRise so they enter the first day phase (voting).
    if consumer.user.id in event['player_ids']:
        game_session = await GameSession.load(room_id=consumer.code)
        if game_session is not None:
            mafia_player_ids = [
                p.id for p in game_session.players
                if p.role is not None and p.role.role_type == RoleType.MAFIA
            ]
            for player in game_session.players:
                if player.id == consumer.user.id and player.role is not None:
                    is_mafia = player.role.role_type == RoleType.MAFIA
                    await consumer.send_json(
                        RoleAssigned(
                            role_name=player.role.name,
                            description=player.role.description,
                            role_type=player.role.role_type.value,
                            mafia_ids=mafia_player_ids if is_mafia else None,
                        ).to_json()
                    )
                    break
        await consumer.send_json(
            SunRise(player_ids=event['alive_ids'], logs=[]).to_json()
        )


@trampoline(GameEvents.SUN_SET)
async def sun_set(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        SunSet(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )


@trampoline(GameEvents.SUN_RISE)
async def sun_rise(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        SunRise(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )


@trampoline(GameEvents.VOTE_CAST)
async def vote_cast(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(
        VoteCast(actor_id=event['actor_id'], target_id=event['target_id']).to_json()
    )


@trampoline(GameEvents.VOTE_RESULT_STARTED)
async def vote_result_started(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        VoteResultStarted(
            lynch_target_id=event['lynch_target_id'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )


# =========================================================================
# Helpers
# =========================================================================


async def _try_auto_transition_night(
    consumer: RealtimeConsumer,
    game_session: GameSession,
) -> None:
    """Check if the night round is done. If so, start grace and auto-resolve."""
    round_ = game_session.current_round()
    if round_.phase != Phase.NIGHT:
        return
    if not await round_.is_round_done():
        return

    # Start the grace timer.
    round_.start_grace()
    await game_session.save()

    # Fire-and-forget: sleep grace period, then resolve.
    asyncio.create_task(_resolve_after_grace(consumer, game_session))


async def _resolve_after_grace(
    consumer: RealtimeConsumer,
    game_session: GameSession,
) -> None:
    """Sleep GRACE_SECONDS, then re-load and resolve the night round."""
    await asyncio.sleep(GRACE_SECONDS)

    # Re-load from Redis to pick up any optional actions submitted during grace.
    fresh = await GameSession.load(room_id=game_session.room_id)
    if fresh is None:
        return
    round_ = fresh.current_round()
    if round_.phase != Phase.NIGHT:
        return  # already transitioned

    logs = await round_.resolve()
    group = GameSessionGroup(room_code=consumer.code, session_id=fresh.id)
    await _transition_after_resolve(fresh, round_, logs, consumer, group)


async def _require_game(consumer: RealtimeConsumer) -> GameSession | None:
    game_session = await GameSession.load(room_id=consumer.code)
    if game_session is None:
        await consumer.send_error(ErrorCode.GAME_NOT_STARTED, 'No game in progress')
        return None
    return game_session


async def _transition_after_resolve(
    game_session: GameSession,
    round_: object,
    logs: list[str],
    consumer: RealtimeConsumer,
    group: object,
) -> None:
    """Emit the phase-transition event and start the next round.

    NIGHT       → new DAY round   → SunRise
    DAY         → new NIGHT round → SunSet   (no lynch target edge case)
    VOTE_RESULT → new NIGHT round → SunSet
    """
    if round_.phase == Phase.NIGHT:
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        if len(alive_ids) <= 1:
            await consumer.groups.emit(group, SunRise(player_ids=alive_ids, logs=logs))
            return
        await game_session.new_round(phase=Phase.DAY)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunRise(player_ids=alive_ids, logs=logs))
    else:
        # DAY (no lynch) or EXECUTION → transition to NIGHT.
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        if len(alive_ids) <= 1:
            await consumer.groups.emit(group, SunSet(player_ids=alive_ids, logs=logs))
            return
        await game_session.new_round(phase=Phase.NIGHT)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunSet(player_ids=alive_ids, logs=logs))


async def _guard_phase(consumer: RealtimeConsumer, expected: Phase) -> bool:
    """Return True if the current round phase matches *expected*, else send error."""
    game_session = await GameSession.load(room_id=consumer.code)
    if game_session is None:
        await consumer.send_error(ErrorCode.GAME_NOT_STARTED, 'No game in progress')
        return False
    round_ = game_session.current_round()
    if round_.phase != expected:
        await consumer.send_error(
            ErrorCode.WRONG_PHASE,
            f'This action is only allowed during the {expected.value} phase',
        )
        return False
    return True
