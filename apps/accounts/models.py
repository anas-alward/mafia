from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # Add custom fields here if needed
    # For example: email_verified = models.BooleanField(default=False)
    pass
