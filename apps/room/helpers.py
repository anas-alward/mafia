"""Room helper utilities."""

from __future__ import annotations


def meeting_id_for(code: str) -> str:
    """Return the LiveKit room name for a room code.

    LiveKit creates the room automatically when the first
    participant connects, so no server-side call is needed.
    """
    return f'mafia-room-{code}'
