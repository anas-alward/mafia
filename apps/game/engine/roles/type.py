from enum import StrEnum

from ..constants import ActionType, Phase, ActionConfig


class RoleType(StrEnum):
    TOWN = 'town'
    MAFIA = 'mafia'


class BaseRole:
    role_type: RoleType
    name: str
    description: str
    actions: dict[Phase, list[ActionConfig]] = {}


class TownDoctor(BaseRole):
    role_type = RoleType.TOWN
    name = "Doctor"
    description = "Protects one player from being eliminated each night."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.HEAL, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownCop(BaseRole):
    role_type = RoleType.TOWN
    name = "Detective"
    description = "Investigates one player each night to learn their alignment."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.DETECT, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownVigilante(BaseRole):
    role_type = RoleType.TOWN
    name = "Azure Vigilante"
    description = "Can choose to eliminate a player at night, but has limited ammo."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.SHOOT, required=False),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownBomb(BaseRole):
    role_type = RoleType.TOWN
    name = "Crimson Kamikaze"
    description = "Explodes upon death, eliminating whoever was responsible for killing them."
    actions = {
        Phase.VOTE_RESULT: [
            ActionConfig(action_type=ActionType.REVENGE, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownVanilla(BaseRole):
    role_type = RoleType.TOWN
    name = "Vanilla Townie"
    description = "Has no special ability. Uses vote power during the day."
    actions = {
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaGodfather(BaseRole):
    role_type = RoleType.MAFIA
    name = "Mafia King"
    description = "The leader of the Mafia. Appears as 'Town' if investigated by the Cop."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=1),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaRoleblocker(BaseRole):
    role_type = RoleType.MAFIA
    name = "Mafia Silencer"
    description = "Blocks one player each night, preventing them from using their action."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=2),
            ActionConfig(action_type=ActionType.ROLEBLOCK, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaMember(BaseRole):
    role_type = RoleType.MAFIA
    name = "Black Hand"
    description = "Basic Mafia member who participates in night kills."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=3),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


ROLES: list[BaseRole] = [
    TownDoctor(),
    TownCop(),
    TownVigilante(),
    TownBomb(),
    TownVanilla(),
    MafiaGodfather(),
    MafiaRoleblocker(),
    MafiaMember(),
]

ROLE_REGISTRY: dict[str, BaseRole] = {role.name: role for role in ROLES}
