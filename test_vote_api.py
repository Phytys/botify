#!/usr/bin/env python3
"""Test GET /api/votes/pair and GET /api/bots/me/votes against live API."""
import hashlib
import json
import random
import urllib.request

BASE = "https://botify.resonancehub.app"
BOT_NAME = f"test-vote-api-{random.randint(10000,99999)}"

def http(url, method="GET", headers=None, body=None):
    h = dict(headers or {})
    if body:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def solve_pow(token, bits):
    c = 0
    while True:
        h = hashlib.sha256(f"{token}:{c}".encode()).digest()
        n = sum(8 - (b.bit_length() if b else 0) for b in h) if True else 0
        n = 0
        for b in h:
            if b == 0:
                n += 8
                continue
            for i in range(7, -1, -1):
                if (b >> i) & 1:
                    break
                n += 1
            break
        if n >= bits:
            return c
        c += 1

print("1. Register...")
ch = http(f"{BASE}/api/pow?purpose=register")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
reg = http(f"{BASE}/api/bots/register", "POST",
    body={"name": BOT_NAME, "pow_token": ch["token"], "pow_counter": counter})
KEY = reg["api_key"]
print(f"   Bot: {reg['name']}")

print("2. GET /api/votes/pair...")
pair = http(f"{BASE}/api/votes/pair", headers={"X-API-Key": KEY})
assert "a_id" in pair and "b_id" in pair and "a" in pair and "b" in pair
print(f"   Pair: {pair['a']['title']} vs {pair['b']['title']}")

print("3. POST /api/votes/pairwise...")
ch = http(f"{BASE}/api/pow?purpose=vote")
counter = solve_pow(ch["token"], ch["difficulty_bits"])
result = http(f"{BASE}/api/votes/pairwise", "POST",
    headers={"X-API-Key": KEY, "X-POW-Token": ch["token"], "X-POW-Counter": str(counter)},
    body={"a_id": pair["a_id"], "b_id": pair["b_id"], "winner_id": pair["a_id"]})
print(f"   Voted: {result['winner_id']}")

print("4. GET /api/bots/me/votes...")
votes = http(f"{BASE}/api/bots/me/votes", headers={"X-API-Key": KEY})
assert isinstance(votes, list)
assert len(votes) >= 1
v = votes[0]
assert "a_id" in v and "b_id" in v and "winner_id" in v and "a_title" in v and "b_title" in v
print(f"   Votes: {len(votes)} (latest: {v['a_title']} vs {v['b_title']} -> winner {v['winner_id']})")

print("\nAll tests passed!")
