#!/bin/bash
# Bygger uppladdningspaketet för ChatGPT-granskning (se docs/chatgpt.md):
# tre .txt-filer i docs/chatgpt-paket/ med dokumentation, backend och frontend.
# Tar ENDAST git-spårade textfiler — .env, databaser och loggar kan aldrig läcka.
# Kör om skriptet och ersätt filerna i ChatGPT-projektet efter större ändringar.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
UT="$ROOT/docs/chatgpt-paket"
mkdir -p "$UT"
cd "$ROOT"

bundle() {  # bundle <utfil> <rubrik> <fil...>
  local namn="$1" out="$UT/$1" rubrik="$2"; shift 2
  {
    echo "Spelkompisen — $rubrik (paket för ChatGPT-granskning)"
    echo "Genererat: $(date '+%Y-%m-%d %H:%M') · git: $(git rev-parse --short HEAD)"
    echo "Varje fil inleds med raden '===== FIL: <sökväg> ====='."
  } > "$out"
  local f
  for f in "$@"; do
    [ -f "$f" ] || continue
    { echo; echo "===== FIL: $f ====="; echo; cat "$f"; } >> "$out"
  done
  echo "  $namn  ($(wc -l < "$out" | tr -d ' ') rader)"
}

echo "Bygger ChatGPT-paketet i docs/chatgpt-paket/ ..."
bundle 01-dokumentation.txt "dokumentation" \
  CLAUDE.md README.md docs/plan.md docs/forbattringar.md
# shellcheck disable=SC2046 — inga mellanslag i spårade sökvägar
bundle 02-backend.txt "backend (Python/FastAPI)" \
  backend/cli.py backend/requirements.txt backend/scripts/snapshot.sh \
  $(git ls-files 'backend/app/*.py')
bundle 03-frontend.txt "frontend (React/Vite)" \
  frontend/index.html frontend/vite.config.js \
  $(git ls-files 'frontend/src/*.jsx' 'frontend/src/*.js' 'frontend/src/*.css')
echo "Klart — ladda upp de tre filerna till ChatGPT-projektet (ersätt de gamla)."
