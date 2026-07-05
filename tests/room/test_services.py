"""Unit tests for RoomService."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestRoomServiceCreateRoom:
    def test_create_room_makes_user_host(self, create_user) -> None:
        from apps.room.models import Room
        from apps.room.services import RoomService

        user = create_user(username='host_user')
        svc = RoomService()
        room = svc.create_room(
            host=user,
            name='Test Room',
            max_members=10,
        )
        assert room.host == user
        assert room.name == 'Test Room'
        assert room.max_members == 10
        assert room.status == Room.Status.WAITING
        assert len(room.code) == 6

    def test_create_room_generates_unique_code(self, create_user) -> None:
        from apps.room.services import RoomService

        user = create_user(username='code_test')
        svc = RoomService()
        room1 = svc.create_room(host=user, name='Room 1', max_members=8)
        room2 = svc.create_room(host=user, name='Room 2', max_members=8)
        assert room1.code != room2.code

    def test_create_room_adds_host_as_member(self, create_user) -> None:
        from apps.room.models import RoomMember
        from apps.room.services import RoomService

        user = create_user(username='host_member')
        svc = RoomService()
        room = svc.create_room(host=user, name='Test', max_members=8)

        assert RoomMember.objects.filter(user=user, room=room).exists()


class TestRoomServiceHostedRooms:
    def test_get_hosted_rooms_filters_by_host(self, create_user) -> None:
        from apps.room.services import RoomService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = RoomService()

        svc.create_room(host=alice, name='Room A')
        svc.create_room(host=alice, name='Room B')
        svc.create_room(host=bob, name='Room C')

        alice_rooms = svc.get_hosted_rooms(host=alice)
        assert alice_rooms.count() == 2

        bob_rooms = svc.get_hosted_rooms(host=bob)
        assert bob_rooms.count() == 1



