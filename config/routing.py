import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from django.urls import re_path

from apps.realtime.consumers import RealtimeConsumer

logger = logging.getLogger(__name__)


class UnmatchedRouteConsumer(AsyncWebsocketConsumer):
    """Closes stray websocket connections cleanly.

    Without this fallback, URLRouter raises
    ``ValueError: No route found for path ...`` for every probe or
    misrouted client (e.g. empty-path connections), spamming the logs
    with tracebacks.
    """

    async def connect(self):
        logger.warning(
            'Rejected websocket connection to unmatched path: %r',
            self.scope.get('path'),
        )
        await self.close(code=4404)


websocket_urlpatterns = [
    re_path(r'ws/room/(?P<code>\w+)/$', RealtimeConsumer.as_asgi()),
    # Catch-all: must stay last — closes unknown/empty paths with 4404.
    re_path(r'.*', UnmatchedRouteConsumer.as_asgi()),
]
