#!/bin/bash
# Wrapper som launchd startar på :00/:30. `cli.py smart` äger Oddset:
# fullt varv och därefter lätta 4-minutersvarv nära avspark, max ~25 min.
# Poolspelen har ett separat, kort 5-minutersjobb (`pool_snapshot.sh`) så att
# tung Oddset-insamling aldrig skapar luckor runt T−20m.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY="$BACKEND_DIR/.venv/bin/python"
LOG="$BACKEND_DIR/data/snapshot.log"
mkdir -p "$BACKEND_DIR/data"

cd "$BACKEND_DIR"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
OUT="$("$PY" cli.py smart 2>&1 | sed 's/^/  /' || echo '  FEL')"
{ echo "[$TS] oddset-smart:"; echo "$OUT"; } >> "$LOG"
