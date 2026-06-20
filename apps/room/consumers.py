import asyncio
import random

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.game import Role
from apps.game.models import GameSession, Participant
from .models import Room


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.code = self.scope['url_route']['kwargs']['code']
        self.room_group = f'room_{self.code}'
        self.user = self.scope.get('user')

        room = await self.get_room()
        if not room or not self.user:
            await self.close(code=4001)
            return

        if room.status != Room.Status.WAITING:
            await self.close(code=4002)
            return

        await self.add_member(room)
        await self.channel_layer.group_add(self.room_group, self.channel_name)
        await self.accept()

        member_count = await self.get_member_count()
        asyncio.create_task(self._broadcast('player_joined', {
            'user_id': self.user.id,
            'username': self.user.username,
            'member_count': member_count,
        }))

    async def disconnect(self, close_code):
        if not hasattr(self, 'room_group'):
            return

        await self.remove_member()
        await self.channel_layer.group_discard(self.room_group, self.channel_name)

        member_count = await self.get_member_count()
        asyncio.create_task(self._broadcast('player_left', {
            'user_id': self.user.id,
            'username': self.user.username,
            'member_count': member_count,
        }))

    async def _broadcast(self, event_type, payload):
        await self.channel_layer.group_send(self.room_group, {
            'type': event_type,
            **payload,
        })

    async def receive_json(self, content):
        event_type = content.get('type')

        if event_type == 'chat':
            await self.channel_layer.group_send(self.room_group, {
                'type': 'chat_message',
                'user_id': self.user.id,
                'username': self.user.username,
                'message': content['message'],
            })

        elif event_type == 'start_game':
            room = await self.get_room()
            if room and room.host_id == self.user.id:
                session_id = await self.create_game_session(room)
                await self.set_room_status(Room.Status.PLAYING)
                await self.channel_layer.group_send(self.room_group, {
                    'type': 'game_started',
                    'session_id': session_id,
                    'host': self.user.username,
                })

    # ---- event handlers (sent to group, received by each client) ----

    async def player_joined(self, event):
        await self.send_json({
            'type': 'player_joined',
            'user_id': event['user_id'],
            'username': event['username'],
            'member_count': event['member_count'],
        })

    async def player_left(self, event):
        await self.send_json({
            'type': 'player_left',
            'user_id': event['user_id'],
            'username': event['username'],
            'member_count': event['member_count'],
        })

    async def chat_message(self, event):
        await self.send_json({
            'type': 'chat',
            'user_id': event['user_id'],
            'username': event['username'],
            'message': event['message'],
        })

    async def game_started(self, event):
        await self.send_json({
            'type': 'game_started',
            'session_id': event['session_id'],
            'host': event['host'],
        })

    # ---- database helpers ----

    @database_sync_to_async
    def get_room(self):
        try:
            return Room.objects.select_related('host').get(code=self.code)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def add_member(self, room):
        room.members.add(self.user)
        return room.members.count()

    @database_sync_to_async
    def remove_member(self):
        try:
            room = Room.objects.get(code=self.code)
            room.members.remove(self.user)
        except Room.DoesNotExist:
            pass

    @database_sync_to_async
    def get_member_count(self):
        return Room.objects.get(code=self.code).members.count()

    @database_sync_to_async
    def set_room_status(self, status):
        Room.objects.filter(code=self.code).update(status=status)

    @database_sync_to_async
    def create_game_session(self, room):
        members = list(room.members.all())
        roles = self._assign_roles(len(members))
        random.shuffle(roles)

        session = GameSession.objects.create(room=room)
        for user, role in zip(members, roles):
            Participant.objects.create(user=user, game_session=session, role=role)

        return session.pk

    def _assign_roles(self, count):
        if count < 4:
            return [Role.VILLAGER] * count
        mafia = max(1, count // 4)
        specials = [Role.DETECTIVE, Role.DOCTOR][:min(2, max(0, count - mafia - 2))]
        villagers = count - mafia - len(specials)
        return (
            [Role.MAFIA] * mafia
            + specials
            + [Role.VILLAGER] * villagers
        )
