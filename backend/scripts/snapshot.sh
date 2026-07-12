#!/bin/bash
# Wrapper som launchd kör: Oddset-odds först (snabbt, ~30 s), sedan poolspels-
# snapshot för alla produkter. "snapshot-smart" förtätar själv till var 5:e minut
# när någon omgång stänger inom 2 h (kör max ~25 min, sedan tar nästa körning vid).
# Loggar till backend/data/snapshot.log. Felfri exit även om inget sparas.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
ODDSET_OUT="$("$PY" cli.py oddset 2>&1 | sed 's/^/  /' || echo '  FEL')"
OUT="$("$PY" cli.py snapshot-smart 2>&1 | sed 's/^/  /' || echo '  FEL')"
{ echo "[$TS] oddset:"; echo "$ODDSET_OUT";
  echo "[$TS] snapshot-smart:"; echo "$OUT"; } >> "$LOG"
