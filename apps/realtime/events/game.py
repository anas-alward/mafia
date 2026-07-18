from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from .base import InboundEvent, OutboundEvent


class GameEvents(StrEnum):
    START_GAME = 'start_game'
    VOTE = 'vote'
    KILL = 'kill'
    REVENGE = 'revenge'
    HEAL = 'heal'
    SHOOT = 'shoot'
    DETECT = 'detect'
    SUBMIT_VOTES = 'submit_votes'
    SILENT = 'silent'
    SUN_SET = 'sun_set'
    GAME_STARTED = 'game_started'
    SUN_RISE = 'sun_rise'
    ROLE_ASSIGNED = 'role_assigned'
    VOTE_CAST = 'vote_cast'
    VOTE_RESULT_STARTED = 'vote_result_started'
    SUBMIT_VOTE_RESULT = 'submit_vote_result'


# -- Inbound ------------------------------------------------------------------

class StartGame(InboundEvent):
    type: ClassVar[str] = GameEvents.START_GAME
    player_ids: list[int]


class Vote(InboundEvent):
    type: ClassVar[str] = GameEvents.VOTE
    target_id: int


class Kill(InboundEvent):
    type: ClassVar[str] = GameEvents.KILL
    target_id: int


class Revenge(InboundEvent):
    type: ClassVar[str] = GameEvents.REVENGE
    target_id: int


class Heal(InboundEvent):
    type: ClassVar[str] = GameEvents.HEAL
    target_id: int


class Shoot(InboundEvent):
    type: ClassVar[str] = GameEvents.SHOOT
    target_id: int


class Detect(InboundEvent):
    type: ClassVar[str] = GameEvents.DETECT
    target_id: int


class SubmitVotes(InboundEvent):
    type: ClassVar[str] = GameEvents.SUBMIT_VOTES


class Silent(InboundEvent):
    type: ClassVar[str] = GameEvents.SILENT
    target_id: int | None = None


# -- Outbound -----------------------------------------------------------------

class SunSet(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.SUN_SET
    player_ids: list[int]
    logs: list[dict[str, Any]]


class SunRise(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.SUN_RISE
    player_ids: list[int]
    logs: list[dict[str, Any]]


class GameStarted(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.GAME_STARTED
    player_ids: list[int]
    session_id: str
    host: int
    alive_ids: list[int]


class RoleAssigned(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.ROLE_ASSIGNED
    role_name: str
    description: str
    role_type: str
    mafia_ids: list[int] | None = None


class VoteCast(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.VOTE_CAST
    actor_id: int
    target_id: int


class VoteResultStarted(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.VOTE_RESULT_STARTED
    lynch_target_id: int
    logs: list[dict[str, Any]]


class SubmitVoteResult(InboundEvent):
    type: ClassVar[str] = GameEvents.SUBMIT_VOTE_RESULT
