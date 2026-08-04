#!/usr/bin/env bash
# Demo-Stack stoppen. Standardmäßig bleiben die Demodaten erhalten (Volume);
# mit --reset werden sie beim nächsten Start komplett neu (leer) angelegt.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--reset" ]; then
  docker compose -f docker-compose.demo.yml down -v
  echo "Demo-Stack gestoppt, Demodaten gelöscht."
else
  docker compose -f docker-compose.demo.yml down
  echo "Demo-Stack gestoppt, Demodaten bleiben erhalten. Zum Zurücksetzen: scripts/demo-down.sh --reset"
fi
