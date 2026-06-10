#!/bin/bash
# Wrapper som launchd kör: snapshotta alla produkter och logga.
# "snapshot-smart" förtätar själv till var 5:e minut när någon omgång
# stänger inom 2 h (kör max ~25 min, sedan tar nästa launchd-körning vid).
# Loggar till backend/data/snapshot.log. Felfri exit även om inget sparas.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$("$PY" cli.py snapshot-smart 2>&1 | sed 's/^/  /' || echo '  FEL')"
{ echo "[$TS] snapshot-smart:"; echo "$OUT"; } >> "$LOG"
