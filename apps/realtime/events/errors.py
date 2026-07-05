from dataclasses import dataclass

from ..error_codes import ErrorCode
from .base import OutboundEvent


class ErrorEvent(OutboundEvent):
    code: ErrorCode
    message: str
    type: str = 'error'

    def to_json(self) -> dict:
        return {'type': self.type, 'code': self.code, 'message': self.message}
