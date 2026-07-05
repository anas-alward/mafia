"""GroupMembership: the only place that talks to channel_layer directly.

Wraps group_add / group_discard / group_send so the consumer works in
terms of GroupScope objects, not raw strings, and never has to remember
which groups it's currently in by hand (join/leave is tracked here, so
disconnect cleanup is one call: `await self.groups.leave_all()`).

This does NOT replace EventDispatchMixin/@on (events.py / dispatch.py) --
that's still the typed-payload-per-message-type system for INBOUND
messages and OUTBOUND event shapes. This is the orthogonal concern of
"which groups is this socket a member of right now." A consumer uses
both together: `self.groups.join(scope)` to subscribe, then
`self.groups.emit(scope, SomeOutboundEvent(...))` to broadcast into it.
"""

from __future__ import annotations

from .groups import GroupScope
from .events import OutboundEvent


class GroupMembership:
    """Per-connection tracker of which GroupScopes this socket has joined.

    One instance lives on each consumer (created in `connect`). It holds
    a reference to the consumer's channel_layer and channel_name once,
    so call sites don't repeat them.
    """

    def __init__(self, *, channel_layer, channel_name: str) -> None:
        self._channel_layer = channel_layer
        self._channel_name = channel_name
        self._joined: dict[str, GroupScope] = {}


    def __iter__(self):
        return iter(self._joined.keys())

    async def join(self, scope: GroupScope) -> None:
        """Add this socket to the group named by `scope`. Idempotent-ish:
        joining the same scope twice just re-adds (Channels itself is
        idempotent on group_add), but we only track it once."""
        await self._channel_layer.group_add(scope.name, self._channel_name)
        self._joined[scope.name] = scope

    async def leave(self, scope: GroupScope) -> None:
        await self._channel_layer.group_discard(scope.name, self._channel_name)
        self._joined.pop(scope.name, None)

    async def leave_all(self) -> None:
        """Call from disconnect(). Removes this socket from every scope
        it ever joined, without the caller needing to remember the list."""
        for name in list(self._joined):
            await self._channel_layer.group_discard(name, self._channel_name)
        self._joined.clear()

    def is_in(self, scope: GroupScope) -> bool:
        return scope.name in self._joined

    @property
    def active_scopes(self) -> list[GroupScope]:
        """Useful for debugging / tests: what is this socket subscribed to."""
        return list(self._joined.values())

    async def emit(self, scope: GroupScope, event: OutboundEvent) -> None:
        """Broadcast a typed outbound event into the group named by `scope`.
        Equivalent to the old `self.channel_layer.group_send(group_str, ...)`
        but takes a GroupScope instead of a hand-built string."""
        await self._channel_layer.group_send(scope.name, event.to_event())