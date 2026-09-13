import pytest
from channels.testing import WebsocketCommunicator
from django.core.exceptions import PermissionDenied

from config.asgi import application


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_unknown_websocket_path_is_closed_cleanly():
    communicator = WebsocketCommunicator(application, '/ws/unknown/')
    connected, _ = await communicator.connect()
    assert not connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_empty_websocket_path_is_closed_cleanly():
    """Empty-path probes must not raise inside URLRouter."""
    communicator = WebsocketCommunicator(application, '')
    connected, _ = await communicator.connect()
    assert not connected
    await communicator.disconnect()


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_room_route_matches_then_rejects_unauthenticated():
    """The room route still matches — the consumer then raises
    PermissionDenied without a token, which is distinct from
    'no route found'."""
    communicator = WebsocketCommunicator(application, '/ws/room/ABC123/')
    with pytest.raises(PermissionDenied):
        await communicator.connect()
