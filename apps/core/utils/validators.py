"""Shared validation utilities."""

from __future__ import annotations

from django.core.validators import RegexValidator

username_validator = RegexValidator(
    regex=r'^[a-zA-Z0-9_-]+$',
    message='Username can only contain letters, numbers, underscores, and hyphens.',
)
