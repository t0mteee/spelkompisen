#!/bin/bash
# Startar Stryktips-hjälpen lokalt: backend (FastAPI) + frontend (Vite).
# Avsluta med Ctrl+C (eller kör ./stop.sh från en annan terminal).
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

# frigör portar om något hänger kvar sedan tidigare.
# -sTCP:LISTEN => döda bara servern, inte klienter (t.ex. webbläsare anslutna till porten).
lsof -ti:8000 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
lsof -ti:5173 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true

echo "→ Startar backend på http://127.0.0.1:8000 ..."
( cd "$ROOT/backend" && exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
BACKEND_PID=$!
trap 'echo; echo "→ Stänger ner ..."; kill $BACKEND_PID 2>/dev/null; lsof -ti:5173 -sTCP:LISTEN | xargs -r kill 2>/dev/null' EXIT INT TERM

for _ in $(seq 1 20); do
  curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 0.5
done
echo "✓ Backend uppe."

echo "→ Startar frontend – öppna http://localhost:5173 ..."
cd "$ROOT/frontend"
npm run dev
