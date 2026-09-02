# Spelkompisen — färdplan

## STATUS (2026-09-02) — läs detta först i ny session

Det här blocket **ersätts** vid varje leverans — skriv över, stapla inte.
Tidigare statusblock ligger daterade och ordagranna i
`docs/status-historik.md`. Överlämningar: `docs/overlamningar/`. Aktiv
arbetslista: `docs/backlog.md` (avsnittet **Aktivt** överst).

**Drift.** Allt kör på MacBook-servern `192.168.50.100` (backend 8002, byggd
frontend 5175, launchd: snapshot/pool/kalltest + Chartervakt/Bonusvakt);
se `docs/macbook-server-2026-08-11.md` och `docs/AI-OVERLAMNING-SERVER.md`.
Kontroll före push: `tools/kontroll.sh` (837+ backendtester, eslint, 13
frontendtester, ~60 s) — pre-push-hooken i `tools/githooks/` kör den.
`backend/requirements.lock` är serverns frysta venv.

**Kontrakt som gäller nu.**
- **Live-radar** `chance-gap-shadow-v11` (Ligue 1 i scope sedan 2026-08-23;
  v10 från 2026-08-18 låser bästa färska överpris från Kambi/Ninja/Pinnacle,
  Pinnacle bara vid Age ≤ 90 s). Flashscore ankare, FotMob sekundär, Sofascore
  urkopplad ur radarn men kvar för resultatstatistik/frånvaro.
- **V2.2** samlar under manifest v10
  (`docs/model-v2.2-multileague-forward-manifest-v10.json`), sharp
  `s-2f14f9a6`; `/api/health` bevakar versionskontraktet. Aldrig tipsinput.
- **Modell** (amber, sämre än Pinnacle i alla ligor): modelldata v5,
  `powerrank-v2`. Modelligor: Allsvenskan/Superettan/Eliteserien/OBOS/MLS +
  PL/Serie A/La Liga/Bundesliga. Ligue 1 samlas (621/622 med xG) men står
  utanför `MODEL_LEAGUES` tills temperaturen kalibrerats.
- **Pool.** `pool-draw-risk-v1`: X skyddas ≥ 29,5 % vid Pinnacle-total ≤ 2,25
  (32 % utan total) i ALLA automatiska byggen. Matematiskt max v2 = 3 spikar +
  1 halv + 9 hela = 39 366 rader. PH3 gen 2, champion `b256-medel`,
  Topptipset-familjen tak 512. Radprofiler Standard/Träffsäkrare/Radform v1·test.
  Topptipset Dagens/Stryk/Extra är ETT spel i all redovisning (`family_of`).
  Spelade kuponger liverättas från tre 1X2-källor; glömda kuponger kan
  importeras ur radfil.

**Pågående mätningar — passiva. Läs på kadens, bygg inget nytt före skörd.**
V2.2-gaten · PH5 forward (5 000 rader; Stryk 4966→, Europa 2600→) ·
Max-tester `mathmax-v1`/`reducedmax-v1` (Stryk 4968/Europa 2603→) ·
`pool-strength-blend-v1` (Historik → Poolmodell) · radarens blindtest (200
matcher/60 dagar) · pooloptimerare v1 (nästa: färsk read-only-snapshot + full
10 000-sökning; `final_only` får nominera, aldrig promovera).

**Senast levererat.** 2026-09-02 (Claude): rött test rättat med
klockinjektion, `tools/kontroll.sh` + pre-push-hook + `requirements.lock`,
KAPPA-synklås backend↔frontend, den här dokumentstrukturen. 2026-08-31
(Codex): X-risk v1 + matematiskt max v2. Allt äldre: `docs/status-historik.md`.

## Modellplan — vägen till en modell att lita på (efter backtest-domen)

**Ersatt 2026-07-16 av den förregistrerade marknadsankrade v2-planen i
`docs/modell-v2-plan.md`. Punkterna M1–M5 nedan bevaras som historik.**

Backtesten visade: DC-modellen är nära marknaden i Allsvenskan men slår den inte,
och är svag i Eliteserien. Att slå Pinnacles STÄNGNING på 1X2 är fel mål — planen
är att vinna där marknaden är svag:

- **M1 — xG-viktad fit ✅ MÄTT (backtest v2, 2026-07-12)**: backfill klar
  (978 nya matcher; totalt ~574+390 med xG). Dom: **xG lyfter modellen i BÅDA
  ligorna** (logloss 1.029→1.022 Allsvenskan, 0.991→0.980 Eliteserien; bättre
  kalibrering). Allsvenskan blev t.o.m. lönsam vid låga trösklar: **+13,4 % ROI
  vid edge ≥2 % (n=326), +10,4 % vid ≥5 %** mot Pinnacle-stängning — MEN bara
  ~1,4σ från noll (snittodds ~4) = inom bruset, och ≥8 % vänder negativt
  (modellens största avvikelser är dess största fel). Eliteserien fortsatt
  giftig (−16..−20 %). rho-grid: −0.01/−0.04 bekräftad. Beslut: amber kvarstår,
  modell-loggtröskeln sänkt till 2 % (2–8 %-bandet är det intressanta) så
  forward-facitet (M3) byggs snabbare.
- **M2 — Elo-prior för tunna lag ✅ (2026-07-12)**: lag som saknas i fitten eller
  har <8 viktade matcher får styrkor ur ClubElo relativt liga-medlet
  (q = 10^(Δelo/400); att = q^0.35, def = q^−0.35; tunna lag blandas
  proportionellt). `_ensure_priors` i oddset_model; ⚠-not i M-radens tooltip
  (`model.prior`). Grov mappning — forward-loggen utvärderar även denna.
- **M3 — forward-test i produktion (IGÅNG)**: modell-flaggor loggas live
  (tier='model', aldrig notis/spel) och jämförs med Pinnacle-stängningen.
  **Grönt-kriteriet per liga: ≥50 stängda modell-flaggor med positivt snitt
  close-EV.** Facitet avgör — inte känsla, inte backtest ensam.
- **M4 — marknader där böcker är slöa**: modellens realistiska nisch är inte
  Pinnacles 1X2 utan (a) tidiga linjer innan sharpen öppnat (redan synligt:
  modell + Elo finns för nästa omgång före Pinnacle), (b) hörnor/lagmål där
  vi har egen Sofascore-data, (c) mindre ligor. **Superettan TILLAGD som liga
  (2026-07-12)**: Pinnacle 2476 + Kambi `football/sweden/superettan` + Altenar
  4825 + Sofascore ut 46 (MED xG!); ingen football-data → Sofascore är
  resultatkälla (MODEL_LEAGUES-gaten). Egen flik, full värdemotor + modell.
- **M5 — blend som referens**: backtesten fann w=0.1 modell + 0.9 marknad ≥
  marknaden ensam i Allsvenskan — modellen bär EN nypa egen information.
  När M1–M2 höjt den kan blenden bli "husets fair" för matcher med tunn sharp.

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

### Etapp 1 — Matchlista + odds ✅ (2026-07-12)
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

### Etapp 2 — Värde + steam + notiser ✅ (2026-07-12)
- Porta `value.py`-mönstret: power-devigad Pinnacle = fair; edge mot Svenska Spel (Kambi)
  per marknad. AH/ÖU jämförs ENDAST på samma linje.
- Steam i devigade procentenheter (6/24/72 h) per match/marknad; 🔥-flaggor i listan.
- ntfy-notiser: (a) sharp-edge ≥ tröskel, (b) snabb sharp-rörelse nära avspark —
  träningsmatch-caset: Pinnacle flyttar ≥X pp inom 30–60 min medan Kambi står still →
  notis medan det höga oddset lever. EGET NTFY_TOPIC (inte svs:s).
- CLV-logg från dag 1 (first/best, stängning = sista devigade Pinnacle före avspark) —
  bara sharp-ankrade flaggor får logga.

### Etapp 3 — Egen modell ✅ (2026-07-12)
- Datainsamling per liga: resultat, tabeller, form. Kandidater: ESPN (`swe.1`, `nor.1` —
  scoreboard + `/summary` med skott/hörnor/possession), football-data.co.uk (SWE.csv,
  NOR.csv — resultat + historiska odds, perfekt backtest-facit), ClubElo (klubbstyrkor,
  täcker nordiska ligor).
- ~~Undersök fler källor~~ GJORT 2026-07-12 (se Prober): Sofascore valdes då
  som ensam xG-källa. **Det beslutet är historiskt:** FotMob kopplades in
  2026-07-25 och Flashscore 2026-08-01; modelldata v4 lagrar providers
  parallellt. FBref/football-data.org är fortsatt avförda.
- Modell: xG-viktad Poisson-styrkefit per liga med DC-korrektion i prediktionen
  (vm:s `model.py` som bas; rho refittas för klubbfotboll,
  vm fann −0.04 landslag vs litteraturens −0.13 klubbar), hemmafördel per liga,
  ClubElo som prior/korsreferens. Ursprungligen kom xG bara från Sofascore;
  aktuellt v4-kontrakt väljer ett komplett providerpar enligt fryst prioritet
  och redovisar proveniensen. ESPN-skottdata är fallback-proxy.
- μ kalibreras mot devigad sharp ÖU-linje där Pinnacle finns (linje ≈ median, inte medel).
- Output: modell-tips som AMBER-tier (bakom toggle, UR CLV) tills backtest (Etapp 5)
  visar att de håller. Sharp-ankrade tips förblir enda gröna.
- Träningsmatcher: modellen får låg vikt (rotationsrisk) — där är steam/lineup-signalen
  (Etapp 2/4) huvudverktyget.

### Etapp 4 — Skador, lineups, nyheter ⛔ SKIPPAD (beslut 2026-07-12: steam täcker caset)
- Google News RSS per lag/match (vm-mönstret: sv+en, dedup, cap).
- X syndication-flödet (vm `twitter.py`): klubbkonton + relevanta journalister; 429-paca.
- Lineup-bevakning: källa oklar — undersök gratis-vägar (klubbarnas konton är mest
  realistiskt; strukturerade lineups utan betal-API är svårt). Kopplas till notiserna:
  "lineup-nyhet + sharp-rörelse + bok står still" är guldsignalen för träningsmatcher.
- Skador: nyhetsbaserat (fritext-flaggor per lag), inte strukturerad data (betalspår).

### Etapp 5 — Backtest + kalibrering ✅ (2026-07-12 — resultat i STATUS-blocket)
- football-data.co.uk SWE/NOR: modell mot historiska stängningsodds — samma beslutsregel-
  validering som svs backtest. Kalibrera trösklar (edge-%, steam-pp) innan de blir "gröna".
- CLV-uppföljning: håller flaggorna mot stängningslinjen? (Facit växer från Etapp 2.)
- Först härefter kan modell-tips ev. flyttas från amber till grönt, marknad för marknad.

### Senare / backlog

- ~~Cross-liga-fit~~ ✅ KLAR (2026-07-12): fit_league tar nu rader från flera
  ligor — lagstyrkor delas, base + hemmafördel per liga (FIT_POOLS: Allsvenskan
  + Superettan = Sverige-pool; Eliteserien egen). Backtest v3 (xG + pool,
  Allsvenskan): samma precision (logloss 1.0216 vs 1.0217) men **+8 matcher
  täckta** = nyuppflyttades matcher som tidigare saknade prediktion. Behållen.
- **Hörn-förväntan (M4b)** ✅ (2026-07-12): `corner_model` per liga ur egen
  Sofascore-data (~1400 matcher med hörnor): liga-snitt-total + hemmaandel ~
  xG-supremacy (OLS). Visas som M-rad i Hörnor-kolumnen (modell-toggle).
  ENDAST förväntan — inga pills/logg (vm-lärdomen: hörn-värde kräver sharp linje).
  OBS: ClubElo täcker bara ~7/23 Superettan-lag, så M2-priorn når inte alla där.
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
| **Sofascore (browser-TLS)** | xG/hörnor/resultat/frånvaro + livechansdata | ✅ i drift via `curl_cffi`; egen livecapture, presence och source-health. Modelldata samlas parallellt med Flashscore; resultat-only-ligor använder normaltidsresultat. OBS: live-xG saknas ofta i Allsvenskan. |
| **FotMob** | live-xG/xGOT/open-play-xG/skott | ✅ i drift med `fotmob-live-v2`; egen tabell/presence/health, koherent ställning+stats och fristående kort vid unik identitet. Ingen providerblandning. |
| **Flashscore** | live-xG/xGOT/skott/stora chanser/hörnor + avslutad xG/hörnor/frånvaro | ✅ i drift med publik pipe-feed/persisted query inom källgränsen; `flashscore-live-v2`, egen tabell/presence/health och parallella providerobservationer i modelldata v4. Ingen säsongsbakfyllning. |
| allsvenskan.se / eliteserien.no | officiell statistik | 🟡 WordPress med wp-json — undersök vid behov, låg prio |
| FBref (browser-kontext) | tabeller/grundstats | 🟡 browser passerar Cloudflare (verifierat) men INGEN xG för Allsvenskan (22 tabeller kollade) — lågt värde, skippa |
| Blockerade (omtestade 2026-07-12; FotMob senare LÖST, se egen rad) | football-data.org (Allsvenskan i katalogen men datat kräver betald tier), Opta-webben (Akamai; gratisvägen = renderade bilder, feeds kräver betald outlet-nyckel — omkollat 2026-07-25) | ⛔ |
| ASA (American Soccer Analysis) | MLS: xG/xPass/Goals Added/löner/domare/arenor — oberoende MLS-kvalitetskontroll | 🔴 certfel 2026-07-13 (hostname mismatch, både httpx & Chrome-TLS) — verifiera åtkomst innan planering (WP9a). Blanda aldrig providers' xG i samma fält. |
| Sofascore shotmap | shot-xG + xGOT per skott | ✅ probat 2026-07-13: Eliteserien 30/30 skott med xG — Allsvenskan 0/31 (fältet saknas för SWE). Coverage-matrix (WP9b) innan features byggs. |
| Sofascore team-events | lagets ALLA tävlingar (cup/Europa) | ✅ WP9c i drift 2026-07-17: 94 lag, 3 329 unika event, PIT-first-seen, vila/belastning + basarena-reseproxy; ännu inte modellinput |
| Open-Meteo Historical Forecast | väder med äkta point-in-time-prognoser | 🟡 dokumenterat gratis-API; liten väntad effekt → P2 |
| Betfair Historical | exchange-stängningar | ⛔ skip tills konkret behov — kontokrav, marginell nytta över Pinnacle-close för våra ligor |

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
- **FotMob, historisk rekognosering:** gamla `/api/leagues` var borta (404),
  men slutsatsen att källan skulle skippas upphävdes 2026-07-25. Den nutida
  publika vägen används i `app/fotmob.py`; aktuellt capturekontrakt är v2.
- **Flashscore**: `d.flashscore.com/x/feed/...` svarar 200 med header `x-fsign: SW9D1eZo`
  — åtkomsten finns och feed-formatet är odokumenterat teckenprotokoll. Det
  parseras nu i `app/flashscore.py`/`flashscore_data.py` med fail-closed-
  koherensvakter; källan är i drift sedan 2026-08-01.
- **football-data.org**: `/v4/competitions` listar Allsvenskan (188 ligor, utan token) men
  match-datat svarar "check your subscription" — gratis-tiern täcker inte våra ligor. Skippa.

## Portar & processer

| Projekt | Backend | Frontend | Preview | launchd |
|---|---|---|---|---|
| svs (FRYST ARKIV 2026-07-20) | 8000 | 5173 | 5180 | urlastat (servrar stoppade, DB kvar) |
| vm (Boll boll kollen) | 8001 | 5174 | — | com.saman.vm.* (5 jobb) |
| **spelkompisen** | **8002** | **5175** | **5181** | com.saman.spelkompisen.{snapshot,pool,backend} |
