"""Type-safe inbound message dispatch for RoomConsumer.

Mechanism:
  1. @on(SomeInboundEvent) tags a consumer method with the dataclass it
     expects. Tagging happens at class-body-execution time -- it just
     stamps a hidden attribute on the function object; nothing is
     "registered" yet.
  2. EventDispatchMixin.__init_subclass__ runs ONCE, automatically, right
     after the consumer class finishes being defined (a normal Python
     hook, not Channels-specific). It walks every attribute on the class,
     finds the tagged methods, and builds a real lookup dict:
         {"accept_join_request": (AcceptJoinRequest, "handle_accept_join_request"), ...}
  3. At actual request time, dispatch_inbound(content) reads content["type"],
     looks it up in that dict, validates the raw payload into the right
     dataclass via from_payload, and calls the tagged method with the
     typed object -- never a raw dict.

This module has NO equivalent for outbound events. Channels dispatches
those itself by doing `getattr(consumer, message["type"])` internally --
a hardcoded mechanism inside the channels package, not something this
mixin participates in. Each outbound landing-spot method must exist on
the consumer with an exact matching name; see consumer.py.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar, TypeVar

from .events import InboundEvent, MessageValidationError

_HandlerT = TypeVar("_HandlerT", bound=Callable[..., Any])

_HANDLES_EVENT_CLS_ATTR = "_handles_event_cls"


def on(event_cls: type[InboundEvent]) -> Callable[[_HandlerT], _HandlerT]:
    """Decorator: tags a consumer method as the handler for `event_cls`.
    Must be used on a method inside an EventDispatchMixin subclass.
    By convention, name the tagged method `handle_<event_cls.type>`."""

    def decorator(func: _HandlerT) -> _HandlerT:
        setattr(func, _HANDLES_EVENT_CLS_ATTR, event_cls)
        return func

    return decorator


class EventDispatchMixin:
    """Mix into a Channels consumer to get type-safe inbound dispatch via
    dispatch_inbound(content)."""

    _inbound_handlers: ClassVar[dict[str, tuple[type[InboundEvent], str]]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        handlers: dict[str, tuple[type[InboundEvent], str]] = {}
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name, None)
            event_cls = getattr(attr, _HANDLES_EVENT_CLS_ATTR, None)
            if event_cls is not None:
                handlers[event_cls.type] = (event_cls, attr_name)
        cls._inbound_handlers = handlers

    async def dispatch_inbound(self, content: dict[str, Any]) -> None:
        """Look up, validate, and call the handler for content['type'].
        Unknown types and validation failures are reported via the
        on_unknown_event_type / on_invalid_event_payload hooks below,
        which you should override with real behavior."""
        raw_type = content.get("type")
        if not isinstance(raw_type, str):
            await self.on_invalid_event_payload(
                MessageValidationError("<missing>", "message has no string 'type' field")
            )
            return

        entry = self._inbound_handlers.get(raw_type)
        if entry is None:
            await self.on_unknown_event_type(raw_type)
            return

        event_cls, method_name = entry
        try:
            typed_event = event_cls.from_payload(content)
        except MessageValidationError as exc:
            await self.on_invalid_event_payload(exc)
            return

        handler = getattr(self, method_name)
        await handler(typed_event)

    # -- overridable error hooks -------------------------------------------

    async def on_unknown_event_type(self, raw_type: str) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic (e.g. send an error
        frame back to the client, log it, etc.)."""
        pass

    async def on_invalid_event_payload(self, exc: MessageValidationError) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        pass