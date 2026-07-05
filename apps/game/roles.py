from enum import StrEnum


class RoleType(StrEnum):
    TOWN = 'town'
    MAFIA = 'mafia'

# 1. Define the base class everything will share
class BaseRole:
    role_type: RoleType
    name: str
    description: str

    # You can put shared helper methods here later, like:
    # @classmethod
    # def is_mafia(cls) -> bool:
    #     return cls.role_type == RoleType.MAFIA


# 2. Inherit from BaseRole
class TownDoctor(BaseRole):
    role_type = RoleType.TOWN
    name = "Emerald Medic"
    description = "Protects one player from being eliminated each night."


class TownCop(BaseRole):
    role_type = RoleType.TOWN
    name = "Indigo Investigator"
    description = "Investigates one player each night to learn their alignment."


class TownVigilante(BaseRole):
    role_type = RoleType.TOWN
    name = "Azure Vigilante"
    description = "Can choose to eliminate a player at night, but has limited ammo."


class TownBomb(BaseRole):
    role_type = RoleType.TOWN
    name = "Crimson Kamikaze"
    description = "Explodes upon death, eliminating whoever was responsible for killing them."


class TownVanilla(BaseRole):
    role_type = RoleType.TOWN
    name = "Vanilla Townie"
    description = "Has no special ability. Uses vote power during the day."


class MafiaGodfather(BaseRole):
    role_type = RoleType.MAFIA
    name = "Obsidian Overlord"
    description = "The leader of the Mafia. Appears as 'Town' if investigated by the Cop."


class MafiaRoleblocker(BaseRole):
    role_type = RoleType.MAFIA
    name = "Scarlet Silencer"
    description = "Blocks one player each night, preventing them from using their action."


class MafiaMember(BaseRole):
    role_type = RoleType.MAFIA
    name = "Black Hand"
    description = "Basic Mafia member who participates in night kills."


# Type hint ROLES as a list of class types that inherit from BaseRole
ROLES: list[type[BaseRole]] = [
    TownDoctor,
    TownCop,
    TownVigilante,
    TownBomb,
    TownVanilla,
    MafiaGodfather,
    MafiaRoleblocker,
    MafiaMember,
]
