#!/usr/bin/env bash
# Täglicher DB-Dump (Kapitel 5) – per Cron aufrufen, Ziel z.B. NAS-Mount.
# Beispiel-Cron:  15 2 * * *  /pfad/zum/repo/scripts/backup.sh /mnt/nas/haushaltsbuch
set -euo pipefail

TARGET_DIR="${1:-./backups}"
KEEP=14  # Aufbewahrung mehrerer Generationen

mkdir -p "$TARGET_DIR"
STAMP=$(date +%Y-%m-%d_%H%M)
FILE="$TARGET_DIR/haushaltsbuch_$STAMP.sql.gz"

cd "$(dirname "$0")/.."
docker compose exec -T db pg_dump -U haushaltsbuch haushaltsbuch | gzip > "$FILE"
echo "Dump geschrieben: $FILE ($(du -h "$FILE" | cut -f1))"

# Alte Generationen aufräumen
ls -1t "$TARGET_DIR"/haushaltsbuch_*.sql.gz | tail -n +$((KEEP + 1)) | xargs -r rm --
