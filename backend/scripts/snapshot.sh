#!/bin/bash
# Wrapper som launchd kör var 30:e min: "cli.py smart" gör ett fullt varv
# (Oddset-odds + poolspels-snapshots) och fortsätter sedan själv med snabbvarv
# var 4:e min när någon oddset-match startar inom 3 h (endast Pinnacle +
# böckernas 1X2, notiser i samma varv — backlog A1) och/eller tätvarv var 5:e
# min när ett poolspel stänger inom 2 h. Kör max ~25 min, sedan tar nästa
# launchd-körning vid. Loggar till backend/data/snapshot.log.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$("$PY" cli.py smart 2>&1 | sed 's/^/  /' || echo '  FEL')"
{ echo "[$TS] smart:"; echo "$OUT"; } >> "$LOG"
