#!/usr/bin/env bash
# Botify database backup script.
# Run daily via cron. For PostgreSQL: dumps to backups/pg-YYYYMMDD-HHMMSS.sql
# Place in /opt/botify/scripts/backup-db.sh and chmod +x.

set -e
BACKUP_DIR="${BACKUP_DIR:-/opt/botify/backups}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# Detect: Postgres (pgdata volume / postgres container) vs SQLite
if docker exec botify-postgres pg_isready -U botify -d botify >/dev/null 2>&1; then
  OUT="$BACKUP_DIR/pg-$TIMESTAMP.sql"
  docker exec botify-postgres pg_dump -U botify botify > "$OUT"
  gzip -f "$OUT"
  echo "Backed up Postgres to ${OUT}.gz"
  # Keep last 7 daily
  ls -t "$BACKUP_DIR"/pg-*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm -f
elif [ -f /opt/botify/data/botify.db ]; then
  cp /opt/botify/data/botify.db "$BACKUP_DIR/sqlite-$TIMESTAMP.db"
  echo "Backed up SQLite to $BACKUP_DIR/sqlite-$TIMESTAMP.db"
  ls -t "$BACKUP_DIR"/sqlite-*.db 2>/dev/null | tail -n +8 | xargs -r rm -f
else
  echo "No database found to backup"
  exit 1
fi
