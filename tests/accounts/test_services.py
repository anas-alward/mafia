"""Unit tests for AccountService."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestAccountServiceRegister:
    def test_register_creates_user(self) -> None:
        from apps.accounts.services import AccountService

        svc = AccountService()
        result = svc.register(
            username='newuser',
            email='new@example.com',
            password='SecurePass123!',
        )
        assert result['user'].username == 'newuser'
        assert result['user'].email == 'new@example.com'
        assert result['user'].check_password('SecurePass123!')

    def test_register_returns_tokens(self) -> None:
        from apps.accounts.services import AccountService

        svc = AccountService()
        result = svc.register(
            username='tokenuser',
            email='token@example.com',
            password='SecurePass123!',
        )
        assert 'access' in result
        assert 'refresh' in result
        assert result['user'].username == 'tokenuser'

    def test_register_duplicate_username_raises(self) -> None:
        from apps.accounts.services import AccountService

        svc = AccountService()
        svc.register(username='dupe', email='dupe1@example.com', password='SecurePass123!')

        with pytest.raises(ValueError, match='already taken'):
            svc.register(username='dupe', email='dupe2@example.com', password='SecurePass123!')

    def test_register_duplicate_email_raises(self, create_user) -> None:
        from apps.accounts.services import AccountService

        create_user(username='existing', email='shared@example.com')
        svc = AccountService()

        with pytest.raises(ValueError, match='already taken'):
            svc.register(username='newbie', email='shared@example.com', password='SecurePass123!')


class TestAccountServiceLogin:
    def test_login_valid_credentials(self, create_user) -> None:
        from apps.accounts.services import AccountService

        create_user(username='login_test', password='testpass123')
        svc = AccountService()
        result = svc.login(username='login_test', password='testpass123')
        assert 'access' in result
        assert 'refresh' in result

    def test_login_invalid_password(self, create_user) -> None:
        from apps.accounts.services import AccountService

        create_user(username='login_test2', password='testpass123')
        svc = AccountService()

        with pytest.raises(ValueError, match='Invalid credentials'):
            svc.login(username='login_test2', password='wrongpass')

    def test_login_nonexistent_user(self) -> None:
        from apps.accounts.services import AccountService

        svc = AccountService()
        with pytest.raises(ValueError, match='Invalid credentials'):
            svc.login(username='nobody', password='whatever')


class TestAccountServiceLogout:
    def test_logout_blacklists_refresh_token(self, create_user) -> None:
        from apps.accounts.services import AccountService

        create_user(username='logout_test', password='testpass123')
        svc = AccountService()
        result = svc.login(username='logout_test', password='testpass123')
        svc.logout(result['refresh'])
