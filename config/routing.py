from django.urls import re_path

from apps.realtime.consumers import RealtimeConsumer

websocket_urlpatterns = [
    re_path(r'ws/room/(?P<code>\w+)/$', RealtimeConsumer.as_asgi()),
]
