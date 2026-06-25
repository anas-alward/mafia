"""Friend business logic."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models

from .models import FriendRequest

User = get_user_model()


class FriendService:
    def send_request(self, sender: User, username: str) -> FriendRequest:
        if sender.username == username:
            raise ValueError('Cannot send friend request to yourself.')

        try:
            recipient = User.objects.get(username=username)
        except User.DoesNotExist:
            raise ValueError('User not found.')

        # Check for existing request either direction
        existing = FriendRequest.objects.filter(
            models.Q(sender=sender, recipient=recipient)
            | models.Q(sender=recipient, recipient=sender),
        ).first()

        if existing and existing.status == FriendRequest.Status.ACCEPTED:
            raise ValueError('Already friends.')
        if existing and existing.status == FriendRequest.Status.PENDING:
            if existing.recipient == sender:
                # Other user already sent us a request — auto-accept both
                existing.status = FriendRequest.Status.ACCEPTED
                existing.save(update_fields=['status'])
                return existing
            raise ValueError('A pending request already exists.')

        return FriendRequest.objects.create(sender=sender, recipient=recipient)

    def accept_request(self, request_id: int, recipient: User) -> FriendRequest:
        req = FriendRequest.objects.get(id=request_id)
        if req.recipient != recipient:
            raise ValueError('Only the recipient can accept the request.')
        if req.status != FriendRequest.Status.PENDING:
            raise ValueError('Request is not pending.')
        req.status = FriendRequest.Status.ACCEPTED
        req.save(update_fields=['status'])
        return req

    def decline_request(self, request_id: int, recipient: User) -> FriendRequest:
        req = FriendRequest.objects.get(id=request_id)
        if req.recipient != recipient:
            raise ValueError('Only the recipient can decline the request.')
        if req.status != FriendRequest.Status.PENDING:
            raise ValueError('Request is not pending.')
        req.status = FriendRequest.Status.DECLINED
        req.save(update_fields=['status'])
        return req

    def remove_friend(self, user: User, friend_id: int) -> None:
        friend = User.objects.get(id=friend_id)
        FriendRequest.objects.filter(
            models.Q(sender=user, recipient=friend, status=FriendRequest.Status.ACCEPTED)
            | models.Q(sender=friend, recipient=user, status=FriendRequest.Status.ACCEPTED),
        ).delete()

    def get_friends(self, user: User) -> models.QuerySet[User]:
        sent = FriendRequest.objects.filter(
            sender=user, status=FriendRequest.Status.ACCEPTED,
        ).values_list('recipient_id', flat=True)
        received = FriendRequest.objects.filter(
            recipient=user, status=FriendRequest.Status.ACCEPTED,
        ).values_list('sender_id', flat=True)
        friend_ids = set(sent) | set(received)
        return User.objects.filter(id__in=friend_ids)

    def get_incoming_requests(self, user: User) -> models.QuerySet[FriendRequest]:
        return FriendRequest.objects.filter(
            recipient=user,
            status=FriendRequest.Status.PENDING,
        ).select_related('sender').order_by('-created_at')

    def get_outgoing_requests(self, user: User) -> models.QuerySet[FriendRequest]:
        return FriendRequest.objects.filter(
            sender=user,
            status=FriendRequest.Status.PENDING,
        ).select_related('recipient').order_by('-created_at')

    def search_users(self, query: str, searcher_username: str | None = None) -> models.QuerySet[User]:
        qs = User.objects.filter(username__icontains=query)
        if searcher_username:
            qs = qs.exclude(username=searcher_username)
        return qs.order_by('username')[:20]
