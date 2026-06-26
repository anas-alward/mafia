"""Friend REST endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from utils.errors import api_error
from utils.pagination import StandardPagination

from .models import FriendRequest
from .serializers import (
    FriendRequestSerializer,
    FriendSerializer,
    SendFriendRequestSerializer,
    UserSearchSerializer,
)
from .services import FriendService


class SendFriendRequestView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        serializer = SendFriendRequestSerializer(data=request.data)
        if not serializer.is_valid():
            from utils.errors import api_validation_error
            return api_validation_error(
                'Validation failed.',
                errors=dict(serializer.errors),
            )

        svc = FriendService()
        try:
            friend_req = svc.send_request(
                sender=request.user,
                username=serializer.validated_data['username'],
            )
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': friend_req.id,
            'status': friend_req.status,
        }, status=status.HTTP_201_CREATED)


class FriendListView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request: Any) -> Response:
        svc = FriendService()
        friends = svc.get_friends(request.user)
        page = self.paginate_queryset(friends)
        if page is not None:
            return self.get_paginated_response(FriendSerializer(page, many=True).data)
        return Response({'friends': FriendSerializer(friends, many=True).data})


class IncomingRequestListView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request: Any) -> Response:
        svc = FriendService()
        requests = svc.get_incoming_requests(request.user)
        data = FriendRequestSerializer(requests, many=True).data
        return Response({'requests': data})


class OutgoingRequestListView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardPagination

    def get(self, request: Any) -> Response:
        svc = FriendService()
        requests = svc.get_outgoing_requests(request.user)
        page = self.paginate_queryset(requests)
        if page is not None:
            return self.get_paginated_response(FriendRequestSerializer(page, many=True).data)
        return Response({'requests': FriendRequestSerializer(requests, many=True).data})


class AcceptFriendRequestView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, id: int) -> Response:
        svc = FriendService()
        try:
            friend_req = svc.accept_request(request_id=id, recipient=request.user)
        except FriendRequest.DoesNotExist:
            return api_error('Friend request not found.', status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': friend_req.id,
            'status': friend_req.status,
        })


class DeclineFriendRequestView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Any, id: int) -> Response:
        svc = FriendService()
        try:
            friend_req = svc.decline_request(request_id=id, recipient=request.user)
        except FriendRequest.DoesNotExist:
            return api_error('Friend request not found.', status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return api_error(str(e), status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'id': friend_req.id,
            'status': friend_req.status,
        })


class RemoveFriendView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request: Any, user_id: int) -> Response:
        svc = FriendService()
        try:
            svc.remove_friend(user=request.user, friend_id=user_id)
        except ValueError:
            return api_error('Not friends.', status=status.HTTP_404_NOT_FOUND)

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserSearchView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Any) -> Response:
        query = request.query_params.get('q', '')
        if not query:
            return Response({'users': []})

        svc = FriendService()
        users = svc.search_users(query=query, searcher_username=request.user.username)
        return Response({'users': UserSearchSerializer(users, many=True).data})
