#!/bin/bash
# Stoppar appen (backend + frontend). Bakgrundsinsamlingen (launchd) lämnas
# orörd – styr den i UI:t eller med:  launchctl unload ~/Library/LaunchAgents/com.saman.svs.snapshot.plist
echo "→ Stoppar backend (8000) och frontend (5173) ..."
# -sTCP:LISTEN => bara serverprocesserna, inte klienter (webbläsare) anslutna till porten.
lsof -ti:8000 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
lsof -ti:5173 -sTCP:LISTEN | xargs -r kill -9 2>/dev/null || true
# (tog bort 'pkill -f "uvicorn app.main:app"' – den dödade även VM-projektets
#  backend på 8001 eftersom båda kör samma kommando.)
echo "✓ Appen stoppad. (Insamlingen fortsätter i bakgrunden om den är aktiv.)"
