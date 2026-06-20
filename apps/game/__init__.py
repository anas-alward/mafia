from django.db import models


class Role(models.TextChoices):
    MAFIA = 'mafia', 'Mafia'
    DETECTIVE = 'detective', 'Detective'
    DOCTOR = 'doctor', 'Doctor'
    VILLAGER = 'villager', 'Villager'
