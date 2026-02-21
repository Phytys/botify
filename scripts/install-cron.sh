#!/usr/bin/env bash
# Install daily backup cron job.
# Run once on the VPS: sudo ./scripts/install-cron.sh

CRON_LINE="0 2 * * * root BACKUP_DIR=/opt/botify/backups /opt/botify/scripts/backup-db.sh >> /var/log/botify-backup.log 2>&1"
CRON_FILE="/etc/cron.d/botify-backup"

mkdir -p /opt/botify/backups
chmod +x /opt/botify/scripts/backup-db.sh

echo "$CRON_LINE" | tee "$CRON_FILE"
chmod 644 "$CRON_FILE"
echo "Installed: daily backup at 02:00 to /opt/botify/backups"
