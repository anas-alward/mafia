"""Tests for room joining logic in RoomService."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestAddFriendToRoom:
    def test_host_adds_friend(self, create_user) -> None:
        from apps.room.models import RoomMember
        from apps.room.services import RoomService

        host = create_user(username='host')
        friend = create_user(username='friend')
        svc = RoomService()
        room = svc.create_room(host=host, name='Test', max_members=8)

        svc.add_friend_to_room(room=room, host=host, friend=friend)
        assert RoomMember.objects.filter(user=friend, room=room).exists()

    def test_non_host_cannot_add(self, create_user) -> None:
        from apps.room.services import RoomService

        host = create_user(username='host')
        friend = create_user(username='friend')
        other = create_user(username='other')
        svc = RoomService()
        room = svc.create_room(host=host, name='Test', max_members=8)

        with pytest.raises(ValueError, match='Only the host'):
            svc.add_friend_to_room(room=room, host=other, friend=friend)


class TestRequestToJoin:
    def test_request_creates_pending_request(self, create_user) -> None:
        from apps.room.services import RoomService

        host = create_user(username='host')
        joiner = create_user(username='joiner')
        svc = RoomService()
        room = svc.create_room(host=host, name='Test', max_members=8)

        req = svc.request_to_join(room=room, user=joiner)
        assert req.status == 'pending'

    def test_full_room_rejects(self, create_user) -> None:
        from apps.room.services import RoomService

        host = create_user(username='host')
        joiner = create_user(username='joiner')
        svc = RoomService()
        room = svc.create_room(host=host, name='Test', max_members=1)

        with pytest.raises(ValueError, match='full'):
            svc.request_to_join(room=room, user=joiner)
