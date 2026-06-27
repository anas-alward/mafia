"""RoomConsumer: real-time room events via WebSocket."""

from __future__ import annotations

import os
from typing import Any

import redis.asyncio as aioredis
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from .models import Room
from .realtime import realtime


def _get_redis() -> aioredis.Redis:
    return aioredis.Redis(
        host=os.environ.get('REDIS_HOST', 'redis'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=2,
        decode_responses=True,
    )


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.code: str = self.scope['url_route']['kwargs']['code']
        self.room_group: str = f'room_{self.code}'
        self.user: Any = self.scope.get('user')
        self._is_member: bool = False

        room = await self.get_room()
        if not room or not self.user:
            await self.close(code=4001)
            return

        if room.status == Room.Status.FINISHED:
            await self.close(code=4002)
            return

        if await self._check_membership(room):
            await self._connect_as_member(room)
        else:
            await self._connect_as_pending(room)

    # -- connect helpers --------------------------------------------------

    async def _connect_as_member(self, room: Room) -> None:
        self._is_member = True

        host_regained = False
        if room.host_id != self.user.id:
            if await self._was_original_host(room):
                await self._regain_host(room)
                host_regained = True

        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        room_state = await self._get_room_state(room)
        credentials = realtime.add_participant(
            meeting_id=room.meeting_id,
            participant_id=str(self.user.id),
            name=self.user.username,
        )
        await self.send_json({
            'type': 'room_state',
            'credentials': credentials,
            **room_state,
        })

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

    async def _connect_as_pending(self, room: Room) -> None:
        self._is_member = False
        await self.accept()

        r = _get_redis()
        try:
            await r.hset(
                f'room:{self.code}:pending',
                str(self.user.id),
                self.channel_name,
            )
        finally:
            await r.aclose()

        await self.channel_layer.group_send(self.room_group, {
            'type': 'join_request_received',
            'user_id': self.user.id,
            'username': self.user.username,
        })

    # -- disconnect -------------------------------------------------------

    async def disconnect(self, close_code: int) -> None:
        if not hasattr(self, 'room_group'):
            return

        if not self._is_member:
            await self._remove_from_pending()
            await self.channel_layer.group_send(self.room_group, {
                'type': 'join_request_cancelled',
                'user_id': self.user.id if self.user else 0,
                'username': self.user.username if self.user else '',
            })
            return

        room = await self.get_room()
        was_host = room and room.host_id == (self.user.id if self.user else None)

        await self.remove_member()
        await self.channel_layer.group_discard(self.room_group, self.channel_name)

        member_count = await self.get_member_count()

        if was_host and member_count > 0:
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

    # -- receive ----------------------------------------------------------

    async def receive_json(self, content: dict[str, Any]) -> None:
        event_type = content.get('type')

        if event_type == 'accept_join_request':
            await self._accept_pending(content)
        elif event_type == 'reject_join_request':
            await self._reject_pending(content)
        elif event_type == 'chat':
            if not self._is_member:
                return
            await self.channel_layer.group_send(self.room_group, {
                'type': 'chat_message',
                'user_id': self.user.id,
                'username': self.user.username,
                'message': content['message'],
            })

    async def _accept_pending(self, content: dict[str, Any]) -> None:
        user_id = content['user_id']

        r = _get_redis()
        try:
            channel_name = await r.hget(f'room:{self.code}:pending', str(user_id))
            if not channel_name:
                return
            await r.hdel(f'room:{self.code}:pending', str(user_id))
        finally:
            await r.aclose()

        room = await self.get_room()
        username = await self._add_member(room, user_id)

        await self.channel_layer.send(channel_name, {
            'type': 'join_request_accepted',
        })

        member_count = await self.get_member_count()
        await self.channel_layer.group_send(self.room_group, {
            'type': 'player_joined',
            'user_id': user_id,
            'username': username,
            'member_count': member_count,
        })

    async def _reject_pending(self, content: dict[str, Any]) -> None:
        user_id = content['user_id']

        r = _get_redis()
        try:
            channel_name = await r.hget(f'room:{self.code}:pending', str(user_id))
            if not channel_name:
                return
            await r.hdel(f'room:{self.code}:pending', str(user_id))
        finally:
            await r.aclose()

        await self.channel_layer.send(channel_name, {
            'type': 'join_request_rejected',
        })

    # -- event handlers (inbound from channel layer) ----------------------

    async def room_state(self, event: dict[str, Any]) -> None:
        pass  # Only sent directly to the connecting client

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
            'user_id': event['user_id'],
            'username': event['username'],
        })

    async def join_request_cancelled(self, event: dict[str, Any]) -> None:
        await self.send_json({
            'type': 'join_request_cancelled',
            'user_id': event['user_id'],
            'username': event['username'],
        })

    async def join_request_accepted(self, event: dict[str, Any]) -> None:
        """Received by the pending user when the host admits them."""
        self._is_member = True
        await self.channel_layer.group_add(self.room_group, self.channel_name)

        room = await self.get_room()
        room_state = await self._get_room_state(room)
        credentials = realtime.add_participant(
            meeting_id=room.meeting_id,
            participant_id=str(self.user.id),
            name=self.user.username,
        )

        await self.send_json({
            'type': 'room_state',
            'credentials': credentials,
            **room_state,
        })

    async def join_request_rejected(self, event: dict[str, Any]) -> None:
        """Received by the pending user when the host denies them."""
        await self.send_json({
            'type': 'join_request_rejected',
            'room_code': self.code,
        })
        await self.close(code=4000)

    # -- database helpers -------------------------------------------------

    @database_sync_to_async
    def get_room(self) -> Room | None:
        try:
            return Room.objects.select_related('host').get(code=self.code)
        except Room.DoesNotExist:
            return None

    async def _check_membership(self, room: Room) -> bool:
        r = _get_redis()
        try:
            return await r.hexists(f'room:{self.code}:members', str(self.user.id))
        finally:
            await r.aclose()

    async def get_member_count(self) -> int:
        r = _get_redis()
        try:
            return await r.hlen(f'room:{self.code}:members')
        finally:
            await r.aclose()

    async def remove_member(self) -> None:
        r = _get_redis()
        try:
            await r.hdel(f'room:{self.code}:members', str(self.user.id))
        finally:
            await r.aclose()

    async def _add_member(self, room: Room, user_id: int) -> str:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = await database_sync_to_async(User.objects.get)(id=user_id)
        username = user.username
        r = _get_redis()
        try:
            await r.hset(f'room:{self.code}:members', str(user_id), username)
        finally:
            await r.aclose()
        return username

    async def _get_room_state(self, room: Room) -> dict[str, Any]:
        r = _get_redis()
        try:
            raw = await r.hgetall(f'room:{self.code}:members')
        finally:
            await r.aclose()

        members = [
            {
                'id': int(uid),
                'username': uname,
                'is_host': int(uid) == room.host_id,
            }
            for uid, uname in raw.items()
        ]

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
            'members': members,
            'member_count': len(members),
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
        # Membership is in Redis now — just clear the host.
        # The new host will be assigned when someone claims it.
        return 0, ''

    # -- redis helpers ----------------------------------------------------

    async def _remove_from_pending(self) -> bool:
        if not self.user:
            return False
        r = _get_redis()
        try:
            deleted = await r.hdel(f'room:{self.code}:pending', str(self.user.id))
            return bool(deleted)
        finally:
            await r.aclose()
