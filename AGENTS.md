# Spelkompisen — instruktioner för Codex

**Läs i denna ordning (duplicera aldrig innehållet hit — kopior driftar):**

1. `CLAUDE.md` — den underhållna projektinstruktionen: arkitektur, kommandon,
   API-egenheter, domänformler, metodregler, UI-konventioner. Allt där gäller
   Codex likadant.
2. `docs/plan.md` — **STATUS-SAMMANFATTNINGEN överst är projektets sanning**;
   därefter den prioriterade WP-backloggen.
3. `docs/overlamning-2026-08-01-codex-hardening.md` — AKTUELL överlämning:
   ren livekohort v4, tre-källorsradar, settlement/close-facit och
   providerseparerad modelldata v4. Föregående Flashscore-överlämning är
   uttryckligen ersatt men behålls som historik; 2026-07-16-versionens
   "Fallgropar" gäller fortfarande.
4. `docs/granskning-2026-07-13.md` — granskningsevidens (fil:rad/DB) och
   acceptanskriterier per arbetspaket. `docs/db-atgarder.md` — logg över
   databas-åtgärder + processregeln.

## Codex-specifikt

- Commit-meddelanden på svenska, imperativ rubrik, avsluta med
  `Co-Authored-By: Codex <modell>`. **Committa färdigt arbete utan att fråga**
  (Samans stående order 2026-08-11). Committa bara egna ändringar — aldrig
  `git add .`, aldrig `backend/data/`, aldrig hemligheter, och rör inte andras
  ocommittade ändringar i arbetskatalogen.
- Preview/launch-konfigurationen ligger i `.claude/launch.json` (delas av båda
  assistenterna — katalognamnet är historiskt, skapa ingen egen kopia).
- Rör ALDRIG `/Users/saman/svs` eller `/Users/saman/vm`. Lägg ALDRIG spel
  automatiskt. Enbart gratiskällor. Inga API-nycklar utanför `backend/.env`.
- DB-ändringar = skript + backup + rapport (`docs/db-atgarder.md`) — aldrig
  ad-hoc-SQL. Grönt beslutas per signalgrupp, aldrig per tier. Bumpa
  `DATA_VERSION`/`MODEL_PARAMS` när databehandling/algoritm ändras.
- Backend har ingen auto-reload: efter ändring
  `lsof -ti:8002 -sTCP:LISTEN | xargs kill -9; cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 &`
  — ALDRIG `pkill -f uvicorn` (dödar svs/vm) och ALDRIG `lsof -ti:<port>` utan
  `-sTCP:LISTEN`.
