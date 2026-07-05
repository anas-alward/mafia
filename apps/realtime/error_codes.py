from enum import StrEnum


class ErrorCode(StrEnum):
    UNKNOWN_EVENT_TYPE = 'unknown_event_type'
    INVALID_PAYLOAD = 'invalid_payload'
    NOT_HOST = 'not_host'
    NOT_PENDING = 'not_pending'
    NOT_MEMBER = 'not_member'
    GAME_NOT_STARTED = 'game_not_started'
    GAME_ALREADY_STARTED = 'game_already_started'
    INVALID_ACTION = 'invalid_action'
    WRONG_PHASE = 'wrong_phase'
    NOT_ALL_VOTED = 'not_all_voted'
    INTERNAL_ERROR = 'internal_error'


