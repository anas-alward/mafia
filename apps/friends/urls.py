"""Friend URL routing."""

from __future__ import annotations

from django.urls import path

from .views import (
    AcceptFriendRequestView,
    DeclineFriendRequestView,
    FriendListView,
    IncomingRequestListView,
    OutgoingRequestListView,
    RemoveFriendView,
    SendFriendRequestView,
    UserSearchView,
)

urlpatterns = [
    path('', FriendListView.as_view(), name='friend-list'),
    path('requests/send/', SendFriendRequestView.as_view(), name='send-friend-request'),
    path('requests/incoming/', IncomingRequestListView.as_view(), name='incoming-requests'),
    path('requests/outgoing/', OutgoingRequestListView.as_view(), name='outgoing-requests'),
    path('requests/<int:id>/accept/', AcceptFriendRequestView.as_view(), name='accept-friend-request'),
    path('requests/<int:id>/decline/', DeclineFriendRequestView.as_view(), name='decline-friend-request'),
    path('search/', UserSearchView.as_view(), name='user-search'),
    path('<int:user_id>/', RemoveFriendView.as_view(), name='remove-friend'),
]
