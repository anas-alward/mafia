from __future__ import annotations

from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict


class InboundEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra='ignore')

    type: ClassVar[str]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Self:
        data = {k: v for k, v in payload.items() if k != 'type'}
        return cls(**data)

    @classmethod
    def _type_name(cls) -> str:
        return getattr(cls, 'type', '<unknown>')


class OutboundEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra='ignore')

    channel_type: ClassVar[str]

    def to_event(self) -> dict[str, Any]:
        return {'type': self.channel_type, **self.model_dump()}

    def to_json(self) -> dict[str, Any]:
        return {'type': self.channel_type, **self.model_dump()}