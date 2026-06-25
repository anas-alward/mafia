"""Transition scheduled rooms to WAITING when their scheduled_at has passed."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.room.models import Room


class Command(BaseCommand):
    help = 'Transition SCHEDULED rooms to WAITING when scheduled_at has passed.'

    def handle(self, *args: object, **options: object) -> None:
        now = timezone.now()
        updated = Room.objects.filter(
            status=Room.Status.SCHEDULED,
            scheduled_at__isnull=False,
            scheduled_at__lte=now,
        ).update(status=Room.Status.WAITING)

        self.stdout.write(f'Transitioned {updated} room(s) from SCHEDULED to WAITING.')
