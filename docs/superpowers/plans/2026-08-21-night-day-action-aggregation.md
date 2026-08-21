# Night/Day Action Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate night/day actions at resolution time so a player's "change of mind" (re-submitting the same action type) applies only the LAST submission, and restrict night KILL to the single designated mafia killer.

**Architecture:** Add a `_last_actions` helper to `GameRound` that collapses a list of `Action` by key `(actor_id, action_type)` keeping the last occurrence. Call it at the top of each `resolve()` (after `_merge_pending_actions()`), and derive the designated killer from `self.obligations` to gate KILL. History in Redis and live broadcasts are untouched — dedup happens only at resolution.

**Tech Stack:** Python 3.14, Django 6, dataclasses, pytest + pytest-asyncio.

## Global Constraints

- Dedup happens at **resolution**, not submission — Redis history (`night_actions` / `day_actions`) stays intact and live broadcasts (`NightAction`, `VoteCast`) still fire per submission.
- Dedup key is `(actor_id, action_type)` — the Godfather's last KILL wins; a Roleblocker keeps both their last KILL and last ROLEBLOCK (different types).
- KILL takes effect only when `actor_id == designated_killer` (derived from `self.obligations`, lowest priority number: Godfather → Roleblocker → Member). `SHOOT` (Vigilante) is unaffected.
- No changes to handlers (`apps/realtime/handlers/game.py`), events, session, Redis keys, or live broadcasts.
- Python target is 3.14; follow existing `ruff` (single quotes, line-length 100) and `mypy` conventions.

---

### Task 1: Add `_last_actions` aggregation helper to `GameRound`

**Files:**
- Modify: `apps/game/engine/round.py` (add method to `GameRound`, after `alive_player_ids()` at line 79)
- Test: `tests/game/test_aggregation.py` (new)

**Interfaces:**
- Produces: `GameRound._last_actions(actions: list[Action]) -> list[Action]` — collapses `actions` by `(actor_id, action_type)`, returning the last occurrence of each key. Used by Tasks 2 and 3.

- [ ] **Step 1: Write the failing test**

Create `tests/game/test_aggregation.py`:

```python
from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase
from apps.game.engine.round import NightRound


def test_last_actions_keeps_last_occurrence():
    round_ = NightRound(round_number=1, members=[], phase=Phase.NIGHT)
    actions = [
        Action(actor_id=1, target_id=2, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=3, action_type=ActionType.KILL),
        Action(actor_id=1, target_id=5, action_type=ActionType.ROLEBLOCK),
        Action(actor_id=2, target_id=4, action_type=ActionType.KILL),
    ]

    result = round_._last_actions(actions)

    by_key = {(a.actor_id, a.action_type): a.target_id for a in result}
    assert by_key == {
        (1, ActionType.KILL): 3,
        (1, ActionType.ROLEBLOCK): 5,
        (2, ActionType.KILL): 4,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: FAIL with `AttributeError: 'NightRound' object has no attribute '_last_actions'`

- [ ] **Step 3: Write minimal implementation**

In `apps/game/engine/round.py`, add to `GameRound` immediately after `alive_player_ids()` (currently ends at line 79):

```python
    def _last_actions(self, actions: list[Action]) -> list[Action]:
        """Collapse actions by (actor_id, action_type), keeping the last occurrence."""
        seen: dict[tuple[int, ActionType], Action] = {}
        for a in actions:
            seen[(a.actor_id, a.action_type)] = a
        return list(seen.values())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/game/engine/round.py tests/game/test_aggregation.py
git commit -m "feat: add _last_actions aggregation helper to GameRound"
```

---

### Task 2: Night-round dedup + designated-killer gate

**Files:**
- Modify: `apps/game/engine/round.py` (`NightRound.resolve`, lines 245-286)
- Test: `tests/game/test_aggregation.py` (append tests)

**Interfaces:**
- Consumes: `self._last_actions` (Task 1), `self.obligations` (populated by `compute_obligations()`).
- Produces: `NightRound.resolve()` now dedupes `night_actions` and ignores KILL from non-designated killers.

- [ ] **Step 1: Write the failing tests**

Append to `tests/game/test_aggregation.py`:

```python
import pytest

from apps.game.engine.action import Action
from apps.game.engine.constants import ActionType, Phase, PlayerStatus
from apps.game.engine.player import Player
from apps.game.engine.roles.type import (
    MafiaGodfather,
    MafiaRoleblocker,
    TownDoctor,
    TownVanilla,
)
from apps.game.engine.round import NightRound


@pytest.mark.asyncio
async def test_night_change_of_mind_kill():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))

    logs = await round_.resolve()

    assert players[1].status == PlayerStatus.ALIVE  # first target survives
    assert players[2].status == PlayerStatus.DEAD   # final target dies
    kill_logs = [l for l in logs if l['action_type'] == 'kill']
    assert kill_logs == [{'target_id': 3, 'action_type': 'kill'}]


@pytest.mark.asyncio
async def test_night_change_of_mind_heal():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=TownDoctor()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.HEAL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.HEAL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.DEAD   # A killed (heal on A discarded)
    assert players[3].status == PlayerStatus.ALIVE  # B healed
    heal_logs = [l for l in logs if l['action_type'] == 'heal']
    assert heal_logs == [{'target_id': 4, 'action_type': 'heal'}]


@pytest.mark.asyncio
async def test_roleblocker_keeps_both_actions():
    players = [
        Player(id=1, role=MafiaRoleblocker()),
        Player(id=2, role=TownDoctor()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.ROLEBLOCK))
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=1, target_id=4, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.HEAL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.ALIVE  # abandoned kill target survives
    assert players[3].status == PlayerStatus.DEAD   # final kill target dies
    assert {'target_id': 2, 'action_type': 'roleblock'} in logs
    kill_logs = [l for l in logs if l['action_type'] == 'kill']
    assert kill_logs == [{'target_id': 4, 'action_type': 'kill'}]


@pytest.mark.asyncio
async def test_non_designated_killer_ignored():
    players = [
        Player(id=1, role=MafiaGodfather()),
        Player(id=2, role=MafiaRoleblocker()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = NightRound(round_number=1, members=players, phase=Phase.NIGHT)
    round_.compute_obligations()
    round_.night_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.KILL))
    round_.night_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.KILL))

    logs = await round_.resolve()

    assert players[2].status == PlayerStatus.DEAD   # Godfather's target dies
    assert players[3].status == PlayerStatus.ALIVE  # Roleblocker's kill ignored
    kill_logs = [l for l in logs if l['action_type'] == 'kill']
    assert kill_logs == [{'target_id': 3, 'action_type': 'kill'}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: `test_night_change_of_mind_kill` FAIL (target 2 also dies), `test_night_change_of_mind_heal` FAIL (target 3 healed), `test_roleblocker_keeps_both_actions` FAIL, `test_non_designated_killer_ignored` FAIL. `test_last_actions_keeps_last_occurrence` still passes.

- [ ] **Step 3: Write minimal implementation**

Replace `NightRound.resolve` (lines 245-286) with:

```python
    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        actions = self._last_actions(self.night_actions)
        designated_killer = next(
            (pid for pid, types in self.obligations.items() if ActionType.KILL in types),
            None,
        )
        logs: list[dict] = []
        blocked: set[int] = set()
        healed: set[int] = set()

        # 1. ROLEBLOCK
        for a in actions:
            if a.action_type == ActionType.ROLEBLOCK:
                blocked.add(a.target_id)
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 2. HEAL
        for a in actions:
            if a.action_type == ActionType.HEAL:
                if a.actor_id in blocked:
                    continue
                healed.add(a.target_id)
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        # 3. OFFENSIVE ACTIONS (KILL / SHOOT)
        for a in actions:
            if a.action_type in (ActionType.KILL, ActionType.SHOOT):
                if a.action_type == ActionType.KILL and a.actor_id != designated_killer:
                    continue
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
        for a in actions:
            if a.action_type == ActionType.DETECT:
                if a.actor_id in blocked:
                    continue
                logs.append({'target_id': a.target_id, 'action_type': a.action_type.value})

        await self._autosave()
        return logs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run existing game tests to check for regressions**

Run: `pytest tests/game/ -v`
Expected: PASS (all existing `test_obligations.py` tests still green)

- [ ] **Step 6: Commit**

```bash
git add apps/game/engine/round.py tests/game/test_aggregation.py
git commit -m "feat: dedup night actions and gate KILL to designated killer"
```

---

### Task 3: Day & vote-result dedup

**Files:**
- Modify: `apps/game/engine/round.py` (`DayRound.resolve`, lines 330-355; `VoteResultRound.resolve`, lines 417-435)
- Test: `tests/game/test_aggregation.py` (append tests)

**Interfaces:**
- Consumes: `self._last_actions` (Task 1).
- Produces: `DayRound.resolve()` and `VoteResultRound.resolve()` dedupe their action lists before tallying/applying.

- [ ] **Step 1: Write the failing tests**

Append to `tests/game/test_aggregation.py`:

```python
from apps.game.engine.roles.type import TownBomb
from apps.game.engine.round import DayRound, VoteResultRound


@pytest.mark.asyncio
async def test_day_vote_change_of_mind():
    players = [
        Player(id=1, role=TownVanilla()),
        Player(id=2, role=TownVanilla()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = DayRound(round_number=1, members=players, phase=Phase.DAY)
    round_.compute_obligations()
    round_.day_actions.append(Action(actor_id=1, target_id=2, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=1, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=3, target_id=3, action_type=ActionType.VOTE))
    round_.day_actions.append(Action(actor_id=4, target_id=2, action_type=ActionType.VOTE))

    logs = await round_.resolve()

    assert round_.lynch_target_id == 3
    vote_entries = [l for l in logs if l['action_type'] == 'vote']
    assert vote_entries == [
        {'actor_id': 1, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 2, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 3, 'target_id': 3, 'action_type': 'vote'},
        {'actor_id': 4, 'target_id': 2, 'action_type': 'vote'},
    ]


@pytest.mark.asyncio
async def test_revenge_dedup():
    players = [
        Player(id=1, role=TownVanilla()),
        Player(id=2, role=TownBomb()),
        Player(id=3, role=TownVanilla()),
        Player(id=4, role=TownVanilla()),
    ]
    round_ = VoteResultRound(
        round_number=1, members=players, phase=Phase.VOTE_RESULT, lynch_target_id=2
    )
    round_.compute_obligations()
    round_.day_actions.append(Action(actor_id=2, target_id=3, action_type=ActionType.REVENGE))
    round_.day_actions.append(Action(actor_id=2, target_id=4, action_type=ActionType.REVENGE))

    logs = await round_.resolve()

    assert players[1].status == PlayerStatus.DEAD   # lynched
    assert players[2].status == PlayerStatus.ALIVE  # abandoned revenge target survives
    assert players[3].status == PlayerStatus.DEAD   # final revenge target dies
    revenge_logs = [l for l in logs if l['action_type'] == 'revenge']
    assert revenge_logs == [{'actor_id': 2, 'target_id': 4, 'action_type': 'revenge'}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: `test_day_vote_change_of_mind` FAIL (vote log for actor 1 appears twice), `test_revenge_dedup` FAIL (both revenge targets die).

- [ ] **Step 3: Write minimal implementation**

In `DayRound.resolve` (lines 330-340), replace the merge + loop header:

```python
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
```

In `VoteResultRound.resolve` (lines 417-432), replace the merge + REVENGE loop:

```python
    async def resolve(self) -> list[dict]:
        await self._merge_pending_actions()
        actions = self._last_actions(self.day_actions)
        logs: list[dict] = []

        if self.lynch_target_id is not None:
            target = self._get_player(self.lynch_target_id)
            if target:
                target.status = PlayerStatus.DEAD
            logs.append({'actor_id': self.lynch_target_id, 'target_id': None, 'action_type': ActionType.LYNCH.value})

            for a in actions:
                if a.action_type == ActionType.REVENGE:
                    revenge_target = self._get_player(a.target_id)
                    if revenge_target:
                        revenge_target.status = PlayerStatus.DEAD
                    logs.append({'actor_id': a.actor_id, 'target_id': a.target_id, 'action_type': a.action_type.value})

        await self._autosave()
        return logs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/game/test_aggregation.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Run full game test suite + lint**

Run: `pytest tests/game/ -v && ruff check apps/game/engine/round.py tests/game/test_aggregation.py`
Expected: all tests green, no lint errors

- [ ] **Step 6: Commit**

```bash
git add apps/game/engine/round.py tests/game/test_aggregation.py
git commit -m "feat: dedup day votes and revenge actions at resolution"
```

---

## Self-Review

**Spec coverage:**
- §1 Aggregation rule (`_last_actions` by `(actor_id, action_type)`) → Task 1 + used in Tasks 2/3. ✅
- §2 Designated mafia killer gate → Task 2 (`test_non_designated_killer_ignored`). ✅
- §3.1 NightRound.resolve dedup → Task 2. ✅
- §3.2 DayRound.resolve dedup → Task 3. ✅
- §3.3 VoteResultRound.resolve dedup → Task 3. ✅
- §4 Files to change (`round.py` + new `tests/game/test_aggregation.py`) → covered across tasks. ✅
- §5 Six test scenarios → `test_night_change_of_mind_kill`, `test_night_change_of_mind_heal`, `test_roleblocker_keeps_both_actions`, `test_non_designated_killer_ignored`, `test_day_vote_change_of_mind`, `test_revenge_dedup` (plus a direct `_last_actions` unit test). ✅

**Placeholder scan:** No TBD/TODO; every code step contains full code. ✅

**Type consistency:** `_last_actions(self, actions: list[Action]) -> list[Action]` is consistent across Tasks 1-3; `designated_killer` is `int | None` derived from `self.obligations`. ✅
