from django.conf import settings
from django.db import models

from . import Role


class GameSession(models.Model):
    class Phase(models.TextChoices):
        NIGHT = 'night', 'Night'
        DAY = 'day', 'Day'
        VOTING = 'voting', 'Voting'
        ENDED = 'ended', 'Ended'

    class Outcome(models.TextChoices):
        MAFIA = 'mafia', 'Mafia'
        VILLAGERS = 'villagers', 'Villagers'
        DRAW = 'draw', 'Draw'

    room = models.OneToOneField(
        'room.Room',
        on_delete=models.CASCADE,
        related_name='game_session',
    )
    phase = models.CharField(
        max_length=12,
        choices=Phase.choices,
        default=Phase.NIGHT,
    )
    round_number = models.PositiveSmallIntegerField(default=1)
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='Participant',
        related_name='game_sessions',
    )
    night_actions = models.JSONField(default=dict, blank=True)
    winner = models.CharField(
        max_length=10,
        choices=Outcome.choices,
        blank=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.room.name} — Round {self.round_number} ({self.get_phase_display()})'

    def alive_players(self):
        return self.participant_set.filter(is_alive=True)

    def players_by_role(self, role):
        return self.participant_set.filter(role=role)


class Participant(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='participations',
    )
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=12, choices=Role.choices)
    is_alive = models.BooleanField(default=True)
    won = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ('user', 'game_session')

    def __str__(self):
        return f'{self.user.username} as {self.get_role_display()}'
