from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * ((4 - (len(s) % 4)) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def hash_api_key(api_key: str, secret: str) -> str:
    # HMAC the key with server secret so DB leak doesn't give raw keys.
    digest = hmac.new(secret.encode("utf-8"), api_key.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class PowPayload:
    purpose: Literal["register", "submit", "vote"]
    exp: int
    diff: int
    salt: str


def issue_pow_token(secret: str, purpose: str, diff_bits: int, ttl_seconds: int = 300) -> str:
    payload = {
        "purpose": purpose,
        "exp": int(time.time()) + ttl_seconds,
        "diff": int(diff_bits),
        "salt": secrets.token_hex(8),
    }
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64url_encode(payload_b)
    sig = hmac.new(secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256).digest()
    sig_part = _b64url_encode(sig)
    return f"{payload_part}.{sig_part}"


def verify_pow_token(secret: str, token: str) -> PowPayload:
    try:
        payload_part, sig_part = token.split(".", 1)
    except ValueError:
        raise ValueError("Invalid POW token format")

    expected_sig = hmac.new(secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_encode(expected_sig), sig_part):
        raise ValueError("Invalid POW token signature")

    payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))

    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("POW token expired")

    purpose = payload.get("purpose")
    if purpose not in ("register", "submit", "vote"):
        raise ValueError("Invalid POW token purpose")

    diff = int(payload.get("diff", 0))
    if diff <= 0 or diff > 32:
        raise ValueError("Invalid POW token difficulty")

    salt = str(payload.get("salt", ""))

    return PowPayload(purpose=purpose, exp=int(payload["exp"]), diff=diff, salt=salt)


def leading_zero_bits(digest: bytes) -> int:
    # Count leading 0 bits in a bytestring.
    n = 0
    for byte in digest:
        if byte == 0:
            n += 8
            continue
        # Count leading zeros in this byte.
        for i in range(7, -1, -1):
            if (byte >> i) & 1 == 0:
                n += 1
            else:
                return n
        return n
    return n


def verify_pow_solution(token: str, counter: int, diff_bits: int) -> bool:
    msg = f"{token}:{counter}".encode("utf-8")
    digest = hashlib.sha256(msg).digest()
    return leading_zero_bits(digest) >= diff_bits


# --- Single-use PoW replay guard (Redis if configured, else in-memory) ---

_used_lock = threading.Lock()
_used_tokens: dict[str, float] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = __import__("os").environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return None
    try:
        import redis as redis_lib
        _redis_client = redis_lib.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


def mark_pow_used(token: str, expiry: float) -> None:
    """Mark a solved PoW token as consumed. Raises ValueError if replayed."""
    key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    redis_key = f"botify:pow:used:{key_hash}"
    ttl_seconds = max(60, int(expiry - time.time()))

    r = _get_redis()
    if r is not None:
        if r.set(redis_key, "1", nx=True, ex=ttl_seconds):
            return
        raise ValueError("POW token already used")

    # Fallback: in-memory (single-instance only)
    with _used_lock:
        now = time.time()
        expired = [k for k, exp in _used_tokens.items() if exp < now]
        for k in expired:
            del _used_tokens[k]
        if key_hash in _used_tokens:
            raise ValueError("POW token already used")
        _used_tokens[key_hash] = expiry
