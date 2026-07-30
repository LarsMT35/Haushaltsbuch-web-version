#!/usr/bin/env bash
# Rücksicherung eines Dumps – mindestens einmal testen: ein Backup, das nie
# zurückgespielt wurde, ist kein Backup (Kapitel 5).
set -euo pipefail

DUMP="${1:?Aufruf: restore.sh <dump.sql.gz>}"

cd "$(dirname "$0")/.."
echo "ACHTUNG: überschreibt die aktuelle Datenbank. Abbruch mit Strg+C, weiter mit Enter."
read -r
gunzip -c "$DUMP" | docker compose exec -T db psql -U haushaltsbuch -d haushaltsbuch
echo "Rücksicherung abgeschlossen."
