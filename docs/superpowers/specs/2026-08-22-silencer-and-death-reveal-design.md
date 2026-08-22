# Silencer Voice-Mute & Death Role-Reveal — Design

## Overview

Two game-mechanic changes, combined into one spec because they both fire from
the same resolution choke point (`_transition_after_resolve` in
`apps/realtime/handlers/game.py`):

1. **Silencer voice-mute.** The Mafia Silencer's `silence` action no longer
   blocks the target's night actions (the current "roleblock" behavior). Instead
   it physically mutes the target's voice in the Cloudflare Realtime Kit WebRTC
   meeting for the duration of the following day, then unmutes them at the next
   night resolution.

2. **Death role-reveal.** When a player dies, (a) the dead player is privately
   sent the full roster — every player's role — since they are no longer playing,
   and (b) the dead player's own role is revealed publicly to everyone in the
   room (playing and non-playing members alike).

---

## 1. Silencer Voice-Mute

### 1.1 Current behavior (to be removed)

`NightRound.resolve()` (`apps/game/engine/round.py`) treats `SILENCE` as a
roleblock: it builds a `blocked` set and skips HEAL / KILL / SHOOT / DETECT for
any actor in that set. This is the behavior we are dropping.

### 1.2 New behavior

- `SILENCE` no longer affects night-action resolution in any way. It only
  produces a log entry (`{'target_id', 'action_type': 'silence'}`) for the
  night log.
- At the **end of the night phase** (after everything has resolved), the
  silenced target is muted in WebRTC. They remain muted through the following
  day discussion, then are unmuted at the **end of the next night**.

### 1.3 Lifecycle

```
Night N        Silencer casts silence → target X.
Night N end    X is muted (preset → "silent_players").
Day N+1        X cannot speak.
Night N+1      X acts normally (mute never blocks actions).
Night N+1 end  X is unmuted (preset → "group_call_host").
Day N+2        X can speak again.
```

### 1.4 Tracking muted players

A new field on `GameSession` records who is currently muted:

```python
# apps/game/engine/session.py
@dataclass
class GameSession:
    ...
    silenced_player_ids: list[int] = field(default_factory=list)
```

- Serialized in `to_dict()` as `'silenced_player_ids'`.
- Hydrated in `from_dict()` with `data.get('silenced_player_ids', [])` (so
  existing Redis sessions without the field still load).

A new helper on `NightRound` extracts the targets silenced *this* night:

```python
# apps/game/engine/round.py — NightRound
def silenced_target_ids(self) -> list[int]:
    actions = self._last_actions(self.night_actions)
    return [
        a.target_id for a in actions
        if a.action_type == ActionType.SILENCE
        and a.target_id in self.alive_player_ids()
    ]
```

(Filtering to alive targets means we never try to mute a player who just died.)

### 1.5 Applying mute / unmute

Add a `preset_name`-aware edit method to the WebRTC wrapper, mirroring the
existing `add_participant` shape:

```python
# apps/core/webrtc.py — WebRTCClient
def edit_participant(self, meeting_id: str, participant_id: str, preset_name: str) -> None:
    self.client.realtime_kit.meetings.edit_participant(
        account_id=self.account_id,
        app_id=self.app_id,
        meeting_id=meeting_id,
        participant_id=participant_id,
        preset_name=preset_name,
    )
```

The actual mute/unmute happens in the **NIGHT branch** of
`_transition_after_resolve` (`apps/realtime/handlers/game.py`), *before*
`new_round(Phase.DAY)`:

```python
async def _apply_silence(consumer, game_session, round_) -> None:
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
```

Notes:

- `participant_id` is `str(player.id)`, consistent with how
  `_connect_as_member` registers participants.
- WebRTC calls are synchronous, matching the existing `add_participant` usage;
  they run in the `_resolve_after_grace` background task, so the brief block is
  acceptable.
- The preset names are `'silent_players'` (mute) and `'group_call_host'`
  (unmute, the default preset used at registration).

### 1.6 Role description

Update `MafiaSilencer.description` from "preventing them from acting" to
reflect the new mechanic, e.g. "Silences one player each night, muting their
voice for the following day."

---

## 2. Death Role-Reveal

### 2.1 What is revealed

On each death:

1. **To the dead player (private):** the full roster — `id`, `role_code`,
   `role_name`, `role_type`, `description` for every player in the game.
2. **To everyone in the room (public):** the dead player's own role (code,
   name, type, description).

The public audience is `RoomActive` (accepted members), matching every other
room-wide event. This is a **one-time snapshot** at the moment of death — the
dead player does not become a live spectator of future secret events.

### 2.2 New outbound events

```python
# apps/realtime/events/game.py
class RoleRevealed(OutboundEvent):      # public: dead player's role
    channel_type: ClassVar[str] = GameEvents.ROLE_REVEALED
    player_id: int
    role_code: str
    role_name: str
    role_type: str
    description: str

class RolesRevealed(OutboundEvent):     # private: full roster to the dead player
    channel_type: ClassVar[str] = GameEvents.ROLES_REVEALED
    players: list[dict[str, Any]]
```

Add `ROLE_REVEALED = 'role_revealed'` and `ROLES_REVEALED = 'roles_revealed'`
to `GameEvents`.

### 2.3 New channel group

A per-player group lets us reach a specific dead player without leaking the
roster in a room-wide broadcast:

```python
# apps/realtime/groups.py
@dataclass(frozen=True, slots=True)
class GameSessionPlayer(GroupScope):
    room_code: str
    session_id: str
    player_id: int

    @property
    def name(self) -> str:
        return f'room.{self.room_code}.session.{self.session_id}.player.{self.player_id}'
```

Each player joins their own `GameSessionPlayer` group when the game starts
(`game_started` trampoline) and on reset (`game_reset` trampoline), alongside
the existing `GameSessionGroup` join.

### 2.4 Detecting deaths

Deaths are detected by diffing the alive set before and after `resolve()`:

```python
newly_dead = alive_before - round_.alive_player_ids()
```

This captures all death sources uniformly — night KILL/SHOOT and vote-result
LYNCH/REVENGE — because both resolve through `_resolve_after_grace`.

To make `alive_before` available, capture it **before** `resolve()` at both call
sites and pass it into `_transition_after_resolve`:

- `_resolve_after_grace`: `alive_before = round_.alive_player_ids()` immediately
  before `logs = await round_.resolve()`.
- `handle_submit_votes` (no-lynch branch): same capture before its
  `resolve()` call (produces an empty diff, but keeps the signature uniform).

### 2.5 Firing the reveal

Inside `_transition_after_resolve`, fire reveals **before** the winner check so
the final death that ends the game is still revealed (the session is flushed
only after):

```python
newly_dead = alive_before - round_.alive_player_ids()
for dead_id in newly_dead:
    await _reveal_death(consumer, game_session, dead_id)
```

`_reveal_death` builds the roster from the already-loaded `game_session` (avoiding
a race with the game-over `flush()`) and emits:

```python
async def _reveal_death(consumer, game_session, dead_id) -> None:
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

---

## 3. Resolution Order in `_transition_after_resolve`

The consolidated flow (NIGHT and VOTE_RESULT both land here via
`_resolve_after_grace`):

```
1. newly_dead = alive_before - round_.alive_player_ids()
2. for each dead player: _reveal_death(...)
3. winner = game_session.check_winner()
   if winner: emit GameOver → flush → clear game_session_id → return
4. if NIGHT:
       _apply_silence(...)        # mute/unmute before the day starts
       new_round(DAY) → emit SunRise
   else:
       new_round(NIGHT) → emit SunSet
```

Death reveals happen before the winner check so the game-ending kill/lynch is
still revealed; silence is applied at the NIGHT→DAY boundary only.

---

## 4. Files to Change

| File | Change |
|------|--------|
| `apps/core/webrtc.py` | Add `edit_participant(meeting_id, participant_id, preset_name)` |
| `apps/game/engine/session.py` | Add `silenced_player_ids` field + serialize/hydrate |
| `apps/game/engine/round.py` | Remove `blocked` roleblock logic from `NightRound.resolve`; add `silenced_target_ids()` |
| `apps/game/engine/roles/type.py` | Update `MafiaSilencer.description` |
| `apps/realtime/groups.py` | Add `GameSessionPlayer` scope |
| `apps/realtime/events/game.py` | Add `ROLE_REVEALED`/`ROLES_REVEALED` enums + `RoleRevealed`/`RolesRevealed` events |
| `apps/realtime/handlers/game.py` | Add `_apply_silence`/`_reveal_death`; thread `alive_before` into `_transition_after_resolve`; join `GameSessionPlayer` in `game_started`/`game_reset` trampolines |
| `tests/game/test_aggregation.py` | Update `test_silencer_keeps_both_actions` for voice-mute-only semantics |

---

## 5. Testing

### Engine tests (existing pattern: direct `NightRound` construction, no Redis)

1. **Update `test_silencer_keeps_both_actions`** — silence no longer blocks the
   Doctor's heal. The healed target now survives and the kill log carries
   `result: 'healed'`:

   ```python
   assert players[3].status == PlayerStatus.ALIVE  # healed (silence no longer blocks)
   kill_logs == [{'target_id': 4, 'action_type': 'kill', 'result': 'healed'}]
   ```

2. **New `test_silenced_target_ids`** — a `NightRound` with a SILENCE action on a
   living target returns that id; a SILENCE on a dead target is filtered out.

### Handler-level logic (manual / integration)

The WebRTC mute/unmute calls and group-broadcast reveals live in
`handlers/game.py` and are not covered by the engine test suite (which the repo
keeps at the engine level). They are validated against the running Cloudflare
Realtime Kit meeting and Channels group routing.

---

## 6. Out of Scope

- Muting or removing dead players' voice — a dead player's WebRTC state is not
  touched here (only their role is revealed).
- Re-delivering the death snapshot on reconnect — the reveal is one-time.
- Any `silence` blocking of actions beyond what already exists (all blocking is
  removed).
