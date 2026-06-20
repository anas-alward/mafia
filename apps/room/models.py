import uuid

from django.conf import settings
from django.db import models


class Room(models.Model):
    class Status(models.TextChoices):
        WAITING = 'waiting', 'Waiting'
        PLAYING = 'playing', 'Playing'
        FINISHED = 'finished', 'Finished'

    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_rooms',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=8, unique=True, db_index=True)
    max_members = models.PositiveSmallIntegerField(default=8)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='joined_rooms',
        blank=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.WAITING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.code})'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:6].upper()
        super().save(*args, **kwargs)

    @property
    def member_count(self):
        return self.members.count()
