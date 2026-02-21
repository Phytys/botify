#!/usr/bin/env python3
"""Migrate data from SQLite backup to PostgreSQL.
Run from botify container with backups mounted:
  docker compose run --rm -v $(pwd)/backups:/backups botify python scripts/migrate_sqlite_to_pg.py [path-to-backup.db]
"""
import os
import sys
import sqlite3
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    backup_dir = Path("/backups")
    if len(sys.argv) > 1:
        sqlite_path = Path(sys.argv[1])
    else:
        # Find latest sqlite pre-postgres backup
        candidates = list(backup_dir.glob("botify-sqlite-pre-postgres-*.db")) + \
                     list(backup_dir.glob("botify.db.pre-upgrade-*"))
        if not candidates:
            print("No SQLite backup found in /backups. Expected botify-sqlite-pre-postgres-*.db")
            sys.exit(1)
        sqlite_path = max(candidates, key=lambda p: p.stat().st_mtime)

    db_url = os.environ.get("BOTIFY_DATABASE_URL", "")
    if not db_url or "postgresql" not in db_url:
        print("BOTIFY_DATABASE_URL not set or not PostgreSQL")
        sys.exit(1)

    print(f"Migrating from {sqlite_path} to PostgreSQL...")

    import psycopg2
    from urllib.parse import urlparse

    parsed = urlparse(db_url)
    pg_conn = psycopg2.connect(
        host=parsed.hostname or "postgres",
        port=parsed.port or 5432,
        dbname=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    pg_conn.autocommit = False

    sqlite_conn = sqlite3.connect(str(sqlite_path))

    # Read from SQLite
    sqlite_conn.row_factory = sqlite3.Row
    bots = [dict(r) for r in sqlite_conn.execute("SELECT id, name, api_key_hash, created_at FROM bot").fetchall()]
    tracks = [dict(r) for r in sqlite_conn.execute(
        "SELECT id, title, description, tags, creator_id, canonical_json, sha256, score, vote_count, created_at FROM track"
    ).fetchall()]
    votes = [dict(r) for r in sqlite_conn.execute(
        "SELECT id, voter_id, a_id, b_id, winner_id, pair_key, created_at FROM vote"
    ).fetchall()]

    print(f"  Bots: {len(bots)}, Tracks: {len(tracks)}, Votes: {len(votes)}")

    with pg_conn.cursor() as cur:
        # Truncate (preserve schema, remove seed data)
        cur.execute("TRUNCATE vote, track, bot RESTART IDENTITY CASCADE")

        for b in bots:
            cur.execute(
                "INSERT INTO bot (id, name, api_key_hash, created_at) VALUES (%s::uuid, %s, %s, %s)",
                (str(b["id"]), b["name"], b["api_key_hash"], b["created_at"]),
            )

        for t in tracks:
            cur.execute(
                """INSERT INTO track (id, title, description, tags, creator_id, canonical_json, sha256, score, vote_count, created_at)
                   VALUES (%s::uuid, %s, %s, %s, %s::uuid, %s, %s, %s, %s, %s)""",
                (
                    str(t["id"]), t["title"], t["description"], t["tags"] or "",
                    str(t["creator_id"]), t["canonical_json"], t["sha256"],
                    float(t["score"]), int(t["vote_count"]), t["created_at"],
                ),
            )

        for v in votes:
            cur.execute(
                """INSERT INTO vote (id, voter_id, a_id, b_id, winner_id, pair_key, created_at)
                   VALUES (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s)""",
                (str(v["id"]), str(v["voter_id"]), str(v["a_id"]), str(v["b_id"]),
                 str(v["winner_id"]), v["pair_key"], v["created_at"]),
            )

    pg_conn.commit()
    pg_conn.close()
    sqlite_conn.close()

    print("Migration complete.")

if __name__ == "__main__":
    main()
