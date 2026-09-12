# mypy: disable-error-code="attr-defined"
"""Throttle tests for auth endpoints — exceeding a scope rate returns 429."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

User = get_user_model()

# NOTE: DRF binds THROTTLE_RATES at import time, so override_settings cannot
# change enforced rates — patch the class attribute instead. Each test uses
# its own IP and the cache is cleared on both sides for full isolation.
_TINY_RATES = {
    'anon': '10000/min',
    'user': '10000/min',
    'login': '2/min',
    'register': '2/min',
    'verify': '2/min',
    'resend-verification': '2/min',
    'password-reset-request': '2/min',
    'password-reset-confirm': '2/min',
    'token-refresh': '2/min',
}

_patch_rates = patch.object(SimpleRateThrottle, 'THROTTLE_RATES', _TINY_RATES)


@_patch_rates
class AuthThrottleTests(TestCase):
    """Scoped throttles kick in after the rate is exceeded."""

    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()

    def tearDown(self) -> None:
        cache.clear()

    def _post(self, url: str, payload: dict, ip: str):
        return self.client.post(url, payload, format='json', REMOTE_ADDR=ip)

    def test_login_throttled_after_rate_exceeded(self) -> None:
        """Repeated logins from one IP are throttled with 429."""
        User.objects.create_user(
            username='throttle1',
            email='throttle1@example.com',
            password='TestPass123',
            is_verified=True,
        )
        url = reverse('accounts:login')
        payload = {'email': 'throttle1@example.com', 'password': 'WrongPass'}

        assert self._post(url, payload, '10.10.0.1').status_code == 401
        assert self._post(url, payload, '10.10.0.1').status_code == 401
        resp = self._post(url, payload, '10.10.0.1')
        assert resp.status_code == 429

    def test_register_throttled_after_rate_exceeded(self) -> None:
        """Repeated registrations from one IP are throttled with 429."""
        url = reverse('accounts:register')

        resp1 = self._post(url, {'email': 't1@example.com', 'password': 'TestPass123'}, '10.10.0.2')
        resp2 = self._post(url, {'email': 't2@example.com', 'password': 'TestPass123'}, '10.10.0.2')
        resp3 = self._post(url, {'email': 't3@example.com', 'password': 'TestPass123'}, '10.10.0.2')
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp3.status_code == 429

    def test_password_reset_request_throttled(self) -> None:
        """Repeated reset requests from one IP are throttled with 429."""
        User.objects.create_user(
            username='throttle2',
            email='throttle2@example.com',
            password='TestPass123',
            is_verified=True,
        )
        url = reverse('accounts:password-reset-request')
        payload = {'email': 'throttle2@example.com'}

        assert self._post(url, payload, '10.10.0.3').status_code == 200
        assert self._post(url, payload, '10.10.0.3').status_code == 200
        resp = self._post(url, payload, '10.10.0.3')
        assert resp.status_code == 429
