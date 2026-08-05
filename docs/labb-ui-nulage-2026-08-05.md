# Labb-vyn: nulägesmätning 2026-08-05

Beställare: Saman. Hans egna ord: **"svårt att förstå vad som är vad, vad som
är relevant, vad som är gammalt/inaktuellt och vad allt betyder."**

Samma metod som Historik-ombyggnaden (`docs/historik-ui-2026-08-05.md`):
detta dokument är Del 1 — nuläget mätt INNAN någon rad ändras. Del 2 (besluten)
fylls i efter Samans genomgång; Del 3 (efterläget) efter ombyggnaden.

---

## Del 1 — NULÄGET (mätt före ombyggnad)

### Sidan som helhet

Mätt i preview (1280×720, `document.body.scrollHeight`), backend :8002 med
riktiga data:

| Kort | y | Höjd | Innehåll |
|---|---|---|---|
| 💰 Signal-facit (sharp-CLV) | 104 | **1 801 px** | 27 rader liga × version |
| 🎯 Utfalls-facit (sharp) | 104 | 1 801 px | **1 datarad** (grid-sträckt mot grannen) |
| 🧭 Modell mot close och full signallogg | 1 917 | 875 px hopfälld | 15 modellkort + 5 valideringskort + två togglar |
| ⚓ Två ankare | 2 804 | 230 px | 1 rad |
| ⚡ Radar-facit och signaljournal | 3 046 | 1 093 px | regler + blindtest + grupper + diagnostik + journal |
| 6 forskningskort (`LABB_RESEARCH`) | 4 151 | 145–164 px st | statiska dok-pekare |

**Total sidhöjd 4 571 px hopfälld — 16 075 px expanderad.** Beviskortet 🧭
ensamt blir 12 379 px med båda togglarna öppna (184-gruppstabellen + 200 av
1 617 loggrader) — samma klass som Historikens omsättningstabell före
ombyggnaden (12 480 px).

### Huvudproblemet, verifierat: versioner utan aktualitetsmarkering

Signal-facit-kortet visar 26 liga × version-rader — Allsvenskan ensamt har
sex (legacy + fem hashar) — utan någon markering av vilken som gäller nu.
Läsaren kan inte se:

- vilken rad som är aktuell (uppmätt efterhand: **5 av 26** hör till aktiva
  `s-95e14fca`; resten är historik),
- när en version var aktiv (inga datum i CLV-grupperna),
- vad `s-0f1355fb` betyder (fingeravtryck förklaras ingenstans i UI:t).

**Rättelse under arbetet (2026-08-06):** första analysen hävdade att INGEN
synlig rad var aktuell, baserat på ledgerns `active_version = s-cc671efd`.
Det var fel — ledgerns fingeravtryck (captureprocessen) och value-loggens
(`oddset_value.signal_versions`) är olika namnrymder som båda råkar börja på
`s-`. Att ens en fokuserad genomläsning gjorde den korsjämförelsen är i sig
ett symtom: UI:t redovisar hashar utan att säga vilket system de tillhör.
Ombyggnaden markerar aktiv per respektive systems egen definition.

Samma mönster i Modell mot close-griden: 15 kort över fyra modellversioner
där 11 hör till äldre versioner (`m-3c7789ac`, `m-4c84fdf4`, `m-d82792f7`),
blandade med nuvarande `m-0e901a67` utan gruppering — "✕ sämre än sharp" på
en pensionerad version läses som dagens läge. Märkningen finns
("äldre"/"nuvarande" i liten text) men ordningen och mängden gör den osynlig.

### Övriga problem, verifierade

1. **Utfalls-facit-kortet är 1 801 px högt med en enda datarad** — CSS-gridens
   radhöjd sträcker det till grannens höjd. En hel skärm till höger är tom.
2. **Statuspillen kan ljuga om aktualitet.** `Signal-facit`-pillen är
   `primaryClv.some(g => g.green_ready)` över ALLA versioner — en pensionerad
   version med green_ready skulle tända GATE-PASS på kortet trots att aktiva
   versionen står på noll. (Visar SAMLAR i dag, men logiken är fel.)
3. **184-gruppstabellen saknar filter och sortering.** Ingen avgränsning på
   liga/status/version, ingen `SortableTable`, inget "aktiv version först".
   1 617-radersloggen har paginering (200 åt gången) men inga filter.
4. **Ytgränsen från 2026-08-05 bryts åt andra hållet.** Beslutet var
   Historik = 100 % pool, Labb = 100 % odds. Tre av sex forskningskort är
   pool: `📐 pit-v4` (AKTIVT pool-spår, samlar), `🎟 PH5 256/512 rader`
   (falsifierad, pool), `🔓 startOdds` (pool-kovariat). PH3-kortet togs bort
   ur Labb i går med just den motiveringen.
5. **Blindtestet visar extremvärden utan lågt-n-varning.** Över-ROI −100,0 %
   KI [−100..−100] på n=2 (v5-kohorten är 1 dag gammal). Siffran är korrekt
   men läses som katastrof i stället för "för tidigt att säga något".
   Att räknaren nollställdes med v5 sägs inte heller ut.
6. **Oöversatta/oförklarade termer i synligt läge:** `M 3,46 pp · P 0,93 pp`
   (modellens respektive Pinnacles snittfel — förklaras bara i tooltip),
   `log-score Δ`, `🌡 Kalibrering: allsvenskan t=1.02`, `1 dagar`
   (pluralfel), pillarna SAMLAR/CANDIDATE/GATE-PASS/FALSIFIERAD har tooltip
   men ingen synlig förklaring eller nästa-utvärderingsdatum.
7. **Radar-kortet är fem saker i ett** (1 093 px): statiska signalregler,
   blindtest-gate, gruppfacit, diagnostiskt providerfacit (details) och
   journal (default öppen, växer obegränsat i höjd med 12-radersgränsen
   från API:t i dag).

### Vad som INTE är trasigt

- Engångsläsningen (ingen poll) är rätt för mätserier.
- Journal-/loggdata i sig är korrekt och versionsdisciplinen i backend håller
  (kohortregeln, append-once) — det här är ett presentationsproblem.
- "INGET här är tips"-ramen och shadow-markeringarna är tydliga.
- Två ankare-kortet är kompakt och läsbart (CANDIDATE vid 206 ≥ 50 mätta
  är korrekt pill enligt förregistrerade regeln).

### Underlag som redan finns (ingen ny insamling behövs)

- Ledger-API:t bär redan `active_version`, `first_resolved_at`,
  `last_resolved_at`, `primary`, `status` per grupp — allt som behövs för
  "aktiv först, historik bakom toggle, datum i stället för hash".
- CLV-API:ts grupper saknar datum och aktiv-flagga — behöver två fält till
  (`active`, datumintervall) för samma behandling; datan finns i
  `oddset_value_log`.
- `SortableTable` med `limit` efter sortering finns sedan Historik-ombyggnaden.

---

## Del 2 — BESLUTEN

Fattade av Saman 2026-08-05 efter genomgång av Del 1. Alla sex punkter kör:

1. **Aktiv version först.** Öppet läge visar bara aktiva versionens rader per
   primärgrupp (+ ärlig "inga stängda ännu"-rad). Historiska versioner bakom
   "visa historik"-toggle, märkta med datumintervall i stället för enbart hash.
   Gäller Signal-facit, Modell mot close-griden och 184-gruppstabellen.
2. **Slå ihop 💰 Signal-facit + 🎯 Utfalls-facit** till ett kort — samma API,
   samma spår (sharp-facit); utfalls-ROI är redan bara display.
3. **Tabellhygien som Historik:** filter (liga/status/endast aktiv) +
   `SortableTable` där sortering tillför något.
4. **Poolforskningskorten** (pit-v4, PH5, startOdds) flyttar till Historik
   enligt ytgränsen — pit-v4 är dessutom ett AKTIVT poolspår.
5. **Lågt-n-spärr i display:** ROI/KI visas som "för tidigt (n=2)" under
   `ROI_MIN_N = 10` i stället för −100 %.
6. **Ordlista/klartext:** synlig statuslegend under rubriken, M/P-förklaring i
   modellgriden, `🌡 Modelltemperatur` i stället för `t=`-raden, pluralfel
   rättat, kohortrad med versionens startdatum i radarkortet.

Dessutom (samma beslut): dagsarbetet 2026-08-05 committades som två commits
(radar-kohortmigreringen respektive Historik-ombyggnaden + PH3 gen 2) och
pushades till PR #1 innan Labb-arbetet började.

## Del 3 — EFTERLÄGET

Mätt likadant som Del 1 (1280×720, `document.body.scrollHeight`, riktiga
data) 2026-08-06.

### Sidhöjd

| Läge | Före | Efter |
|---|---|---|
| Hopfälld | 4 571 px | **3 058 px** (−33 %) |
| Allt expanderat | 16 075 px | **11 925 px** (−26 %)* |

\* Expanderat efterläge inkluderar ALLA fyra togglar öppna samtidigt
(21 CLV-historikrader + 11 äldre modellversioner + 58 aktiva ledgergrupper +
200 loggrader). Ledgertabellen visar aktiva versioner som standard; kryssrutan
"visa även 126 grupper från äldre versioner" ger hela 184-listan uttryckligen.

### Punkt för punkt

1. **Sharp-facit-kortet: 1 801 → 658 px.** Öppet läge visar aktiv version
   (`s-95e14fca`, fem ligor med riktig data, t.ex. MLS 16/16 stängda +4,8 %
   KI [3,0..7,1]), raden "Alla versioner sedan start" och utfallsraden. De
   21 historiska versionsgrupperna ligger i en sorterbar tabell bakom toggle,
   med **period som datumintervall** (t.ex. `s-327b148a · 25 juli – 26 juli`)
   — sorteringen driftverifierad mot API:ts `first_at_max`.
2. **Utfalls-facit-kortet är borta som eget kort** — en rad i Sharp-facit.
   Tomrummet på 1 800 px försvann med det.
3. **Modell mot close visar bara nuvarande version öppet** (4 kort,
   `m-0e901a67`); de 11 äldre mätningarna är en kompakt tabell bakom toggle.
   "1 dagar" → "1 dag". M/P förklaras synligt i rubriken.
4. **Ledgertabellen öppnar med 58 aktiva grupper** i stället för 184 blandade;
   äldre kräver aktivt kryss. Signalloggen fick liga- och statusfilter som
   filtrerar FÖRE 200-raderskapningen (driftverifierat: MLS × stängda =
   289 av 1 617, sidan visar de 200 senaste inom filtret).
5. **Blindtestet visar "Över-ROI: för tidigt att mäta (n=2)"** i stället för
   −100 % i rött; samma spärr i gruppfacitet. Radarkortet fick kohortraden
   "`chance-gap-shadow-v5` sedan 3 aug — räknarna nollställdes vid
   versionsbytet".
6. **Ytgränsen är hel åt båda hållen:** Labb har 7 kort, alla odds; Historik
   fick sektionen `🔬 Forskningsspår (pool)` med pit-v4 (SAMLAR), PH5
   (FALSIFIERAD) och startOdds (GATE-PASS).
7. **Statuslegenden är synlig text** under rubriken; versionsbegreppet
   förklaras där i en mening.

### API-tillägg (display-only, inga grindar rörda)

- `clv_report`: `active_versions` per tier samt `active`/`first_at_min`/
  `first_at_max` per grupp (`oddset_value.py`).
- `live_settlement.facit`: `signal_version_started_at` (radarns kohortstart).

### Verifiering

- 552 backend-tester gröna; `vite build` exitkod 0; eslint har kvar exakt de
  3 kända anmärkningarna från 2026-08-04 (rad 140/662/761), inga nya.
- Driftverifierat i preview: togglar, checkbox (58 ↔ 184 rader), loggfilter,
  periodsortering, mobilvy utan horisontell scroll och med sortbar.
- Skärmbildsverktyget i browserpanelen gav svart bild under sessionen
  (panelen dold); verifieringen gjordes via DOM-mätningar och
  accessibility-trädet, som visar hela strukturen renderad.

### Kvar att göra

- Kalibreringsraden visas bara när `oddsetcalibrate` körts (oförändrat).
- `s-`-prefixet används av TVÅ fingeravtrycksfamiljer (value-loggens urval
  respektive ledgerns captureprocess) — se rättelsen i Del 1. UI:t blandar
  dem inte längre, men en namnrymdsmarkering i själva versionssträngen vore
  robustare på sikt.
