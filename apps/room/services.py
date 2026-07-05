"""Room business logic."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models

from .models import Room
from apps.core.webrtc import webrtc_client

User = get_user_model()


class RoomService:
    def create_room(
        self,
        host: User,
        name: str = 'New Room',
    ) -> Room:
        room = Room.objects.create(
            host=host,
            name=name,
        )
        meeting_id = webrtc_client.create_meeting(room.name)
        room.meeting_id = meeting_id
        room.save(update_fields=['meeting_id'])
        return room

    def get_hosted_rooms(self, host: User) -> models.QuerySet[Room]:
        return Room.objects.filter(host=host).order_by('-created_at')

    def get_room_by_code(self, code: str) -> Room:
        try:
            return Room.objects.get(code=code)
        except Room.DoesNotExist:
            raise ValueError('Room not found.')

    def finish_room(self, room: Room, user: User) -> Room:
        if room.host != user:
            raise ValueError('Only the host can finish the room.')
        if room.status == Room.Status.FINISHED:
            raise ValueError('Room is already finished.')
        room.status = Room.Status.FINISHED
        room.save(update_fields=['status'])
        return room

