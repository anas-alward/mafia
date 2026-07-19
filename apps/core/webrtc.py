from cloudflare import Cloudflare
from django.conf import settings


class WebRTCClient:
    """A wrapper for Cloudflare Realtime Kit operations."""

    def __init__(self):
        self.client = Cloudflare(api_token=settings.CLOUDFLARE_API_TOKEN)
        self.account_id = settings.CLOUDFLARE_ACCOUNT_ID
        self.app_id = settings.CLOUDFLARE_APP_ID

    def get_or_create_app(self, name: str = 'mafia') -> str:
        """Fetch the first matching app or create one if none exists."""
        existing = self.client.realtime_kit.apps.get(
            account_id=self.account_id,
            search=name,
        )
        if existing.data:
            return existing.data[0].id

        result = self.client.realtime_kit.apps.post(
            account_id=self.account_id,
            name=name,
        )
        return result.data.app.id

    def create_meeting(self, title: str) -> str:
        """Create a Realtime Kit meeting and return its ID."""
        result = self.client.realtime_kit.meetings.create(
            account_id=self.account_id,
            app_id=self.app_id,
            title=title,
        )
        return result.data.id

    def add_participant(
        self,
        meeting_id: str,
        participant_id: str,
        name: str,
        preset_name: str = 'group_call_host',
    ) -> dict:
        """Register a participant and return their credentials (id, token)."""
        result = self.client.realtime_kit.meetings.add_participant(
            account_id=self.account_id,
            app_id=self.app_id,
            meeting_id=meeting_id,
            custom_participant_id=participant_id,
            preset_name=preset_name,
            name=name,
        )
        return {
            'participant_id': result.data.custom_participant_id,
            'token': result.data.token,
        }

    def refresh_token(self, meeting_id: str, participant_id: str) -> str:
        """Regenerate a participant's auth token."""
        result = self.client.realtime_kit.meetings.refresh_participant_token(
            account_id=self.account_id,
            app_id=self.app_id,
            meeting_id=meeting_id,
            participant_id=participant_id,
        )
        return result.data.token

    def remove_participant(self, meeting_id: str, participant_id: str) -> None:
        """Remove a participant from a meeting."""
        self.client.realtime_kit.meetings.delete_meeting_participant(
            account_id=self.account_id,
            app_id=self.app_id,
            meeting_id=meeting_id,
            participant_id=participant_id,
        )

    def end_meeting(self, meeting_id: str) -> None:
        """Set a meeting status to INACTIVE."""
        self.client.realtime_kit.meetings.update_meeting_by_id(
            meeting_id=meeting_id,
            account_id=self.account_id,
            app_id=self.app_id,
            status='INACTIVE',
        )

webrtc_client = WebRTCClient()

