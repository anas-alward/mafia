"""Room model."""

from __future__ import annotations

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

    def is_waiting(self) -> bool:
        return self.status == self.Status.WAITING

    def is_host(self, user: User) -> bool:
        return self.host_id == user.id
