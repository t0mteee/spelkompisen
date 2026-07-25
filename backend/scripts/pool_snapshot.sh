#!/bin/bash
# Kort bakgrundstick: poolspel + live-radar. Pool-CLI:n gör basvarv var
# 30:e minut och varje tick när närmaste spelstopp är inom två timmar.
# Live-radarn samlar alltid pågående matcher men påverkar inga tips.
#
# OBS: `live-tick` FÖRTÄTAR SIG SJÄLV inom jobbet (två varv, 0 s och 120 s,
# budget 180 s), så radarn uppdateras varannan minut utan att launchd-intervallet
# ändras. Den slutar direkt om ingen livematch har chansdata. Poolvarvet och
# Pinnacle förtätas INTE: bulk-endpointen är CDN-cachad 905 s, så tätare anrop
# returnerar exakt samma objekt.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/pool-snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
POOL_OUT="$("$PY" -B cli.py pool-tick 2>&1 | sed 's/^/  /' || echo '  POOL FEL')"
LIVE_OUT="$("$PY" -B cli.py live-tick 2>&1 | sed 's/^/  /' || echo '  LIVE FEL')"
{
  echo "[$TS] pool+live-tick:"
  echo "$POOL_OUT"
  echo "$LIVE_OUT"
} >> "$LOG"
