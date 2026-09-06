# Required Actions Per Round — Design

## Overview

Define for each role which actions are available, required vs. optional, and with
what priority. The engine enforces that all required actions are completed before
a phase can transition, emits personalized phase-change events per player, and
uses phase-specific transition triggers (auto for Night/VoteResult, host-triggered for Day).

---

## 1. Role Action Configuration

Each role class carries an `actions` dict mapping `Phase` → list of `ActionConfig`:

```python
@dataclass
class ActionConfig:
    action_type: ActionType   # KILL, HEAL, DETECT, VOTE, etc.
    required: bool            # True = must submit before phase transition
    priority: int | None      # lower = higher priority; used for fallback chains (mafia kill)
```

### Full mapping

| Role              | Phase        | Action     | Required | Priority |
|-------------------|-------------|------------|----------|----------|
| MafiaGodfather    | NIGHT        | KILL       | Yes      | 1        |
|                   | DAY          | VOTE       | Yes      | —        |
| MafiaRoleblocker  | NIGHT        | KILL       | Yes      | 2        |
|                   | NIGHT        | ROLEBLOCK  | Yes      | —        |
|                   | DAY          | VOTE       | Yes      | —        |
| MafiaMember       | NIGHT        | KILL       | Yes      | 3        |
|                   | DAY          | VOTE       | Yes      | —        |
| TownDoctor        | NIGHT        | HEAL       | Yes      | —        |
|                   | DAY          | VOTE       | Yes      | —        |
| TownCop           | NIGHT        | DETECT     | Yes      | —        |
|                   | DAY          | VOTE       | Yes      | —        |
| TownVigilante     | NIGHT        | SHOOT      | No       | —        |
|                   | DAY          | VOTE       | Yes      | —        |
| TownBomb          | VOTE_RESULT  | REVENGE    | Yes      | —        |
|                   | DAY          | VOTE       | Yes      | —        |
| TownVanilla       | DAY          | VOTE       | Yes      | —        |

**Mafia KILL priority chain:** at obligation time, the engine picks the
highest-priority (lowest number) alive mafia whose config includes KILL. Only
that player gets KILL as a required action. If Godfather is dead, falls to
Roleblocker, then Member. Only one KILL per night.

---

## 2. Phase Transition Logic

### Night — Auto-transition

```
Player submits required action → check "all required done?"
  → NO: wait for remaining players
  → YES: start 5-second grace timer (optional actions like SHOOT can still arrive)
         → timer expires → resolve night → emit personalized SunRise → new DAY round
```

No host trigger needed.

### Day — Host-triggered

```
Host calls SubmitVotes → engine checks "all alive players voted?"
  → NO: reject with list of missing player IDs
  → YES: resolve vote tally
         → lynch target exists → new VOTE_RESULT round
         → no lynch target     → new NIGHT round (emit personalized SunSet)
```

### Vote Result — Auto-transition

```
Enter VOTE_RESULT (lynch target from day)
  → If lynched player has on-death required actions (TownBomb → REVENGE):
      that dead player must submit REVENGE
  → Once all required VOTE_RESULT actions done → 5s grace → auto-resolve
  → Resolve: carry out lynch + revenge kills → emit personalized SunSet → new NIGHT
```

The VOTE_RESULT phase uniquely tracks required actions for a **dead** player
(the lynched Bomb). Obligation is tied to "lynched this round" not "alive."

---

## 3. Personalized Phase-Change Events

`SunSet`, `SunRise`, `VoteResultStarted` are emitted **per player** with only
that player's required actions and valid target options.

### Example: Night begins (SunSet)

```json
// Godfather
{"type":"sun_set","round":2,"alive_player_ids":[1,2,3,4,5,6,7],
 "required_actions":[{"action_type":"kill","target_options":[2,3,5,6,7]}]}

// Doctor
{"type":"sun_set","round":2,"alive_player_ids":[1,2,3,4,5,6,7],
 "required_actions":[{"action_type":"heal","target_options":[1,2,3,4,5,6,7]}]}

// Vanilla (no night actions)
{"type":"sun_set","round":2,"alive_player_ids":[1,2,3,4,5,6,7],
 "required_actions":[]}

// Dead player
{"type":"sun_set","round":2,"alive_player_ids":[1,2,3,4,5,6,7],
 "required_actions":[]}
```

### Example: Day begins (SunRise)

```json
// Every alive player
{"type":"sun_rise","round":2,"alive_player_ids":[1,2,3,4,5,6,7],
 "required_actions":[{"action_type":"vote","target_options":[1,2,3,4,5,6,7]}]}
```

### Example: Vote result (only the lynched Bomb)

```json
{"type":"vote_result_started","round":2,"lynch_target_id":3,
 "required_actions":[{"action_type":"revenge","target_options":[1,2,4,5,6,7]}]}
```

---

## 4. Round Obligation Tracking

`GameRound` gains two new responsibilities:

- **`obligations`** — computed at round start: which player IDs must submit which
  actions. Resolves mafia KILL priority chain at this point (who is the designated
  killer?).

- **`is_round_done()`** — true when every obligated player has submitted all
  their required actions. For Night/VoteResult this triggers the 5s grace timer.
  For Day this gates `SubmitVotes` validation.

- **`is_player_done(player_id)`** — true when a specific player has submitted
  all their individual required actions.

---

## 5. Files to Change

| File | Change |
|------|--------|
| `apps/game/engine/constants.py` | Add `ActionConfig` dataclass |
| `apps/game/engine/roles/type.py` | Add `actions` dict to each role class |
| `apps/game/engine/round.py` | Add obligation tracking, `is_round_done()`, `is_player_done()`, grace timer, auto-transition for Night/VoteResult |
| `apps/game/engine/session.py` | Minor: round initialization passes players with roles |
| `apps/game/engine/player.py` | Minor: may need `is_alive` helper |
| `apps/realtime/handlers/game.py` | Update trampolines to emit personalized events; add Night auto-transition trigger on action |
| `apps/realtime/events/game.py` | Update `SunSet`/`SunRise`/`VoteResultStarted` dataclasses with `required_actions` field |
