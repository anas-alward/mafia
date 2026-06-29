from django.urls import path

from apps.game.consumers import GameConsumer
from apps.room.realtime.consumers import RoomConsumer

websocket_urlpatterns = [
    path('ws/room/<str:code>/', RoomConsumer.as_asgi()),
    path('ws/game/<int:session_id>/', GameConsumer.as_asgi()),
]
