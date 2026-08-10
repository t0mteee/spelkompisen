# Spelkompisen

Personligt lokalt verktyg som kombinerar **SvS kompisen** (poolspels-analys: Stryktipset,
Europatipset, Topptipset, Bomben) med en ny **Oddset-del**: enskilda matcher (Allsvenskan,
norska Eliteserien, träningsmatcher till att börja med) med sharp-odds, oddsrörelser,
egen modell och värdespels-tips (1X2, asian handicap, över/under, hörnor på sikt).

**Läge (2026-08-09):** Etapp 0–5 KLARA + långt därutöver. Oddset-delen är i full drift:
18 ligor (Allsvenskan/Superettan/Eliteserien/OBOS/Besta deild/MLS/träningsmatcher + CL/EL/
Conference INKL. kval + Premier League/Serie A/La Liga/Bundesliga + danska
Superliga/belgiska Pro League/Primeira Liga/Bolivias Primera División — cuperna är
två Pinnacle-ligor + två Kambi-vägar per nyckel,
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
Allsvenskan + Premier League/Serie A/La Liga/Bundesliga med WP9c
i isolerad sharp-identitetskontroll. **Aktuellt fryst kontrakt är manifest v7**
från 2026-08-10T06:50:39Z:
`docs/model-v2.2-multileague-forward-manifest-v7.json`. V1/v2 är historik;
v3 hann få 0 captures innan ett ofullständigt aliasfingeravtryck upptäcktes
och ersattes; v4 bar 12 rader/2 avgjorda när de fyra Europaligornas
lagnamnsalias utökades inför xG-bakfyllningen; v5 bar 1 rad/0 avgjorda när
ClubElo-identiteten rättades och kalibreringen utökades; v6 bar 19 rader/8
matcher när xG-retryn rättades (`MODEL_DATA_VERSION=5`). En ny kalibrering
räknas som ändrad datagenererande process — `model_source_version` bär
T per liga. Manifestets EGEN `change_policy` kräver då
ett nytt manifest — en aliasändring i en liga som ingår i V2.2:s FIT_POOLS
(inkl. matarligorna Championship/Serie B/Segunda/2. Bundesliga) är en ändrad
datagenererande process. Äldre manifest blandas aldrig in. Det är inte en
tränad modell och får inte påverka tips, notiser eller CLV.
**Aktuell överlämning:**
`docs/overlamning-2026-08-09.md` (LÄS FÖRST) — settlementens omprövningstid,
ensidig träningsmatchslänkning, jackpotläckan mellan produkter, b1024 ur
Topptipset-familjen och det TYSTA bortfallet av Topptipset Dagens (fem dygn
utan insamling). Föregående överlämning
`docs/overlamning-2026-08-07-powerrank.md` gäller nu bara som historik — dess arbete
(radar v6/v7, sharp v8 closing-drift, Europaligorna fullt följda, MLS
kalibrerad, powerrank-fliken). Powerranken är nu **`powerrank-v2`**: v1:s
metodfel (poäng på ALLA matcher men xPts bara på xG-täckta, hopjämkat med
skalningen `pts × n_xg / matches`) är rättat — poäng, mål och xPts mäts på
EXAKT samma matcher, nämligen de med xG, och lag utan xG-matcher faller ur
tabellen i stället för att visas med `–`. `MIN_MATCHES` prövas mot hela
historiken, aldrig mot det säsongsfiltrerade urvalet.
**xG är BAKFYLLT för Europaligorna 2026-08-07** (`scripts/backfill_xg_ligor.py`,
61 min): PL/Serie A/La Liga 760 matcher och Bundesliga 611 — alla **100 %**,
MLS 73 % → 82 %. Matchantalen är oförändrade, alltså inga dubbletter.
Bakfyllning är tillåten för RESULTATSTATISTIK (ett avgjort resultat och dess
xG är settlade fakta) men aldrig för priser, live-signaler eller presence, där
observationstiden är en del av mätningen.
**De fyra ligorna är MODELLIGOR sedan 2026-08-07** (Samans beslut efter
bakfyllningen). Mätt mot Pinnacles stängning är de i linje med ligorna vi
redan accepterat — PL ligger NÄRMAST marknaden av alla sju (logloss-gap
+0,0035 mot Allsvenskans +0,0123). Modellen är sämre än marknaden i ALLA
ligor; det är väntat och är själva skälet till att den är amber.
De poolas MEDVETET INTE med sina matarligor: uppmätt försämrar poolning
modellen i alla fyra (+0,0036 till +0,0125 logloss), eftersom matarligorna
saknar xG. T kalibrerat per liga (PL 0,8, Serie A 0,7, La Liga 0,9,
Bundesliga 0,95) — `_fetch_texts` läser nu även de klassiska säsongsfilerna,
som bär samma stängningsodds. Modellversionen gick `m-67d028e9` →
`m-e900ed90`; **sharp är oförändrad**, så sharp-CLV-facitet rörs inte.
**`_xg_is_measured()`** förkastar xG-par där båda är exakt 0,00 eller där ett
lag som GJORDE MÅL har 0,00 — Sofascore rapporterar saknad mätning som noll
(samma fel som fällde den som livekälla). Ett mållöst lag med 0,00 lämnas
orört: radera på omöjlighet, aldrig på osannolikhet.
**`_fd_result_rows(..., div=)`** kontrollerar filens EGEN divisionskod:
football-data serverade skotsk Championship på La Ligas säsongs-URL.
**`oddset_model.elo_for()`** slår upp ClubElo på EXAKT nyckel eller VERIFIERAT
alias — aldrig fuzzy. `_find_team`s delsträngsregel (utan likhetströskel) gav
37 felaktiga länkar över modelligorna: `stuttgart`→`start` (IK Start, NOR,
1295), `minnesota united`→`man united` (1915), `leicester`→`lillestrom`.
Ingen tröskel kan separera dem från de KORREKTA delsträngsparen
(`werder bremen`→`werder` 0,63), så fuzzy ska inte försöka. `ELO_TEAM_ALIAS`
nådde tidigare bara V2-spåret och delas nu; bekräftat olika klubbar står i
`ELO_REJECTED_LINKS`. Ett lag utan verifierad länk får INGEN Elo — för ett
tunt lag betyder det ingen modell alls i stället för fel modell. ClubElo
saknar just nu Bayern och Stuttgart helt (källan svarade inte vid kontroll;
aliaset finns och börjar gälla när de dyker upp).
Föregående Flashscore-överlämning är ersatt och gäller bara som historik.
De fyra Europaligorna (PL, Serie A, La Liga, Bundesliga) är **FULLT FÖLJDA
sedan 2026-08-07** inför säsongsstarten: sidoböcker, deep-marknader,
värdesignaler, CLV och notiser precis som Allsvenskan. `research_only` är
borta för dem och `RESEARCH_LEAGUE_KEYS` är tom. Spärren behövdes aldrig för
SHARP-tiern — den är ren oddsjämförelse och har inget med V2.2:s modell-
hypotes att göra; V2.2 kör vidare på sin EGEN `SCOPE_LEAGUES`. De var
utanför `MODEL_LEAGUES` så länge de saknade xG — en xG-viktad modell utan xG
vore sämre än ingen — och kom in 2026-08-07 när bakfyllningen gav 100 %.
Mekanismen synlig≠actionable finns kvar även när ingen liga använder
den (cuper och träningsmatcher visas och bär sharp-signaler utan modell). `_next_round_for_empty_leagues` (f.d. `_research_next_round`) gäller nu
ALLA synliga ligor: under säsongsuppehåll visas nästa omgång i stället för
en tom liga.
Poolspår PH1–PH4 finns nu: historiskt settlement, framåtriktad presence-ledger
och CDN-ålderskorrigerad `pit-v3`, kontrafaktiskt systemfacit samt fryst
forward-gate. Det samlar
data utan bakfyllning och påverkar ännu inte runtimeförslag. Nästa steg är att
auditera de första riktiga v3-horisonterna, systemfrysningarna och settlementen;
se `docs/pool-pit-v3-2026-07-25.md`.
Ett separat `pool-strength-blend-v1` samlar från 2026-08-10 under
`docs/pool-strength-forward-manifest-v1.json`: Pinnacle är orörd baslinje,
90/10 Pinnacle/lagstyrka är enda kandidat och 80/20 är diagnostik. En rad
fryses per match vid h24/h3/m20, även vid bortfall; ingen historisk
rekonstruktion och inga system ändras. Status visas i **Historik → Poolmodell**
och API:t är `/api/pool/strength-shadow`. Modellversion, timing, identitet,
blend eller gate ändras aldrig inne i samma manifest/shadowversion.

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
                      (/api/pool/systems; champion = dagens byggare).
                      **GENERATION 2 sedan 2026-08-05:** budget
                      144/256/512/1024 kr × risk säker/medel/tuff (vw 20/50/80)
                      = 12 konfigurationer, champion `b256-medel`. Radpriset är
                      1 kr för alla produkter, så budget = antal rader.
                      **`benchmarks_for(product)` är ENDA källan till vad som
                      mäts** (frysning, championrapport och översikt måste läsa
                      samma familj). Topptipset-familjen har tak 512:
                      8 matcher ⇒ 3^8 = 6 561 möjliga rader, så 1 024 rader är
                      15,6 % av HELA utfallsrummet (mattbombning, och spelet
                      har bara EN vinstnivå) mot 0,06 % på ett 13-matchsspel.
                      Samma nyckel mätte två olika saker. Beslutat 2026-08-09
                      EFTER att raderna var synliga — inte en ren
                      förregistrering, se `docs/db-atgarder.md`.
                      Generation 1 (`ev50-*`, `ev256-*`) är PENSIONERAD och
                      blandas aldrig in — en config_key ändras aldrig i
                      efterhand, så nya nycklar räcker (ingen migrering).
                      Championen MÅSTE spegla appens budgetreglage: den stod
                      på 50 kr medan reglaget stod på 128, så etiketten var
                      osann. Promotion kräver BH-FDR över hela
                      utmanarfamiljen (60 jämförelser) OCH ≥40 parade
                      omgångar — `champion_report()`. `system_detail()` ger
                      ett fryst system match för match mot facit med streck
                      vid frysning och vid stopp; ingen ny insamling behövs
  app/live_radar.py  shadow-radar för pågående matcher: TVÅ separata
                      provider-serier (`LIVE_SOURCES`), högst 12 min gamla.
                      **Flashscore är ANKARE sedan 2026-08-06; Sofascore är
                      URKOPPLAD ur radarn** — den rapporterade xG som 0.0 i
                      stället för att utelämna det, och en nolla ser ut som
                      en mätning (Paide–SK Rapid: 0.0/0.0 mot Flashscores
                      0.09/0.81). Sofascore samlar OFÖRÄNDRAT resultat,
                      modellstatistik och frånvaro. Källan väljs på
                      strukturell fälttäckning (aldrig på signalvärdet),
                      därefter fast prioritet Flashscore→FotMob.
                      Länk kräver unik liga/lag/avsparksträff; en olänkad
                      färsk providerserie får eget kort.
                      **Oddset-spärren för träningsmatcher** (`known_friendly`)
                      prövar ETT lag entydigt när båda inte räcker: ett lag
                      spelar en match i taget, så delar exakt EN Oddset-
                      träningsmatch i samma tidslucka ett lag med providerns
                      rad är det samma match. Uppmätt 2026-08-09 föll 15 av 27
                      på tvåsidig namnlikhet, varav 6 uppenbart samma match
                      (`Atl. Madrid`/`Atlético Madrid`, `Johor DT`/`Johor
                      Darul Takzim`, `Ath Bilbao`, `Monaco`/`AS Monaco`) och
                      noll tvetydiga. Manchester City och Chelsea föll på
                      MOTSTÅNDARENS namn. Avspark måste vara känd på båda
                      sidor och två kandidater ⇒ avslag. Spärren styr RÄCKVIDD,
                      inte pris: ett falskt positivt kostar ett statistikanrop,
                      aldrig ett odds på fel match. Aldrig automatiska
                      spel eller runtime-modellinput.
                      **NAMNLÄNKNING I TRE STEG** (`_linked_series`), där
                      varje steg kräver EXAKT en kandidat: (1) strikt
                      `_same_team` på båda lagen; (2) `_same_team_in_context`
                      på båda (kortnamn, förkortning, grundningsår i mitten);
                      (3) `_one_side_candidates` — ETT lag räcker, eftersom
                      ett lag spelar en match i taget: delar två rader liga
                      och exakt avspark och är ett lag samma, kan de omöjligen
                      vara olika matcher. Steg 2–3 är säkra ENBART tack vare
                      anropsstället och får aldrig användas fristående
                      (`Inter` ↔ `Inter Miami` passerar namnregeln men delar
                      aldrig avspark). Truppmarkörer (U23/B/women) spärrar i
                      ALLA steg — `Inter` mot `Como` och `Inter U23` mot
                      `Como` är två matcher. Steg 3 avskaffar aliasjakten för
                      översättningar (`Austria Vienna` ↔ `Austria Wien`).
                      `live_norm_team` prövar aliaset IGEN efter att
                      landskoden strippats: `norm_team` slår upp på hela
                      strängen, så `goteborg (swe)` missade varje alias och
                      internationella matcher tappade tyst sina alias.
                      `cli.py lanklucka` MÅSTE köra samma regler som länken
  app/live_signal_ledger.py framåtriktad append-only-journal över den första
                      synliga Följer/Stark-nivån per match × signaltyp:
                      minut/ställning/mått + observerad öppen Kambi-live-Ö/U,
                      normaltidsfacit och Asian-Över-ROI. Aldrig tipsinput
  app/flashscore.py   liveprovider med `flashscore-live-v4`: publik pipe-feed,
                      statisk publik
                      headerkonstant (samma klass som Pinnacles gästnyckel);
                      brotli KRÄVS. Minuten HÄRLEDS ur stadiets starttid
                      (AC 12/13 + AO) — okänt stadium ⇒ None. Dagsfeeden är
                      CDN-FRYST uppåt 2 min; ställningen räddas då ur
                      per-match-feeden `df_sur` (`parse_summary`: BA/BB+BC/BD
                      per halvlek, AT/AU-fallback, fältregel driftverifierad
                      2026-08-02). Koherensvakten är RIKTAD åt båda hållen:
                      ställning äldre än stats = farlig (20 s, fabricerar
                      "hög xG men inget mål"), stats äldre än ställning =
                      konservativ (180 s). Stadiebyte i `df_sur` censurerar
                      minuten hellre än låter den ticka i fel stadium. Lyckad
                      tom lista avslutar presence, transport-/parsefel aldrig.
  app/flashscore_data.py Flashscore samlar modelldata PARALLELLT med
                      Sofascore till `oddset_result_stats`; resultatkällan
                      överlastas aldrig och `+fs` är avskaffat. xG väljs som
                      ett helt hem/borta-par, hörnor som ett separat helt par,
                      båda med explicit provider/event-id/observationstid.
                      Ingen historisk Flashscore-bakfyllning; bara dagsfeeds.
                      Frånvaro lagras separat per provider/status och tomt
                      lyckat svar är en riktig observation.
                      **Feeden har TVÅ paket** (mätt 2026-08-06 på 12 matcher):
                      8/12 bar bara bas (possession/skott/på mål/utanför/
                      blockerade/hörnor), 2/12 hela paketet med xG, xGOT,
                      stora chanser och skott i box. xG SAKNAS alltså genuint
                      för de flesta europacupkval — providerns gräns, inte
                      parserns. `STAT_NAMES` läser nu även shots_off,
                      shots_blocked, touches_box, saves och possession;
                      `touches_box` ingick i `_stats_rank` utan att någon
                      källa kunde fylla det. Possession läses med `_share`
                      (`54%`), aldrig med `_f` — feedens övriga procenttal är
                      härledda kvoter (`85% (271/319)`) där andelen inte är
                      måttet.
                      **KLOCKAN SAKNAS ALDRIG** (Samans krav 2026-08-06).
                      `STAGE_FROZEN` bär etikett OCH spelad minut för stadier
                      där klockan står stilla (38 = Paus, 45 spelade min) —
                      minuten TICKAR inte där, men den finns, för annars
                      returnerar `radar_signal` `no_clock` och matchen faller
                      ur "starkt chansgap" i samma sekund domaren blåser av.
                      `STAGE_LABEL` (bara frysta stadier) visas I KLOCKANS
                      STÄLLE; `STAGE_NAME` (alla kända stadier) används BARA
                      som reserv när minuten saknas helt, t.ex. när
                      koherensvakten nollställt stadieklockan
  app/fotmob.py       liveprovider med `fotmob-live-v2`: live-xG/xGOT/skott,
                      även Oddset-spärrade friendlies. Ställningen tas ur samma
                      eventdetalj som statistiken; äldre listställning får
                      skilja högst 15 s innan hela listan/id-indexet omhämtas.
                      Saknas koherent ställning sparas ingen rad. Egen tabell,
                      egen presence och egen source-health.
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
  mobil samma sortering över kort. `SortableTable` kapar med `limit` EFTER
  sorteringen — slicea aldrig `rows` före anropet, det ger en falsk topplista.
  Signalgruppsfacit och signallogg hör hemma i Labb, aldrig som en femte
  Oddset-sektion.
  **YTGRÄNSEN (2026-08-05): Historik = 100 % POOL, Labb = 100 % ODDS.**
  Sammanhörande data får inte spridas över två vyer. Poolens prognosfel och
  PH4-κ-fönster flyttades därför till Historik, och PH3-kortet togs bort ur
  Labb (det dubblerade Historikens Systemfacit). Historik har EN produktväljare
  överst som styr hela sidan — kuponger, systemfacit, prognos och omsättning.
  Det gäller även poolens styrkemodell-shadow: dess täckning, logloss mot
  Pinnacle och grind ligger i Historik → Poolmodell, aldrig i Labb.
  Långa tabeller visar 20 rader med "visa alla". Ingen parameter göms i en
  nyckelsträng: budget, strategi och värdevikt är egna kolumner. Horisonter
  visas i minuter (180/20), aldrig som `h3`/`m20`. Se
  `docs/historik-ui-2026-08-05.md` för före/efter-mätningarna.
  **Labb ombyggt 2026-08-05 med samma metod** (`docs/labb-ui-nulage-2026-08-05.md`):
  öppet läge visar bara AKTIVA versioner (aktiv-markeringen kommer från
  respektive systems eget fingeravtryck — value-loggens och ledgerns
  `s-`-namnrymder är OLIKA och får aldrig korsjämföras); versionshistorik
  ligger bakom togglar med datumintervall, ROI/KI visas aldrig under
  `ROI_MIN_N` (=10) observationer, och poolens forskningskort (pit-v4, PH5,
  startOdds) renderas i Historik via `HISTORIK_RESEARCH`.
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
- Källhälsa/varvlucka: `cd backend && .venv/bin/python -B cli.py kallhalsa [timmar]`
  (läser `oddset_source_health_log`; `—` i varvkolumnen = källan kördes inte).
- **Dubblettjakt: `cd backend && .venv/bin/python -B cli.py lanklucka [timmar]`**
  — providerpar med samma liga, samma avspark och hög namnlikhet som ändå INTE
  länkar. Kör den efter varje ny liga/kvalomgång: fem namnfall upptäcktes på
  ett dygn genom att Saman såg dubbletter i UI:t, vilket är fel ordning.
  Bekräftade par går i `LIVE_TEAM_ALIASES` (kanonisk form = den i
  `oddset_results`), bekräftat olika klubbar i `LIVE_TEAM_REJECTED`.
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
  **SETTLEMENT KÖR PÅ VARJE TICK** (`_settle_pass`, 2026-08-08), även när inget
  basvarv behövs: insamling kostar, facit gör det inte. Varje rad i
  `pool_backfill_log` bär sin EGEN `retry_after`, härledd ur draw-payloaden —
  matcher som rullar prövas när de rimligen är slut (avspark + 130 min), en
  färdigspelad omgång var 15:e minut, tak 6 h. Den gamla fasta
  6-timmarsbackoffen VAR hela fördröjningen: 100 % av 30 mätta
  `not_finalized→ok`-gap låg över 5,5 h, median 6,21 h. Ett försök gjordes ofta
  innan matcherna var färdigspelade — en spelad kupong är kandidat från
  bokföringen — och blockerade då just det försök som hade lyckats. Höj inte
  `SETTLE_PASS_MAX_DRAWS` (2/produkt, uppmätt 0,15 s tyst) utan att räkna om
  radarns marginal. `pool_played.match_finished()` är EN delad definition av
  "färdigspelad" för livekortet och omprövningstiden — skriv aldrig en parallell.
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
  inaktuell ställning som följd. Varje liveprovider har egen presence och
  source-health. Ett **lyckat** tomt roster avslutar tidigare kort direkt;
  nät-/parsefel får aldrig göra det. `last_run` i API/UI är den äldsta av
  `LIVE_SOURCES`-kontrollerna och är tom tills alla har kontrollerats —
  Sofascore ingår inte längre och får inte hålla tillbaka stämpeln.
  En färsk match med chansdata ska visas även om den andra källan saknar
  den; `fotmob:<id>` respektive `flashscore:<id>` är då kortets namespacade
  event-id. Gör aldrig livevisningen beroende av att en källa först kan
  länkas till en annan providers rad.
  Live-radarn är shadow/informationsstöd och får inte påverka tips, Kelly,
  CLV, pushnotiser eller systemförslag utan ett nytt explicit beslut.
  Signaljournalens blindkohort är FÖRSTA aktiva signalen per match (en
  Följer→Stark-eskalering får finnas i diagnostiken men får inte dubblera
  blindtestet). Minst 200 oddssatta+avgjorda signalmatcher, minst 60 dagar och
  undre KI90 > 0 krävs före stöd; inga historiska liveodds bakfylls.
  **Aktiv signalversion är `chance-gap-shadow-v9` från exakt
  2026-08-09T18:00:00Z**. v9 ändrar bara scope: Bolivias Primera División
  läggs till som ordinarie live-/sharp-liga. Besta deild fanns redan, men
  v9 rättar FotMobs aktuella ligarubrik `Besta deildin` och lägger UT 188
  explicit i radarscopet; Island blir därmed verifierat tvåkälligt.
  Trösklar, providers, källrankning och identitet är oförändrade; metodnot:
  `docs/radar-scope-v9-2026-08-09.md`. v8:s tre ligor och produktionskvitto
  finns kvar i `docs/radar-scope-v8-2026-08-09.md`. v7:s proxysignal
  (`docs/radar-proxy-v7-forregistrering-2026-08-07.md`) aktiverade
  aktivering krävde `skott i box` — ett fält som bara finns i 43 % av
  matcherna, nämligen exakt de som ändå har xG. Proxyn tillförde därför NOLL
  matcher utöver xG-signalen medan 59 % aldrig kunde få någon signal alls.
  Villkoret använder nu `farliga skott` = på mål + blockerade (100 %
  täckning); TRÖSKELVÄRDENA ÄR OFÖRÄNDRADE — ett fält byts, ingen ny
  frihetsgrad. Validerat: korrelation 0,890 mot skott i box och samma svar
  vid tröskel ≥8 i 91 % av 1 342 observationer. Räckvidden gick 43 % → 100 %,
  utlösningsfrekvensen 29 % av matcherna. Proxyn är ETT ENHETSLÖST INDEX
  (`proxy_index`) och får aldrig uttryckas i mål — en regression av xG på
  skottmåtten gav negativ hörnkoefficient och ett fel lika stort som
  signalen. v6 (2026-08-06T16:45Z→) samlade fyra ändringar i samma process:
  Sofascore urkopplad som livekälla, Flashscore som ankare, flerstegs
  namnlänkning och fem nya måttpar (som även ändrar källrankningen). v5 (2026-08-03T06Z→) samlade i sin tur tre
  identitetsfixar, riktad koherensvakt, `df_sur`-ställning och spegellänk med
  transponering (`_mirrored_capture` — en spegelvänd providerserie uttrycks i
  ankarets orientering, aldrig rå). v4 (2026-08-01T21Z→) och ogiltiga piloten
  v3 (08–21Z) är historik; v2 <08Z. Settlement stämplar efter capturetid,
  aldrig efter versionen som råkar vara aktiv när kön körs. En ändrad
  datagenererande process kräver alltid ny signalversion.
  **`radar_version` MÅSTE ligga i `_FLASHSCORE_VIEW_KEYS`/`_FOTMOB_VIEW_KEYS`**
  — journalen läser radens egen version DÄR. Saknas den härleds kohorten ur
  observerade växlingar, och varje rad efter den sista kända växlingen blir
  felaktigt `transitional`, alltså raderad ur blindkohorten. Journalens
  `_clock` läser signalens `basis` i stället för att härleda lånet på nytt.
  **KOHORTREGELN (2026-08-05):** en rad hör till vN bara om vN-KODEN
  producerade den OCH den observerades i vN:s DEKLARERADE fönster — annars
  `transitional`, som ingår i INGEN kohort. Rader flyttas ALDRIG till
  föregående kohort. `RADAR_*_STARTED_AT` är handskriven AVSIKT; koden byter
  i samma sekund filen sparas (jobben kör ur arbetskopian), och de två gled
  isär åt båda hållen tills 57 % av v4 var v5-producerad. Nya captures bär
  `radar_version` PÅ RADEN; historik (NULL) härleds ur journalens frysta
  `RADAR_OBSERVED_SWITCHES`, och inne i en växling blir raden transitional i
  stället för gissad. Före bevishorisonten 2026-08-01T01:02:15Z finns ingen
  journal — v2 är ovaliderad och duger inte som baslinje. Se
  `docs/db-atgarder.md` 2026-08-05 och `scripts/migrera_radar_kohorter.py`.
  Provider-id hanteras som ogenomskinlig STRÄNG i presence, journal och
  settlement (Flashscores är alfanumeriskt: `SKg88Q3T`). Tabellen
  `oddset_live_moment_settlement.event_id` är därför TEXT; ändringen görs
  endast med `scripts/migrera_radar_event_id_text.py` + backup.
  **Livelagnamn (2026-08-02):** `live_radar._same_team` styr TRE länkar —
  provider↔provider (dubbletter), livekort↔Oddset (`no_canonical_match` = inget
  live-odds) och signal↔resultat (facit). Ett namn som inte matchar ger därför
  två journalkort där odds hamnar på den ena raden och facit på den andra;
  matchen bidrar med NOLL till blindkohorten trots att båda delarna finns.
  Ett par som bara skiljer sig i providerns PRESENTATION går i
  `LIVE_TEAM_ALIASES`; ett par som är samma klubb även i resultathistoriken hör
  hemma i Oddsets `TEAM_ALIASES` (modellidentitet) — se DB-åtgärden 2026-08-02,
  där 588 dubblerade resultatrader slogs ihop.
  Flerords-prefixregeln är farlig: `Los Angeles FC`
  normaliseras till `los angeles` och blev därmed samma lag som
  `Los Angeles Galaxy`. Kända falska par skrivs explicit i
  `LIVE_TEAM_REJECTED` — samma princip som `TEAM_REJECTED_LINKS`, aldrig en
  generell regel.
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
7. **En latest-state-tabell är inget facit på att en källa kördes.**
   `oddset_source_health` har PK `(source, league, scope)` och skriver över sig
   själv — den svarar bara "vad sa källan sist". `oddset_source_health_log`
   (2026-08-02) är append-only med `checked_at` i nyckeln och är den enda som
   får bevisa att en källa kontrollerades i ett visst varv. Beskärs 30 dygn på
   djupvarvet. Samma princip som presence-ledgern: skriv en rad per kontroll,
   annars går "vi frågade och fick tomt" inte att skilja från "vi frågade
   aldrig".
8. **`Z` betyder UTC, inte bara ett suffix.** En offsetmedveten tid måste
   konverteras med `astimezone(timezone.utc)` innan den formateras med `Z`.
   Europatipset 2597 fick annars `21:25Z` av `21:25+02` fast rätt tid var
   `19:25Z`, vilket gömde publicerad utdelning i exakt två timmar.

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

**CLOSING-DRIFT (v8, 2026-08-07):** `fair` är inte Pinnacles pris NU utan en
skattning av var det STÄNGER. Mätt på 10 908 parade observationer driftar
Pinnacle systematiskt per band: favoriter −0,61 pp, outsiders +0,32 pp,
mitten inte alls — konstant mellan T−24h och T−3h, ~5× mindre vid T−20m.
Följden i facitet var att favoritflaggor gav +0,29 % close-EV (KI rymmer
noll) mot outsiders +5,96 %. `drift_adjust` korrigerar per band i två
tidsregimer; bandet sätts på den OJUSTERADE sannolikheten (annars cirkulärt)
och summan normaliseras INTE om (det är en nivåkorrigering, ingen devigering).
Detta är INTE momentum — korrelationen tidig/sen rörelse är +0,020, R²=0,000.
Se `docs/closing-drift-v8-forregistrering-2026-08-07.md`.

Andra ankaret är BORTKOPPLAT 2026-08-07: Smarkets har 56 030 priser på 1X2
och NOLL på AH/Ö/U/hörnor, så den kunde bara mäta 24 % av flaggorna och 271
frånvaronoteringar var brus om ett känt hål. **Spärren i `ANCHOR_SOURCES`
står kvar** — den är en SÄKERHETSSPÄRR, inte en användning: utan den blir
Smarkets en spelbar bok igen (184 av 476 felaktiga flaggor 2026-07-25).
Historiska rader: andra ankaret (`ANCHOR2_SOURCE`) MÄTTES i skugga på varje flagga
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
  **Scanhintet ägs av `Storage.seed_hint()`/`store_seed()`** och MÅSTE användas
  av både API och insamlingsvarv — `_scan_draws` tittar bara 80 nummer framåt.
  `cli.py` körde på kodens statiska seed (4177) medan `main.py` läste meta
  (4259), så Topptipset Dagens 4256+ låg utanför varvets scanfönster: appen
  visade omgångarna, varvet slutade TYST samla dem 2026-08-04. Stryk och Extra
  låg kvar innanför fönstret och dolde felet. Varvet skriver tillbaka hintet
  själv, och hintet går bara FRAMÅT.
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
  **Byggaren (`systemStats`) värderar alltid mot prognosen, kupongen
  (`couponStats`) mot LIVE tills användaren trycker `→ prognos`** — därför
  visar de två panelerna olika tal på samma system, och skillnaden är exakt
  omsättningskvoten. Det är avsiktligt, men måste sägas ut i UI:t.
  `PayoutTable` härleder omsättning OCH etikett ur `s.turnover`, dvs. den
  potterna faktiskt byggdes med; skicka aldrig in omsättningen separat
  (2026-08-06 beskrev byggarens fottext prognospotter som `live`).

### Export till Svenska Spel ("Egna rader")

- `.txt` (CRLF) med obligatorisk rubrikrad: Stryktipset/Europatipset = produktnamnet;
  Topptipset = `Topptipset[,Stryk|,Europa],Omg=<nr>,Insats=<1–10>`. Därefter `E,1,X,2,...`.
- Exportera alltid konkreta enumererade rader (E), aldrig M-system.
- Uppladdning på `spela.svenskaspel.se/{produkt}/externa-systemspel`.
- R 4-0-9 / R 0-7-16 / R 4-4-144 är exakta Hamming-täckningar; R 3-3-24 är greedy (38 rader).

### CLV-facit (signalvalidering)

- **Modelldata v4:** `oddset_results` bär bara matchidentitet och normaltids-
  resultat. En komplett football-data-rad vinner atomiskt som resultatfacit
  (källa, råa lagnamn, hemma- och bortamål som ett paket). xG och hörnor bor i
  `oddset_result_stats`: välj alltid ett komplett hem/borta-par per
  statistikfamilj och redovisa `xg_provider*` respektive
  `corners_provider*`; blanda aldrig fält mellan providers. Flashscore och
  Sofascore samlas parallellt. Frånvaro har provider i primärnyckeln,
  namespacade spelar-id:n och status `observed`/`unavailable`; transportfel är
  aldrig `unavailable`, medan ett lyckat tomt svar är en riktig observation.
  `MODEL_DATA_VERSION=4` och V2.2-manifest v4 isolerar äldre kohorter.

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
- `scripts/close_drift_facit.py` och `close_drift_facit_v2.py` väljer en
  **exakt** `signal_version` (default = aktuell sharp-version). Nycklar och
  linjeflyttsjoin innehåller versionen; rapporter får aldrig slå ihop eller
  korsjoina historiska versioner.
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
- Oddset har FEM persisterade sub-tabbar och en alltid synlig räknarrad.
  **🏋 Lagstyrka (`powerrank-v2`, 2026-08-07)** visar modellens egen powerrank
  per liga: `att`/`def` ur samma `fit_league` som prognoserna använder (aldrig
  en parallell skattning), plus xPts ur matchernas xG och avvikelsen mot
  faktiska poäng — positivt = laget har tagit mer än chanserna motiverar och
  är kandidat för nedgång. **Poäng, mål och xPts mäts på EXAKT samma
  matchmängd: de med observerad xG.** En match utan xG bidrar med ingenting,
  och ett lag utan xG-matcher visas inte alls — v1:s skalning
  `pts × n_xg / matches` antog att poängen fördelade sig jämnt över täckta
  och otäckta matcher och gjorde avvikelsen till en approximation. Ingen
  bakfyllning här; xG kommer ur `oddset_result_stats`.
  `season_of()` avgör säsongsetikett på `FD_SEASON_CODES` (höst/vår ⇒
  `2025/26`, annars kalenderår) — återanvänd den listan, skriv aldrig en
  parallell. Säsongsvalet gäller BARA de räknade kolumnerna: fitten ser alltid
  hela poolen med tidsvikt, och `MIN_MATCHES` prövas mot hela historiken så
  tabellen inte är tom två månader varje säsongsstart.
  `#` är styrkerank, INTE tabellplacering — avsiktligt, annars vore den bara
  tabellen igen. Visningsnamnet (`name`) väljs bland RÅA namn: diakriter
  först, sedan längst, och oddssidans namn (`Storage.oddset_team_names`)
  läggs till som variant eftersom football-data strippar diakriter
  (`Djurgarden` → `Djurgårdens IF`). Uppslaget kräver exakt normaliserad
  nyckel — aldrig fuzzy, fel klubbnamn är värre än ett tråkigt.
  Ranken syns även som chip i matchraden, uppslaget
  på RÅA lagnamn (`aliases`), aldrig på substräng när ett exakt alias finns.
  Allt detta är **AMBER**: uppmätt förutsäger modellen inte Pinnacles drift
  till stängning (r = −0,120, 90 % KI [−0,252, +0,034]), så ranken får inte
  ge stödchip, lyfta ett spelkort eller påverka edge, urval eller notiser.
  Poolens nya styrkeblend är därför ett isolerat facitspår, inte ett undantag:
  den får först mäta 90/10 mot Pinnacle och därefter passera en separat
  system-shadow innan byggaren ens kan övervägas.
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
