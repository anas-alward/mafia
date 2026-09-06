import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from apps.core.redis import redis_client

from .action import Action
from .constants import ActionType, Phase, PlayerStatus, VIGILANTE_AMMO
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

    def _last_actions(self, actions: list[Action]) -> list[Action]:
        """Collapse actions by (actor_id, action_type), keeping the last occurrence."""
        seen: dict[tuple[int, ActionType], Action] = {}
        for a in actions:
            seen[(a.actor_id, a.action_type)] = a
        return list(seen.values())

    @property
    def all_actions(self) -> list[Action]:
        """All actions recorded in this round (for reconnection / logs display)."""
        return self._get_actions_list()

    async def voter_ids_for(self, target_id: int) -> list[int]:
        """IDs of players whose CURRENT vote targets *target_id*.

        Respects revotes: only each actor's last vote in this round counts.
        Reads both the in-memory action list and any pending Redis actions
        (votes live in the pending list until the round resolves).
        """
        actions: list[Action] = list(self._get_actions_list())
        if self._session is not None:
            pending_raw = await redis_client.lrange(
                self._session.pending_actions_key, 0, -1
            )
            for raw in pending_raw:
                actions.append(Action.from_dict(json.loads(raw)))

        latest: dict[int, Action] = {}
        for a in actions:
            if a.action_type == ActionType.VOTE and a.target_id is not None:
                latest[a.actor_id] = a
        return [a.actor_id for a in latest.values() if a.target_id == target_id]

    def _record_dying_revenge(self, target: Player) -> None:
        """Entitle a victim whose role carries vote-result revenge actions
        (e.g. the Mafia King) to act in the following vote-result round."""
        if self._session is None or target.role is None:
            return
        if any(
            cfg.action_type == ActionType.REVENGE
            for cfg in target.role.actions.get(Phase.VOTE_RESULT, [])
        ):
            self._session.pending_dying_revenge.append(target.id)

    def _shoot_uses(self, player_id: int) -> int:
        """Total SHOOT actions the player has spent across the whole game."""
        uses = 0
        if self._session is not None:
            for r in self._session.rounds:
                uses += sum(
                    1
                    for a in r._get_actions_list()
                    if a.actor_id == player_id
                    and a.action_type == ActionType.SHOOT
                )
        return uses

    async def requirement_summary(self) -> list[dict]:
        """Anonymous per-action-type completion status for this phase.

        Returns [{'action_type': <str>, 'done': <bool>}] — no player
        identities. Clients show what is done/pending without learning
        who must act.
        """
        actions: list[Action] = list(self._get_actions_list())
        if self._session is not None:
            pending_raw = await redis_client.lrange(
                self._session.pending_actions_key, 0, -1
            )
            for raw in pending_raw:
                actions.append(Action.from_dict(json.loads(raw)))
        submitted = {(a.actor_id, a.action_type) for a in actions}

        summary: list[dict] = []
        for at in ActionType:
            obligated = [
                pid for pid, types in self.obligations.items() if at in types
            ]
            if not obligated:
                continue
            done = all((pid, at) in submitted for pid in obligated)
            summary.append({'action_type': at.value, 'done': done})
        return summary

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

    async def has_submitted_action(self, player_id: int, action_type: ActionType) -> bool:
        """True when *player_id* has already recorded *action_type* this round.

        Checks both the in-memory action list and any pending actions still in
        Redis (submitted via :meth:`add_action` but not yet merged).
        """
        for a in self._get_actions_list():
            if a.actor_id == player_id and a.action_type == action_type:
                return True

        if self._session is not None:
            pending_raw = await redis_client.lrange(self._session.pending_actions_key, 0, -1)
            for raw in pending_raw:
                a = Action.from_dict(json.loads(raw))
                if a.actor_id == player_id and a.action_type == action_type:
                    return True

        return False

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
            member_map = {p.id: p for p in self.members}
            for sp in self._session.players:
                if sp.id in member_map:
                    sp.status = member_map[sp.id].status
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
    """Night phase: mafia kills, heals, investigations, silences, etc."""

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
        actions = self._last_actions(self.night_actions)
        designated_killer = next(
            (pid for pid, types in self.obligations.items() if ActionType.KILL in types),
            None,
        )
        logs: list[dict] = []
        healed: set[int] = set()

        # 1. SILENCE — logs only; no longer blocks any night action.
        for a in actions:
            if a.action_type == ActionType.SILENCE:
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 2. HEAL
        for a in actions:
            if a.action_type == ActionType.HEAL:
                healed.add(a.target_id)
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 3. OFFENSIVE ACTIONS (KILL)
        for a in actions:
            if a.action_type == ActionType.KILL:
                if a.actor_id != designated_killer:
                    continue
                if a.target_id in healed:
                    logs.append({'target_id': a.target_id, 'action_type': a.action_type.value, 'result': 'healed'})
                else:
                    target = self._get_player(a.target_id)
                    if target:
                        target.status = PlayerStatus.DEAD
                        self._record_dying_revenge(target)
                    logs.append({
                        'target_id': a.target_id,
                        'action_type': a.action_type.value,
                        # Role reveal — dead players' cards are shown to everyone.
                        'role_code': target.role.code if target and target.role else None,
                        'role_name': target.role.name if target and target.role else None,
                    })

        # 4. DETECT — never logged. The detective receives their result
        # privately via detect_result; broadcasting it would reveal the
        # investigation to everyone.
        await self._autosave()
        return logs

    def silenced_target_ids(self) -> list[int]:
        actions = self._last_actions(self.night_actions)
        return [
            a.target_id for a in actions
            if a.action_type == ActionType.SILENCE
            and a.target_id in self.alive_player_ids()
        ]

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

    def _vigilante_id(self) -> int | None:
        """The alive player whose role carries an optional day shot."""
        for p in self.members:
            if p.status != PlayerStatus.ALIVE or p.role is None:
                continue
            day_actions = p.role.actions.get(Phase.DAY, [])
            if any(
                cfg.action_type == ActionType.SHOOT and not cfg.required
                for cfg in day_actions
            ):
                return p.id
        return None

    def get_required_actions_for_player(self, player_id: int) -> list[dict]:
        result = super().get_required_actions_for_player(player_id)
        # The vigilante's optional day shot, while ammo lasts.
        if (
            player_id == self._vigilante_id()
            and self._shoot_uses(player_id) < VIGILANTE_AMMO
        ):
            result.append({
                'action_type': ActionType.SHOOT.value,
                'target_options': [
                    pid for pid in self.alive_player_ids() if pid != player_id
                ],
            })
        return result

    async def is_player_done(self, player_id: int) -> bool:
        # A day shot replaces the vote for the vigilante.
        if await super().is_player_done(player_id):
            return True
        return await self.has_submitted_action(player_id, ActionType.SHOOT)

    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        actions = self._last_actions(self.day_actions)
        logs: list[dict] = []
        actor_votes: dict[int, int] = {}

        for a in actions:
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

        # Day shots (vigilante): the victim dies with a public role reveal.
        # Shooting a Town player eliminates the vigilante as well. Shooting
        # a role with vote-result revenge actions entitles that victim.
        for a in actions:
            if a.action_type != ActionType.SHOOT:
                continue
            target = self._get_player(a.target_id)
            if target is None or target.status != PlayerStatus.ALIVE:
                continue
            target.status = PlayerStatus.DEAD
            logs.append({
                'actor_id': a.actor_id,
                'target_id': a.target_id,
                'action_type': a.action_type.value,
                'role_code': target.role.code if target.role else None,
                'role_name': target.role.name if target.role else None,
            })
            self._record_dying_revenge(target)
            # Town penalty: shooting a Town player costs the vigilante
            # their own life; shooting mafia is safe.
            actor = self._get_player(a.actor_id)
            if (
                actor is not None
                and actor.status == PlayerStatus.ALIVE
                and target.role is not None
                and target.role.role_type.value == 'town'
                and actor.role is not None
                and actor.role.role_type.value == 'town'
                and actor.id != target.id
            ):
                actor.status = PlayerStatus.DEAD
                logs.append({
                    'actor_id': None,
                    'target_id': a.actor_id,
                    'action_type': 'died',
                })

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
        """Return the set of actor IDs who have voted this round.

        A vigilante day shot replaces the vote, so shoot-actors count too.
        """
        voters: set[int] = set()
        for a in self.day_actions:
            if a.action_type == ActionType.VOTE:
                voters.add(a.actor_id)
        if self._session is not None:
            pending_raw = await redis_client.lrange(self._session.pending_actions_key, 0, -1)
            for raw in pending_raw:
                a = Action.from_dict(json.loads(raw))
                if a.action_type in (ActionType.VOTE, ActionType.SHOOT):
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
        # Dying-revenge entitlements (e.g. the Mafia King killed at night)
        # act in this round, even though they are already dead.
        dying_ids = self._session.pending_dying_revenge if self._session else []
        for player in self.members:
            if player.role is None:
                continue
            if player.id == self.lynch_target_id:
                role_actions = player.role.actions.get(Phase.VOTE_RESULT, [])
                for cfg in role_actions:
                    if cfg.required:
                        self.obligations.setdefault(player.id, []).append(cfg.action_type)
            elif player.id in dying_ids:
                self.obligations.setdefault(player.id, []).append(ActionType.REVENGE)

    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        actions = self._last_actions(self.day_actions)
        logs: list[dict] = []

        if self.lynch_target_id is not None:
            target = self._get_player(self.lynch_target_id)
            if target:
                target.status = PlayerStatus.DEAD
            logs.append({
                'actor_id': self.lynch_target_id,
                'target_id': None,
                'action_type': ActionType.LYNCH.value,
                # Role reveal — the lynched player's card is shown to everyone.
                'role_code': target.role.code if target and target.role else None,
                'role_name': target.role.name if target and target.role else None,
            })

        for a in actions:
            if a.action_type == ActionType.REVENGE:
                revenge_target = self._get_player(a.target_id)
                if revenge_target:
                    revenge_target.status = PlayerStatus.DEAD
                logs.append({
                    'actor_id': a.actor_id,
                    'target_id': a.target_id,
                    'action_type': a.action_type.value,
                    # Role reveal — dead players' cards are shown to everyone.
                    'role_code': revenge_target.role.code if revenge_target and revenge_target.role else None,
                    'role_name': revenge_target.role.name if revenge_target and revenge_target.role else None,
                })

        # The dying-revenge entitlement is consumed this round.
        if self._session is not None:
            self._session.pending_dying_revenge = []

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
