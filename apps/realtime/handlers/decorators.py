"""Decorators for inbound handler guards.

Usage (stack under @on/@trampoline, outermost first):

    @on(Kill)
    @require_phase(Phase.NIGHT)
    @require_role(MafiaGodfather, MafiaRoleblocker, MafiaMember)
    async def handle_kill(consumer, event, game_session): ...

    @on(StartGame)
    @is_host
    async def handle_start_game(consumer, event): ...
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any

from apps.game.engine.constants import Phase, PlayerStatus
from apps.game.engine.roles.type import BaseRole
from apps.game.engine.session import GameSession

from ..error_codes import ErrorCode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..consumers import RealtimeConsumer


def is_host(fn):
    """Silently return None if the consumer is not the room host."""

    @wraps(fn)
    async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
        if not await consumer.session.is_host(consumer.user):
            return None
        return await fn(consumer, event, *args, **kwargs)

    return wrapper


def _extract_game_session(*args) -> GameSession | None:
    """Return a GameSession from positional args if one was injected by an
    outer decorator (e.g. ``@require_phase``), otherwise None."""
    for a in args:
        if isinstance(a, GameSession):
            return a
    return None


async def _get_game_session(consumer: RealtimeConsumer, *args: Any) -> GameSession | None:
    """Return an already-injected GameSession from *args*, or load from Redis."""
    existing = _extract_game_session(*args)
    if existing is not None:
        return existing
    return await GameSession.load(room_id=consumer.code)


def require_phase(phase: Phase):
    """Load the game session, verify the current round phase matches *phase*,
    and pass ``game_session`` as the third positional argument.

    Sends an error and returns None if no game is in progress or the phase
    doesn't match.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
            game_session = await _get_game_session(consumer, *args)
            if game_session is None:
                await consumer.send_error(
                    ErrorCode.GAME_NOT_STARTED, 'No game in progress'
                )
                return None
            round_ = game_session.current_round()
            if round_.phase != phase:
                await consumer.send_error(
                    ErrorCode.WRONG_PHASE,
                    f'This action is only allowed during the {phase.value} phase',
                )
                return None
            return await fn(consumer, event, game_session, *args, **kwargs)

        return wrapper

    return decorator


def require_role(*allowed_roles: type[BaseRole]):
    """Check the consumer's role is among *allowed_roles*.

    Accepts role **classes** (e.g. ``MafiaGodfather``, ``TownDoctor``) and
    checks ``isinstance(player.role, allowed_roles)``.

    Reuses the game session injected by ``@require_phase`` if present;
    otherwise loads it from Redis.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
            game_session = await _get_game_session(consumer, *args)
            if game_session is None:
                await consumer.send_error(
                    ErrorCode.GAME_NOT_STARTED, 'No game in progress'
                )
                return None

            player = next(
                (p for p in game_session.players if p.id == consumer.user.id), None
            )
            if player is None or player.role is None:
                await consumer.send_error(
                    ErrorCode.INVALID_ACTION,
                    'You are not a player with a role',
                )
                return None

            if not isinstance(player.role, allowed_roles):
                await consumer.send_error(
                    ErrorCode.INVALID_ACTION,
                    'Your role cannot perform this action',
                )
                return None

            return await fn(consumer, event, *args, **kwargs)

        return wrapper

    return decorator


def is_alive(fn):
    """Check the consumer is alive. Dead players cannot act.

    Reuses the game session injected by ``@require_phase`` if present;
    otherwise loads it from Redis.
    """

    @wraps(fn)
    async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
        game_session = await _get_game_session(consumer, *args)
        if game_session is None:
            await consumer.send_error(
                ErrorCode.GAME_NOT_STARTED, 'No game in progress'
            )
            return None

        player = next(
            (p for p in game_session.players if p.id == consumer.user.id), None
        )
        if player is None:
            await consumer.send_error(
                ErrorCode.INVALID_ACTION,
                'You are not a player in this game',
            )
            return None

        if player.status != PlayerStatus.ALIVE:
            await consumer.send_error(
                ErrorCode.INVALID_ACTION,
                'Dead players cannot perform actions',
            )
            return None

        return await fn(consumer, event, *args, **kwargs)

    return wrapper
