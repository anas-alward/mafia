from apps.game.engine.constants import PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaMember,
    TownDoctor,
    TownVanilla,
)
from apps.game.engine.session import GameSession


class TestCheckWinner:
    def _session(self, players: list[Player]) -> GameSession:
        return GameSession(id='test', room_id='room1', players=players)

    def test_all_mafia_dead_town_wins(self):
        players = [
            Player(id=1, role=MafiaGodfather(), status=PlayerStatus.DEAD),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.ALIVE),
            Player(id=3, role=TownDoctor(), status=PlayerStatus.ALIVE),
        ]
        assert self._session(players).check_winner() == 'town'

    def test_mafia_majority_mafia_wins(self):
        players = [
            Player(id=1, role=MafiaGodfather(), status=PlayerStatus.ALIVE),
            Player(id=2, role=MafiaMember(), status=PlayerStatus.ALIVE),
            Player(id=3, role=TownVanilla(), status=PlayerStatus.ALIVE),
        ]
        assert self._session(players).check_winner() == 'mafia'

    def test_mafia_equal_to_town_mafia_wins(self):
        players = [
            Player(id=1, role=MafiaGodfather(), status=PlayerStatus.ALIVE),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.ALIVE),
        ]
        assert self._session(players).check_winner() == 'mafia'

    def test_mafia_fewer_than_town_game_continues(self):
        players = [
            Player(id=1, role=MafiaGodfather(), status=PlayerStatus.ALIVE),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.ALIVE),
            Player(id=3, role=TownDoctor(), status=PlayerStatus.ALIVE),
        ]
        assert self._session(players).check_winner() is None

    def test_dead_players_ignored(self):
        players = [
            Player(id=1, role=MafiaGodfather(), status=PlayerStatus.ALIVE),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.ALIVE),
            # Dead townies must not push the game into "continues".
            Player(id=3, role=TownDoctor(), status=PlayerStatus.DEAD),
            Player(id=4, role=TownVanilla(), status=PlayerStatus.DEAD),
        ]
        assert self._session(players).check_winner() == 'mafia'
