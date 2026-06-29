"""Typed inbound/outbound WebSocket event payloads for RoomConsumer.

This file holds DATA SHAPES ONLY -- no behavior, no side effects.

Inbound events (client -> server) are validated via `from_payload`,
which raises MessageValidationError on bad input instead of letting a
raw KeyError/TypeError escape into a handler.

Outbound events (server -> client) are built from these dataclasses and
converted with `to_event()` (for group_send) / `to_json()` (for
send_json) so call sites never hand-construct dicts.

Real logic for every event lives in consumer.py, in a method named
handle_<event_type> for inbound, or in the Channels-required trampoline
method (named exactly the channel_type) for outbound. See consumer.py's
module docstring for the full wiring.

HOW TO ADD A NEW EVENT:
  Inbound:  1) subclass InboundEvent, set `type`, implement from_payload
            2) in consumer.py: add a method tagged @on(YourEvent),
               named handle_<type> by convention
  Outbound: 1) subclass OutboundEvent, set `channel_type`, add fields
            2) in consumer.py: add a trampoline method named exactly
               `channel_type` (Channels requires this exact name)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Self


class MessageValidationError(Exception):
    """Raised when an inbound client message doesn't match its expected shape."""

    def __init__(self, event_type: str, detail: str) -> None:
        self.event_type = event_type
        self.detail = detail
        super().__init__(f"{event_type}: {detail}")


def _require(payload: dict[str, Any], key: str, expected_type: type, event_type: str) -> Any:
    if key not in payload:
        raise MessageValidationError(event_type, f"missing required field '{key}'")
    value = payload[key]
    if not isinstance(value, expected_type):
        raise MessageValidationError(
            event_type,
            f"field '{key}' expected {expected_type.__name__}, got {type(value).__name__}",
        )
    return value


# ---------------------------------------------------------------------------
# Inbound (client -> server)
# ---------------------------------------------------------------------------

class InboundEvent:
    """Base for client->server messages. Subclasses set `type` and
    implement `from_payload`. No `handle` here -- logic lives in
    consumer.py, on the method tagged @on(ThisClass)."""

    type: ClassVar[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        raise NotImplementedError


@dataclass(slots=True, frozen=True)
class AcceptJoinRequest(InboundEvent):
    type: ClassVar[str] = "accept_join_request"
    user_id: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        return cls(user_id=_require(payload, "user_id", int, cls.type))


@dataclass(slots=True, frozen=True)
class RejectJoinRequest(InboundEvent):
    type: ClassVar[str] = "reject_join_request"
    user_id: int

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        return cls(user_id=_require(payload, "user_id", int, cls.type))


@dataclass(slots=True, frozen=True)
class CloseRoom(InboundEvent):
    """Host-only: explicitly ends the room for everyone."""
    type: ClassVar[str] = "close_room"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        return cls()


@dataclass(slots=True, frozen=True)
class ChatMessage(InboundEvent):
    type: ClassVar[str] = "chat"
    message: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        message = _require(payload, "message", str, cls.type)
        if not message.strip():
            raise MessageValidationError(cls.type, "message must not be empty")
        return cls(message=message)


# ---------------------------------------------------------------------------
# Outbound (server -> client)
# ---------------------------------------------------------------------------

class OutboundEvent:
    """Base for server->client messages, sent via group_send (channel layer)
    or directly via send_json. `channel_type` is the Channels dispatch
    method name -- Channels itself calls `consumer.<channel_type>` by name
    when a group_send uses this type; that method must exist on the
    consumer with this exact name (a hard Channels constraint, not
    something this file or the @on registry controls)."""

    channel_type: ClassVar[str]

    def to_event(self) -> dict[str, Any]:
        """Shape handed to channel_layer.group_send."""
        return {"type": self.channel_type, **asdict(self)}

    def to_json(self) -> dict[str, Any]:
        """Shape sent to the actual client over send_json."""
        return {"type": self.channel_type, **asdict(self)}


@dataclass(slots=True, frozen=True)
class PlayerJoined(OutboundEvent):
    channel_type: ClassVar[str] = "player_joined"
    user_id: int
    username: str
    member_count: int


@dataclass(slots=True, frozen=True)
class PlayerLeft(OutboundEvent):
    channel_type: ClassVar[str] = "player_left"
    user_id: int
    username: str
    member_count: int


@dataclass(slots=True, frozen=True)
class HostChanged(OutboundEvent):
    channel_type: ClassVar[str] = "host_changed"
    previous_host_id: int
    new_host_id: int
    new_host_username: str
    reason: str


@dataclass(slots=True, frozen=True)
class GameStarted(OutboundEvent):
    channel_type: ClassVar[str] = "game_started"
    session_id: str
    host: int


@dataclass(slots=True, frozen=True)
class RoomClosed(OutboundEvent):
    channel_type: ClassVar[str] = "room_closed"
    room_code: str


@dataclass(slots=True, frozen=True)
class ChatBroadcast(OutboundEvent):
    channel_type: ClassVar[str] = "chat_message"
    user_id: int
    username: str
    message: str


@dataclass(slots=True, frozen=True)
class JoinRequestReceived(OutboundEvent):
    channel_type: ClassVar[str] = "join_request_received"
    user_id: int
    username: str


@dataclass(slots=True, frozen=True)
class JoinRequestCancelled(OutboundEvent):
    channel_type: ClassVar[str] = "join_request_cancelled"
    user_id: int
    username: str


@dataclass(slots=True, frozen=True)
class JoinRequestAccepted(OutboundEvent):
    channel_type: ClassVar[str] = "join_request_accepted"
    user_id: int


@dataclass(slots=True, frozen=True)
class JoinRequestRejected(OutboundEvent):
    channel_type: ClassVar[str] = "join_request_rejected"
    user_id: int


@dataclass(slots=True, frozen=True)
class RoomState(OutboundEvent):
    """Sent directly via send_event, never through group_send (per-
    connection state for the socket that just joined/reconnected)."""
    channel_type: ClassVar[str] = "room_state"
    credentials: dict[str, Any]
    room_id: int | None
    room_name: str | None
    host_id: int | None
    members: list[int]