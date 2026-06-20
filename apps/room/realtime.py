import os

from cloudflare import Cloudflare


def _get_client():
    """Build a Cloudflare client from environment variables."""
    return Cloudflare(
        api_token=os.environ["CLOUDFLARE_API_TOKEN"],
    )


def _account_id():
    return os.environ["CLOUDFLARE_ACCOUNT_ID"]


def _app_id():
    return os.environ["CLOUDFLARE_APP_ID"]


def get_or_create_app(name: str = "mafia"):
    """Fetch the first matching app or create one if none exists."""
    client = _get_client()
    account_id = _account_id()

    existing = client.realtime_kit.apps.get(
        account_id=account_id,
        search=name,
    )
    if existing.data:
        return existing.data[0].id

    result = client.realtime_kit.apps.post(
        account_id=account_id,
        name=name,
    )
    return result.data.app.id


def create_meeting(title: str) -> str:
    """Create a Realtime Kit meeting and return its ID."""
    client = _get_client()
    result = client.realtime_kit.meetings.create(
        account_id=_account_id(),
        app_id=_app_id(),
        title=title,
    )
    return result.data.id


def add_participant(
    meeting_id: str,
    participant_id: str,
    name: str,
    preset_name: str = "group_call_host",
) -> dict:
    """Register a participant and return their credentials (id, token)."""
    client = _get_client()
    result = client.realtime_kit.meetings.add_participant(
        account_id=_account_id(),
        app_id=_app_id(),
        meeting_id=meeting_id,
        custom_participant_id=participant_id,
        preset_name=preset_name,
        name=name,
    )
    return {
        "participant_id": result.data.id,
        "token": result.data.token,
    }


def refresh_token(meeting_id: str, participant_id: str) -> str:
    """Regenerate a participant's auth token."""
    client = _get_client()
    result = client.realtime_kit.meetings.refresh_participant_token(
        account_id=_account_id(),
        app_id=_app_id(),
        meeting_id=meeting_id,
        participant_id=participant_id,
    )
    return result.data.token


def remove_participant(meeting_id: str, participant_id: str) -> None:
    """Remove a participant from a meeting."""
    client = _get_client()
    client.realtime_kit.meetings.delete_meeting_participant(
        account_id=_account_id(),
        app_id=_app_id(),
        meeting_id=meeting_id,
        participant_id=participant_id,
    )


def end_meeting(meeting_id: str) -> None:
    """Set a meeting status to INACTIVE."""
    client = _get_client()
    client.realtime_kit.meetings.update_meeting_by_id(
        meeting_id=meeting_id,
        account_id=_account_id(),
        app_id=_app_id(),
        status="INACTIVE",
    )
