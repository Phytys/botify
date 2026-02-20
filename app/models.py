from __future__ import annotations

import datetime as dt
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Bot(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, max_length=64)
    api_key_hash: str = Field(index=True, max_length=64)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc), index=True)


class Track(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str = Field(index=True, max_length=120)
    description: str = Field(default="", max_length=500)
    tags: str = Field(default="", max_length=200)  # comma-separated

    creator_id: UUID = Field(index=True)

    canonical_json: str
    sha256: str = Field(index=True, unique=True, max_length=64)

    score: float = Field(default=1000.0, index=True)
    vote_count: int = Field(default=0, index=True)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc), index=True)


class Vote(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    voter_id: UUID = Field(index=True)
    a_id: UUID = Field(index=True)
    b_id: UUID = Field(index=True)
    winner_id: UUID = Field(index=True)
    pair_key: str = Field(index=True, max_length=64)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc), index=True)


class Listen(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    track_id: UUID = Field(index=True)
    listener_id: Optional[UUID] = Field(default=None, index=True)
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc), index=True)
