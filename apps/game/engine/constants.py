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
