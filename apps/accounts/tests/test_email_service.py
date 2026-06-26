"""Unit tests for EmailService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.accounts.services.email import EmailService


class EmailServiceTests(SimpleTestCase):
    """Tests for EmailService Mailjet integration."""

    @override_settings(EMAIL_VERIFICATION_ENABLED=True, MAILJET_SENDER_EMAIL='noreply@mafia.game')
    @patch('apps.accounts.services.email.Client')
    def test_send_verification_email_dispatches_to_mailjet(self, mock_client: MagicMock) -> None:
        """send_verification_email calls Mailjet API with correct payload."""
        mock_send = MagicMock()
        mock_send.json.return_value = {'Messages': [{'Status': 'success'}]}
        mock_client.return_value = MagicMock(send=mock_send)

        service = EmailService()
        service.send_verification_email(to_email='test@example.com', code='123456')

        mock_send.create.assert_called_once()
        call_data = mock_send.create.call_args.kwargs['data']
        msg = call_data['Messages'][0]
        assert msg['From']['Email'] == 'noreply@mafia.game'
        assert msg['To'][0]['Email'] == 'test@example.com'
        assert msg['Subject'] == 'Verify your email address'
        assert '123456' in msg['HTMLPart']

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    @patch('apps.accounts.services.email.Client')
    def test_send_verification_email_skips_when_flag_off(self, mock_client: MagicMock) -> None:
        """When EMAIL_VERIFICATION_ENABLED is False, no Mailjet API call is made."""
        mock_send = MagicMock()
        mock_client.return_value = MagicMock(send=mock_send)

        service = EmailService()
        service.send_verification_email(to_email='test@example.com', code='123456')

        mock_send.create.assert_not_called()

    @override_settings(EMAIL_VERIFICATION_ENABLED=True, MAILJET_SENDER_EMAIL='noreply@mafia.game')
    @patch('apps.accounts.services.email.Client')
    def test_send_password_reset_email_dispatches_to_mailjet(self, mock_client: MagicMock) -> None:
        """send_password_reset_email calls Mailjet API with reset token."""
        mock_send = MagicMock()
        mock_send.json.return_value = {'Messages': [{'Status': 'success'}]}
        mock_client.return_value = MagicMock(send=mock_send)

        service = EmailService()
        service.send_password_reset_email(to_email='test@example.com', reset_token='abcd-token')

        call_data = mock_send.create.call_args.kwargs['data']
        msg = call_data['Messages'][0]
        assert msg['Subject'] == 'Reset your password'
        assert 'abcd-token' in msg['HTMLPart']

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    @patch('apps.accounts.services.email.Client')
    def test_send_password_reset_email_skips_when_flag_off(self, mock_client: MagicMock) -> None:
        """When EMAIL_VERIFICATION_ENABLED is False, no Mailjet API call for reset either."""
        mock_send = MagicMock()
        mock_client.return_value = MagicMock(send=mock_send)

        service = EmailService()
        service.send_password_reset_email(to_email='test@example.com', reset_token='token')

        mock_send.create.assert_not_called()
