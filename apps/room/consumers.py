"""RoomConsumer: real-time room events via WebSocket."""

from __future__ import annotations

from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .realtime import realtime
from .session import MemberStatus, RoomMember, RoomSession


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        code = self.scope['url_route']['kwargs']['code']
        self.code: str = code
        self.pending_group: str = f'room_{code}:pending'
        self.active_group: str = f'room_{code}:active'
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

        if session.is_member(self.user.id):
            await self._connect_as_member(regain_host=True)
        else:
            await session.request_join(self.user)
            await self.accept()
            await self.channel_layer.group_send(
                self.pending_group,
                {
                    'type': 'join_request_received',
                    'user_id': self.user.id,
                    'username': self.user.username,
                },
            )

    async def _connect_as_member(self, *, regain_host: bool) -> None:
        """Add an already-approved user to the active group. Used on first
        accept and on every reconnect of an existing member."""
        self._is_member = True

        member = await self.session.get_member(self.user.id)
        if member is None:
            # Defensive fallback: in members set but no member hash (e.g.
            # stale state). Create one rather than failing the connection.
            member = RoomMember(user_id=self.user.id, name=self.user.get_full_name())
            await self.session.add_member(member)
        elif member.is_disconnected:
            await self.session.reconnect_member(self.user.id)

        await self.channel_layer.group_add(self.active_group, self.channel_name)

        host_regained = False
        if (
            regain_host
            and self.session.is_original_host(self.user)
            and self.session.host_is_switched()
        ):
            previous_host_id = self.session.host_id
            await self.session.revert_host()
            host_regained = True

        await self.accept()

        credentials = realtime.add_participant(
            meeting_id=self.session.meeting_id,
            participant_id=str(self.user.id),
            name=self.user.username,
        )
        await self.send_json(
            {
                'type': 'room_state',
                'credentials': credentials,
                'room_id': self.session.id,
                'room_name': self.session.name,
                'host_id': self.session.host_id,
                'members': list(self.session.members),
            }
        )

        if host_regained:
            await self.channel_layer.group_send(
                self.active_group,
                {
                    'type': 'host_changed',
                    'previous_host_id': previous_host_id,
                    'new_host_id': self.user.id,
                    'new_host_username': self.user.username,
                    'reason': 'host_reconnected',
                },
            )
        else:
            await self.channel_layer.group_send(
                self.active_group,
                {
                    'type': 'player_joined',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'member_count': len(self.session.members),
                },
            )

    # -- disconnect -------------------------------------------------------

    async def disconnect(self, close_code: int) -> None:
        if not hasattr(self, 'session') or not self.user:
            return

        if not self._is_member:
            await self.session.cancel_join_request(self.user.id)
            await self.channel_layer.group_send(
                self.pending_group,
                {
                    'type': 'join_request_cancelled',
                    'user_id': self.user.id,
                    'username': self.user.username,
                },
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
                await self.channel_layer.group_send(
                    self.active_group,
                    {
                        'type': 'host_changed',
                        'previous_host_id': self.user.id,
                        'new_host_id': new_host_id,
                        'new_host_username': '',
                        'reason': 'host_disconnected',
                    },
                )

        await self.channel_layer.group_send(
            self.active_group,
            {
                'type': 'player_left',
                'user_id': self.user.id,
                'username': self.user.username,
                'member_count': len(self.session.members),
            },
        )

    # -- receive ----------------------------------------------------------

    async def receive_json(self, content: dict[str, Any]) -> None:
        event_type = content.get('type')

        if event_type == 'accept_join_request':
            await self._handle_join_decision(content['user_id'], approve=True)
        elif event_type == 'reject_join_request':
            await self._handle_join_decision(content['user_id'], approve=False)
        elif event_type == 'chat':
            if not self._is_member:
                return
            await self.channel_layer.group_send(
                self.active_group,
                {
                    'type': 'chat_message',
                    'user_id': self.user.id,
                    'username': self.user.username,
                    'message': content['message'],
                },
            )

    async def _handle_join_decision(self, target_user_id: int, *, approve: bool) -> None:
        """Only accepted members may decide; broadcast happens on the pending
        group, since the target socket is only present there."""
        if not self._is_member:
            return

        if approve:
            waiting = await self.session.get_waiting_details(target_user_id)
            name = waiting['name'] if waiting else str(target_user_id)
            member = RoomMember(user_id=target_user_id, name=name)
            await self.session.add_member(member)
            await self.channel_layer.group_send(
                self.pending_group,
                {'type': 'join_request_accepted', 'user_id': target_user_id},
            )
        else:
            await self.session.reject_join(target_user_id)
            await self.channel_layer.group_send(
                self.pending_group,
                {'type': 'join_request_rejected', 'user_id': target_user_id},
            )

    # -- event handlers (inbound from channel layer) ----------------------

    async def player_joined(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'player_joined',
                'user_id': event['user_id'],
                'username': event['username'],
                'member_count': event['member_count'],
            }
        )

    async def player_left(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'player_left',
                'user_id': event['user_id'],
                'username': event['username'],
                'member_count': event['member_count'],
            }
        )

    async def host_changed(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'host_changed',
                'previous_host_id': event['previous_host_id'],
                'new_host_id': event['new_host_id'],
                'new_host_username': event['new_host_username'],
                'reason': event['reason'],
            }
        )

    async def game_started(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'game_started',
                'session_id': event['session_id'],
                'host': event['host'],
            }
        )

    async def room_closed(self, event: dict[str, Any]) -> None:
        await self.send_json({'type': 'room_closed', 'room_code': self.code})

    async def chat_message(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'chat_message',
                'user_id': event['user_id'],
                'username': event['username'],
                'message': event['message'],
            }
        )

    async def join_request_received(self, event: dict[str, Any]) -> None:
        # Delivered to everyone in pending_group (members + other waiters).
        # Members care; waiters can safely ignore it client-side.
        await self.send_json(
            {
                'type': 'join_request_received',
                'user_id': event['user_id'],
                'username': event['username'],
            }
        )

    async def join_request_cancelled(self, event: dict[str, Any]) -> None:
        await self.send_json(
            {
                'type': 'join_request_cancelled',
                'user_id': event['user_id'],
                'username': event['username'],
            }
        )

    async def join_request_accepted(self, event: dict[str, Any]) -> None:
        """Broadcast on pending_group. Only the targeted socket promotes
        itself into the active group; everyone else (other waiters,
        existing members) just gets an informational ping."""
        if event['user_id'] != self.user.id:
            return
        await self._connect_as_member(regain_host=False)

    async def join_request_rejected(self, event: dict[str, Any]) -> None:
        if event['user_id'] != self.user.id:
            return
        await self.send_json({'type': 'join_request_rejected', 'room_code': self.code})
        await self.close(code=4000)
