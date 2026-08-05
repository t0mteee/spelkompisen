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

### Huvudproblemet, verifierat: allt synligt CLV-facit är historiskt

Aktiv sharp-signalversion är **`s-cc671efd`** (ledgerns `active_version`).
CLV-API:ts grupper innehåller versionerna `legacy`, `s-0f1355fb`,
`s-327b148a`, `s-776ca0e0`, `s-95e14fca`, `s-c32b7065` + sju m-versioner —
**inte en enda rad från den aktiva versionen** (den har inga stängda flaggor
ännu; versionsbytena 2026-08-01→05 följde av alias-/koherensfixarna, precis
som kohortregeln kräver).

Signal-facit-kortet visar därför 26 liga × version-rader där ALLA är
inaktuella, utan någon markering av det. Allsvenskan ensamt har sex rader
(legacy + fem hashar). Läsaren kan inte se:

- vilken rad som gäller NU (ingen — men det syns inte),
- när en version var aktiv (inga datum i CLV-grupperna),
- vad `s-0f1355fb` betyder (fingeravtryck förklaras ingenstans i UI:t).

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

(Fylls i efter Samans genomgång av Del 1.)

Föreslagna beslutspunkter:

1. **Aktiv version först.** Öppet läge visar bara aktiva versionens rader per
   primärgrupp (+ ärlig "inga stängda ännu"-rad). Historiska versioner bakom
   "visa historik"-toggle, märkta med datumintervall i stället för enbart hash.
   Gäller Signal-facit, Modell mot close-griden och 184-gruppstabellen.
2. **Slå ihop 💰 Signal-facit + 🎯 Utfalls-facit** till ett kort — samma API,
   samma spår (sharp-facit); utfalls-ROI är redan bara display.
3. **Tabellhygien som Historik:** filter (liga/status/endast aktiv) +
   `SortableTable` + 20 rader med "visa alla" där det går.
4. **Poolforskningskorten** (pit-v4, PH5, startOdds): flytta till Historik
   enligt ytgränsen, alternativt behåll som uttryckligt "arkiv"-avsnitt.
5. **Lågt-n-spärr i display:** ROI/KI visas som "för tidigt (n=2)" under en
   liten gräns i stället för −100 %.
6. **Ordlista/klartext:** synlig en-radsförklaring per kort i stället för
   enbart tooltip; pluralfel och `t=`-kalibrering får läsbar form.

## Del 3 — EFTERLÄGET

(Fylls i efter ombyggnaden: samma mätningar som Del 1.)
