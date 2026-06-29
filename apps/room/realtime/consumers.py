"""RoomConsumer: real-time room events via WebSocket.

DISPATCH SUMMARY
-----------------
INBOUND (client -> server):
    receive_json -> dispatch_inbound (dispatch.py) -> looks up
    content['type'] in the registry built from @on-tagged methods below
    -> validates payload into the matching dataclass -> calls the tagged
    method with the typed object.

    To add a new inbound message: add a dataclass + from_payload to
    events.py, then add one @on(YourEvent)-tagged method here, named
    handle_<type> by convention. receive_json itself never changes.

OUTBOUND (server -> client, via channel_layer.group_send):
    Channels itself calls a method on THIS CLASS by exact name match to
    whatever 'type' was passed to group_send -- e.g. group_send(group,
    {'type': 'player_joined', ...}) requires `player_joined` to exist
    here, with that exact name. This is hardcoded inside the channels
    package (`getattr(consumer, message['type'])`); it is NOT part of
    the @on registry and cannot be renamed or routed through it. Each
    one below rebuilds the matching OutboundEvent dataclass from the raw
    dict and sends it -- fill in any extra logic per event.

GROUPS
------
pending_group: every connected socket for this room -- waiting users AND
    accepted members. Lets accepted members see join requests, and lets
    a waiting user hear back about approval/rejection.
active_group: accepted members only. In-room events (chat, host changes,
    player join/leave) broadcast here.
"""

from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .dispatch import EventDispatchMixin, on
from .events import (
    AcceptJoinRequest,
    ChatBroadcast,
    ChatMessage,
    CloseRoom,
    GameStarted,
    HostChanged,
    JoinRequestAccepted,
    JoinRequestCancelled,
    JoinRequestReceived,
    JoinRequestRejected,
    OutboundEvent,
    PlayerJoined,
    PlayerLeft,
    RejectJoinRequest,
    RoomClosed,
    RoomState,
)
from .session import MemberStatus, RoomMember, RoomSession
from .webrtc import realtime


class RoomConsumer(EventDispatchMixin, AsyncJsonWebsocketConsumer):
    # -- lifecycle (Channels hooks, not typed events) ----------------------

    async def connect(self) -> None:
        code = self.scope['url_route']['kwargs']['code']
        self.code: str = code
        self.pending_group: str = f'room_{code}.pending'
        self.active_group: str = f'room_{code}.active'
        self.user: Any = self.scope.get('user')
        self._is_member: bool = False

        session = await RoomSession.from_code(code)

        if not self.user or not session:
            await self.close(code=4001)
            return

        self.session = session

        # Everyone connected sits in the pending group: it's how accepted
        # members hear about join requests, and how a waiting user hears
        # back about approval/rejection.
        await self.channel_layer.group_add(self.pending_group, self.channel_name)

        if session.is_original_host(self.user):
            await self._connect_as_member(regain_host=True)
        elif session.is_member(self.user.id):
            await self._connect_as_member(regain_host=False)
        else:
            await session.request_join(self.user)
            await self.accept()
            await self.emit(
                self.pending_group,
                JoinRequestReceived(user_id=self.user.id, username=self.user.username),
            )

    async def disconnect(self, close_code: int) -> None:
        if not hasattr(self, 'session') or not self.user:
            return

        if not self._is_member:
            await self.session.cancel_join_request(self.user.id)
            await self.emit(
                self.pending_group,
                JoinRequestCancelled(user_id=self.user.id, username=self.user.username),
            )
            return

        was_host = self.session.is_host(self.user)

        # Soft leave: member stays in the room, marked disconnected, so a
        # reconnect resumes the same RoomMember instead of recreating one.
        await self.session.disconnect_member(self.user.id)
        await self.channel_layer.group_discard(self.active_group, self.channel_name)
        await self.channel_layer.group_discard(self.pending_group, self.channel_name)

        if was_host:
            live_members = await self.session.get_live_members()
            candidates = [m for m in live_members if m.user_id != self.user.id]
            if candidates:
                new_host_id = candidates[0].user_id
                await self.session.switch_host(new_host_id)
                await self.emit(
                    self.active_group,
                    HostChanged(
                        previous_host_id=self.user.id,
                        new_host_id=new_host_id,
                        new_host_username='',
                        reason='host_disconnected',
                    ),
                )

        await self.emit(
            self.active_group,
            PlayerLeft(
                user_id=self.user.id,
                username=self.user.username,
                member_count=len(self.session.members),
            ),
        )

    # -- shared connect-as-member path (first accept + every reconnect) ----

    async def _connect_as_member(self, *, regain_host: bool) -> None:
        self._is_member = True

        member = await self.session.get_member(self.user.id)
        if member is None:
            # Defensive fallback: in members set but no member hash (e.g.
            # stale state). Create one rather than failing the connection.
            member = RoomMember(user_id=self.user.id, name=self.user.get_full_name())
            await self.session.add_member(member)
        elif member.status == MemberStatus.DISCONNECTED:
            await self.session.reconnect_member(self.user.id)

        await self.channel_layer.group_add(self.active_group, self.channel_name)

        host_regained = False
        previous_host_id: int | None = None
        if regain_host and self.session.is_original_host(self.user) and self.session.host_is_switched():
            previous_host_id = self.session.host_id
            await self.session.revert_host()
            host_regained = True

        await self.accept()

        credentials = realtime.add_participant(
            meeting_id=self.session.meeting_id,
            participant_id=str(self.user.id),
            name=self.user.username,
        )
        await self.send_event(
            RoomState(
                credentials=credentials,
                room_id=self.session.id,
                room_name=self.session.name,
                host_id=self.session.host_id,
                members=list(self.session.members),
            )
        )

        if host_regained:
            await self.emit(
                self.active_group,
                HostChanged(
                    previous_host_id=previous_host_id,
                    new_host_id=self.user.id,
                    new_host_username=self.user.username,
                    reason='host_reconnected',
                ),
            )
        else:
            await self.emit(
                self.active_group,
                PlayerJoined(
                    user_id=self.user.id,
                    username=self.user.username,
                    member_count=len(self.session.members),
                ),
            )

    # -- inbound entry point (fixed; never changes when adding events) ----

    async def receive_json(self, content: dict[str, Any]) -> None:
        await self.dispatch_inbound(content)

    # -- inbound handlers (tagged with @on, named handle_<type>) ----------

    @on(AcceptJoinRequest)
    async def handle_accept_join_request(self, event: AcceptJoinRequest) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        user_id = event.user_id
        if self.session.is_host(self.user):
            await self.session.approve_join(user_id)


    @on(RejectJoinRequest)
    async def handle_reject_join_request(self, event: RejectJoinRequest) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        pass

    @on(CloseRoom)
    async def handle_close_room(self, event: CloseRoom) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        pass

    @on(ChatMessage)
    async def handle_chat_message(self, event: ChatMessage) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        pass

    # -- outbound trampolines (forced exact names by Channels) ------------
    # Each one's body always follows the same shape: rebuild the matching
    # OutboundEvent dataclass from the raw dict, then send/act on it.

    async def player_joined(self, event: dict[str, Any]) -> None:
        await self.send_json(PlayerJoined(
            user_id=event['user_id'],
            username=event['username'],
            member_count=event['member_count'],
        ).to_json())

    async def player_left(self, event: dict[str, Any]) -> None:
        await self.send_json(PlayerLeft(
            user_id=event['user_id'],
            username=event['username'],
            member_count=event['member_count'],
        ).to_json())

    async def host_changed(self, event: dict[str, Any]) -> None:
        await self.send_json(HostChanged(
            previous_host_id=event['previous_host_id'],
            new_host_id=event['new_host_id'],
            new_host_username=event['new_host_username'],
            reason=event['reason'],
        ).to_json())

    async def game_started(self, event: dict[str, Any]) -> None:
        await self.send_json(GameStarted(
            session_id=event['session_id'],
            host=event['host'],
        ).to_json())

    async def room_closed(self, event: dict[str, Any]) -> None:
        await self.send_json(RoomClosed(
            room_code=event['room_code'],
        ).to_json())

    async def chat_message(self, event: dict[str, Any]) -> None:
        await self.send_json(ChatBroadcast(
            user_id=event['user_id'],
            username=event['username'],
            message=event['message'],
        ).to_json())

    async def join_request_received(self, event: dict[str, Any]) -> None:
        await self.send_json(JoinRequestReceived(
            user_id=event['user_id'],
            username=event['username'],
        ).to_json())

    async def join_request_cancelled(self, event: dict[str, Any]) -> None:
        await self.send_json(JoinRequestCancelled(
            user_id=event['user_id'],
            username=event['username'],
        ).to_json())

    async def join_request_accepted(self, event: dict[str, Any]) -> None:
        """Broadcast on pending_group. Only the targeted socket promotes
        itself into the active group; everyone else (other waiters,
        existing members) just gets an informational ping.
        DUMP IMPLEMENTATION for the "everyone else" branch -- fill in if
        you want waiters/members to react to this too."""
        if event['user_id'] != self.user.id:
            return
        await self._connect_as_member(regain_host=False)

    async def join_request_rejected(self, event: dict[str, Any]) -> None:
        """DUMP IMPLEMENTATION. Fill in real logic."""
        pass

    async def room_state(self, event: dict[str, Any]) -> None:
        await self.send_json(RoomState(
            credentials=event['credentials'],
            room_id=event['room_id'],
            room_name=event['room_name'],
            host_id=event['host_id'],
            members=event['members'],
        ).to_json())

    # -- shared send helpers (plumbing for your handler bodies to use) -----

    async def emit(self, group: str, event: OutboundEvent) -> None:
        """Broadcast a typed outbound event to a channel group."""
        await self.channel_layer.group_send(group, event.to_event())

    async def send_event(self, event: OutboundEvent) -> None:
        """Send a typed outbound event directly to this socket."""
        await self.send_json(event.to_json())