"""LiveKit server integration.

The backend never talks to the LiveKit media server over the network:
rooms are created implicitly on first participant join, and access is
granted by minting JWT access tokens locally. The public surface is
kept in meeting terms (create_meeting / add_participant) so callers
stay independent of the media-server implementation.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from livekit import api


class LiveKitClient:
    """Mints LiveKit room names and participant access tokens."""

    TOKEN_TTL = timedelta(hours=6)

    def create_meeting(self, code: str) -> str:
        """Return the LiveKit room name for a room code.

        LiveKit creates the room automatically when the first
        participant connects, so no server-side call is needed.
        """
        return f'mafia-room-{code}'

    def add_participant(
        self,
        meeting_id: str,
        participant_id: str,
        name: str,
    ) -> dict:
        """Mint an access token for a participant and return their credentials."""
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(participant_id)
            .with_name(name)
            .with_ttl(self.TOKEN_TTL)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=meeting_id,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
        )
        return {
            'participant_id': participant_id,
            'token': token.to_jwt(),
            'server_url': settings.LIVEKIT_URL,
        }


livekit_client = LiveKitClient()
