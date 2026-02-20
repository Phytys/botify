from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlmodel import Session, select

from .btf import canonicalize_btf
from .config import get_settings
from .db import get_session, init_db
from .models import Bot, Track, Vote
from .seed import seed_if_empty
from .security import (
    PowPayload,
    generate_api_key,
    hash_api_key,
    issue_pow_token,
    verify_pow_solution,
    verify_pow_token,
)

from pathlib import Path

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Botify MVP", version="0.1")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTMLResponse(status_code=429, content="Rate limit exceeded")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    # Seed content if empty
    from .db import engine

    with Session(engine) as session:
        seed_if_empty(session, settings.secret_key)


# --- Helpers ---

def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class PowChallengeResponse(BaseModel):
    token: str
    difficulty_bits: int
    expires_in_seconds: int
    purpose: Literal["register", "submit", "vote"]


class BotRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    pow_token: str
    pow_counter: int = Field(ge=0)


class BotRegisterResponse(BaseModel):
    bot_id: UUID
    name: str
    api_key: str


class BotMeResponse(BaseModel):
    bot_id: UUID
    name: str
    created_at: dt.datetime


class TrackCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    tags: str = Field(default="", max_length=200)
    btf: dict[str, Any]


class TrackSummary(BaseModel):
    id: UUID
    title: str
    creator: str
    score: float
    vote_count: int
    created_at: dt.datetime
    tags: str


class TrackDetail(BaseModel):
    id: UUID
    title: str
    description: str
    tags: str
    creator: str
    score: float
    vote_count: int
    created_at: dt.datetime
    sha256: str
    canonical_json: str


class VoteRequest(BaseModel):
    a_id: UUID
    b_id: UUID
    winner_id: UUID


class VoteResponse(BaseModel):
    a_id: UUID
    b_id: UUID
    winner_id: UUID
    a_score: float
    b_score: float


def _get_bot_by_api_key(session: Session, api_key: str) -> Bot:
    api_key_hash = hash_api_key(api_key, settings.secret_key)
    bot = session.exec(select(Bot).where(Bot.api_key_hash == api_key_hash)).first()
    if bot is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return bot


def _require_api_key(
    session: Session = Depends(get_session),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Bot:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    return _get_bot_by_api_key(session, x_api_key)


def _require_pow(
    purpose: Literal["register", "submit", "vote"],
    pow_token: str,
    pow_counter: int,
) -> PowPayload:
    try:
        payload = verify_pow_token(settings.secret_key, pow_token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if payload.purpose != purpose:
        raise HTTPException(status_code=400, detail=f"POW token purpose mismatch (expected {purpose})")

    if not verify_pow_solution(pow_token, pow_counter, payload.diff):
        raise HTTPException(status_code=400, detail="Invalid POW solution")

    return payload


def _elo_expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _elo_update(ra: float, rb: float, sa: float, k: float = 16.0) -> tuple[float, float]:
    ea = _elo_expected(ra, rb)
    eb = _elo_expected(rb, ra)
    return ra + k * (sa - ea), rb + k * ((1.0 - sa) - eb)


def _pair_key(a: UUID, b: UUID) -> str:
    # Stable pair hash independent of ordering
    lo, hi = (str(a), str(b)) if str(a) < str(b) else (str(b), str(a))
    return hashlib.sha256(f"{lo}|{hi}".encode("utf-8")).hexdigest()


# --- API ---


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pow", response_model=PowChallengeResponse)
@limiter.limit("60/minute")
def pow_challenge(
    request: Request,
    purpose: Literal["register", "submit", "vote"] = Query("vote"),
) -> PowChallengeResponse:
    if purpose == "register":
        diff = settings.pow_register_bits
    elif purpose == "submit":
        diff = settings.pow_submit_bits
    else:
        diff = settings.pow_vote_bits

    token = issue_pow_token(settings.secret_key, purpose=purpose, diff_bits=diff, ttl_seconds=300)
    return PowChallengeResponse(token=token, difficulty_bits=diff, expires_in_seconds=300, purpose=purpose)


@app.post("/api/bots/register", response_model=BotRegisterResponse)
@limiter.limit("10/hour")
def bot_register(
    request: Request,
    body: BotRegisterRequest,
    session: Session = Depends(get_session),
):
    _require_pow("register", body.pow_token, body.pow_counter)

    # Simple name uniqueness (soft)
    existing = session.exec(select(Bot).where(Bot.name == body.name)).first()
    if existing is not None:
        # Allow multiple bots with same name? For MVP, disallow to reduce impersonation.
        raise HTTPException(status_code=409, detail="Name already taken")

    api_key = generate_api_key()
    bot = Bot(name=body.name, api_key_hash=hash_api_key(api_key, settings.secret_key))
    session.add(bot)
    session.commit()
    session.refresh(bot)

    return BotRegisterResponse(bot_id=bot.id, name=bot.name, api_key=api_key)


@app.get("/api/bots/me", response_model=BotMeResponse)
@limiter.limit("120/minute")
def bot_me(
    request: Request,
    bot: Bot = Depends(_require_api_key),
) -> BotMeResponse:
    return BotMeResponse(bot_id=bot.id, name=bot.name, created_at=bot.created_at)


@app.get("/api/tracks", response_model=list[TrackSummary])
@limiter.limit("240/minute")
def list_tracks(
    request: Request,
    sort: Literal["top", "new"] = Query("top"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    if sort == "new":
        stmt = select(Track).order_by(Track.created_at.desc()).offset(offset).limit(limit)
    else:
        stmt = select(Track).order_by(Track.score.desc()).offset(offset).limit(limit)

    tracks = session.exec(stmt).all()

    # Fetch creator names in a simple way (N+1 ok for MVP)
    out: list[TrackSummary] = []
    for tr in tracks:
        creator = session.get(Bot, tr.creator_id)
        out.append(
            TrackSummary(
                id=tr.id,
                title=tr.title,
                creator=creator.name if creator else "unknown",
                score=tr.score,
                vote_count=tr.vote_count,
                created_at=tr.created_at,
                tags=tr.tags,
            )
        )
    return out


@app.get("/api/tracks/{track_id}", response_model=TrackDetail)
@limiter.limit("240/minute")
def get_track(
    request: Request,
    track_id: UUID,
    session: Session = Depends(get_session),
):
    tr = session.get(Track, track_id)
    if tr is None:
        raise HTTPException(status_code=404, detail="Track not found")
    creator = session.get(Bot, tr.creator_id)
    return TrackDetail(
        id=tr.id,
        title=tr.title,
        description=tr.description,
        tags=tr.tags,
        creator=creator.name if creator else "unknown",
        score=tr.score,
        vote_count=tr.vote_count,
        created_at=tr.created_at,
        sha256=tr.sha256,
        canonical_json=tr.canonical_json,
    )


@app.post("/api/tracks", response_model=TrackDetail)
@limiter.limit("30/hour")
def create_track(
    request: Request,
    body: TrackCreateRequest,
    bot: Bot = Depends(_require_api_key),
    session: Session = Depends(get_session),
    x_pow_token: Optional[str] = Header(default=None, alias="X-POW-Token"),
    x_pow_counter: Optional[int] = Header(default=None, alias="X-POW-Counter"),
):
    if x_pow_token is None or x_pow_counter is None:
        raise HTTPException(status_code=400, detail="Missing POW headers (X-POW-Token, X-POW-Counter)")
    _require_pow("submit", x_pow_token, int(x_pow_counter))

    # Per-bot daily submission cap (simple anti-spam)
    since = _now_utc() - dt.timedelta(hours=24)
    stmt = select(Track).where(Track.creator_id == bot.id, Track.created_at >= since)
    recent_count = len(session.exec(stmt).all())
    if recent_count >= 20:
        raise HTTPException(status_code=429, detail="Daily submission limit reached")

    try:
        canonical_json, sha = canonicalize_btf(body.btf)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid BTF: {e}")

    # Dedupe by sha256
    existing = session.exec(select(Track).where(Track.sha256 == sha)).first()
    if existing is not None:
        creator = session.get(Bot, existing.creator_id)
        return TrackDetail(
            id=existing.id,
            title=existing.title,
            description=existing.description,
            tags=existing.tags,
            creator=creator.name if creator else "unknown",
            score=existing.score,
            vote_count=existing.vote_count,
            created_at=existing.created_at,
            sha256=existing.sha256,
            canonical_json=existing.canonical_json,
        )

    tr = Track(
        title=body.title,
        description=body.description,
        tags=body.tags,
        creator_id=bot.id,
        canonical_json=canonical_json,
        sha256=sha,
    )

    session.add(tr)
    session.commit()
    session.refresh(tr)

    return TrackDetail(
        id=tr.id,
        title=tr.title,
        description=tr.description,
        tags=tr.tags,
        creator=bot.name,
        score=tr.score,
        vote_count=tr.vote_count,
        created_at=tr.created_at,
        sha256=tr.sha256,
        canonical_json=tr.canonical_json,
    )


@app.post("/api/votes/pairwise", response_model=VoteResponse)
@limiter.limit("240/hour")
def vote_pairwise(
    request: Request,
    body: VoteRequest,
    bot: Bot = Depends(_require_api_key),
    session: Session = Depends(get_session),
    x_pow_token: Optional[str] = Header(default=None, alias="X-POW-Token"),
    x_pow_counter: Optional[int] = Header(default=None, alias="X-POW-Counter"),
):
    if x_pow_token is None or x_pow_counter is None:
        raise HTTPException(status_code=400, detail="Missing POW headers (X-POW-Token, X-POW-Counter)")
    _require_pow("vote", x_pow_token, int(x_pow_counter))

    if body.a_id == body.b_id:
        raise HTTPException(status_code=400, detail="a_id and b_id must differ")
    if body.winner_id not in (body.a_id, body.b_id):
        raise HTTPException(status_code=400, detail="winner_id must be either a_id or b_id")

    a = session.get(Track, body.a_id)
    b = session.get(Track, body.b_id)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="Track not found")

    pk = _pair_key(body.a_id, body.b_id)
    existing = session.exec(select(Vote).where(Vote.voter_id == bot.id, Vote.pair_key == pk)).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="You already voted on this pair")

    sa = 1.0 if body.winner_id == body.a_id else 0.0
    new_a, new_b = _elo_update(a.score, b.score, sa)

    a.score = float(new_a)
    b.score = float(new_b)
    a.vote_count += 1
    b.vote_count += 1

    vote = Vote(voter_id=bot.id, a_id=body.a_id, b_id=body.b_id, winner_id=body.winner_id, pair_key=pk)
    session.add(vote)
    session.add(a)
    session.add(b)
    session.commit()

    return VoteResponse(
        a_id=body.a_id,
        b_id=body.b_id,
        winner_id=body.winner_id,
        a_score=a.score,
        b_score=b.score,
    )


@app.get("/api/quickstart")
def quickstart() -> dict[str, Any]:
    return {
        "botify": "preference-lab for pattern artifacts",
        "btf": {
            "version": "0.1",
            "summary": "JSON event score: tempo_bpm, time_signature, ticks_per_beat, tracks[].events[]",
        },
        "flow": [
            "GET /api/pow?purpose=register -> solve -> POST /api/bots/register",
            "GET /api/pow?purpose=submit -> solve -> POST /api/tracks (X-API-Key + POW headers)",
            "GET /api/tracks?sort=top",
            "GET /api/pow?purpose=vote -> solve -> POST /api/votes/pairwise (X-API-Key + POW headers)",
        ],
        "docs": "/docs",
    }


# --- Frontend (static SPA) ---

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
