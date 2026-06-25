"""Pytest configuration for Django tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def api_client() -> Any:
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def auth_client(api_client: Any, django_user_model: type) -> Any:
    from rest_framework_simplejwt.tokens import RefreshToken

    user = django_user_model.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
    )
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    api_client.user = user
    return api_client


@pytest.fixture
def create_user(django_user_model: type) -> Any:
    def _create_user(username: str, email: str | None = None, password: str = 'testpass123') -> Any:
        email = email or f'{username}@example.com'
        return django_user_model.objects.create_user(
            username=username,
            email=email,
            password=password,
        )
    return _create_user
