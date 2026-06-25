"""Integration tests for account endpoints."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status

User = get_user_model()
pytestmark = pytest.mark.django_db


class TestRegisterView:
    def test_register_returns_tokens(self, api_client) -> None:
        response = api_client.post('/api/accounts/register/', {
            'username': 'viewtest',
            'email': 'viewtest@example.com',
            'password': 'SecurePass123!',
        })
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert 'access' in data
        assert 'refresh' in data
        assert data['username'] == 'viewtest'

    def test_register_duplicate_username(self, api_client, create_user) -> None:
        create_user(username='existing_user', password='testpass123')
        response = api_client.post('/api/accounts/register/', {
            'username': 'existing_user',
            'email': 'other@example.com',
            'password': 'SecurePass123!',
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.json()

    def test_register_missing_fields(self, api_client) -> None:
        response = api_client.post('/api/accounts/register/', {
            'username': 'incomplete',
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_access_blocked(self, api_client) -> None:
        response = api_client.get('/api/rooms/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLoginView:
    def test_login_returns_tokens(self, api_client, create_user) -> None:
        create_user(username='login_vt', password='testpass123')
        response = api_client.post('/api/accounts/login/', {
            'username': 'login_vt',
            'password': 'testpass123',
        })
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'access' in data
        assert 'refresh' in data

    def test_login_invalid_credentials(self, api_client) -> None:
        response = api_client.post('/api/accounts/login/', {
            'username': 'nobody',
            'password': 'wrong',
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLogoutView:
    def test_logout_blacklists_token(self, api_client, create_user) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken

        user = create_user(username='logout_vt', password='testpass123')
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        response = api_client.post('/api/accounts/logout/', {
            'refresh': str(refresh),
        })
        assert response.status_code == status.HTTP_200_OK


class TestTokenRefreshView:
    def test_refresh_returns_new_access(self, api_client, create_user) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken

        user = create_user(username='refresh_vt', password='testpass123')
        refresh = RefreshToken.for_user(user)

        response = api_client.post('/api/accounts/token/refresh/', {
            'refresh': str(refresh),
        })
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.json()
