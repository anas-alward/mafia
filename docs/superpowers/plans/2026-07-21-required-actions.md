# Required Actions Per Round — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-role required-action configuration, obligation tracking per round, phase-specific transition triggers (auto for Night/VoteResult, host-triggered for Day), and personalized phase-change events.

**Architecture:** ActionConfig dataclass lives on each role class. GameRound computes obligations at init (resolving mafia KILL priority chain), tracks submissions with `is_player_done` / `is_round_done`, and triggers grace-timer + auto-resolve for Night/VoteResult. Trampolines personalize SunSet/SunRise/VoteResultStarted per consumer.

**Tech Stack:** Python 3.12+, Django Channels, Redis (game state), asyncio (grace timer)

## Global Constraints

- Django 6.x with Daphne ASGI server
- All game state persisted as JSON in Redis via `GameSession.save()`
- Inbound events use pydantic `BaseModel` with `type: ClassVar[str]`
- Outbound events use pydantic `BaseModel` with `channel_type: ClassVar[str]`
- Handlers use `@on(InboundClass)` / `@trampoline('type_str')` decorators

---

### Task 1: Add `ActionConfig` dataclass to constants

**Files:**
- Modify: `apps/game/engine/constants.py`

**Interfaces:**
- Produces: `ActionConfig(action_type: ActionType, required: bool, priority: int | None = None)` with `.to_dict()` and `.from_dict(data: dict)`

- [ ] **Step 1: Add the dataclass**

```python
# apps/game/engine/constants.py — add at top after existing imports

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .constants import ActionType


@dataclass
class ActionConfig:
    action_type: 'ActionType'
    required: bool
    priority: int | None = None

    def to_dict(self) -> dict:
        return {
            'action_type': self.action_type.value,
            'required': self.required,
            'priority': self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionConfig':
        return cls(
            action_type=ActionType(data['action_type']),
            required=data['required'],
            priority=data.get('priority'),
        )
```

Wait — the `TYPE_CHECKING` trick with self-referencing `ActionType` is awkward here since `ActionType` is defined in the same file above `ActionConfig`. Instead just reference it directly:

```python
# apps/game/engine/constants.py — add at the end of the file

from dataclasses import dataclass


@dataclass
class ActionConfig:
    action_type: ActionType
    required: bool
    priority: int | None = None

    def to_dict(self) -> dict:
        return {
            'action_type': self.action_type.value,
            'required': self.required,
            'priority': self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ActionConfig':
        return cls(
            action_type=ActionType(data['action_type']),
            required=data['required'],
            priority=data.get('priority'),
        )
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add apps/game/engine/constants.py
git commit -m "feat: add ActionConfig dataclass for per-role action configuration"
```

---

### Task 2: Add `actions` dict to each role class

**Files:**
- Modify: `apps/game/engine/roles/type.py`
- Modify: `apps/game/roles.py` (keep in sync — the distributor imports from here)

**Interfaces:**
- Produces: Each role class has `actions: dict[Phase, list[ActionConfig]]` class attribute
- Consumes: `ActionConfig` from Task 1, `Phase` and `ActionType` from `constants.py`

- [ ] **Step 1: Add imports and actions to engine roles**

```python
# apps/game/engine/roles/type.py — replace entire file

from enum import StrEnum

from ..constants import ActionType, Phase, ActionConfig


class RoleType(StrEnum):
    TOWN = 'town'
    MAFIA = 'mafia'


class BaseRole:
    role_type: RoleType
    name: str
    description: str
    actions: dict[Phase, list[ActionConfig]] = {}


class TownDoctor(BaseRole):
    role_type = RoleType.TOWN
    name = "Emerald Medic"
    description = "Protects one player from being eliminated each night."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.HEAL, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownCop(BaseRole):
    role_type = RoleType.TOWN
    name = "Indigo Investigator"
    description = "Investigates one player each night to learn their alignment."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.DETECT, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownVigilante(BaseRole):
    role_type = RoleType.TOWN
    name = "Azure Vigilante"
    description = "Can choose to eliminate a player at night, but has limited ammo."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.SHOOT, required=False),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownBomb(BaseRole):
    role_type = RoleType.TOWN
    name = "Crimson Kamikaze"
    description = "Explodes upon death, eliminating whoever was responsible for killing them."
    actions = {
        Phase.VOTE_RESULT: [
            ActionConfig(action_type=ActionType.REVENGE, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class TownVanilla(BaseRole):
    role_type = RoleType.TOWN
    name = "Vanilla Townie"
    description = "Has no special ability. Uses vote power during the day."
    actions = {
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaGodfather(BaseRole):
    role_type = RoleType.MAFIA
    name = "Obsidian Overlord"
    description = "The leader of the Mafia. Appears as 'Town' if investigated by the Cop."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=1),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaRoleblocker(BaseRole):
    role_type = RoleType.MAFIA
    name = "Scarlet Silencer"
    description = "Blocks one player each night, preventing them from using their action."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=2),
            ActionConfig(action_type=ActionType.ROLEBLOCK, required=True),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


class MafiaMember(BaseRole):
    role_type = RoleType.MAFIA
    name = "Black Hand"
    description = "Basic Mafia member who participates in night kills."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=3),
        ],
        Phase.DAY: [
            ActionConfig(action_type=ActionType.VOTE, required=True),
        ],
    }


ROLES: list[BaseRole] = [
    TownDoctor(),
    TownCop(),
    TownVigilante(),
    TownBomb(),
    TownVanilla(),
    MafiaGodfather(),
    MafiaRoleblocker(),
    MafiaMember(),
]

ROLE_REGISTRY: dict[str, BaseRole] = {role.name: role for role in ROLES}
```

- [ ] **Step 2: Sync `apps/game/roles.py`**

The distributor imports from `apps.game.roles`, so add the same `actions` dict to roles there. This file currently defines roles as plain classes (no `actions`). Add the same `actions` class attribute to each role class:

```python
# apps/game/roles.py — add to each role class

from apps.game.engine.constants import ActionType, Phase, ActionConfig

# Add `actions = {}` to BaseRole, then add actions to each class
# exactly matching the mapping from type.py above.
```

Full replacement:

```python
from enum import StrEnum

from apps.game.engine.constants import ActionType, Phase, ActionConfig


class RoleType(StrEnum):
    TOWN = 'town'
    MAFIA = 'mafia'


class BaseRole:
    role_type: RoleType
    name: str
    description: str
    actions: dict[Phase, list[ActionConfig]] = {}


class TownDoctor(BaseRole):
    role_type = RoleType.TOWN
    name = "Emerald Medic"
    description = "Protects one player from being eliminated each night."
    actions = {
        Phase.NIGHT: [ActionConfig(action_type=ActionType.HEAL, required=True)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class TownCop(BaseRole):
    role_type = RoleType.TOWN
    name = "Indigo Investigator"
    description = "Investigates one player each night to learn their alignment."
    actions = {
        Phase.NIGHT: [ActionConfig(action_type=ActionType.DETECT, required=True)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class TownVigilante(BaseRole):
    role_type = RoleType.TOWN
    name = "Azure Vigilante"
    description = "Can choose to eliminate a player at night, but has limited ammo."
    actions = {
        Phase.NIGHT: [ActionConfig(action_type=ActionType.SHOOT, required=False)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class TownBomb(BaseRole):
    role_type = RoleType.TOWN
    name = "Crimson Kamikaze"
    description = "Explodes upon death, eliminating whoever was responsible for killing them."
    actions = {
        Phase.VOTE_RESULT: [ActionConfig(action_type=ActionType.REVENGE, required=True)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class TownVanilla(BaseRole):
    role_type = RoleType.TOWN
    name = "Vanilla Townie"
    description = "Has no special ability. Uses vote power during the day."
    actions = {
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class MafiaGodfather(BaseRole):
    role_type = RoleType.MAFIA
    name = "Obsidian Overlord"
    description = "The leader of the Mafia. Appears as 'Town' if investigated by the Cop."
    actions = {
        Phase.NIGHT: [ActionConfig(action_type=ActionType.KILL, required=True, priority=1)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class MafiaRoleblocker(BaseRole):
    role_type = RoleType.MAFIA
    name = "Scarlet Silencer"
    description = "Blocks one player each night, preventing them from using their action."
    actions = {
        Phase.NIGHT: [
            ActionConfig(action_type=ActionType.KILL, required=True, priority=2),
            ActionConfig(action_type=ActionType.ROLEBLOCK, required=True),
        ],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }


class MafiaMember(BaseRole):
    role_type = RoleType.MAFIA
    name = "Black Hand"
    description = "Basic Mafia member who participates in night kills."
    actions = {
        Phase.NIGHT: [ActionConfig(action_type=ActionType.KILL, required=True, priority=3)],
        Phase.DAY: [ActionConfig(action_type=ActionType.VOTE, required=True)],
    }
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add apps/game/engine/roles/type.py apps/game/roles.py
git commit -m "feat: add actions config dict to each role class"
```

---

### Task 3: Obligation tracking in `GameRound`

**Files:**
- Modify: `apps/game/engine/round.py`

**Interfaces:**
- Produces: `GameRound.obligations: dict[int, list[ActionType]]`, `compute_obligations()`, `is_player_done(player_id: int) -> bool`, `is_round_done() -> bool`
- Consumes: `ActionConfig` from Task 1, role `actions` from Task 2

- [ ] **Step 1: Add obligation fields and computation to `GameRound`**

```python
# apps/game/engine/round.py — additions inside GameRound dataclass

# New field (add to dataclass fields):
obligations: dict[int, list[ActionType]] = field(default_factory=dict)

# New method — compute obligations at round start:
def compute_obligations(self) -> None:
    """Compute which players must submit which actions this phase.

    For the mafia KILL priority chain, only the highest-priority alive
    mafia gets KILL as a required obligation. Lower-priority mafia also
    get KILL removed from their obligations so they aren't separately
    required.
    """
    self.obligations = {}
    phase = self.phase

    # Separate tracking for the mafia KILL priority chain.
    mafia_kill_candidates: list[tuple[int, int]] = []  # (priority, player_id)

    for player in self.members:
        if player.role is None or player.status == PlayerStatus.DEAD:
            continue

        role_actions = player.role.actions.get(phase, [])
        required: list[ActionType] = []

        for cfg in role_actions:
            if not cfg.required:
                continue
            if cfg.action_type == ActionType.KILL and cfg.priority is not None:
                # Mafia kill — defer to priority resolution.
                mafia_kill_candidates.append((cfg.priority, player.id))
            else:
                required.append(cfg.action_type)

        if required:
            self.obligations[player.id] = required

    # Resolve mafia KILL priority chain: only the highest-priority alive
    # mafia gets the KILL obligation.
    if mafia_kill_candidates:
        mafia_kill_candidates.sort(key=lambda x: x[0])  # lowest priority number = highest priority
        chosen_id = mafia_kill_candidates[0][1]
        self.obligations.setdefault(chosen_id, []).append(ActionType.KILL)

    # VOTE_RESULT phase: lynched player may have on-death obligations.
    if phase == Phase.VOTE_RESULT and self.lynch_target_id is not None:
        lynched = self._get_player(self.lynch_target_id)
        if lynched and lynched.role is not None:
            vote_result_actions = lynched.role.actions.get(Phase.VOTE_RESULT, [])
            for cfg in vote_result_actions:
                if cfg.required:
                    self.obligations.setdefault(lynched.id, []).append(cfg.action_type)

    # DAY phase: all alive players must vote.
    if phase == Phase.DAY:
        for player in self.members:
            if player.status == PlayerStatus.ALIVE:
                self.obligations.setdefault(player.id, []).append(ActionType.VOTE)

    def is_player_done(self, player_id: int) -> bool:
        """True when this player has submitted all their required actions."""
        required = self.obligations.get(player_id, [])
        if not required:
            return True  # no obligations = trivially done

        submitted: set[ActionType] = set()
        actions_list = self.night_actions if self.phase == Phase.NIGHT else self.day_actions
        for a in actions_list:
            if a.actor_id == player_id:
                submitted.add(a.action_type)

        return all(at in submitted for at in required)

    def is_round_done(self) -> bool:
        """True when ALL obligated players have completed their required actions."""
        if not self.obligations:
            return True
        return all(self.is_player_done(pid) for pid in self.obligations)
```

Wait — `is_player_done` and `is_round_done` are methods, not nested functions. Let me restructure. They should be regular methods on `GameRound`.

Also, `_get_player` already exists on `GameRound`.

Let me rewrite this task more cleanly. The key changes to `round.py`:

1. Add `obligations` field
2. Add `compute_obligations()` that sets up `self.obligations`
3. Call `compute_obligations()` during `__post_init__` or from `new_round` / resolve
4. Add `is_player_done()` and `is_round_done()`

Here's the clean version:

- [ ] **Step 1: Add obligations field and methods to GameRound**

Add the new field:
```python
# In the dataclass fields of GameRound, add:
obligations: dict[int, list[ActionType]] = field(default_factory=dict)
```

Add these methods after the existing `alive_player_ids` method:

```python
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


def is_player_done(self, player_id: int) -> bool:
    """True when this player has submitted all their required actions."""
    required = self.obligations.get(player_id, [])
    if not required:
        return True
    actions_list = self.night_actions if self.phase == Phase.NIGHT else self.day_actions
    submitted = {a.action_type for a in actions_list if a.actor_id == player_id}
    return all(at in submitted for at in required)


def is_round_done(self) -> bool:
    """True when ALL obligated players have completed their required actions."""
    if not self.obligations:
        return True
    return all(self.is_player_done(pid) for pid in self.obligations)
```

- [ ] **Step 2: Call `compute_obligations()` from `GameSession.new_round()`**

In `apps/game/engine/session.py`, after creating a `GameRound` in `new_round()`, call `compute_obligations()`:

```python
async def new_round(self, phase: Phase = Phase.NIGHT) -> GameRound:
    round_ = GameRound(
        round_number=len(self.rounds) + 1,
        members=self.players.copy(),
        phase=phase,
        _session=self,
    )
    round_.compute_obligations()
    self.rounds.append(round_)
    await self.save()
    return round_
```

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add apps/game/engine/round.py apps/game/engine/session.py
git commit -m "feat: add obligation tracking to GameRound"
```

---

### Task 4: Grace timer and Night auto-transition

**Files:**
- Modify: `apps/game/engine/round.py`
- Modify: `apps/realtime/handlers/game.py`

**Interfaces:**
- Produces: `GameRound.grace_started_at: float | None`, `start_grace()`, `is_grace_expired()`; `_try_auto_transition_night()` in handlers
- Consumes: `is_round_done()` from Task 3

- [ ] **Step 1: Add grace timer fields and methods to GameRound**

```python
# Add field to GameRound dataclass:
grace_started_at: float | None = field(default=None, repr=False)

# Add constant at module level in round.py:
GRACE_SECONDS: float = 5.0

# Add methods to GameRound:
def start_grace(self) -> None:
    """Begin the grace period for optional actions."""
    import time
    self.grace_started_at = time.monotonic()

def is_grace_expired(self) -> bool:
    """True if grace period has elapsed since start_grace was called."""
    import time
    if self.grace_started_at is None:
        return False
    return (time.monotonic() - self.grace_started_at) >= GRACE_SECONDS

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
```

- [ ] **Step 2: Update serialization for new fields**

```python
# In to_dict(), add:
'grace_started_at': self.grace_started_at,
'obligations': {
    str(k): [at.value for at in v] for k, v in self.obligations.items()
},

# In from_dict(), add:
grace_started_at=data.get('grace_started_at'),
# obligations is recomputed via compute_obligations() on load
```

After `from_dict` creates the round, the caller must call `compute_obligations()`:

In `GameSession.from_dict`, after creating each round:
```python
for r in session.rounds:
    r.compute_obligations()
```

- [ ] **Step 3: Add auto-transition helper in handlers/game.py**

In `apps/realtime/handlers/game.py`, add a helper that night action handlers call after adding their action:

```python
import asyncio
import time

async def _try_auto_transition_night(
    consumer: RealtimeConsumer,
    game_session: GameSession,
) -> None:
    """Check if the night round is done. If so, start grace and auto-resolve."""
    round_ = game_session.current_round()
    if round_.phase != Phase.NIGHT:
        return
    if not round_.is_round_done():
        return
    
    # Start the grace timer.
    round_.start_grace()
    await game_session.save()
    
    # Fire-and-forget: sleep grace period, then resolve.
    asyncio.create_task(_resolve_after_grace(consumer, game_session))


async def _resolve_after_grace(
    consumer: RealtimeConsumer,
    game_session: GameSession,
) -> None:
    """Sleep GRACE_SECONDS, then re-load and resolve the night round."""
    await asyncio.sleep(5.0)
    
    # Re-load from Redis to pick up any optional actions submitted during grace.
    fresh = await GameSession.load(room_id=game_session.room_id)
    if fresh is None:
        return
    round_ = fresh.current_round()
    if round_.phase != Phase.NIGHT:
        return  # already transitioned
    
    logs = await round_.resolve()
    group = GameSessionGroup(room_code=consumer.code, session_id=fresh.id)
    await _transition_after_resolve(fresh, round_, logs, consumer, group)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 5: Commit**

```bash
git add apps/game/engine/round.py apps/realtime/handlers/game.py
git commit -m "feat: add grace timer and night auto-transition logic"
```

---

### Task 5: Update `SunSet`/`SunRise`/`VoteResultStarted` events with `required_actions`

**Files:**
- Modify: `apps/realtime/events/game.py`

**Interfaces:**
- Produces: Updated `SunSet`, `SunRise`, `VoteResultStarted` outbound events with `required_actions: list[dict[str, Any]]` field

- [ ] **Step 1: Update event dataclasses**

```python
# apps/realtime/events/game.py — update these three classes

class SunSet(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.SUN_SET
    player_ids: list[int]
    logs: list[dict[str, Any]]
    required_actions: list[dict[str, Any]] = []


class SunRise(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.SUN_RISE
    player_ids: list[int]
    logs: list[dict[str, Any]]
    required_actions: list[dict[str, Any]] = []


class VoteResultStarted(OutboundEvent):
    channel_type: ClassVar[str] = GameEvents.VOTE_RESULT_STARTED
    lynch_target_id: int
    logs: list[dict[str, Any]]
    required_actions: list[dict[str, Any]] = []
```

- [ ] **Step 2: Run tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 3: Commit**

```bash
git add apps/realtime/events/game.py
git commit -m "feat: add required_actions field to phase-change events"
```

---

### Task 6: Personalized trampolines and night handler auto-transition wiring

**Files:**
- Modify: `apps/realtime/handlers/game.py`

**Interfaces:**
- Consumes: `get_required_actions_for_player()` from Task 4, updated events from Task 5
- Produces: Personalized events per consumer in trampolines; auto-transition triggers in night action handlers

- [ ] **Step 1: Update `sun_set` trampoline to personalize**

```python
@trampoline(GameEvents.SUN_SET)
async def sun_set(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        SunSet(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )
```

- [ ] **Step 2: Update `sun_rise` trampoline to personalize**

```python
@trampoline(GameEvents.SUN_RISE)
async def sun_rise(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        SunRise(
            player_ids=event['player_ids'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )
```

- [ ] **Step 3: Update `vote_result_started` trampoline to personalize**

```python
@trampoline(GameEvents.VOTE_RESULT_STARTED)
async def vote_result_started(consumer: RealtimeConsumer, event: dict) -> None:
    game_session = await GameSession.load(room_id=consumer.code)
    required_actions: list[dict[str, Any]] = []
    if game_session is not None:
        round_ = game_session.current_round()
        required_actions = round_.get_required_actions_for_player(consumer.user.id)
    await consumer.send_json(
        VoteResultStarted(
            lynch_target_id=event['lynch_target_id'],
            logs=event.get('logs', []),
            required_actions=required_actions,
        ).to_json()
    )
```

- [ ] **Step 4: Wire auto-transition into each night action handler**

In each of `handle_kill`, `handle_heal`, `handle_shoot`, `handle_detect`, `handle_silent` — after adding the action, add:

```python
    await _try_auto_transition_night(consumer, game_session)
```

For example, `handle_kill` becomes:

```python
@on(Kill)
async def handle_kill(consumer: RealtimeConsumer, event: Kill) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.KILL)
    )
    await _try_auto_transition_night(consumer, game_session)
```

Apply the same `await _try_auto_transition_night(consumer, game_session)` line to:
- `handle_heal`
- `handle_shoot`
- `handle_detect`
- `handle_silent`

And add it to `handle_roleblock` (which doesn't exist yet but uses ROLEBLOCK — we'll add it now):

```python
@on(Roleblock)
async def handle_roleblock(consumer: RealtimeConsumer, event: Roleblock) -> None:
    if not await _guard_phase(consumer, Phase.NIGHT):
        return
    game_session = await _require_game(consumer)
    if game_session is None:
        return
    await game_session.current_round().add_action(
        Action(actor_id=consumer.user.id, target_id=event.target_id, action_type=ActionType.ROLEBLOCK)
    )
    await _try_auto_transition_night(consumer, game_session)
```

- [ ] **Step 5: Add missing `Roleblock` inbound event and `SUBMIT_NIGHT` event**

In `apps/realtime/events/game.py`, add:

```python
class Roleblock(InboundEvent):
    type: ClassVar[str] = GameEvents.ROLEBLOCK
    target_id: int
```

And add `ROLEBLOCK = 'roleblock'` and `SUBMIT_NIGHT = 'submit_night'` to `GameEvents` enum:

```python
class GameEvents(StrEnum):
    # ... existing entries ...
    ROLEBLOCK = 'roleblock'
    SUBMIT_NIGHT = 'submit_night'
```

- [ ] **Step 6: Run tests**

```bash
cd backend && uv run pytest tests/ -x -q
```

- [ ] **Step 7: Commit**

```bash
git add apps/realtime/handlers/game.py apps/realtime/events/game.py
git commit -m "feat: personalize phase-change events and wire night auto-transition"
```

---

### Task 7: Integration validation

- [ ] **Step 1: Start the server and verify startup**

```bash
cd backend && timeout 5 python manage.py runserver 2>&1 || true
```
Expected: no import errors.

- [ ] **Step 2: Run full test suite**

```bash
cd backend && uv run pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 3: Verify obligations serialization round-trip**

```python
# Quick manual test via pytest:
# tests/game/test_obligations.py

import pytest
from apps.game.engine.constants import Phase, ActionType, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import MafiaGodfather, TownDoctor, TownVanilla
from apps.game.engine.round import GameRound


class TestObligations:
    def test_night_obligations_godfather_and_doctor(self):
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
            Player(id=3, role=TownVanilla()),
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        
        # Godfather must kill
        assert ActionType.KILL in round_.obligations.get(1, [])
        # Doctor must heal
        assert ActionType.HEAL in round_.obligations.get(2, [])
        # Vanilla has no night obligations
        assert 3 not in round_.obligations

    def test_mafia_kill_priority_chain(self):
        from apps.game.engine.roles.type import MafiaRoleblocker, MafiaMember
        
        players = [
            Player(id=1, role=MafiaMember()),       # priority 3
            Player(id=2, role=MafiaRoleblocker()),  # priority 2
            Player(id=3, role=MafiaGodfather()),    # priority 1
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        
        # Only Godfather (priority 1) gets KILL obligation
        assert ActionType.KILL in round_.obligations.get(3, [])
        assert ActionType.KILL not in round_.obligations.get(2, [])
        assert ActionType.KILL not in round_.obligations.get(1, [])

    def test_mafia_kill_fallback_when_godfather_dead(self):
        from apps.game.engine.roles.type import MafiaRoleblocker, MafiaMember
        
        players = [
            Player(id=1, role=MafiaMember(), status=PlayerStatus.ALIVE),
            Player(id=2, role=MafiaRoleblocker(), status=PlayerStatus.ALIVE),
            Player(id=3, role=MafiaGodfather(), status=PlayerStatus.DEAD),
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        
        # Roleblocker (priority 2) gets KILL since Godfather is dead
        assert ActionType.KILL in round_.obligations.get(2, [])
        assert ActionType.KILL not in round_.obligations.get(1, [])

    def test_day_all_alive_must_vote(self):
        players = [
            Player(id=1, role=TownVanilla()),
            Player(id=2, role=TownVanilla(), status=PlayerStatus.DEAD),
            Player(id=3, role=TownDoctor()),
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.DAY)
        round_.compute_obligations()
        
        assert ActionType.VOTE in round_.obligations.get(1, [])
        assert ActionType.VOTE in round_.obligations.get(3, [])
        # Dead player has no obligations
        assert 2 not in round_.obligations

    def test_is_player_done(self):
        players = [
            Player(id=1, role=TownDoctor()),
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        
        assert not round_.is_player_done(1)
        
        from apps.game.engine.action import Action
        round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.HEAL))
        assert round_.is_player_done(1)

    def test_is_round_done(self):
        players = [
            Player(id=1, role=MafiaGodfather()),
            Player(id=2, role=TownDoctor()),
        ]
        round_ = GameRound(round_number=1, members=players, phase=Phase.NIGHT)
        round_.compute_obligations()
        assert not round_.is_round_done()
        
        from apps.game.engine.action import Action
        round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.KILL))
        assert not round_.is_round_done()
        
        round_.night_actions.append(Action(actor_id=2, target_id=1, action_type=ActionType.HEAL))
        assert round_.is_round_done()
```

- [ ] **Step 4: Run the obligation tests**

```bash
cd backend && uv run pytest tests/game/test_obligations.py -v
```
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/game/test_obligations.py
git commit -m "test: add obligation tracking unit tests"
```
