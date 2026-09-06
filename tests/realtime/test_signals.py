"""Unit tests for action-signal audience rules."""

from __future__ import annotations

from types import SimpleNamespace

from apps.game.engine.constants import ActionType, PlayerStatus
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    TownCop,
    TownDoctor,
    TownVanilla,
)
from apps.realtime.signals import signal_recipients


def _player(pid: int, role, status=PlayerStatus.ALIVE):
    return SimpleNamespace(id=pid, role=role, status=status)


def _session(players):
    return SimpleNamespace(players=players)


class TestSignalRecipients:
    def test_kill_goes_to_alive_mafia_only(self) -> None:
        session = _session(
            [
                _player(1, MafiaGodfather(), PlayerStatus.DEAD),  # dead king
                _player(2, MafiaMember()),
                _player(3, TownCop()),
                _player(4, TownVanilla(), PlayerStatus.DEAD),
            ]
        )
        recipients, include_actor = signal_recipients(
            ActionType.KILL, session, actor_id=2
        )
        assert recipients == [2]
        assert include_actor is False

    def test_heal_goes_to_doctor_only(self) -> None:
        session = _session(
            [
                _player(1, TownDoctor()),
                _player(2, TownVanilla()),
                _player(3, MafiaMember()),
            ]
        )
        recipients, include_actor = signal_recipients(
            ActionType.HEAL, session, actor_id=1
        )
        assert recipients == [1]
        assert include_actor is False

    def test_vote_goes_to_everyone_with_actor(self) -> None:
        session = _session(
            [
                _player(1, TownVanilla()),
                _player(2, MafiaMember(), PlayerStatus.DEAD),
                _player(3, TownCop()),
            ]
        )
        recipients, include_actor = signal_recipients(
            ActionType.VOTE, session, actor_id=1
        )
        assert recipients == [1, 2, 3]
        assert include_actor is True

    def test_unknown_action_has_no_recipients(self) -> None:
        session = _session([_player(1, TownVanilla())])
        recipients, include_actor = signal_recipients(
            ActionType.DETECT, session, actor_id=1
        )
        assert recipients == []
        assert include_actor is False
