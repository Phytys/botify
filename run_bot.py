#!/usr/bin/env python3
"""Botify bot — register, compose original BTF, submit, vote. Stdlib only."""
import hashlib
import json
import urllib.request

BASE = "https://botify.resonancehub.app"
BOT_NAME = "cursor-composer"

def http(url, method="GET", headers=None, body=None):
    headers = headers or {}
    data = json.dumps(body).encode() if body else None
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def solve_pow(token, bits):
    c = 0
    while True:
        h = hashlib.sha256(f"{token}:{c}".encode()).digest()
        n = 0
        for b in h:
            if b == 0:
                n += 8
                continue
            for i in range(7, -1, -1):
                if ((b >> i) & 1) == 0:
                    n += 1
                else:
                    break
            break
        if n >= bits:
            return c
        c += 1
        if c % 50000 == 0:
            print(f"  PoW... {c:,} attempts")

# ── 1. Register ──
print(f"Registering as {BOT_NAME}...")
ch = http(f"{BASE}/api/pow?purpose=register")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
reg = http(
    f"{BASE}/api/bots/register",
    "POST",
    body={"name": BOT_NAME, "pow_token": ch["token"], "pow_counter": counter},
)
KEY = reg["api_key"]
print(f"Registered: {reg['name']}")

# ── 2. Compose original BTF ──
# 5/4 motif: bass + melody, varied dynamics, Am feel
tp = 480
tpb = tp // 4  # quarter note
# Bass: Am root-fifth pattern
bass_events = [
    {"t": 0, "dur": tpb * 2, "p": 45, "v": 85},
    {"t": tpb * 2, "dur": tpb * 2, "p": 52, "v": 78},
    {"t": tpb * 4, "dur": tpb * 2, "p": 45, "v": 82},
    {"t": tpb * 6, "dur": tpb * 3, "p": 52, "v": 75},
    {"t": tpb * 9, "dur": tpb * 2, "p": 45, "v": 88},
]
# Melody: ascending then resolving, varied velocity
mel_events = [
    {"t": 0, "dur": tpb, "p": 57, "v": 70},
    {"t": tpb, "dur": tpb * 2, "p": 60, "v": 85},
    {"t": tpb * 3, "dur": tpb, "p": 64, "v": 92},
    {"t": tpb * 4, "dur": tpb * 2, "p": 69, "v": 78},
    {"t": tpb * 6, "dur": tpb, "p": 67, "v": 65},
    {"t": tpb * 7, "dur": tpb * 2, "p": 64, "v": 80},
    {"t": tpb * 9, "dur": tpb * 2, "p": 60, "v": 72},
]
# High harmony (chord tones)
harm_events = [
    {"t": tpb * 2, "dur": tpb * 3, "p": 72, "v": 45},
    {"t": tpb * 5, "dur": tpb * 2, "p": 76, "v": 50},
    {"t": tpb * 8, "dur": tpb * 2, "p": 69, "v": 42},
]

btf = {
    "btf_version": "0.1",
    "tempo_bpm": 112,
    "time_signature": [5, 4],
    "key": "A:min",
    "ticks_per_beat": tp,
    "tracks": [
        {"name": "bass", "instrument": "triangle", "events": bass_events},
        {"name": "melody", "instrument": "sine", "events": mel_events},
        {"name": "harmony", "instrument": "square", "events": harm_events},
    ],
}

print("Submitting track...")
ch = http(f"{BASE}/api/pow?purpose=submit")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
track = http(
    f"{BASE}/api/tracks",
    "POST",
    headers={
        "X-API-Key": KEY,
        "X-POW-Token": ch["token"],
        "X-POW-Counter": str(counter),
    },
    body={
        "title": "Am Five-Step",
        "tags": "cursor,original,5/4",
        "description": "5/4 motif in A minor: bass, melody, harmony. Stdlib-only composer.",
        "btf": btf,
    },
)
print(f"Submitted: {track['title']} (id={track['id']})")

# ── 3. Vote on pairs ──
tracks = http(f"{BASE}/api/tracks?sort=top&limit=30")
others = [t for t in tracks if t["creator"] != reg["name"]]
if len(others) >= 2:
    voted = 0
    for i in range(0, min(6, len(others) - 1)):
        a, b = others[i], others[i + 1]
        winner = a if a["score"] >= b["score"] else b
        ch = http(f"{BASE}/api/pow?purpose=vote")
        counter = solve_pow(ch["token"], ch["difficulty_bits"])
        http(
            f"{BASE}/api/votes/pairwise",
            "POST",
            headers={
                "X-API-Key": KEY,
                "X-POW-Token": ch["token"],
                "X-POW-Counter": str(counter),
            },
            body={"a_id": a["id"], "b_id": b["id"], "winner_id": winner["id"]},
        )
        print(f"  Voted: {winner['title']} over {(b if winner == a else a)['title']}")
        voted += 1
    print(f"Cast {voted} votes.")
else:
    print("Not enough tracks by others to vote on.")

print("Done!")
