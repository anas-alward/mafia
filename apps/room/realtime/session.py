from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Self

from redis.asyncio import Redis

from apps.accounts.models import User
from apps.core.redis import redis_client

from apps.room.models import Room


class MemberStatus(StrEnum):
    LIVE = "live"
    DISCONNECTED = "disconnected"
    AWAY = "away"
    MUTED = "muted"


@dataclass(slots=True)
class RoomMember:
    user_id: int
    name: str
    status: MemberStatus = MemberStatus.LIVE
    joined_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    role: str = "participant"  # participant, co-host
    is_screensharing: bool = False
    is_hand_raised: bool = False

    def to_dict(self) -> dict[str, str]:
        """Serialize to Redis-compatible string dict."""
        return {
            "user_id": str(self.user_id),
            "name": self.name,
            "status": self.status.value,
            "joined_at": self.joined_at,
            "role": self.role,
            "is_screensharing": str(self.is_screensharing),
            "is_hand_raised": str(self.is_hand_raised),
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Self:
        """Deserialize from Redis hash."""
        return cls(
            user_id=int(data["user_id"]),
            name=data["name"],
            status=MemberStatus(data.get("status", "live")),
            joined_at=data.get("joined_at", datetime.utcnow().isoformat()),
            role=data.get("role", "participant"),
            is_screensharing=data.get("is_screensharing", "False") == "True",
            is_hand_raised=data.get("is_hand_raised", "False") == "True",
        )

    def disconnect(self) -> None:
        self.status = MemberStatus.DISCONNECTED

    def reconnect(self) -> None:
        self.status = MemberStatus.LIVE

    def raise_hand(self) -> None:
        self.is_hand_raised = True

    def lower_hand(self) -> None:
        self.is_hand_raised = False

    def start_screenshare(self) -> None:
        self.is_screensharing = True

    def stop_screenshare(self) -> None:
        self.is_screensharing = False

    @property
    def is_disconnected(self):
        return self.status == MemberStatus

@dataclass(slots=True)
class RoomSession:
    code: str
    cache: Redis = redis_client

    # Room data
    _id: int | None = field(default=None, init=False, repr=False)
    _name: str | None = field(default=None, init=False, repr=False)
    _original_host_id: int | None = field(default=None, init=False, repr=False)
    _host_id: int | None = field(default=None, init=False, repr=False)
    _meeting_id: str | None = field(default=None, init=False, repr=False)
    _exists: bool = field(default=False, init=False, repr=False)

    # Cached sets
    _members: set[int] = field(default_factory=set, init=False, repr=False)
    _waiting: set[int] = field(default_factory=set, init=False, repr=False)

    # -------------------------
    # Properties
    # -------------------------
    @property
    def id(self) -> int | None:
        return self._id

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def original_host_id(self) -> int | None:
        """The user who created the room. Never changes."""
        return self._original_host_id

    @property
    def host_id(self) -> int | None:
        """Current active host. May differ from original_host_id if switched."""
        return self._host_id

    @property
    def meeting_id(self) -> str | None:
        return self._meeting_id

    @property
    def members(self) -> set[int]:
        return self._members.copy()

    @property
    def waiting(self) -> set[int]:
        return self._waiting.copy()

    @property
    def room_key(self) -> str:
        return f'room:{self.code}'

    @property
    def members_key(self) -> str:
        return f'room:{self.code}:members'

    @property
    def waiting_key(self) -> str:
        return f'room:{self.code}:waiting'

    def member_key(self, user_id: int) -> str:
        return f'room:{self.code}:member:{user_id}'

    def waiting_member_key(self, user_id: int) -> str:
        return f'room:{self.code}:waiting:{user_id}'

    # -------------------------
    # Truthiness
    # -------------------------
    def __bool__(self) -> bool:
        return self._exists and self._id is not None and self._name is not None

    # -------------------------
    # Host checks
    # -------------------------
    def is_host(self, user) -> bool:
        """Check if user is the CURRENT active host."""
        return user.id == self._host_id

    def is_original_host(self, user) -> bool:
        """Check if user is the original creator of the room."""
        return user.id == self._original_host_id

    def is_effective_host(self, user) -> bool:
        """User is either original or current switched host."""
        return user.id == self._host_id

    def host_is_switched(self) -> bool:
        """Returns True if host was temporarily switched from original."""
        return self._host_id != self._original_host_id

    # -------------------------
    # Async factory
    # -------------------------
    @classmethod
    async def from_code(cls, code: str) -> 'RoomSession':
        session = cls(code=code)
        await session._load()
        return session

    async def _load(self) -> None:
        cached = await self.cache.hgetall(self.room_key)

        if cached:
            self._populate_from_cache(cached)
            self._exists = True
        else:
            try:
                room = await Room.objects.aget(code=self.code)
            except Room.DoesNotExist:
                self._exists = False
                return

            data = self._room_to_dict(room)
            await self._store_room(data)
            self._populate_from_dict(data)
            self._exists = True

        await self._refresh_members()
        await self._refresh_waiting()

    async def _refresh_members(self) -> None:
        member_ids = await self.cache.smembers(self.members_key)
        self._members = {int(m) for m in member_ids}

    async def _refresh_waiting(self) -> None:
        waiting_ids = await self.cache.smembers(self.waiting_key)
        self._waiting = {int(m) for m in waiting_ids}

    async def refresh(self) -> None:
        await self._refresh_members()
        await self._refresh_waiting()

    # -------------------------
    # Store / Invalidate
    # -------------------------
    async def store(self, room: Room) -> None:
        data = self._room_to_dict(room)
        await self._store_room(data)
        self._populate_from_dict(data)
        self._exists = True

    async def invalidate(self) -> None:
        pipe = self.cache.pipeline()
        pipe.delete(self.room_key)
        pipe.delete(self.members_key)
        pipe.delete(self.waiting_key)
        await pipe.execute()

        self._exists = False
        self._id = None
        self._name = None
        self._original_host_id = None
        self._host_id = None
        self._members = set()
        self._waiting = set()

    async def _store_room(self, data: dict[str, str]) -> None:
        await self.cache.hset(self.room_key, mapping=data)
        await self.cache.expire(self.room_key, 3600)

    # -------------------------
    # Population helpers
    # -------------------------
    def _populate_from_cache(self, cached: dict[str, str]) -> None:
        self._id = int(cached['id'])
        self._name = cached['name']
        self._original_host_id = int(cached['original_host_id'])
        # host_id may not exist in old data — fallback to original_host_id
        self._host_id = int(cached.get('host_id', cached['original_host_id']))
        self._meeting_id = cached.get('meeting_id', '')

    def _populate_from_dict(self, data: dict[str, str]) -> None:
        self._id = int(data['id'])
        self._name = data['name']
        self._original_host_id = int(data['original_host_id'])
        self._host_id = int(data.get('host_id', data['original_host_id']))
        self._meeting_id = data.get('meeting_id', '')

    @staticmethod
    def _room_to_dict(room: Room) -> dict[str, str]:
        return {
            'id': str(room.id),
            'original_host_id': str(room.host_id),  # creator is original
            'host_id': str(room.host_id),            # starts same as original
            'name': room.name,
            'code': room.code,
            'meeting_id': room.meeting_id or '',
        }

    # -------------------------
    # HOST SWITCHING (the new stuff!)
    # -------------------------
    async def switch_host(self, new_host_id: int) -> None:
        """
        Temporarily switch host to another user (e.g., original host disconnected).
        The new host must be an approved member of the room.
        """
        if not self.is_member(new_host_id):
            raise ValueError("New host must be an approved member of the room")

        if new_host_id == self._host_id:
            return  # Already host, nothing to do

        # Update Redis
        await self.cache.hset(self.room_key, 'host_id', str(new_host_id))

        # Update local state
        self._host_id = new_host_id

    async def revert_host(self) -> None:
        """
        Revert host back to the original creator.
        Call this when original host reconnects.
        """
        if self._host_id == self._original_host_id:
            return  # Already original host

        await self.cache.hset(self.room_key, 'host_id', str(self._original_host_id))
        self._host_id = self._original_host_id

    async def set_host(self, user_id: int | None = None) -> None:
        """
        Set host explicitly. If user_id is None, reverts to original host.
        """
        if user_id is None:
            await self.revert_host()
            return

        await self.switch_host(user_id)

    # -------------------------
    # MEMBERS
    # -------------------------
    async def remove_member(self, user_id: int) -> None:
        # If removing current host, revert to original first
        if user_id == self._host_id and user_id != self._original_host_id:
            await self.revert_host()
        elif user_id == self._host_id:
            # Can't remove original host without assigning new one first
            raise ValueError("Cannot remove original host. Switch host first.")

        pipe = self.cache.pipeline()
        pipe.srem(self.members_key, str(user_id))
        pipe.delete(self.member_key(user_id))
        await pipe.execute()

        self._members.discard(user_id)

    # -------------------------
    # WAITING
    # -------------------------
    async def request_join(self, user: User) -> None:
        if self.is_member(user.pk):
            raise ValueError("User is already a member")
        if self.is_waiting(user.pk):
            raise ValueError("User already has a pending request")

        data = {
            'user_id': str(user.pk),
            'name': user.get_full_name(),
            'requested_at': datetime.utcnow().isoformat(),
        }

        pipe = self.cache.pipeline()
        pipe.sadd(self.waiting_key, str(user.pk))
        pipe.hset(self.waiting_member_key(user.pk), mapping=data)
        await pipe.execute()

        self._waiting.add(user.pk)

    async def approve_join(self, user_id: int, member_data: dict | None = None) -> None:
        if not self.is_waiting(user_id):
            raise ValueError("User is not in waiting list")

        pipe = self.cache.pipeline()
        pipe.srem(self.waiting_key, str(user_id))
        pipe.delete(self.waiting_member_key(user_id))
        pipe.sadd(self.members_key, str(user_id))
        if member_data:
            pipe.hset(self.member_key(user_id), mapping=member_data)
        await pipe.execute()

        self._waiting.discard(user_id)
        self._members.add(user_id)

    async def reject_join(self, user_id: int) -> None:
        pipe = self.cache.pipeline()
        pipe.srem(self.waiting_key, str(user_id))
        pipe.delete(self.waiting_member_key(user_id))
        await pipe.execute()

        self._waiting.discard(user_id)

    async def cancel_join_request(self, user_id: int) -> None:
        if not self.is_waiting(user_id):
            raise ValueError("No pending request found")
        await self.reject_join(user_id)

    async def get_waiting_details(self, user_id: int) -> dict | None:
        return await self.cache.hgetall(self.waiting_member_key(user_id)) or None

    async def list_waiting(self) -> list[dict]:
        waiting_ids = await self.cache.smembers(self.waiting_key)
        result = []
        for wid in waiting_ids:
            details = await self.cache.hgetall(self.waiting_member_key(int(wid)))
            if details:
                result.append(details)
        return result

    def is_member(self, user_id: int) -> bool:
        return user_id in self._members

    def is_waiting(self, user_id: int) -> bool:
        return user_id in self._waiting

    async def add_member(self, member: RoomMember) -> None:
        pipe = self.cache.pipeline()
        pipe.sadd(self.members_key, str(member.user_id))
        pipe.srem(self.waiting_key, str(member.user_id))
        pipe.delete(self.waiting_member_key(member.user_id))
        pipe.hset(self.member_key(member.user_id), mapping=member.to_dict())
        await pipe.execute()

        self._members.add(member.user_id)
        self._waiting.discard(member.user_id)

    async def get_member(self, user_id: int) -> RoomMember | None:
        data = await self.cache.hgetall(self.member_key(user_id))
        if not data:
            return None
        return RoomMember.from_dict(data)

    async def update_member(self, user_id: int, **kwargs) -> RoomMember | None:
        """Update specific fields of a member."""
        member = await self.get_member(user_id)
        if not member:
            return None

        for key, value in kwargs.items():
            if hasattr(member, key):
                setattr(member, key, value)

        await self.cache.hset(self.member_key(user_id), mapping=member.to_dict())
        return member

    async def set_member_status(self, user_id: int, status: MemberStatus) -> None:
        await self.update_member(user_id, status=status)

    async def disconnect_member(self, user_id: int) -> None:
        member = await self.get_member(user_id)
        if member:
            member.disconnect()
            await self.cache.hset(self.member_key(user_id), mapping=member.to_dict())

    async def reconnect_member(self, user_id: int) -> None:
        member = await self.get_member(user_id)
        if member:
            member.reconnect()
            await self.cache.hset(self.member_key(user_id), mapping=member.to_dict())

    async def list_members(self) -> list[RoomMember]:
        """Get all members as structured objects."""
        member_ids = await self.cache.smembers(self.members_key)
        result = []
        for mid in member_ids:
            member = await self.get_member(int(mid))
            if member:
                result.append(member)
        return result

    async def get_live_members(self) -> list[RoomMember]:
        """Filter only live (connected) members."""
        all_members = await self.list_members()
        return [m for m in all_members if m.status == MemberStatus.LIVE]

    async def get_disconnected_members(self) -> list[RoomMember]:
        all_members = await self.list_members()
        return [m for m in all_members if m.status == MemberStatus.DISCONNECTED]