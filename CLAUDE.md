# Spelkompisen

Personligt lokalt verktyg som kombinerar **SvS kompisen** (poolspels-analys: Stryktipset,
Europatipset, Topptipset, Bomben) med en ny **Oddset-del**: enskilda matcher (Allsvenskan,
norska Eliteserien, träningsmatcher till att börja med) med sharp-odds, oddsrörelser,
egen modell och värdespels-tips (1X2, asian handicap, över/under, hörnor på sikt).

**Läge (2026-07-23):** Etapp 0–5 KLARA + långt därutöver. Oddset-delen är i full drift:
6 ligor (Allsvenskan/Superettan/Eliteserien/OBOS/MLS/träningsmatcher), 4 bokkällor +
Pinnacle, kvalitetsviktade värdesignaler, steam-radar, xG-viktad Poisson-modell med
DC-korrektion (amber, settlement-ankrad efter T — kalla den inte DC-MLE), frånvarodata, CLV-facit
per tier med grönt-kriterium v2 (≥50 stängda OCH undre bootstrap-KI-gräns > 0, per
liga/marknad/modellversion). **STATUS-SAMMANFATTNINGEN överst i `docs/plan.md` är
sanningen — LÄS DEN FÖRST i ny session** (+ WP-backloggen där, prioriterad; gransknings-
evidens i `docs/granskning-2026-07-13.md`).
Den underkända V2.1 är fortsatt vilande. Ett separat V2.2-experiment samlar
Allsvenskan + research-only Premier League/Serie A/La Liga/Bundesliga med WP9c
i isolerad sharp-identitetskontroll; se
`docs/model-v2.2-multileague-forward-manifest.json`. Det är inte en tränad
modell och får inte påverka tips, notiser eller CLV.

**Relationen till syskonprojekten:**
- `/Users/saman/svs` (SvS kompisen, portar 8000/5173) — ursprunget, **FRYST ARKIV sedan
  2026-07-20** (paritet nådd: launchd urlastat, servrar stoppade, DB kvar som arkiv;
  återaktivering via plist i svs/backend/scripts/). RÖR ALDRIG svs härifrån.
- `/Users/saman/vm` (Boll boll kollen, portar 8001/5174) — VM-bevakning, mönsterkälla för
  Oddset-delen (Pinnacle AH/ÖU/hörnor, Kambi-klient, värdescreen, steam, Dixon-Coles, CLV).
  Läs vm-koden som referens vid portning men RÖR den inte.
- Portar här: **backend 8002, frontend 5175, preview 5181** — krockar aldrig med svs/vm.

## Arkitektur

```
backend/  Python 3.13 + FastAPI + httpx (venv i backend/.venv — INTE uv)
  app/svenskaspel.py  SvS pools-API-klient (PRODUCTS, GAME_GROUPS, Draw)
  app/pinnacle.py     Pinnacle Arcadia (gratis guest-API), + derive.py (1X2 ur spread/total)
  app/analysis.py     fair_prob (power-metod), värde, taggar, speltyp, mover-flagga
  app/builder.py      radbyggare: matematiskt/reducerat/garanti/SvS R-system/EV-topp
  app/bomben.py       Poisson-målmodell för Bomben
  app/storage.py      SQLite (data/stryktips.db): snapshots, sharp_snapshots, dedup, movement
  app/oddset_v22.py   isolerad V2.2 feature-/shadowcapture (ej live-tips)
  app/main.py         API-endpoints + PRIZE_PLANS (officiella vinstplaner)
  cli.py              show|spikar|snapshot|history|rad
frontend/ React + Vite, ALLT i src/App.jsx + App.css (mörkt tema)
start.sh / stop.sh    kör/stoppa båda lokalt (8002 + 5175)
docs/plan.md          FÄRDPLANEN: etapper, datakällor, beslut — projektets sanning
docs/forbattringar.md ärvd svs-backlog (poolspels-lärdomar, fortfarande giltiga)
```

## Kommandon

- Starta allt: `./start.sh` (backend :8002, frontend :5175). Stoppa: `./stop.sh`.
- Tester: `cd backend && .venv/bin/python -B -m unittest discover -s tests -v`.
- V2.2-status: `cd backend && .venv/bin/python -B cli.py v22audit`.
- **Backend har INGEN auto-reload** — efter ändring:
  `lsof -ti:8002 -sTCP:LISTEN | xargs kill -9; cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 &`
- ALDRIG `pkill -f uvicorn` (dödar svs 8000 och vm 8001 — samma kommando).
  ALDRIG `lsof -ti:<port>` utan `-sTCP:LISTEN` (dödar annars webbläsare med öppna sockets).
- Frontend nås via Tailscale/LAN (vite.config: `host:true, allowedHosts:true`).
- Verifiering i browser: preview-servern `frontend-preview` (port 5181) i `.claude/launch.json`.
- **Insamling: launchd `com.saman.spelkompisen.snapshot` är LADDAT** och kör
  `backend/scripts/snapshot.sh` → `cli.py smart` var 30:e min: fullt varv (alla källor +
  Kambi-deep + modelldata + poolspel) och därefter snabbvarv var 4:e min så länge någon
  match startar inom 3 h (Pinnacle + böckernas 1X2 + SvS-deep för 3h-matcherna;
  `FAST_WITHIN_H` i oddset.py)
  och/eller tätvarv var 5:e min när ett poolspel stänger inom 2 h — allt inom ~25 min
  budget. Notiser går i samma varv, bakom **notisvakten** (presence-set: larm kräver att
  priset observerades i det aktuella lyckade varvet).
- **WP2-prisregel:** `fetched_at` = prisförändring, `last_seen_at` = senaste
  lyckade bekräftelse. Värde/modell/steam/facit kräver `available` och högst
  45 min gammal bekräftelse. Källfel får aldrig markera ett pris unavailable.
- Push-notiser: `app/notify.py` via ntfy.sh, kräver `NTFY_TOPIC` i gitignore:ade
  `backend/.env`. Använd ett EGET topic (inte samma som svs — annars dubbla notiser).
  Notifieringsspåret är pausat på Samans begäran 2026-07-16 — återuppta inte utan besked.

## Poolspelen (ärvt från svs — allt gäller oförändrat)

### Svenska Spel-API:t (öppet, inga nycklar)

- `https://api.spela.svenskaspel.se/draw/1/{slug}/draws` (lista) och `/draws/{nr}` (en omgång).
  Prefixet är ALLTID `1` (API-version, inte productId). Nyckel i svaret: `draws` (lista) / `draw` (singular).
- Slugs: stryktipset, europatipset (har listing); topptipset, topptipsetstryk, topptipsetextra
  (pid 25/23/24, INGEN listing → nummerscanning med seed i meta-tabellen). Topptipset-fliken
  aggregerar alla tre via `GAME_GROUPS`; varje omgång bär sin egen `product`-slug.
- Svenska decimaler: "5,50" → 5.50 (`_f` i svenskaspel.py). `svenskaFolket` = streck %,
  `currentNetSale` = omsättning, `drawEvents[].match.participants[].isoCode` = flaggor.
- `/draws/{nr}/result` ger `distribution` (faktiska vinstnivåer/utdelningar).
- **Jackpot**: `/draw/1/jackpots` (matcha på productId + drawNumber — `fund` på draws är
  opålitligt). Belopp som svensk decimalsträng ("6000000,00").
- Vinstplaner (validerade): Stryk/Europa 65 % åter, split 13/12/11/10 = 40/15/12/25 %.
  Topptipset 70 %, bara 8 rätt delar potten. Finns i `PRIZE_PLANS` i main.py.

### Pinnacle (sharp-odds, gratis)

- `https://guest.api.arcadia.pinnacle.com/0.1`, header `X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R`,
  soccer = sport 29. `/sports/29/matchups` + `/sports/29/markets/straight` (moneyline period 0).
  Amerikanska odds → decimal. Matchning via ISO/pycountry + fuzzy + tidsfönster + spegling 1↔2.
- Saknas moneyline härleds 1X2 ur spread/total (derive.py) — märks `P~` i UI.
- OBS (vm-lärdom): Arcadia Cloudflare-blockar i perioder på IP-nivå — headers/TLS hjälper EJ.
  vm:s fallback via the-odds-api är mönstret om det blir akut.

### Domänmodell (kärnformler)

- **fair_prob**: overround bort med **power-metoden** (lös k så att Σ(1/odds)^k = 1).
  Sannolikhetskälla i prioritetsordning: SvS-odds → sharp (Pinnacle) → streck.
- **Värde-kvot** = fair_prob ÷ (streck/100). > 1.08 grönt (köpläge), < 0.92 rött (överspelat).
- **EV per rad** (poolspel): P(rad) × utdelning där utdelning = pott_nivå / (fält × P_folk(rad) + 1),
  cappad vid potten. Jackpot/rullpott läggs på toppnivån **före radvalet**.
  Medvinnare per nivå via Poisson-binomial. +1 = du själv.
  `evalRows` (frontend) och `build_ev_system` (backend) — håll dem konsistenta.
- **κ för poolmedvinnare** skattas som `Σ faktiska vinnare / Σ prognos` med
  omgången som bootstrap-block, aldrig som medel/geometriskt medel av enskilda
  kvoter. Nuvarande 100-omgångsfacit motiverar ingen optimistisk runtime-
  korrektion; toppnivån kör κ=1,00. Lägre nivåer är uttryckligen approximationer.
- **Värderader**: score = P(rad)^k × EV(rad) där k = 2·(1−value_weight); reglaget är enda
  risk-axeln (strategin sätter bara startpunkten 20/50/80).
- **RLM**: folket och devigad sharp åt olika håll (◆ smart pengar / ⚠ fadea).
- **Streck-allokering** (`_size_to_budget`): värde/kostnads-girig per Δlog(täckt sannolikhet)/Δlog(rader).
- **Steam** (`app/steam.py`): devigade sannolikhetsskift (pp) över 6/24/72 h; 🔥 + ntfy på
  24h-skiftet (≥3,5 pp markant, ≥6 pp stark). `movement_with_steam` är delade helpern.
- Bomben: kolumn-baserad byggare (rader = manuell ifyllnad = fil = kostnad), Poisson-modell,
  hålls utanför CLV-facitet (modell-härledd). INGEN exakt-rad-reducering.
- Projicerad slutomsättning: `_projected_turnover` i main.py — EV-/färgsystem räknar mot
  prognosen; EV mot dagens omsättning är glädjesiffror.

### Export till Svenska Spel ("Egna rader")

- `.txt` (CRLF) med obligatorisk rubrikrad: Stryktipset/Europatipset = produktnamnet;
  Topptipset = `Topptipset[,Stryk|,Europa],Omg=<nr>,Insats=<1–10>`. Därefter `E,1,X,2,...`.
- Exportera alltid konkreta enumererade rader (E), aldrig M-system.
- Uppladdning på `spela.svenskaspel.se/{produkt}/externa-systemspel`.
- R 4-0-9 / R 0-7-16 / R 4-4-144 är exakta Hamming-täckningar; R 3-3-24 är greedy (38 rader).

### CLV-facit (signalvalidering)

- `app/clv.py` + `value_log`-tabellen: gröna värde-kvoter (≥1.08) / sharp-edge (≥2 %) loggas
  first/best per selektion; stängning = devigad Pinnacle; facit från resultat-API:t.
- **Metodregel (dyrast lärdom från vm):** ENDAST marknadspriser får logga flaggor —
  modellhärledda sannolikheter förorenar facitet.
- Oddset-facitets identitet är match + marknad + tecken + normaliserad lina +
  semantisk signalversion. Stäng alltid mot flaggans lina när ett färskt pris
  finns; spara annars slutlinans delta som `linje flyttad` utan fabricerat
  close-EV. Positivt `line_move_score` betyder rörelse med selektionen.
- WP5-ledgern (`app/oddset_ledger.py`) är forskningsfacitet: alla prediktioner
  och oflaggade kontroller fryses vid T−24 h/T−3 h/T−20 min. Bakfyll aldrig en
  missad horisont; capture-markören bevarar även tomt källutfall. Endast captures
  inom 45/15/10 min timingtolerans får bidra till candidate/green.
- Primära grupper är sharp × 1X2 × Allsvenskan/Superettan/Eliteserien/OBOS/
  MLS. Träningsmatcher och alla andra grupper är utforskande och kräver
  BH-FDR 10 %. Candidate är sticky; green kräver out-of-time-data efter
  candidate-datumet. Aggregat får aldrig ändra gruppstatus.
- V2.2-shadow (`app/oddset_v22.py`) får bara samla de fem manifestligorna/1X2.
  PL/Serie A/La Liga/Bundesliga är `research_only` och filtreras ur ordinarie
  API/UI. Före träningsgaten måste `p_v22 == p_sharp` exakt; tabellen läses
  inte av värde-, notis-, CLV- eller ordinarie UI-vägar.

## Oddset-delen (byggs nu — se docs/plan.md för detaljer)

- Mönsterkälla: `/Users/saman/vm/backend/app/` — `pinnacle.py` (AH/ÖU/hörn-specials via
  units='Corners'), Kambi-klienten (Svenska Spel Sport, operator `svenskaspel`, milliodds:
  1420=1.42, line i milli: 2500=2.5), `value.py`/`service.value_screen` (power-devig sharp
  vs bok), `model.py` (Dixon-Coles, μ KALIBRERAS mot sharp ÖU-linje ≈ median), steam/CLV/
  notify-mönstren, `elo.py` (ClubElo), `oddsapi.py` (the-odds-api, vilande).
- Enbart gratiskällor (användarbeslut 2026-07-12); rena betalspår = framtida projekt.
- Tier-regel för tips: **sharp-ankrat = actionable (grönt, in i CLV); modell-utan-sharp =
  amber (bakom toggle, UR CLV)** — vm bevisade tre gånger att modell-edges utan sharp-ankare
  blir systematiskt uppblåsta (DC alt-totaler +40–55 %, hörnor +120 % okalibrerat).
- Metodregler från granskningen 2026-07-13/16 (`docs/granskning-2026-07-13.md`):
  asiatiska sannolikheter alltid settlement-aware (push/half-win) även i ankring;
  notiser kräver närvaro-bekräftat bokpris (✅ notisvakten); alla prediktioner loggas vid
  fasta horisonter med modellversion — flaggor är urval för handling, inte
  utvärderingsunderlag; **grönt beslutas per signalgrupp, aldrig per tier/aggregat**;
  versionspolicy: `signal_version` (s-/m-fingeravtryck) grupperar facitet, `git_hash`
  ger reproducerbarhet — docs/UI-commits får inte fragmentera facitet.
- **DB-ändringar = skript + backup + rapport** (`docs/db-atgarder.md`) — aldrig ad-hoc-SQL.

## UI-konventioner

- v2-design: 13px bas, sektioner är kort (`section` = --panel, inre ytor = --panel2),
  pill-tabbar i kompakt header, EN statusrad. Bred skärm (≥1280px): sektionspar i `.cols`-grid.
- Mobil: ALLT i `@media (max-width:760px)` — desktop får inte ändras. OBS:
  `td:first-child`-regler måste exkludera `.chartrow`.
- Alla GET-fetch: `cache:'no-store'` + `&_t=${Date.now()}` (annars cachar webbläsare/iOS).
- Tillstånd sparas i `localStorage` (`svs_state`); bootstrap återställer.
- Inga `cursor: help`-frågetecken; förklaringar som title-tooltips.
- Oddset-delen: röd = oddset NER (ökad vinstchans), grön = UPP (vm-konvention).
- Frånvaro: `oddset_absence_capture` + `oddset_absence_player` är PIT-historiken;
  capture skrivs även för en lyckad tom lista. Sofascore `player.id` och position
  bevaras. `meta oddset_abs:*` är bara senaste-payload för bakåtkompatibilitet.
- ClubElo: `oddset_elo_capture`/`oddset_elo_rating` är observerade dagrankingar;
  `oddset_elo_history` är providerintervall för historisk `as_of`-läsning.
  Retroanalys får aldrig använda dagens meta-ranking. Backfill markerar bara en
  klubb klar efter ett entydigt lyckat svar; timeout/502 ska förbli retrybart.
- Resultatidentitet: fuzzy auto-merge kräver >0,75 och ALLA sådana länkar ska
  synas i `cli.py modeldata` tills de flyttats till `TEAM_ALIAS`/meta. Förslag i
  0,55–0,75 mergas aldrig. Kända falska par läggs i `TEAM_REJECTED_LINKS` och
  redovisas som verifierade avvisningar (Egersund ≠ Haugesund).

## Regler

- **Lägg ALDRIG spel automatiskt** — bara deep-link/fil; användaren laddar upp och betalar själv.
- Klicka inte i cookie-/samtyckesrutor åt användaren.
- Committa endast när användaren ber om det. Commit-meddelanden på svenska,
  imperativ rubrik, avsluta med `Co-Authored-By: Claude <modell>`.
- API-nycklar i gitignore:ad `backend/.env` (ODDS_API_KEY finns, the-odds-api är vilande).
- Rör ALDRIG `/Users/saman/svs` eller `/Users/saman/vm` från detta projekt.
- Uppdatera STATUS-blocket i `docs/plan.md` när en etapp/delmål blir klar.
