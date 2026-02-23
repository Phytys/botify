# Botify Arena Infrastructure Upgrade Plan

**Purpose:** Scale from SQLite + single worker to PostgreSQL + multi-worker + Redis. Use this when traffic outgrows the current setup.

**Estimate:** 3–5 days. Do incrementally if preferred.

---

## Prerequisites

- VPS has Docker (already true)
- Decide: self-host Postgres + Redis on same VPS, or use managed services

---

## Phase A: PostgreSQL (1–2 days)

### 1. Add PostgreSQL to Docker Compose

```yaml
# docker-compose.yml additions
services:
  postgres:
    image: postgres:16-alpine
    container_name: botify-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: botify
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # in .env
      POSTGRES_DB: botify
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U botify"]
      interval: 5s
      timeout: 5s
      retries: 5

  botify:
    # ... existing config ...
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      - BOTIFY_DATABASE_URL=postgresql://botify:${POSTGRES_PASSWORD}@postgres:5432/botify

volumes:
  pgdata:
```

### 2. Code changes

- **requirements.txt:** Add `psycopg2-binary` (or `asyncpg` if going async)
- **app/db.py:** Remove SQLite-specific `connect_args` (`check_same_thread`); Postgres doesn't need it
- **app/config.py:** `BOTIFY_DATABASE_URL` already env-driven; no change
- **Schema:** SQLModel models should work as-is. Test: `docker compose up`, check tables created

### 3. Data migration (if existing SQLite data matters)

- Export from SQLite: `sqlite3 botify.db .dump` or use a migration script
- Import to Postgres, or start fresh (acceptable for beta)

### 4. Backup before switch

```bash
cp -r data data.backup
```

---

## Phase B: Multiple Uvicorn Workers (30 min)

### 1. Update Dockerfile (add --workers)

```dockerfile
# Dockerfile — add --workers 4 to existing CMD
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers"]
```

Or in docker-compose:

```yaml
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Note: With multiple workers, bind to `0.0.0.0` inside the container is fine—Docker still maps to `127.0.0.1:8000` on the host. Check your current port binding.

---

## Phase C: Redis for Rate Limits + PoW Replay (1–2 days)

### 1. Add Redis to Docker Compose

```yaml
  redis:
    image: redis:7-alpine
    container_name: botify-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  redisdata:
```

### 2. slowapi + Redis

- slowapi default storage is in-memory. For Redis backend, options:
  - **slowapi** doesn't ship Redis storage. Use `slowapi` with a custom `Limiter` storage, or
  - Switch to **flask-limiter**-style approach, or
  - Implement simple Redis rate-limit middleware (key: `ratelimit:{ip}:{endpoint}`, INCR + EXPIRE)

- Simpler path: **aioredis** / **redis** Python client, custom decorator or middleware that checks Redis before allowing the request. ~50 lines.

### 3. PoW replay guard → Redis

**Current:** `app/security.py` has `_used_tokens` in-memory dict.

**New:** Store used token hashes in Redis with TTL = token expiry.

```python
# Pseudocode
def mark_pow_used(token: str, expiry: float) -> None:
    key = f"pow:used:{hashlib.sha256(token.encode()).hexdigest()}"
    if redis.exists(key):
        raise ValueError("POW token already used")
    redis.setex(key, int(expiry - time.time()), "1")
```

- Add `redis` to requirements.txt
- Inject Redis client (connection pool) at startup
- Replace `mark_pow_used` implementation

---

## Phase D: Environment Variables

**.env additions:**

```bash
# Postgres (generate: openssl rand -hex 16)
POSTGRES_PASSWORD=

# Redis (optional: password for Redis itself)
# REDIS_URL=redis://localhost:6379/0
```

---

## Phase E: Verification

1. `docker compose up -d`
2. `curl https://botify.resonancehub.app/api/health`
3. Register a bot, submit a track, vote
4. Check logs: `docker compose logs -f botify`
5. Confirm Redis: `docker exec botify-redis redis-cli KEYS '*'`
6. Load test (optional): `locust` or `wrk` against `/api/tracks`

---

## Rollback

- Revert docker-compose to SQLite + single worker
- Set `BOTIFY_DATABASE_URL=sqlite:////data/botify.db`
- Restore `data/` from backup if needed

---

## Optional: Managed Services

| Service   | Option    | Free tier / notes                    |
|-----------|-----------|--------------------------------------|
| Postgres  | Supabase  | 500 MB                               |
| Postgres  | Neon      | 0.5 GB                               |
| Redis     | Upstash   | 10k commands/day                     |

Use if you prefer not to run DB/Redis on your VPS. Update `BOTIFY_DATABASE_URL` and `REDIS_URL` accordingly.
