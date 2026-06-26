# mypy: disable-error-code="attr-defined"
"""Integration tests for account auth endpoints."""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()


class US1RegisterVerifyTests(TestCase):
    """User Story 1: Register + Email Verification."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.register_url = reverse('accounts:register')
        self.verify_url = reverse('accounts:verify-email')
        self.resend_url = reverse('accounts:resend-verification')

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_register_creates_unverified_user(self, mock_task: MagicMock) -> None:
        """Registration creates user with is_verified=False."""
        mock_task.delay = MagicMock()

        resp = self.client.post(self.register_url, {
            'email': 'new@example.com',
            'password': 'TestPass123',
        }, format='json')

        assert resp.status_code == 201
        user = User.objects.get(email='new@example.com')
        assert user.is_verified is False

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_verify_with_flag_off_accepts_any_code(self) -> None:
        """When EMAIL_VERIFICATION_ENABLED=False, any code verifies."""
        User.objects.create_user(
            username='devuser',
            email='dev@example.com',
            password='TestPass123',
            is_verified=False,
        )
        resp = self.client.post(self.verify_url, {
            'email': 'dev@example.com',
            'code': '000000',
        }, format='json')

        assert resp.status_code == 200
        user = User.objects.get(email='dev@example.com')
        assert user.is_verified is True

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_verify_with_expired_code_fails(self, mock_task: MagicMock) -> None:
        """Expired verification code is rejected."""
        mock_task.delay = MagicMock()
        from datetime import datetime, timedelta

        from apps.accounts.services.token import TokenService

        user = User.objects.create_user(
            username='expired',
            email='expired@example.com',
            password='TestPass123',
            is_verified=False,
        )
        code = '123456'
        user.verification_code_hash = TokenService.hash_verification_code(code)
        user.verification_code_expiry = datetime.now(UTC) - timedelta(minutes=1)
        user.save()

        resp = self.client.post(self.verify_url, {
            'email': 'expired@example.com',
            'code': code,
        }, format='json')

        assert resp.status_code == 400

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_re_register_unverified_overrides(self, mock_task: MagicMock) -> None:
        """Re-registering with an unverified email overrides the old record."""
        mock_task.delay = MagicMock()
        from apps.accounts.services.token import TokenService

        user = User.objects.create_user(
            username='rereg',
            email='rereg@example.com',
            password='FirstPass1',
            is_verified=False,
        )
        old_pw_hash = user.password
        user.verification_code_hash = TokenService.hash_verification_code('111111')
        user.verification_code_expiry = TokenService.verification_expiry()
        user.save()

        resp = self.client.post(self.register_url, {
            'email': 'rereg@example.com',
            'password': 'SecondPass2',
        }, format='json')

        assert resp.status_code == 201
        user.refresh_from_db()
        assert user.password != old_pw_hash

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_re_register_verified_is_rejected(self) -> None:
        """Re-registering with a verified email is rejected."""
        User.objects.create_user(
            username='verified',
            email='verified@example.com',
            password='TestPass123',
            is_verified=True,
        )

        resp = self.client.post(self.register_url, {
            'email': 'verified@example.com',
            'password': 'NewPass456',
        }, format='json')

        assert resp.status_code in (400, 409)

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_verification_email_task')
    def test_resend_verification_for_unverified_user(self, mock_task: MagicMock) -> None:
        """Resend verification sends a new code for unverified user."""
        mock_task.delay = MagicMock()
        User.objects.create_user(
            username='resend',
            email='resend@example.com',
            password='TestPass123',
            is_verified=False,
        )

        resp = self.client.post(self.resend_url, {
            'email': 'resend@example.com',
        }, format='json')

        assert resp.status_code == 200
        mock_task.delay.assert_called_once()

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_resend_verification_for_unknown_email_is_silent(self) -> None:
        """Resend for unknown email returns generic success (no info leak)."""
        resp = self.client.post(self.resend_url, {
            'email': 'nonexistent@example.com',
        }, format='json')

        assert resp.status_code == 200


class US2LoginTests(TestCase):
    """User Story 2: Login with Email."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.login_url = reverse('accounts:login')

    def test_login_verified_user_returns_token_and_user(self) -> None:
        """Verified user logs in with email, gets token + user object."""
        User.objects.create_user(
            username='player1',
            email='player1@example.com',
            password='TestPass123',
            is_verified=True,
        )

        resp = self.client.post(self.login_url, {
            'email': 'player1@example.com',
            'password': 'TestPass123',
        }, format='json')

        assert resp.status_code == 200
        assert 'access' in resp.data
        assert 'refresh' in resp.data
        assert 'user' in resp.data
        assert resp.data['user']['email'] == 'player1@example.com'

    def test_login_wrong_password_returns_401_generic(self) -> None:
        """Wrong password returns generic 401 error."""
        User.objects.create_user(
            username='p2',
            email='player2@example.com',
            password='TestPass123',
            is_verified=True,
        )

        resp = self.client.post(self.login_url, {
            'email': 'player2@example.com',
            'password': 'WrongPass',
        }, format='json')

        assert resp.status_code == 401
        assert 'Invalid credentials' in resp.data.get('error', '')

    def test_login_unverified_account_returns_401(self) -> None:
        """Unverified account login fails with generic 401."""
        User.objects.create_user(
            username='unv',
            email='unv@example.com',
            password='TestPass123',
            is_verified=False,
        )

        resp = self.client.post(self.login_url, {
            'email': 'unv@example.com',
            'password': 'TestPass123',
        }, format='json')

        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self) -> None:
        """Unknown email returns same generic 401."""
        resp = self.client.post(self.login_url, {
            'email': 'nobody@example.com',
            'password': 'TestPass123',
        }, format='json')

        assert resp.status_code == 401


class US3PasswordResetTests(TestCase):
    """User Story 3: Password Reset."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.reset_request_url = reverse('accounts:password-reset-request')
        self.reset_confirm_url = reverse('accounts:password-reset-confirm')
        self.login_url = reverse('accounts:login')

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    @patch('apps.accounts.services.account.send_password_reset_email_task')
    def test_password_reset_flow(self, mock_task: MagicMock) -> None:
        """Full password reset flow: request -> confirm -> login with new password."""
        mock_task.delay = MagicMock()
        User.objects.create_user(
            username='reset1',
            email='reset1@example.com',
            password='OldPass123',
            is_verified=True,
        )

        # Request reset
        resp = self.client.post(self.reset_request_url, {
            'email': 'reset1@example.com',
        }, format='json')
        assert resp.status_code == 200

        # Get the token from the task call
        call_args = mock_task.delay.call_args
        reset_token = call_args[1]['reset_token']

        # Confirm reset
        resp = self.client.post(self.reset_confirm_url, {
            'email': 'reset1@example.com',
            'token': reset_token,
            'new_password': 'NewPass456',
        }, format='json')
        assert resp.status_code == 200

        # Login with new password
        resp = self.client.post(self.login_url, {
            'email': 'reset1@example.com',
            'password': 'NewPass456',
        }, format='json')
        assert resp.status_code == 200

    @override_settings(EMAIL_VERIFICATION_ENABLED=True)
    def test_password_reset_unknown_email_is_silent(self) -> None:
        """Reset request for unknown email returns generic success."""
        resp = self.client.post(self.reset_request_url, {
            'email': 'ghost@example.com',
        }, format='json')
        assert resp.status_code == 200

    def test_password_reset_invalid_token_fails(self) -> None:
        """Invalid reset token is rejected."""
        resp = self.client.post(self.reset_confirm_url, {
            'email': 'x@example.com',
            'token': 'invalid-token',
            'new_password': 'NewPass456',
        }, format='json')
        assert resp.status_code == 400


class US4ChangePasswordTests(TestCase):
    """User Story 4: Change Password."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.change_url = reverse('accounts:change-password')

    def test_change_password_authenticated(self) -> None:
        """Authenticated user changes password successfully."""
        user = User.objects.create_user(
            username='chpw',
            email='chpw@example.com',
            password='OldPass123',
            is_verified=True,
        )
        self.client.force_authenticate(user=user)

        resp = self.client.post(self.change_url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')

        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.check_password('NewPass456') is True

    def test_change_password_wrong_current(self) -> None:
        """Wrong current password returns 400."""
        user = User.objects.create_user(
            username='wrongpw',
            email='wrongpw@example.com',
            password='OldPass123',
            is_verified=True,
        )
        self.client.force_authenticate(user=user)

        resp = self.client.post(self.change_url, {
            'current_password': 'WrongOld',
            'new_password': 'NewPass456',
        }, format='json')

        assert resp.status_code == 400

    def test_change_password_unauthenticated(self) -> None:
        """Unauthenticated request returns 401."""
        resp = self.client.post(self.change_url, {
            'current_password': 'OldPass123',
            'new_password': 'NewPass456',
        }, format='json')

        assert resp.status_code == 401
