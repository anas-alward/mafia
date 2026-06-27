"""Room REST endpoints."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from utils.errors import api_error
from utils.pagination import StandardPagination

from .models import Room, RoomJoinRequest, RoomMember
from .realtime import realtime
from .serializers import CreateRoomSerializer, JoinRequestSerializer, RoomSerializer
from .services import RoomService

User = get_user_model()


class RoomDetailView(generics.RetrieveAPIView):
    lookup_field = 'code'
    lookup_url_kwarg = 'code'
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self) ->耳目 None:
        code = self.kwargs.get(self.lookup_url_kwarg)
        try:
            room = Room.objects.get(code=code)
        except Room.DoesNotExist:
            raise ValueError('Room not found.')

        is_member = room.members.filter(user=self.request.user).exists()
        if not is_member and room.host != self.request.user:
            raise PermissionError('You are not a member of this room.')

        return room

    def handle_exception(self, exc: Any) -> Response:
        if isinstance(exc, ValueError):
            return api_error(str(exc), status=status.HTTP_404_NOT_FOUND)
        if isinstance(exc, PermissionError):
            return api_error(str(exc), status=status.HTTP_403_FORBIDDEN)
        return super().handle_exception(exc)


class CreateRoomView(generics.CreateAPIView):
    queryset = Room.objects.all()
    serializer_class = CreateRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            from utils.errors import api_validation_error

            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        room = RoomService().create_room(
            host=request.user,
            **serializer.validated_data,
        )

        return Response(
            {
                'room': RoomSerializer(room).data,
            },
            status=status.HTTP_201_CREATED,
        )


class JoinRoomView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            join_req = svc.request_to_join(room=room, user=request.user)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'request_id': join_req.id,
                'status': join_req.status,
            },
            status=status.HTTP_200_OK,
        )


class HostedRoomListView(generics.ListAPIView):
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self) -> Any:
        return RoomService().get_hosted_rooms(host=self.request.user)


class AddMemberView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        user_id = request.data.get('user_id')
        if not user_id:
            return api_error('user_id is required.', status=status.HTTP_400_BAD_REQUEST)

        try:
            friend = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return api_error('User not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            svc.add_friend_to_room(room=room, host=request.user, friend=friend)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'room': RoomSerializer(room).data,
                'user_id': friend.id,
                'username': friend.username,
            }
        )


class MemberListView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        is_member = room.members.filter(user=request.user).exists()
        if not is_member and room.host != request.user:
            return api_error(
                'You are not a member of this room.',
                status=status.HTTP_403_FORBIDDEN,
            )

        members = list(svc.get_members(room))
        return Response(
            {
                'host': {'id': room.host_id, 'username': room.host.username},
                'member_count': len(members),
                'max_members': room.max_members,
                'members': [
                    {
                        'id': m.user_id,
                        'username': m.user.username,
                        'joined_at': m.joined_at,
                    }
                    for m in members
                ],
            }
        )


class RemoveMemberView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        user_id = request.data.get('user_id')
        if not user_id:
            return api_error('user_id is required.', status=status.HTTP_400_BAD_REQUEST)

        try:
            user_to_remove = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return api_error('User not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            svc.remove_member(
                room=room, host=request.user, user_to_remove=user_to_remove
            )
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'room': RoomSerializer(room).data,
                'removed_user_id': user_to_remove.id,
                'removed_username': user_to_remove.username,
            }
        )


class FinishRoomView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            svc.finish_room(room=room, user=request.user)
        except ValueError as e:
            status_code = status.HTTP_400_BAD_REQUEST
            if 'Only the host' in str(e):
                status_code = status.HTTP_403_FORBIDDEN
            return api_error(str(e), status=status_code)

        return Response({'room': RoomSerializer(room).data})


class JoinRequestListView(generics.GenericAPIView):
    queryset = Room.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request: Any, code: str) -> Response:
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        if room.host != request.user:
            return api_error(
                'Only the host can view join requests.',
                status=status.HTTP_403_FORBIDDEN,
            )

        requests = svc.get_join_requests(room)
        page = self.paginate_queryset(requests)
        if page is not None:
            return self.get_paginated_response(
                JoinRequestSerializer(page, many=True).data
            )
        return Response(
            {
                'requests': JoinRequestSerializer(requests, many=True).data,
            }
        )


class AcceptJoinRequestView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str, request_id: int) -> Response:
        svc = RoomService()
        try:
            svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            room = svc.accept_join_request(request_id=request_id, host=request.user)
        except RoomJoinRequest.DoesNotExist:
            return api_error(
                'Join request not found.', status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({'room': RoomSerializer(room).data})


class RejectJoinRequestView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, code: str, request_id: int) -> Response:
        svc = RoomService()
        try:
            svc.get_room_by_code(code)
        except ValueError:
            return api_error('Room not found.', status=status.HTTP_404_NOT_FOUND)

        try:
            svc.reject_join_request(request_id=request_id, host=request.user)
        except RoomJoinRequest.DoesNotExist:
            return api_error(
                'Join request not found.', status=status.HTTP_404_NOT_FOUND
            )
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({'status': 'rejected'})
