"""Unit tests for the LiveKit client."""

from __future__ import annotations

import jwt
import pytest

from apps.core.livekit import LiveKitClient

pytestmark = pytest.mark.django_db


class TestLiveKitClient:
    def test_add_participant_returns_credentials(self) -> None:
        client = LiveKitClient()

        credentials = client.add_participant(
            meeting_id='mafia-room-abc123',
            participant_id='42',
            name='alice',
        )

        assert credentials['participant_id'] == '42'
        assert credentials['server_url'] == 'ws://localhost:7880'

    def test_add_participant_token_grants_room_access(self, settings) -> None:
        settings.LIVEKIT_API_KEY = 'test-key'
        settings.LIVEKIT_API_SECRET = 'test-secret'
        client = LiveKitClient()

        credentials = client.add_participant(
            meeting_id='mafia-room-abc123',
            participant_id='42',
            name='alice',
        )

        payload = jwt.decode(
            credentials['token'],
            'test-secret',
            algorithms=['HS256'],
            issuer='test-key',
        )
        assert payload['sub'] == '42'
        assert payload['name'] == 'alice'
        assert payload['video']['roomJoin'] is True
        assert payload['video']['room'] == 'mafia-room-abc123'
        assert payload['video']['canPublish'] is True
        assert payload['video']['canSubscribe'] is True
