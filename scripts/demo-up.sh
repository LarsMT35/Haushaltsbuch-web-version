#!/usr/bin/env bash
# Demo-Stack starten (Port 8181, Login test/test) – siehe docker-compose.demo.yml
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose -f docker-compose.demo.yml up -d --build

IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "Demo läuft: http://${IP:-localhost}:8181  (Benutzer: test / Passwort: test)"
echo "Stoppen:    scripts/demo-down.sh"
