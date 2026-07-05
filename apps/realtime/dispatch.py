"""Event dispatch: inbound @on registry + outbound @trampoline registry.

TWO REGISTRIES
--------------
1. INBOUND  (@on): maps an event dataclass -> async handler function.
   Called by `dispatch_inbound` when a message arrives from the client.
   Handler signature: async def handle_something(consumer, event: SomeEvent)

2. OUTBOUND (@trampoline): maps a Channels message-type string -> async
   handler function. Called by `dispatch_outbound` which the consumer
   exposes as __getattr__ so Channels can resolve any type name without
   the consumer declaring each method explicitly.
   Handler signature: async def some_event_type(consumer, event: dict)

Both registries are module-level dicts populated at import time when
handler modules are imported (see handlers/__init__.py). The consumer
itself never lists which domains exist.

ADDING A NEW DOMAIN
-------------------
1. Create handlers/your_domain.py.
2. Use @on(YourEvent) for inbound handlers.
3. Use @trampoline('your_event_type') for outbound trampolines.
4. Add one import line in handlers/__init__.py.
Done. consumer.py never changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from .error_codes import ErrorCode

logger = logging.getLogger('realtime')


# ---- inbound registry ---------------------------------------------------

# Maps event class -> handler function
_INBOUND: dict[type, Callable] = {}


def on(event_cls: type) -> Callable:
    """Decorator: register a function as the inbound handler for event_cls.

    Usage (in any handler module):
        @on(ChatMessage)
        async def handle_chat_message(consumer, event: ChatMessage): ...
    """
    def decorator(fn: Callable) -> Callable:
        _INBOUND[event_cls] = fn
        return fn
    return decorator


# ---- outbound (trampoline) registry -------------------------------------

# Maps Channels message-type string -> handler function
_OUTBOUND: dict[str, Callable] = {}


def trampoline(event_type: str) -> Callable:
    """Decorator: register a function as the outbound handler for a
    Channels message type. Channels calls consumer.<event_type>(msg) --
    EventDispatchMixin.__getattr__ resolves that lookup here, so the
    consumer never needs to declare these methods itself.

    Usage (in any handler module):
        @trampoline('chat_message')
        async def chat_message(consumer, event: dict): ...
    """
    def decorator(fn: Callable) -> Callable:
        _OUTBOUND[event_type] = fn
        return fn
    return decorator


# ---- mixin --------------------------------------------------------------

class EventDispatchMixin:
    """Mix into the consumer to activate both registries.

    dispatch_inbound: called from receive_json. Looks up the event type
    in _INBOUND, validates the payload via Pydantic, calls the handler.

    __getattr__: intercepts Channels' getattr(consumer, message['type'])
    lookup for outbound messages and resolves it against _OUTBOUND,
    returning a bound coroutine so Channels can await it normally.
    """

    async def dispatch_inbound(self, content: dict[str, Any]) -> None:
        event_type_str = content.get('type')
        handler = None
        event_obj = None

        for event_cls, fn in _INBOUND.items():
            if getattr(event_cls, 'type', None) == event_type_str:
                try:
                    event_obj = event_cls.from_payload(content)
                except ValidationError as e:
                    await self.send_error(ErrorCode.INVALID_PAYLOAD, e.errors())
                    return
                handler = fn
                break

        if handler is None:
            await self.send_error(
                ErrorCode.UNKNOWN_EVENT_TYPE, f'no handler for "{event_type_str}"'
            )
            return

        try:
            await handler(self, event_obj)
        except Exception:
            logger.exception('handler failed for %s', event_type_str)
            await self.send_error(
                ErrorCode.INTERNAL_ERROR, 'something went wrong processing your request'
            )

    def __getattr__(self, name: str) -> Any:
        # Only intercept names that are registered outbound handlers.
        # Everything else raises AttributeError as normal so we don't
        # swallow real missing-attribute bugs.
        if name in _OUTBOUND:
            fn = _OUTBOUND[name]
            async def bound(event: dict) -> None:
                await fn(self, event)
            return bound
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")