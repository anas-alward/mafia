"""Token generation, hashing, and validation utilities.

Verification codes: 6-digit numeric, hashed via Django password hasher.
Password reset tokens: UUID-based, hashed via Django password hasher.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password


class TokenService:
    """Generate, hash, and validate verification and password reset tokens."""

    @staticmethod
    def generate_verification_code() -> str:
        """Generate a cryptographically random 6-digit numeric code."""
        return ''.join(
            str(secrets.randbelow(10)) for _ in range(6)
        )

    @staticmethod
    def hash_verification_code(code: str) -> str:
        """Hash a verification code using Django's password hasher."""
        return make_password(code)

    @staticmethod
    def validate_verification_code(code: str, hashed: str) -> bool:
        """Check a plaintext code against its hash."""
        return check_password(code, hashed)

    @staticmethod
    def is_code_expired(expires_at: datetime) -> bool:
        """Return True if the code's expiry timestamp has passed."""
        return datetime.now(UTC) >= expires_at

    @staticmethod
    def generate_password_reset_token() -> str:
        """Generate a UUID-based reset token."""
        return str(uuid.uuid4())

    @staticmethod
    def hash_password_reset_token(token: str) -> str:
        """Hash a reset token using Django's password hasher."""
        return make_password(token)

    @staticmethod
    def validate_password_reset_token(token: str, hashed: str) -> bool:
        """Check a plaintext reset token against its hash."""
        return check_password(token, hashed)

    @staticmethod
    def is_reset_expired(expires_at: datetime) -> bool:
        """Return True if the reset token's expiry timestamp has passed."""
        return datetime.now(UTC) >= expires_at

    @staticmethod
    def verification_expiry() -> datetime:
        """Return the expiry datetime for a new verification code."""
        return datetime.now(UTC) + settings.EMAIL_VERIFICATION_TIMEOUT

    @staticmethod
    def reset_expiry() -> datetime:
        """Return the expiry datetime for a new password reset token."""
        return datetime.now(UTC) + settings.PASSWORD_RESET_TIMEOUT
