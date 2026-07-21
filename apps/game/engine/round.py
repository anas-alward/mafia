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

@dataclass
class GameRound:
    round_number: int
    members: list[Player] = field(default_factory=list)

    night_actions: list[Action] = field(default_factory=list)
    day_actions: list[Action] = field(default_factory=list)

    phase: Phase = Phase.NIGHT

    # The player voted to be lynched this round (set during DAY resolution,
    # carried out during VOTE_RESULT resolution).
    lynch_target_id: int | None = None

    # Which actions each player MUST submit this phase (computed at round start).
    # Keyed by player_id → list of required ActionTypes.  Computed, not persisted.
    obligations: dict[int, list[ActionType]] = field(default_factory=dict)

    # Grace timer — set when all required night actions are in and the
    # 5-second optional-action window begins.  Persisted so it survives
    # server restarts during the grace window.
    grace_started_at: float | None = field(default=None, repr=False)

    # Back-reference to the owning session, set by GameSession.new_round().
    # Excluded from serialization (it would recurse); needed so add_action /
    # resolve can trigger an autosave without the caller having to do it.
    _session: GameSession | None = field(default=None, repr=False, compare=False)

    # -------------------------
    # ACTION ENTRY
    # -------------------------
    async def add_action(self, action: Action) -> None:
        """Atomically push action to Redis to avoid read-modify-write races.

        Multiple players can submit actions concurrently — each RPUSH is
        atomic so no action is lost.  Pending actions are merged into the
        in-memory round inside resolve() before resolution runs.
        """
        if self._session is None:
            # Non-persisted round (tests, etc.) — fall back to in-memory.
            if self.phase == Phase.NIGHT:
                self.night_actions.append(action)
            else:
                self.day_actions.append(action)
            return
        payload = json.dumps(action.to_dict())
        await redis_client.rpush(self._session.pending_actions_key, payload)

    # -------------------------
    # MAIN RESOLVE ENTRY
    # -------------------------
    async def resolve(self):
        # Merge any pending actions that were atomically pushed to Redis
        # by concurrent add_action calls before we resolve.
        if self._session is not None:
            pending_key = self._session.pending_actions_key
            pending_raw = await redis_client.lrange(pending_key, 0, -1)
            for raw in pending_raw:
                action = Action.from_dict(json.loads(raw))
                if self.phase == Phase.NIGHT:
                    self.night_actions.append(action)
                else:
                    self.day_actions.append(action)
            if pending_raw:
                await redis_client.delete(pending_key)

        if self.phase == Phase.NIGHT:
            logs = self._resolve_night()
        elif self.phase == Phase.DAY:
            logs = self._resolve_day()
        else:
            logs = self._resolve_vote_result()
        await self._autosave()
        return logs

    # -------------------------
    # NIGHT RESOLUTION (sync helper, no Redis calls inside)
    # -------------------------
    def _resolve_night(self):
        logs: list[dict] = []

        blocked: set[int] = set()
        healed: set[int] = set()

        # 1. ROLEBLOCK
        for a in self.night_actions:
            if a.action_type == ActionType.ROLEBLOCK:
                blocked.add(a.target_id)
                logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        # 2. HEAL
        for a in self.night_actions:
            if a.action_type == ActionType.HEAL:
                if a.actor_id in blocked:
                    continue
                healed.add(a.target_id)
                logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        # 3. OFFENSIVE ACTIONS (KILL / SHOOT)
        for a in self.night_actions:
            if a.action_type in (ActionType.KILL, ActionType.SHOOT):
                if a.actor_id in blocked:
                    continue

                if a.target_id in healed:
                    logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value, 'result': 'healed'})
                else:
                    target = self._get_player(a.target_id)
                    if target:
                        target.status = PlayerStatus.DEAD
                    logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        # 4. DETECT
        for a in self.night_actions:
            if a.action_type == ActionType.DETECT:
                if a.actor_id in blocked:
                    continue
                logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        return logs

    # -------------------------
    # DAY RESOLUTION (sync helper, no Redis calls inside)
    # -------------------------
    def _resolve_day(self):
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

        return logs

    # -------------------------
    # VOTE_RESULT RESOLUTION (sync helper, no Redis calls inside)
    # -------------------------
    def _resolve_vote_result(self):
        """Carry out the lynch and process any revenge actions."""
        logs: list[dict] = []

        if self.lynch_target_id is None:
            return logs

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

        return logs

    # -------------------------
    # HELPER
    # -------------------------
    def _get_player(self, player_id: int) -> Player | None:
        for p in self.members:
            if p.id == player_id:
                return p
        return None

    def alive_player_ids(self) -> set[int]:
        return {p.id for p in self.members if p.status == PlayerStatus.ALIVE}

    # -------------------------
    # OBLIGATIONS TRACKING
    # -------------------------
    def compute_obligations(self) -> None:
        """Compute which players must submit which actions this phase.

        Mafia KILL uses a priority chain: only the highest-priority alive
        mafia gets KILL as a required obligation.
        """
        self.obligations = {}
        phase = self.phase
        mafia_kill_candidates: list[tuple[int, int]] = []

        for player in self.members:
            if player.role is None:
                continue

            # VOTE_RESULT: only the lynched player may have obligations.
            if phase == Phase.VOTE_RESULT:
                if player.id == self.lynch_target_id:
                    role_actions = player.role.actions.get(phase, [])
                    for cfg in role_actions:
                        if cfg.required:
                            self.obligations.setdefault(player.id, []).append(cfg.action_type)
                continue

            # DAY: all alive players must vote.
            if phase == Phase.DAY:
                if player.status == PlayerStatus.ALIVE:
                    self.obligations[player.id] = [ActionType.VOTE]
                continue

            # NIGHT: alive players with night actions.
            if player.status == PlayerStatus.DEAD:
                continue

            role_actions = player.role.actions.get(phase, [])
            for cfg in role_actions:
                if not cfg.required:
                    continue
                if cfg.action_type == ActionType.KILL and cfg.priority is not None:
                    mafia_kill_candidates.append((cfg.priority, player.id))
                else:
                    self.obligations.setdefault(player.id, []).append(cfg.action_type)

        # Resolve mafia KILL priority chain.
        if mafia_kill_candidates:
            mafia_kill_candidates.sort(key=lambda x: x[0])
            chosen_id = mafia_kill_candidates[0][1]
            self.obligations.setdefault(chosen_id, []).append(ActionType.KILL)

    # -------------------------
    # GRACE TIMER
    # -------------------------
    def start_grace(self) -> None:
        """Begin the grace period for optional actions."""
        self.grace_started_at = time.time()

    def is_grace_expired(self) -> bool:
        """True if grace period has elapsed since start_grace was called."""
        if self.grace_started_at is None:
            return False
        return (time.time() - self.grace_started_at) >= GRACE_SECONDS

    # -------------------------
    # TARGET OPTIONS
    # -------------------------
    def get_required_actions_for_player(self, player_id: int) -> list[dict]:
        """Return the list of required actions with target_options for a player.

        Each entry: {'action_type': str, 'target_options': list[int]}
        """
        required_types = self.obligations.get(player_id, [])
        if not required_types:
            return []

        result = []
        for at in required_types:
            result.append({
                'action_type': at.value,
                'target_options': self._target_options_for(player_id, at),
            })
        return result

    def _target_options_for(self, actor_id: int, action_type: ActionType) -> list[int]:
        """Return valid target player IDs for a given action type."""
        if action_type == ActionType.REVENGE:
            # Can target any alive player (the Bomb takes someone with them).
            return [p.id for p in self.members if p.status == PlayerStatus.ALIVE]
        if action_type == ActionType.KILL:
            # Mafia cannot target other mafia.
            actor = self._get_player(actor_id)
            if actor and actor.role:
                return [
                    p.id for p in self.members
                    if p.status == PlayerStatus.ALIVE
                    and (p.role is None or p.role.role_type != actor.role.role_type)
                ]
        # Default: any alive player.
        return [p.id for p in self.members if p.status == PlayerStatus.ALIVE]

    async def is_player_done(self, player_id: int) -> bool:
        """True when this player has submitted all their required actions.

        Merges pending Redis actions with in-memory actions, following the
        same pattern as :meth:`voter_ids`, so this check is accurate even
        before :meth:`resolve` runs.
        """
        required = self.obligations.get(player_id, [])
        if not required:
            return True

        submitted: set[ActionType] = set()
        actions_list = self.night_actions if self.phase == Phase.NIGHT else self.day_actions
        for a in actions_list:
            if a.actor_id == player_id:
                submitted.add(a.action_type)

        # Also check pending Redis actions that haven't been merged yet.
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

    async def voter_ids(self) -> set[int]:
        """Return the set of actor IDs who have voted this round.

        Merges pending Redis actions with in-memory actions so the check
        is accurate even before resolve() runs.
        """
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

    async def _autosave(self):
        if self._session is not None:
            await self._session.save()

    # -------------------------
    # SERIALIZATION
    # -------------------------
    def to_dict(self) -> dict:
        return {
            'round_number': self.round_number,
            'members': [p.to_dict() for p in self.members],
            'night_actions': [a.to_dict() for a in self.night_actions],
            'day_actions': [a.to_dict() for a in self.day_actions],
            'phase': self.phase.value,
            'lynch_target_id': self.lynch_target_id,
            'grace_started_at': self.grace_started_at,
        }

    @classmethod
    def from_dict(cls, data: dict, session: GameSession) -> GameRound:
        return cls(
            round_number=data['round_number'],
            members=[Player.from_dict(p) for p in data['members']],
            night_actions=[Action.from_dict(a) for a in data['night_actions']],
            day_actions=[Action.from_dict(a) for a in data['day_actions']],
            phase=Phase(data['phase']),
            lynch_target_id=data.get('lynch_target_id'),
            grace_started_at=data.get('grace_started_at'),
            _session=session,
        )
