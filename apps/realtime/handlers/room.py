"""Room domain handlers.

All events that belong to the room lifecycle: join requests, host
changes, player presence, room close. ~20 events expected here.

Each inbound handler: @on(EventClass), signature (consumer, event).
Each outbound trampoline: @trampoline('type_string'), signature (consumer, event_dict).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.webrtc import webrtc_client
from apps.room.session import RoomMember

from .decorators import is_host
from ..dispatch import on, trampoline
from ..error_codes import ErrorCode
from ..events import (
    AcceptJoinRequest,
    ChatBroadcast,
    ChatMessage,
    CloseRoom,
    HostChanged,
    JoinRequestAccepted,
    JoinRequestRejected,
    JoinRequestReceived,
    PlayerJoined,
    PlayerLeft,
    RejectJoinRequest,
    RoomClosed,
    RoomState,
)
from ..events.room import RoomEvents
from ..groups import RoomActive, RoomPending

if TYPE_CHECKING:
    from ..consumers import RealtimeConsumer


# =========================================================================
# INBOUND handlers (@on)
# =========================================================================


@on(AcceptJoinRequest)
@is_host
async def handle_accept_join_request(consumer, event: AcceptJoinRequest) -> None:
    user_id = event.user_id
    await consumer.session.approve_join(user_id)
    await consumer.groups.emit(
        RoomPending(room_code=consumer.code),
        JoinRequestAccepted(user_id=user_id),
    )


@on(RejectJoinRequest)
async def handle_reject_join_request(consumer: RealtimeConsumer, event: RejectJoinRequest) -> None:
    session = consumer.session
    if not await session.is_host(consumer.user):
        await consumer.send_error(code=ErrorCode.NOT_HOST, message='Only host can perform this')

    if await session.is_waiting(event.user_id):
        await session.reject_join(user_id=event.user_id)
        return consumer.groups.emit(
            RoomPending(room_code=consumer.code), JoinRequestRejected(user_id=event.user_id)
        )

    else:
        await consumer.send_error(code=ErrorCode.NOT_PENDING, message=f'There is no pending user with this id {event.user_id}')


@on(CloseRoom)
@is_host
async def handle_close_room(consumer, event: CloseRoom) -> None:
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        RoomClosed(room_code=consumer.code),
    )
    await consumer.session.invalidate()


@on(ChatMessage)
async def handle_chat_message(consumer, event: ChatMessage) -> None:
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        ChatBroadcast(
            user_id=consumer.user.id,
            username=consumer.user.username,
            message=event.message,
        ),
    )


# =========================================================================
# OUTBOUND trampolines (@trampoline)
# Channels calls consumer.<type>(event_dict) -- resolved via __getattr__.
# =========================================================================


@trampoline(RoomEvents.PLAYER_JOINED)
async def player_joined(consumer, event: dict) -> None:
    await consumer.send_json(
        PlayerJoined(
            user_id=event['user_id'],
            username=event['username'],
            member_count=event['member_count'],
        ).to_json()
    )


@trampoline(RoomEvents.PLAYER_LEFT)
async def player_left(consumer, event: dict) -> None:
    await consumer.send_json(
        PlayerLeft(
            user_id=event['user_id'],
            username=event['username'],
            member_count=event['member_count'],
        ).to_json()
    )


@trampoline(RoomEvents.HOST_CHANGED)
async def host_changed(consumer, event: dict) -> None:
    await consumer.send_json(
        HostChanged(
            new_host_id=event['new_host_id'],
            new_host_username=event['new_host_username'],
            reason=event['reason'],
        ).to_json()
    )


@trampoline(RoomEvents.ROOM_CLOSED)
async def room_closed(consumer, event: dict) -> None:
    await consumer.send_json(
        RoomClosed(
            room_code=event['room_code'],
        ).to_json()
    )


@trampoline(RoomEvents.CHAT_MESSAGE)
async def chat_message(consumer, event: dict) -> None:
    await consumer.send_json(
        ChatBroadcast(
            user_id=event['user_id'],
            username=event['username'],
            message=event['message'],
        ).to_json()
    )


@trampoline(RoomEvents.JOIN_REQUEST_RECEIVED)
async def join_request_received(consumer, event: dict) -> None:
    await consumer.send_json(
        JoinRequestReceived(
            user_id=event['user_id'],
            username=event['username'],
        ).to_json()
    )


@trampoline(RoomEvents.JOIN_REQUEST_REJECTED)
async def join_request_rejected(consumer, event: dict) -> None:
    if consumer.user.id == event['user_id']:
        await consumer.send_event(
            JoinRequestRejected(
                user_id=event['user_id'],
            )
        )


@trampoline(RoomEvents.JOIN_REQUEST_ACCEPTED)
async def join_request_accepted(consumer: RealtimeConsumer, event: dict) -> None:
    if event['user_id'] != consumer.user.id:
        return

    consumer._is_member = True

    member = RoomMember(user_id=consumer.user.id, name=consumer.user.get_full_name())
    await consumer.session.add_member(member)

    await consumer.groups.join(RoomActive(room_code=consumer.code))

    credentials = webrtc_client.add_participant(
        meeting_id=consumer.session.meeting_id,
        participant_id=str(consumer.user.id),
        name=consumer.user.username,
    )
    member_ids = await consumer.session.get_member_ids()

    await consumer.send_event(
        JoinRequestAccepted(user_id=consumer.user.id),
    )
    await consumer.send_event(
        RoomState(
            credentials=credentials,
            room_id=consumer.session.id,
            room_name=consumer.session.name,
            host_id=consumer.session.host_id,
            members=list(member_ids),
        )
    )


@trampoline(RoomEvents.ROOM_STATE)
async def room_state(consumer, event: dict) -> None:
    await consumer.send_json(
        RoomState(
            credentials=event['credentials'],
            room_id=event['room_id'],
            room_name=event['room_name'],
            host_id=event['host_id'],
            members=event['members'],
        ).to_json()
    )
