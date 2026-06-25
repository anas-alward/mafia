"""Integration tests for friend endpoints."""

from __future__ import annotations

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


class TestSendFriendRequestView:
    def test_send_friend_request(self, auth_client, create_user) -> None:
        create_user(username='target_user')
        response = auth_client.post('/api/friends/requests/send/', {
            'username': 'target_user',
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()['status'] == 'pending'

    def test_cannot_send_to_self(self, auth_client) -> None:
        response = auth_client.post('/api/friends/requests/send/', {
            'username': 'testuser',
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestFriendListView:
    def test_list_friends(self, auth_client, create_user) -> None:
        from apps.friends.models import FriendRequest

        friend = create_user(username='my_friend')
        FriendRequest.objects.create(sender=auth_client.user, recipient=friend, status='accepted')

        response = auth_client.get('/api/friends/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        friends = data.get('results', data.get('friends', []))
        assert len(friends) == 1


class TestSearchView:
    def test_search_users(self, auth_client, create_user) -> None:
        create_user(username='searchable')
        response = auth_client.get('/api/friends/search/?q=searchable')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()['users']) == 1


class TestAcceptRequestView:
    def test_accept_request(self, auth_client, create_user) -> None:
        from apps.friends.models import FriendRequest

        friend = create_user(username='accept_me')
        req = FriendRequest.objects.create(sender=friend, recipient=auth_client.user)

        response = auth_client.post(f'/api/friends/requests/{req.id}/accept/')
        assert response.status_code == status.HTTP_200_OK
