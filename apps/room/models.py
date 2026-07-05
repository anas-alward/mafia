"""Room model."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.accounts.models import User
from apps.core.utils.uuid import generate_code


class Room(models.Model):
    class Status(models.TextChoices):
        PLAYING = 'playing', 'Playing'
        FINISHED = 'finished', 'Finished'

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=8, unique=True, default=generate_code, db_index=True)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_rooms',
    )
    meeting_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=10,
        default=Status.PLAYING,
        choices=Status.choices,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.name} ({self.code})'

    def is_finished(self):
        return self.status == self.Status.FINISHED

    def is_host(self, user: User) -> bool:
        return self.host_id == user.id
