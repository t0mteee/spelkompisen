# Tips-hjälpen

Personligt verktyg för att analysera Svenska Spels tipsspel — **Topptipset,
Stryktipset och Europatipset** — hitta spikar, värdestreck och oddsrörelser,
samt föreslå rader och system. Spelväljare i toppen; Topptipset (8 matcher,
körs varje kväll) har även en omgångsväljare eftersom flera kuponger kan vara
öppna samtidigt.

Körs **lokalt**. Stack: Python + FastAPI (backend), React kommer senare (frontend).

## Status

**Klart:**
- **Datainsamling**: hämtar aktuell omgång från Svenska Spels öppna API (odds,
  startodds, svenska folkets streck + referensvärden, Kambi/BetRadar-id:n).
  Saknas odds tidigt i veckan används streck som fallback.
- **Analys**: overround-justerad sannolikhet, värde (`fair% - streck%`),
  oddsrörelse (`odds` vs `startOdds`), spik-score och öppen-score.
- **Snapshots**: loggar i SQLite (sparar bara vid förändring) så oddsrörelse
  kan följas fram till matchstart.
- **Radmotor**: bygger spelförslag per strategi (säker/medel/tuff) och budget,
  som matematiskt system eller reducerat (villkors-/färgreducering).
- **Frontend**: React-vy (Vite) med analystabell, spik/öppen-staplar, radbyggare,
  start/stopp-knapp för insamling och oddsrörelse-graf (klicka på en match).
- **Insamlare i appen**: starta/stoppa datainsamling från UI:t (bakgrundstråd).
- **Extern oddskälla** (valfri): the-odds-api.com som backup för matcher utan
  Svenska Spel-odds + Pinnacle som sharp-referens. Aktiveras med `ODDS_API_KEY`.

### Starta appen (enklast)

```bash
./start.sh     # startar backend + frontend → http://localhost:5173
./stop.sh      # stoppar appen (insamlingen i bakgrunden lämnas orörd)
```

Avsluta även med Ctrl+C. Insamlingsstatus och start/stopp finns också i UI:t.

Eller manuellt i två terminaler:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload   # terminal 1
cd frontend && npm run dev                               # terminal 2
```

### Datainsamling (körs i bakgrunden via launchd)

Insamlingen är installerad som ett launchd-jobb och kör var 30:e minut **även
när appen är stängd** (hämtar Svenska Spel-odds + Pinnacle sharp, gratis):

```bash
# status / logg
launchctl list | grep svs
tail -f backend/data/snapshot.log

# stoppa / starta igen
launchctl unload ~/Library/LaunchAgents/com.saman.svs.snapshot.plist
launchctl load   ~/Library/LaunchAgents/com.saman.svs.snapshot.plist
```

Vill du köra en insamling ad hoc medan appen är öppen finns även knappen
**Datainsamling → Starta** i UI:t.

(Plist:en ligger i `backend/scripts/` om jobbet behöver installeras om.)

## Kom igång

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### CLI (snabbast)

```bash
cd backend
.venv/bin/python cli.py show           # analyserad omgång som tabell
.venv/bin/python cli.py spikar         # matcher rankade efter spik-score
.venv/bin/python cli.py snapshot       # spara ett snapshot i SQLite
.venv/bin/python cli.py history 4956 1 1   # oddshistorik: draw event sign
.venv/bin/python cli.py rad medel 100      # radförslag: strategi + budget
.venv/bin/python cli.py rad tuff 500 reducerat   # reducerat system
```

Lägg `snapshot` i cron/launchd (t.ex. var 30:e min onsdag–lördag) för att
bygga upp oddsrörelse-historik inför lördagens omgång.

### Webserver (API)

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload
```

| Endpoint | Beskrivning |
|---|---|
| `GET /api/draw` | Aktuell omgång, rådata |
| `GET /api/analysis` | Analyserad omgång (spik/värde/rörelse) |
| `GET /api/spikar` | Matcher sorterade efter spik-score |
| `GET /api/system?strategy=&budget=&reduced=` | Radförslag (matematiskt/reducerat) |
| `POST /api/snapshot` | Hämta + spara snapshot |
| `GET /api/history?draw=&event=&sign=` | Oddshistorik för ett utfall |
| `GET/POST /api/collector/status\|start\|stop` | Styr bakgrundsinsamlingen |
| `GET /api/external-odds?only_missing=` | Externa odds (the-odds-api), kräver nyckel |

### Sharp-odds: Pinnacle (primär, gratis) + the-odds-api (fallback)

Sharp-källan är **Pinnacle direkt** via deras publika "Arcadia"-API (samma som
pinnacle.se). Gratis, inget credit-system, och täcker även internationella
vänskapsmatcher som the-odds-api saknar. Två gratis-anrop hämtar hela soccer-
utbudet; matchning sker mot SS-matcherna (ISO/fuzzy + tidsfönster + båda
lagorienteringar med spegling av 1↔2). Knappen **Hämta sharp-odds (Pinnacle,
gratis)** i UI:t.

the-odds-api används bara om du kryssar i fallbacken (för matcher Pinnacle
saknar) och kostar då 1 credit per matchad match.

**Coverage-status** per match visas i UI:t: `matched` (1X2 hämtat), `no_moneyline`
(matchen finns men Pinnacle har bara öppnat spread/total — 1X2 kommer ofta
närmare avspark) eller `not_listed` (ej i Pinnacles utbud ännu). Insamlaren
uppdaterar Pinnacle gratis varje cykel, så 1X2 plockas upp automatiskt när de
öppnas.

### the-odds-api (fallback) — credit-snål

Lägg din nyckel i `backend/.env` (gitignorerad), laddas automatiskt:

```
ODDS_API_KEY=din_nyckel
```

**Två skilda datakällor med olika kostnad:**
- **Svenska Spel** = gratis. Insamlas ofta (collector-knappen / launchd).
- **Sharp (the-odds-api)** = kostar credits. **Manuell knapp** i UI:t, körs bara
  på klick. 500 credits i starter-paketet.

Credit-modellen (verifierad live): `/sports` och `/events` är **gratis**, så vi
matchar matcher mot ett fritt event-index och betalar **bara 1 credit per
matchad match** (en region). `only_missing=true` betalar bara för matcher där
Svenska Spel saknar odds. Lagmatchning: ISO-kod→engelskt namn (landslag) +
fuzzy (klubbar) + **tidsfönster** (±36h) för att stänga ute fel fixtures.
Bara matchningar över konfidenströskeln används.

Alla tar `?product=stryktipset` (även `europatipset`, `topptipset`).

## Signaler (så de tolkas)

- **Värdestreck (★)**: `fair% − streck% ≥ 6` — marknaden tror mer än folket.
- **Fallande odds (↓)**: oddset ned ≥ 4 % mot startodds — pengar flödar in.
- **Spik**: stark favorit (hög `fair_prob`), bonus vid fallande odds/brett folkstöd.
- **Sharp-värde (S)**: Pinnacle-sannolikhet − streck% ≥ 6 — sharp ser värde folket missat.
- **SS felprisat (▲/▽)**: sharp-sannolikhet vs SS-sannolikhet skiljer ≥ 6 pe.
  ▲ = SS-odds för höga (back-läge), ▽ = för låga. Sharp = sanningskälla.
- **Rörelse (⇊/⇈)**: odds vs *våra egna snapshots* (inte bara startodds).
  ⇊ = stärkts ≥ 5 % sedan vi började logga (stark signal, ger spik-bonus). Kräver
  att insamlingen kört ett tag. Sannolikhetsbas i analysen: SS-odds → sharp → streck.

Sharp-signalerna kräver att du först klickat **Hämta sharp-odds**; de cachas i
SQLite och vävs sedan in i analysen utan att kosta fler credits. `value_sharp`
används också när raden byggs (bästa värdetecken). Trösklar (`VALUE_MIN`,
`EDGE_MIN` m.fl.) ligger överst i `app/analysis.py` och är lätta att tweaka.

## Din kupong (klickbar)

Klicka 1/X/2 direkt i analystabellen för att bygga en kupong (flera tecken =
gardering). "Fyll från förslag" fyller utifrån senaste systemet eller
analysens speltyp. Live-beräkningar:

- **Rader & insats** (produkt av valda tecken × radpris).
- **Förväntat antal rätt** och **chans till alla rätt** (Poisson-binomial över
  fair-sannolikheterna).
- **Förväntad utdelning & EV** beräknad från **aktuell omsättning** och Svenska
  Spels **officiella vinstplan** (`/api/payouts`):
  - Stryktipset/Europatipset: 65 % återbetalning, fördelat 13:40 % · 12:15 % ·
    11:12 % · 10:25 %. Topptipset: 70 %, endast 8 rätt.
  - Prispott per nivå = omsättning × andel. Antal vinnare (och därmed kr/vinnare)
    uppskattas från **nuvarande streck** (Poisson-binomial per rad), så en
    favorit-rad som folket överspelar ger låg utdelning och en undervärderad rad
    hög — EV speglar verkligt värde.

EV är en uppskattning — verklig utdelning beror på slutlig omsättning och utfall
(ev. jackpot/garantifond ingår ej).

## System (radbyggaren)

Obs: de reducerade systemen är **egna** reduceringar (inte Svenska Spels
katalog-R-system). Villkoret som används visas alltid i utskriften.

- **Matematiskt** – alla kombinationer, dimensionerat mot budget.
- **Reducerat (värde)** – färgreducering: behåller rader med högst N avvikelser
  från favorittecknen (villkoret visas).
- **R-system (garanti)** – välj "minst 11/12 rätt"; bygger via covering ett
  reducerat system som *garanterar* den nivån om alla dina tecken är rätt.

## Nästa steg (ej byggt än)

- Spara/exportera valda rader (format för Svenska Spels systemkupong).
- U-system och fler garantinivåer.
```
