"""Room URL routing."""

from __future__ import annotations

from django.urls import path

from .views import (
    AcceptJoinRequestView,
    AddMemberView,
    CreateRoomView,
    FinishRoomView,
    RoomDetailView,
    HostedRoomListView,
    JoinRequestListView,
    JoinRoomView,
    MemberListView,
    RejectJoinRequestView,
    RemoveMemberView,
)

urlpatterns = [
    path('', HostedRoomListView.as_view(), name='hosted-rooms'),
    path('<str:code>/', RoomDetailView.as_view(), name='room-detail'),
    path('create/', CreateRoomView.as_view(), name='create-room'),
    path('<str:code>/join/', JoinRoomView.as_view(), name='join-room'),
    path('<str:code>/members/', MemberListView.as_view(), name='list-members'),
    path('<str:code>/add/', AddMemberView.as_view(), name='add-member'),
    path('<str:code>/remove/', RemoveMemberView.as_view(), name='remove-member'),
    path('<str:code>/finish/', FinishRoomView.as_view(), name='finish-room'),
    path('<str:code>/join-requests/', JoinRequestListView.as_view(), name='list-join-requests'),
    path('<str:code>/join-requests/<int:request_id>/accept/', AcceptJoinRequestView.as_view(), name='accept-join-request'),
    path('<str:code>/join-requests/<int:request_id>/reject/', RejectJoinRequestView.as_view(), name='reject-join-request'),
]
