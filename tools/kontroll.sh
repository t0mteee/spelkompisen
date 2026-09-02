#!/bin/bash
# Hela kontrollen före push: backendtester, frontendlint, frontendtester.
# Samma kommando för människa, Claude och Codex — och för pre-push-hooken
# i tools/githooks (aktiveras med: git config core.hooksPath tools/githooks).
#
#   tools/kontroll.sh            allt
#   tools/kontroll.sh backend    bara backendtester
#   tools/kontroll.sh frontend   bara lint + frontendtester
#
# Bakgrund: 837 tester fanns men inget körde dem — main var röd i ett dygn
# (2026-09-02) utan att någon såg det.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Serverns node ligger utanför PATH i icke-interaktiva skal; launchd-jobben
# använder samma runtime.
RUNTIME="$HOME/.local/spelkompisen-runtime/bin"
[ -d "$RUNTIME" ] && export PATH="$RUNTIME:$PATH"
DEL="${1:-allt}"
fel=0
resultat=()

kor() {  # kor <namn> <katalog> <kommando...>
  local namn=$1 dir=$2; shift 2
  local logg; logg=$(mktemp)
  printf '\n→ %s\n' "$namn"
  if ( cd "$dir" && "$@" ) >"$logg" 2>&1; then
    tail -n 3 "$logg"
    resultat+=("✓ $namn")
  else
    grep -E '^(FAIL|ERROR):|^not ok|error' "$logg" | head -n 20
    tail -n 5 "$logg"
    resultat+=("✗ $namn")
    fel=1
  fi
  rm -f "$logg"
}

if [ "$DEL" = allt ] || [ "$DEL" = backend ]; then
  kor "backendtester" "$ROOT/backend" .venv/bin/python -B -m unittest discover -s tests
fi
if [ "$DEL" = allt ] || [ "$DEL" = frontend ]; then
  if command -v npm >/dev/null 2>&1; then
    kor "frontendlint" "$ROOT/frontend" npm run -s lint
    kor "frontendtester" "$ROOT/frontend" npm run -s test
  else
    echo "✗ npm saknas i PATH — frontend kan inte kontrolleras här"
    resultat+=("✗ frontend (npm saknas)"); fel=1
  fi
fi

printf '\n== kontroll ==\n'
printf '%s\n' "${resultat[@]}"
[ "$fel" -eq 0 ] && echo "ALLT GRÖNT" || echo "STOPP — rätta innan push (medvetet förbi: SKIP_KONTROLL=1)"
exit "$fel"
