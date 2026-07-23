import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from apps.core.redis import redis_client

from .action import Action
from .constants import ActionType, Phase, PlayerStatus
from .player import Player

if TYPE_CHECKING:
    from .session import GameSession

GRACE_SECONDS: float = 5.0


# =============================================================================
# BASE CLASS
# =============================================================================


@dataclass
class GameRound:
    """Shared state and behaviour for a single game round.

    Subclasses (NightRound, DayRound, VoteResultRound) own the
    phase-specific fields, resolution logic, obligation computation,
    and target-option filtering.
    """

    round_number: int
    phase: Phase
    members: list[Player] = field(default_factory=list)
    obligations: dict[int, list[ActionType]] = field(default_factory=dict)
    grace_started_at: float | None = field(default=None, repr=False)
    _session: GameSession | None = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Abstract interface (subclasses MUST implement)
    # ------------------------------------------------------------------

    def _get_actions_list(self) -> list[Action]:
        """Return the mutable action list for the current phase."""
        raise NotImplementedError

    def compute_obligations(self) -> None:
        """Fill ``self.obligations`` for this phase."""
        raise NotImplementedError

    async def resolve(self) -> list[dict]:
        """Run phase-specific resolution.  Return log entries."""
        raise NotImplementedError

    def _target_options_for(self, actor_id: int, action_type: ActionType) -> list[int]:
        """Return valid target player IDs for *action_type*."""
        return [p.id for p in self.members if p.status == PlayerStatus.ALIVE]

    @staticmethod
    def _extra_kwargs_from_dict(data: dict) -> dict:
        """Additional kwargs for the subclass constructor during deserialization."""
        raise NotImplementedError

    def _to_dict_extra(self) -> dict:
        """Additional key-value pairs for serialization."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_player(self, player_id: int) -> Player | None:
        for p in self.members:
            if p.id == player_id:
                return p
        return None

    def alive_player_ids(self) -> set[int]:
        return {p.id for p in self.members if p.status == PlayerStatus.ALIVE}

    @property
    def all_actions(self) -> list[Action]:
        """All actions recorded in this round (for reconnection / logs display)."""
        return self._get_actions_list()

    # ------------------------------------------------------------------
    # Grace timer
    # ------------------------------------------------------------------

    def start_grace(self) -> None:
        self.grace_started_at = time.time()

    def is_grace_expired(self) -> bool:
        if self.grace_started_at is None:
            return False
        return (time.time() - self.grace_started_at) >= GRACE_SECONDS

    # ------------------------------------------------------------------
    # Obligation helpers
    # ------------------------------------------------------------------

    def get_required_actions_for_player(self, player_id: int) -> list[dict]:
        """Return the list of required actions with target_options for a player."""
        required_types = self.obligations.get(player_id, [])
        if not required_types:
            return []
        result: list[dict] = []
        for at in required_types:
            result.append({
                'action_type': at.value,
                'target_options': self._target_options_for(player_id, at),
            })
        return result

    async def is_player_done(self, player_id: int) -> bool:
        """True when this player has submitted all their required actions."""
        required = self.obligations.get(player_id, [])
        if not required:
            return True

        submitted: set[ActionType] = set()
        for a in self._get_actions_list():
            if a.actor_id == player_id:
                submitted.add(a.action_type)

        if self._session is not None:
            pending_raw = await redis_client.lrange(self._session.pending_actions_key, 0, -1)
            for raw in pending_raw:
                a = Action.from_dict(json.loads(raw))
                if a.actor_id == player_id:
                    submitted.add(a.action_type)

        return all(at in submitted for at in required)

    async def is_round_done(self) -> bool:
        """True when ALL obligated players have completed their required actions."""
        if not self.obligations:
            return True
        for pid in self.obligations:
            if not await self.is_player_done(pid):
                return False
        return True

    # ------------------------------------------------------------------
    # Action entry & resolution helpers
    # ------------------------------------------------------------------

    async def add_action(self, action: Action) -> None:
        """Atomically push action to Redis to avoid read-modify-write races."""
        if self._session is None:
            self._get_actions_list().append(action)
            return
        payload = json.dumps(action.to_dict())
        await redis_client.rpush(self._session.pending_actions_key, payload)

    async def _merge_pending_actions(self) -> None:
        """Merge pending Redis actions into the in-memory action list."""
        if self._session is not None:
            pending_key = self._session.pending_actions_key
            pending_raw = await redis_client.lrange(pending_key, 0, -1)
            for raw in pending_raw:
                action = Action.from_dict(json.loads(raw))
                self._get_actions_list().append(action)
            if pending_raw:
                await redis_client.delete(pending_key)

    async def _autosave(self) -> None:
        if self._session is not None:
            await self._session.save()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        result = {
            'round_type': self.__class__.__name__,
            'round_number': self.round_number,
            'members': [p.to_dict() for p in self.members],
            'phase': self.phase.value,
            'grace_started_at': self.grace_started_at,
        }
        result.update(self._to_dict_extra())
        return result

    @classmethod
    def from_dict(cls, data: dict, session: GameSession) -> GameRound:
        round_type = data.get('round_type')
        if round_type is None:
            phase = Phase(data['phase'])
            round_type = ROUND_CLASSES[phase].__name__
        subclass = ROUND_REGISTRY[round_type]
        kwargs = dict(
            round_number=data['round_number'],
            members=[Player.from_dict(p) for p in data['members']],
            phase=Phase(data['phase']),
            grace_started_at=data.get('grace_started_at'),
            _session=session,
        )
        kwargs.update(subclass._extra_kwargs_from_dict(data))
        instance = subclass(**kwargs)
        instance.compute_obligations()
        return instance


# =============================================================================
# NIGHT ROUND
# =============================================================================


@dataclass
class NightRound(GameRound):
    """Night phase: mafia kills, heals, investigations, roleblocks, etc."""

    night_actions: list[Action] = field(default_factory=list)

    def _get_actions_list(self) -> list[Action]:
        return self.night_actions

    def compute_obligations(self) -> None:
        self.obligations = {}
        mafia_kill_candidates: list[tuple[int, int]] = []
        for player in self.members:
            if player.role is None:
                continue
            if player.status == PlayerStatus.DEAD:
                continue
            role_actions = player.role.actions.get(Phase.NIGHT, [])
            for cfg in role_actions:
                if not cfg.required:
                    continue
                if cfg.action_type == ActionType.KILL and cfg.priority is not None:
                    mafia_kill_candidates.append((cfg.priority, player.id))
                else:
                    self.obligations.setdefault(player.id, []).append(cfg.action_type)
        if mafia_kill_candidates:
            mafia_kill_candidates.sort(key=lambda x: x[0])
            chosen_id = mafia_kill_candidates[0][1]
            self.obligations.setdefault(chosen_id, []).append(ActionType.KILL)

    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        logs: list[dict] = []
        blocked: set[int] = set()
        healed: set[int] = set()

        # 1. ROLEBLOCK
        for a in self.night_actions:
            if a.action_type == ActionType.ROLEBLOCK:
                blocked.add(a.target_id)
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 2. HEAL
        for a in self.night_actions:
            if a.action_type == ActionType.HEAL:
                if a.actor_id in blocked:
                    continue
                healed.add(a.target_id)
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 3. OFFENSIVE ACTIONS (KILL / SHOOT)
        for a in self.night_actions:
            if a.action_type in (ActionType.KILL, ActionType.SHOOT):
                if a.actor_id in blocked:
                    continue
                if a.target_id in healed:
                    logs.append({'target_id': a.target_id, 'action_type': a.action_type.value, 'result': 'healed'})
                else:
                    target = self._get_player(a.target_id)
                    if target:
                        target.status = PlayerStatus.DEAD
                    logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 4. DETECT
        for a in self.night_actions:
            if a.action_type == ActionType.DETECT:
                if a.actor_id in blocked:
                    continue
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        await self._autosave()
        return logs

    def _target_options_for(self, actor_id: int, action_type: ActionType) -> list[int]:
        if action_type == ActionType.KILL:
            actor = self._get_player(actor_id)
            if actor and actor.role:
                return [
                    p.id for p in self.members
                    if p.status == PlayerStatus.ALIVE
                    and (p.role is None or p.role.role_type != actor.role.role_type)
                ]
        return super()._target_options_for(actor_id, action_type)

    def _to_dict_extra(self) -> dict:
        return {'night_actions': [a.to_dict() for a in self.night_actions]}

    @staticmethod
    def _extra_kwargs_from_dict(data: dict) -> dict:
        return {
            'night_actions': [Action.from_dict(a) for a in data.get('night_actions', [])],
        }


# =============================================================================
# DAY ROUND
# =============================================================================


@dataclass
class DayRound(GameRound):
    """Day phase: voting and lynch determination."""

    day_actions: list[Action] = field(default_factory=list)
    lynch_target_id: int | None = None

    def _get_actions_list(self) -> list[Action]:
        return self.day_actions

    def compute_obligations(self) -> None:
        self.obligations = {}
        for player in self.members:
            if player.status == PlayerStatus.ALIVE:
                self.obligations[player.id] = [ActionType.VOTE]

    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        logs: list[dict] = []
        actor_votes: dict[int, int] = {}

        for a in self.day_actions:
            if a.action_type == ActionType.VOTE:
                if a.target_id is None:
                    continue
                actor_votes[a.actor_id] = a.target_id
                logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        tally: dict[int, int] = {}
        for target_id in actor_votes.values():
            tally[target_id] = tally.get(target_id, 0) + 1

        if tally:
            lynch = max(tally, key=tally.get)
            self.lynch_target_id = lynch
            self.day_actions.append(
                Action(actor_id=lynch, target_id=None, action_type=ActionType.LYNCH)
            )
            logs.append({'actor_id': lynch, 'target_id': None, 'action_type': ActionType.LYNCH.value})

        await self._autosave()
        return logs

    def _to_dict_extra(self) -> dict:
        return {
            'day_actions': [a.to_dict() for a in self.day_actions],
            'lynch_target_id': self.lynch_target_id,
        }

    @staticmethod
    def _extra_kwargs_from_dict(data: dict) -> dict:
        return {
            'day_actions': [Action.from_dict(a) for a in data.get('day_actions', [])],
            'lynch_target_id': data.get('lynch_target_id'),
        }

    # ------------------------------------------------------------------
    # Voting helpers
    # ------------------------------------------------------------------

    async def voter_ids(self) -> set[int]:
        """Return the set of actor IDs who have voted this round."""
        voters: set[int] = set()
        for a in self.day_actions:
            if a.action_type == ActionType.VOTE:
                voters.add(a.actor_id)
        if self._session is not None:
            pending_raw = await redis_client.lrange(self._session.pending_actions_key, 0, -1)
            for raw in pending_raw:
                a = Action.from_dict(json.loads(raw))
                if a.action_type == ActionType.VOTE:
                    voters.add(a.actor_id)
        return voters


# =============================================================================
# VOTE RESULT ROUND
# =============================================================================


@dataclass
class VoteResultRound(GameRound):
    """Vote-result phase: carry out the lynch and process revenge actions."""

    day_actions: list[Action] = field(default_factory=list)
    lynch_target_id: int | None = None

    def _get_actions_list(self) -> list[Action]:
        return self.day_actions

    def compute_obligations(self) -> None:
        self.obligations = {}
        if self.lynch_target_id is None:
            return
        for player in self.members:
            if player.role is None:
                continue
            if player.id == self.lynch_target_id:
                role_actions = player.role.actions.get(Phase.VOTE_RESULT, [])
                for cfg in role_actions:
                    if cfg.required:
                        self.obligations.setdefault(player.id, []).append(cfg.action_type)

    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        logs: list[dict] = []

        if self.lynch_target_id is not None:
            target = self._get_player(self.lynch_target_id)
            if target:
                target.status = PlayerStatus.DEAD
            logs.append({'actor_id': self.lynch_target_id, 'target_id': None, 'action_type': ActionType.LYNCH.value})

            for a in self.day_actions:
                if a.action_type == ActionType.REVENGE:
                    revenge_target = self._get_player(a.target_id)
                    if revenge_target:
                        revenge_target.status = PlayerStatus.DEAD
                    logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        await self._autosave()
        return logs

    def _to_dict_extra(self) -> dict:
        return {
            'day_actions': [a.to_dict() for a in self.day_actions],
            'lynch_target_id': self.lynch_target_id,
        }

    @staticmethod
    def _extra_kwargs_from_dict(data: dict) -> dict:
        return {
            'day_actions': [Action.from_dict(a) for a in data.get('day_actions', [])],
            'lynch_target_id': data.get('lynch_target_id'),
        }



# =============================================================================
# REGISTRY
# =============================================================================

ROUND_REGISTRY: dict[str, type[GameRound]] = {
    'NightRound': NightRound,
    'DayRound': DayRound,
    'VoteResultRound': VoteResultRound,
}

ROUND_CLASSES: dict[Phase, type[GameRound]] = {
    Phase.NIGHT: NightRound,
    Phase.DAY: DayRound,
    Phase.VOTE_RESULT: VoteResultRound,
}
