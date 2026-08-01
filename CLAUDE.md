# Spelkompisen

Personligt lokalt verktyg som kombinerar **SvS kompisen** (poolspels-analys: Stryktipset,
Europatipset, Topptipset, Bomben) med en ny **Oddset-del**: enskilda matcher (Allsvenskan,
norska Eliteserien, träningsmatcher till att börja med) med sharp-odds, oddsrörelser,
egen modell och värdespels-tips (1X2, asian handicap, över/under, hörnor på sikt).

**Läge (2026-07-25):** Etapp 0–5 KLARA + långt därutöver. Oddset-delen är i full drift:
10 ligor (Allsvenskan/Superettan/Eliteserien/OBOS/Besta deild/MLS/träningsmatcher + CL/EL/
Conference INKL. kval — cuperna är två Pinnacle-ligor + två Kambi-vägar per nyckel,
`pin_ids`/`kambi_paths` i oddset.py), 4 bokkällor +
Pinnacle, kvalitetsviktade värdesignaler, steam-radar, xG-viktad Poisson-modell med
DC-korrektion (amber, settlement-ankrad efter T — kalla den inte DC-MLE), frånvarodata, CLV-facit
per tier med grönt-kriterium v2 (≥50 stängda OCH undre bootstrap-KI-gräns > 0, per
liga/marknad/modellversion). **STATUS-SAMMANFATTNINGEN överst i `docs/plan.md` är
sanningen — LÄS DEN FÖRST i ny session** (+ WP-backloggen där, prioriterad; gransknings-
evidens i `docs/granskning-2026-07-13.md`).
Prediction-ledgern har dessutom en förregistrerad modell-mot-Pinnacle-close-grind
för alla frysta modellvektorer; äldre 1X2-version är fälld som sämre än sharp.
Matchvyn visar modell/Pinnacle/SvS i procent och pp på exakt samma lina.
Hörnens Poisson-baslinje samlar framåt under egen marknadsversion; historiska
hörnpriser får aldrig bakfyllas med dagens modell. Se
`docs/modell-mot-close-2026-07-25.md`.
Ninja/Altenar visas under `+ Fler odds` för 1X2, Ö/U och hörnor och får vara
spelbar mjuk bok i sharp-värdemotorn. UI får bara säga `bekräftat kvar` när
det oförändrade bokpriset återobserverats efter Pinnacles senaste prisändring;
vanlig färskhet eller ett gammalt cachepris räcker inte.
Den underkända V2.1 är fortsatt vilande. Ett separat V2.2-experiment samlar
Allsvenskan + research-only Premier League/Serie A/La Liga/Bundesliga med WP9c
i isolerad sharp-identitetskontroll; se
`docs/model-v2.2-multileague-forward-manifest.json`. Det är inte en tränad
modell och får inte påverka tips, notiser eller CLV.
**Aktuell överlämning:**
`docs/overlamning-2026-07-31-live-signaljournal.md` (LÄS FÖRST).
Föregående: `docs/overlamning-2026-07-25-kvall.md`.
Beställning 1 är LEVERERAD 2026-07-24: de fyra Europaligorna syns i ordinarie
Oddset-vyn (🔬 forskningsmärkta, `visible_in_ui`) men är fortsatt icke-
actionable — `VISIBLE_LEAGUE_KEYS` ≠ `ACTIONABLE_LEAGUE_KEYS` i `oddset.py`.
Poolspår PH1–PH4 finns nu: historiskt settlement, framåtriktad presence-ledger
och CDN-ålderskorrigerad `pit-v3`, kontrafaktiskt systemfacit samt fryst
forward-gate. Det samlar
data utan bakfyllning och påverkar ännu inte runtimeförslag. Nästa steg är att
auditera de första riktiga v3-horisonterna, systemfrysningarna och settlementen;
se `docs/pool-pit-v3-2026-07-25.md`.

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
  app/altenar.py      Ninja Casino/Altenar: publik listvy för 1X2 + mål och
                      eventdetalj för huvudlinan totalt antal hörnor. Detaljen
                      hämtas bara i deep-/snabbfönstret; alternativa hörnlinor
                      finns i källan men lagras inte i book-lagret ännu
  app/betsson.py      Publik Betsson-bootstrap/headerkontext (ej inkopplad källa;
                      eventtabellen CloudFront-blockerad utanför browser —
                      omverifierat 2026-07-25: context-details 200, events-table 403.
                      KRÄVER brotli i venv, se transportregeln nedan)
  app/analysis.py     fair_prob (power-metod), värde, taggar, speltyp, mover-flagga
  app/builder.py      radbyggare: matematiskt/reducerat/garanti/SvS R-system/EV-topp
  app/bomben.py       Poisson-målmodell för Bomben
  app/storage.py      SQLite (data/stryktips.db): snapshots, sharp_snapshots, dedup, movement
  app/oddset_v22.py   isolerad V2.2 feature-/shadowcapture (ej live-tips)
  app/pool_settlement.py PH1: immutable poolfacit (append-once, payload-hash;
                      backfill/migration i scripts/, läs-API /api/pool/history)
  app/pool_dataset.py PH2: PIT-features per omgång/horisont (pit-v3, enbart
                      observed_pit — no backfill) + separat presence-ledger
                      och proveniensmärkt pool_draw_snapshot-serie
  app/pool_played.py  SPELADE kuponger: 🎟-knappen bokför att SAMAN själv lämnat
                      in kupongen (lägger inga spel). FACIT = settlementlagrets
                      officiella `outcome` per eventNumber (samma kanon som PH3;
                      struken match = SvS fastställda tecken, aldrig "rätt för
                      alla") mot PUBLICERAD utdelning — kupongen låg i potten,
                      så beloppen inkluderar den; utspädningen i PH3 gäller
                      kontrafaktiska system och får ALDRIG återanvändas här.
                      LIVESTATUS (aldrig facit) ur SvS draw-payload
                      (`match.result` "Current" + `statusId`), tecken parade
                      via `events_order`, så en oavgjord/struken match håller
                      alla tecken öppna
  app/pool_system_ledger.py PH3: förregistrerade benchmarksystem fryses
                      T−3h/T−20m i varvet, settlas kontrafaktiskt med egen
                      vinnarutspädning; rollover utan vinnare = okänd ROI
                      (/api/pool/systems; champion = dagens byggare)
  app/live_radar.py  shadow-radar för pågående matcher: observerad xG,
                      stora chanser/skott/boxtryck; råa femminuterscaptures,
                      aldrig automatiska spel eller runtime-modellinput
  app/live_signal_ledger.py framåtriktad append-only-journal över den första
                      synliga Följer/Stark-nivån per match × signaltyp:
                      minut/ställning/mått + observerad öppen Kambi-live-Ö/U,
                      normaltidsfacit och Asian-Över-ROI. Aldrig tipsinput
  app/flashscore.py   PRIMÄRA live-ögat (Samans beslut 2026-08-01, mätt samma
                      dag: xG där FotMob bara hade skott eller ingenting,
                      aldrig sämre). Publik pipe-feed, statisk publik
                      headerkonstant (samma klass som Pinnacles gästnyckel);
                      brotli KRÄVS. Minuten HÄRLEDS ur stadiets starttid
                      (AC 12/13 + AO) — okänt stadium ⇒ None, aldrig gissad.
  app/flashscore_data.py Flashscore som MODELLDATAKÄLLA (2026-08-01): fyller
                      SAKNAD xG på nyss avgjorda matcher och hämtar
                      frånvarande spelare (publik persisted query, hash i
                      flashscore.py). Två hårda regler: (1) INGEN bakfyllning
                      — bara dagsfeeds ~5 dygn bakåt, aldrig säsongsfeeds;
                      (2) en befintlig xG skrivs ALDRIG över (`oddset_fill_xg`
                      har `xg_h IS NULL` i SQL:en), källan märks `+fs` och
                      frånvarocaptures får `source_event_id='fs:<id>'` så
                      proveniensen syns i efterhand. Lagmatchning är strängare
                      än live-radarns: norm_team + svensk genitiv + strippat
                      landssuffix ('Chelsea (Eng)'), tvetydighet länkar aldrig.
  app/fotmob.py       ANDRA live-ögat (var primärt 2026-07-28→08-01):
                      live-xG/xGOT/skott, täcker även Oddset-spärrade
                      friendlies. Sofascore är tredje källa.
                      ALLA TRE: EGEN tabell; providrar blandas ALDRIG.
                      Källval rankar DATAKVALITET först (xG > skott/chansmått
                      > no_stats) och vid lika vinner Flashscore, sedan
                      FotMob — en match där FotMob har xG och Flashscore bara
                      skott nedgraderas alltså aldrig. HELA signalen/deltat
                      kommer från vald serie. `signal.stats_source` säger
                      vilken; `coverage.by_source` redovisar fördelningen.
                      Shadow.
  app/main.py         API-endpoints + PRIZE_PLANS (officiella vinstplaner)
  cli.py              show|spikar|snapshot|history|rad (snapshotvarvet settlar
                      även nyss avgjorda poolomgångar via settle_recent)
frontend/ React + Vite, mörkt tema. src/AppV3.jsx + AppV3.css är APPEN
  (enda gränssnittet sedan 2026-07-26 — klassiska v2-vyn är RIVEN): vyerna
  Idag, Poolspel, Oddset, Historik och 🧪 Labb (bevisytan: alla mät-/
  shadowspår som statuskort — inget där är tips). src/App.jsx + App.css är
  KOMPONENTBIBLIOTEKET (AnalysisTable, SystemView, CouponPanel, OddsetView,
  PlayRec, PlayedPanel m.fl. via exportblocket i slutet) — nya tunga
  komponenter definieras där och monteras i AppV3. Tillstånd (kupong/omgång/
  inställningar) ligger i localStorage `svs_state`. Oddset är uppdelat i
  Matcher/Live/Värdespel/Rörelser; desktop använder delade `SortableTable`,
  mobil samma sortering över kort. Signalgruppsfacit och signallogg hör
  hemma i Labb, aldrig som en femte Oddset-sektion.
start.sh / stop.sh    kör/stoppa båda lokalt (8002 + 5175)
docs/plan.md          FÄRDPLANEN: status, datakällor, beslut — projektets sanning
docs/backlog.md       AKTIV BACKLOG (2026-07-26): prioritering, pågående mätningar,
                      parkerat/avfört — ändra prioritet bara med Samans godkännande
docs/forbattringar.md ARKIV: svs-ärvda lärdomar + bokkälls-kartläggning (referens)
```

## Kommandon

- Starta allt: `./start.sh` (backend :8002, frontend :5175). Stoppa: `./stop.sh`.
- Tester: `cd backend && .venv/bin/python -B -m unittest discover -s tests -v`.
- V2.2-status: `cd backend && .venv/bin/python -B cli.py v22audit`.
- Live-radar manuellt prov: `cd backend && .venv/bin/python -B cli.py live-tick`
  (shadowdata; påverkar inga tips/notiser). Varvet sparar även nya
  beslutssignaler och settlar avslutade signaler append-once.
- **Backend har INGEN auto-reload** — efter ändring:
  `lsof -ti:8002 -sTCP:LISTEN | xargs kill -9; cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 &`
- ALDRIG `pkill -f uvicorn` (dödar svs 8000 och vm 8001 — samma kommando).
  ALDRIG `lsof -ti:<port>` utan `-sTCP:LISTEN` (dödar annars webbläsare med öppna sockets).
- Frontend nås via Tailscale/LAN (vite.config: `host:true, allowedHosts:true`).
- Verifiering i browser: preview-servern `frontend-preview` (port 5181) i `.claude/launch.json`.
- **Insamling: två launchd-jobb är LADDade.**
  `com.saman.spelkompisen.snapshot` kör Oddsets fullvarv på fasta :00/:30
  (alla källor + Kambi-deep + modelldata) och därefter snabbvarv var 4:e min så länge någon
  match startar inom 3 h (Pinnacle + böckernas 1X2 + SvS-deep för 3h-matcherna;
  `FAST_WITHIN_H` i oddset.py), inom ~25 min budget.
  `com.saman.spelkompisen.pool` kör ett separat kort varv var 5:e min:
  `pool-tick` gör basinsamling var 30:e min och varje tick när ett poolspel
  stänger inom 2 h; därefter samlar `live-tick` observerad live-xG/chansdata.
  **`live-tick` förtätar sig själv** (två varv, 0 s och 120 s, budget 180 s —
  `LIVE_DENSE_BUDGET_S`/`_INTERVAL_S` i cli.py), så radarn uppdateras varannan
  minut utan ändrat launchd-intervall, och den slutar direkt när ingen livematch
  har chansdata. Budgeten är räknad mot att `pool-tick` kan ta upp mot en minut
  före radarn — ändra den inte utan att räkna om marginalen till nästa tick.
  **Förtäta ALDRIG poolvarvet eller Oddset-varvet på samma sätt:** Pinnacles
  bulk är CDN-cachad `max-age=905`, så anrop oftare än ~15 min returnerar samma
  objekt — det kostar trafik utan en enda ny prispunkt. Radarns källor är
  däremot färska (FotMob `max-age=10`, Sofascore live, Flashscore `Age` ~3 s).
  Flashscores dagsfeed är 173 kB på tråden (1,4 MB avkodad) — en begäran per
  varv, så den hämtas färsk varje gång i stället för att cachas med en
  inaktuell ställning som följd.
  En färsk match med chansdata ska visas även om de andra källorna saknar
  den; `fotmob:<id>` respektive `flashscore:<id>` är då kortets namespacade
  event-id. Gör aldrig livevisningen beroende av att en källa först kan
  länkas till en Sofascore-rad.
  Live-radarn är shadow/informationsstöd och får inte påverka tips, Kelly,
  CLV, pushnotiser eller systemförslag utan ett nytt explicit beslut.
  Signaljournalens blindkohort är FÖRSTA aktiva signalen per match (en
  Följer→Stark-eskalering får finnas i diagnostiken men får inte dubblera
  blindtestet). Minst 200 oddssatta+avgjorda signalmatcher, minst 60 dagar och
  undre KI90 > 0 krävs före stöd; inga historiska liveodds bakfylls.
  **Signalversionen är `chance-gap-shadow-v3`** sedan 2026-08-01: trösklarna
  är oförändrade, men Flashscore ändrar VILKA matcher som kan ge signal —
  alltså kohortens datagenererande process. v2:s två rader ligger kvar som
  historik och blandas aldrig med v3. En ny statistikkälla kräver alltid
  samma versionsbump.
  Provider-id hanteras som ogenomskinlig STRÄNG i presence, journal och
  settlement (Flashscores är alfanumeriskt: `SKg88Q3T`).
  Notiser går i Oddset-varvet, bakom **notisvakten** (presence-set: larm kräver att
  priset observerades i det aktuella lyckade varvet).
- **WP2-prisregel:** `fetched_at` = prisförändring, `last_seen_at` = senaste
  lyckade bekräftelse. Värde/modell/steam/facit kräver `available` och högst
  45 min gammal bekräftelse. Pinnacles HTTP `Age` dras av före båda
  tidsstämplarna; cacheobjekt äldre än 5 min öppnar inte notisgrinden.
  Källfel får aldrig markera ett pris unavailable.

### 🕐 OBSERVATIONSTIDSREGELN — läs innan du skriver en ny insamlare

Samma bugg har uppstått TRE gånger på tre dygn (pit-v1, Pinnacle-klienten,
live-radarn). Den ser olika ut men är alltid samma sak: **något annat än
observationsögonblicket används som observationstid.**

1. **Förändringstid ≠ observationstid.** `snapshots`/`sharp_snapshots` skriver
   bara vid förändring. Ett oförändrat pris är fortfarande observerat — bara
   `pool_market_capture` (presence-ledgern) får bevisa att en källa lästes.
2. **Hämtningstid ≠ pristid.** CDN-cachade svar kan vara minuter gamla. Dra av
   HTTP `Age`. Pinnacles bulk kör `max-age=905`.
3. **Loopstart ≠ per-post-tid.** Sätt tidsstämpeln EFTER varje anrop, aldrig
   en gång per varv. En ligaloop kan pågå 25 min; ett radarvarv 90 s.
4. **Klockan får bara gå framåt.** `last_seen_at` uppdateras med
   `MAX(last_seen_at, ?)`. Ett svar som är äldre än vår senaste bekräftelse
   bär ingen ny information — hoppa över det, skriv det aldrig bakåtdaterat
   (rad före tidigare observation) eller med nutid (lögn om färskhet).
5. **Transporthälsa använder riktig hämtningstid** — den mäter källan, inte
   priset.
6. **En källa vi inte frågade är ingen observation.** Dubbeltrafikspärren
   returnerar tomma `hits`/`status` UTAN fel; `status.get(event, "not_listed")`
   gjorde då "vi frågade inte" till "Pinnacle listar inte matchen" — 52 % av
   poolens sharp-ticks blev falska frånvaroobservationer på ett dygn (0 % dagen
   före). Spärren får förbigås bara i ett öppet horisontfönster
   (`pool_dataset.horizon_window_open`), eftersom en horisont observeras en enda
   gång och aldrig får bakfyllas. Se `docs/m20-och-falsk-franvaro-2026-07-25.md`.

### 📦 TRANSPORTREGELN — status 200 betyder inte läsbar kropp

`brotli` MÅSTE finnas i venv:et (`requirements.txt`). CloudFront svarar
`content-encoding: br` även på `Accept-Encoding: gzip`, och httpx avkodar br
bara om paketet är installerat — annars kommer kroppen tillbaka som binärt
skräp med status 200. Betsson-bootstrapen dog i drift 2026-07-25 med "saknar
sportsbookBrandId" på en fullt fungerande sida, medan de fixturbaserade
testerna var gröna. **En parse som misslyckas på 200 är ett transportfel
tills motsatsen är bevisad** — kontrollera `content-encoding` innan du drar
slutsatsen att sidan ändrats eller källan blockerar.

### 🎯 ANKARE ≠ BOK

`BOOKS` i oddset.py styr INSAMLINGEN. `oddset_value.ANCHOR_SOURCES` styr
VÄRDERINGEN. Båda behövs: `attach_value` byggde tidigare sin boklista som
"allt utom pinnacle", så Smarkets blev automatiskt en bok att hitta värde hos
trots att den låg utanför `BOOKS` — 192 felaktiga flaggor innan det upptäcktes.
Lägger du till en sharp-referens (börs, andra sharp-böcker) MÅSTE den in i
`ANCHOR_SOURCES`, annars förorenar den CLV-facitet. Spärren är låst av
`tests/test_oddset_value.py::AnchorSourceTests` sedan 2026-07-25.

Andra ankaret (`ANCHOR2_SOURCE`, i dag Smarkets) MÄTS i skugga på varje flagga
(`anchor2_*` i `oddset_value_log`, ⚓-raden i Signal-loggen) men får ALDRIG
påverka urval, edge, q eller notiser: en selektionsändring byter
`signal_version` och nollställer facitgruppen. Promotion till gate sker bara
enligt den förregistrerade regeln i `docs/tva-ankare-2026-07-25.md`.
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
- Vinstplaner OMMÄTTA 2026-07-24 mot settlementlagret (150 omgångar/produkt):
  **Stryktipset** 40/15/12/25, **Europatipset har EGEN plan** 39/**22**/12/25 —
  den gamla koden kopierade Stryktipsets och underskattade Europas 12-rättspott
  med 47 %. Splitsen summerar till < 1 (Stryk 0,92, Europa 0,98); resten går
  till jackpotfonder. Använd `_payout_ratio()` (= ratio × Σsplits) för allt som
  visas som återbetalning: Stryk **59,8 %**, Europa **63,7 %**, Topptipset 70 %.
  Break-even mot fältet är därmed +67 % (Stryk), inte +54 %. `/api/payouts`
  svarar med `payout_ratio`, `hurdle`, `product` och `guarantees`.
- **Garantier** (`guaranteedJackpots`, t.ex. ensamvinnargaranti 10 Mkr) läses av
  `get_guarantees()` och visas i UI men går ALDRIG in i EV — villkoren är inte
  verifierade mot SvS regler. `get_jackpot()` summerar bara rullpotten.
- **Strukna matcher räknas normalt** (uppmätt: mest streckade tecknet vinner
  52,8 % i 593 strukna mot 52,1 % i 75 514 ostrukna; inga extra toppvinnare per
  omsatt krona). Tvinga aldrig helgardering på dem — det tredubblar kostnaden.
  Topptipset 70 %, bara 8 rätt delar potten. Finns i `PRIZE_PLANS` i main.py.

### Pinnacle (sharp-odds, gratis)

- `https://guest.api.arcadia.pinnacle.com/0.1`, header `X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R`,
  soccer = sport 29. `/sports/29/matchups` + `/sports/29/markets/straight` (moneyline period 0).
  Amerikanska odds → decimal. Matchning via ISO/pycountry + fuzzy + tidsfönster + spegling 1↔2.
- Saknas moneyline härleds 1X2 ur spread/total (derive.py) — märks `P~` i UI.
- **CDN-CACHE (uppmätt 2026-07-24):** bulk-endpointerna svarar
  `cache-control: public, max-age=905` och objektet är ofta redan flera minuter
  gammalt (observerat `age` 469–539 s). **Hämtningstid ≠ pristid** — samma
  klass av fel som pit-v1:s förändringstid ≠ observationstid. `Pinnacle`
  exponerar `last_age_s`; sedan 2026-07-25 drar både Oddset-färskhet och
  poolens PIT-capture av den. Liveverifiering: hämtning 23:15:31,
  `Age=338` ⇒ observation 23:09:53. Kadenskonsekvens: snabbvarv
  oftare än ~15 min ger SAMMA objekt igen. Per-matchup-endpointen
  (`/matchups/{id}/markets/straight`) är däremot liten (8 kB) och är den enda
  som ger LIVE-priser — `/markets/related/straight` returnerar tyst FRYSTA
  prematch-marknader (lätt fälla).
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
  kvoter. **PH4-analysen 2026-07-24 (`docs/ph4-analys-2026-07-24.md`,
  7 754 omgångar) mätte κ>1 överallt** (4–29 %; U-formad folkkorrelation =
  fetare svansar; favoriter överstreckade). Sedan 2026-07-24 är κ per produkt
  och nivå INKOPPLAD i radvalet: `builder.KAPPA` + `KAPPA` i App.jsx måste
  hållas identiska. Sedan 2026-07-28 även i PORTFÖLJSIMULERINGEN
  (`pool_mc kappa_by_tier` via /api/system) — alla tre värderingsvägarna
  ska berätta samma sanning. κ>1 sänker EV — korrektionen kan aldrig blåsa
  upp förväntningar, och PH3-ledgern mäter nu champion MED κ.
- **Streck-golv:** `builder._pq` och frontendens `folkProb` golvar folkets
  sannolikhet vid 0,001. Utan golv gav streck = 0 utdelning = hela potten.
- **Pool-PIT presence-regel:** `snapshots`/`sharp_snapshots` är ENBART
  förändringsserier. Endast `pool_market_capture` får bevisa att en källa var
  observerad vid T−24h/T−3h/T−20m; gamla `pit-v1`/PH0-laggar får aldrig
  omtolkas till presence. `pool-streckmove-v1`/`pit-v2` hann aldrig
  forward-scoras och är historiskt fryst. Aktuellt experiment finns i
  `docs/pool-ph4-forward-manifest-v2.json` och börjar rent med `pit-v3`;
  captures före `FEATURE_START_AT` får aldrig bakfyllas in.
- **Värderader**: score = P(rad)^k × EV(rad) där k = 2·(1−value_weight); reglaget är enda
  risk-axeln (strategin sätter bara startpunkten 20/50/80).
- **RLM**: folket och devigad sharp åt olika håll (◆ smart pengar / ⚠ fadea).
- **Streck-allokering** (`_size_to_budget`): värde/kostnads-girig per Δlog(täckt sannolikhet)/Δlog(rader).
- **Steam** (`app/steam.py`): devigade sannolikhetsskift (pp) över 6/24/72 h; 🔥 + ntfy på
  24h-skiftet (≥3,5 pp markant, ≥6 pp stark). `movement_with_steam` är delade helpern.
- Bomben: kolumn-baserad byggare (rader = manuell ifyllnad = fil = kostnad), Poisson-modell,
  hålls utanför CLV-facitet (modell-härledd). INGEN exakt-rad-reducering.
- Projicerad slutomsättning: `_projected_turnover` i main.py — sedan 2026-07-28
  median av senaste 8 avgjorda omgångar med SAMMA spelstoppsveckodag ur LOKALA
  `pool_draw_settlement` (0 nätverk; Europatipsets onsdag ≠ söndag), fallback
  senaste-6 redovisad i `projection_basis`. EV-/färgsystem räknar mot
  prognosen; EV mot dagens omsättning är glädjesiffror. Jackpotläge saknas
  medvetet (ingen jackpotkolumn i settlementlagret).

### Export till Svenska Spel ("Egna rader")

- `.txt` (CRLF) med obligatorisk rubrikrad: Stryktipset/Europatipset = produktnamnet;
  Topptipset = `Topptipset[,Stryk|,Europa],Omg=<nr>,Insats=<1–10>`. Därefter `E,1,X,2,...`.
- Exportera alltid konkreta enumererade rader (E), aldrig M-system.
- Uppladdning på `spela.svenskaspel.se/{produkt}/externa-systemspel`.
- R 4-0-9 / R 0-7-16 / R 4-4-144 är exakta Hamming-täckningar; R 3-3-24 är greedy (38 rader).

### CLV-facit (signalvalidering)

- `app/clv.py` + `value_log`-tabellen: gröna värde-kvoter (≥1.08) / sharp-edge (≥2 %) loggas
  first/best per selektion; stängning = devigad Pinnacle; facit från resultat-API:t.
- **Utfalls-facit för Oddset-flaggor (P2, 2026-07-28):** `oddset_value_log`
  har `outcome`/`outcome_key`; `resolve_outcomes` settlar 1X2 via modell-
  spårets join (alias, ±1 dygn, tvetydighet ⇒ ingen gissning). Resultat-ROI/
  träff är DISPLAY (🎯 i Signal-loggen) — grindarna ägs av close-EV. Ligor
  utan football-data får resultat via `RESULT_ONLY_UT` (Sofascore, normaltid,
  INGA statistik-anrop; en EGEN tabell — SOFA_UT ingår i wp9c-/V2.2-
  fingeravtrycken och rörs bara vid omfrysning).
- **Metodregel (dyrast lärdom från vm):** ENDAST marknadspriser får logga flaggor —
  modellhärledda sannolikheter förorenar facitet. Sedan 2026-07-24 gäller den
  även UI:t: amber-modellen mäter −4,2 % close-EV (KI utan noll) och får därför
  inte ge stödchip eller lyfta ett spelkort till "★ starkast stödd".
- **Statistikregler för facitet (2026-07-24, efter att +6,6 % visade sig vara
  +2,65 %):** (1) `oddset_clv_rows()` utan `limit` = hela historiken — trunkering
  ger survivorship; (2) huvudsiffra och KI måste vara SAMMA estimand
  (`avg_close_ev` är winsoriserad som KI:t, `avg_close_ev_raw` visas separat);
  (3) censurerade linjeflyttar räknas (`n_censored`, `resolved_share`) och
  blockerar grönt om de utgör majoriteten av de stängbara flaggorna;
  (4) statusbeslut (candidate/green) körs på förregistrerad kadens
  `EVAL_INTERVAL_H` = 1 vecka — utvärdering vid varje 30-minutersvarv är
  sekventiell testning och lyser förr eller senare grönt på brus.
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
  PL/Serie A/La Liga/Bundesliga är `research_only` men SYNS sedan 2026-07-24 i
  ordinarie vyn (`visible_in_ui`, 🔬-märkta): odds/prisålder/rörelser visas,
  UI-payloaden strippar värde-/modellfält och `_research_next_round` visar
  nästa omgång under säsongsuppehåll. Actionability är oförändrat avstängd —
  inga värdesignaler/Kelly/notiser/CLV/ordinarie model-captures. Före
  träningsgaten måste `p_v22 == p_sharp` exakt; tabellen läses inte av
  värde-, notis-, CLV- eller ordinarie UI-vägar.

## Oddset-delen (byggs nu — se docs/plan.md för detaljer)

- Mönsterkälla: `/Users/saman/vm/backend/app/` — `pinnacle.py` (AH/ÖU/hörn-specials via
  units='Corners'), Kambi-klienten (Svenska Spel Sport, operator `svenskaspel`, milliodds:
  1420=1.42, line i milli: 2500=2.5), `value.py`/`service.value_screen` (power-devig sharp
  vs bok), `model.py` (Dixon-Coles, μ KALIBRERAS mot sharp ÖU-linje ≈ median), steam/CLV/
  notify-mönstren, `elo.py` (ClubElo), `oddsapi.py` (the-odds-api, vilande).
- Enbart gratiskällor (användarbeslut 2026-07-12); rena betalspår = framtida projekt.

### 🚧 KÄLLGRÄNSEN (Samans beslut 2026-07-25: flyttad så långt den går)

Saman satte gränsen så långt den kan gå — till den punkt där den möter modellens
egna gränser. Vidga den inte ytterligare; det som står under "stängt" flyttas
inte av att någon ber om det.

**Öppet:** publika JSON-API:er · statiska publika tokens i sidans kod (t.ex.
Pinnacles gästnyckel, Flashscores `x-fsign`) · läsa publik JavaScript ·
browserlik TLS-signatur (`curl_cffi impersonate`, används redan för Sofascore) ·
observera sidans egen publika nätverkstrafik för att lära sig
endpoint-kontraktet · läsa publika sidor i browsern · artig rate limiting,
timeouts och matchtak.

**Stängt (modellens gräns, inte repots):** lösa eller förfalska
anti-bot-utmaningar — Cloudflare-interstitials, Impervas `reese84`, DataDome,
CAPTCHA · exportera eller återspela browsersession, cookies eller WAF-token för
att framstå som en inloggad/verifierad klient · skapa konton eller logga in.

**Tumregel:** en endpoint som svarar 401/403 *därför att en utmaning eller
session saknas* förblir stängd. En som svarar med data givet publika konstanter
är öppen. bet365, Coolbet, Betano och Betssons `events-table` ligger bakom det
förra.

**Miljöanteckning:** behörighetsklassaren blockerar skript som söker tokens i
JS-buntar (det läser som token-skörd) även när gränsen tillåter det. Behövs det
måste Saman lägga in en Bash-behörighetsregel — se
`docs/live-kallor-2026-07-25.md`.
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

- Designsystemet: 13px bas, sektioner är kort (`section` = --panel, inre ytor = --panel2),
  pill-tabbar i kompakt header, EN statusrad. Bred skärm (≥1280px): sektionspar i `.cols`-grid.
- Mobil: ALLT i `@media (max-width:760px)` — desktop får inte ändras. OBS:
  `td:first-child`-regler måste exkludera `.chartrow`.
- Alla GET-fetch: `cache:'no-store'` + `&_t=${Date.now()}` (annars cachar webbläsare/iOS).
- Tillstånd sparas i `localStorage` (`svs_state`); bootstrap återställer.
- Inga `cursor: help`-frågetecken; förklaringar som title-tooltips.
- Oddset-delen: röd = oddset NER (ökad vinstchans), grön = UPP (vm-konvention).
- Oddset har fyra persisterade sub-tabbar och en alltid synlig räknarrad.
  Jämförbara listor använder EN `SortableTable`: rubrikklick på desktop,
  sortval + samma kortordning på mobil. Matcher-flikens persisterade
  Dölj/Visa startade-filter får inte filtrera Live eller signalflikarna.
  Skapa aldrig tabbspecifika kopior.
- Labb äger validering och fulla loggar. Oddset är beslutsytan; Labb är
  bevisytan. Stora loggar visas stegvis (200 rader) så mobilen inte låser sig.
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
- Odds-eventidentitet (incident 2026-07-26): minsta laglikhet 0,55 gäller på
  BÅDA sidor och parscore ≥0,75. `pinnacle_id`/`kambi_id` är write-once,
  globalt unika och får aldrig bytas via fuzzy-matchning. `pin:<id>` respektive
  `svs:<id>` måste stämma med sin provideridentitet. Samtidiga prisvarianter
  eller suffix/id-krock ger `data_conflict`: visa råodds diagnostiskt men
  stoppa värde, steam, modell, ledger, CLV och notiser. Full audit:
  `docs/oddset-identitetsaudit-2026-07-26.md`.

## Regler

- **Lägg ALDRIG spel automatiskt** — bara deep-link/fil; användaren laddar upp och betalar själv.
- Klicka inte i cookie-/samtyckesrutor åt användaren.
- Committa endast när användaren ber om det. Commit-meddelanden på svenska,
  imperativ rubrik, avsluta med `Co-Authored-By: Claude <modell>`.
- API-nycklar i gitignore:ad `backend/.env` (ODDS_API_KEY finns, the-odds-api är vilande).
- Rör ALDRIG `/Users/saman/svs` eller `/Users/saman/vm` från detta projekt.
- Uppdatera STATUS-blocket i `docs/plan.md` när en etapp/delmål blir klar.
