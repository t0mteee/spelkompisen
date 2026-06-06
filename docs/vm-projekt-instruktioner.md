# Instruktioner: VM-koll (nytt projekt) — återanvänd från `svs`

Self-notes till nästa tråd. Mål: en snygg sida med **stenkoll på fotbolls-VM 2026**.
Bygg INTE i `svs`-repot — starta nytt projekt. Det här dokumentet sammanfattar vad
som kan återanvändas och de svåra lärdomarna (särskilt API:er).

## Vad sidan ska göra
1. Lista matcher i datum/tid-ordning, snyggt UI med **flaggor**, **arena + stad**.
2. Per match: odds från **Pinnacle** och **Svenska Spel**, samt **spåra & visa oddsrörelser**.
3. Per match: båda lagens **5 senaste matcher + resultat**.
4. Per matchup: **nyheter/previews** (skador, förväntade laguppställningar) från olika siter.

## Stack & arkitektur (återanvänd rakt av från `svs`)
- **Backend:** Python 3.13 + FastAPI + httpx. **Frontend:** React + Vite (en `App.jsx`, mörkt tema).
- Körs **lokalt**, ingen inloggning. `python3 -m venv backend/.venv`.
- **SQLite** för all lagring (tidsserier + nyckel/värde-meta). Mönster i `svs/backend/app/storage.py`:
  snapshots med **dedup (spara bara vid förändring)**, `meta(key,value)`-tabell, `first/last`-rörelse.
- **start.sh / stop.sh** i repo-roten (backend :8000 + Vite :5173, dödar gamla portar). Kopiera.
- **Bakgrundsinsamling = launchd** (`backend/scripts/snapshot.sh` + `com.*.plist`). Kör en CLI var N:e min.
  OBS: användaren måste `launchctl load` själv (att skriva plist till ~/Library/LaunchAgents blockeras
  ibland av behörighetskontrollen — lägg plist i repot och ge load-kommandot).
- **.env-loader utan beroenden:** `svs/backend/app/config.py` (lägg ev. API-nycklar i gitignore:ad `.env`).
- **CORS** för localhost:5173. **Viktigt:** alla GET-fetch i frontend ska ha `cache:'no-store'` +
  `&_t=${Date.now()}` annars cachar webbläsaren och data "uppdateras inte".

## Datakällor — konkret (det svåraste, spar mest tid)

### Pinnacle (gratis, ingen auth) — KOPIERA `svs/backend/app/pinnacle.py`
- Bas: `https://guest.api.arcadia.pinnacle.com/0.1`
- Header: `X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R` (publik guest-nyckel) + vanlig User-Agent.
- Soccer = **sport id 29**. Endpoints:
  - `GET /sports/29/leagues` → hitta VM-ligan (sök namn "World Cup" / "FIFA"). Spara dess `id`.
  - `GET /leagues/{ligaId}/matchups` (gratis) → matcher. Filtrera `parent===null && type==='matchup'`
    (övriga är specialmarknader). `participants[].alignment` = home/away, `startTime`.
  - `GET /leagues/{ligaId}/markets/straight` → odds. Ta `type==='moneyline' && period===0`,
    `prices[].designation` = home/draw/away i **amerikanskt format** → konvertera till decimal:
    `a>0 ? 1+a/100 : 1+100/(-a)`. (Kod finns: `american_to_decimal`, även spread/total + 1X2-härledning i `derive.py`.)
  - Alternativt sport-nivå: `/sports/29/matchups` + `/sports/29/markets/straight` (allt soccer i 2 anrop).
- Lagmatchning mellan källor: `svs/backend/app/odds_provider.py` har `_norm`, `english_name` (ISO→namn via
  pycountry), `_best_side`, tidsfönster, och **testa båda lagorienteringarna + spegla 1↔2**. Återanvänd.

### Svenska Spel-odds för VM = **Oddset** (ej tipsspel-API:t!)
- `svs` använde `api.spela.svenskaspel.se/draw/1/{slug}/draws...` — det är för Stryktipset/Topptipset, INTE VM.
- För enskilda VM-matchers 1X2 behövs **Oddset/sportbook-API:t**. MÅSTE undersökas i nästa tråd
  (troligen annan host/endpoint under `api.spela.svenskaspel.se` eller `api.www.svenskaspel.se/external/1`;
  den senare kräver dock auth). Använd Claude-in-Chrome-extensionen och inspektera nätverksanropen på
  spela.svenskaspel.se/oddset för en VM-match (se "Browser-tips" nedan).

### the-odds-api (backup, kostar credits)
- Har **`soccer_fifa_world_cup`** (VM-2026-matcherna ligger där). Gratis-tier 500 credits;
  `/sports` och `/events` gratis, odds = 1 credit/match/region. Flera bookmakers inkl Pinnacle.
- Bra som fallback om Pinnacle saknar en match. Nyckel finns ej — användaren får skaffa gratis.

### Matcher, lag-form (5 senaste), arena/stad, flaggor — NY källa behövs
- Behöver en fotbolls-data-API. Rekommendation i prioritet:
  1. **API-Football (api-sports.io)** — mest komplett: fixtures (med **venue + stad**), `teams/statistics`,
     **senaste matcher/form**, **lineups**, **injuries**, **predictions**. Free-tier ~100 anrop/dag. Kräver nyckel.
  2. **football-data.org** — gratis, har VM, fixtures, resultat (form härleds från resultat). Enklare.
  3. **TheSportsDB** — gratis, har lag, **flaggor/badges**, arenor, senaste events. Bra fallback/komplement.
- **Flaggor:** ISO-landskod → `https://flagcdn.com/{iso2}.svg` eller flagg-emoji. (Landslag → iso via pycountry.)
- **Form-UI:** W/D/L-pills (grön/grå/röd) + resultat, likt värde-pillrarna i `svs/frontend/src/App.css`.

### Nyheter/previews (skador, laguppställningar)
- Bäst strukturerat: **API-Football** `injuries` + `lineups` (predicted) + `predictions`.
- Allmänna nyheter/previews: **NewsAPI.org** (free-tier) eller **Google News RSS** per matchup-query
  (`https://news.google.com/rss/search?q={lag1}+{lag2}+preview&hl=sv`). Parsa RSS, visa kort med källa/länk.
- Visa länkar — skrapa inte hela artiklar (upphovsrätt). Korta sammanfattningar + källänk.

## Oddsrörelse-mönster (återanvänd direkt)
- Tidsserie-tabell i SQLite per källa; dedup vid förändring; `first/last` + min/max för drift.
- Bakgrunds-poll (launchd) var ~15–30 min. För VM-matcher: poll tätare nära avspark.
- **Graf-komponent:** `MiniChart`/`MovementChart` i `svs/frontend/src/App.jsx` — en liten graf per utfall
  (1/X/2) med odds-axel + tidsaxel + "↓ stärkts". Kopiera och rendera Pinnacle vs SvS.

## Konkreta moduler att kopiera från `svs/backend/app/`
- `pinnacle.py` — Arcadia-klient (+ `derive.py` om 1X2 saknas men spread/total finns).
- `odds_provider.py` — bara hjälpfunktionerna: `_norm`, `english_name`, `_best_side`, `_hours_apart`, trösklar.
- `storage.py` — mönster för snapshots/tidsserie/dedup/meta (bygg om tabellerna för matcher/odds/form/news).
- `config.py` (.env), CORS-setup i `main.py`, `start.sh`/`stop.sh`, launchd-plist + `scripts/snapshot.sh`.
- Frontend: dark-tema CSS, fetch-mönster (`no-store` + cache-bust), MiniChart, badge/pill-stil.

## Föreslagen datamodell (nya projektet)
- `match(id, kickoff, stage/group, home, away, home_iso, away_iso, venue, city, status, result)`
- `odds_snapshot(match_id, source, sign, odds, fetched_at)` (source: 'pinnacle'|'svenskaspel')
- `form(team, opponent, result W/D/L, score, date)` (eller hämta on-demand och cacha)
- `news(match_id, source, title, url, published, summary)`
- Endpoints: `GET /api/matches` (sorterade på kickoff, grupperade per datum),
  `GET /api/match/{id}` (odds + rörelse + form + news). Bakgrundsinsamlare för odds + nyheter.

## UI-skiss
- Matchlista per datum, **flagga + lagnamn**, kickoff (lokal tid), **arena · stad**, kort odds-rad (P / SvS).
- Klick på match → odds + **oddsrörelse-graf** (Pinnacle vs SvS), **senaste 5 (W/D/L-pills + resultat)**
  för båda lag, och **nyhets-/preview-kort** (skador, trolig 11, källänkar).
- Mörkt tema, kompakt, hover-tooltips (som `svs`).

## Browser-tips (Claude-in-Chrome) — för att hitta odolda API:er
- `tabs_context_mcp(createIfEmpty:true)` → egen flik. Nätverksspårning startar vid första `read_network_requests`-
  anropet → **ladda om sidan efter** att spårning aktiverats (annars cachat/missat).
- **Query-strängar maskeras** i href/`read_network_requests`/`location.search` — MEN den fullständiga URL:en
  syns i "Tab Context"-raden längst ner i verktygssvaret. (Så hittade jag draw=966&product=23.)
- SPA-data finns sällan i DOM; läs JS-chunks eller `fetch` i sid-kontext via `javascript_tool`
  (async IIFE, returnera promise — undvik top-level `await`). Hjälpsidor ("hur funkar det") avslöjar vendor-logik.

## Säkerhetsregler (gäller även nästa projekt)
- **Klicka inte i cookie-/samtyckesrutor** åt användaren; **lägg inga pengaspel** åt användaren.
- Be användaren installera Claude-tillägget i Chrome om webbläsarinspektion behövs.
- Lägg ev. API-nycklar i gitignore:ad `.env`.

## Snabb startordning i nästa tråd
1. Scaffold backend (FastAPI) + frontend (Vite), kopiera config/CORS/start.sh.
2. Pinnacle-klient → hitta VM-ligan, lista matcher + odds. Verifiera mot riktig data.
3. Datamodell + SQLite + odds-snapshots (dedup) + launchd-poll.
4. Lägg till fotbolls-data-API (form/venue/flaggor) — börja med en match end-to-end.
5. Nyheter/previews per matchup.
6. Frontend: matchlista → matchvy med odds/rörelse/form/nyheter.
7. Undersök Svenska Spel Oddset-API:t (browser-nätverk) och lägg till som andra oddskälla.
