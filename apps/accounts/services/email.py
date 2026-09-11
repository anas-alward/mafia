"""Email sending service backed by Django's email backend (Anymail + Resend).

Respects EMAIL_VERIFICATION_ENABLED flag — when OFF, all sends are no-ops.
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail


class EmailService:
    """Send transactional emails via Django/Anymail (Resend ESP)."""

    @property
    def _enabled(self) -> bool:
        return bool(getattr(settings, 'EMAIL_VERIFICATION_ENABLED', True))

    def send_verification_email(self, to_email: str, code: str) -> None:
        """Send a verification email with a 6-digit code."""
        if not self._enabled:
            print("NOT enabled++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
            return
        minutes = settings.EMAIL_VERIFICATION_TIMEOUT.seconds // 60
        send_mail(
            subject='Verify your email address',
            message=(
                f'Welcome to Mafia!\n\n'
                f'Your verification code is: {code}\n'
                f'This code expires in {minutes} minutes.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=(
                f'<p>Welcome to Mafia!</p>'
                f'<p>Your verification code is: <strong>{code}</strong></p>'
                f'<p>This code expires in {minutes} minutes.</p>'
            ),
        )

    def send_password_reset_email(self, to_email: str, reset_token: str) -> None:
        """Send a password reset email with a link carrying the reset token."""
        if not self._enabled:
            return
        from urllib.parse import urlencode

        query = urlencode({'token': reset_token, 'email': to_email})
        reset_link = f'{settings.FRONTEND_URL}/password/reset?{query}'
        send_mail(
            subject='Reset your password',
            message=(
                f'We received a request to reset your password.\n\n'
                f'Reset your password here: {reset_link}\n'
                f'This link expires in 1 hour.\n'
                f'If you did not request this, please ignore this email.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=(
                f'<p>We received a request to reset your password.</p>'
                f'<p><a href="{reset_link}">Reset your password</a></p>'
                f'<p>This link expires in 1 hour.</p>'
                f'<p>If you did not request this, please ignore this email.</p>'
            ),
        )
