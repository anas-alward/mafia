from enum import StrEnum


class PlayerStatus(StrEnum):
    ALIVE = 'alive'
    DEAD = 'dead'


class ActionType(StrEnum):
    KILL = 'kill'
    REVENGE = 'revenge'
    VOTE = 'vote'
    HEAL = 'heal'
    DETECT = 'detect'
    SHOOT = 'shoot'
    ROLEBLOCK = 'roleblock'
    SILENT = 'silent'
    LYNCH = 'lynch'


class Phase(StrEnum):
    DAY = 'day'
    NIGHT = 'night'
    VOTE_RESULT = 'vote_result'


from dataclasses import dataclass


@dataclass
class ActionConfig:
    action_type: ActionType
    required: bool
    priority: int | None = None

    def to_dict(self) -> dict:
        return {
            'action_type': self.action_type.value,
            'required': self.required,
            'priority': self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionConfig':
        return cls(
            action_type=ActionType(data['action_type']),
            required=data['required'],
            priority=data.get('priority'),
        )
