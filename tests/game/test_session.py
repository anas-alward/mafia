from apps.game.engine.session import GameSession


def test_session_to_dict_includes_silenced_player_ids():
    session = GameSession(id='abc', room_id='room1', silenced_player_ids=[3, 7])
    data = session.to_dict()
    assert data['silenced_player_ids'] == [3, 7]


def test_session_roundtrip_preserves_silenced_player_ids():
    session = GameSession(id='abc', room_id='room1', silenced_player_ids=[3, 7])
    restored = GameSession.from_dict(session.to_dict())
    assert restored.silenced_player_ids == [3, 7]


def test_session_from_dict_defaults_missing_silenced_player_ids():
    data = {
        'id': 'abc',
        'room_id': 'room1',
        'players': [],
        'rounds': [],
    }
    restored = GameSession.from_dict(data)
    assert restored.silenced_player_ids == []
