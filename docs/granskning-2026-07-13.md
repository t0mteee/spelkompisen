# Kritisk granskning av Codex-feedbacken + reviderad projektplan

**Datum:** 2026-07-13 · **Granskad kod:** spelkompisen `2430bd6` · **Databas:** kopia av `data/stryktips.db` (14 MB) — originalet orört. Inga ändringar gjorda i kod, DB, konfiguration eller docs.

**Klassning som används:** 🔴 VERIFIERAD BUGG (fel i kod, bevisat) · 🟠 METODRISK (design som kan ge fel beslut; frekvens/effekt ej alltid mätt) · 🔵 HYPOTES (kräver data innan dom) · ⚪ FRAMTIDA IDÉ · ✅/⚠️/❌ = bekräftad/delvis/avfärdad.

---

## 0. Sammanfattning

Codex-genomgången är **ovanligt träffsäker**. Av tio områden bekräftas åtta helt eller i kärnan, med exakta siffror som reproducerar (892/574, 761/586, 1672/932, 5+5 stängda flaggor). Två områden behöver nyanseras: poolspels-EV:ns riktningsanalys (Jensen-felet är *konservativt*, det verkliga överskattningshålet är oberoende-antagandet som Codex inte nämnde) och MLS-xG-täckningen (observationen stämmer, men rotorsaken är **inte** källtäckning utan vårt eget merge-haveri — alla 932 Sofascore-MLS-rader har xG).

De tre allvarligaste verifierade fynden, i ordning:

1. **MLS-fitten tränas på korrupt data**: 304 dubblettmatcher (samma match två gånger pga UTC/lokal-datum) + LA Galaxy splittrat i två lag. ~18 % av fit-raderna är dubbletter.
2. **ÖU-ankringen är inte settlement-aware**: fel på 72 % av ankrade matcher (23 % heltalslinjer = fullt fel, 49 % kvartslinjer = halvt). Ankringen är modellens ryggrad — felet fortplantar sig till 1X2, AH och alla amber-flaggor.
3. **Priser saknar närvarobegrepp**: schemat kan inte skilja "oförändrat pris" från "plockat/suspenderat" — och suspension sker typiskt exakt när larmen triggar (lagbesked).

---

## 1. Granskningsmatris

### Område 1 — Asian Ö/U och sharp-ankring

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 1a | Ankringen matchar P(total > linje) direkt mot marknadens devigade sannolikhet — fel vid push | ✅ BEKRÄFTAD | 🔴 |
| 1b | Temperatur appliceras efter ankring och bryter ankaret | ✅ BEKRÄFTAD | 🔴 (liten i dag) |
| 1c | (tillägg utöver Codex) T är dessutom kalibrerad på **oankrade** prediktioner | ✅ BEKRÄFTAD | 🟠 |

**Evidens 1a:** `oddset_model.py:231-243` (`_anchor_total`) bisekterar skalfaktorn tills `total_over(matrix, line) == p_over`, där `total_over` (`oddset_model.py:73-74`) är den **ovillkorade** P(i+j > linje) och `p_over` kommer från power-devig av 1/odds (`attach_model`, `oddset_model.py:388-393`). För en heltalslinje är marknadens devigade sannolikhet ≈ **villkorad** vinstchans P(över | ej push) — fair odds för heltalslinje uppfyller o = (1−P_push)/P_vinst. Att sätta den ovillkorade svansen lika med den villkorade blåser upp totalen: exempel linje 3.0 med P(push)≈0,22 och marknads-p 0,50 → ankringen tvingar P(total ≥ 4) = 0,50 när korrekt är ≈ 0,39, dvs ~0,4–0,6 mål för hög μ-total. Kvartslinjer får halva felet (halva insatsen på hellinjen). **DB-frekvens:** av 83 unika Pinnacle-huvudlinjer i historiken är 19 hela (23 %), 41 kvarts (49 %), 23 halva (28 %) — felet biter på 72 % av ankrade matcher.

**Central observation som gör fixen liten:** `pair_fair` (`oddset_model.py:268-286`) är **redan settlement-korrekt** (push: fair o löser o·P_vinst + P_push = 1; kvartslinje = split på grannlinjer). Buggen är isolerad till ankarsteget. Fixen är att bisektera på den *villkorade* sannolikheten ur `pair_fair`-matematiken i stället för på `total_over`.

**Evidens 1b:** `attach_model` `oddset_model.py:392-396`: ankra → bygg matris → `temper(matrix, cal_t)`. `temper` (56-64) renormaliserar p^(1/T) vilket flyttar P(över) när T≠1. I dag: Allsvenskan T=1.0 (no-op), Eliteserien T=0.85 → ankaret glider där. Litet i dag, men blir fel på riktigt när fler ligor får T≠1.

**Evidens 1c:** `oddset_backtest.run_league` (`oddset_backtest.py:62-123`) ankrar **aldrig** (ingen `_anchor_total` i backtesten), och `fit_temperature` (199-) fittar T på dessa oankrade prediktioner — som live appliceras på ankrade matriser. T är alltså kalibrerad för en annan fördelningsfamilj än den den justerar. Dessutom fittas och utvärderas T på samma walk-forward-material (in-sample för T; 1 parameter — låg risk men värd att notera, jfr område 7).

**Konsekvens:** μ-totalen systematiskt fel på hel-/kvartslinjer → 1X2-, AH- och ÖU-fair fel → amber-flaggor (mou/mah/m1x2) och deras forward-facit förorenade. Modellens grönt-kriterium mäter delvis den här buggen i stället för modellen.

**Åtgärd (WP1):** settlement-aware ankare via `pair_fair`-matematiken; ordning tempera→ankra (eller fixpunkts-iterera ankare på tempererad matris, 2–3 varv räcker); omkör `oddsetcalibrate` efteråt.

**Acceptanskriterium:** roundtrip-egenskapstest — prisa en linje ur en känd DC-matris med `pair_fair`, deviga, ankra en *annan* μ-uppsättning mot det priset; pipelinens (temper+ankare) villkorade P(över) ska återge marknads-p inom 1e-3 för hel-, halv- och kvartslinjer, med T≠1. I dag failar hel/kvarts.

**Testning innan implementation (Codex fråga):** skriv testet ovan FÖRST (det failar nu), plus enhetstester för `_half_outcome`/`pair_fair` mot handräknade fall: linje 3.0 (push), 2.75/3.25 (half-win/half-loss), 2.5 (ren). Ingen migration. Facit påverkas inte bakåt (amber-flaggor loggade före fixen märks med modellversion — se WP5).

---

### Område 2 — Oddsens aktualitet och tillgänglighet

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 2a | Gamla priser kan misstolkas som aktuella → falsk värdesignal | ✅ BEKRÄFTAD som designlucka | 🟠 |
| 2b | Avstängda/borttagna marknader hanteras inte | ✅ BEKRÄFTAD | 🟠 |
| 2c | Källa som slutat svara upptäcks inte per selektion | ✅ BEKRÄFTAD (delvis: fel loggas per liga i rapporten, men värdemotorn ser dem inte) | 🟠 |

**Evidens:** `oddset_odds`-schemat (`storage.py:117-128`) har bara `fetched_at`; dedup-sparningen (`oddset_save_market`, `storage.py:546-566`) skriver **endast vid förändring** → `fetched_at` = "först sedd till detta pris", och det finns ingen `last_seen_at`. `oddset_latest` (579-) tar senaste sparade raden utan åldersfilter; `attach_value` (`oddset_value.py:44-83`) läser aldrig `fetched_at`. `kambi.league_events` läser bara "Fulltid"-betoffern utan status/suspended-fält; försvinner eventet/priset ur listView skrivs inget — det gamla priset förblir "latest" tills matchstart (enda vakten är live-guarden på starttid). Samma sak för Pinnacle/Betinia.

**Viktig nyans (delvis emot Codex):** min DB-mätning av "åldersgap" (t.ex. AIK–GAIS: svenskaspels senaste *sparade* pris 21 h äldre än Pinnacles) visar mest **oförändrade** priser, inte döda källor — dedupen gör att vi inte kan skilja fallen, och det är just det som är bristen. Frekvensen av äkta felfall (suspenderat/plockat pris i värdelistan) är **omätbar i dag** eftersom instrumenteringen saknas. Farligaste kända scenariot: SvS suspenderar 1X2 vid lagbesked — exakt när 🔥/💰-larmen fyras av — och edgen räknas mot ett ospelbart pris.

**Konsekvens:** falska notiser/edges i det mest tidskritiska fönstret; radar-pillen "bok står kvar på gamla priset" kan ljuga.

**Åtgärd (WP2):** Codex modell nedskalad till projektets skala: `last_seen_at` per selektion (uppdateras billigt även vid dedup-skip), härledd `available`-status (sedd i senaste varvet för källan?), source-health per källa/liga i meta + statusraden, åldersvakt i `attach_value`/notiser (notis kräver pris bekräftat ≤ senaste varv; UI visar bekräftelseålder i tooltip). TTL per källa behövs inte som separat mekanism — "sedd i senaste lyckade varvet" är rätt granularitet med A1-snabbpollen.

**Acceptans:** syntetiskt collect-test där ett pris försvinner → värdemotorn markerar unavailable och notiser uteblir; andel pushade notiser med pris bekräftat ≤ 5 min: 100 %.

**Migration:** `ALTER TABLE oddset_odds ADD COLUMN last_seen_at` + backfill = `fetched_at`. Facit påverkas inte.

---

### Område 3 — Event-, lag- och provideridentitet

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 3a | Namnvarianter splittrar lag (LA Galaxy) | ✅ BEKRÄFTAD | 🔴 |
| 3b | Lokal tid vs UTC lägger matcher på olika datum | ✅ BEKRÄFTAD (304 MLS-dubbletter) | 🔴 |
| 3c | MLS har sämre xG-täckning | ⚠️ DELVIS — observationen stämmer, orsaken är fel | 🔴 (vår, inte källans) |
| 3d | Fuzzy bör föreslå, inte tyst bestämma | ✅ Rimlig princip | 🟠 |

**Evidens (allt reproducerat på DB-kopian):**
- Codex siffror stämmer exakt: Allsvenskan 892 lagrade / 580 mergade / 574 med xG; Eliteserien 761 / 587 / 586; MLS 1672 / 1648 / 932.
- **304 par** i MLS med samma (kanoniserade) lagpar och datum ±1 dag, ena raden `sofa`, andra `fd` (ex: Columbus–Atlanta 2025-06-25 sofa vs 2025-06-26 fd). Mekanism: `_ingest_event` datumsätter i UTC (`oddset_data.py:136-137`) medan football-data-datumet är lokalt/brittiskt; merge-nyckeln `(date, home, away)` kräver **exakt** datum (`merged_results`, `oddset_data.py:361`). USA-kvällsmatcher hamnar systematiskt på var sin sida midnatt. Skandinavien drabbas inte (avsparkar före midnatt UTC) — därför funkar SWE/NOR-mergen (99–100 % xG på mergade rader).
- **`la galaxy` vs `los angeles galaxy`: likhet 0,67 < tröskeln 0,7** (`to_canon`, `oddset_data.py:350-355`) → aldrig kanoniserad; enda av 30 sofa-namn under tröskeln, men det är ett topplag (45+36 matcher under två identiteter).
- **xG-täckningen i källan är inte problemet:** 932 av 932 sofa-MLS-rader har xG; 740 av 740 fd-MLS-rader saknar (0 write-time-merges för MLS). "Sämre täckning" = vårt merge-fel, inte Sofascores.

**Konsekvens:** MLS-fitten (`FIT_POOLS` mls är egen pool) dubbelräknar ~18 % av matcherna och delar LA Galaxys styrka på två svagare identiteter → alla MLS-amber-flaggor och den planerade B7-kalibreringen står på korrupt grund. Vilodagar/resor (B6) omöjliga utan riktig identitet.

**Åtgärd (WP3):** Codex "canonical identity layer" är rätt riktning men överdimensionerad för scopet. Nedskalad version: `team_alias`-tabell (källa, källnamn → kanoniskt namn, verified-flagga), merge-nyckel med **datumtolerans ±1 dygn** (eller ännu hellre avspark-UTC när båda källor har den), **granskningslista** för osäkra matchningar (0,55–0,75) i stället för tyst `to_canon`-val, dubblettvarning i modeldata-rapporten. Interna event-/spelar-ID:n: spelar-ID tas med i frånvaro-snapshots (WP8); arena/tävlings-ID skjuts (⚪). Därefter: rensa MLS-raderna + `oddset_sofa_seen`-nycklarna och kör om ingest.

**Acceptans:** 0 par med datumoffset; LA Galaxy en identitet; ≥95 % xG på mergade MLS-rader; granskningslistan tom eller manuellt godkänd; fit-loggen listar inga lag med < 8 viktade matcher som borde ha fler.

**Migration:** ny tabell + omtag av MLS-resultatdata (results-tabellen är återuppbyggbar från källorna; CLV-facitet ligger i andra tabeller och berörs inte).

---

### Område 4 — CLV och facit

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 4a | PK saknar linan → olika linjer kolliderar | ✅ BEKRÄFTAD | 🔴 |
| 4b | "Linje flyttad" censurerar de mest informativa rörelserna | ✅ BEKRÄFTAD i kod (ej materialiserad i data ännu) | 🟠 |

**Evidens:** PK = `(match_id, market, sign)` (`storage.py:144-162`); `oddset_log_flag` (657-672) behåller första radens `line` men uppdaterar `best_edge` även när den nya edgen avser en **annan** lina → blandade linjer under en identitet. `resolve_closings` (`oddset_value.py:250-253`) sätter `closing_note='linje flyttad'` + NULL-stängning när sista snapshotens lina ≠ flaggans → raden utesluts ur snitt-close-EV (`clv_report`, 268-284). Nuläge i DB: sharp 16 flaggor (5 stängda), modell m1x2 27 (5), mah 10 (0), mou 13 (0), 0 censurerade hittills — buggen är verifierad i kod men facitet är för ungt för att den ska ha bitit; **rätt läge att fixa nu innan datat växer**.

**Konsekvens:** när AH/ÖU-facitet väl växer blir det systematiskt skevt: linjeflytt korrelerar med stor rörelse → censuren tar bort just de flaggor där CLV-signalen är störst.

**Åtgärd (WP4):** PK → `(match_id, market, sign, line)` (recreate + kopiera 66 befintliga rader — linan finns redan som kolumn). Stängning: använd sista observationen **på flaggans lina** var som helst i serien (inte bara sista tidpunkten); när linan flyttat permanent: stäng mot nya huvudlinjen och redovisa som egen kategori "line-moved" med Δlina — **inte** censur. Normaliserad line-CLV (översätta pris över linjeskift via modellmatris) är elegant men modellberoende — bryter regeln att facitet ska vara rent marknadsdata; jag rekommenderar kategoriredovisning i stället. Fasta horisonter (T−24h/−3h/−20m): hör hemma i WP5-ledgern, inte i value_log.

**Acceptans:** test där samma match/marknad/tecken flaggas på två linor → två rader; CLV-rapport visar snitt inkl/exkl line-moved + andel line-moved.

**Migration:** tabell-recreate; **facitet bevaras** (ta DB-backup före).

---

### Område 5 — Vetenskaplig validering

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 5a | "≥50 stängda + positivt snitt" är för svagt (korrelation, multiple testing, drift, ingen kontrollgrupp, extremodds-dominans) | ⚠️ DELVIS — riskerna är verkliga; regeln var dock en medveten minimigrind | 🟠 |
| 5b | Komplett prediction ledger med versionering | ✅ Rätt riktning, ska skalas till projektets storlek | ⚪→🟠 |

**Bedömning:** Alla fem riskmekanismer är reella och tre är redan observerbara i projektet: (i) modell-tier loggar m1x2+mah+mou per match = korrelerade observationer; (ii) modellen har ändrats mitt i insamlingen (rho-refit, xG-vikt, T-kalibrering, kvalitetsvikt q — allt 2026-07-12) utan versionstagg på flaggorna; (iii) close-EV på höga odds dominerar lätt ett medel (kvalitetsvikten q hanterar detta för *notiser* men facitet är oviktat). Kontrollgruppspoängen är den värdefullaste: loggas bara flaggade selektioner finns ingen nollhypotes-baslinje.

**Försvar av nuläget:** first/best-CLV mot devigad Pinnacle-stängning är rätt riktvärde och standardmetod; "≥50 + positivt snitt" formulerades som minsta grind för att ens *överväga* grönt, inte som slutgiltigt beviskrav. Men Codex har rätt i att gränsen kan passeras av brus.

**Åtgärd (WP5):** `prediction_log`-tabell som vid **fasta horisonter** (T−24h, T−3h, T−20m — sammanfaller naturligt med 30-min-varv + A1-snabbvarv) loggar ALLA prediktioner för alla kommande matcher: sharp-fair, modell-fair, bästa bokpris+bok, availability (från WP2), linje, `model_version` (git-hash + params-hash), tier. Rapport med **block-bootstrap per match** (spelvecka som alternativt block), 90 %-KI, grönt-kriterium = *undre KI-gräns > 0* och n ≥ 50 per (liga, marknad, tier, modellversion); winsoriserad close-EV (±20 %) som robusthetskontroll. Öppningslinje-ankaret (gamla backlog-A2) faller ut gratis ur ledgern (första loggade horisonten = öppningsreferens). Manuell spel-journal (faktiskt spelade tips) = egen liten tabell/flik, skild från forskningsloggen — bra idé, litet jobb, Samans beslut.

**Acceptans:** rapport per version/liga/marknad/tier med KI; ledgern innehåller även o-flaggade prediktioner (kontrollgrupp); en modelländring skapar ny version i rapporten.

**Migration:** ren tilläggstabell. Volym: ~40 matcher × 3 horisonter × ~10 selektioner/dag — trivialt för SQLite.

---

### Område 6 — Poolspelens EV-beräkning

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 6a | Poisson-binomialen beskriver inte medvinnare på lägre nivåer korrekt | ✅ BEKRÄFTAD som approximation | 🟠 |
| 6b | pott/(E[N]+1) ≠ E[pott/(N+1)] | ✅ BEKRÄFTAD men **riktningen är konservativ** — delvis emot Codex framtoning | 🟠 |
| 6c | Egna korrelerade rader behandlas som ensamma vinnare | ✅ BEKRÄFTAD, liten effekt | 🟠 |
| 6d | Backend optimerar utan jackpot, frontend visar EV med jackpot | ✅ BEKRÄFTAD | 🔴 (inkonsekvens) |
| 6e | (tillägg) Oberoende-antagandet överskattar utdelning (κ>1) — mätt men oapplicerat | ✅ (egen observation) | 🟠 |

**Evidens:** `build_ev_system` (`builder.py:522-630`): potter = `turnover × ratio × share` — **ingen jackpot någonstans i builder.py**; main.py:302-303 skickar inte jackpot; frontenden lägger jackpot på toppnivån (`App.jsx:1417, 1460`) och förifyller den från API:t (1651-1653) → radvalet är optimerat mot en annan målfunktion än den visade EV:n. Nivå-EV: `pf[c] × min(pool, pool/(field × pk[c] + 1))` (591-596; identiskt i `evalRows`, `App.jsx:1380-1404` — de två är åtminstone konsistenta, som CLAUDE.md kräver). `pk[c]` = P(slumpmässig folkrad matchar *min* rad på exakt c matcher) — korrekt medvinnartäthet bara i specialfallet utfall = min rad (exakt för c = N, approximation för c < N där medvinnarna beror på det faktiska utfallet). Jensen: pool/(E[W]+1) **underskattar** E[pool/(W+1)] (konvexitet) — mest på toppnivån vid få förväntade vinnare, dvs. dagens formel är *försiktig* där. Åt andra hållet: oberoende-antagandet P_folk(rad) = Π streck underskattar klustring — `cli.py backtest` (282-290) mäter κ = faktiska vinnare / oberoende-prognos men **κ appliceras aldrig** i EV-formeln. Egna rader: `+1` per rad, ingen egen-konkurrens (6c) — effekt noll på toppnivån (distinkta rader kan inte båda ha alla rätt) och liten på 12/11/10 där fältet dominerar.

**Svar på Codex fråga:** Ja — nuvarande EV bör beskrivas som **relativ rankningsheuristik med absoluta tal av indikativ kvalitet**, tills portfolio-simulering finns. Rankingen (radval) påverkas mest av toppnivån där matematiken är exakt givet oberoende-antagandet; absoluttalen på lägre nivåer är osäkrast.

**Åtgärd (WP6):** (S) skicka jackpot in i builderns toppnivåpott — nu; (S) applicera uppmätt κ̂ per produkt som medvinnar-multiplikator + UI-text om approximationen; (M) **portfolio-Monte-Carlo** för kupongvärdering: simulera ~10 000 utfall ur fair_prob per match, räkna kupongens totala utdelning per utfall med exakta medvinnare E[pott/(W+1)] (W ~ Poisson/binomial per nivå, egna rader räknade), ger dessutom varians/percentiler ("risk för 0 kr") — löser 6a+6b+6c på en gång. Beräkningstid: 10k × 13 matcher × ≤500 rader är hanterbart i backend (sekunder); frontenden behåller formeln som snabb förhandsvisning.

**Acceptans:** MC vs formel divergerar < ~5 % på toppnivå-EV utan jackpot (validering av båda); med jackpot ska builderns radval förändras mätbart (fler differentierade rader) och visad EV = optimerad EV.

---

### Område 7 — Modellens statistiska status

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 7a | Inte full DC-MLE utan iterativ Poisson-/momentfit med rho endast i prediktion | ✅ BEKRÄFTAD | 🟠 (benämning) |
| 7b | rho vald via grid, rätt mål? | ✅ grid på 1X2-logloss (`oddset_backtest.py:148-154`), in-sample över eval-perioden; målet ok för 1X2, återanvänds oprövat för AH/ÖU | 🟠 |
| 7c | Temperatur tränas/utvärderas på samma material | ✅ BEKRÄFTAD (in-sample, 1 parameter — låg risk) + tränas oankrat, appliceras ankrat (se 1c) | 🟠 |
| 7d | T ärvs av tunna ligor | ✅ BEKRÄFTAD (`attach_model._cal`, `oddset_model.py:347-358`) — medvetet, dokumenterat, obevisat | 🔵 |
| 7e | DECAY_DAYS=240 är e-folding, inte halveringstid | ✅ BEKRÄFTAD — kommentaren "~1 säsong halveringstid" (`oddset_model.py:31`) är fel: halveringstid = 240·ln2 ≈ 166 d | 🔴 (dokumentation) |

**Detaljer:** `fit_league` (`oddset_model.py:79-158`) är iterativ proportionell anpassning av Poisson-väntevärden på "effektiva mål" (0.65·xG + 0.35·mål) med ridge-dämpning ^0.98; för ren Poisson är momentekvationerna = MLE-scoreekvationerna, så "Poisson-fit" är ärlig benämning — men DC-korrektionen (tau) ligger enbart i `dc_matrix` vid prediktion och rho är en konstant vald ur backtest-grid. Praktisk skillnad mot äkta DC-MLE är liten vid rho = −0,01, men **etiketten "Dixon-Coles" översäljer**.

**Åtgärd (WP7):** byt benämning i UI/docs till "xG-viktad Poisson-styrkefit med DC-korrektion (ρ) i prediktionen"; rätta decay-kommentaren (behåll beteendet, kalla det e-folding ~240 d ≈ halveringstid 166 d — eller ändra konstanten om intentionen var 240 d halveringstid, men det kräver omkalibrering); notera T:s in-sample-status i kalibreringsmetan; efter WP1: omkalibrera T på ankrade prediktioner om backtesten kan ankra (kräver ÖU-stängningslinjer som football-data saknar → alternativt: kalibrera på levande ledger-data när WP5 samlat nog).

**Acceptans:** docs/UI beskriver exakt vad koden gör; ingen formulering låter modellen vara mer än den är.

---

### Område 8 — Datainsamling och reproducerbarhet

| # | Påstående | Verdikt | Klass |
|---|---|---|---|
| 8a | Event markeras "seen" även om statistikhämtning misslyckas | ✅ BEKRÄFTAD (`oddset_data.py:146-162`: statistics i try/except-pass, seen-mark alltid) — permanent xG-lucka utan retry. DB: 10 sofa-rader utan xG (6 allsv/3 obos/1 sup) är sannolika offer | 🔴 |
| 8b | Frånvaro skrivs över, inte snapshottad; spelar-ID/position tappas | ✅ BEKRÄFTAD (`meta_set("oddset_abs:{id}")`, `oddset_data.py:312`; endast namn/orsak/apps/rating sparas, 293-311) | 🔴 för framtida B5 |
| 8c | Elo bara aktuellt värde | ✅ BEKRÄFTAD (`oddset_data.py:236-238`) — mitigeras av att ClubElo har historiskt API (backfillbart) | 🟠 |
| 8d | SQLite utan WAL/busy_timeout/samlade transaktioner | ✅ BEKRÄFTAD: `journal_mode=delete` (uppmätt), `sqlite3.connect` utan pragmas (`storage.py:166-179`), commit per rad i `oddset_save_result` (643) → ~1 700 commits per fd-refresh | 🟠 |
| 8e | Inga automatiska tester för kritisk matematik | ✅ BEKRÄFTAD (0 testfiler i repot) | 🟠 |

**Åtgärd (WP0 + WP8):** WAL + busy_timeout + batchade transaktioner (S, gör först — API:t och 25-min-smartpasset skriver nu parallellt); seen-mark endast efter lyckad statistikhämtning alt. retry-lista med max-försök; frånvaro → tidsstämplade snapshots med spelar-ID/position (ger B5 träningsdata + möjliggör "vilken frånvaro flyttar linjen?"-analys); Elo → daglig snapshot per datum + engångs-backfill. Tester (pytest som dev-beroende): power-devig, asiatisk settlement (WP1-testerna), eventmatchning/tidszon (WP3), closing-line-matchning (WP4), poolutdelning (WP6-MC vs formel), kalibrering. Skriv testerna FÖRE respektive fix — de är acceptanskriterierna.

---

### Område 9 — Nya kostnadsfria datakällor

| Källa | Verdikt efter probe | Kommentar |
|---|---|---|
| ASA API | 🔵 OBEKRÄFTAD — certfel härifrån | `app.americansocceranalysis.com` ger SSL hostname-mismatch via både httpx och Chrome-TLS (curl_cffi) just nu. Måste verifieras (annan host? tillfälligt CDN-fel?) innan den planeras in. Om åtkomlig: bäst som **oberoende MLS-kvalitetskontroll** + domare/arena-metadata. Blanda aldrig ASA-xG och Sofascore-xG i samma kolumn (olika modeller) — egen provider-tagg. |
| Sofascore shotmap | ✅ VERIFIERAD, exakt som Codex sa | Eliteserien: 30/30 skott med shot-xG + xGOT. Allsvenskan: 0/31 (shotmap finns, xG-fält saknas). Coverage-matrix per liga/säsong/endpoint/fält är rätt krav innan någon shot-feature byggs. |
| Sofascore lineups | ✅ redan i drift | Utöka med spelar-ID/position/marknadsvärde i WP8-snapshots (fälten finns i svaret vi redan hämtar). |
| Sofascore incidents | 🔵 ej probat | Trolig och billig; värde först vid event-features (⚪). |
| MLS Player Availability Report | ⚪ | Officiell men editorial HTML — skör parser. Värde: officiell frånvaro för MLS. P2. |
| NFF fiksId-sidor | ⚪ | JS-app, kräver reverse-engineering. Startelvor/underlag/domare NOR. P2. |
| Fogis | ⚪ | Officiell SWE-källa, oklar åtkomst. Endast spaning. P2. |
| Open-Meteo Historical Forecast | ⚪ | Seriöst gratis-API med äkta point-in-time-prognoser. Men väder→måleffekt är liten; P2, efter ledgern. |
| Alla tävlingar per lag | 🟠 värdefullt | Sofascore `/team/{id}/events` täcker cuper/Europa — krävs för att B6 (vila/resor) inte ska räkna fel. Efter WP3. |
| Betfair Historical | ⚪/skip | Kontokrav; "basic" gratis men mervärde över Pinnacle-stängning är marginellt för våra ligor. Skip tills konkret behov. |

---

### Område 10 — Codex prioriteringsordning

**I stort ✅.** "Sanningslagret före mer data", "matematikfel före validering" och "skjut Europa-expansionen" är alla rätt — Europa-ligorna löser inget av ovanstående och multiplicerar datavolymen på trasig identitetsgrund. Justeringar: (1) settlement-ankringen och jackpot-fixen är små och fristående — kör dem *före* de stora sanningslager-paketen (quick wins med testskydd); (2) "canonical identity" skalas ner (alias + datumtolerans, inte spelare/arena-ID överallt); (3) CLV-fix och ledger är i praktiken ett sammanhängande schema-arbete; (4) WAL/transaktioner är en förutsättning och tar en timme — allra först; (5) mobilpolish (C9) hålls som parallellt småspår (daglig användarnytta) i stället för sist.

---

## 2. Reviderad prioriterad plan

```
WP0 → (allt)          WP1 ─→ omkalibrering T ──┐
WP2 ─→ notisvakt ─→ WP5                        ├─→ grönt-kriterium v2 (modell)
WP3 ─→ MLS-omtag ─→ WP9-ASA, B6, B7            │
WP4 ─────────────→ WP5 ─→ facit-rapport v2 ────┘
WP6/WP7/WP8 = fristående småpaket, körs i luckor
Europa-ligor (gamla D): PAUSAD tills WP0–WP5 klara
```

| WP | Innehåll | Storlek | Beroende av | Blockerar | DB-migration | Rör facit? |
|---|---|---|---|---|---|---|
| **WP0** SQLite-robusthet | WAL, busy_timeout, batch-transaktioner | **S** | — | inget (men gör först) | nej (pragmas) | nej |
| **WP1** Settlement-ankring | test-först; villkorad ankring via pair_fair; temper→ankare-ordning; omkör kalibrering | **S/M** | WP0 | trovärdiga mou/mah/m1x2-flaggor; T-omkalibrering | nej | nej (nya flaggor får ny modellversion) |
| **WP2** Pris-närvaro | last_seen_at, available, source health, åldersvakt i notiser, ålder i UI | **M** | WP0 | WP5 (availability-fält); ärliga notiser | ALTER + backfill | nej |
| **WP3** Identitet light | team_alias, merge ±1 dygn, granskningslista, dubblettvarning; MLS-rensning + omtag | **M** | WP0 | MLS-modell/B7, ASA (WP9), B6 vila/resor | ny tabell + MLS-omtag | nej (results ≠ facit) |
| **WP4** CLV-identitet | line i PK, stängning på flaggans lina, line-moved som kategori | **S/M** | WP0 | WP5, trovärdigt AH/ÖU-facit | PK-recreate (kopiera 66 rader) | **bevaras** (backup först) |
| **WP5** Prediction ledger | fasta horisonter T−24h/−3h/−20m, alla prediktioner, model_version, block-bootstrap-KI, winsorisering; ersätter gamla A2 (öppningslinje) | **M/L** | WP2, WP4 | grönt-kriterium v2; odds-band-facit (gamla A3) | ny tabell | nej (tillägg) |
| **WP6** Pool-EV | S-del: jackpot in i builder + κ̂-korrektion + UI-ärlighet. M-del: MC-portfolio med varians | **S + M** | — | — | nej | nej |
| **WP7** Benämningar | "xG-viktad Poisson + DC-korrektion", decay-text, T-status | **S** | — | — | nej | nej |
| **WP8** Insamlingsintegritet | seen-fix med retry, frånvaro-snapshots med spelar-ID, Elo-historik | **S/M** | WP0 | B5 frånvaro-modellering | meta-nycklar/ny tabell | nej |
| **WP9** Källor | ASA-verifiering + integration (efter WP3), Sofascore coverage-matrix, team-events | **S/st** | WP3 | B6 | nej | nej |

**Föreslagen ordning:** WP0+WP7+WP6-S+WP8-seen-fixen (allt S, en "städdag") → WP1 → WP2 → WP3 → WP4+WP5 → WP6-M + WP9 + T-omkalibrering → därefter beslut om Europa-ligorna.

**Vad kan göras utan risk för historiken:** allt — enda momenten som kräver försiktighet är WP4:s tabell-recreate (backup) och WP3:s MLS-omtag (rör bara `oddset_results`+seen-nycklar, aldrig `oddset_value_log`). Gamla amber-flaggor loggade före WP1 märks som äldre modellversion i stället för att raderas.

**Oförändrat från befintlig backlog:** NTFY_TOPIC (Samans steg — nu ännu viktigare eftersom A1-snabbpollen larmar inom minuter), mobilpolish C9 (parallellt), B5/B8 (efter WP8/WP5), Betsson/Altenar-champ (E13/E15, vilande).

---

## 3. Datakällematris

| Liga | Källa | Fält | Djup | Point-in-time? | Täckning | Risk | Löser konkret |
|---|---|---|---|---|---|---|---|
| MLS | **ASA API** | match/skott-xG, xPass, Goals Added, löner, domare, arenor | 2013– | efterhand | full MLS | 🔴 åtkomst ej verifierad härifrån (certfel); gratis, väletablerad | oberoende xG-kontroll av Sofascore, identitets-korsreferens, domare/arena-metadata |
| NOR (Elite/OBOS) | **Sofascore shotmap** | shot-xG + xGOT per skott | ≥ nuvarande säsonger | efterhand | ✅ verifierad 30/30 | inofficiell, 403-skydd (curl_cffi funkar) | skott-baserade features NOR; bättre hörn/xG-kvalitetskontroll |
| SWE (Allsv/Sup) | Sofascore shotmap | skottpositioner UTAN xG | — | efterhand | ❌ verifierad 0/31 | — | inget shot-xG för SWE — match-xG (statistics) förblir källan |
| Alla 6 | **Sofascore lineups** (drift) | missingPlayers, XI, spelar-ID, position, rating, marknadsvärde | live | **ja, om snapshottad (WP8)** | god (verifierad i drift) | inofficiell | frånvaro-features (B5), ✓XI-triggern, spelaridentitet |
| Alla 6 | Sofascore incidents | mål/kort/byten m. minuter | säsonger | efterhand | ej probat | inofficiell | framtida event-features (⚪) |
| Alla | **Sofascore team-events** | lagets ALLA tävlingar | ja | efterhand | ej probat | inofficiell | B6 vila/resor/rotation utan cup-blindhet |
| MLS | MLS Availability Report | officiell frånvaro/status | löpande | ja om snapshottad | ok | HTML-editorial, skör parser | officiell MLS-frånvaro (⚪/P2) |
| NOR | NFF fiksId-sidor | startelvor, bänk, arena, underlag, publik, domare | ja | delvis | ok | JS-app, kräver RE | officiella NOR-matchfakta (⚪/P2) |
| SWE | Fogis | officiella laguppställningar | ja | delvis | okänd | oklar åtkomst | officiell SWE-källa (⚪/spaning) |
| Alla | Open-Meteo Historical Forecast | väder, äkta prognos-as-of | 2016– | **ja (unikt)** | global | låg; gratis | väderfeature med korrekt PIT (⚪/P2, liten väntad effekt) |
| — | Betfair Historical | exchange-priser | djupt | ja | våra ligor tunna | konto + licensvillkor; nyttan marginell vs Pinnacle-close | skip tills konkret behov |
| SWE/NOR | ClubElo historik | dagliga ratings bakåt | 2000-tal– | ja (datum-API) | god | låg | PIT-Elo till ledger/backtest (S, del av WP8) |
| SWE/NOR/MLS | football-data.co.uk (drift) | resultat + Pinnacle-close | 2012– | close = ja | god | låg | backtest-facit (befintlig) |

Genomgående regel (Codex har rätt): **blanda aldrig providers' xG i samma fält** — egen kolumn/tagg per provider, jämför i coverage-matrixen innan någon får vikt i fitten.

---

## 4. Beslut som behövs av dig

1. **Identitet (WP3):** ok med nedskalad lösning (alias-tabell + datumtolerans + granskningslista) i stället för Codex fulla canonical layer? *(rekommendation: ja)*
2. **MLS-omtag:** ok att rensa och återhämta MLS-resultatdata (rör inte CLV-facitet)? *(rekommendation: ja)*
3. **CLV line-moved (WP4):** egen facit-kategori i stället för censur — ok? *(rekommendation: ja)*
4. **Grönt-kriterium v2 (WP5):** byt "≥50 + positivt snitt" mot "n ≥ 50 **och** undre 90 %-KI > 0 (block-bootstrap per match), per liga/marknad/modellversion"? Modellen får vänta längre på grönt — det är priset för att lita på den. *(rekommendation: ja)*
5. **Pool-EV (WP6):** jackpot-fix + κ-korrektion direkt, MC-portfolio som senare M-paket — ok? Och ok att UI:t explicit kallar nivå-EV under toppnivån för approximation?
6. **DECAY_DAYS:** behåll beteendet (240 d e-folding ≈ 166 d halveringstid) och rätta bara texten, eller ändra till äkta 240-d-halveringstid (kräver omkalibrering)? *(rekommendation: behåll beteendet)*
7. **Europa-ligorna (aug):** pausa tills WP0–WP5 är klara, enligt Codex? *(rekommendation: ja — behåll id-tabellen i plan.md som förberedelse)*
8. **Manuell spel-journal:** vill du ha en liten "mina spel"-logg i appen (skild från forsknings-facitet)?
9. **ASA:** åtkomsten failar på certnivå härifrån — ok att jag felsöker vidare (alternativ host/via browser-kontext) innan den tas in i planen?
10. **Tester:** pytest som dev-beroende i backend/.venv — ok?

---

## 5. Förslag till ändringar i docs/plan.md (EJ utförda)

1. **STATUS-blocket:** ny rad under insamlingsraden: *"Granskningsrunda 2026-07-13 (Codex + Claude-verifiering): P0 = sanningslager (pris-närvaro WP2, identitet WP3, ledger WP5) + settlement-ankring WP1 + CLV-linje WP4. Europa-expansionen pausad tills dess. Full rapport: docs/granskning-2026-07-13.md"* — plus omformulering av modellraden till "xG-viktad Poisson-styrkefit med DC-korrektion (amber)".
2. **Ny sektion "Granskningsfynd (verifierade 2026-07-13)"** direkt efter STATUS: punktlista med de sex 🔴-fynden (ankring 72 %, MLS-dubbletter 304, LA Galaxy-split, CLV-PK utan lina, seen-utan-statistik, jackpot-inkonsekvensen) med fil-referenser.
3. **Backloggen A–E skrivs om till WP0–WP9-strukturen** ur avsnitt 2 ovan, med beroendegraf och storlekar. Gamla nummer mappas: A2→ingår i WP5, A3→uppfylls av WP5-rapporten, A4→efter WP5, B5→efter WP8, B6→efter WP3+WP9, B7→**BLOCKERAD av WP3**, B8→efter WP5, C9–C11 kvar som parallellspår, D-sektionen får rubriktillägget "(startas först när WP0–WP5 är klara — beslut 2026-07-13)".
4. **Metodregler-sektionen** (delas med CLAUDE.md vid nästa uppdatering) utökas med tre regler: *(a)* asiatiska sannolikheter hanteras alltid settlement-aware (push/half-win) — ankring såväl som prissättning; *(b)* notiser kräver att bokpriset är närvaro-bekräftat i senaste varvet; *(c)* alla prediktioner loggas vid fasta horisonter med modellversion — flaggor är ett urval för handling, aldrig underlaget för utvärdering.
5. **Källtabellen** kompletteras med raderna ur avsnitt 3 (ASA "ej verifierad härifrån", shotmap-täckningen per liga, team-events, Open-Meteo, Betfair=skip).

---

## Bilaga: skillnaden bugg/risk/hypotes — hela listan

**Verifierade buggar (🔴):** ankring ej settlement-aware (72 % av linjer); temper bryter ankaret (T≠1); MLS-dubbletter (304) + LA Galaxy-split; CLV-PK utan lina; "linje flyttad"-censur (i kod); Sofascore seen-mark utan statistik (10 kända offer); jackpot utanför radoptimeringen; DECAY-kommentaren (dokumentationsfel); frånvaro/Elo utan historik (informationsförlust).

**Metodrisker (🟠):** pris-närvaro/staleness (frekvens omätbar i dag — det är bristen); grönt-kriteriets styrka (korrelation, drift, ingen kontrollgrupp, extremodds); pool-EV-approximationerna inkl. oapplicerad κ; rho/T in-sample; T-arv till tunna ligor; inga tester; commit-per-rad/ingen WAL.

**Hypoteser som kräver data (🔵):** att stale-priser genererat faktiska falska notiser (instrumentera först); T-arvets kvalitet; incidents/teamevents-värde; ASA-åtkomst.

**Framtida idéer (⚪):** full canonical layer med spelar/arena-ID; normaliserad line-CLV; väder; NFF/Fogis/MLS-report-parsers; Betfair; MC-portfolio-EV:ns percentilvy i UI.
