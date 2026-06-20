"""End-to-end WebSocket game flow test.

Usage: uv run python test_ws.py <session_id> [user_id_offset]
"""
import asyncio
import json
import sys
import urllib.request

import websockets

BASE = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

SESSION_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 8
OFFSET = int(sys.argv[2]) if len(sys.argv) > 2 else 7

USER_IDS = {
    "alice": OFFSET,
    "bob": OFFSET + 1,
    "charlie": OFFSET + 2,
    "diana": OFFSET + 3,
}


def get_token_sync(username):
    data = json.dumps({"username": username, "password": "testpass123"}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/accounts/token/",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access"]


async def recv_with_timeout(ws, timeout=5):
    """Receive a message or raise on timeout."""
    return json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))


async def main():
    tokens = {}
    for name in ["alice", "bob", "charlie", "diana"]:
        tokens[name] = get_token_sync(name)
    print("✓ Tokens obtained for all 4 players")

    # ── Connect all 4 players ──
    connections = {}
    roles = {}

    for name in tokens:
        ws = await websockets.connect(
            f"{WS_BASE}/ws/game/{SESSION_ID}/?token={tokens[name]}"
        )
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "your_role", f"{name}: got {msg}"
        roles[name] = msg["role"]
        connections[name] = ws

    print(f"✓ All 4 connected. Roles: {roles}")
    assert roles["alice"] == "mafia"
    assert roles["bob"] == "detective"
    assert roles["charlie"] == "doctor"
    assert roles["diana"] == "villager"
    print("✓ Role assignments verified")

    ws_alice = connections["alice"]
    ws_bob = connections["bob"]
    ws_charlie = connections["charlie"]

    # ── Non-host phase advance ignored ──
    await ws_bob.send(json.dumps({"type": "next_phase"}))
    await asyncio.sleep(0.3)
    print("✓ Non-host phase advance ignored")

    # ── Detective investigates ──
    await ws_bob.send(json.dumps({"type": "detective_investigate", "target_id": USER_IDS["alice"]}))
    result = await recv_with_timeout(ws_bob)
    assert result["type"] == "investigation_result" and result["is_mafia"] is True
    print("✓ Detective identified alice as mafia")

    await ws_bob.send(json.dumps({"type": "detective_investigate", "target_id": USER_IDS["diana"]}))
    result = await recv_with_timeout(ws_bob)
    assert result["is_mafia"] is False
    print("✓ Detective correctly ID'd diana as not mafia")

    # ── Doctor protects diana ──
    await ws_charlie.send(json.dumps({"type": "doctor_protect", "target_id": USER_IDS["diana"]}))
    print("✓ Doctor protected diana")

    # ── Mafia kills diana ──
    await ws_alice.send(json.dumps({"type": "mafia_kill", "target_id": USER_IDS["diana"]}))
    print("✓ Mafia voted to kill diana")

    # ── Phase: NIGHT → DAY (resolve_night runs) ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))

    # resolve_night runs AFTER phase_changed broadcast.
    # Doctor protects diana → no kill, so only phase_changed is sent.
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed", f"{name}: got {msg}"
        assert msg["phase"] == "day", f"{name}: phase={msg['phase']}"
    print("✓ Phase → day (diana survived via doctor protection)")

    # ── Phase: DAY → DISCUSSION ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed", f"{name}: got {msg['type']}"
        assert msg["phase"] == "discussion", f"{name}: phase={msg.get('phase')}"
    print("✓ Phase → discussion")

    # ── Phase: DISCUSSION → VOTING ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed", f"{name}: got {msg['type']}"
        assert msg["phase"] == "voting"
    print("✓ Phase → voting")

    # ── Vote during VOTING ──
    await ws_bob.send(json.dumps({"type": "vote", "target_id": USER_IDS["alice"]}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "vote_cast", f"{name}: got {msg}"
        assert msg["user_id"] == USER_IDS["bob"]
        assert msg["target_id"] == USER_IDS["alice"]
    print("✓ Vote cast and broadcast to all")

    # ── Phase: VOTING → NIGHT (round 2) ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed", f"{name}: got {msg['type']}"
        assert msg["phase"] == "night"
        assert msg["round_number"] == 2
    print("✓ Phase → night (round 2)")

    # ── Round 2: Mafia kills diana, no doctor protect → expect kill ──
    await ws_alice.send(json.dumps({"type": "mafia_kill", "target_id": USER_IDS["diana"]}))
    await ws_alice.send(json.dumps({"type": "next_phase"}))

    # Everyone gets phase_changed day, then player_killed for diana
    killed_received = {name: False for name in connections}
    for name, ws in connections.items():
        msg1 = await recv_with_timeout(ws)
        msg2 = await recv_with_timeout(ws)
        for msg in [msg1, msg2]:
            if msg["type"] == "phase_changed":
                assert msg["phase"] == "day"
            elif msg["type"] == "player_killed":
                assert msg["user_id"] == USER_IDS["diana"]
                killed_received[name] = True
        assert killed_received[name], f"{name} did not receive player_killed"
    print("✓ Round 2: diana killed, all players notified")

    # diana is dead, should not be able to reconnect
    await connections["diana"].close()
    del connections["diana"]
    try:
        ws = await websockets.connect(
            f"{WS_BASE}/ws/game/{SESSION_ID}/?token={tokens['diana']}"
        )
        await ws.recv()
        print("✗ Dead player should not connect")
        await ws.close()
        return
    except Exception:
        print("✓ Dead player rejected on reconnect")

    # ── Phase: DAY → DISCUSSION ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed" and msg["phase"] == "discussion"
    print("✓ Phase → discussion")

    # ── Phase: DISCUSSION → VOTING ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed" and msg["phase"] == "voting"
    print("✓ Phase → voting")

    # ── Advance to night round 3 ──
    await ws_alice.send(json.dumps({"type": "next_phase"}))
    for name, ws in connections.items():
        msg = await recv_with_timeout(ws)
        assert msg["type"] == "phase_changed" and msg["phase"] == "night"
        assert msg["round_number"] == 3
    print("✓ Phase → night (round 3)")

    # ── Clean up ──
    for ws in connections.values():
        await ws.close()

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED")
    print("=" * 50)


asyncio.run(main())
