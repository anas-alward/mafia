"""Room business logic."""

from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from apps.accounts.models import User

from .models import Room, RoomJoinRequest, RoomMember
from .realtime import  realtime


class RoomService:
    def create_room(
        self,
        host: User,
        name: str,
        max_members: int = 8,
        scheduled_at: str | None = None,
        role_configuration: dict | None = None,
    ) -> Room:
        room = Room.objects.create(
            host=host,
            created_by=host,
            name=name,
            max_members=max_members,
            scheduled_at=scheduled_at,
            role_configuration=role_configuration or {},
        )
        meeting_id = realtime.create_meeting(room.name)
        room.meeting_id = meeting_id
        room.save(update_fields=['meeting_id'])

        RoomMember.objects.create(
            user=host,
            room=room,
            added_by=RoomMember.AddedBy.HOST_DIRECT,
        )
        return room

    def get_hosted_rooms(self, host: User) -> models.QuerySet[Room]:
        return Room.objects.filter(host=host).order_by('-created_at')

    def get_room_by_code(self, code: str) -> Room:
        try:
            return Room.objects.get(code=code)
        except Room.DoesNotExist:
            raise ValueError('Room not found.')

    def finish_room(self, room: Room, user: User) -> Room:
        if room.host != user:
            raise ValueError('Only the host can finish the room.')
        if room.status == Room.Status.FINISHED:
            raise ValueError('Room is already finished.')
        room.status = Room.Status.FINISHED
        room.save(update_fields=['status'])
        return room

    def add_friend_to_room(self, room: Room, host: User, friend: User) -> Room:
        if not room.is_host(host):
            raise ValueError('Only the host can add members.')
        if not room.is_waiting():
            raise ValueError('Game already started.')
        if RoomMember.objects.filter(user=friend, room=room).exists():
            raise ValueError('User is already a member.')

        with transaction.atomic():
            room = Room.objects.select_for_update().get(pk=room.pk)
            if room.is_full():
                raise ValueError('Room is full.')
            RoomMember.objects.create(
                user=friend,
                room=room,
                added_by=RoomMember.AddedBy.HOST_DIRECT,
            )
            self._expire_pending_requests(room)
        return room

    def request_to_join(self, room: Room, user: User) -> RoomJoinRequest:
        if not room.is_waiting():
            raise ValueError('Room is no longer available.')
        if RoomMember.objects.filter(user=user, room=room).exists():
            raise ValueError('Already a member of this room.')
        if room.is_full():
            raise ValueError('Room is full.')
        if RoomJoinRequest.objects.filter(
            user=user,
            room=room,
            status=RoomJoinRequest.Status.PENDING,
        ).exists():
            raise ValueError('A pending request already exists.')

        return RoomJoinRequest.objects.create(user=user, room=room)

    def accept_join_request(self, request_id: int, host: User) -> Room:
        with transaction.atomic():
            join_req = (
                RoomJoinRequest.objects.select_related('room')
                .select_for_update()
                .get(id=request_id)
            )
            room = Room.objects.select_for_update().get(pk=join_req.room.pk)

            if not room.is_host(host):
                raise ValueError('Only the host can accept join requests.')
            if join_req.status != RoomJoinRequest.Status.PENDING:
                raise ValueError('Request is not pending.')
            if room.is_full():
                join_req.status = RoomJoinRequest.Status.EXPIRED
                join_req.resolved_at = timezone.now()
                join_req.save(update_fields=['status', 'resolved_at'])
                raise ValueError('Room is full.')

            join_req.status = RoomJoinRequest.Status.ACCEPTED
            join_req.resolved_at = timezone.now()
            join_req.save(update_fields=['status', 'resolved_at'])

            RoomMember.objects.create(
                user=join_req.user,
                room=room,
                added_by=RoomMember.AddedBy.LINK_REQUEST,
            )
            self._expire_pending_requests(room)
        return room

    def reject_join_request(self, request_id: int, host: User) -> None:
        join_req = RoomJoinRequest.objects.get(id=request_id)
        if join_req.room.host != host:
            raise ValueError('Only the host can reject join requests.')
        if join_req.status != RoomJoinRequest.Status.PENDING:
            raise ValueError('Request is not pending.')

        join_req.status = RoomJoinRequest.Status.REJECTED
        join_req.resolved_at = timezone.now()
        join_req.save(update_fields=['status', 'resolved_at'])

    def get_join_requests(self, room: Room) -> models.QuerySet[RoomJoinRequest]:
        return RoomJoinRequest.objects.filter(
            room=room,
            status=RoomJoinRequest.Status.PENDING,
        ).order_by('requested_at')

    def get_members(self, room: Room) -> models.QuerySet[RoomMember]:
        return RoomMember.objects.filter(room=room).order_by('joined_at')

    def remove_member(self, room: Room, host: User, user_to_remove: User) -> Room:
        if not room.is_host(host):
            raise ValueError('Only the host can remove members.')
        if user_to_remove == host:
            raise ValueError('Cannot remove yourself as host.')
        try:
            membership = RoomMember.objects.get(user=user_to_remove, room=room)
            membership.delete()
        except RoomMember.DoesNotExist:
            raise ValueError('User is not a member of this room.')
        return room

    def _expire_pending_requests(self, room: Room) -> None:
        """Auto-expire all pending join requests when room reaches max members."""
        if not room.is_full():
            return
        RoomJoinRequest.objects.filter(
            room=room,
            status=RoomJoinRequest.Status.PENDING,
        ).update(
            status=RoomJoinRequest.Status.EXPIRED,
            resolved_at=timezone.now(),
        )
