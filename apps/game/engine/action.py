from dataclasses import dataclass

from .constants import ActionType


@dataclass
class Action:
    actor_id: int
    target_id: int | None
    action_type: ActionType

    def to_dict(self) -> dict:
        return {
            'actor_id': self.actor_id,
            'target_id': self.target_id,
            'action_type': self.action_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Action:
        return cls(
            actor_id=data['actor_id'],
            target_id=data['target_id'],
            action_type=ActionType(data['action_type']),
        )
