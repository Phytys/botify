#!/usr/bin/env bash
# Restore a PostgreSQL backup.
# Usage: ./restore-pg.sh backups/pg-20260221-120000.sql.gz
# Requires: botify-postgres container running, gunzip the file if .gz

set -e
FILE="${1:?Usage: $0 backups/pg-YYYYMMDD-HHMMSS.sql.gz}"

if [[ "$FILE" == *.gz ]]; then
  zcat "$FILE" | docker exec -i botify-postgres psql -U botify -d botify
else
  cat "$FILE" | docker exec -i botify-postgres psql -U botify -d botify
fi
echo "Restored from $FILE"
