"""Room business logic."""

from __future__ import annotations

import os
import uuid

import redis
from django.contrib.auth import get_user_model
from django.db import models

from .models import Room
from .realtime import realtime

User = get_user_model()


def _get_redis() -> redis.Redis:
    return redis.Redis(
        host=os.environ.get('REDIS_HOST', 'redis'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=2,
        decode_responses=True,
    )


def _members_key(code: str) -> str:
    return f'room:{code}:members'


def generate_room_code(length: int = 6) -> str:
    code = uuid.uuid4().hex[:length].upper()
    while Room.objects.filter(code=code).exists():
        code = uuid.uuid4().hex[:length].upper()
    return code


class RoomService:
    # -- room lifecycle --------------------------------------------------

    def create_room(
        self,
        host: User,
        name: str = 'New Room',
        max_members: int = 8,
        scheduled_at: str | None = None,
        role_configuration: dict | None = None,
    ) -> Room:
        code = generate_room_code()
        room = Room.objects.create(
            host=host,
            created_by=host,
            name=name,
            code=code,
            max_members=max_members,
            scheduled_at=scheduled_at,
            role_configuration=role_configuration or {},
        )
        # meeting_id = realtime.create_meeting(room.name)
        # room.meeting_id = meeting_id
        # room.save(update_fields=['meeting_id'])

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

    # -- members ---------------------------------------------------------

    def is_member(self, code: str, user_id: int) -> bool:
        r = _get_redis()
        try:
            return r.hexists(_members_key(code), str(user_id))
        finally:
            r.close()
