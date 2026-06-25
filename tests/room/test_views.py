"""Integration tests for room endpoints."""

from __future__ import annotations

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestCreateRoomView:
    def test_create_room_returns_room_data(self, auth_client) -> None:
        response = auth_client.post('/api/rooms/create/', {
            'name': 'My Room',
            'max_members': 10,
        })
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert 'room' in data
        assert data['room']['name'] == 'My Room'
        assert data['room']['host'] == 'testuser'
        assert len(data['room']['code']) == 6

    def test_create_room_requires_auth(self, api_client) -> None:
        response = api_client.post('/api/rooms/create/', {
            'name': 'Unauthorized',
            'max_members': 8,
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestHostedRoomListView:
    def test_list_hosted_rooms(self, auth_client, create_user) -> None:
        from apps.room.models import Room

        other = create_user(username='other_user')
        room1 = Room.objects.create(host=auth_client.user, created_by=auth_client.user, name='R1')
        room2 = Room.objects.create(host=auth_client.user, created_by=auth_client.user, name='R2')
        Room.objects.create(host=other, created_by=other, name='R3')

        response = auth_client.get('/api/rooms/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['count'] == 2


class TestFinishRoomView:
    def test_finish_room_as_host(self, auth_client) -> None:
        from apps.room.models import Room

        room = Room.objects.create(host=auth_client.user, created_by=auth_client.user, name='Finish Me')
        response = auth_client.post(f'/api/rooms/{room.code}/finish/')
        assert response.status_code == status.HTTP_200_OK
        room.refresh_from_db()
        assert room.status == Room.Status.FINISHED

    def test_finish_room_not_host(self, auth_client, create_user) -> None:
        from apps.room.models import Room

        other = create_user(username='other_host')
        room = Room.objects.create(host=other, created_by=other, name='Not Mine')

        response = auth_client.post(f'/api/rooms/{room.code}/finish/')
        assert response.status_code == status.HTTP_403_FORBIDDEN
