import random

from .type import (
    MafiaGodfather,
    MafiaMember,
    MafiaRoleblocker,
    TownBomb,
    TownCop,
    TownDoctor,
    TownVanilla,
    TownVigilante,
)
class UndefinedPlayerCountError(Exception):
    """Raised when no role composition has been defined for a given player count."""

    def __init__(self, count: int):
        self.count = count
        super().__init__(
            f"No role composition defined for {count} players. "
            f"Defined counts: {sorted(ROLE_COMPOSITIONS.keys())}"
        )


# -----------------------------
# ROLE COMPOSITIONS
# -----------------------------
# Keyed by exact player count. Each value is the flat list of role classes
# to hand out for a game of that size — order doesn't matter, RoleDistributor
# shuffles before assigning. Add new counts here as they're defined; counts
# with no entry raise UndefinedPlayerCountError rather than silently guessing.
ROLE_COMPOSITIONS: dict[int, list[type]] = {
    6: [
        TownDoctor,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaMember,
        MafiaMember,
    ],
    7: [
        TownDoctor,
        TownCop,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaGodfather,
        MafiaMember,
    ],
    8: [
        TownDoctor,
        TownCop,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaGodfather,
        MafiaRoleblocker,
    ],
    9: [
        TownDoctor,
        TownCop,
        TownVigilante,
        TownBomb,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaGodfather,
        MafiaRoleblocker,
        MafiaMember,
    ],
    10: [
        TownDoctor,
        TownCop,
        TownVigilante,
        TownBomb,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaGodfather,
        MafiaRoleblocker,
        MafiaMember,
    ],
    11: [
        TownDoctor,
        TownCop,
        TownVigilante,
        TownBomb,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        TownVanilla,
        MafiaGodfather,
        MafiaRoleblocker,
        MafiaMember,
    ],
}


class RoleDistributor:
    """
    Builds Player objects with randomly assigned roles for a given list of
    player ids, based on a fixed per-player-count composition table.

    Usage:
        players = RoleDistributor.distribute(player_ids=[1, 2, 3, 4, 5, 6])
    """

    @staticmethod
    def distribute(player_ids: list[int]) -> list['Player']:
        from ...engine.player import Player  # noqa: F811

        count = len(player_ids)

        composition = ROLE_COMPOSITIONS.get(count)
        if composition is None:
            raise UndefinedPlayerCountError(count)

        roles = composition.copy()
        random.shuffle(roles)

        return [
            Player(id=player_id, role=role)
            for player_id, role in zip(player_ids, roles)
        ]