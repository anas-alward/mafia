import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from apps.core.redis import redis_client
from apps.game.roles import ROLES  # ROLES = [TownDoctor, TownCop, ...]

# -----------------------------
# ROLE REGISTRY (name -> class)
# -----------------------------
# Roles are plain classes with no instance state (role_type, name, description
# are class attributes), so persistence only needs the class *name* — the
# class itself is looked up from this registry on load.
ROLE_REGISTRY: dict[str, type[Any]] = {role.__name__: role for role in ROLES}


class PlayerStatus(StrEnum):
    ALIVE = 'alive'
    DEAD = 'dead'


class Phase(StrEnum):
    DAY = 'day'
    NIGHT = 'night'


class ActionType(StrEnum):
    KILL = 'kill'
    REVENGE = 'revenge'
    VOTE = 'vote'
    HEAL = 'heal'
    DETECT = 'detect'
    SHOOT = 'shoot'
    ROLEBLOCK = 'roleblock'


# -----------------------------
# ACTION MODEL
# -----------------------------


@dataclass
class Action:
    actor_id: int
    target_id: int | None
    action_type: ActionType

    def to_dict(self) -> dict:
        return {
            'actor_id': self.actor_id,
            'target_id': self.target_id,
            'action_type': self.action_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Action:
        return cls(
            actor_id=data['actor_id'],
            target_id=data['target_id'],
            action_type=ActionType(data['action_type']),
        )


# -----------------------------
# PLAYER MODEL
# -----------------------------

RoleClass = type[Any]


@dataclass
class Player:
    id: int
    status: PlayerStatus = PlayerStatus.ALIVE
    role: RoleClass = None

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'status': self.status.value,
            'role': self.role.__name__ if self.role else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Player:
        role_name = data.get('role')
        return cls(
            id=data['id'],
            status=PlayerStatus(data['status']),
            role=ROLE_REGISTRY.get(role_name) if role_name else None,
        )


# -----------------------------
# GAME ROUND
# -----------------------------


@dataclass
class GameRound:
    round_number: int
    members: list[Player] = field(default_factory=list)

    night_actions: list[Action] = field(default_factory=list)
    day_actions: list[Action] = field(default_factory=list)

    phase: Phase = Phase.NIGHT

    # Back-reference to the owning session, set by GameSession.new_round().
    # Excluded from serialization (it would recurse); needed so add_action /
    # resolve can trigger an autosave without the caller having to do it.
    _session: GameSession | None = field(default=None, repr=False, compare=False)

    # -------------------------
    # ACTION ENTRY
    # -------------------------
    async def add_action(self, action: Action):
        if self.phase == Phase.NIGHT:
            self.night_actions.append(action)
        else:
            self.day_actions.append(action)
        await self._autosave()

    # -------------------------
    # MAIN RESOLVE ENTRY
    # -------------------------
    async def resolve(self):
        if self.phase == Phase.NIGHT:
            logs = self._resolve_night()
        else:
            logs = self._resolve_day()
        await self._autosave()
        return logs

    # -------------------------
    # NIGHT RESOLUTION (sync helper, no Redis calls inside)
    # -------------------------
    def _resolve_night(self):
        logs = []

        blocked = set()
        healed = set()

        # 1. ROLEBLOCK
        for a in self.night_actions:
            if a.action_type == ActionType.ROLEBLOCK:
                blocked.add(a.target_id)
                logs.append(f'{a.target_id} was roleblocked')

        # 2. HEAL
        for a in self.night_actions:
            if a.action_type == ActionType.HEAL:
                if a.actor_id in blocked:
                    continue
                healed.add(a.target_id)
                logs.append(f'{a.target_id} is protected')

        # 3. OFFENSIVE ACTIONS (KILL / SHOOT)
        for a in self.night_actions:
            if a.action_type in (ActionType.KILL, ActionType.SHOOT):
                if a.actor_id in blocked:
                    continue

                if a.target_id in healed:
                    logs.append(f'{a.target_id} survived attack')
                else:
                    target = self._get_player(a.target_id)
                    if target:
                        target.status = PlayerStatus.DEAD
                    logs.append(f'{a.target_id} died')

        # 4. DETECT
        for a in self.night_actions:
            if a.action_type == ActionType.DETECT:
                if a.actor_id in blocked:
                    continue
                logs.append(f'{a.actor_id} investigated {a.target_id}')

        return logs

    # -------------------------
    # DAY RESOLUTION (sync helper, no Redis calls inside)
    # -------------------------
    def _resolve_day(self):
        logs = []
        votes = {}

        for a in self.day_actions:
            if a.action_type == ActionType.VOTE:
                if a.target_id is None:
                    continue
                votes[a.target_id] = votes.get(a.target_id, 0) + 1
                logs.append(f'{a.actor_id} voted {a.target_id}')

        if votes:
            lynch = max(votes, key=votes.get)
            target = self._get_player(lynch)
            if target:
                target.status = PlayerStatus.DEAD
            logs.append(f'{lynch} was lynched')

        return logs

    # -------------------------
    # HELPER
    # -------------------------
    def _get_player(self, player_id: int) -> Player | None:
        for p in self.members:
            if p.id == player_id:
                return p
        return None

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
        }

    @classmethod
    def from_dict(cls, data: dict, session: 'GameSession | None' = None) -> 'GameRound':
        return cls(
            round_number=data['round_number'],
            members=[Player.from_dict(p) for p in data['members']],
            night_actions=[Action.from_dict(a) for a in data['night_actions']],
            day_actions=[Action.from_dict(a) for a in data['day_actions']],
            phase=Phase(data['phase']),
            _session=session,
        )


# -----------------------------
# GAME SESSION  (a.k.a. RoomSession)
# -----------------------------


@dataclass
class GameSession:
    """
    Persists the full game state for one room as a single JSON blob in Redis,
    under f"{key_prefix}{room_id}". Every mutation (add_action, resolve,
    new_round) autosaves — callers never need to call save() themselves,
    though it's exposed directly in case it's ever needed.
    """

    id: str
    room_id: str

    rounds: list[GameRound] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)

    key_prefix: str = 'mafia:session:'

    # -------------------------
    # KEY HELPERS
    # -------------------------
    @property
    def redis_key(self) -> str:
        return f'{self.key_prefix}{self.room_id}'

    @classmethod
    def _key_for(cls, room_id: str, key_prefix: str = 'mafia:session:') -> str:
        return f'{key_prefix}{room_id}'

    # -------------------------
    # ROUND MANAGEMENT
    # -------------------------
    async def new_round(self, phase: Phase = Phase.NIGHT) -> GameRound:
        round_ = GameRound(
            round_number=len(self.rounds) + 1,
            members=self.players.copy(),
            phase=phase,
            _session=self,
        )
        self.rounds.append(round_)
        await self.save()
        return round_

    def current_round(self) -> GameRound:
        return self.rounds[-1]

    # -------------------------
    # SERIALIZATION
    # -------------------------
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'room_id': self.room_id,
            'players': [p.to_dict() for p in self.players],
            'rounds': [r.to_dict() for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, data: dict, key_prefix: str = 'mafia:session:') -> GameSession:
        session = cls(
            id=data['id'],
            room_id=data['room_id'],
            players=[Player.from_dict(p) for p in data['players']],
            key_prefix=key_prefix,
        )
        session.rounds = [GameRound.from_dict(r, session=session) for r in data['rounds']]
        return session

    # -------------------------
    # PERSISTENCE
    # -------------------------
    async def save(self) -> None:
        payload = json.dumps(self.to_dict())
        await redis_client.set(self.redis_key, payload)

    @classmethod
    async def load(cls, room_id: str, key_prefix: str = 'mafia:session:') -> GameSession | None:
        key = cls._key_for(room_id, key_prefix)
        raw = await redis_client.get(key)
        if raw is None:
            return None
        return cls.from_dict(json.loads(raw), key_prefix=key_prefix)

    async def flush(self) -> None:
        """Delete this session's persisted state from Redis."""
        await redis_client.delete(self.redis_key)

    @classmethod
    async def flush_room(cls, room_id: str, key_prefix: str = 'mafia:session:') -> None:
        """Delete a room's persisted session without needing an instance."""
        await redis_client.delete(cls._key_for(room_id, key_prefix))

    @classmethod
    async def start_new(cls, id: str, room_id: str, player_ids: list[int]) -> GameSession:
        from .distributor import RoleDistributor

        players = RoleDistributor.distribute(player_ids=player_ids)
        session = cls(id=id, room_id=room_id, players=players)
        await session.save()
        return session


