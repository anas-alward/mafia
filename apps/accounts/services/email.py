"""Email sending service with Mailjet integration.

Respects EMAIL_VERIFICATION_ENABLED flag — when OFF, all sends are no-ops.
"""

from __future__ import annotations

from django.conf import settings
from mailjet_rest import Client


class EmailService:
    """Send transactional emails via Mailjet."""

    def __init__(self) -> None:
        self._client = Client(
            auth=(settings.MAILJET_API_KEY, settings.MAILJET_API_SECRET),
            version='v3.1',
        )

    @property
    def _enabled(self) -> bool:
        return bool(getattr(settings, 'EMAIL_VERIFICATION_ENABLED', True))

    def send_verification_email(self, to_email: str, code: str) -> None:
        """Send a verification email with a 6-digit code."""
        if not self._enabled:
            return
        data = {
            'Messages': [
                {
                    'From': {'Email': settings.MAILJET_SENDER_EMAIL, 'Name': 'Mafia Game'},
                    'To': [{'Email': to_email}],
                    'Subject': 'Verify your email address',
                    'HTMLPart': (
                        f'<p>Welcome to Mafia!</p>'
                        f'<p>Your verification code is: <strong>{code}</strong></p>'
                        f'<p>This code expires in '
                        f'{settings.EMAIL_VERIFICATION_TIMEOUT.seconds // 60} minutes.</p>'
                    ),
                }
            ]
        }
        self._client.send.create(data=data)

    def send_password_reset_email(self, to_email: str, reset_token: str) -> None:
        """Send a password reset email with a reset token."""
        if not self._enabled:
            return
        data = {
            'Messages': [
                {
                    'From': {'Email': settings.MAILJET_SENDER_EMAIL, 'Name': 'Mafia Game'},
                    'To': [{'Email': to_email}],
                    'Subject': 'Reset your password',
                    'HTMLPart': (
                        f'<p>We received a request to reset your password.</p>'
                        f'<p>Your password reset token is: <strong>{reset_token}</strong></p>'
                        f'<p>This token expires in 1 hour.</p>'
                        f'<p>If you did not request this, please ignore this email.</p>'
                    ),
                }
            ]
        }
        self._client.send.create(data=data)
