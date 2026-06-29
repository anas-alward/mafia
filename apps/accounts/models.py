from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    verification_code_hash = models.CharField(max_length=128, default='', blank=True)
    verification_code_expiry = models.DateTimeField(null=True, default=None, blank=True)
    password_reset_hash = models.CharField(max_length=128, default='', blank=True)
    password_reset_expiry = models.DateTimeField(null=True, default=None, blank=True)

    USERNAME_FIELD = 'email'

    REQUIRED_FIELDS = ['username']