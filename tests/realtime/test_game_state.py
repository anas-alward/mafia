from __future__ import annotations

import pytest
from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    MafiaRoleblocker,
    RoleType,
    TownCop,
    TownDoctor,
    TownVanilla,
)
from apps.game.engine.round import NightRound
from apps.realtime.events.game import GameState


class TestGameStateEvent:
    """Verify the GameState outbound event fields and defaults."""

    def test_defaults(self):
        gs = GameState()
        assert gs.session_id is None
        assert gs.players == []
        assert gs.live_player_ids == []
        assert gs.dead_player_ids == []
        assert gs.current_phase is None
        assert gs.round_number is None
        assert gs.lynch_target_id is None
        assert gs.logs == []
        assert gs.role_name is None
        assert gs.role_type is None
        assert gs.role_description is None
        assert gs.mafia_ids is None
        assert gs.required_actions == []

    def test_channel_type(self):
        gs = GameState()
        assert gs.channel_type == 'game_state'

    def test_full_payload_structure(self):
        gs = GameState(
            session_id='abc123',
            players=[
                {'id': 1, 'code': 'AX1B2C', 'status': 'alive'},
                {'id': 2, 'code': 'DY3E4F', 'status': 'dead'},
            ],
            live_player_ids=[1],
            dead_player_ids=[2],
            current_phase='night',
            round_number=3,
            lynch_target_id=None,
            logs=[{'actor_id': 1, 'target_id': 2, 'action_type': 'kill'}],
            role_name='Mafia King',
            role_type='mafia',
            role_description='The leader of the Mafia.',
            mafia_ids=[1, 4],
            required_actions=[{'action_type': 'kill', 'target_options': [2, 3]}],
        )
        payload = gs.to_json()
        assert payload['type'] == 'game_state'
        assert payload['session_id'] == 'abc123'
        assert len(payload['players']) == 2
        assert payload['live_player_ids'] == [1]
        assert payload['dead_player_ids'] == [2]
        assert payload['current_phase'] == 'night'
        assert payload['round_number'] == 3
        assert payload['lynch_target_id'] is None
        assert len(payload['logs']) == 1
        assert payload['role_name'] == 'Mafia King'
        assert payload['role_type'] == 'mafia'
        assert payload['mafia_ids'] == [1, 4]
        assert len(payload['required_actions']) == 1


class TestReconnectionPayload:
    """Verify the logic used to build the GameState on reconnect."""

    def _build_public_players(self, players: list[Player]) -> list[dict]:
        return [
            {'id': p.id, 'code': p.code, 'status': p.status.value}
            for p in players
        ]

    def test_public_players_strip_role(self):
        """Player list sent in GameState must only expose id, code, status."""
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
            Player(id=3, role=TownVanilla()),
        ]
        public = self._build_public_players(players)
        for entry in public:
            assert set(entry.keys()) == {'id', 'code', 'status'}
            assert 'role' not in entry
            assert 'role_name' not in entry
            assert 'role_type' not in entry

    def test_live_and_dead_splits(self):
        players = [
            Player(id=1, role=TownVanilla(), status=PlayerStatus.ALIVE),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.DEAD),
            Player(id=3, role=TownVanilla(), status=PlayerStatus.ALIVE),
            Player(id=4, role=TownVanilla(), status=PlayerStatus.DEAD),
        ]
        live_ids = [p.id for p in players if p.status == PlayerStatus.ALIVE]
        dead_ids = [p.id for p in players if p.status == PlayerStatus.DEAD]
        assert live_ids == [1, 3]
        assert dead_ids == [2, 4]

    def test_mafia_ids_only_for_mafia_player(self):
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
            Player(id=3, role=MafiaMember()),
            Player(id=4, role=TownVanilla()),
        ]

        # Mafia player (id=1) sees mafia_ids.
        mafia_player = next(p for p in players if p.id == 1)
        assert mafia_player.role.role_type == RoleType.MAFIA
        mafia_teammates = [
            p.id for p in players
            if p.role is not None and p.role.role_type == RoleType.MAFIA
        ]
        assert mafia_teammates == [1, 3]

        # Town player (id=2) gets None.
        town_player = next(p for p in players if p.id == 2)
        assert town_player.role.role_type == RoleType.TOWN
        is_mafia = town_player.role.role_type == RoleType.MAFIA
        assert is_mafia is False

    def test_role_info_for_reconnecting_player(self):
        players = [
            Player(id=1, role=MafiaRoleblocker()),
            Player(id=2, role=TownCop()),
        ]
        my_player = next(p for p in players if p.id == 1)
        assert my_player.role is not None
        assert my_player.role.name == 'Mafia Silencer'
        assert my_player.role.role_type.value == 'mafia'
        assert 'Blocks one player' in my_player.role.description

    def test_required_actions_for_reconnecting_player(self):
        players = [
            Player(id=1, role=TownDoctor()),
            Player(id=2, role=MafiaGodfather()),
            Player(id=3, role=TownVanilla()),
        ]
        round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()

        doctor_actions = round_.get_required_actions_for_player(1)
        assert len(doctor_actions) == 1
        assert doctor_actions[0]['action_type'] == 'heal'
        assert 2 in doctor_actions[0]['target_options']

        vanilla_actions = round_.get_required_actions_for_player(3)
        assert vanilla_actions == []

    def test_logs_include_round_actions(self):
        round_ = NightRound(round_number=2, members=[], phase=Phase.NIGHT)
        round_.night_actions = [
            Action(actor_id=1, target_id=2, action_type=ActionType.KILL),
            Action(actor_id=3, target_id=1, action_type=ActionType.HEAL),
        ]
        logs = [a.to_dict() for a in round_.all_actions]
        assert len(logs) == 2
        assert logs[0] == {'actor_id': 1, 'target_id': 2, 'action_type': 'kill'}
        assert logs[1] == {'actor_id': 3, 'target_id': 1, 'action_type': 'heal'}
