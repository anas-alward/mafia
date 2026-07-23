import json
from dataclasses import dataclass, field

from apps.core.redis import redis_client

from .constants import Phase
from .player import Player
from .roles.distributor import RoleDistributor
from .round import ROUND_CLASSES, GameRound



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

    @property
    def pending_actions_key(self) -> str:
        return f'{self.key_prefix}{self.room_id}:pending_actions'

    @classmethod
    def _key_for(cls, room_id: str, key_prefix: str = 'mafia:session:') -> str:
        return f'{key_prefix}{room_id}'

    # -------------------------
    # ROUND MANAGEMENT
    # -------------------------
    async def new_round(self, phase: Phase = Phase.NIGHT, lynch_target_id: int | None = None) -> GameRound:
        round_cls = ROUND_CLASSES[phase]
        kwargs: dict = {
            'round_number': len(self.rounds) + 1,
            'members': self.players.copy(),
            'phase': phase,
            '_session': self,
        }
        if lynch_target_id is not None:
            kwargs['lynch_target_id'] = lynch_target_id
        round_ = round_cls(**kwargs)
        round_.compute_obligations()
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
        from .player import Player
        session = cls(
            id=data['id'],
            room_id=data['room_id'],
            players=[Player.from_dict(p) for p in data['players']],
            key_prefix=key_prefix,
        )
        session.rounds = [GameRound.from_dict(r, session=session) for r in data['rounds']]
        for r in session.rounds:
            r.compute_obligations()
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
        await redis_client.delete(self.redis_key, self.pending_actions_key)

    @classmethod
    async def flush_room(cls, room_id: str, key_prefix: str = 'mafia:session:') -> None:
        """Delete a room's persisted session without needing an instance."""
        await redis_client.delete(
            cls._key_for(room_id, key_prefix),
            f'{key_prefix}{room_id}:pending_actions',
        )

    @classmethod
    async def start_new(cls, id: str, room_id: str, player_ids: list[int]) -> GameSession:
        players = RoleDistributor.distribute(player_ids=player_ids)
        session = cls(id=id, room_id=room_id, players=players)
        await session.save()
        return session


