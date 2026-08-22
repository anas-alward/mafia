# Silencer Voice-Mute & Death Role-Reveal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change the Silencer's `silence` action from roleblocking night actions to muting the target's voice in WebRTC for the following day, and reveal roles on death (full roster privately to the dead player, dead player's role publicly to the room).

**Architecture:** Engine changes (round resolution, session state) are pure Redis-free dataclass logic tested directly. The WebRTC preset flip and the group-scoped role reveals live in `apps/realtime/handlers/game.py`, firing from the single `_transition_after_resolve` choke point that both night and vote-result resolution funnel through.

**Tech Stack:** Django 6.x, Django Channels (WebSockets), Cloudflare Realtime Kit SDK, Redis-backed game engine, pytest.

## Global Constraints

- The mute preset is `'silent_players'`; the unmute/default preset is `'group_call_host'` (the same default used at participant registration).
- `participant_id` convention for WebRTC calls is `str(player.id)` (`str(user.id)`).
- The private reveal goes to a per-player group `room.{room_code}.session.{session_id}.player.{player_id}`; the public reveal goes to `RoomActive`.
- `GRACE_SECONDS = 5.0` (do not change).
- Engine tests construct `NightRound` / `GameSession` directly with no Redis; handler-level WebRTC/group code is validated manually against a running meeting (not unit-tested).
- `RoleRevealed` (singular) = public dead-player's role; `RolesRevealed` (plural) = private full roster.

---

### Task 1: Remove silencer roleblock + add `silenced_target_ids()`

**Files:**
- Modify: `apps/game/engine/round.py:271-319` (`NightRound.resolve`) and add a new method after `resolve`
- Test: `tests/game/test_aggregation.py:78-98` (update `test_silencer_keeps_both_actions`), add `test_silenced_target_ids`

**Interfaces:**
- Consumes: `ActionType.SILENCE`, `ActionType.HEAL`, `ActionType.KILL`, `PlayerStatus.ALIVE` (already defined).
- Produces: `NightRound.silenced_target_ids() -> list[int]` — the alive targets silenced this night, deduped by `(actor_id, action_type)` via `_last_actions`. Task 5 consumes this.

- [ ] **Step 1: Write the failing tests**

Update `test_silencer_keeps_both_actions` so the Doctor's heal is *not* blocked (target survives, kill log carries `result: 'healed'`), and add `test_silenced_target_ids`.

In `tests/game/test_aggregation.py`, replace the body of `test_silencer_keeps_both_actions` (from `logs = await round_.resolve()` to the end of the function):

```python
    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.ALIVE  # abandoned kill target survives
    assert players[3].status == PlayerStatus.ALIVE  # healed — silence no longer blocks
    assert {'target_id': 2, 'action_type': 'silence'} in logs
    kill_logs = [entry for entry in logs if entry['action_type'] == 'kill']
    assert kill_logs == [{'target_id': 4, 'action_type': 'kill', 'result': 'healed'}]
```

Then append a new test at the end of the file (after `test_revenge_dedup`):

```python
def test_silenced_target_ids():
    players = [
        Player(id=1, role=MafiaSilencer()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla(), status=PlayerStatus.DEAD),
    ]

    living = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    living.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.SILENCE))
    assert living.silenced_target_ids() == [2]

    dead = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    dead.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.SILENCE))
    assert dead.silenced_target_ids() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: `test_silencer_keeps_both_actions` FAILS (player 4 still `DEAD`, kill log lacks `'healed'`); `test_silenced_target_ids` FAILS with `AttributeError: 'NightRound' object has no attribute 'silenced_target_ids'`.

- [ ] **Step 3: Implement the engine change**

In `apps/game/engine/round.py`, replace `NightRound.resolve` (lines 271-319) with the version that drops the `blocked` set, and add `silenced_target_ids()` immediately after it.

```python
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

        # 3. OFFENSIVE ACTIONS (KILL / SHOOT)
        for a in actions:
            if a.action_type in (ActionType.KILL, ActionType.SHOOT):
                if a.action_type == ActionType.KILL and a.actor_id != designated_killer:
                    continue
                if a.target_id in healed:
                    logs.append({'target_id': a.target_id, 'action_type': a.action_type.value, 'result': 'healed'})
                else:
                    target = self._get_player(a.target_id)
                    if target:
                        target.status = PlayerStatus.DEAD
                    logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 4. DETECT
        for a in actions:
            if a.action_type == ActionType.DETECT:
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        await self._autosave()
        return logs

    def silenced_target_ids(self) -> list[int]:
        actions = self._last_actions(self.night_actions)
        return [
            a.target_id for a in actions
            if a.action_type == ActionType.SILENCE
            and a.target_id in self.alive_player_ids()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/game/engine/round.py tests/game/test_aggregation.py
git commit -m "feat: remove silencer roleblock; silence only mutes voice"
```

---

### Task 2: Track muted players on `GameSession`

**Files:**
- Modify: `apps/game/engine/session.py:12-28` (add field), `session.py:69-89` (serialize/hydrate)
- Test: `tests/game/test_session.py` (new file)

**Interfaces:**
- Consumes: none.
- Produces: `GameSession.silenced_player_ids: list[int]` (default `[]`), serialized as `'silenced_player_ids'`, hydrated with `data.get('silenced_player_ids', [])`. Task 5 reads and writes this field.

- [ ] **Step 1: Write the failing tests**

Create `tests/game/test_session.py`:

```python
from apps.game.engine.session import GameSession


def test_session_to_dict_includes_silenced_player_ids():
    session = GameSession(id='abc', room_id='room1', silenced_player_ids=[3, 7])
    data = session.to_dict()
    assert data['silenced_player_ids'] == [3, 7]


def test_session_roundtrip_preserves_silenced_player_ids():
    session = GameSession(id='abc', room_id='room1', silenced_player_ids=[3, 7])
    restored = GameSession.from_dict(session.to_dict())
    assert restored.silenced_player_ids == [3, 7]


def test_session_from_dict_defaults_missing_silenced_player_ids():
    data = {
        'id': 'abc',
        'room_id': 'room1',
        'players': [],
        'rounds': [],
    }
    restored = GameSession.from_dict(data)
    assert restored.silenced_player_ids == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/game/test_session.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'silenced_player_ids'`.

- [ ] **Step 3: Implement the field + serialization**

In `apps/game/engine/session.py`, add the field after `players`:

```python
    rounds: list[GameRound] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)

    silenced_player_ids: list[int] = field(default_factory=list)

    key_prefix: str = 'mafia:session:'
```

Update `to_dict`:

```python
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'room_id': self.room_id,
            'players': [p.to_dict() for p in self.players],
            'rounds': [r.to_dict() for r in self.rounds],
            'silenced_player_ids': self.silenced_player_ids,
        }
```

Update `from_dict`'s `cls(...)` call:

```python
        session = cls(
            id=data['id'],
            room_id=data['room_id'],
            players=[Player.from_dict(p) for p in data['players']],
            silenced_player_ids=data.get('silenced_player_ids', []),
            key_prefix=key_prefix,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/game/test_session.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/game/engine/session.py tests/game/test_session.py
git commit -m "feat: track muted players on GameSession"
```

---

### Task 3: WebRTC `edit_participant` + silencer description

**Files:**
- Modify: `apps/core/webrtc.py:37-56` (add method after `add_participant`)
- Modify: `apps/game/engine/roles/type.py:110` (`MafiaSilencer.description`)

**Interfaces:**
- Consumes: `webrtc_client` (module singleton already imported by `handlers/game.py`).
- Produces: `WebRTCClient.edit_participant(meeting_id, participant_id, preset_name) -> None`. Task 5 consumes this.

- [ ] **Step 1: Add `edit_participant` to the WebRTC wrapper**

In `apps/core/webrtc.py`, insert after `add_participant` (after line 56):

```python
    def edit_participant(self, meeting_id: str, participant_id: str, preset_name: str) -> None:
        """Update a participant's preset (e.g. mute via 'silent_players')."""
        self.client.realtime_kit.meetings.edit_participant(
            account_id=self.account_id,
            app_id=self.app_id,
            meeting_id=meeting_id,
            participant_id=participant_id,
            preset_name=preset_name,
        )
```

- [ ] **Step 2: Update the silencer description**

In `apps/game/engine/roles/type.py`, change `MafiaSilencer.description`:

```python
    description = "Silences one player each night, muting their voice for the following day."
```

- [ ] **Step 3: Verify no regressions**

Run: `pytest tests/game/ tests/realtime/ -q`
Expected: all pass (the existing `test_role_info_for_reconnecting_player` asserts `'Silences one player' in description`, which still holds).

- [ ] **Step 4: Commit**

```bash
git add apps/core/webrtc.py apps/game/engine/roles/type.py
git commit -m "feat: add WebRTC edit_participant and update silencer description"
```

---

### Task 4: Death-reveal events + per-player group scope

**Files:**
- Modify: `apps/realtime/events/game.py:9-34` (add enums) and after `GameOver` (add events)
- Modify: `apps/realtime/groups.py` (add `GameSessionPlayer`)
- Test: `tests/realtime/test_role_reveal_events.py` (new file)

**Interfaces:**
- Consumes: `OutboundEvent` (from `.base`), `GroupScope` (from `groups.py`).
- Produces:
  - `GameEvents.ROLE_REVEALED = 'role_revealed'`, `GameEvents.ROLES_REVEALED = 'roles_revealed'`.
  - `RoleRevealed(player_id, role_code, role_name, role_type, description)` — public.
  - `RolesRevealed(players: list[dict])` — private roster.
  - `GameSessionPlayer(room_code, session_id, player_id)` with `.name` = `room.{code}.session.{sid}.player.{pid}`.
  Task 5 consumes all of these.

- [ ] **Step 1: Write the failing tests**

Create `tests/realtime/test_role_reveal_events.py`:

```python
from apps.realtime.events.game import RoleRevealed, RolesRevealed
from apps.realtime.groups import GameSessionPlayer


def test_role_revealed_channel_type_and_payload():
    event = RoleRevealed(
        player_id=4,
        role_code='godfather',
        role_name='Mafia King',
        role_type='mafia',
        description='The leader of the Mafia.',
    )
    payload = event.to_json()
    assert payload['type'] == 'role_revealed'
    assert payload['player_id'] == 4
    assert payload['role_code'] == 'godfather'
    assert payload['role_name'] == 'Mafia King'
    assert payload['role_type'] == 'mafia'
    assert payload['description'] == 'The leader of the Mafia.'


def test_roles_revealed_channel_type_and_payload():
    roster = [
        {'id': 1, 'role_code': 'godfather', 'role_name': 'Mafia King', 'role_type': 'mafia', 'description': 'The leader.'},
        {'id': 2, 'role_code': 'doctor', 'role_name': 'Doctor', 'role_type': 'town', 'description': 'Protects one.'},
    ]
    event = RolesRevealed(players=roster)
    payload = event.to_json()
    assert payload['type'] == 'roles_revealed'
    assert payload['players'] == roster


def test_game_session_player_scope_name():
    scope = GameSessionPlayer(room_code='ABC123', session_id='sess1', player_id=7)
    assert scope.name == 'room.ABC123.session.sess1.player.7'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/realtime/test_role_reveal_events.py -v`
Expected: FAIL with `ImportError` (symbols not yet defined).

- [ ] **Step 3: Add the events**

In `apps/realtime/events/game.py`, add two enum members to `GameEvents` (after `GAME_OVER = 'game_over'`):

```python
    ROLE_REVEALED = 'role_revealed'
    ROLES_REVEALED = 'roles_revealed'
```

Append at the end of the file (after `GameOver`):

```python
class RoleRevealed(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.ROLE_REVEALED
    player_id: int
    role_code: str
    role_name: str
    role_type: str
    description: str


class RolesRevealed(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.ROLES_REVEALED
    players: list[dict[str, Any]]
```

- [ ] **Step 4: Add the group scope**

In `apps/realtime/groups.py`, append after `GameSessionRole` (after line 122):

```python
@dataclass(frozen=True, slots=True)
class GameSessionPlayer(GroupScope):
    """Per-player group within a game session.

    Used to reach one specific player privately — e.g. send a dead player
    the full roster without leaking it in a room-wide broadcast.
    """

    room_code: str
    session_id: str
    player_id: int

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.session.{self.session_id}.player.{self.player_id}'
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/realtime/test_role_reveal_events.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/realtime/events/game.py apps/realtime/groups.py tests/realtime/test_role_reveal_events.py
git commit -m "feat: add death-reveal events and per-player group scope"
```

---

### Task 5: Wire mute/unmute and death reveals in handlers

**Files:**
- Modify: `apps/realtime/handlers/game.py` (imports, two trampolines, two call sites, `_transition_after_resolve`, two new helpers)

**Interfaces:**
- Consumes: `GameSession.silenced_player_ids` (Task 2), `NightRound.silenced_target_ids()` (Task 1), `WebRTCClient.edit_participant` (Task 3), `RoleRevealed`/`RolesRevealed`/`GameSessionPlayer` (Task 4), `webrtc_client`.
- Produces: no new public surface; behavior wired into the existing resolution path.

This task has no unit test (handler-level WebRTC/group logic is validated manually — see Global Constraints). Verify the module imports and lint instead.

- [ ] **Step 1: Update imports**

In `apps/realtime/handlers/game.py`, add to the existing imports:

```python
from apps.core.webrtc import webrtc_client
```

Change the round import to also bring in `NightRound`:

```python
from apps.game.engine.round import GRACE_SECONDS, NightRound
```

Add `RoleRevealed` and `RolesRevealed` to the `from ..events.game import (...)` block (alphabetical position after `ResetGame` / before `RoleAssigned`):

```python
    RoleRevealed,
    RolesRevealed,
```

Change the groups import to include `GameSessionPlayer`:

```python
from ..groups import GameSessionGroup, GameSessionPlayer, GameSessionRole, RoomActive
```

- [ ] **Step 2: Join `GameSessionPlayer` in the `game_started` trampoline**

In `game_started`, inside the existing `if consumer.user.id in event['player_ids']:` block that joins `GameSessionGroup`, add a second join:

```python
    if consumer.user.id in event['player_ids']:
        await consumer.groups.join(
            GameSessionGroup(room_code=consumer.code, session_id=event['session_id'])
        )
        await consumer.groups.join(
            GameSessionPlayer(
                room_code=consumer.code,
                session_id=event['session_id'],
                player_id=consumer.user.id,
            )
        )
```

- [ ] **Step 3: Join `GameSessionPlayer` in the `game_reset` trampoline**

Apply the same addition in `game_reset`, inside its `if consumer.user.id in event['player_ids']:` block (which currently joins only `GameSessionGroup`):

```python
    if consumer.user.id in event['player_ids']:
        await consumer.groups.join(
            GameSessionGroup(room_code=consumer.code, session_id=event['session_id'])
        )
        await consumer.groups.join(
            GameSessionPlayer(
                room_code=consumer.code,
                session_id=event['session_id'],
                player_id=consumer.user.id,
            )
        )
```

- [ ] **Step 4: Thread `alive_before` through `_resolve_after_grace`**

In `_resolve_after_grace`, capture the alive set before `resolve()` and pass it down:

```python
    alive_before = round_.alive_player_ids()
    logs = await round_.resolve()
    group = GameSessionGroup(room_code=consumer.code, session_id=fresh.id)
    await _transition_after_resolve(fresh, round_, logs, consumer, group, alive_before)
```

- [ ] **Step 5: Thread `alive_before` through `handle_submit_votes`**

In `handle_submit_votes`, the `alive` set is already computed before `resolve()`; pass it as `alive_before` on the no-lynch path:

```python
    await _transition_after_resolve(game_session, round_, logs, consumer, group, alive_before=alive)
```

- [ ] **Step 6: Update `_transition_after_resolve`**

Replace the function with the version that fires reveals before the winner check and applies silence at the NIGHT→DAY boundary:

```python
async def _transition_after_resolve(
    game_session: GameSession,
    round_: object,
    logs: list[str],
    consumer: RealtimeConsumer,
    group: object,
    alive_before: set[int],
) -> None:
    """Emit the phase-transition event and start the next round.

    NIGHT       → new DAY round   → SunRise
    DAY         → new NIGHT round → SunSet   (no lynch target edge case)
    VOTE_RESULT → new NIGHT round → SunSet
    """
    newly_dead = alive_before - round_.alive_player_ids()
    for dead_id in newly_dead:
        await _reveal_death(consumer, game_session, dead_id)

    player_ids = [p.id for p in game_session.players]
    winner = game_session.check_winner()
    if winner is not None:
        await consumer.groups.emit(
            RoomActive(room_code=consumer.code),
            GameOver(winner=winner, player_ids=player_ids, logs=logs),
        )
        await game_session.flush()
        await consumer.session.clear_game_session_id()
        return

    if round_.phase == Phase.NIGHT:
        await _apply_silence(consumer, game_session, round_)
        await game_session.new_round(phase=Phase.DAY)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunRise(player_ids=alive_ids, logs=logs))
    else:
        # DAY (no lynch) or EXECUTION → transition to NIGHT.
        await game_session.new_round(phase=Phase.NIGHT)
        alive_ids = [p.id for p in game_session.players if p.status == PlayerStatus.ALIVE]
        await consumer.groups.emit(group, SunSet(player_ids=alive_ids, logs=logs))
```

- [ ] **Step 7: Add the `_apply_silence` and `_reveal_death` helpers**

Append to the Helpers section at the bottom of the file:

```python
async def _apply_silence(
    consumer: RealtimeConsumer,
    game_session: GameSession,
    round_: NightRound,
) -> None:
    meeting_id = consumer.session.meeting_id
    if not meeting_id:
        return
    newly = set(round_.silenced_target_ids())
    previously = set(game_session.silenced_player_ids)

    for pid in previously - newly:      # unmute
        webrtc_client.edit_participant(meeting_id, str(pid), 'group_call_host')
    for pid in newly - previously:      # mute
        webrtc_client.edit_participant(meeting_id, str(pid), 'silent_players')

    game_session.silenced_player_ids = sorted(newly)
    await game_session.save()


async def _reveal_death(consumer: RealtimeConsumer, game_session: GameSession, dead_id: int) -> None:
    dead_player = next((p for p in game_session.players if p.id == dead_id), None)
    if dead_player is None or dead_player.role is None:
        return

    roster = [
        {'id': p.id, 'role_code': p.role.code, 'role_name': p.role.name,
         'role_type': p.role.role_type.value, 'description': p.role.description}
        for p in game_session.players if p.role is not None
    ]

    # Public: the dead player's role, to the whole room.
    await consumer.groups.emit(
        RoomActive(room_code=consumer.code),
        RoleRevealed(
            player_id=dead_id,
            role_code=dead_player.role.code,
            role_name=dead_player.role.name,
            role_type=dead_player.role.role_type.value,
            description=dead_player.role.description,
        ),
    )

    # Private: the full roster, only to the dead player.
    await consumer.groups.emit(
        GameSessionPlayer(room_code=consumer.code, session_id=game_session.id, player_id=dead_id),
        RolesRevealed(players=roster),
    )
```

- [ ] **Step 8: Verify imports, lint, and full test suite**

Run: `python -c "import apps.realtime.handlers.game"` (imports resolve, no syntax errors).
Run: `ruff check apps/realtime/handlers/game.py apps/core/webrtc.py apps/game/engine/`
Run: `pytest -q`
Expected: no import errors, no new lint errors, full suite PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/realtime/handlers/game.py
git commit -m "feat: wire voice mute/unmute and death role reveal in handlers"
```

---

## Self-Review Notes

- **Spec coverage:** Task 1 → spec 1.1/1.2/1.4 (`silenced_target_ids`, drop roleblock); Task 2 → spec 1.4 (session field); Task 3 → spec 1.5 (`edit_participant`) + 1.6 (description); Task 4 → spec 2.2/2.3 (events + group); Task 5 → spec 1.5 (`_apply_silence`), 2.4/2.5 (`alive_before`, `_reveal_death`), 3 (resolution order).
- **Out of scope honored:** dead players' WebRTC state is not touched; the reveal is one-time (no reconnect re-delivery). Reconnecting players re-join `GameSessionGroup` but not `GameSessionPlayer`, which is consistent with the one-time snapshot design.
- **Type consistency:** `silenced_player_ids` (session) ↔ `silenced_target_ids()` (round) ↔ `_apply_silence` (handler); `RoleRevealed`/`RolesRevealed`/`GameSessionPlayer` names match across events, groups, and handlers.
