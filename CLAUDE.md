# SvS kompisen

Personligt lokalt verktyg för att hitta **+EV-rader** på Svenska Spels poolspel
(Stryktipset, Europatipset, Topptipset) via odds, oddsrörelser, sharp-odds
(Pinnacle) och folkets streck. Ingen inloggning, ingen automatisk spelläggning.

## Arkitektur

```
backend/  Python 3.13 + FastAPI + httpx (venv i backend/.venv — INTE uv)
  app/svenskaspel.py  SvS pools-API-klient (PRODUCTS, GAME_GROUPS, Draw)
  app/pinnacle.py     Pinnacle Arcadia (gratis guest-API), + derive.py (1X2 ur spread/total)
  app/analysis.py     fair_prob (power-metod), värde, taggar, speltyp, mover-flagga
  app/builder.py      radbyggare: matematiskt/reducerat/garanti/SvS R-system/EV-topp
  app/storage.py      SQLite (data/svs.db): snapshots, sharp_snapshots, dedup, movement
  app/main.py         API-endpoints + PRIZE_PLANS (officiella vinstplaner)
  cli.py              show|spikar|snapshot|history|rad (snapshot körs av launchd)
frontend/ React + Vite, ALLT i src/App.jsx + App.css (mörkt tema)
start.sh / stop.sh    kör/stoppa båda lokalt
```

## Kommandon

- Starta allt: `./start.sh` (backend :8000, frontend :5173). Stoppa: `./stop.sh`.
- **Backend har INGEN auto-reload** — efter ändring:
  `lsof -ti:8000 | xargs kill -9; cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &`
- Frontend nås via Tailscale/LAN (vite.config: `host:true, allowedHosts:true`).
  Stoppa ALDRIG 5173-servern utan att starta om den — användaren kör mot den från mobilen.
- Verifiering i browser: preview-servern `frontend-preview` (port 5180) i `.claude/launch.json`.
- Bakgrundsinsamling: launchd `com.saman.svs.snapshot` var 30:e min → `backend/scripts/snapshot.sh`
  → `cli.py snapshot-smart` (alla produkter; förtätar SJÄLV till var 5:e min när någon omgång
  stänger inom 2 h, max ~25 min per körning). Skriv inte plist-filer åt användaren
  (behörighetsklassaren blockerar) — be hen köra `launchctl load`.
- Push-notiser (🔥 sen oddssänkning ≤8 h före spelstopp): `app/notify.py` via ntfy.sh.
  Aktiveras med `NTFY_TOPIC=<hemligt-namn>` i gitignore:ade `backend/.env` + prenumeration
  på samma topic i ntfy-appen. Utan topic = avstängt. Dedup per match via meta-tabellen.
- Projicerad slutomsättning: `_projected_turnover` i main.py (median av senaste avgjorda
  omgångars slutomsättning, cachad 6 h i meta). /api/payouts ger `projected_turnover` +
  `spelvarde_proj`; EV-/färgsystem räknar mot prognosen. EV mot dagens omsättning är glädjesiffror.

## Svenska Spel-API:t (öppet, inga nycklar)

- `https://api.spela.svenskaspel.se/draw/1/{slug}/draws` (lista) och `/draws/{nr}` (en omgång).
  Prefixet är ALLTID `1` (API-version, inte productId). Nyckel i svaret: `draws` (lista) / `draw` (singular).
- Slugs: stryktipset, europatipset (har listing); topptipset, topptipsetstryk, topptipsetextra
  (pid 25/23/24, INGEN listing → nummerscanning med seed i meta-tabellen). Topptipset-fliken
  aggregerar alla tre via `GAME_GROUPS`; varje omgång bär sin egen `product`-slug.
- Svenska decimaler: "5,50" → 5.50 (`_f` i svenskaspel.py). `svenskaFolket` = streck %,
  `currentNetSale` = omsättning, `drawEvents[].match.participants[].isoCode` = flaggor.
- `/draws/{nr}/result` ger `distribution` (faktiska vinstnivåer/utdelningar) — användbart för backtest.
- **Jackpot**: `/draw/1/jackpots` (matcha på productId + drawNumber — `fund` på draws är
  opålitligt och productName byter skepnad, t.ex. Europatipset = "VM-tipset" under VM).
  Belopp som svensk decimalsträng ("6000000,00").
- Vinstplaner (validerade mot utfall): Stryk/Europa 65 % åter, split 13/12/11/10 = 40/15/12/25 %.
  Topptipset 70 %, bara 8 rätt delar potten. Finns i `PRIZE_PLANS` i main.py.

## Pinnacle (sharp-odds, gratis)

- `https://guest.api.arcadia.pinnacle.com/0.1`, header `X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R`,
  soccer = sport 29. `/sports/29/matchups` + `/sports/29/markets/straight` (moneyline period 0).
  Amerikanska odds → decimal. Matchning via ISO/pycountry + fuzzy + tidsfönster + spegling 1↔2.
- Saknas moneyline härleds 1X2 ur spread/total (derive.py) — märks `P~` i UI.

## Domänmodell (kärnformler)

- **fair_prob**: overround bort med **power-metoden** (lös k så att Σ(1/odds)^k = 1) —
  korrigerar favorit/longshot-bias, bättre kalibrerad än proportionell normalisering.
  Sannolikhetskälla i prioritetsordning: SvS-odds → sharp (Pinnacle) → streck.
- **Värde-kvot** = fair_prob ÷ (streck/100). > 1.08 grönt (köpläge), < 0.92 rött (överspelat).
- **EV per rad** (poolspel): P(rad) × utdelning där utdelning = pott_nivå / (fält × P_folk(rad) + 1),
  cappad vid potten; fält = omsättning/radpris. P_folk = produkt av streck (oberoende-antagande).
  Medvinnare per nivå via Poisson-binomial. +1 = du själv. Detta är `evalRows` (frontend)
  och `build_ev_system` (backend) — håll dem konsistenta.
- **EV-topp-systemet** rankar kandidatrader (topp-2/3 tecken per match, cap 60k) efter
  toppnivå-EV, finrankar topp ~4k med full nivå-EV, tar budgetens bästa.
- Strategi (säker/medel/tuff) styr garderingssammansättning; **EV-reglaget är enda risk-axeln**
  (strategin sätter reglagets startpunkt 20/50/80 — ingen dold bias i backend).
- Teckenpoäng `_sign_score`: sharp-sannolikhet före SvS, bonus för tecken marknaden backar
  (fallande odds/ss_undervärderad) så de inte petas pga tillfällig överstreckning.
- **Steam** (`app/steam.py`): devigade sannolikhetsskift (pp) över 6/24/72 h — jämförbart
  favorit/skräll, marginalbrus borta. 🔥-flaggan + ntfy triggar på 24h-skiftet
  (≥3,5 pp markant, ≥6 pp stark); rå oddsrörelse är bara fallback utan sharp-serie.
  `movement_with_steam` är den delade rörelse-helpern (API + notiser — håll dem i synk).

## Export till Svenska Spel ("Egna rader")

- `.txt` (CRLF) med **obligatorisk rubrikrad** (annars "Produktnamnet verkar inte stämma"):
  Stryktipset/Europatipset = bara produktnamnet (`Stryktipset`); Topptipset =
  `Topptipset[,Stryk|,Europa],Omg=<nr>,Insats=<1–10>` (Stryk=topptipsetstryk,
  Europa=topptipsetextra). Därefter en rad per spelrad: `E,1,X,2,...`.
  Filspecen står på resp. produkts `/externa-systemspel`-sida (verifierad där).
  Uppladdning på `spela.svenskaspel.se/{stryktipset|europatipset|topptipset}/externa-systemspel`
  (alla Topptipset-varianter går via topptipset-sidan).
- Exportera alltid **konkreta enumererade rader** (E), aldrig M-system — annars förloras reduceringen.
- R 4-0-9 / R 0-7-16 / R 4-4-144 är exakta Hamming-täckningar (= SvS officiella rader).
  R 3-3-24 är greedy (38 rader) — spelas billigare direkt på SvS systemkupong.

## CLV-facit (signalvalidering)

- `app/clv.py` + `value_log`-tabellen: snapshot-pollen loggar tecken med grön
  värde-kvot (≥1.08) eller sharp-edge (≥2 %) — first/best per selektion.
  Stängning = devigad Pinnacle (sista sharp-snapshot före avspark); facit från
  resultat-API:t. `/api/clv` + "Signal-facit"-panelen i UI.
- Metodregel (från VM-projektet): ENDAST marknadspriser får logga flaggor —
  modellhärledda sannolikheter förorenar facitet. Se docs/forbattringar.md
  för fler metodlärdomar (steam i devigade pp, ClubElo, football-data-backtest).

## UI-konventioner

- Bred skärm (≥1280px): sektionspar i `.cols`-grid (Bygg förslag | Kupong,
  Sharp | Signal-facit). Kupongen är navet — export/inlämning finns BARA där
  (förslagsvyn har "Lägg i kupongen", inga dubblettknappar).
- Inga bakgrundstoner på odds-celler för värde/edge — kvot-pillret och märkena
  (★ S ▲ ⇊ ↓) bär den infon. Grön ram = i kupongen; grön ton + ×N = radläge.

- Mobil: ALLT i `@media (max-width:760px)` — desktop får inte ändras. Analystabellen blir kort
  (klass `analysis`, `data-sign` på odds-celler). OBS: `td:first-child`-regler måste exkludera
  `.chartrow` (grafradens enda td är också :first-child).
- Alla GET-fetch: `cache:'no-store'` + `&_t=${Date.now()}` (annars cachar webbläsare/iOS).
- Tillstånd (flik/omgång/kupong/inställningar) sparas i `localStorage` (`svs_state`) —
  iOS hemskärms-app slänger sidan ur minnet; bootstrap återställer om omgången är öppen.
- Inga `cursor: help`-frågetecken; förklaringar som title-tooltips på badges/pills/odds.

## Regler

- **Lägg ALDRIG spel automatiskt** — bara deep-link/fil; användaren laddar upp och betalar själv.
- Klicka inte i cookie-/samtyckesrutor åt användaren.
- Committa endast när användaren ber om det. Commit-meddelanden på svenska,
  imperativ rubrik, avsluta med `Co-Authored-By: Claude <modell>`.
- API-nycklar i gitignore:ad `backend/.env` (ODDS_API_KEY finns där, the-odds-api är vilande).
- Användarens långsiktiga backlog: `docs/forbattringar.md`.
