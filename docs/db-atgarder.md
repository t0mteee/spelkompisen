# Databas-åtgärder (löpande logg)

**Processregel (granskningen runda 2, punkt 7):** varje manuell ändring av
`data/stryktips.db` sker via (1) backup i `backend/data/backups/`, (2) skript
eller dokumenterad SQL i repot, (3) post i denna fil. Ad-hoc-SQL utan spår är
förbjudet. Automatisk upptäckt av kända felmönster: `cli.py modeldata`
(identitets-audit: okopplade namn, datum-dubbletter med olika mål).

---

## 2026-07-24 — PH2/PH3 v2: presence, proveniens och kontrafaktiskt facit

- **Skript:** `backend/scripts/migrera_pool_capture_v2.py` (additivt,
  idempotent, testat med dubbelkörning). Full metodrapport:
  `docs/pool-pit-v2-2026-07-24.md`.
- **Backup:** `backend/data/backups/stryktips-2026-07-24-fore-pool-capture-v2.db`
  (69 MB SQLite online-backup före schemaändringen, SHA-256
  `abb0a6577dc6b91a05ec276573890a88350e50bd519e670ae48a552666d4403e`).
- **Schema:** ny `pool_market_capture`; jackpotproveniens i
  `pool_draw_snapshot`/`pool_system_ledger`; timingpolicy och källeligibility
  i PIT-tabellerna; publicerad vinst, payout-completeness och
  settlementversion i systemledgern.
- **Radbevarande:** före/efter oförändrat:
  `pool_draw_snapshot=109`, `pool_pit_draw_features=256`,
  `pool_pit_match_features=2333`, `pool_system_ledger=0`.
  `pit-v1` skrevs inte om och får inte användas som presence-bevis.
- **Första livevarv:** 212 capture-rader (SvS 106 matched; Pinnacle 95 matched
  + 11 not_listed). Jackpot: 2 `verified_endpoint`, 10 `missing`; 109 äldre
  värderader märkta `legacy_unverified`. `pit-v2=0` efter varvet eftersom
  ingen passerad horisont hade en capture före cutoff — korrekt no-backfill.
- **Kontroll:** `PRAGMA integrity_check = ok`; 163 backendtester gröna.

## 2026-07-24 — PH2/PH3: PIT-dataset och systemledger för poolspelen

> Historisk v1-post. Timing byggde på förändringspunkter och systemfacitet
> försummade egen utspädning. Båda semantikerna ersätts av v2-posten ovan.

- **Skript:** `backend/scripts/migrera_pool_pit_ph23.py` (backup + fyra
  tabeller) och `backend/scripts/bygg_pit_dataset.py` (idempotent helsvep).
  Moduler: `backend/app/pool_dataset.py` (features, `FEATURE_VERSION=pit-v1`)
  och `backend/app/pool_system_ledger.py` (frysning/settling). 11 unittest i
  `backend/tests/test_pool_pit.py`.
- **Backup:** `backend/data/backups/stryktips-2026-07-24-fore-ph23-pit.db`.
- **Nya tabeller:** `pool_draw_snapshot` (framåtriktad omsättnings-/
  jackpottserie — skrivs av varje snapshotvarv vid förändring),
  `pool_pit_draw_features` + `pool_pit_match_features` (frysta features per
  omgång/horisont, ENBART observed_pit — horisont utan observation byggs
  aldrig; devigade sannolikheter, first→as-of-rörelser i pp, streck, gap,
  reversal, entropi/favorittryck, laggar, coverage) samt `pool_system_ledger`
  (byggarens konkreta rader frysta före spelstopp + facit).
- **Helsvepet:** 98 observerade omgångar → **256 horisontrader** (h24/h3/m20
  där observation fanns; streck-täckning 100 %, sharp ~85–95 %).
- **Förregistrerad benchmarkmatris (ändra aldrig befintliga nycklar):**
  `ev50-medel-vw50` (PRIMÄR), `ev50-tuff-vw80`, `ev256-medel-vw50` —
  Värderader via samma motor som UI:t, frysta vid T−3 h (tolerans 30 min,
  varvkadens) och T−20 min (tolerans 10 min, tätläge). Sena frysningar
  sparas med `timely=0`. Settling mot `pool_draw_settlement`s riktiga
  utfall + faktiska utdelningsnivåer (egen-vinst-utspädning försummad,
  noterad i settle_note). Bomben ingår inte (egen kolumnbyggare).
- **Läs-API:** `/api/pool/systems` (champion-baselinens läge). Första
  frysningen sker automatiskt när nästa omgång går in i sitt T−3h-fönster.

## 2026-07-24 — PH1: immutable settlementlager för poolspelen

- **Skript:** `backend/scripts/migrera_pool_settlement.py` (backup + fyra nya
  tabeller, ingen data) och `backend/scripts/backfill_pool_settlement.py`
  (idempotent, resumable API-backfill, 0,35 s throttling, GAP_STOP=25 för
  permanenta gränser). Modul: `backend/app/pool_settlement.py`; schema i
  `POOL_SETTLEMENT_SCHEMA` (storage.py). Design + testfall granskade i
  `docs/ph1-settlement-schema-forslag-2026-07-24.md`; 10 unittest i
  `backend/tests/test_pool_settlement.py`.
- **Backup:** `backend/data/backups/stryktips-2026-07-24-fore-ph1-settlement.db`
  (tagen före tabellskapandet; backfillen är append-once i de nya tabellerna
  och rör inga befintliga).
- **Nya tabeller:** `pool_draw_settlement` (kanonrad per omgång med
  payload-hash + källversion), `pool_event_settlement` (utfall, cancelled,
  slutstreck, rått startOdds med NULL-provenance), `pool_payout_tier`
  (vinnare + belopp per nivå), `pool_backfill_log` (journal: ok/http_404/
  not_finalized/incomplete_result/divergence/error — gör allt retrybart).
- **Regler:** första lyckade läsningen är kanon; avvikande omhämtning loggas
  som `divergence` och skriver aldrig över. `final_only`-kohorten får aldrig
  påstås ha rörelser. Slug är identiteten (topptipsvarianterna separata).
  `startOdds` är spärrat för analys tills providersemantiken verifierats.
- **Framåtriktat:** `cli.py`-snapshotvarvet settlar nyss avgjorda omgångar
  via `pool_settlement.settle_recent` (budgeterat, tyst, retryfönster 6 h).
- **Backfill-resultat (slutfört 2026-07-24, två resumable körningar):**
  **8 278 omgångar totalt**, alla fem produkter tillbaka till **januari 2013**
  (= API:ts arkivhorisont — mycket djupare än PH0-sonderingens golv):
  Stryktipset 696 (#4267–#4962), Europatipset 1 370 (#1221–#2592),
  Topptipset 4 145 (#78–#4224), Topptipset Extra 1 371 (#481–#1851),
  Topptipset Stryk 696 (#273–#972). 76 554 event-facit och 14 476
  utdelningsnivåer. Journal: 8 278 ok, 131 http_404 (gränser/luckor),
  26 not_finalized (öppna/kommande — settlas av snapshotvarvet), 0 fel,
  0 divergenser. Ingen 429 under hela körningen (~17 000 requests, 0,35 s).
  PH0-golven i backfillskriptet var alltså konservativa — verkliga gränser
  hittades via GAP_STOP-serien precis som designat.
- **Läs-API:** `/api/pool/history` (lista + `draw`-detalj) driver v3-UI:ts
  Historik-vy. Enbart läsning.

## 2026-07-23 — V2.2 flerligedata och research-matchidentitet

- **Skript:** `backend/scripts/forbered_v22_multiliga.py` (idempotent
  resultat-/Elo-/WP9c-/oddsförberedelse),
  `backend/scripts/migrera_v22_research_identitet.py` (snäv
  placeholdertidsmigration) och read-only
  `backend/scripts/auditera_v22_multiliga.py`.
- **Backuper:**
  `backend/data/backups/stryktips-2026-07-23-fore-v22-multiliga.db` före första
  europeiska dataraden och
  `backend/data/backups/stryktips-2026-07-23-fore-v22-research-identitet.db`
  före matchidentitetsmigrationen.
- **Resultatdata:** 2 892 toppligerader (Premier League/Serie A/La Liga/
  Bundesliga) och 3 400 fit-only-rader (Championship/Serie B/Segunda/
  2. Bundesliga), 2024/25–2025/26. Dagens ClubElo-capture utökades med
  ENG/ITA/ESP/GER; providerintervall förlängdes aldrig manuellt.
- **WP9c:** 78 ligalag, 78 arenor med koordinat och 3 441 relevanta lag-event.
  Sofascore saknade koordinat för Brighton venue 2443; explicit
  OpenStreetMap/Nominatim way 28537290-override lades i den versionerade
  WP9c-policyn och samma förberedelseskript reparerade exakt lag 30.
- **Oddsidentitet:** första källvarvet hittade 39 matcher hos både Pinnacle och
  Kambi. Kambis gemensamma placeholdertider skapade 20 rena dubbla
  matchidentiteter (Serie A 10, La Liga 7, Bundesliga 3). Migrationen krävde
  entydigt hemma-/bortalagpar, vägrade rader med facit/features, flyttade
  Kambi-ID/oddshistorik till Pinnacle-raden och behöll Pinnacles avspark. 20
  sammanslagna, 0 rena Kambi-rader kvar, `integrity_check = ok`. Framtida
  researchinsamling har samma team-only-skydd.
- **Readiness:** 38/39 aktuella matcher kompletta. Enda missing är
  Bayern–Stuttgart eftersom ClubElo saknar giltigt 2026-07-23-intervall för
  båda; raden faller till sharp-identitet utan påhittad Elo.

## 2026-07-23 — V2.2 isolerad shadowledger

- **Skript:** `backend/scripts/migrera_v22_shadow.py` (idempotent, additivt
  schema och SQLite online-backup).
- **Säkerhetsbackup:**
  `backend/data/backups/stryktips-2026-07-23-fore-v22-tomtabell-stadning.db`.
  En första read-only-audit öppnade `Storage`, vars grundschema hann skapa den
  nya tabellen tom före migrationskörningen. Skriptet verifierade exakt 0 rader,
  tog säkerhetsbackupen och tog bort just den tomma förhandskopian.
- **Före-migrationsbackup:**
  `backend/data/backups/stryktips-2026-07-23-fore-v22-shadow.db`, skapad efter
  den verifierade tomtabellstädningen och före den avsedda migrationen.
- **Vad:** `oddset_v22_shadow_capture` är ett separat forskningslager per match
  × fast horisont × fryst shadowversion. Det sparar sharp-kontroll,
  V2.2-kontroll, eligibility, fallbackorsak, featurehash och källversioner men
  läses aldrig av värde, notiser, CLV eller ordinarie UI.
- **Första status:** migrationen skapade tabell + index med 0 rader;
  `integrity_check = ok`. Ingen gammal horisont bakfylldes. Första livecapture
  sker automatiskt när ledgern når en ny T−24 h/T−3 h/T−20 min-horisont efter
  manifestets frystid.

## 2026-07-20 — Alt-linjelager för sharpens parmarknader

- **Schema:** additiv tabell `oddset_sharp_alt` (skapas idempotent via `_SCHEMA`;
  dedup per match × marknad × linje × tecken, `last_seen_at`/`available` med
  samma närvarosemantik som `oddset_odds`).
- **Backup:** `backend/data/backups/stryktips-2026-07-20-fore-altlinjer.db`.
- **Varför:** samma-linje-regeln dödade 67 % av AH- och ~40 % av Ö/U-
  jämförelserna (mätt på 7 dygns matcher: AH samma linje 33 %, Ö/U 59 %,
  hörnor 60 %) — Pinnacles alternativa linjer fanns redan i samma API-svar men
  slängdes i parsningen. Ingen ny HTTP-trafik.
- **Första varvet:** 1 238 rader över 38 matcher (AH 280 match-linjer, Ö/U 307,
  hörnor 20). Värdejämförelser direkt: Ö/U 66 poster (28 via alt-linje),
  AH 38 (12), hörnor 6 (2). Sharp-versionen byts till `s-776ca0e0`
  (`alt_lines: True` i SHARP_PARAMS) så facitet delas rent.
- **Stängning:** `closing_snapshot` läser alt-lagret när huvudlinan flyttat —
  exakt-line-close i stället för "linje flyttad" där alt-linjen fanns färsk.
- **Tester:** `tests/test_alt_lines.py` (5 fall: dedup/plockning, historikpunkt,
  alt-värde, stale-alt avvisas, alt-stängning). Sviten: 112/112.

## 2026-07-17 — WP9c lagmatcher i alla tävlingar

- **Skript:** `backend/scripts/migrera_team_events.py` (idempotent, additiva
  tabeller/index och konsistent SQLite-backup innan första migration).
- **Backup:** `backend/data/backups/stryktips-2026-07-17-fore-wp9c.db`, skapad
  innan de fyra tabellerna fanns; `integrity_check = ok`.
- **Vad:** `oddset_sofa_team` + scope sparar providerlag och basarena;
  `oddset_sofa_team_event_capture` sparar lyckade, policyversionerade svar även
  när eventlistan är tom; `oddset_sofa_team_event` deduplicerar provider-event
  och bevarar första/senaste observation. PIT-läsning kräver att eventet både
  spelats och observerats före `as_of`.
- **Första backfill:** 94 lag och 94 captures, 5 533 lag-eventposter → 3 329
  unika matcher i 24 tävlingar. 94/94 lag har arenakoordinater. Den felaktiga
  gamla OBOS-säsongscachen 97377 förkastades; korrekt fotbollssäsong 87867/UT 22
  gav 16 lag och 687 relevanta event.
- **Verifiering:** alla 48 kommande källligamatcher fick komplett exakt/
  aliasverifierad identitet, vila, belastning och reseproxy. Inga gamla
  `first_seen_at` fabricerades; backfillen är användbar först framåt.
  Slutlig `integrity_check = ok`. Metodrapport:
  `docs/wp9c-team-events-2026-07-17.md`.

## 2026-07-17 — Modell v2-A point-in-time-features

- **Skript:** `backend/scripts/migrera_v2_features.py` (idempotent, additiv
  tabell/index, kräver namngiven backup).
- **Backup:** `backend/data/backups/stryktips-2026-07-17-fore-v2a.db`, skapad
  med SQLite online-backup före migrationen; `integrity_check = ok`.
- **Vad:** `oddset_v2_feature_capture` fryser kanoniskt JSON + SHA-256 per match
  × fast horisont × modellversion × featureversion. Payloaden innehåller
  resultat/xG-inputhash och cutoff, PIT-Elo-intervall, råa features,
  saknas-flaggor samt öppet redovisad lagidentitet.
- **Migration:** tabellen skapades tom, inga historiska värden fabricerades.
  Därefter skapades 6 uttryckligt `reconstructed` featurecaptures för att testa
  pipeline på de 4 redan ledgerförda V2-ligamatcherna. De är kodmässigt spärrade
  från promotion; framtida prediction-captures skriver `live` automatiskt.
  24 rekonstruerade rader från fyra semantiska utvecklingsversioner skapade före
  slutversionen rensades explicit av samma skript; kvar är exakt 6 aktuella.
- **Verifiering:** aktuell featureversion `f-7ce587c1`; 5 dataset-rader/4 matcher,
  0 post-kickoff-/featureläckor, 0 match-horisontdubbletter, identitetsmodellens
  max `|Δp| = 2,78e−17`; slutlig `integrity_check = ok`.

## 2026-07-16 — WP8 dagliga Elo-captures och PIT-historik

- **Skript:** `backend/scripts/migrera_elohistorik.py` (additivt schema,
  legacy endast när capture-tabellen är tom, idempotent) och
  `backend/scripts/backfill_elohistorik.py` (återupptagningsbar klubbbackfill;
  lyckat nätanrop krävs innan en klubb markeras klar).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp8-elo.db`
  (18 MB SQLite online-backup, `integrity_check = ok`, 0 Elo-tabeller före
  migrationen).
- **Vad:** `oddset_elo_capture` + `oddset_elo_rating` bevarar observerade
  dagrankingar och payload-hash. `oddset_elo_history` bevarar ClubElos
  inkluderande `From`/`To`-intervall; `get_elo(..., as_of=datum)` läser enbart
  intervallet som gällde den dagen. Meta-rankingen är kompatibilitetscache.
- **Migration:** befintlig meta-ranking → 1 legacy-capture + 32 ratings.
  Identisk omkörning 0/0. En verifieringskörning efter att meta flyttats hittade
  och rensade 1 sekundnära redundant legacy/daily-capture från en tidig
  skriptversion; nästa körning rensade 0 och skapade 0. Kvar: 1 legacy, 2
  backfill-ankare och 1 daily-capture (128 ratings totalt).
- **Backfill:** rankningar 2024-07-01, 2025-07-01 och 2026-07-16 gav 39 unika
  klubbar. Full klubbhistorik lyckades för 36; tillsammans med ankarintervallen
  finns 4 197 intervall för alla 39 klubbnycklar. KFUM Oslo, Odd Grenland och
  Sirius har bara 1–3 ankarintervall eftersom fulla endpoints timeoutade; deras
  `oddset_elo_backfill:*`-markörer saknas avsiktligt så nästa körning retryar.
- **Täckning:** med samma namnmatchning som modellen får 507/581 Allsvenskan-
  matcher och 483/587 Eliteserien-matcher båda lagens as-of-Elo. Superettan
  19/600 och OBOS 11/600 — ett dokumenterat skäl att inte behandla Elo som
  heltäckande feature i andradivisionerna. Slutlig `integrity_check = ok`.

## 2026-07-16 — WP8 tidsstämplad frånvarohistorik

- **Skript:** `backend/scripts/migrera_franvarohistorik.py` (idempotent,
  additiva tabeller/index, legacy-backfill utan påhittade identiteter).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp8-franvaro.db`
  (18 MB SQLite online-backup, `integrity_check = ok`, tagen innan tabellerna
  fanns och innan backenden startades med ny kod).
- **Vad:** `oddset_absence_capture` sparar varje lyckat lineup-svar, även tom
  frånvarolista, med match/event/tid/bekräftelsestatus och payload-hash.
  `oddset_absence_player` sparar sida, Sofascore player-ID, position, orsakskod,
  beskrivning/slutdatum samt säsongsmatcher/rating. Detta gör frånvaron point-in-
  time och möjlig att koppla till samma matchs oddshistorik.
- **Backfill:** 15 befintliga `meta oddset_abs:*` → 15 legacy-captures och 77
  spelarrader. Gamla payloads saknade ID/position; dessa lämnades NULL i stället
  för att fyllas med namnmatchade gissningar. Identisk omkörning gav 0/0.
- **Första livevarv:** 16 matcher kontrollerades, 14 hade lineup-svar och gav
  14 nya captures + 75 spelarrader; **75/75 hade både provider-ID och position**.
  Två källsvar saknades och skapade ingen falsk tom-observation. Totalt efter
  varvet: 29 captures, 152 spelarrader, 15 matcher; `integrity_check = ok`.
- **Källkorrigering:** råfälten verifierades mot Sofascore-lineups. Kod 0 =
  annat; 1 = skada; 11/12/13 = kortavstängningar (tidigare visades 11 felaktigt
  som "annat"). Rå `description` lagras också för framtida omklassning.

## 2026-07-16 — WP5 prediction ledger

- **Skript:** `backend/scripts/migrera_prediction_ledger.py` (idempotent,
  kräver backup; enbart additiva tabeller/index).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp5.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** skapade `oddset_prediction_capture`, `oddset_prediction_log` och
  `oddset_prediction_group_state`. Capture är unik per match × horisont × tier
  × semantisk kompositversion och skrivs även vid noll prediktionsrader;
  ledgerrader är immutabla point-in-time-observationer.
- **Migrering:** 0 gamla rader bakfylldes (avsiktligt — historiska odds kan inte
  göras om till äkta T−24h/T−3h/T−20m-snapshots),
  `PRAGMA integrity_check = ok`.
- **Kopietest före live:** 58 aktuella matcher gav 30 tier-captures och 220
  prediktioner (8 captures i 3h-bucket, 22 i 24h-bucket); identisk omkörning
  gav 0 captures/0 rader. Dessa kopierader är testdata och finns inte i
  produktionsdatabasen.
- **Första live-capture:** launchd skrev 30 tier-captures/220 prediktioner
  2026-07-16 13:30:07Z. Timingvakten godkände 4/13 3h-captures och 0/17
  bootstrap-24h-captures; sena rader finns kvar för coverage men kan inte
  kvalificera en grupp. 220/220 prediktionsidentiteter är unika.
- **Staging-race, metadata-only:** launchd hann köra fem minuter innan commit
  `4cd0bb0` skapades och `_code_version()` skrev därför föräldrahashen
  `6156f74`, trots att det exekverade WP5-trädet var exakt det staged träd som
  blev `4cd0bb0`. `backend/scripts/korrigera_wp5_githash.py` verifierar HEAD,
  diff på alla kärnfiler, exakt capture-tid och exakt 220 rader innan den ändrar
  enbart `git_hash`. Separat backup:
  `backend/data/backups/stryktips-2026-07-16-fore-wp5-githash.db`.
  Utfall: 220 rader `6156f74→4cd0bb0`, `integrity_check = ok`.

## 2026-07-16 — WP4 CLV-identitet och linjeflytt

- **Skript:** `backend/scripts/migrera_clv_identitet.py` (idempotent, kräver
  backup och recreatar tabellen atomärt).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp4.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** primärnyckeln byttes från `(match_id, market, sign)` till
  `(match_id, market, sign, line_key, model_version)`. `line_key` är
  `round(line×1000)`; marknader utan lina använder sentinel `2147483647`.
  Closing-facitet fick `closing_line`, `line_delta` och `line_move_score`, där
  positivt score betyder att marknaden rörde sig med selektionen.
- **Migrering:** 110→110 rader, 110 unika nya identiteter,
  `PRAGMA integrity_check = ok`. En tidigare censurerad Ö3,25-rad
  (Djurgården–Halmstad) öppnades för omkörning och klassades mot slutlinan
  3,50 som `linje flyttad`, delta/score `+0,25`; inget close-EV skapades eftersom
  exakt-line-priset inte var färskt nog.
- **Efterkontroll:** produktionen accepterade 41 nya version/lina-identiteter
  (totalt 151/151 unika rader) som den gamla nyckeln hade blockerat. Rapporten
  visar linjeflytten separat från de 16 jämförbara close-EV-raderna.

## 2026-07-16 — WP2 prisnärvaro och källhälsa

- **Skript:** `backend/scripts/migrera_prisnarvaro.py` (idempotent, kräver backup).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp2.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** `oddset_odds` fick `last_seen_at` och `available`; befintliga 16 400
  rader backfillades konservativt med `last_seen_at=fetched_at`, `available=1`.
  Tabellen `oddset_source_health` skapades. Inga prisrader raderades eller
  skrevs om. `PRAGMA integrity_check = ok`, 0 NULL efter migrering.
- **Efterkontroll:** ett fullt live-varv gav 27 källhälsorader utan fel,
  349/349 aktuellt visade marknader färska och 72 nya prisförändringsrader
  (16 400→16 472). Notifiering var avstängd; 0 pushar.

## 2026-07-16 — Versionsmigration av signal-facitet

- **Skript:** `backend/scripts/migrera_signalversion.py` (idempotent, kräver backup).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-versionsmigration.db`.
- **Vad:** `model_version` bytte betydelse från git-hash till semantiskt
  signal-fingeravtryck (`s-`/`m-`-prefix per tier); git-hashen flyttades till nya
  kolumnen `git_hash`. Rader stämplade `5cfe78f` (43 st: 19 sharp → `s-c32b7065`,
  24 modell → `m-8bf25277`) loggades under exakt de parametrar dagens
  fingeravtryck beskriver (ingen algoritm-/parameter-/kalibrerings-/dataändring
  sedan ffc6d04) → infogade i nuvarande version utan regimblandning.
  66 rader med NULL (loggade före versionsstämpling OCH före identitetsfixen =
  annan dataregim) lämnades som legacy (`-`).

## 2026-07-13 — Sanering av straff-kontaminerade MLS-resultat

- **Upptäckt:** identitetsmergens målvakt (b11a7e8) flaggade Montreal–Atlanta
  som "olika mål — mergas ej"; skanning visade ett kluster av slutspelsrader
  där Sofascores `current`-score inkluderade straffläggning. **Rotorsaksfix:**
  `_ingest_event` läser nu `normaltime` (fallback `current`).
- **Backup:** `backend/data/backups/stryktips-2026-07-13-fore-sanering.db`
  (tagen som analys-kopia FÖRE åtgärden; flyttad hit 2026-07-16).
- **Urvalsregel:** sofa-rad med fd-motpart ±1 dygn och avvikande mål ⇒ rätta
  till fd (officiellt FT-resultat); utan fd-motpart men hg+ag ≥ 9 och datum
  okt–dec (MLS-slutspel) ⇒ radera (bevisligt straff-kontaminerad, facit saknas).
- **Berörda rader** (alla `league='mls'`, `source='sofa'`; PK = league+date+home+away):

| Åtgärd | date | home | away | före | efter |
|---|---|---|---|---|---|
| UPDATE | 2024-10-22 | montreal | atlanta united | 6-7 | 2-2 (fd 2024-10-23) |
| DELETE | 2024-10-29 | seattle sounders | houston dynamo | 5-4 | — |
| DELETE | 2024-10-30 | real salt lake | minnesota united | 4-5 | — |
| DELETE | 2024-11-03 | houston dynamo | seattle sounders | 7-8 | — |
| DELETE | 2024-11-03 | new york red bulls | columbus crew | 7-6 | — |
| DELETE | 2024-11-09 | cincinnati | new york city | 5-6 | — |
| DELETE | 2025-10-26 | philadelphia union | chicago fire | 6-4 | — |
| DELETE | 2025-11-01 | new york city | charlotte | 6-7 | — |
| DELETE | 2025-11-02 | portland timbers | san diego | 5-4 | — |
| DELETE | 2025-11-08 | minnesota united | seattle sounders | 10-9 | — |
| DELETE | 2025-11-23 | vancouver whitecaps | los angeles | 6-5 | — |

- **Reproducerbar SQL** (mot backupen ger exakt dagens läge):

```sql
UPDATE oddset_results SET hg=2, ag=2
 WHERE league='mls' AND source='sofa' AND date='2024-10-22'
   AND home='montreal' AND away='atlanta united';
DELETE FROM oddset_results
 WHERE league='mls' AND source='sofa' AND hg+ag>=9
   AND strftime('%m', date) IN ('10','11','12')
   AND (date, home, away) IN (VALUES
   ('2024-10-29','seattle sounders','houston dynamo'),
   ('2024-10-30','real salt lake','minnesota united'),
   ('2024-11-03','houston dynamo','seattle sounders'),
   ('2024-11-03','new york red bulls','columbus crew'),
   ('2024-11-09','cincinnati','new york city'),
   ('2025-10-26','philadelphia union','chicago fire'),
   ('2025-11-01','new york city','charlotte'),
   ('2025-11-02','portland timbers','san diego'),
   ('2025-11-08','minnesota united','seattle sounders'),
   ('2025-11-23','vancouver whitecaps','los angeles'));
```

- **Anmärkning (processavvikelse):** saneringen kördes 2026-07-13 som direkta
  SQL-satser i sessionen — skript/backup-i-repo fanns inte då. Denna fil +
  processregeln är åtgärden; framtida saneringar följer regeln från start.
- **Kvarvarande osäkerhet:** Superettan 2025-11-23 örebro–hammarby talang 7-4
  och Eliteserien 2025-11-30 kongsvinger–aalesunds 4-5 är kvalmatcher utan
  fd-motpart — kan inte verifieras, lämnade orörda (normaltime-fixen skyddar
  framåt).
## 2026-07-25 — Live-radarns observationslager

- **Skript:** `backend/scripts/migrera_live_radar.py` (additivt och
  idempotent; SQLite-backup före migration).
- **Backup:**
  `backend/data/backups/stryktips-2026-07-25-fore-live-radar.db`.
- **Vad:** skapade `oddset_live_capture` med 26 kolumner och index för
  femminuterssnapshots av observerad live-xG/chansstatistik. Tabellen lagrar
  råa källobservationer, aldrig spelrekommendationer.
- **Migration:** 0→0 rader, `PRAGMA integrity_check = ok`.
- **Efterkontroll:** första källprovet skrev 5 utvecklingsrader som
  `sofa-live-v1`. Scope-rättningen begränsade globala träningsmatcher till
  matcher som redan finns i Oddset och bumpade aktuell version till
  `sofa-live-v2`; första v2-provet skrev 2 matchcaptures. V1-raderna är
  auditerbara men filtreras ur API och utvärdering.

---

## 2026-07-25 — Rensning av ankarflaggor i CLV-facitet

- **Skript:** `backend/scripts/rensa_ankarflaggor.py` (torrkörning som default,
  `--kor` utför; idempotent — andra körningen raderar 0 rader).
- **Backup:** `backend/data/backups/stryktips-2026-07-25-fore-ankarrensning.db`.
- **Orsak:** Smarkets kopplades in 2026-07-24 som sharp-ANKARE och lades
  medvetet utanför `BOOKS`. Men `oddset_value.attach_value` byggde sin
  boklista som "allt utom pinnacle" — `BOOKS` styr insamlingen, inte
  värderingen. Börspriserna behandlades därför som en mjuk bok att hitta
  värde hos.
- **Omfattning:** 192 av 902 rader i `oddset_value_log` (varav 11 redan
  stängda) hade `book='smarkets'` — 133 i tunna träningsmatcher, snitt-edge
  13,2 % mot Svenska Spels 6,0 %. Raderna mätte ankaroenighet och
  bid-ask-spread, inte felprissättning.
- **Utfall:** 192 raderade, 710 kvar, `integrity_check = ok`. CLV-facitet
  tillbaka på +2,65 % [1,19..4,11] över 147 stängda — samma baslinje som före
  kontamineringen.
- **Spärr framåt:** `oddset_value.ANCHOR_SOURCES`. Se ANKARE ≠ BOK i CLAUDE.md.

---

## 2026-07-25 — Skuggmätning av andra ankaret i CLV-facitet

- **Vad:** fem additiva, nullbara kolumner på `oddset_value_log`:
  `anchor2_source`, `anchor2_fair`, `anchor2_edge`, `anchor2_closing_fair`,
  `anchor2_note`. Ingen befintlig rad ändras, ingen data raderas.
- **Mekanism:** schemat i `storage.py` + `ALTER TABLE`-listan i `Storage.__init__`
  (samma additiva mönster som `book`/`tier`/`model_version`/`git_hash`), inte ett
  separat skript — det finns ingen data att transformera.
- **Backup:** `backend/data/backups/stryktips-2026-07-25-fore-anchor2.db`
  (`VACUUM INTO`, `integrity_check = ok`).
- **OBS om ordningen:** migreringen hann köras av pool-jobbet (var 5:e minut,
  startar en färsk `Storage` och läser `storage.py` från disk) innan backupen
  togs. Additivt och nullbart ⇒ ofarligt, och 737 rader var intakta med
  `first_fair` komplett efteråt. **Lärdom:** en ändring i `storage.py` går live
  vid nästa launchd-tick, inte vid omstart av backend — ta backupen FÖRE
  redigeringen nästa gång, eller lasta ur jobbet under arbetet.
- **Orsak:** devigmetodens val rör ~3 pp medan flaggtröskeln är 2 pp; 11 % av
  selektionerna skiljer mer än hela tröskeln mellan Pinnacle och Smarkets. Utan
  mätning går det inte att säga om +2,65 % är marknadens felprissättning eller
  vårt ankarval. Förregistrerad plan och beslutsregel:
  `docs/tva-ankare-2026-07-25.md`.
- **Runtime:** OFÖRÄNDRAT. `SHARP_PARAMS` och `signal_version` är orörda, samma
  flaggor väljs, samma notiser går. Låst av
  `tests/test_oddset_value.py::AnchorSourceTests` (fem fall, inkl. den tidigare
  otestade ANKARE ≠ BOK-spärren).
- **Efterkontroll:** ett riktigt Oddset-varv 2026-07-25 loggade första mätta
  flaggan — Pinnacle-edge +2,6 % mot Smarkets −0,4 %, oenighet 0,82 pp. Den
  hade alltså inte flaggats med det andra ankaret. Bakfyllning är omöjlig
  (Smarkets-serien börjar 2026-07-24) och de 737 äldre raderna behåller NULL =
  "ej mätt", aldrig "eniga".

---

## 2026-07-25 — pit-v4: nytt forwardexperiment efter falsk frånvaro

- **Vad:** `pool_dataset.FEATURE_VERSION` `pit-v3` → **`pit-v4`**,
  `FEATURE_START_AT` = 2026-07-25T16:00:00Z. Nytt manifest
  `docs/pool-ph4-forward-manifest-v3.json` (`pool-streckmove-v3`).
  **Ingen rad ändras eller raderas.**
- **Orsak:** dubbeltrafikspärren mot Pinnacle returnerade tomma `hits`/`status`
  utan fel, och `record_sharp_capture` skrev då `not_listed` per match. 52 % av
  poolens sharp-ticks 2026-07-25 blev falska frånvaroobservationer (0 % dagen
  före), så `sharp_eligible = 0` kunde betyda "vi frågade inte". Fixen ändrar vad
  flaggan BETYDER — alltså nytt experiment, inte omskriven historik. Samma val som
  v2→v3 gjorde i går. Analys: `docs/m20-och-falsk-franvaro-2026-07-25.md`.
- **pit-v3 lämnas orört** (71 featurerader, `n_eval_draws = 0` — hann aldrig
  forward-scoras). v2-manifestet ligger kvar som historik och skrivs aldrig om.
- **Oförändrat i v3-manifestet:** toleranser (h24=45, h3=45, m20=10),
  featureuppsättningar b–f, primärt mått, bootstrap-metod och seed,
  promotionsgrind. Enda tillägget: `skipped_fetch_is_not_an_observation`.
- **Konsumenter:** `scripts/ph4_ablationer.py` läser v3-manifestet;
  `tests/test_ph4_forward.py` binder runtime-versionen till manifestet (den
  kopplingen fångade bumpen direkt). `tests/test_pool_pit.py` flyttade sin
  NOW-fixtur till 2026-07-27 så även h24-horisonten ligger efter feature-starten
  — att i stället backa `FEATURE_START_AT` hade öppnat för bakfyllning i drift.
- **Efterkontroll:** 239 tester gröna. Första v4-featurerader väntas när nästa
  omgångs h3-fönster öppnas.

## 2026-07-26 — Granskningsfixar F4/F5: kupongfacit, PIT-avsparkstider, wp9c-version

- **Skript:** `backend/scripts/migrera_team_event_start.py`.
  **Backup:** `backend/data/backups/stryktips-2026-07-26-fore-event-start-serie.db`.
- **Ny tabell `oddset_sofa_team_event_start`** (event_id, start_at, seen_at):
  PIT-förändringsserie för avsparkstid. `oddset_sofa_team_event`-upserten
  skriver över `start_at` vid ombokning, så `oddset_sofa_team_fixtures_as_of`
  läste DAGENS tid för historiska `as_of`. Seedad med 6 728 rader
  (`seen_at = first_seen_at`); ombokningar FÖRE migreringen kan inte
  återskapas — för dem gäller nuvarande tid från first_seen_at.
  Integritet: `ok`. **Ingen rad ändras eller raderas.**
- **F5c (drift):** capture-valideringen krävde `finished` medan insamlaren
  sedan 2026-07-25 22:39 skickar även `scheduled`/`inprogress` — varje
  lagcapture med kommande fixtur hade kraschat tyst. TTL:n (20 h, senaste
  captures 2026-07-25T20:26) gjorde att första skarpa försöket låg ~16:26
  2026-07-26; buggen fångades och fixades INNAN dess, så inga captures gick
  förlorade (0 scheduled-event fanns sparade = rotationsriskdatat hade aldrig
  flödat). Verifierat efter fix: force-refresh Allsvenskan gav 16/16 captures,
  757 event varav 150 scheduled, 0 fel.
- **wp9c POLICY schema 3→4** (F5b): statusomfång, forwardvikter och
  starttidsserien fingeravtrycks nu. Det bumpar `policy_version` →
  `feature_version` → V2.2-manifestets `change_policy` kräver nytt manifest:
  `docs/model-v2.2-multileague-forward-manifest-v2.json`
  (experiment `v2.2-wp9c-multileague-v2`, `feature_version` `f22-952e86fe`,
  start 2026-07-26T11:00Z). v1-raderna 2026-07-23→26 ligger kvar som historik
  under gammal shadow-version och blandas aldrig in; de var redan fracturerade
  av den tysta payloadändringen + insamlingsstoppet ovan.
- **Spelade kuponger `played-v2`** (F4): facit tas nu ur
  `pool_event_settlement.outcome` per eventNumber (samma kanon som PH3) i
  stället för draw-payloadens Current-score; `events_order`-join, hård
  breddvakt, struken match = SvS fastställda tecken (aldrig "rätt för alla").
  0 kuponger fanns bokförda — ingen historik påverkad.
- **Efterkontroll:** 292 tester gröna (14 nya regressionsfall: F1 spökpris,
  F2 deep-anropstid, F3 bok-Age, F4 kanonfacit/breddvakt/eventjoin,
  F5 självguard/statusomfång/starttidsserie).
