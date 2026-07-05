from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import Field

from .base import InboundEvent, OutboundEvent


class RoomEvents(StrEnum):
    ACCEPT_JOIN_REQUEST = 'accept_join_request'
    REJECT_JOIN_REQUEST = 'reject_join_request'
    CLOSE_ROOM = 'close_room'
    CHAT = 'chat'
    PLAYER_JOINED = 'player_joined'
    PLAYER_LEFT = 'player_left'
    HOST_CHANGED = 'host_changed'
    ROOM_CLOSED = 'room_closed'
    CHAT_MESSAGE = 'chat_message'
    JOIN_REQUEST_RECEIVED = 'join_request_received'
    JOIN_REQUEST_ACCEPTED = 'join_request_accepted'
    JOIN_REQUEST_REJECTED = 'join_request_rejected'
    ROOM_STATE = 'room_state'


class AcceptJoinRequest(InboundEvent):
    type: ClassVar[str] = RoomEvents.ACCEPT_JOIN_REQUEST
    user_id: int


class RejectJoinRequest(InboundEvent):
    type: ClassVar[str] = RoomEvents.REJECT_JOIN_REQUEST
    user_id: int


class CloseRoom(InboundEvent):
    """Host-only: explicitly ends the room for everyone."""
    type: ClassVar[str] = RoomEvents.CLOSE_ROOM


class ChatMessage(InboundEvent):
    type: ClassVar[str] = RoomEvents.CHAT
    message: str = Field(min_length=1, strip_whitespace=True)


# ---------------------------------------------------------------------------
# Outbound (server -> client)
# ---------------------------------------------------------------------------


class PlayerJoined(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.PLAYER_JOINED
    user_id: int
    username: str
    member_count: int


class PlayerLeft(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.PLAYER_LEFT
    user_id: int
    username: str
    member_count: int


class HostChanged(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.HOST_CHANGED
    new_host_id: int
    new_host_username: str
    reason: str


class RoomClosed(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.ROOM_CLOSED
    room_code: str


class ChatBroadcast(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.CHAT_MESSAGE
    user_id: int
    username: str
    message: str


class JoinRequestReceived(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.JOIN_REQUEST_RECEIVED
    user_id: int
    username: str


class JoinRequestAccepted(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.JOIN_REQUEST_ACCEPTED
    user_id: int


class JoinRequestRejected(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.JOIN_REQUEST_REJECTED
    user_id: int


class RoomState(OutboundEvent):
    channel_type: ClassVar[str] = RoomEvents.ROOM_STATE
    credentials: dict[str, Any]
    room_id: int | None
    room_name: str | None
    host_id: int | None
    members: list[int]