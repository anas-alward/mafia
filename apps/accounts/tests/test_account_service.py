"""Unit tests for AccountService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.accounts.services.account import AccountService
from apps.accounts.services.token import TokenService


class AccountServiceRegisterTests(TestCase):
    """Tests for register and verify_email methods."""

    def setUp(self) -> None:
        self.service = AccountService()

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_register_creates_unverified_user(self, mock_task: MagicMock) -> None:
        """register() creates user with is_verified=False and dispatches email task."""
        mock_task.delay = MagicMock()
        result = self.service.register(email='Test@Example.com', password='TestPass123')
        user: User = result['user']  # type: ignore[assignment]
        assert user.email == 'test@example.com'
        assert user.is_verified is False
        mock_task.delay.assert_called_once()

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_register_skips_email_when_flag_off(self) -> None:
        """register() skips email task when EMAIL_VERIFICATION_ENABLED is False."""
        result = self.service.register(email='dev@example.com', password='TestPass123')
        user: User = result['user']  # type: ignore[assignment]
        assert user.is_verified is False

    def test_register_verified_email_rejected(self) -> None:
        """register() raises ValueError for already verified email."""
        User.objects.create_user(
            username='v',
            email='verified@example.com',
            password='TestPass123',
            is_verified=True,
        )
        with self.assertRaises(ValueError):
            self.service.register(email='verified@example.com', password='NewPass456')

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_register_unverified_override(self, mock_task: MagicMock) -> None:
        """register() overrides unverified account with same email."""
        mock_task.delay = MagicMock()
        user = User.objects.create_user(
            username='old',
            email='override@example.com',
            password='OldPass1',
            is_verified=False,
        )
        old_pw = user.password

        self.service.register(email='override@example.com', password='NewPass2')
        user.refresh_from_db()
        assert user.password != old_pw
        assert user.is_verified is False

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_verify_email_with_valid_code(self) -> None:
        """verify_email() activates account with valid code."""
        user = User.objects.create_user(
            username='vuser',
            email='v@example.com',
            password='TestPass123',
            is_verified=False,
        )
        code = '654321'
        user.verification_code_hash = TokenService.hash_verification_code(code)
        user.verification_code_expiry = TokenService.verification_expiry()
        user.save()

        result = self.service.verify_email(email='v@example.com', code=code)
        assert result.is_verified is True

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_verify_email_wrong_code_fails(self) -> None:
        """verify_email() rejects wrong verification code."""
        User.objects.create_user(
            username='wuser',
            email='w@example.com',
            password='TestPass123',
            is_verified=False,
        )
        code = '111111'
        user = User.objects.get(email='w@example.com')
        user.verification_code_hash = TokenService.hash_verification_code(code)
        user.verification_code_expiry = TokenService.verification_expiry()
        user.save()

        with self.assertRaises(ValueError):
            self.service.verify_email(email='w@example.com', code='222222')

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_verify_email_expired_code_fails(self) -> None:
        """verify_email() rejects expired verification code."""
        user = User.objects.create_user(
            username='xuser',
            email='x@example.com',
            password='TestPass123',
            is_verified=False,
        )
        code = '999999'
        user.verification_code_hash = TokenService.hash_verification_code(code)
        user.verification_code_expiry = datetime.now(UTC) - timedelta(minutes=1)
        user.save()

        with self.assertRaises(ValueError):
            self.service.verify_email(email='x@example.com', code=code)

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_verify_email_flag_off_any_code(self) -> None:
        """verify_email() accepts any code when flag is OFF."""
        User.objects.create_user(
            username='dev2',
            email='dev2@example.com',
            password='TestPass123',
            is_verified=False,
        )
        result = self.service.verify_email(email='dev2@example.com', code='anything')
        assert result.is_verified is True
