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


_DEV_SECRET = "dev-secret-change-me"


def get_settings() -> Settings:
    secret_key = os.getenv("BOTIFY_SECRET", "")
    dev_mode = os.getenv("BOTIFY_DEV", "").lower() in ("1", "true", "yes")

    if not secret_key:
        if dev_mode:
            secret_key = _DEV_SECRET
        else:
            raise RuntimeError(
                "BOTIFY_SECRET is not set. "
                "Generate one with:  openssl rand -hex 32\n"
                "Set BOTIFY_DEV=1 to use an insecure default for local development."
            )

    if secret_key == _DEV_SECRET and not dev_mode:
        raise RuntimeError(
            "BOTIFY_SECRET is set to the dev default. "
            "Generate a real secret with:  openssl rand -hex 32"
        )

    database_url = os.getenv("BOTIFY_DATABASE_URL", "sqlite:///./botify.db")

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
