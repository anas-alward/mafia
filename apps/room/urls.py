from django.urls import path

from .views import (
    AddMemberView, CreateRoomView, FinishRoomView, HostedRoomListView,
    JoinRoomView, MemberListView, RemoveMemberView,
)

urlpatterns = [
    path('', HostedRoomListView.as_view(), name='hosted-rooms'),
    path('create/', CreateRoomView.as_view(), name='create-room'),
    path('<str:code>/join/', JoinRoomView.as_view(), name='join-room'),
    path('<str:code>/members/', MemberListView.as_view(), name='list-members'),
    path('<str:code>/add/', AddMemberView.as_view(), name='add-member'),
    path('<str:code>/remove/', RemoveMemberView.as_view(), name='remove-member'),
    path('<str:code>/finish/', FinishRoomView.as_view(), name='finish-room'),
]
