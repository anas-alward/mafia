from dataclasses import dataclass, field

from apps.core.utils.uuid import generate_code

from .constants import PlayerStatus
from .roles.type import ROLE_REGISTRY, BaseRole


@dataclass
class Player:
    id: int
    code: str = field(default_factory=lambda: generate_code(length=6))
    status: PlayerStatus = PlayerStatus.ALIVE
    role: BaseRole = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'code': self.code,
            'status': self.status.value,
            'role_code': self.role.code if self.role else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Player:
        role_code = data.get('role_code')
        return cls(
            id=data['id'],
            code=data['code'],
            status=PlayerStatus(data['status']),
            role=ROLE_REGISTRY.get(role_code) if role_code else None,
        )
