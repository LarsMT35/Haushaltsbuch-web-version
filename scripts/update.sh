#!/usr/bin/env bash
# Update auf den neuesten Stand (Kapitel 5: Upgrade-Weg).
# 1. Sicherungs-Dump VOR der Migration  2. neuen Stand holen  3. neu bauen –
# Alembic-Migrationen laufen beim Containerstart automatisch.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "➤ Sicherungs-Dump vor dem Update …"
./scripts/backup.sh "${BACKUP_DIR:-./backups}"

echo "➤ Hole neuen Stand …"
git pull --ff-only

echo "➤ Baue und starte Stack neu …"
docker compose up -d --build

echo "✔ Update abgeschlossen. Version siehe: curl -s http://localhost:${APP_PORT:-8080}/api/health"
echo "  Bei Problemen: Dump aus ${BACKUP_DIR:-./backups} mit scripts/restore.sh zurückspielen"
echo "  und vorherigen Stand mit 'git checkout <commit>' + 'docker compose up -d --build' starten."
