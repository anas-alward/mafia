"""Game domain handlers.

All events that belong to game session lifecycle: start, night actions,
day voting, phase resolution. ~15 events expected here.

Each inbound handler: @on(EventClass), signature (consumer, event).
Each outbound trampoline: @trampoline('type_string'), signature (consumer, event_dict).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from apps.core.livekit import livekit_client
from apps.core.utils.uuid import generate_code
from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus, VIGILANTE_AMMO
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    MafiaSilencer,
    RoleType,
    TownCop,
    TownDoctor,
    TownVigilante,
)
from apps.game.engine.round import GRACE_SECONDS
from apps.game.engine.session import GameSession
from apps.realtime.players import build_public_players
from apps.realtime.signals import emit_action_signal

from ..dispatch import on, trampoline
from ..error_codes import ErrorCode
from ..events.game import (
    ActionSignal,
    CancelGame,
    Detect,
    DetectResult,
    GameCanceled,
    GameEvents,
    GameOver,
    GameReset,
    GameStarted,
    Heal,
    Kill,
    NightAction,
    ResetGame,
    Revenge,
    RoleAssigned,
    Shoot,
    Silence,
    StartGame,
    SubmitVotes,
    SunRise,
    SunSet,
    Vote,
    VoteCast,
    VoteResultStarted,
)
from ..groups import GameSessionGroup, GameSessionRole, RoomActive
from .decorators import game_session, is_alive, is_host, require_phase, require_role

if TYPE_CHECKING:
    from ..consumers import RealtimeConsumer


# =========================================================================
# INBOUND handlers (@on)
# =========================================================================


@on(StartGame)
@is_host
async def handle_start_game(consumer: RealtimeConsumer, event: StartGame) -> None:
    session = consumer.session
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
    players_public = await build_public_players(consumer.session, game_session)
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        GameStarted(
            player_ids=player_ids,
            session_id=game_id,
            host=consumer.user.id,
            alive_ids=alive_ids,
            players=players_public,
        ),
    )


@on(Vote)
@game_session(on_none="error")
@is_alive
@require_phase(Phase.DAY)
async def handle_vote(consumer: RealtimeConsumer, event: Vote, *, game_session: GameSession) -> None:
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.VOTE)
    )
    await consumer.groups.emit(
        GameSessionGroup(room_code=consumer.code, session_id=game_session.id),
        VoteCast(actor_id=consumer.user.id, target_id=event.target_id),
    )
    await emit_action_signal(
        consumer, game_session, ActionType.VOTE, consumer.user.id, event.target_id
    )


async def emit_action_done(
    consumer: RealtimeConsumer,
    game_session: GameSession,
    action_type: ActionType,
) -> None:
    """Tell every player, anonymously, that one phase requirement is done.

    Emitted right after a night/vote-result action is accepted so all
    clients can hide the corresponding phase-requirement icon in real time
    without learning who acted.
    """
    await consumer.groups.emit(
        GameSessionGroup(room_code=consumer.code, session_id=game_session.id),
        NightAction(action_type=action_type.value),
    )


@on(Kill)
@game_session(on_none="error")
@require_phase(Phase.NIGHT)
@is_alive
@require_role(MafiaGodfather, MafiaSilencer, MafiaMember)
async def handle_kill(consumer: RealtimeConsumer, event: Kill, *, game_session: GameSession) -> None:
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.KILL)
    )
    await emit_action_done(consumer, game_session, ActionType.KILL)
    await consumer.groups.emit(
        GameSessionRole(
            room_code=consumer.code,
            session_id=game_session.id,
            role_type=RoleType.MAFIA.value,
        ),
        NightAction(
            actor_id=consumer.user.id,
            target_id=event.target_id,
            action_type=ActionType.KILL.value,
        ),
    )
    await emit_action_signal(
        consumer, game_session, ActionType.KILL, consumer.user.id, event.target_id
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Revenge)
@game_session(on_none="error")
@require_phase(Phase.VOTE_RESULT)
async def handle_revenge(consumer: RealtimeConsumer, event: Revenge, *, game_session: GameSession) -> None:
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.REVENGE)
    )
    await emit_action_done(consumer, game_session, ActionType.REVENGE)
    await emit_action_signal(
        consumer, game_session, ActionType.REVENGE, consumer.user.id, event.target_id
    )
    await _try_auto_transition_vote_result(consumer, game_session)


@on(Heal)
@game_session(on_none="error")
@require_phase(Phase.NIGHT)
@require_role(TownDoctor)
@is_alive
async def handle_heal(consumer: RealtimeConsumer, event: Heal, *, game_session: GameSession) -> None:
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.HEAL)
    )
    await emit_action_done(consumer, game_session, ActionType.HEAL)
    await emit_action_signal(
        consumer, game_session, ActionType.HEAL, consumer.user.id, event.target_id
    )
    await _try_auto_transition_night(consumer, game_session)


@on(Shoot)
@game_session(on_none="error")
@require_phase(Phase.DAY)
@require_role(TownVigilante)
@is_alive
async def handle_shoot(consumer: RealtimeConsumer, event: Shoot, *, game_session: GameSession) -> None:
    round_ = game_session.current_round()
    if round_._shoot_uses(consumer.user.id) >= VIGILANTE_AMMO:
        await consumer.send_error(ErrorCode.INVALID_ACTION, 'No ammo left')
        return
    await round_.add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.SHOOT)
    )
    await emit_action_signal(
        consumer, game_session, ActionType.SHOOT, consumer.user.id, event.target_id
    )


@on(Detect)
@game_session(on_none="error")
@require_phase(Phase.NIGHT)
@require_role(TownCop)
@is_alive
async def handle_detect(consumer: RealtimeConsumer, event: Detect, *, game_session: GameSession) -> None:
    round_ = game_session.current_round()
    if await round_.has_submitted_action(consumer.user.id, ActionType.DETECT):
        await consumer.send_error(
            ErrorCode.INVALID_ACTION,
            'Detective can only investigate once per night',
        )
        return

    await round_.add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.DETECT)
    )
    await emit_action_done(consumer, game_session, ActionType.DETECT)

    target = next((p for p in game_session.players if p.id == event.target_id), None)
    if target is not None and target.role is not None:
        role_type = target.role.role_type.value
        if isinstance(target.role, MafiaGodfather):
            role_type = RoleType.TOWN.value
        await consumer.send_json(
            DetectResult(
                target_id=event.target_id,
                role_type=role_type,
            ).to_json()
        )

    await _try_auto_transition_night(consumer, game_session)


@on(Silence)
@game_session(on_none="error")
@require_phase(Phase.NIGHT)
@require_role(MafiaSilencer)
@is_alive
async def handle_silence(consumer: RealtimeConsumer, event: Silence, *, game_session: GameSession) -> None:
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.SILENCE)
    )
    await emit_action_done(consumer, game_session, ActionType.SILENCE)
    await consumer.groups.emit(
        GameSessionRole(
            room_code=consumer.code,
            session_id=game_session.id,
            role_type=RoleType.MAFIA.value,
        ),
        NightAction(
            actor_id=consumer.user.id,
            target_id=event.target_id,
            action_type=ActionType.SILENCE.value,
        ),
    )
    await emit_action_signal(
        consumer, game_session, ActionType.SILENCE, consumer.user.id, event.target_id
    )
    await _try_auto_transition_night(consumer, game_session)


@on(SubmitVotes)
@game_session(on_none="error")
@is_host
@require_phase(Phase.DAY)
async def handle_submit_votes(consumer: RealtimeConsumer, event: SubmitVotes, *, game_session: GameSession) -> None:
    """Resolve the DAY voting round and transition to the next phase.

    DAY → resolve → if lynch target → VoteResultStarted → new round (vote_result)
                   → if no lynch target → SunSet → new round (night)
    """
    round_ = game_session.current_round()

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
    if round_.lynch_target_id is not None:
        vote_result_round = await game_session.new_round(phase=Phase.VOTE_RESULT, lynch_target_id=round_.lynch_target_id)
        await consumer.groups.emit(
            group,
            VoteResultStarted(lynch_target_id=round_.lynch_target_id, logs=logs),
        )
        # If the lynched player has no required actions (e.g. not Bomb),
        # start the 5 s grace timer immediately.
        if not vote_result_round.obligations:
            await _try_auto_transition_vote_result(consumer, game_session)
        return

    await _transition_after_resolve(game_session, round_, logs, consumer, group)


@on(ResetGame)
@is_host
@game_session(on_none="error")
async def handle_reset_game(consumer: RealtimeConsumer, event: ResetGame, *, game_session: GameSession) -> None:
    player_ids = [p.id for p in game_session.players]
    await _apply_voice_state(
        game_session,
        restore_ids=game_session.silenced_player_ids,
        silence_ids=[],
    )
    await game_session.flush()

    game_id = generate_code(length=16)
    new_session = await GameSession.start_new(
        id=game_id, room_id=consumer.code, player_ids=player_ids,
    )
    await new_session.new_round(phase=Phase.DAY)
    await consumer.session.set_game_session_id(game_id)

    alive_ids = [p.id for p in new_session.players if p.status == PlayerStatus.ALIVE]
    players_public = await build_public_players(consumer.session, new_session)
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        GameReset(
            player_ids=player_ids,
            session_id=game_id,
            host=consumer.user.id,
            alive_ids=alive_ids,
            players=players_public,
        ),
    )


@on(CancelGame)
@is_host
@game_session(on_none="error")
async def handle_cancel_game(consumer: RealtimeConsumer, event: CancelGame, *, game_session: GameSession) -> None:
    await _apply_voice_state(
        game_session,
        restore_ids=game_session.silenced_player_ids,
        silence_ids=[],
    )
    await game_session.flush()
    await consumer.session.clear_game_session_id()
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        GameCanceled(),
    )


# =========================================================================
# OUTBOUND trampolines (@trampoline)
# =========================================================================


@trampoline(GameEvents.GAME_STARTED)
@game_session(on_none="continue")
async def game_started(
    consumer: RealtimeConsumer, event: dict, *, game_session: GameSession | None
) -> None:
    if consumer.user.id in event['player_ids']:
        await consumer.groups.join(
            GameSessionGroup(room_code=consumer.code, session_id=event['session_id'])
        )
    required_actions: list[dict[str, Any]] = []
    round_requirements: list[dict[str, Any]] = []
    if game_session is not None and consumer.user.id in event['player_ids']:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
        round_requirements = await round_.requirement_summary()
    await consumer.send_json(
        GameStarted(
            player_ids=event['player_ids'],
            session_id=event['session_id'],
            host=event['host'],
            alive_ids=event['alive_ids'],
            players=event.get('players', []),
            required_actions=required_actions,
            round_requirements=round_requirements,
        ).to_json()
    )
    # Send each player their assigned role privately, then the initial
    # SunRise so they enter the first day phase (voting).
    if game_session is not None and consumer.user.id in event['player_ids']:
        mafia_players = [
            p for p in game_session.players
            if p.role is not None and p.role.role_type == RoleType.MAFIA
        ]
        mafia_player_ids = [p.id for p in mafia_players]
        mafia_members = [
            {'id': p.id, 'role_code': p.role.code, 'role_name': p.role.name}
            for p in mafia_players if p.role is not None
        ]
        for player in game_session.players:
            if player.id == consumer.user.id and player.role is not None:
                is_mafia = player.role.role_type == RoleType.MAFIA
                await consumer.send_json(
                    RoleAssigned(
                        role_code=player.role.code,
                        role_name=player.role.name,
                        description=player.role.description,
                        role_type=player.role.role_type.value,
                        mafia_ids=mafia_player_ids if is_mafia else None,
                        mafia_members=mafia_members if is_mafia else None,
                    ).to_json()
                )
                if is_mafia:
                    await consumer.groups.join(
                        GameSessionRole(
                            room_code=consumer.code,
                            session_id=game_session.id,
                            role_type=RoleType.MAFIA.value,
                        )
                    )
                break
        await consumer.send_json(
            SunRise(
                player_ids=event['alive_ids'],
                logs=[],
                required_actions=required_actions,
                round_requirements=round_requirements,
            ).to_json()
        )


@trampoline(GameEvents.SUN_SET)
@game_session(on_none="continue")
async def sun_set(consumer: RealtimeConsumer, event: dict, *, game_session: GameSession | None) -> None:
    required_actions: list[dict[str, Any]] = []
    round_requirements: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
        round_requirements = await round_.requirement_summary()
    await consumer.send_json(
        SunSet(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
            round_requirements=round_requirements,
        ).to_json()
    )


@trampoline(GameEvents.SUN_RISE)
@game_session(on_none="continue")
async def sun_rise(consumer: RealtimeConsumer, event: dict, *, game_session: GameSession | None) -> None:
    required_actions: list[dict[str, Any]] = []
    round_requirements: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
        round_requirements = await round_.requirement_summary()
    await consumer.send_json(
        SunRise(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
            round_requirements=round_requirements,
        ).to_json()
    )


@trampoline(GameEvents.ACTION_SIGNAL)
async def action_signal(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(
        ActionSignal(
            action_type=event['action_type'],
            target_id=event['target_id'],
            actor_id=event.get('actor_id'),
        ).to_json()
    )


@trampoline(GameEvents.VOTE_CAST)
async def vote_cast(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(
        VoteCast(actor_id=event['actor_id'], target_id=event['target_id']).to_json()
    )


@trampoline(GameEvents.NIGHT_ACTION)
async def night_action(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(
        NightAction(
            actor_id=event['actor_id'],
            target_id=event.get('target_id'),
            action_type=event['action_type'],
        ).to_json()
    )


@trampoline(GameEvents.VOTE_RESULT_STARTED)
@game_session(on_none="continue")
async def vote_result_started(
    consumer: RealtimeConsumer, event: dict, *, game_session: GameSession | None
) -> None:
    required_actions: list[dict[str, Any]] = []
    round_requirements: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
        round_requirements = await round_.requirement_summary()
    await consumer.send_json(
        VoteResultStarted(
            lynch_target_id=event['lynch_target_id'],
            logs=event.get('logs', []),
            required_actions=required_actions,
            round_requirements=round_requirements,
        ).to_json()
    )


@trampoline(GameEvents.GAME_RESET)
@game_session(on_none="continue")
async def game_reset(
    consumer: RealtimeConsumer, event: dict, *, game_session: GameSession | None
) -> None:
    if consumer.user.id in event['player_ids']:
        await consumer.groups.join(
            GameSessionGroup(room_code=consumer.code, session_id=event['session_id'])
        )
    required_actions: list[dict[str, Any]] = []
    round_requirements: list[dict[str, Any]] = []
    if game_session is not None and consumer.user.id in event['player_ids']:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
        round_requirements = await round_.requirement_summary()
    await consumer.send_json(
        GameReset(
            player_ids=event['player_ids'],
            session_id=event['session_id'],
            host=event['host'],
            alive_ids=event['alive_ids'],
            players=event.get('players', []),
            required_actions=required_actions,
            round_requirements=round_requirements,
        ).to_json()
    )
    if game_session is not None and consumer.user.id in event['player_ids']:
        mafia_players = [
            p for p in game_session.players
            if p.role is not None and p.role.role_type == RoleType.MAFIA
        ]
        mafia_player_ids = [p.id for p in mafia_players]
        mafia_members = [
            {'id': p.id, 'role_code': p.role.code, 'role_name': p.role.name}
            for p in mafia_players if p.role is not None
        ]
        for player in game_session.players:
            if player.id == consumer.user.id and player.role is not None:
                is_mafia = player.role.role_type == RoleType.MAFIA
                await consumer.send_json(
                    RoleAssigned(
                        role_code=player.role.code,
                        role_name=player.role.name,
                        description=player.role.description,
                        role_type=player.role.role_type.value,
                        mafia_ids=mafia_player_ids if is_mafia else None,
                        mafia_members=mafia_members if is_mafia else None,
                    ).to_json()
                )
                if is_mafia:
                    await consumer.groups.join(
                        GameSessionRole(
                            room_code=consumer.code,
                            session_id=game_session.id,
                            role_type=RoleType.MAFIA.value,
                        )
                    )
                break
        await consumer.send_json(
            SunRise(
                player_ids=event['alive_ids'],
                logs=[],
                required_actions=required_actions,
                round_requirements=round_requirements,
            ).to_json()
        )


@trampoline(GameEvents.GAME_CANCELED)
async def game_canceled(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(GameCanceled().to_json())


@trampoline(GameEvents.GAME_OVER)
async def game_over(consumer: RealtimeConsumer, event: dict) -> None:
    await consumer.send_json(
        GameOver(
            winner=event['winner'],
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
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
    asyncio.create_task(_resolve_after_grace(consumer, game_session, Phase.NIGHT))


async def _resolve_after_grace(
    consumer: RealtimeConsumer,
    game_session: GameSession,
    expected_phase: Phase,
) -> None:
    """Sleep GRACE_SECONDS, then re-load and resolve the round."""
    await asyncio.sleep(GRACE_SECONDS)

    # Re-load from Redis to pick up any optional actions submitted during grace.
    fresh = await GameSession.load(room_id=game_session.room_id)
    if fresh is None:
        return
    round_ = fresh.current_round()
    if round_.phase != expected_phase:
        return  # already transitioned

    logs = await round_.resolve()
    group = GameSessionGroup(room_code=consumer.code, session_id=fresh.id)
    await _transition_after_resolve(fresh, round_, logs, consumer, group)


async def _try_auto_transition_vote_result(
    consumer: RealtimeConsumer,
    game_session: GameSession,
) -> None:
    """Check if the VOTE_RESULT round is done. If so, start grace and auto-resolve."""
    round_ = game_session.current_round()
    if round_.phase != Phase.VOTE_RESULT:
        return
    if not await round_.is_round_done():
        return

    round_.start_grace()
    await game_session.save()
    asyncio.create_task(_resolve_after_grace(consumer, game_session, Phase.VOTE_RESULT))


async def _apply_voice_state(
    game_session: GameSession,
    restore_ids: list[int],
    silence_ids: list[int],
) -> None:
    """Server-enforce the silenced set via the LiveKit RoomService API.

    Silenced players have their microphone muted and their publish
    permission restricted to the camera; restored players may unmute
    themselves again.
    """
    meeting_id = livekit_client.create_meeting(game_session.room_id)
    for pid in restore_ids:
        await livekit_client.set_voice_allowed(meeting_id, str(pid), allowed=True)
    for pid in silence_ids:
        await livekit_client.set_voice_allowed(meeting_id, str(pid), allowed=False)


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
    player_ids = [p.id for p in game_session.players]
    winner = game_session.check_winner()
    if winner is not None:
        await consumer.groups.emit(
            RoomActive(room_code=consumer.code),
            GameOver(winner=winner, player_ids=player_ids, logs=logs),
        )
        await _apply_voice_state(
            game_session,
            restore_ids=game_session.silenced_player_ids,
            silence_ids=[],
        )
        await game_session.flush()
        await consumer.session.clear_game_session_id()
        return

    if round_.phase == Phase.NIGHT:
        # The silencer's targets take effect now: muted through the day and
        # vote-result phases, until the next night begins.
        silenced = (
            round_.silenced_target_ids()
            if hasattr(round_, 'silenced_target_ids')
            else []
        )
        game_session.silenced_player_ids = silenced
        await game_session.save()
        await game_session.new_round(phase=Phase.DAY)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunRise(player_ids=alive_ids, logs=logs))
        await _apply_voice_state(game_session, restore_ids=[], silence_ids=silenced)
    else:
        # DAY (no lynch) or EXECUTION → transition to NIGHT. Last round's
        # silences expire when the night begins.
        expired = game_session.silenced_player_ids
        game_session.silenced_player_ids = []
        await game_session.save()
        await game_session.new_round(phase=Phase.NIGHT)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunSet(player_ids=alive_ids, logs=logs))
        await _apply_voice_state(game_session, restore_ids=expired, silence_ids=[])

