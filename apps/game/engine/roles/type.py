from enum import StrEnum

from ..constants import ActionType, Phase, ActionConfig


class RoleType(StrEnum):
    TOWN = 'town'
    MAFIA = 'mafia'


class BaseRole:
    code: str
    role_type: RoleType
    name: str
    description: str
    actions: dict[Phase, list[ActionConfig]] = {}
    # Voting power in day votes. Everyone has 1 except the Mayor (3).
    vote_weight: int = 1


class TownDoctor(BaseRole):
    code = "doctor"
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
    code = "detective"
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
    code = "vigilante"
    role_type = RoleType.TOWN
    name = "Azure Vigilante"
    description = "May shoot one player during the day instead of voting (2 bullets). Shooting a Town player eliminates the Vigilante too."
    actions = {
        Phase.DAY: [
            ActionConfig(action_type=ActionType.SHOOT, required=False),
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownBomb(BaseRole):
    code = "bomb"
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
    code = "vanilla"
    role_type = RoleType.TOWN
    name = "Vanilla Townie"
    description = "Has no special ability. Uses vote power during the day."
    actions = {
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownMayor(BaseRole):
    code = "mayor"
    role_type = RoleType.TOWN
    name = "Mayor"
    description = "Elected town leader whose day vote counts as 3 votes."
    vote_weight = 3
    actions = {
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaGodfather(BaseRole):
    code = "godfather"
    role_type = RoleType.MAFIA
    name = "Mafia King"
    description = "The leader of the Mafia. Appears as 'Town' if investigated by the Cop. When killed, takes an enemy down with him."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=1),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
        # Dying revenge: when the King is killed at night, he acts in the
        # following vote-result phase (entitlement recorded by the night
        # resolve in session.pending_dying_revenge).
        Phase.VOTE_RESULT: [
            ActionConfig(action_type=ActionType.REVENGE, required=True),
        ],
    }


class MafiaSilencer(BaseRole):
    code = "silencer"
    role_type = RoleType.MAFIA
    name = "Silencer"
    description = "Silences one player each night, muting their voice for the following day."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=2),
            ActionConfig(action_type=ActionType.SILENCE, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaMember(BaseRole):
    code = "mafia_member"
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
    TownMayor(),
    MafiaGodfather(),
    MafiaSilencer(),
    MafiaMember(),
]

ROLE_REGISTRY: dict[str, BaseRole] = {role.code: role for role in ROLES}
