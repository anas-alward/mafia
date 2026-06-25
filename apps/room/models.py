"""Room models: Room, RoomMember, RoomJoinRequest."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from apps.accounts.models import User

class Room(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        WAITING = 'waiting', 'Waiting'
        PLAYING = 'playing', 'Playing'
        FINISHED = 'finished', 'Finished'

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_rooms',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_rooms',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=8, unique=True, db_index=True)
    max_members = models.PositiveSmallIntegerField(default=8)
    meeting_id = models.CharField(max_length=64, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    role_configuration = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.WAITING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.name} ({self.code})'

    def save(self, *args: object, **kwargs: object) -> None:
        if not self.code:
            self.code = uuid.uuid4().hex[:6].upper()
        super().save(*args, **kwargs)

    @property
    def member_count(self) -> int:
        return self.members.count()

    def is_full(self) -> bool:
        return self.members.count() >= self.max_members

    def is_waiting(self) -> bool:
        return self.status == self.Status.WAITING

    def is_host(self, user: User) -> bool:
        return self.host_id == user.id
class RoomMember(models.Model):
    class AddedBy(models.TextChoices):
        HOST_DIRECT = 'host-direct', 'Host Direct'
        LINK_REQUEST = 'link-request', 'Link Request'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    joined_at = models.DateTimeField(auto_now_add=True)
    added_by = models.CharField(
        max_length=12,
        choices=AddedBy.choices,
        default=AddedBy.LINK_REQUEST,
    )
    cloudflare_participant_id = models.CharField(max_length=128, blank=True)

    class Meta:
        unique_together = ('user', 'room')
        ordering = ['joined_at']

    def __str__(self) -> str:
        return f'{self.user.username} in {self.room.name}'


class RoomJoinRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'
        EXPIRED = 'expired', 'Expired'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='join_requests',
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'room')
        ordering = ['-requested_at']

    def __str__(self) -> str:
        return f'{self.user.username} -> {self.room.code} ({self.status})'
