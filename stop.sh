#!/bin/bash
# Stoppar appen (backend + frontend). Ev. bakgrundsinsamling (launchd) lämnas orörd.
echo "→ Stoppar backend (8002) och frontend (5175) ..."
# -sTCP:LISTEN => bara serverprocesserna, inte klienter (webbläsare) anslutna till porten.
lsof -ti:8002 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
lsof -ti:5175 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
# (Aldrig 'pkill -f uvicorn' – det dödar även svs (8000) och vm (8001), samma kommando.)
echo "✓ Appen stoppad."
