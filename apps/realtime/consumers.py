"""RoomConsumer: real-time room events via WebSocket.

This file contains ONLY lifecycle logic (connect / disconnect /
_connect_as_member) and the two fixed entry points (receive_json,
send_event). It declares zero event handlers and zero trampoline methods.

All domain handlers live in handlers/:
  handlers/room.py   — room lifecycle events (~20)
  handlers/game.py   — game session events (~50)
  handlers/lobby.py  — future domain (add handlers/__init__.py import)

How outbound dispatch works without explicit methods here:
  EventDispatchMixin.__getattr__ intercepts Channels' getattr lookup for
  message['type'] and resolves it against the @trampoline registry in
  dispatch.py. Channels never knows the difference.

How inbound dispatch works:
  receive_json -> dispatch_inbound -> _INBOUND registry -> handler fn.
  Same as before, now populated from handler modules instead of methods
  on this class.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import PermissionDenied

from apps.core.livekit import livekit_client
from apps.core.redis import redis_client
from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, PlayerStatus
from apps.game.engine.roles.type import RoleType
from apps.game.engine.session import GameSession
from apps.room.session import MemberStatus, RoomMember, RoomSession

# Importing handlers triggers all @on and @trampoline registrations.
from . import handlers  # noqa: F401
from .dispatch import EventDispatchMixin
from .error_codes import ErrorCode
from .events import (
    ErrorEvent,
    GameState,
    HostChanged,
    JoinRequestReceived,
    JoinRequestRejected,
    OutboundEvent,
    PlayerLeft,
    RoomState,
)
from .groups import GameSessionGroup, GameSessionRole, RoomActive, RoomPending, UserGroup
from .membership import GroupMembership
from .players import build_public_players

logger = logging.getLogger(__name__)


class RealtimeConsumer(EventDispatchMixin, AsyncJsonWebsocketConsumer):
    # -- lifecycle --------------------------------------------------------
    groups: GroupMembership

    async def connect(self) -> None:
        code = self.scope['url_route']['kwargs']['code']
        self.code: str = code
        self.user: Any = self.scope.get('user')
        if not self.user:
            raise PermissionDenied("you must be authenticated")

        self._is_member: bool = False

        self.groups = GroupMembership(
            channel_layer=self.channel_layer,
            channel_name=self.channel_name,
        )
        # Personal channel — targeted, per-recipient events (action signals).
        await self.groups.join(UserGroup(self.user.id))
        self.pending_scope = RoomPending(room_code=code)
        self.active_scope = RoomActive(room_code=code)

        session = await RoomSession.from_code(code)
        if not self.user or not session:
            logger.warning(
                'WS connect rejected — no active session for room %r', code
            )
            await self.close(code=4001)
            return

        self.session = session
        await self.groups.join(self.pending_scope)

        if await session.is_original_host(self.user):
            await self._connect_as_member(regain_host=True)
        elif await session.is_member(self.user.id):
            await self._connect_as_member(regain_host=False)
        else:
            await session.request_join(self.user)
            await self.accept()
            await self.groups.emit(
                self.pending_scope,
                JoinRequestReceived(user_id=self.user.id, username=self.user.username),
            )

    async def disconnect(self, close_code: int) -> None:
        # connect() can bail before a session is resolved (unauthenticated,
        # unknown room) — nothing to clean up in that case.
        session = getattr(self, 'session', None)
        if session is None or not self.user:
            return

        if await session.is_waiting(self.user.id):
            await session.cancel_join_request(self.user.id)
            await self.groups.emit(
                self.pending_scope,
                JoinRequestRejected(user_id=self.user.id, username=self.user.username),
            )
            return

        was_host = await session.is_host(self.user)
        await session.disconnect_member(self.user.id)
        await self.groups.leave_all()

        if was_host:
            live_members = await session.get_live_members()
            candidates = [m for m in live_members if m.user_id != self.user.id]
            if candidates:
                new_host_id = candidates[0].user_id
                await self.session.switch_host(new_host_id)
                await self.groups.emit(
                    self.active_scope,
                    HostChanged(
                        new_host_id=new_host_id,
                        new_host_username='',
                        reason='host_disconnected',
                    ),
                )

        member_ids = await self.session.get_member_ids()
        await self.groups.emit(
            self.active_scope,
            PlayerLeft(
                user_id=self.user.id,
                username=self.user.username,
                member_count=len(member_ids),
            ),
        )

    async def _connect_as_member(self, *, regain_host: bool) -> None:
        self._is_member = True

        member = await self.session.get_member(self.user.id)
        if member is None:
            member = RoomMember(user_id=self.user.id, name=self.user.username)
            await self.session.add_member(member)
        else:
            if member.status == MemberStatus.DISCONNECTED:
                await self.session.reconnect_member(self.user.id)
            # Heal stale members stored with an empty name so game events
            # (vote overlays, logs) carry real usernames.
            if not member.name:
                await self.session.update_member(
                    self.user.id, name=self.user.username
                )

        await self.groups.join(self.active_scope)

        # Re-join the game session group if a game is in progress.
        # On disconnect, leave_all() removes every group; without this,
        # a reconnecting player would miss all game events (vote casts,
        # phase transitions, etc.) even though they're still in the game.
        game_session_id = await self.session.get_game_session_id()
        if game_session_id:
            await self.groups.join(
                GameSessionGroup(room_code=self.code, session_id=game_session_id)
            )

        host_regained = False
        previous_host_id: int | None = None
        if (
            regain_host
            and await self.session.is_original_host(self.user)
            and await self.session.host_is_switched()
        ):
            previous_host_id = self.session.host_id
            await self.session.revert_host()
            host_regained = True

        await self.accept()

        # Load the game session first: silenced players must reconnect with
        # a camera-only publish grant (voice blocked server-side).
        game_session = await GameSession.load(room_id=self.code)
        silenced = (
            game_session is not None
            and self.user.id in game_session.silenced_player_ids
        )
        credentials = livekit_client.add_participant(
            meeting_id=self.session.meeting_id,
            participant_id=str(self.user.id),
            name=self.user.username,
            can_publish_sources=['CAMERA'] if silenced else None,
        )
        member_ids = await self.session.get_member_ids()

        # Build game state payload if a game is in progress.
        game_state_payload: dict[str, Any] | None = None
        if game_session is not None:
            current_round = game_session.current_round()

            players_public = await build_public_players(self.session, game_session)
            live_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
            dead_ids = [p.id for p in game_session.players if p.status == PlayerStatus.DEAD]

            role_code = None
            role_name = None
            role_type = None
            role_description = None
            mafia_ids = None

            my_player = next((p for p in game_session.players if p.id == self.user.id), None)
            if my_player is not None and my_player.role is not None:
                role_code = my_player.role.code
                role_name = my_player.role.name
                role_type = my_player.role.role_type.value
                role_description = my_player.role.description
                if my_player.role.role_type == RoleType.MAFIA:
                    mafia_ids = [
                        p.id for p in game_session.players
                        if p.role is not None and p.role.role_type == RoleType.MAFIA
                    ]
                    await self.groups.join(
                        GameSessionRole(
                            room_code=self.code,
                            session_id=game_session.id,
                            role_type=RoleType.MAFIA.value,
                        )
                    )

            required_actions = current_round.get_required_actions_for_player(self.user.id)
            round_requirements = await current_round.requirement_summary()
            logs = [a.to_dict() for a in current_round.all_actions]

            # Day votes live in the pending Redis list until the round
            # resolves, so all_actions misses them. Include them here so a
            # reconnecting client rebuilds the live vote tally — votes are
            # public (every client already got the vote_cast broadcast), so
            # this leaks nothing.
            pending_raw = await redis_client.lrange(
                game_session.pending_actions_key, 0, -1
            )
            for raw in pending_raw:
                action = Action.from_dict(json.loads(raw))
                if action.action_type == ActionType.VOTE:
                    logs.append(action.to_dict())

            game_state_payload = GameState(
                session_id=game_session.id,
                players=players_public,
                live_player_ids=live_ids,
                dead_player_ids=dead_ids,
                current_phase=current_round.phase.value,
                round_number=current_round.round_number,
                lynch_target_id=getattr(current_round, 'lynch_target_id', None),
                logs=logs,
                role_code=role_code,
                role_name=role_name,
                role_type=role_type,
                role_description=role_description,
                mafia_ids=mafia_ids,
                required_actions=required_actions,
                round_requirements=round_requirements,
            ).model_dump()

        await self.send_event(
            RoomState(
                credentials=credentials,
                room_id=self.session.id,
                room_name=self.session.name,
                host_id=self.session.host_id,
                members=list(member_ids),
                game_state=game_state_payload,
            )
        )

        if host_regained:
            await self.groups.emit(
                self.active_scope,
                HostChanged(
                    new_host_id=self.user.id,
                    new_host_username=self.user.username,
                    reason='host_reconnected',
                ),
            )

    # -- fixed entry points (never change) --------------------------------

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        await self.dispatch_inbound(content)

    async def send_event(self, event: OutboundEvent) -> None:
        """Send a typed outbound event directly to this socket only."""
        await self.send_json(event.to_json())

    # consumer.py
    async def send_error(self, code: ErrorCode, message: str) -> None:
        await self.send_event(ErrorEvent(code=code, message=message))
