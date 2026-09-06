# Night/Day Action Aggregation — Design

## Overview

A player may submit an action and then change their mind in the same phase
(e.g. the Mafia Godfather "Mafia King" kills player A, then re-submits to kill
player B). The engine must consider only the **last** submitted action per
`(player, action_type)`, not apply every submission. This change deduplicates
actions at **resolution time** so that only the final intent takes effect, while
full history is preserved in Redis for reconnect/log display.

It also fixes a related bug: multiple distinct mafia members could each submit a
KILL, causing multiple deaths in one night. Only the **designated killer's**
KILL may take effect.

---

## 1. Aggregation Rule

Actions are collapsed by key `(actor_id, action_type)`, keeping the **last**
occurrence:

```python
def _last_actions(self, actions: list[Action]) -> list[Action]:
    seen: dict[tuple[int, ActionType], Action] = {}
    for a in actions:
        seen[(a.actor_id, a.action_type)] = a
    return list(seen.values())
```

- The Godfather's last KILL wins; earlier KILL targets are ignored.
- A Roleblocker keeps **both** their last KILL and last ROLEBLOCK (different
  action types), as required by their obligations.
- Day votes are deduplicated the same way (this already happened via the
  `actor_votes[actor_id] = target_id` dict, but now it is centralized and also
  cleans up the returned `logs`).

Dedup happens at resolution, not submission, so:
- History in Redis (`night_actions` / `day_actions`) stays intact.
- Live broadcasts (`NightAction`, `VoteCast`) still fire per submission, so
  teammates see each change-of-mind in real time.

---

## 2. Designated Mafia Killer

`compute_obligations()` already assigns `KILL` to exactly one alive mafia member
(the lowest `priority` number: Godfather → Roleblocker → Member). Resolution now
derives that player from `self.obligations`:

```python
designated_killer = next(
    (pid for pid, types in self.obligations.items() if ActionType.KILL in types),
    None,
)
```

Only a KILL whose `actor_id == designated_killer` takes effect. A KILL submitted
by any other mafia member is ignored. `SHOOT` (Vigilante) is unaffected.

---

## 3. Resolution Changes by Round

### NightRound.resolve

```
await self._merge_pending_actions()
actions = self._last_actions(self.night_actions)
designated_killer = <derived from self.obligations>

1. ROLEBLOCK — iterate actions, collect blocked set
2. HEAL      — iterate actions, skip if actor blocked
3. Offensive — SHOOT: apply as before
               KILL: skip unless actor_id == designated_killer, then apply
               (both still skip if actor blocked; KILL/SHOOT still respect heal)
4. DETECT    — iterate actions, skip if actor blocked
```

### DayRound.resolve

```
await self._merge_pending_actions()
actions = self._last_actions(self.day_actions)
build actor_votes and logs from actions (one entry per (actor, VOTE))
tally; if lynch target, append LYNCH action and log (unchanged)
```

### VoteResultRound.resolve

```
await self._merge_pending_actions()
actions = self._last_actions(self.day_actions)   # REVENGE actions
apply lynch, then each REVENGE (deduped, one per actor)
```

---

## 4. Files to Change

| File | Change |
|------|--------|
| `apps/game/engine/round.py` | Add `_last_actions` helper to `GameRound`; use it in `NightRound.resolve`, `DayRound.resolve`, `VoteResultRound.resolve`; add designated-killer gate for KILL |
| `tests/game/test_aggregation.py` (new) | Unit tests for dedup + designated-killer behavior |

No changes to handlers, events, session, Redis keys, or live broadcasts.

---

## 5. Testing

Add `tests/game/test_aggregation.py` following the `test_obligations.py` pattern
(direct `NightRound`/`DayRound`/`VoteResultRound` construction, no Redis):

1. **Night change-of-mind kill** — Godfather submits KILL A then KILL B; only B
   dies.
2. **Night change-of-mind heal** — Doctor HEALs A then B; only B is healed (and
   a KILL on A is not healed).
3. **Roleblocker keeps both actions** — last KILL and last ROLEBLOCK both apply.
4. **Non-designated killer ignored** — Godfather (designated) and Roleblocker each
   KILL different targets; only the Godfather's target dies.
5. **Day vote change-of-mind** — player votes A then B; tally counts B.
6. **Revenge dedup** — Bomb submits REVENGE A then B; only B dies.
