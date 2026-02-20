from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class BTFEvent(BaseModel):
    t: int = Field(ge=0, description="Start time in ticks")
    dur: int = Field(gt=0, le=100000, description="Duration in ticks")
    p: int = Field(ge=0, le=127, description="MIDI pitch")
    v: int = Field(ge=0, le=127, description="Velocity")


class BTFTrack(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    instrument: str = Field(default="sine", max_length=64)
    events: list[BTFEvent] = Field(default_factory=list, max_length=5000)

    @field_validator("events")
    @classmethod
    def _sorted_events(cls, v: list[BTFEvent]) -> list[BTFEvent]:
        # Ensure stable canonicalization; sort by time then pitch.
        return sorted(v, key=lambda e: (e.t, e.p, e.dur, e.v))


class BTF(BaseModel):
    btf_version: Literal["0.1"]
    seed: Optional[int] = None
    tempo_bpm: int = Field(ge=20, le=300)
    time_signature: tuple[int, int] = Field(default=(4, 4))
    key: str = Field(default="C:maj", max_length=16)
    ticks_per_beat: int = Field(default=480, ge=48, le=1920)
    tracks: list[BTFTrack] = Field(min_length=1, max_length=16)

    @field_validator("time_signature")
    @classmethod
    def _validate_ts(cls, v: tuple[int, int]) -> tuple[int, int]:
        num, den = v
        if num < 1 or num > 32:
            raise ValueError("time_signature numerator out of range")
        if den not in (1, 2, 4, 8, 16, 32):
            raise ValueError("time_signature denominator must be a power-of-two")
        return v


def canonicalize_btf(btf_obj: dict[str, Any]) -> tuple[str, str]:
    """Return (canonical_json, sha256_hex)."""
    # Validate and normalize via Pydantic model.
    btf = BTF.model_validate(btf_obj)

    # Re-dump with sorted keys and compact separators.
    canonical_json = json.dumps(
        btf.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    sha = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    return canonical_json, sha
