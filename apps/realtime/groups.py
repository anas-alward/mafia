"""Typed channel-group scopes.

PROBLEM THIS REPLACES
----------------------
Before: group names were inline f-strings built ad hoc per consumer
(`f'room_{code}.pending'`, `f'room_{code}.active'`), with group_add /
group_discard calls hand-paired wherever a method happened to need them.
Adding a new group type meant inventing a new string convention and
remembering every place to wire it in. Nothing stopped you from typo-ing
'room_{code}.active' in one place and 'room_{code}.actve' in another.

NOW
---
A GroupScope is a typed, nestable identifier. It knows its own name AND
its parent's name, so a hierarchy (room -> session -> table, or
room -> spectators) is structural, not convention. GroupMembership
(in membership.py) wraps the raw channel_layer calls so the consumer
never builds a string by hand again.

ADDING A NEW GROUP TYPE
------------------------
1. Subclass GroupScope (or use a plain dataclass like the ones below).
2. Implement `name` -- that's the only required piece.
3. Done. No other file needs to change. The consumer calls
   `self.groups.join(YourNewScope(...))` and `self.groups.emit(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass


class GroupScope:
    """Base class for a channel-group identifier.

    Subclasses only need to provide `name`. Keeping this as a real class
    (not a bare string) means:
      - you get autocomplete / type-checking on what scopes exist
      - you can attach extra data to a scope without re-deriving it from
        a parsed string later
      - renaming the underlying string convention is a one-line change
        in one place, not a grep-and-replace
    """

    @property
    def name(self) -> str:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class RoomPending(GroupScope):
    """Everyone connected to a room: waiting users + accepted members."""

    room_code: str

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.pending'


@dataclass(frozen=True, slots=True)
class RoomActive(GroupScope):
    """Accepted members only. Room-wide events: chat, host changes, etc."""

    room_code: str

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.active'


@dataclass(frozen=True, slots=True)
class RoomSpectators(GroupScope):
    """Users watching a room without being seated members.

    Example of adding a new top-level group type: same shape as
    RoomActive, just a different name. No other code needs to know
    this exists until a consumer method actually joins/emits to it.
    """

    room_code: str

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.spectators'


@dataclass(frozen=True, slots=True)
class GameSessionGroup(GroupScope):
    """All participants of one specific game session within a room.

    A room can have many game sessions over its lifetime (or, if you
    later allow concurrent sessions/tables, many at once). This scope
    is keyed by session_id, not room_code, so it's independent of
    whichever room-level groups exist. The room_code is kept only for
    debuggability in the name -- the actual partitioning key is
    session_id.
    """

    room_code: str
    session_id: str

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.session.{self.session_id}'


@dataclass(frozen=True, slots=True)
class GameSessionTable(GroupScope):
    """Example of a THIRD level of nesting: a sub-table within a session.

    This is the pattern to copy for 'per-team', 'per-table', or any other
    dynamic subdivision you haven't named yet: take the parent scope's
    identifying fields, add your own key, build a name that nests under
    the parent's name. You don't need permission from any other file to
    add this -- it's just another dataclass.
    """

    room_code: str
    session_id: str
    table_id: str

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.session.{self.session_id}.table.{self.table_id}'