"""Unit tests for the shared public-players view-model."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.game.engine.constants import PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import MafiaGodfather, TownDoctor, TownVanilla
from apps.realtime.players import build_public_players


def _room_session(members: dict[int, str]):
    def _list_members():
        return [
            SimpleNamespace(user_id=uid, name=name) for uid, name in members.items()
        ]

    return SimpleNamespace(list_members=_list_members)


class TestBuildPublicPlayers:
    @pytest.mark.asyncio
    async def test_resolves_names_from_room_members(self) -> None:
        room = _room_session({1: 'anas', 2: 'sara', 3: 'omar'})
        game = SimpleNamespace(
            players=[
                Player(id=1, role=TownVanilla()),
                Player(id=2, role=TownDoctor()),
                Player(id=3, role=MafiaGodfather()),
            ]
        )

        players = await build_public_players(room, game)

        by_id = {p['id']: p for p in players}
        assert by_id[1]['name'] == 'anas'
        assert by_id[2]['name'] == 'sara'
        assert by_id[3]['name'] == 'omar'

    @pytest.mark.asyncio
    async def test_alive_players_have_no_role_fields(self) -> None:
        room = _room_session({1: 'anas'})
        game = SimpleNamespace(players=[Player(id=1, role=MafiaGodfather())])

        players = await build_public_players(room, game)

        assert set(players[0].keys()) == {'id', 'code', 'status', 'name'}
        assert players[0]['status'] == 'alive'

    @pytest.mark.asyncio
    async def test_dead_players_carry_revealed_role(self) -> None:
        room = _room_session({1: 'anas', 2: 'sara'})
        game = SimpleNamespace(
            players=[
                Player(id=1, role=MafiaGodfather(), status=PlayerStatus.DEAD),
                Player(id=2, role=TownVanilla()),
            ]
        )

        players = await build_public_players(room, game)

        dead = players[0]
        assert dead['status'] == 'dead'
        assert dead['role_code'] == MafiaGodfather().code
        assert dead['role_name'] == MafiaGodfather().name
        assert 'role_code' not in players[1]

    @pytest.mark.asyncio
    async def test_member_without_game_player_is_ignored(self) -> None:
        room = _room_session({1: 'anas', 99: 'spectator'})
        game = SimpleNamespace(players=[Player(id=1, role=TownVanilla())])

        players = await build_public_players(room, game)

        assert [p['id'] for p in players] == [1]

    @pytest.mark.asyncio
    async def test_name_defaults_to_none_when_member_missing(self) -> None:
        room = _room_session({})
        game = SimpleNamespace(players=[Player(id=1, role=TownVanilla())])

        players = await build_public_players(room, game)

        assert players[0]['name'] is None
