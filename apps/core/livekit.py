"""LiveKit server integration.

The backend never talks to the LiveKit media server over the network:
rooms are created implicitly on first participant join, and access is
granted by minting JWT access tokens locally. The public surface is
kept in meeting terms (create_meeting / add_participant) so callers
stay independent of the media-server implementation.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from livekit import api
from livekit.protocol import models

logger = logging.getLogger(__name__)


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
        can_publish_sources: list[str] | None = None,
    ) -> dict:
        """Mint an access token for a participant and return their credentials.

        `can_publish_sources` restricts which tracks the participant may
        publish (e.g. `['CAMERA']` for silenced players — voice blocked,
        camera allowed). `None` leaves publishing unrestricted.
        """
        grants = api.VideoGrants(
            room_join=True,
            room=meeting_id,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )
        if can_publish_sources:
            grants.can_publish_sources = can_publish_sources
        token = (
            api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
            .with_identity(participant_id)
            .with_name(name)
            .with_ttl(self.TOKEN_TTL)
            .with_grants(grants)
        )
        return {
            'participant_id': participant_id,
            'token': token.to_jwt(),
            'server_url': settings.LIVEKIT_URL,
        }

    # -------------------------
    # SERVER-SIDE ENFORCEMENT
    # -------------------------

    async def set_voice_allowed(
        self,
        meeting_id: str,
        participant_id: str,
        *,
        allowed: bool,
    ) -> None:
        """Enforce a participant's microphone state via the RoomService API.

        When `allowed=False` their live microphone track is muted and their
        publish permission is restricted to the camera, so they cannot unmute
        themselves. When `allowed=True` the restriction is lifted (their mic
        stays muted until they unmute locally).
        """
        lk = api.LiveKitAPI(
            settings.LIVEKIT_SERVER_URL,
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )
        try:
            if not allowed:
                await self._mute_microphone(lk, meeting_id, participant_id)
            permission = models.ParticipantPermission(
                can_subscribe=True,
                can_publish=True,
                can_publish_data=True,
                **(
                    {'can_publish_sources': [models.TrackSource.CAMERA]}
                    if not allowed
                    else {}
                ),
            )
            await lk.room.update_participant(
                api.UpdateParticipantRequest(
                    room=meeting_id,
                    identity=participant_id,
                    permission=permission,
                )
            )
        except Exception:
            logger.warning(
                'LiveKit voice enforcement failed for %s in %s',
                participant_id,
                meeting_id,
                exc_info=True,
            )
        finally:
            await lk.aclose()

    async def _mute_microphone(self, lk: api.LiveKitAPI, room: str, identity: str) -> None:
        participants = await lk.room.list_participants(
            api.ListParticipantsRequest(room=room)
        )
        for p in participants.participants:
            if p.identity != identity:
                continue
            for track in p.tracks:
                if (
                    track.source == models.TrackSource.MICROPHONE
                    and not track.muted
                ):
                    await lk.room.mute_published_track(
                        api.MuteRoomTrackRequest(
                            room=room,
                            identity=identity,
                            track_sid=track.sid,
                            muted=True,
                        )
                    )
                    return


livekit_client = LiveKitClient()
