#!/bin/bash
# Wrapper som launchd kör: ta ett snapshot av aktuell omgång och logga.
# Loggar till backend/data/snapshot.log. Felfri exit även om inget sparas.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$("$PY" cli.py snapshot stryktipset 2>&1 | tail -2 | tr '\n' ' ' || echo 'FEL')"
echo "[$TS] $OUT" >> "$LOG"
