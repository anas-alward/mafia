"""Account business logic: register, login, verify, reset, change password."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.services.token import TokenService
from apps.accounts.tasks.email_tasks import (
    send_password_reset_email_task,
    send_verification_email_task,
)

if TYPE_CHECKING:
    from apps.accounts.models import User
else:
    User = get_user_model()


class EmailAuthBackend(ModelBackend):
    """Authenticate by email (used as username) for verified users only."""

    def authenticate(
        self,
        request: object | None = None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: object,
    ) -> User | None:
        if username is None or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=username.lower(), is_verified=True)
        except User.DoesNotExist:
            return None
        if user.check_password(password):
            return user
        return None


class AccountService:
    """Auth operations: register, login, verify email, reset/change password."""

    def __init__(self) -> None:
        self._token_service = TokenService

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, email: str, password: str) -> dict[str, object]:
        """Create or override an unverified account and send verification code."""
        email = email.lower().strip()

        # Check if a verified account already claims this email
        if User.objects.filter(email=email, is_verified=True).exists():
            raise ValueError('An account with this email already exists.')

        with transaction.atomic():
            user, _created = User.objects.update_or_create(
                email=email,
                defaults={
                    'username': email.split('@')[0],
                    'is_active': True,
                    'is_verified': False,
                },
            )
            user.set_password(password)
            user.save()

        if settings.EMAIL_VERIFICATION_ENABLED:
            code = self._token_service.generate_verification_code()
            user.verification_code_hash = self._token_service.hash_verification_code(code)
            user.verification_code_expiry = self._token_service.verification_expiry()
            user.save(update_fields=['verification_code_hash', 'verification_code_expiry'])
            send_verification_email_task.delay(to_email=email, code=code)

        return {'user': user}

    # ------------------------------------------------------------------
    # Email verification
    # ------------------------------------------------------------------

    def verify_email(self, email: str, code: str) -> User:
        """Verify an unverified account using the provided code."""
        email = email.lower().strip()

        try:
            user = User.objects.get(email=email, is_verified=False)
        except User.DoesNotExist:
            raise ValueError('No pending verification found for this email.')

        if settings.EMAIL_VERIFICATION_ENABLED:
            hashed = user.verification_code_hash or None
            expiry = user.verification_code_expiry

            if not hashed or expiry is None:
                raise ValueError('No verification code found. Please register again.')

            if self._token_service.is_code_expired(expiry):
                raise ValueError('Verification code has expired. Please register again.')

            if not self._token_service.validate_verification_code(code, hashed):
                raise ValueError('Invalid verification code.')

        user.is_verified = True
        user.verification_code_hash = ''
        user.verification_code_expiry = None
        user.save(update_fields=[
            'is_verified', 'verification_code_hash', 'verification_code_expiry',
        ])

        return user

    def resend_verification(self, email: str) -> None:
        """Resend the verification code (reset window). Only for unverified accounts."""
        email = email.lower().strip()

        try:
            user = User.objects.get(email=email, is_verified=False)
        except User.DoesNotExist:
            # Generic success — don't reveal whether account exists
            return

        if not settings.EMAIL_VERIFICATION_ENABLED:
            return

        code = self._token_service.generate_verification_code()
        user.verification_code_hash = self._token_service.hash_verification_code(code)
        user.verification_code_expiry = self._token_service.verification_expiry()
        user.save(update_fields=['verification_code_hash', 'verification_code_expiry'])

        send_verification_email_task.delay(to_email=email, code=code)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> dict[str, str | dict[str, object]]:
        """Authenticate with email+password. Returns tokens + user object."""
        email = email.lower().strip()

        from django.contrib.auth import authenticate

        user = authenticate(request=None, username=email, password=password)
        if user is None:
            raise ValueError('Invalid credentials.')

        refresh = RefreshToken.for_user(user)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
            },
        }

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------

    def request_password_reset(self, email: str) -> None:
        """Generate and send a password reset token for a verified user."""
        email = email.lower().strip()

        try:
            user = User.objects.get(email=email, is_verified=True)
        except User.DoesNotExist:
            # Generic success — don't reveal whether account exists
            return

        token = self._token_service.generate_password_reset_token()
        user.password_reset_hash = self._token_service.hash_password_reset_token(token)
        user.password_reset_expiry = self._token_service.reset_expiry()
        user.save(update_fields=['password_reset_hash', 'password_reset_expiry'])

        send_password_reset_email_task.delay(to_email=email, reset_token=token)

    def confirm_password_reset(self, email: str, token: str, new_password: str) -> None:
        """Set a new password using a valid reset token."""
        email = email.lower().strip()

        try:
            user = User.objects.get(email=email, is_verified=True)
        except User.DoesNotExist:
            raise ValueError('Invalid or expired reset token.')

        hashed = user.password_reset_hash or None
        expiry = user.password_reset_expiry

        if not hashed or expiry is None:
            raise ValueError('Invalid or expired reset token.')

        if self._token_service.is_reset_expired(expiry):
            raise ValueError('Invalid or expired reset token.')

        if not self._token_service.validate_password_reset_token(token, hashed):
            raise ValueError('Invalid or expired reset token.')

        user.set_password(new_password)
        user.password_reset_hash = ''
        user.password_reset_expiry = None
        user.save()

    # ------------------------------------------------------------------
    # Change password (authenticated)
    # ------------------------------------------------------------------

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        """Change password for an authenticated user after verifying current password."""
        if not user.check_password(current_password):
            raise ValueError('Current password is incorrect.')

        user.set_password(new_password)
        user.save()

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self, refresh_token: str) -> None:
        """Blacklist a refresh token."""
        token = RefreshToken(refresh_token)  # type: ignore[arg-type]
        token.blacklist()
