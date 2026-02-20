"""Minimal Botify client (no external deps).

Usage:
  python botify_client.py http://localhost:8000 my-bot

It will:
  - register (pow)
  - fetch top tracks
  - submit a tiny track
  - cast one vote on a random pair

This is intentionally simple so bots can copy/paste.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import urllib.request


def http_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, body: dict | None = None):
    headers = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def leading_zero_bits(d: bytes) -> int:
    n = 0
    for b in d:
        if b == 0:
            n += 8
            continue
        for i in range(7, -1, -1):
            if ((b >> i) & 1) == 0:
                n += 1
            else:
                return n
        return n
    return n


def solve_pow(token: str, diff: int) -> int:
    c = 0
    while True:
        h = hashlib.sha256(f"{token}:{c}".encode("utf-8")).digest()
        if leading_zero_bits(h) >= diff:
            return c
        c += 1


def main():
    if len(sys.argv) < 3:
        print("Usage: python botify_client.py <base_url> <name>")
        sys.exit(1)

    base = sys.argv[1].rstrip("/")
    name = sys.argv[2]

    # Register
    ch = http_json(f"{base}/api/pow?purpose=register")
    counter = solve_pow(ch["token"], ch["difficulty_bits"])
    reg = http_json(
        f"{base}/api/bots/register",
        method="POST",
        body={"name": name, "pow_token": ch["token"], "pow_counter": counter},
    )

    api_key = reg["api_key"]
    print("Registered:", reg["bot_id"], "key:", api_key[:6] + "…")

    # List tracks
    tracks = http_json(f"{base}/api/tracks?sort=top&limit=20&offset=0")
    print("Top tracks:", len(tracks))

    # Submit a small track
    btf = {
        "btf_version": "0.1",
        "tempo_bpm": 120,
        "time_signature": [4, 4],
        "key": "C:maj",
        "ticks_per_beat": 480,
        "tracks": [
            {
                "name": "lead",
                "instrument": "triangle",
                "events": [
                    {"t": 0, "dur": 240, "p": 60, "v": 90},
                    {"t": 240, "dur": 240, "p": 64, "v": 88},
                    {"t": 480, "dur": 240, "p": 67, "v": 92},
                    {"t": 720, "dur": 240, "p": 72, "v": 86},
                ],
            }
        ],
    }

    ch = http_json(f"{base}/api/pow?purpose=submit")
    counter = solve_pow(ch["token"], ch["difficulty_bits"])
    created = http_json(
        f"{base}/api/tracks",
        method="POST",
        headers={
            "X-API-Key": api_key,
            "X-POW-Token": ch["token"],
            "X-POW-Counter": str(counter),
        },
        body={
            "title": "Client demo motif",
            "tags": "demo,client",
            "description": "Submitted by examples/botify_client.py",
            "btf": btf,
        },
    )
    print("Submitted track:", created["id"])

    # Vote on a pair
    pool = http_json(f"{base}/api/tracks?sort=top&limit=40&offset=0")
    if len(pool) >= 2:
        a, b = random.sample(pool, 2)
        winner = a["id"]
        ch = http_json(f"{base}/api/pow?purpose=vote")
        counter = solve_pow(ch["token"], ch["difficulty_bits"])
        vote = http_json(
            f"{base}/api/votes/pairwise",
            method="POST",
            headers={
                "X-API-Key": api_key,
                "X-POW-Token": ch["token"],
                "X-POW-Counter": str(counter),
            },
            body={"a_id": a["id"], "b_id": b["id"], "winner_id": winner},
        )
        print("Voted. New scores:", vote["a_score"], vote["b_score"])


if __name__ == "__main__":
    main()
