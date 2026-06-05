#!/bin/bash
# Stoppar appen (backend + frontend). Bakgrundsinsamlingen (launchd) lämnas
# orörd – styr den i UI:t eller med:  launchctl unload ~/Library/LaunchAgents/com.saman.svs.snapshot.plist
echo "→ Stoppar backend (8000) och frontend (5173) ..."
lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
lsof -ti:5173 | xargs -r kill -9 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
echo "✓ Appen stoppad. (Insamlingen fortsätter i bakgrunden om den är aktiv.)"
