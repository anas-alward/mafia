"""Room URL routing."""

from __future__ import annotations

from django.urls import path

from .views import (
    CreateRoomView,
    FinishRoomView,
    RoomDetailView,
    HostedRoomListView,
)

urlpatterns = [
    path('', HostedRoomListView.as_view(), name='hosted-rooms'),
    path('<str:code>/', RoomDetailView.as_view(), name='room-detail'),
    path('create/', CreateRoomView.as_view(), name='create-room'),
    path('<str:code>/finish/', FinishRoomView.as_view(), name='finish-room'),
]
