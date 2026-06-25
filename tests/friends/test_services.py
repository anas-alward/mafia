"""Unit tests for FriendService."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestFriendServiceSendRequest:
    def test_send_request_creates_pending_request(self, create_user) -> None:
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()

        result = svc.send_request(sender=alice, username='bob')
        assert result.status == 'pending'
        assert result.sender == alice
        assert result.recipient == bob

    def test_cannot_send_to_self(self, create_user) -> None:
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        svc = FriendService()

        with pytest.raises(ValueError, match='yourself'):
            svc.send_request(sender=alice, username='alice')

    def test_cannot_send_duplicate(self, create_user) -> None:
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()
        svc.send_request(sender=alice, username='bob')

        with pytest.raises(ValueError, match='already'):
            svc.send_request(sender=alice, username='bob')


class TestFriendServiceMutual:
    def test_mutual_requests_auto_accept(self, create_user) -> None:
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()

        svc.send_request(sender=alice, username='bob')
        result = svc.send_request(sender=bob, username='alice')

        assert result.status == 'accepted'


class TestFriendServiceAcceptReject:
    def test_accept_request(self, create_user) -> None:
        from apps.friends.models import FriendRequest
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()
        req = svc.send_request(sender=alice, username='bob')

        svc.accept_request(request_id=req.id, recipient=bob)
        req.refresh_from_db()
        assert req.status == FriendRequest.Status.ACCEPTED

    def test_decline_request(self, create_user) -> None:
        from apps.friends.models import FriendRequest
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()
        req = svc.send_request(sender=alice, username='bob')

        svc.decline_request(request_id=req.id, recipient=bob)
        req.refresh_from_db()
        assert req.status == FriendRequest.Status.DECLINED


class TestFriendServiceRemove:
    def test_remove_friend(self, create_user) -> None:
        from apps.friends.models import FriendRequest
        from apps.friends.services import FriendService

        alice = create_user(username='alice')
        bob = create_user(username='bob')
        svc = FriendService()
        req = svc.send_request(sender=alice, username='bob')
        svc.accept_request(request_id=req.id, recipient=bob)

        svc.remove_friend(user=alice, friend_id=bob.id)
        assert not FriendRequest.objects.filter(sender=alice, recipient=bob, status='accepted').exists()
        assert not FriendRequest.objects.filter(sender=bob, recipient=alice, status='accepted').exists()


class TestFriendServiceSearch:
    def test_search_users_partial_match(self, create_user) -> None:
        from apps.friends.services import FriendService

        create_user(username='alice')
        create_user(username='alex')
        create_user(username='bob')
        svc = FriendService()

        results = svc.search_users(query='al', searcher_username=None)
        assert len(list(results)) == 2

    def test_search_excludes_self(self, create_user) -> None:
        from apps.friends.services import FriendService

        create_user(username='search_me')
        svc = FriendService()

        results = svc.search_users(query='search', searcher_username='search_me')
        assert len(list(results)) == 0
