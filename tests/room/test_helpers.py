"""Unit tests for room helpers."""

from __future__ import annotations

from apps.room.helpers import meeting_id_for


class TestMeetingIdFor:
    def test_returns_deterministic_room_name(self) -> None:
        assert meeting_id_for('abc123') == 'mafia-room-abc123'
        assert meeting_id_for('abc123') == 'mafia-room-abc123'
