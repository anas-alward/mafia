from django.urls import path

from apps.room.consumers import RoomConsumer
from apps.game.consumers import GameConsumer

websocket_urlpatterns = [
    path('ws/room/<str:code>/', RoomConsumer.as_asgi()),
    path('ws/game/<int:session_id>/', GameConsumer.as_asgi()),
]
