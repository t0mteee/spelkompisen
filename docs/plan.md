# Spelkompisen — färdplan

## STATUS (uppdatera löpande — läses först i varje ny session)

**2026-07-12 — Etapp 0 KLAR.** Repo klonat från svs, portar bytta (8002/5175/5181),
eget venv, DB seedad från svs (stryktips.db), titel/rubrik "Spelkompisen", Oddset-flik
med platshållarvy i menyn (verifierad i browser, desktop + mobil 375px). Inga launchd-jobb
laddade ännu. Prober körda — alla gröna, se "Prober" nedan; omtestning av "blockade"
källor gav genombrottet **Sofascore-xG i browser-kontext** (xG-risken struken).
App-URL från mobilen (Tailscale): `http://100.122.85.66:5175`.
**Nästa:** Etapp 1 (matchlista + odds) — id:n och vägar är redan verifierade.

## Beslut (Saman, 2026-07-12)

1. **Startpunkt:** kopia av svs som bas — poolspelen funkar dag 1, vm-moduler portas in.
2. **Datakällor:** enbart gratis. Undersök även återanvändbara öppna källor som Flashscore
   och ligornas officiella sajter. Rena betalspår (the-odds-api betald, API-Football) =
   framtida projekt.
3. **Framtid:** svs fryses (bara kritiska fixar) när spelkompisen nått paritet.
4. **Namn:** spelkompisen, katalog `/Users/saman/spelkompisen`.

## Mål

Behålla hela poolspels-analysen (Stryktipset/Europatipset/Topptipset/Bomben) och lägga
till en **Oddset-del**: enskilda matcher i tidsordning (visa/dölj ligor) med aktuella odds,
oddsrörelser, sharp-jämförelse och tips — 1X2, asian handicap, asian över/under, hörnor.
Start-ligor: **Allsvenskan, norska Eliteserien, träningsmatcher**. Tips kommer från två
håll: (a) snabba oddsrörelser där någon bok hänger efter (paradexempel: träningsmatch
där lineups läcker och sharpen rör sig före svenska böcker), (b) egen modell (styrkor,
xG-proxy, form, skador) — alltid med vm-lärdomen: modell utan sharp-ankare = amber-tier.

## Etapper

### Etapp 0 — Skelett ✅ (2026-07-12)
Klon, portar (backend 8002, frontend 5175, preview 5181), venv, DB-seed, namnbyte,
Oddset-flik (platshållare), detta dokument, CLAUDE.md omskriven.

### Etapp 1 — Matchlista + odds (nästa)
- Porta från vm: `pinnacle.py`-utökningarna (matchups + straight för AH/ÖU, inte bara
  moneyline), Kambi-klienten (operator `svenskaspel`, listView + betoffer per event),
  `odds_snapshot`-tabellen med dedup (skriv bara när odds/linje ändrats) och `movement()`.
- Ligaupptäckt Pinnacle: VERIFIERAT (prober nedan) — Allsvenskan 1728, Eliteserien 2333,
  Club Friendlies 1863 (+ 1864 dam). Bygg ändå en `LEAGUES`-tabell (id, namn, Kambi-väg,
  ESPN-slug) så fler ligor bara är en rad till.
- Kambi-vägar: VERIFIERAT — `listView/football/sweden/allsvenskan`,
  `.../norway/eliteserien`, `.../club_friendly_matches` (alla 200; `football/matches` finns EJ).
- Matchnyckel: klubblag, inte landslag → matchning på normaliserat lagnamn + avsparkstid
  (vm:s iso2-matchning funkar inte för klubbar; kolla `names.py`-mönstret + fuzzy).
- Backend: `oddset_matches`-tabell + `/api/oddset/matches` (tidsordnad, liga-filter),
  `/api/oddset/match/{id}` (odds + rörelseserie).
- UI: matchlista i tidsordning, visa/dölj ligor (sparas i localStorage), odds + rörelse
  (samma hover-punktserie-mekanik som analysvyn), flaggor/loggor där de finns.
- Launchd: `com.saman.spelkompisen.snapshot` (30 min; förtäta nära avspark som svs
  snapshot-smart). Saman kör `launchctl load` själv.

### Etapp 2 — Värde + steam + notiser
- Porta `value.py`-mönstret: power-devigad Pinnacle = fair; edge mot Svenska Spel (Kambi)
  per marknad. AH/ÖU jämförs ENDAST på samma linje.
- Steam i devigade procentenheter (6/24/72 h) per match/marknad; 🔥-flaggor i listan.
- ntfy-notiser: (a) sharp-edge ≥ tröskel, (b) snabb sharp-rörelse nära avspark —
  träningsmatch-caset: Pinnacle flyttar ≥X pp inom 30–60 min medan Kambi står still →
  notis medan det höga oddset lever. EGET NTFY_TOPIC (inte svs:s).
- CLV-logg från dag 1 (first/best, stängning = sista devigade Pinnacle före avspark) —
  bara sharp-ankrade flaggor får logga.

### Etapp 3 — Egen modell
- Datainsamling per liga: resultat, tabeller, form. Kandidater: ESPN (`swe.1`, `nor.1` —
  scoreboard + `/summary` med skott/hörnor/possession), football-data.co.uk (SWE.csv,
  NOR.csv — resultat + historiska odds, perfekt backtest-facit), ClubElo (klubbstyrkor,
  täcker nordiska ligor).
- ~~Undersök fler källor~~ GJORT 2026-07-12 (se Prober): **Sofascore = xG-källan**
  (Playwright-hämtare); Flashscore/FBref/FotMob/football-data.org skippas (detaljer i
  källtabellen); allsvenskan.se kvar som lågprio-spår.
- Modell: Dixon-Coles per liga (vm:s `model.py` som bas; rho refittas för klubbfotboll,
  vm fann −0.04 landslag vs litteraturens −0.13 klubbar), hemmafördel per liga,
  ClubElo som prior/korsreferens. **xG från Sofascore** som primär offensiv-/defensiv-
  styrkesignal; ESPN-skottdata som fallback-proxy.
- μ kalibreras mot devigad sharp ÖU-linje där Pinnacle finns (linje ≈ median, inte medel).
- Output: modell-tips som AMBER-tier (bakom toggle, UR CLV) tills backtest (Etapp 5)
  visar att de håller. Sharp-ankrade tips förblir enda gröna.
- Träningsmatcher: modellen får låg vikt (rotationsrisk) — där är steam/lineup-signalen
  (Etapp 2/4) huvudverktyget.

### Etapp 4 — Skador, lineups, nyheter
- Google News RSS per lag/match (vm-mönstret: sv+en, dedup, cap).
- X syndication-flödet (vm `twitter.py`): klubbkonton + relevanta journalister; 429-paca.
- Lineup-bevakning: källa oklar — undersök gratis-vägar (klubbarnas konton är mest
  realistiskt; strukturerade lineups utan betal-API är svårt). Kopplas till notiserna:
  "lineup-nyhet + sharp-rörelse + bok står still" är guldsignalen för träningsmatcher.
- Skador: nyhetsbaserat (fritext-flaggor per lag), inte strukturerad data (betalspår).

### Etapp 5 — Backtest + kalibrering
- football-data.co.uk SWE/NOR: modell mot historiska stängningsodds — samma beslutsregel-
  validering som svs backtest. Kalibrera trösklar (edge-%, steam-pp) innan de blir "gröna".
- CLV-uppföljning: håller flaggorna mot stängningslinjen? (Facit växer från Etapp 2.)
- Först härefter kan modell-tips ev. flyttas från amber till grönt, marknad för marknad.

### Senare / backlog
- Hörnor: Pinnacle hörn-specials (units='Corners', ~nära avspark) = sharp referens;
  vm-lärdomen: totalen är nästan konstant (~8.5–10.6), lag-hörnor följer favoritskapet
  (0.507 + 0.108·supremacy, R²≈0.97) — lag-hörnor är den intressanta marknaden.
- Fler ligor (Superettan? Damallsvenskan? danska Superligaen?) när flödet är bevisat.
- Polymarket som andra sharp-källa (tunn täckning klubbfotboll — låg prio).
- Menyn: gruppera flikarna (Poolspel: Stryk/Europa/Topp/Bomben | Oddset) om det blir trångt.
- Betalspår (framtida projekt): the-odds-api betald (multi-book), API-Football (skador/
  lineups/xG strukturerat).

## Datakällor (gratis) — status

| Källa | Vad | Status |
|---|---|---|
| Pinnacle Arcadia | sharp 1X2/AH/ÖU (+hörn-specials nära avspark) | ✅ verifierad 2026-07-12 (liga-id:n nedan); Cloudflare-block i perioder, IP-nivå |
| Kambi (operator svenskaspel) | Svenska Spels sportsbok, alla marknader, milliodds | ✅ verifierad 2026-07-12 — vägar nedan |
| ESPN | scoreboard/tabeller/matchstats (skott, hörnor) för swe.1/nor.1 | ✅ verifierad 2026-07-12 — 5 matcher/liga i svaret |
| football-data.co.uk | historiska resultat + odds SWE/NOR | ✅ verifierad 2026-07-12 — `new/SWE.csv`/`new/NOR.csv`, Pinnacle-stängning (PSC*) sedan 2012 |
| ClubElo | klubbstyrkor, gratis API | ✅ verifierad 2026-07-12 — `api.clubelo.com/Hammarby` ger full historik; vm har `elo.py` |
| Google News RSS | nyheter per lag | ✅ beprövad (vm) |
| X syndication | klubbkontons flöden | ✅ beprövad (vm), 429-känslig |
| **Sofascore (browser-kontext)** | **xG (!), hörnor, 43 statfält/match** för Allsvenskan & Eliteserien | ✅ verifierad 2026-07-12 — curl får 403 men riktig browser passerar; kräver Playwright-hämtare (mönster: `vm/tools/opta_token.py`). Detaljer under Prober. |
| Flashscore | live/odds/lineups (inofficiellt) | 🟡 feed-endpointen svarar (200 med `x-fsign: SW9D1eZo`) men formatet kräver reverse-engineering — nedprioriterad nu när Sofascore ger xG |
| allsvenskan.se / eliteserien.no | officiell statistik | 🟡 WordPress med wp-json — undersök vid behov, låg prio |
| FBref (browser-kontext) | tabeller/grundstats | 🟡 browser passerar Cloudflare (verifierat) men INGEN xG för Allsvenskan (22 tabeller kollade) — lågt värde, skippa |
| Blockerade (omtestade 2026-07-12 från hemma-IP, slösa inte tid) | FotMob (gamla API:t 404:ar — kräver signerad `x-mas`-header numera), football-data.org (Allsvenskan i katalogen men datat kräver betald tier), Opta-webben (Akamai) | ⛔ — men Opta performfeeds data-API var öppet (showcase-outlet, `vm/backend/app/opta.py`) |

## Kända risker

- ~~xG för Allsvenskan/Eliteserien saknar gratiskälla~~ **LÖST 2026-07-12**: Sofascore har
  xG för båda ligorna, åtkomlig i browser-kontext (se Prober) — kräver Playwright-hämtare,
  vilket är ett nytt beroende (browser i insamlingskedjan = skörare än ren httpx; ESPN-
  skottproxy kvarstår som fallback om Sofascore stänger).
- Pinnacles täckning av träningsmatcher varierar (stora klubbar ok, mindre = tunt eller
  bara nära avspark) — utan sharp-ankare blir de matcherna steam/nyhets-drivna, inte modell.
- Klubbnamnsmatchning (Pinnacle ↔ Kambi ↔ ESPN ↔ ClubElo) är mer jobb än landslags-iso2 —
  bygg en `team_alias`-tabell tidigt, den behövs i varje etapp.

## Prober (körda 2026-07-12 — Etapp 1 kan lita på dessa)

- **Pinnacle** `GET /0.1/sports/29/leagues?all=false` (guest-key): Allsvenskan = **1728**
  (6 matchups), Eliteserien = **2333** (5), Club Friendlies = **1863** (11),
  Club Friendlies Women = 1864. Matchups per liga: `/0.1/leagues/{id}/matchups`
  + `/0.1/sports/29/markets/straight` (vm-mönstret).
- **Kambi** (operator svenskaspel, `eu-offering-api.kambicdn.com/offering/v2018/svenskaspel`):
  `listView/football/sweden/allsvenskan.json` ✅ (9 events), `.../norway/eliteserien.json` ✅,
  `.../club_friendly_matches.json` ✅. `football/matches.json` = 404.
  Param: `?lang=sv_SE&market=SE`. Per match: `betoffer/event/{id}.json`.
- **ESPN**: `site.api.espn.com/apis/site/v2/sports/soccer/{swe.1|nor.1}/scoreboard` ✅
  (dagens omgång komplett, korrekta avsparkstider). Matchstats via `/summary?event=` (vm-mönstret).
- **football-data.co.uk**: `www.football-data.co.uk/new/{SWE|NOR}.csv` ✅ — kolumner
  PSCH/PSCD/PSCA (Pinnacle closing), Max/Avg, säsonger från 2012. Perfekt backtest-facit.
- **ClubElo**: `api.clubelo.com/{Klubbnamn}` ✅ (CSV, full historik; namnformat utan å/ä/ö
  — alias-tabellen behövs här också).
- **Sofascore** (omtestad från hemma-IP 81.234.x, Telia — vm:s 403-tester gick via VPN):
  `api.sofascore.com` ger 403 för curl ÄVEN från hemma-IP (bot-skydd på klientnivå), men
  **riktig browser passerar**: `www.sofascore.com/api/v1/...` ger ren JSON i browser-kontext.
  Verifierade id:n: Allsvenskan = unique-tournament **40** (säsong 2026 = **87925**),
  Eliteserien = **20**. Flöde: `/unique-tournament/{ut}/seasons` →
  `/unique-tournament/{ut}/season/{sid}/events/last/{page}` →
  `/event/{id}/statistics` — innehåller **"Expected goals"** (verifierat: Örgryte–Häcken
  4–3, 2026-07-11 → xG 1.48–1.78) + Corner kicks + 41 fält till.
  Implementeras som Playwright-hämtare i Etapp 3 (körs efter avslutad omgång, ~16 matcher/
  vecka totalt — snällt tempo, paca anropen).
- **FBref**: curl 403, browser passerar Cloudflare — men INGEN xG för Allsvenskan
  (alla 22 tabeller sakna xG-kolumner). Skippa.
- **FotMob**: gamla `/api/leagues` är borta (404, HTML tillbaka) — nutida API kräver
  signerad `x-mas`-header. Skippa (Sofascore täcker behovet).
- **Flashscore**: `d.flashscore.com/x/feed/...` svarar 200 med header `x-fsign: SW9D1eZo`
  — åtkomsten finns men feed-formatet är odokumenterat teckenprotokoll. Nedprioriterad.
- **football-data.org**: `/v4/competitions` listar Allsvenskan (188 ligor, utan token) men
  match-datat svarar "check your subscription" — gratis-tiern täcker inte våra ligor. Skippa.

## Portar & processer

| Projekt | Backend | Frontend | Preview | launchd |
|---|---|---|---|---|
| svs (fryses på sikt) | 8000 | 5173 | 5180 | com.saman.svs.snapshot (kör kvar, matar svs) |
| vm (Boll boll kollen) | 8001 | 5174 | — | com.saman.vm.* (5 jobb) |
| **spelkompisen** | **8002** | **5175** | **5181** | inga ännu → com.saman.spelkompisen.* i Etapp 1 |
