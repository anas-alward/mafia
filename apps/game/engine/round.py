import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from apps.core.redis import redis_client

from .action import Action
from .constants import ActionType, Phase, PlayerStatus
from .player import Player

if TYPE_CHECKING:
    from .session import GameSession

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
            _session=session,
        )
