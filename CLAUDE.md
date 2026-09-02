# Spelkompisen

Personligt lokalt verktyg som kombinerar **SvS kompisen** (poolspels-analys: Stryktipset,
Europatipset, Topptipset, Bomben) med en **Oddset-del**: enskilda matcher i 19 ligor med
sharp-odds, oddsrörelser, egen modell och värdespels-tips (1X2, asian handicap,
över/under, hörnor på sikt).

**Läge: STATUS-blocket överst i `docs/plan.md` är sanningen — LÄS DET FÖRST i ny
session.** Där står vad som är i drift, vilka versioner som gäller (radar, V2.2-manifest,
modelldata, powerrank, PH3-generation) och vilka mätningar som pågår. Aktiv arbetslista:
`docs/backlog.md` (avsnittet **Aktivt**). Historik: `docs/status-historik.md` och
`docs/overlamningar/`. Granskningsevidens: `docs/granskning-2026-07-13.md`.
Versionsnummer skrivs ALDRIG in här — de driftar (den här filen påstod v9 och v11 samtidigt).

Den här filen är REGLERNA. Evidensen, mätningarna och incidenterna bakom varje regel
ligger ordagrant i `docs/claude-md-bakgrund-2026-09-02.md` (fryst fulltext före
bantningen 2026-09-02) — läs den när du undrar VARFÖR, inte varje session.

## Stående regler ur lägesbeskrivningen

- Modellen är en xG-viktad Poisson med DC-korrektion, settlement-ankrad efter T —
  **kalla den inte DC-MLE**. Den är AMBER: sämre än Pinnacle i alla ligor, och det är
  skälet till att den aldrig ger stödchip, lyfter spelkort eller påverkar edge/urval/
  notiser/CLV.
- Historiska hörnpriser får aldrig bakfyllas med dagens modell.
- UI får bara säga `bekräftat kvar` när det oförändrade bokpriset återobserverats efter
  Pinnacles senaste prisändring; vanlig färskhet eller ett gammalt cachepris räcker inte.
- **En ny liga i radarscopet ändrar populationen** som kan producera en signal ⇒ ny
  radarversion, aldrig en utökning inne i en löpande version. `live_settlement` vägrar
  settla när radarversionen saknas i dess capture-tidslinje — spärren ska inte tas bort.
- Liveblindtestets pris: SvS/Kambi, Ninja/Altenar och Pinnacles live-endpoints frågas vid
  första Följer/Stark. **Pinnacle får bara påverka spelet vid HTTP Age ≤ 90 s.** Linan väljs
  först (färsk Pinnacle, annars Kambi, annars Ninja), sedan högsta Över-odds på EXAKT samma
  lina. Alla källobservationer sparas i `oddset_live_signal_quote`; priser bakfylls aldrig.
- Spelade poolkupongers liverättning: 1X2-kedjan Kambi → Ninja → Pinnacle (Age ≤ 90 s).
  Saknar alla tre komplett 1X2 används den märkta ställnings-/tidsmodellen — enbart som
  kupongchans, aldrig som system, värde eller facit. `chance_live_source_counts` visar valet.
- PH5-/maxtestkuponger liverättas via rent läsande `GET /api/pool/systems/live`;
  `events_order` är alltid kanon för kolumnmatchningen. Livebilden skriver aldrig facit.
- **V2.2** är en isolerad sharp-identitetskontroll under fryst manifest (aktuellt nummer i
  plan.md). `feature_version` hashar manifestets EGET experimentnamn — läs ut värdet EFTER
  att den nya manifestfilen finns. En ny kalibrering, en aliasändring i en FIT_POOLS-liga
  (inkl. matarligorna Championship/Serie B/Segunda/2. Bundesliga) eller ändrad
  `MODEL_DATA_VERSION` är en ändrad datagenererande process ⇒ nytt manifest. Äldre manifest
  blandas aldrig in. Det är inte en tränad modell och får inte påverka tips, notiser eller
  CLV. Före träningsgaten måste `p_v22 == p_sharp` exakt.
- **Bakfyllning är tillåten för RESULTATSTATISTIK** (ett avgjort resultat och dess xG är
  settlade fakta) **men aldrig för priser, live-signaler eller presence**, där
  observationstiden är en del av mätningen.
- Modelligorna poolas MEDVETET INTE med sina matarligor (uppmätt sämre — matarligorna saknar
  xG). T är kalibrerat per liga; sharp-versionen rörs inte av en modellkalibrering.
- `_xg_is_measured()` förkastar xG-par där båda är exakt 0,00 eller där ett lag som GJORDE
  MÅL har 0,00 (Sofascore rapporterar saknad mätning som noll). Ett mållöst lag med 0,00
  lämnas orört: **radera på omöjlighet, aldrig på osannolikhet.**
- `_fd_result_rows(..., div=)` kontrollerar filens EGEN divisionskod.
- `oddset_model.elo_for()` slår upp ClubElo på EXAKT nyckel eller VERIFIERAT alias
  (`ELO_TEAM_ALIAS`, avvisningar i `ELO_REJECTED_LINKS`) — **aldrig fuzzy**. Ett lag utan
  verifierad länk får INGEN Elo: ingen modell är bättre än fel modell.
- Synlig ≠ actionable: cuper och träningsmatcher visas och bär sharp-signaler utan modell.
  `_next_round_for_empty_leagues` visar nästa omgång under säsongsuppehåll.
- `pool-strength-blend-v1`: Pinnacle orörd baslinje, 90/10 enda kandidat, 80/20 diagnostik.
  Modellversion, timing, identitet, blend eller gate ändras aldrig inne i samma
  manifest/shadowversion. `/api/pool/strength-shadow` tar `family=1` (en familjenyckel är
  ett giltigt PRODUKTnamn men filtrerar exakt).
- Powerranken (`powerrank-v2`) mäter poäng, mål och xPts på EXAKT samma matchmängd — de med
  xG; lag utan xG-matcher visas inte. `MIN_MATCHES` prövas mot hela historiken.

**Relationen till syskonprojekten:**
- `/Users/saman/svs` (SvS kompisen, portar 8000/5173) — ursprunget, **FRYST ARKIV sedan
  2026-07-20** (paritet nådd: launchd urlastat, servrar stoppade, DB kvar som arkiv;
  återaktivering via plist i svs/backend/scripts/). RÖR ALDRIG svs härifrån.
- `/Users/saman/vm` (Boll boll kollen, portar 8001/5174) — VM-bevakning, mönsterkälla för
  Oddset-delen (Pinnacle AH/ÖU/hörnor, Kambi-klient, värdescreen, steam, Dixon-Coles, CLV).
  Läs vm-koden som referens vid portning men RÖR den inte.
- Portar här: **backend 8002, byggd frontend 5175, dev 5181** — krockar aldrig med svs/vm.

## Arkitektur

```
backend/  Python 3.13 + FastAPI + httpx (venv i backend/.venv — INTE uv)
  app/svenskaspel.py  SvS pools-API-klient (PRODUCTS, GAME_GROUPS, Draw, family_of)
  app/pinnacle.py     Pinnacle Arcadia (gratis guest-API), + derive.py (1X2 ur spread/total)
  app/altenar.py      Ninja Casino/Altenar: listvy 1X2 + mål, eventdetalj för huvudlinan
                      totalt antal hörnor (bara i deep-/snabbfönstret)
  app/betsson.py      Publik Betsson-bootstrap (ej inkopplad; events-table CloudFront-
                      blockerad utanför browser; KRÄVER brotli, se transportregeln)
  app/analysis.py     fair_prob (power-metod), värde, taggar, speltyp, mover-flagga
  app/builder.py      radbyggare: matematiskt/reducerat/garanti/SvS R-system/EV-topp; KAPPA
  app/bomben.py       Poisson-målmodell för Bomben (amber, utanför CLV)
  app/storage.py      SQLite (data/stryktips.db): snapshots, sharp_snapshots, dedup, movement
  app/oddset.py       Oddset-insamling (LEAGUES, BOOKS, collect, matches_payload)
  app/oddset_value.py sharp-värdemotor, ANCHOR_SOURCES, drift_adjust, clv_report
  app/oddset_ledger.py WP5-forskningsfacit: prediktioner frysta vid T−24h/T−3h/T−20m
  app/oddset_model.py xG-viktad Poisson + DC, cached_fit, elo_for, powerrank
  app/oddset_v22.py   isolerad V2.2 feature-/shadowcapture (ej live-tips)
  app/oddset_health.py tystnadsdetektion: Oddset-varv, pool-basvarv, kärnkällor, liveradar
  app/gater.py        alla förregistrerade grindar på ett ställe (cli.py gater)
  app/pool_settlement.py PH1: immutable poolfacit (append-once, payload-hash; retry_after
                      per rad; läs-API /api/pool/history)
  app/pool_dataset.py PH2: PIT-features per omgång/horisont (pit-v4, enbart observed_pit —
                      no backfill) + presence-ledger och proveniensmärkt pool_draw_snapshot
  app/pool_played.py  SPELADE kuponger (🎟 eller bekräftad import av Egna rader-fil): bokför
                      att SAMAN själv lämnat in kupongen, lägger inga spel. FACIT =
                      settlementlagrets officiella outcome mot PUBLICERAD utdelning.
                      LIVESTATUS ur SvS draw-payload — aldrig facit. match_finished()/
                      regulation_over() är de ENDA definitionerna av "färdigspelad"
  app/pool_system_ledger.py PH3: benchmarksystem frysta T−3h/T−20m, settlade kontrafaktiskt;
                      benchmarks_for(product) är ENDA källan till vad som mäts;
                      research_families_for() (PH5/mathmax/reducedmax) är aldrig utmanare
  app/pool_health.py  poolens änd-till-änd-larm (snapshots, frysningar, settlement)
  app/pool_strength_shadow.py pool-strength-blend-v1 (Historik → Poolmodell)
  app/live_radar.py   shadow-radar för pågående matcher: Flashscore ankare, FotMob sekundär,
                      Sofascore URKOPPLAD ur radarn (kvar för resultat/frånvaro)
  app/live_signal_ledger.py append-only-journal över första Följer/Stark per match,
                      låst livepris, normaltidsfacit, Över-ROI. Aldrig tipsinput
  app/live_settlement.py radarmomentens facit per signalversion
  app/flashscore.py   liveprovider (pipe-feed + per-match df_sur); brotli KRÄVS
  app/flashscore_data.py Flashscore modelldata parallellt med Sofascore
  app/fotmob.py       liveprovider: live-xG/xGOT/skott, egen presence/source-health
  app/main.py         API-endpoints + PRIZE_PLANS (officiella vinstplaner)
  cli.py              snapshot|pool-tick|live-tick|kallhalsa|gater|lanklucka|v22audit …
frontend/ React + Vite, mörkt tema.
  src/AppV3.jsx + AppV3.css  APPEN (enda gränssnittet sedan 2026-07-26): vyerna Idag,
                      Poolspel, Oddset, Historik, 5 000-test, Max-tester, 🧪 Labb
  src/App.jsx + App.css  KOMPONENTBIBLIOTEKET (AnalysisTable, SystemView, CouponPanel,
                      PlayRec, PlayedPanel m.fl.) — re-exporterar även allt nedan
  src/lib/            ren logik utan React, testad med node --test: format.js,
                      poolEv.js (KAPPA/evalRows/couponStats/systemStats), playRec.js,
                      poolSelection.js, sourceHealth.js
  src/components/     ui.jsx (Loading/Empty/ErrorState, ErrBoundary, useStoredBool),
                      SortableTable.jsx, charts.jsx
  src/oddset/OddsetView.jsx  hela Oddset-vyn (Matcher/Live/Värdespel/Rörelser/Lagstyrka)
start.sh / stop.sh    lokal utveckling (8002 + 5175); biter INTE på serverns KeepAlive
tools/kontroll.sh     hela kontrollen före push; tools/githooks/pre-push kör den
tools/tjanster.sh     drift på MacBook-servern: start/stopp/omstart av alla LaunchAgents
docs/plan.md          STATUS + färdplan — projektets sanning
docs/status-historik.md daterade statusblock (historik, aldrig nuvarande kontrakt)
docs/overlamningar/   alla överlämningar (overlamning-<datum>-<ämne>.md)
docs/backlog.md       AKTIV BACKLOG — ändra prioritet bara med Samans godkännande
docs/forbattringar.md ARKIV: svs-ärvda lärdomar + bokkälls-kartläggning
docs/claude-md-bakgrund-2026-09-02.md  evidensen bakom reglerna i den här filen
```

### Regler per modul (evidens: bakgrundsdokumentet, samma rubriker)

**pool_played.py — resultat och status**
- **POOLREGELN (Saman 2026-08-11): poolspel fastställs på ordinarie 90 minuter, så en
  match i förlängning RÄKNAS SOM KLAR** — `final` = `regulation_over()` (slut ELLER
  förlängning). Osäkerhet om VILKET resultatet är får inte avgöra om matchen är AVGJORD;
  den bärs av `sign_provisional`, och `_decided()` kräver `final` OCH icke-struken OCH
  icke-provisorisk. Ett obelagt tecken redovisas som SPANN (`alive_min/max_per_level`),
  aldrig som en gissning presenterad som faktum.
- Ordinarie tid läses `Fulltime` → `Current` minus `Overtime` → Flashscores `df_sur`
  (`attach_regulation_time`) → `Current` (märkt). Flashscorevärdet får ALDRIG ligga över
  SvS ställning; källfel ändrar aldrig ett tecken.
- **STATUSKODER GISSAS ALDRIG.** Bara observerade koder får ligga i statusmängder
  (`statusId 23` = "Uppskjuten", inte förlängning); klartexten SvS skickar bredvid är
  skyddsnätet (`EXTRA_TIME_STATUS_WORDS`). `match_postponed()` är en egen fråga och
  settlementets omprövning hoppar över den. `FINISHED_STATUS_IDS` bär 32 och 33.
- **FULLTIME-NÄTET FÅR INTE KÖRA ÖVER KLOCKAN.** Nätet finns för OKÄNDA statuskoder, inte
  som bevis: `match_finished`/`regulation_over` tar `now` och nätet gatas av
  `REGULATION_WALL_CLOCK_MIN` = 105 min. Vetot är FYSIK och gäller BARA nätet — en
  uttalad slutstatus vinner alltid. Stoppa när det är omöjligt, aldrig när det bara är
  osannolikt (marginalen är inte settlementets 130).
- **INSTÄLLD OMGÅNG:** `settle_draw` skriver `draw_state='Cancelled'`; ledgern skiljer
  `cancelled` från `unresolvable`. **Att märka räcker inte — konsumenterna måste
  exkludera** (`/api/pool/history` räknar på icke-inställda; `archive_total` separat).
- Live-1X2-källor: Kambi först, Ninjas `GetLiveEvents` reserv (bara `sportMarketId=70472`,
  ej `isAlt`, kryss-id 2 — id 7 betyder `Ingen` och får ALDRIG bli X), Pinnacle sist
  (Age ≤ 90 s). Samma-sida krävs; ensidigt namnbevis kräver avspark på båda sidor, ≤ 30 min
  och EN kandidat.

**pool_system_ledger.py — PH3**
- `benchmarks_for(product)` är ENDA källan till vad som mäts. Topptipset-familjen har tak
  512 (3^8 = 6 561 rader; 1 024 vore mattbombning). En `config_key` ändras aldrig i
  efterhand — nya nycklar räcker, ingen migrering. Championen MÅSTE spegla appens
  budgetreglage. Promotion kräver BH-FDR över hela utmanarfamiljen OCH ≥ 40 parade omgångar.
- **SPELFAMILJ, INTE PRODUKTSLUG:** `champion_report()` grupperar på `family_of()`;
  `_paired_draw_roi` parar på `(produkt, omgång)`. Produktslug, settlementidentitet och
  `config_key` är OFÖRÄNDRADE — familjen styr vad som mäts ihop, aldrig vad något heter.

**live_radar.py / flashscore.py / fotmob.py — liveidentitet**
- Källan väljs på strukturell fälttäckning (aldrig på signalvärdet), därefter fast
  prioritet Flashscore → FotMob. En olänkad färsk providerserie får eget kort; gör aldrig
  livevisningen beroende av att en källa först kan länkas till en annan providers rad.
- **NAMNLÄNKNING I TRE STEG** (`_linked_series`), varje steg kräver EXAKT en kandidat:
  (1) strikt `_same_team` på båda lagen; (2) `_same_team_in_context`; (3)
  `_one_side_candidates` — ETT lag räcker när liga och exakt avspark delas. Steg 2–3 är
  säkra ENBART tack vare anropsstället. Truppmarkörer (U23/B/women) spärrar i ALLA steg.
  `cli.py lanklucka` MÅSTE köra samma regler som länken.
- Träningsmatchspärren (`known_friendly`) styr RÄCKVIDD, inte pris: avspark känd på båda
  sidor, ≤ 15 min ensidigt, två kandidater ⇒ avslag.
- **KLOCKAN SAKNAS ALDRIG:** `STAGE_FROZEN` bär etikett OCH spelad minut för frysta
  stadier; `STAGE_LABEL` visas i klockans ställe, `STAGE_NAME` bara som reserv. Minuten
  HÄRLEDS ur stadiets starttid — okänt stadium ⇒ None.
- Koherensvakten är RIKTAD: ställning äldre än stats = farlig (20 s), stats äldre än
  ställning = konservativ (180 s). Stadiebyte censurerar minuten hellre än låter den
  ticka fel. Lyckad tom lista avslutar presence; transport-/parsefel aldrig.
- Possession läses med `_share`, aldrig `_f`. xG saknas genuint i de flesta
  europacupkval (feeden har två paket) — providerns gräns, inte parserns.
- `live_radar._same_team` styr TRE länkar (provider↔provider, livekort↔Oddset,
  signal↔resultat). Presentationsskillnad ⇒ `LIVE_TEAM_ALIASES`; samma klubb i
  resultathistoriken ⇒ Oddsets `TEAM_ALIASES`. Kända falska par skrivs explicit i
  `LIVE_TEAM_REJECTED` — aldrig en generell regel (flerords-prefix gjorde LAFC = Galaxy).
- **KOHORTREGELN:** en rad hör till vN bara om vN-KODEN producerade den OCH den
  observerades i vN:s DEKLARERADE fönster — annars `transitional`, som ingår i INGEN
  kohort. Rader flyttas ALDRIG till föregående kohort. `radar_version` MÅSTE ligga i
  `_FLASHSCORE_VIEW_KEYS`/`_FOTMOB_VIEW_KEYS`. Settlement stämplar efter capturetid. En
  ändrad datagenererande process kräver alltid ny signalversion. Provider-id är
  ogenomskinlig STRÄNG överallt.
- Proxysignalen är ETT ENHETSLÖST INDEX (`proxy_index`) och får aldrig uttryckas i mål.

## Kommandon

- Starta allt: `./start.sh` (backend :8002, frontend :5175). Stoppa: `./stop.sh`.
- **På MacBook-servern gäller `tools/tjanster.sh` i stället** — `stop.sh` dödar
  bara porten och launchd startar om tjänsten inom sekunder (`KeepAlive`).
  `tjanster.sh status|start|stopp|omstart <tjänst|all|spelkompisen>`;
  `stopp … --permanent` lägger till `launchctl disable` och överlever omstart.
  Se `docs/AI-OVERLAMNING-SERVER.md` § 3. Omstart bygger INTE frontenden —
  `cd frontend && npm run build` först.
- Tester: `cd backend && .venv/bin/python -B -m unittest discover -s tests -v`.
- **Hela kontrollen före push: `tools/kontroll.sh`** (backendtester + lint +
  frontendtester, `backend`/`frontend` som argument för en del). Pre-push-hooken
  i `tools/githooks/` kör samma sak; aktivera per klon med
  `git config core.hooksPath tools/githooks`, förbi medvetet med `SKIP_KONTROLL=1`.
  `backend/requirements.lock` är serverns frysta venv (`requirements.txt` är avsikten).
- **Alla grindar på ett ställe: `cd backend && .venv/bin/python -B cli.py gater`**
  — läser varje spårs egen statusfunktion, räknar inget om och beslutar inget. Kör den
  innan ett nytt spår startas.
- V2.2-status: `cli.py v22audit`. Källhälsa/varvlucka: `cli.py kallhalsa [timmar]`
  (`—` i varvkolumnen = källan kördes inte; visar även Oddset- och poolhälsan).
- **Dubblettjakt: `cli.py lanklucka [timmar]`** — providerpar med samma liga, samma
  avspark och hög namnlikhet som ändå INTE länkar. Kör den efter varje ny liga/kvalomgång.
  Bekräftade par går i `LIVE_TEAM_ALIASES`, bekräftat olika klubbar i `LIVE_TEAM_REJECTED`.
- Live-radar manuellt prov: `cli.py live-tick` (shadowdata; påverkar inga tips/notiser).
- **Backend har INGEN auto-reload** — efter ändring lokalt:
  `lsof -ti:8002 -sTCP:LISTEN | xargs kill -9; cd backend && nohup .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002 &`
  (på servern: `tools/tjanster.sh omstart backend`).
- ALDRIG `pkill -f uvicorn` (dödar svs 8000 och vm 8001 — samma kommando).
  ALDRIG `lsof -ti:<port>` utan `-sTCP:LISTEN` (dödar annars webbläsare med öppna sockets).
- Frontend nås via Tailscale/LAN (vite.config: `host:true, allowedHosts:true`).
  `frontend` i `.claude/launch.json` bygger och serverar produktionsbunten på 5175.
  `frontend-dev` kör Vite/StrictMode på 5181 endast under utveckling.
  **Dev-servern dubbelkör allt** (StrictMode) — mät alltid på den byggda bunten innan du
  jagar en frontendbugg som är ett dev-artefakt.

### Insamlingen (två launchd-jobb)

- `com.saman.spelkompisen.snapshot`: Oddsets fullvarv på fasta :00/:30 (alla källor +
  Kambi-deep + modelldata), därefter snabbvarv var 4:e min så länge någon match startar
  inom 3 h (`FAST_WITHIN_H`), inom ~25 min budget.
- `com.saman.spelkompisen.pool`: kort varv var 5:e min. `pool-tick` gör basinsamling var
  30:e min och varje tick när ett poolspel stänger inom 2 h; därefter `live-tick`.
  **SETTLEMENT KÖR PÅ VARJE TICK** (`_settle_pass`): insamling kostar, facit gör det inte.
  Varje rad i `pool_backfill_log` bär sin EGEN `retry_after` (avspark + 130 min, färdig
  omgång var 15:e min, tak 6 h). Höj inte `SETTLE_PASS_MAX_DRAWS` (2/produkt) utan att
  räkna om radarns marginal. `pool_played.match_finished()` är EN delad definition —
  skriv aldrig en parallell.
- **`live-tick` förtätar sig själv** (`LIVE_DENSE_BUDGET_S`/`_INTERVAL_S` i cli.py) och
  slutar direkt när ingen livematch har chansdata. Budgeten är räknad mot att `pool-tick`
  kan ta upp mot en minut — ändra den inte utan att räkna om marginalen.
- **Förtäta ALDRIG poolvarvet eller Oddset-varvet:** Pinnacles bulk är CDN-cachad
  `max-age=905`, så anrop oftare än ~15 min returnerar samma objekt. Radarns källor är
  färska (FotMob `max-age=10`, Flashscore `Age` ~3 s). Flashscores dagsfeed hämtas färsk
  varje varv — cachad ställning är värre än trafiken.
- Varje liveprovider har egen presence och source-health. Ett **lyckat** tomt roster
  avslutar tidigare kort; nät-/parsefel får aldrig göra det. `last_run` är den äldsta av
  `LIVE_SOURCES`-kontrollerna och tom tills alla kontrollerats.
- Live-radarn är shadow och får inte påverka tips, Kelly, CLV, pushnotiser eller
  systemförslag utan ett nytt explicit beslut. Blindkohorten är FÖRSTA aktiva signalen per
  match; grinden är `BLIND_MIN_*` i `live_signal_ledger.py` och undre KI90 > 0; inga
  historiska liveodds bakfylls.
- Notiser går i Oddset-varvet bakom **notisvakten** (larm kräver att priset observerades
  i det aktuella lyckade varvet). Notifieringsspåret är pausat på Samans begäran
  2026-07-16 — återuppta inte utan besked. Driftlarm (tystnad) visas i UI:t, aldrig ntfy
  (Samans beslut 2026-09-02).
- **WP2-prisregel:** `fetched_at` = prisförändring, `last_seen_at` = senaste lyckade
  bekräftelse. Värde/modell/steam/facit kräver `available` och högst 45 min gammal
  bekräftelse. Pinnacles HTTP `Age` dras av före båda tidsstämplarna; cacheobjekt äldre än
  5 min öppnar inte notisgrinden. Källfel får aldrig markera ett pris unavailable.

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
   gjorde "vi frågade inte" till "Pinnacle listar inte matchen". Spärren får förbigås
   bara i ett öppet horisontfönster (`pool_dataset.horizon_window_open`), eftersom en
   horisont observeras en enda gång och aldrig får bakfyllas.
7. **En latest-state-tabell är inget facit på att en källa kördes.**
   `oddset_source_health` skriver över sig själv. `oddset_source_health_log` är
   append-only med `checked_at` i nyckeln och är den enda som får bevisa att en källa
   kontrollerades i ett visst varv. Skriv en rad per kontroll, annars går "vi frågade
   och fick tomt" inte att skilja från "vi frågade aldrig".
8. **`Z` betyder UTC, inte bara ett suffix.** En offsetmedveten tid måste konverteras
   med `astimezone(timezone.utc)` innan den formateras med `Z`.
9. **Klockan injiceras, aldrig gömd i SQL** (`'now'`) eller i en funktion ett test inte
   kan styra — annars får testet ett bäst-före-datum (main var röd 2026-09-02 för att en
   "färsk" rad hunnit bli 31 dagar).

### 📦 TRANSPORTREGELN — status 200 betyder inte läsbar kropp

`brotli` MÅSTE finnas i venv:et (`requirements.txt`). CloudFront svarar
`content-encoding: br` även på `Accept-Encoding: gzip`, och httpx avkodar br
bara om paketet är installerat — annars kommer kroppen tillbaka som binärt
skräp med status 200. **En parse som misslyckas på 200 är ett transportfel
tills motsatsen är bevisad** — kontrollera `content-encoding` innan du drar
slutsatsen att sidan ändrats eller källan blockerar.

### ⚡ MODELLFITTEN CACHAS — rör inte numeriken för att vinna tid

`oddset_model.cached_fit()`/`cached_results()` är ENDA vägen till en ligafit i ett
HTTP-svar. Nyckeln är `(db_path, resultat-datastämpel, dagens datum)` + 1 h TTL —
databasen MÅSTE ingå (två tomma DB:er ger annars samma fingeravtryck). Den cachade
basfitten returneras alltid som isolerad deepcopy; `_ensure_priors` får aldrig förorena
nästa svar.

Optimera ALDRIG `_anchor_total`/`dc_matrix` genom att ändra konvergens eller
iterationer — det ändrar modellens utdata, alltså `model_version`, och
nollställer dess facitgrupp. Cachning är gratis; numerik är det inte.

**`UI_HIDDEN_SOURCES`** (oddset.py) döljer källor i API-payloaden (i dag `smarkets`).
Att DÖLJA är inte att AVSPÄRRA: spärren i `ANCHOR_SOURCES` står kvar, insamlingen
fortsätter för promotionsregeln, och den INTERNA payloaden till WP5-ledgern strippas
aldrig. Låst av `test_dold_kalla_forsvinner_ur_api_men_inte_ur_ledgerns_payload`.

### 🎯 ANKARE ≠ BOK

`BOOKS` i oddset.py styr INSAMLINGEN. `oddset_value.ANCHOR_SOURCES` styr
VÄRDERINGEN. Båda behövs. Lägger du till en sharp-referens (börs, andra sharp-böcker)
MÅSTE den in i `ANCHOR_SOURCES`, annars förorenar den CLV-facitet. Spärren är låst av
`tests/test_oddset_value.py::AnchorSourceTests`.

**CLOSING-DRIFT (sharp v8):** `fair` är inte Pinnacles pris NU utan en skattning av
var det STÄNGER. `drift_adjust` korrigerar per band (favoriter ned, outsiders upp) i två
tidsregimer; bandet sätts på den OJUSTERADE sannolikheten (annars cirkulärt) och summan
normaliseras INTE om. Detta är INTE momentum. Förregistrering:
`docs/closing-drift-v8-forregistrering-2026-08-07.md`.

Andra ankaret (Smarkets) är BORTKOPPLAT 2026-08-07. **Spärren i `ANCHOR_SOURCES` står
kvar** — en SÄKERHETSSPÄRR, inte en användning: utan den blir Smarkets en spelbar bok
igen. `anchor2_*`-kolumnerna är historik och får ALDRIG påverka urval, edge, q eller
notiser; promotion sker bara enligt `docs/tva-ankare-2026-07-25.md`.

- Push-notiser: `app/notify.py` via ntfy.sh, kräver `NTFY_TOPIC` i gitignore:ade
  `backend/.env`. Använd ett EGET topic (inte samma som svs).

## Poolspelen (ärvt från svs — allt gäller oförändrat)

### Svenska Spel-API:t (öppet, inga nycklar)

- `https://api.spela.svenskaspel.se/draw/1/{slug}/draws` (lista) och `/draws/{nr}` (en omgång).
  Prefixet är ALLTID `1` (API-version, inte productId). Nyckel i svaret: `draws` (lista) / `draw` (singular).
- Slugs: stryktipset, europatipset (har listing); topptipset, topptipsetstryk, topptipsetextra
  (pid 25/23/24, INGEN listing → nummerscanning med seed i meta-tabellen). Topptipset-fliken
  aggregerar alla tre via `GAME_GROUPS`; varje omgång bär sin egen `product`-slug.
  **Scanhintet ägs av `Storage.seed_hint()`/`store_seed()`** och MÅSTE användas av både
  API och insamlingsvarv — `_scan_draws` tittar bara 80 nummer framåt. Hintet går bara
  FRAMÅT. **ANKARET ≠ HINTET:** `seed_hint()` returnerar SCANANKARET (aldrig så högt att en
  öppen omgång faller under `back=8`); `stored_seed()` är det RÅA hintet som `store_seed()`
  jämför mot och som poolhälsan larmar på. Golvet räknar bara omgångar som RIMLIGEN är
  öppna (`state='Open'` OCH spelstopp inom `SCAN_LIVE_GRACE_H`); `sync_draw_states()`
  skriver tillståndet för ALLA listade omgångar. **Höj inte `back` en tredje gång.**
  En förlorad h3-frysning går ALDRIG att bakfylla — `timely=0`, räknas inte i facitet.
- Svenska decimaler: "5,50" → 5.50 (`_f` i svenskaspel.py). `svenskaFolket` = streck %,
  `currentNetSale` = omsättning, `drawEvents[].match.participants[].isoCode` = flaggor.
- `/draws/{nr}/result` ger `distribution` (faktiska vinstnivåer/utdelningar).
- **Jackpot**: `/draw/1/jackpots` (matcha på productId + drawNumber — `fund` på draws är
  opålitligt). Belopp som svensk decimalsträng ("6000000,00").
- Vinstplaner OMMÄTTA 2026-07-24 mot settlementlagret:
  **Stryktipset** 40/15/12/25, **Europatipset har EGEN plan** 39/**22**/12/25.
  Splitsen summerar till < 1 (Stryk 0,92, Europa 0,98); resten går till jackpotfonder.
  Använd `_payout_ratio()` (= ratio × Σsplits) för allt som visas som återbetalning:
  Stryk **59,8 %**, Europa **63,7 %**, Topptipset 70 %. Break-even mot fältet är därmed
  +67 % (Stryk). `/api/payouts` svarar med `payout_ratio`, `hurdle`, `product`, `guarantees`.
- **Garantier** (`guaranteedJackpots`) läses av `get_guarantees()` och visas i UI men går
  ALDRIG in i EV — villkoren är inte verifierade mot SvS regler. `get_jackpot()` summerar
  bara rullpotten. `/jackpots` hämtas EN gång per payouts-anrop; **cachen ligger i
  API-lagret, inte i klienten** — varvet anropar utan `data` och observerar färskt.
- **Strukna matcher räknas normalt** (uppmätt: ingen fördel). Tvinga aldrig helgardering
  på dem. Topptipset 70 %, bara 8 rätt delar potten. Finns i `PRIZE_PLANS` i main.py.

### Pinnacle (sharp-odds, gratis)

- `https://guest.api.arcadia.pinnacle.com/0.1`, header `X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R`,
  soccer = sport 29. `/sports/29/matchups` + `/sports/29/markets/straight` (moneyline period 0).
  Amerikanska odds → decimal. Matchning via ISO/pycountry + fuzzy + tidsfönster + spegling 1↔2.
- Saknas moneyline härleds 1X2 ur spread/total (derive.py) — märks `P~` i UI.
- **CDN-CACHE:** bulk-endpointerna svarar `max-age=905` och objektet är ofta redan flera
  minuter gammalt. `Pinnacle` exponerar `last_age_s`; Oddset-färskhet och poolens PIT-capture
  drar av den. Per-matchup-endpointen (`/matchups/{id}/markets/straight`) är den enda som
  ger LIVE-priser — `/markets/related/straight` returnerar tyst FRYSTA prematch-marknader.
- OBS (vm-lärdom): Arcadia Cloudflare-blockar i perioder på IP-nivå — headers/TLS hjälper EJ.

### Domänmodell (kärnformler)

- **fair_prob**: overround bort med **power-metoden** (lös k så att Σ(1/odds)^k = 1).
  Sannolikhetskälla i prioritetsordning: SvS-odds → sharp (Pinnacle) → streck.
- **Värde-kvot** = fair_prob ÷ (streck/100). > 1.08 grönt (köpläge), < 0.92 rött (överspelat).
- **EV per rad** (poolspel): P(rad) × utdelning där utdelning = pott_nivå / (fält × P_folk(rad) + 1),
  cappad vid potten. Jackpot/rullpott läggs på toppnivån **före radvalet**.
  Medvinnare per nivå via Poisson-binomial. +1 = du själv.
  `evalRows` (frontend, `src/lib/poolEv.js`) och `build_ev_system` (backend) — håll dem konsistenta.
- **κ för poolmedvinnare** skattas som `Σ faktiska vinnare / Σ prognos` med omgången som
  bootstrap-block. κ per produkt och nivå är INKOPPLAD i radvalet, portföljsimuleringen
  (`pool_mc kappa_by_tier`) och PH3-ledgern: `builder.KAPPA` och `KAPPA` i
  `src/lib/poolEv.js` MÅSTE vara identiska — låst av `tests/test_kappa_synk.py`. κ>1 sänker
  EV — korrektionen kan aldrig blåsa upp förväntningar.
- **Streck-golv:** `builder._pq` och frontendens `folkProb` golvar folkets sannolikhet vid
  0,001. Utan golv gav streck = 0 utdelning = hela potten.
- **Pool-PIT presence-regel:** `snapshots`/`sharp_snapshots` är ENBART förändringsserier.
  Endast `pool_market_capture` får bevisa att en källa var observerad vid T−24h/T−3h/T−20m;
  gamla laggar får aldrig omtolkas till presence. Captures före `FEATURE_START_AT` får
  aldrig bakfyllas in.
- **Värderader**: score = P(rad)^k × EV(rad) där k = 2·(1−value_weight); reglaget är enda
  risk-axeln (strategin sätter bara startpunkten 20/50/80).
- **X-skydd (`pool-draw-risk-v1`):** vid Pinnacle-total ≤ 2,25 skyddas X från 29,5 %
  (32 % utan total) i ALLA automatiska systembyggen. Totalen sparas point-in-time.
- **RLM**: folket och devigad sharp åt olika håll (◆ smart pengar / ⚠ fadea).
- **Streck-allokering** (`_size_to_budget`): värde/kostnads-girig per Δlog(täckt sannolikhet)/Δlog(rader).
- **Steam** (`app/steam.py`): devigade sannolikhetsskift (pp) över 6/24/72 h; 🔥 på
  24h-skiftet (≥3,5 pp markant, ≥6 pp stark). `movement_with_steam` är delade helpern.
- Bomben: kolumn-baserad byggare (rader = manuell ifyllnad = fil = kostnad), Poisson-modell,
  hålls utanför CLV-facitet (modell-härledd). INGEN exakt-rad-reducering.
- Projicerad slutomsättning: `_projected_turnover` — median av senaste 8 avgjorda omgångar
  med SAMMA spelstoppsveckodag ur LOKALA `pool_draw_settlement`. EV-/färgsystem räknar mot
  prognosen; EV mot dagens omsättning är glädjesiffror. **Byggaren (`systemStats`) värderar
  alltid mot prognosen, kupongen (`couponStats`) mot LIVE tills användaren trycker
  `→ prognos`** — avsiktligt, men måste sägas ut i UI:t. `PayoutTable` härleder omsättning
  OCH etikett ur `s.turnover`; skicka aldrig in omsättningen separat.
- **Chansmotorn räknar EXAKT** (klotunion, `_ball_union_probabilities`), inte simulerat;
  Monte Carlo bara när klotet inte ryms i `CHANCE_BALL_MAX_CANDIDATES`. `_round_chance`
  behåller minst tre värdesiffror. Varje match utan livepris TREDUBBLAR arbetet — mät
  alltid med `chance_unpriced` i handen.

### Export till Svenska Spel ("Egna rader")

- `.txt` (CRLF) med obligatorisk rubrikrad: Stryktipset/Europatipset = produktnamnet;
  Topptipset = `Topptipset[,Stryk|,Europa],Omg=<nr>,Insats=<1–10>`. Därefter `E,1,X,2,...`.
- Exportera alltid konkreta enumererade rader (E), aldrig M-system. SvS filspec: högst
  10 000 rader per fil och 20 000 kr insats.
- Uppladdning på `spela.svenskaspel.se/{produkt}/externa-systemspel`.
- Om 🎟-knappen glömdes kan samma sparade fil importeras i Historik:
  `/api/pool/played/import/preview` skriver inget; först `/api/pool/played/import` skapar
  ledgerraden. Filnamnets omgång används för Stryk/Europa; omdöpt fil kräver manuellt
  omgångsnummer och konflikt faller stängt.
- R 4-0-9 / R 0-7-16 / R 4-4-144 är exakta Hamming-täckningar; R 3-3-24 är greedy (38 rader).

### CLV-facit (signalvalidering)

- **Modelldata:** `oddset_results` bär bara matchidentitet och normaltidsresultat (en
  komplett football-data-rad vinner atomiskt). xG och hörnor bor i `oddset_result_stats`:
  alltid ett komplett hem/borta-par per statistikfamilj med `*_provider*`; blanda aldrig
  fält mellan providers. `RESULT_STATS_PRIORITY` är `sofascore` FÖRE `flashscore`
  (Flashscore mäter systematiskt lägre xG; kvar som korskontroll/fallback). Frånvaro har
  provider i primärnyckeln; transportfel är aldrig `unavailable`, ett lyckat tomt svar är
  en riktig observation. Ett verifierat alias vinner över "namnet finns redan i canon".
- `app/clv.py` + `value_log`: poolens gröna värde-kvoter (≥1.08) / sharp-edge (≥2 %)
  loggas first/best per selektion; stängning = sista devigade Pinnacle FÖRE avspark.
- **Utfalls-facit för Oddset-flaggor:** resultat-ROI/träff är DISPLAY — grindarna ägs av
  close-EV. Ligor utan football-data får resultat via `RESULT_ONLY_UT` (egen tabell; ingår
  i V2.2-fingeravtrycken och rörs bara vid omfrysning).
- **Metodregel (dyrast lärdom från vm):** ENDAST marknadspriser får logga flaggor —
  modellhärledda sannolikheter förorenar facitet. Gäller även UI:t: amber-modellen får inte
  ge stödchip eller lyfta ett spelkort till "★ starkast stödd".
- **Statistikregler för facitet:** (1) `oddset_clv_rows()` utan `limit` = hela historiken —
  trunkering ger survivorship; (2) huvudsiffra och KI måste vara SAMMA estimand
  (`avg_close_ev` winsoriserad som KI:t, `avg_close_ev_raw` separat); (3) censurerade
  linjeflyttar räknas (`n_censored`, `resolved_share`) och blockerar grönt om de är
  majoriteten; (4) statusbeslut (candidate/green) körs på förregistrerad kadens
  `EVAL_INTERVAL_H` = 1 vecka — utvärdering varje varv är sekventiell testning.
- Grönt-kriterium v2: ≥ `GREEN_MIN_N` (50) stängda OCH undre bootstrap-KI-gräns > 0
  (kluster per match), per liga/marknad/modellversion. **Grönt beslutas per signalgrupp,
  aldrig per tier/aggregat.**
- Facitets identitet är match + marknad + tecken + normaliserad lina + semantisk
  signalversion. Stäng mot flaggans lina när ett färskt pris finns; annars `linje flyttad`
  utan fabricerat close-EV. Rapporter får aldrig slå ihop eller korsjoina versioner.
- WP5-ledgern (`app/oddset_ledger.py`): alla prediktioner och oflaggade kontroller fryses
  vid T−24 h/T−3 h/T−20 min. Bakfyll aldrig en missad horisont. Endast captures inom
  45/15/10 min timingtolerans bidrar till candidate/green. Primära grupper är sharp × 1X2 ×
  Allsvenskan/Superettan/Eliteserien/OBOS/MLS; övriga kräver BH-FDR 10 %. Candidate är
  sticky; green kräver out-of-time-data. Aggregat får aldrig ändra gruppstatus.
- Versionspolicy: `signal_version` (s-/m-fingeravtryck) grupperar facitet, `git_hash` ger
  reproducerbarhet — docs/UI-commits får inte fragmentera facitet.

## Oddset-delen

- Mönsterkälla: `/Users/saman/vm/backend/app/` (Pinnacle AH/ÖU/hörnor, Kambi-klienten med
  milliodds 1420=1.42 och line 2500=2.5, värdescreen, Dixon-Coles, steam/CLV/notify, ClubElo).
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
förra. AWS Lightsail Stockholm är avfärdat som serverplats (Sofascore 403 på alla
modellvägar) — se `docs/serverfragan-avslutad-2026-08-11.md`.

**Miljöanteckning:** behörighetsklassaren blockerar skript som söker tokens i
JS-buntar (det läser som token-skörd) även när gränsen tillåter det. Behövs det
måste Saman lägga in en Bash-behörighetsregel — se `docs/live-kallor-2026-07-25.md`.

- Tier-regel för tips: **sharp-ankrat = actionable (grönt, in i CLV); modell-utan-sharp =
  amber (bakom toggle, UR CLV)** — vm bevisade tre gånger att modell-edges utan sharp-ankare
  blir systematiskt uppblåsta.
- Metodregler från granskningen 2026-07-13/16: asiatiska sannolikheter alltid
  settlement-aware (push/half-win) även i ankring; notiser kräver närvaro-bekräftat bokpris;
  alla prediktioner loggas vid fasta horisonter med modellversion — flaggor är urval för
  handling, inte utvärderingsunderlag.
- **DB-ändringar = skript + backup + rapport** (`docs/db-atgarder.md`) — aldrig ad-hoc-SQL.
  Kopiera aldrig en aktiv SQLite-fil med filkopiering — använd `.backup`.
- Odds-eventidentitet: minsta laglikhet 0,55 på BÅDA sidor och parscore ≥0,75.
  `pinnacle_id`/`kambi_id` är write-once, globalt unika och får aldrig bytas via fuzzy.
  Samtidiga prisvarianter eller id-krock ger `data_conflict`: visa råodds diagnostiskt men
  stoppa värde, steam, modell, ledger, CLV och notiser (`docs/oddset-identitetsaudit-2026-07-26.md`).
- Resultatidentitet: fuzzy auto-merge kräver >0,75 och ALLA sådana länkar ska synas i
  `cli.py modeldata` tills de flyttats till `TEAM_ALIAS`/meta. 0,55–0,75 mergas aldrig.
  Kända falska par i `TEAM_REJECTED_LINKS`.
- Frånvaro: `oddset_absence_capture` + `oddset_absence_player` är PIT-historiken; capture
  skrivs även för en lyckad tom lista. ClubElo: `oddset_elo_capture`/`_rating` är
  observerade dagrankingar, `oddset_elo_history` providerintervall för `as_of`-läsning —
  retroanalys får aldrig använda dagens ranking; timeout/502 ska förbli retrybart.

## UI-konventioner

- Designsystemet: 13px bas, sektioner är kort (`section` = --panel, inre ytor = --panel2),
  pill-tabbar i kompakt header, EN statusrad. Bred skärm (≥1280px): sektionspar i `.cols`-grid.
- Mobil: ALLT i `@media (max-width:760px)` — desktop får inte ändras. OBS:
  `td:first-child`-regler måste exkludera `.chartrow`.
- Alla GET-fetch: `cache:'no-store'` + `&_t=${Date.now()}` (annars cachar webbläsare/iOS).
- Tillstånd sparas i `localStorage` (`svs_state`); bootstrap återställer. Omladdning
  börjar alltid i Idag (återinför inte `svs_v3_view`).
- Inga `cursor: help`-frågetecken; förklaringar som title-tooltips.
- Oddset-delen: röd = oddset NER (ökad vinstchans), grön = UPP (vm-konvention).
- **Idag** är en lätt översikt: `/api/dashboard/oddset`, `/api/oddset/predictions/summary`
  och `/api/pool/played?live=false` — aldrig de fulla rapporterna. Idag startar inget
  nätarbete de första 650 ms; sekundära kort väntar 1 200 ms; timers och requests rensas
  vid vybyte. Driftlarm (pool, V2.2, Oddset-tystnad) visas överst på Idag.
- **Oddset** laddar progressivt: `/api/oddset/matches?light=true&compact=true&movement=false&limit=40`
  först, hela `compact=true`-listan efter 1,2 s; råa `pts` bara för öppnad match via
  `/api/oddset/movement`. 40 matcher renderas åt gången. Återinför inte all historik i
  första svaret. Oddset har FEM persisterade sub-tabbar med antalen på flikarna.
  Matcher-fliken har TVÅ persisterade filter — Dölj/Visa startade och **Dölj/Visa utan
  odds** (PÅ som standard, `PLAYABLE_BOOKS`) — och INGET av dem får filtrera Live eller
  signalflikarna. Filtret är RENT VISUELLT: insamlingen fortsätter. Signalgruppsfacit och
  signallogg hör hemma i Labb, aldrig som en femte Oddset-sektion.
- **🏋 Lagstyrka** visar `att`/`def` ur samma `fit_league` som prognoserna (aldrig en
  parallell skattning). `season_of()` på `FD_SEASON_CODES` avgör säsongsetikett —
  återanvänd den. `#` är styrkerank, INTE tabellplacering. Visningsnamn väljs bland RÅA
  namn (diakriter först) — exakt normaliserad nyckel, aldrig fuzzy. Allt AMBER.
- Jämförbara listor använder EN `SortableTable` (`src/components/`): rubrikklick på
  desktop, sortval + samma kortordning på mobil. `limit` kapar EFTER sorteringen — slicea
  aldrig `rows` före anropet. Skapa aldrig tabbspecifika kopior.
- **YTGRÄNSEN: Historik = 100 % POOL, Labb = 100 % ODDS.** Sammanhörande data får inte
  spridas över två vyer. Historik har EN produktväljare överst som styr hela sidan.
  Poolens styrkemodell-shadow ligger i Historik → Poolmodell, aldrig i Labb.
- Långa tabeller visar 20 rader med "visa alla". Ingen parameter göms i en nyckelsträng:
  budget, strategi och värdevikt är egna kolumner. Horisonter visas i minuter (180/20),
  aldrig som `h3`/`m20`.
- Labb äger validering och fulla loggar; öppet läge visar bara AKTIVA versioner
  (aktiv-markeringen kommer från respektive systems eget fingeravtryck — value-loggens
  och ledgerns `s-`-namnrymder är OLIKA och får aldrig korsjämföras). ROI/KI visas aldrig
  under `ROI_MIN_N` (=10). Stora loggar visas stegvis (200 rader).
- Spelade kuponger: `PlayedPanel` hämtar i TRE steg (`live=false` → `live=true&chance=false`
  → fullt svar); livebilden är single-flight (20 s) och ett sent svar får inte skriva över
  en nyare uppdatering.

## Regler

- **Lägg ALDRIG spel automatiskt** — bara deep-link/fil; användaren laddar upp och betalar själv.
- Klicka inte i cookie-/samtyckesrutor åt användaren.
- **Committa färdigt arbete utan att fråga** (Samans stående order 2026-08-11 —
  den ersätter den gamla regeln "committa endast på begäran"). Fråga alltså inte
  om lov varje gång. Villkoren är oförändrade: committa BARA filer du själv
  ändrat, aldrig `git add .`, aldrig `backend/data/` och aldrig hemligheter, och
  rör inte andras ocommittade ändringar i arbetskatalogen. Commit-meddelanden på
  svenska, imperativ rubrik, avsluta med `Co-Authored-By: Claude <modell>`.
  Pusha genom hooken; `SKIP_KONTROLL=1` bara för rena dokumentationspushar.
- API-nycklar i gitignore:ad `backend/.env` (ODDS_API_KEY finns, the-odds-api är vilande).
- Rör ALDRIG `/Users/saman/svs` eller `/Users/saman/vm` från detta projekt.
- **Uppdatera STATUS-blocket i `docs/plan.md` när en etapp/delmål blir klar — skriv över,
  stapla inte;** flytta det gamla blocket överst i `docs/status-historik.md`.
- En agent i taget i serverns arbetskatalog. Kör aldrig samma datainsamlare samtidigt på
  två datorer (`docs/AI-OVERLAMNING-SERVER.md`).
- Kör `cli.py gater` innan ett nytt shadow-spår startas: skörda det som är moget först.
