"""RoomConsumer: real-time room events via WebSocket."""

from __future__ import annotations

from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from .realtime import realtime
from .models import Room, RoomMember


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.code: str = self.scope['url_route']['kwargs']['code']
        self.room_group: str = f'room_{self.code}'
        self.user: Any = self.scope.get('user')

        room = await self.get_room()
        if not room or not self.user:
            await self.close(code=4001)
            return

        if room.status == Room.Status.FINISHED:
            await self.close(code=4002)
            return

        # Original host reconnects — regain host role
        host_regained = False
        if room.host_id != self.user.id:
            was_original_host = await self._was_original_host(room)
            if was_original_host:
                await self._regain_host(room)
                host_regained = True

        if not self.is_member():
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        # Send full current room state to the connecting client
        room_state = await self._get_room_state(room)
        credentials = realtime.add_participant(room.meeting_id)
        await self.send_json({'type': 'room_state','credentials': credentials ,**room_state})

        if host_regained:
            await self.channel_layer.group_send(self.room_group, {
                'type': 'host_changed',
                'previous_host_id': room.host_id,
                'previous_host_username': '',
                'new_host_id': self.user.id,
                'new_host_username': self.user.username,
                'reason': 'host_reconnected',
            })
        else:
            member_count = await self.get_member_count()
            await self.channel_layer.group_send(self.room_group, {
                'type': 'player_joined',
                'user_id': self.user.id,
                'username': self.user.username,
                'member_count': member_count,
            })

    async def disconnect(self, close_code: int) -> None:
        if not hasattr(self, 'room_group'):
            return

        room = await self.get_room()
        was_host = room and room.host_id == (self.user.id if self.user else None)

        await self.remove_member()
        await self.channel_layer.group_discard(self.room_group, self.channel_name)

        member_count = await self.get_member_count()

        if was_host and member_count > 0:
            # Transfer host to second joiner
            new_host_id, new_host_username = await self._transfer_host(room)
            await self.channel_layer.group_send(self.room_group, {
                'type': 'host_changed',
                'previous_host_id': self.user.id,
                'previous_host_username': self.user.username,
                'new_host_id': new_host_id,
                'new_host_username': new_host_username,
                'reason': 'host_disconnected',
            })

        await self.channel_layer.group_send(self.room_group, {
            'type': 'player_left',
            'user_id': self.user.id if self.user else 0,
            'username': self.user.username if self.user else '',
            'member_count': member_count,
        })

    async def receive_json(self, content: dict[str, Any]) -> None:
        event_type = content.get('type')

        if event_type == 'chat':
            await self.channel_layer.group_send(self.room_group, {
                'type': 'chat_message',
                'user_id': self.user.id,
                'username': self.user.username,
                'message': content['message'],
            })

    # ---- event handlers ----

    async def room_state(self, event: dict[str, Any]) -> None:
        pass  # Only sent to the connecting client, not from group_send

    async def player_joined(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'player_joined',
            'user_id': event['user_id'],
            'username': event['username'],
            'member_count': event['member_count'],
        })

    async def player_left(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'player_left',
            'user_id': event['user_id'],
            'username': event['username'],
            'member_count': event['member_count'],
        })

    async def chat_message(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'chat',
            'user_id': event['user_id'],
            'username': event['username'],
            'message': event['message'],
        })

    async def host_changed(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'host_changed',
            'previous_host_id': event['previous_host_id'],
            'previous_host_username': event['previous_host_username'],
            'new_host_id': event['new_host_id'],
            'new_host_username': event['new_host_username'],
            'reason': event['reason'],
        })

    async def game_started(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'game_started',
            'session_id': event['session_id'],
            'host': event['host'],
        })

    async def room_closed(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'room_closed',
            'room_code': self.code,
        })

    async def member_removed(self, event: dict[str, Any]) -> None:
        if event.get('user_id') == self.user.id:
            await self.send_json({
                'type': 'member_removed',
                'room_code': self.code,
            })

    async def join_request_received(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'join_request_received',
            'request_id': event['request_id'],
            'user_id': event['user_id'],
            'username': event['username'],
        })

    async def join_request_resolved(self, event: dict[str, Any]) -> None:
        if event.get('user_id') == self.user.id:
            await self.send_json({
                'type': 'join_request_resolved',
                'room_code': self.code,
                'room_name': event.get('room_name', ''),
                'status': event['status'],
            })

    # ---- database helpers ----

    @database_sync_to_async
    def get_room(self) -> Room | None:
        try:
            return Room.objects.select_related('host').get(code=self.code)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def is_member(self, room: Room) -> None:
        return RoomMember.objects.filter(user=self.user, room=room).exists()

    @database_sync_to_async
    def remove_member(self) -> None:
        try:
            RoomMember.objects.filter(user=self.user, room__code=self.code).delete()
        except Exception:
            pass

    @database_sync_to_async
    def get_member_count(self) -> int:
        return RoomMember.objects.filter(room__code=self.code).count()

    @database_sync_to_async
    def _get_room_state(self, room: Room) -> dict[str, Any]:
        return {
            'room': {
                'code': room.code,
                'name': room.name,
                'status': room.status,
                'host': {'id': room.host_id, 'username': room.host.username},
                'max_members': room.max_members,
                'role_configuration': room.role_configuration,
                'scheduled_at': (
                    room.scheduled_at.isoformat() if room.scheduled_at else None
                ),
            },
            'members': [
                {
                    'id': m.user_id,
                    'username': m.user.username,
                    'joined_at': m.joined_at.isoformat(),
                    'is_host': m.user_id == room.host_id,
                }
                for m in (
                    RoomMember.objects
                    .filter(room=room)
                    .select_related('user')
                    .order_by('joined_at')
                )
            ],
            'member_count': RoomMember.objects.filter(room=room).count(),
        }

    @database_sync_to_async
    def _was_original_host(self, room: Room) -> bool:
        return room.created_by_id == self.user.id

    @database_sync_to_async
    def _regain_host(self, room: Room) -> None:
        room.host = self.user
        room.save(update_fields=['host'])

    @database_sync_to_async
    def _transfer_host(self, room: Room) -> tuple[int, str]:
        second_member = (
            RoomMember.objects
            .filter(room=room)
            .exclude(user_id=self.user.id)
            .order_by('joined_at')
            .select_related('user')
            .first()
        )
        if second_member:
            room.host = second_member.user
            room.save(update_fields=['host'])
            return second_member.user_id, second_member.user.username
        return 0, ''
