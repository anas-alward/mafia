"""Unit tests for EmailService (Django email backend / Anymail+Resend)."""

from __future__ import annotations

from django.core import mail
from django.test import SimpleTestCase, override_settings

from apps.accounts.services.email import EmailService


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='noreply@mafia.game',
)
class EmailServiceTests(SimpleTestCase):
    """Tests for EmailService via Django's locmem outbox."""

    def setUp(self) -> None:
        mail.outbox.clear()

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_send_verification_email_dispatches(self) -> None:
        """send_verification_email queues one message with correct payload."""
        service = EmailService()
        service.send_verification_email(to_email='test@example.com', code='123456')

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.from_email == 'noreply@mafia.game'
        assert msg.to == ['test@example.com']
        assert msg.subject == 'Verify your email address'
        assert '123456' in msg.body
        assert msg.alternatives
        assert '123456' in msg.alternatives[0][0]

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_send_verification_email_skips_when_flag_off(self) -> None:
        """When EMAIL_VERIFICATION_ENABLED is False, nothing is sent."""
        service = EmailService()
        service.send_verification_email(to_email='test@example.com', code='123456')

        assert len(mail.outbox) == 0

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_send_password_reset_email_dispatches(self) -> None:
        """send_password_reset_email queues one message with reset token."""
        service = EmailService()
        service.send_password_reset_email(to_email='test@example.com', reset_token='abcd-token')

        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.subject == 'Reset your password'
        assert 'abcd-token' in msg.body
        assert msg.alternatives
        assert 'abcd-token' in msg.alternatives[0][0]

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_send_password_reset_email_skips_when_flag_off(self) -> None:
        """When EMAIL_VERIFICATION_ENABLED is False, no reset email either."""
        service = EmailService()
        service.send_password_reset_email(to_email='test@example.com', reset_token='token')

        assert len(mail.outbox) == 0
