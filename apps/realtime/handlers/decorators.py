"""Decorators for inbound/outbound handler guards.

Usage (stack under @on/@trampoline, outermost first):

    @on(Kill)
    @game_session(on_none='error')
    @require_phase(Phase.NIGHT)
    @require_role(MafiaGodfather, MafiaRoleblocker, MafiaMember)
    @is_alive
    async def handle_kill(consumer, event, *, game_session): ...

    @trampoline(GameEvents.SUN_RISE)
    @game_session(on_none='continue')
    async def sun_rise(consumer, event, *, game_session=None): ...

    @on(StartGame)
    @is_host
    async def handle_start_game(consumer, event): ...
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING

from apps.game.engine.constants import Phase, PlayerStatus
from apps.game.engine.roles.type import BaseRole
from apps.game.engine.session import GameSession

from ..error_codes import ErrorCode

if TYPE_CHECKING:
    from ..consumers import RealtimeConsumer


def is_host(fn):
    """Silently return None if the consumer is not the room host."""

    @wraps(fn)
    async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
        if not await consumer.session.is_host(consumer.user):
            return None
        return await fn(consumer, event, *args, **kwargs)

    return wrapper


def game_session(on_none: str = "error"):
    """Load GameSession from Redis and pass it as the ``game_session``
    keyword argument through the decorator chain.

    Stack this right below ``@on`` / ``@trampoline`` so every inner
    decorator and the handler itself receive ``game_session``.

    ``on_none`` controls behaviour when no game session is in progress:

    - ``"error"`` — send :attr:`ErrorCode.GAME_NOT_STARTED` and return ``None``
    - ``"continue"`` — pass ``game_session=None`` to the handler
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
            session = await GameSession.load(room_id=consumer.code)
            if session is None and on_none == "error":
                await consumer.send_error(
                    ErrorCode.GAME_NOT_STARTED, "No game in progress"
                )
                return None
            return await fn(consumer, event, *args, game_session=session, **kwargs)

        return wrapper

    return decorator


def require_phase(phase: Phase):
    """Verify the current round phase matches *phase*.

    Reads ``game_session`` from keyword arguments — requires
    ``@game_session`` to be stacked above it.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
            game_session = kwargs.pop("game_session", None)
            if game_session is None:
                raise RuntimeError(
                    "@require_phase requires @game_session to be stacked above it"
                )
            round_ = game_session.current_round()
            if round_.phase != phase:
                await consumer.send_error(
                    ErrorCode.WRONG_PHASE,
                    f"This action is only allowed during the {phase.value} phase",
                )
                return None
            return await fn(consumer, event, *args, game_session=game_session, **kwargs)

        return wrapper

    return decorator


def require_role(*allowed_roles: type[BaseRole]):
    """Check the consumer's role is among *allowed_roles*.

    Accepts role **classes** (e.g. ``MafiaGodfather``, ``TownDoctor``) and
    checks ``isinstance(player.role, allowed_roles)``.

    Reads ``game_session`` from keyword arguments — requires
    ``@game_session`` to be stacked above it.
    """

    def decorator(fn):
        @wraps(fn)
        async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
            game_session = kwargs.pop("game_session", None)
            if game_session is None:
                raise RuntimeError(
                    "@require_role requires @game_session to be stacked above it"
                )

            player = next(
                (p for p in game_session.players if p.id == consumer.user.id), None
            )
            if player is None or player.role is None:
                await consumer.send_error(
                    ErrorCode.INVALID_ACTION,
                    "You are not a player with a role",
                )
                return None

            if not isinstance(player.role, allowed_roles):
                await consumer.send_error(
                    ErrorCode.INVALID_ACTION,
                    "Your role cannot perform this action",
                )
                return None

            return await fn(consumer, event, *args, game_session=game_session, **kwargs)

        return wrapper

    return decorator


def is_alive(fn):
    """Check the consumer is alive. Dead players cannot act.

    Reads ``game_session`` from keyword arguments — requires
    ``@game_session`` to be stacked above it.
    """

    @wraps(fn)
    async def wrapper(consumer: RealtimeConsumer, event, *args, **kwargs):
        game_session = kwargs.pop("game_session", None)
        if game_session is None:
            raise RuntimeError(
                "@is_alive requires @game_session to be stacked above it"
            )

        player = next(
            (p for p in game_session.players if p.id == consumer.user.id), None
        )
        if player is None:
            await consumer.send_error(
                ErrorCode.INVALID_ACTION,
                "You are not a player in this game",
            )
            return None

        if player.status != PlayerStatus.ALIVE:
            await consumer.send_error(
                ErrorCode.INVALID_ACTION,
                "Dead players cannot perform actions",
            )
            return None

        return await fn(consumer, event, *args, game_session=game_session, **kwargs)

    return wrapper
