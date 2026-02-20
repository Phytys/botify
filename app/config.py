from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    secret_key: str
    database_url: str
    pow_register_bits: int
    pow_submit_bits: int
    pow_vote_bits: int
    public_base_url: str


def get_settings() -> Settings:
    secret_key = os.getenv("BOTIFY_SECRET", "")
    if not secret_key:
        # Dev default; for production set BOTIFY_SECRET.
        secret_key = "dev-secret-change-me"

    database_url = os.getenv("BOTIFY_DATABASE_URL", "sqlite:///./botify.db")

    # Default difficulties are intentionally small so browsers can solve them quickly.
    # You can raise these on a VPS if you see spam.
    pow_register_bits = int(os.getenv("BOTIFY_POW_REGISTER_BITS", "16"))
    pow_submit_bits = int(os.getenv("BOTIFY_POW_SUBMIT_BITS", "15"))
    pow_vote_bits = int(os.getenv("BOTIFY_POW_VOTE_BITS", "13"))

    public_base_url = os.getenv("BOTIFY_PUBLIC_BASE_URL", "")

    return Settings(
        secret_key=secret_key,
        database_url=database_url,
        pow_register_bits=pow_register_bits,
        pow_submit_bits=pow_submit_bits,
        pow_vote_bits=pow_vote_bits,
        public_base_url=public_base_url,
    )
