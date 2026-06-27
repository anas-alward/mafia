"""Room REST endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from utils.errors import api_error
from utils.pagination import StandardPagination

from .models import Room
from .serializers import CreateRoomSerializer, RoomSerializer
from .services import RoomService


class RoomDetailView(generics.RetrieveAPIView):
    lookup_field = 'code'
    lookup_url_kwarg = 'code'
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self) -> Any:
        code = self.kwargs.get(self.lookup_url_kwarg)
        svc = RoomService()
        try:
            room = svc.get_room_by_code(code)
        except ValueError:
            raise ValueError('Room not found.')

        is_member = svc.is_member(code, self.request.user.id)
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


class HostedRoomListView(generics.ListAPIView):
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get_queryset(self) -> Any:
        return RoomService().get_hosted_rooms(host=self.request.user)


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


