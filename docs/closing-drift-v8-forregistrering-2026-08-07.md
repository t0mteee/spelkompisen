# Förregistrering: driftjusterad closing-estimat (sharp v8)

Skriven **innan** koden ändrades. Beslut: Saman, 2026-08-07.

> "Du borde tagga till och försöka slå closing, det är vad vi är ute efter.
> Varför flaggar du inte tidigare och bättre vad du tror closing kommer vara?"

## Problemet

Värdemotorn använder Pinnacles **nuvarande** devigade pris som `fair` och
räknar `edge = fair × bokodds − 1`. Det behandlar implicit dagens pris som
stängningspriset. Det är fel, och felet är mätbart.

## Mätning 1 — Pinnacle driftar systematiskt per sannolikhetsband

10 908 parade observationer (horisontpris → stängning), 1X2, sharp-tier.
Block-bootstrap på **match** (utfallen inom en match är beroende), 90 % KI:

| Horisont | Band | n | Drift (pp) | 90 % KI | |
|---|---|---|---|---|---|
| T−24h | fav ≥50 % | 679 | **−0,607** | [−1,023, −0,185] | *** |
| T−24h | mid 25–50 % | 1349 | −0,040 | [−0,093, +0,012] | |
| T−24h | out <25 % | 1452 | **+0,321** | [+0,128, +0,508] | *** |
| T−3h | fav | 784 | **−0,625** | [−0,917, −0,350] | *** |
| T−3h | mid | 1492 | +0,010 | [−0,032, +0,054] | |
| T−3h | out | 1651 | **+0,288** | [+0,154, +0,429] | *** |
| T−20m | fav | 688 | **−0,120** | [−0,229, −0,012] | *** |
| T−20m | mid | 1360 | −0,012 | [−0,029, +0,005] | |
| T−20m | out | 1453 | **+0,068** | [+0,015, +0,120] | *** |

Driften är i praktiken **konstant mellan T−24h och T−3h** och krymper sedan
~5× till T−20m. Mittbandet har ingen effekt i någon horisont.

## Mätning 2 — biasen syns i våra faktiska flaggors utfall

471 stängda 1X2-sharpflaggor, close-EV per band (block-bootstrap på match):

| Band | n | Close-EV | 90 % KI |
|---|---|---|---|
| favorit ≥50 % | 124 | **+0,29 %** | [−0,99, +1,57] ← rymmer noll |
| mellan 25–50 % | 208 | +3,63 % | [+2,39, +4,93] |
| outsider <25 % | 139 | **+5,96 %** | [+3,08, +9,03] |

Favoritflaggorna tjänar alltså **ingenting**, precis som driften förutsäger:
vi jämför bokens pris mot ett Pinnacle-pris som är systematiskt för högt i
sannolikhet, och den falska marginalen äts upp till stängning.

## Mätning 3 — momentum är dött, och ska inte byggas

Korrelation mellan rörelse T−24h→T−3h och T−3h→stängning: **+0,020,
R² = 0,000** (3 378 tripletter). Pinnacle är en martingal inom vårt fönster.
`Close-drift v1` föll med rätta 2026-07-26, och ingen ny momentumvariant är
värd att bygga. **Driftjusteringen nedan är inte momentum** — den är en
nivåkorrigering per sannolikhetsband, inte en extrapolation av rörelse.

## Ändringen

`fair` justeras med den uppmätta driften innan edge räknas, i två tidssteg
(mätningen visar två regimer, inte en glidande skala):

```
tid till avspark ≥ 3 h:   fav −0,60 pp   mid 0   out +0,30 pp
tid till avspark < 3 h:   fav −0,12 pp   mid 0   out +0,07 pp
```

Band sätts på Pinnacles **ojusterade** fair (annars blir gränsen cirkulär).
Justeringen appliceras per tecken och normaliseras INTE om — den korrigerar
ett skattningsfel, den är ingen ny devigering.

Mittbandet lämnas orört eftersom dess KI rymmer noll i alla tre horisonter.

### Förväntad effekt

Simulerat på de 471 stängda flaggorna:

| | Flaggor | Snitt close-EV |
|---|---|---|
| Nuläge | 471 | +3,44 % |
| Driftjusterat | 417 | **+4,04 %** |
| (jämförelse: filtrera bort favoriter helt) | 347 | +4,56 % |

Driftjustering valdes framför kategorifiltrering därför att den svarar på
rätt fråga — *var hamnar closing* — och behåller de favoritflaggor som har
tillräcklig marginal för att överleva korrigeringen.

## Ärlig begränsning

Justeringens storlek är vald på **samma data som den mättes på**. Effekten i
drift blir sannolikt mindre än de simulerade +4,04 %. Därför:

1. **Ny signalversion.** Selektionen ändras, alltså byter `signal_version`
   automatiskt via `SHARP_PARAMS`-fingeravtrycket. CLV-facitet börjar om;
   äldre versioner blandas aldrig in.
2. **Ingen bakfyllning.** Historiska flaggor räknas aldrig om.
3. **Grinden är oförändrad:** ≥50 stängda per grupp OCH undre bootstrap-KI > 0
   per liga × marknad × version, på veckokadens.
4. **Ingen omjustering av koefficienterna utan ny version.** Om driften
   ändras är det en ny förregistrering, inte en tyst tweak.
5. **Utvärderingskriterium:** den nya versionen ska visa högre close-EV än
   v-föregående på jämförbara grupper. Gör den inte det inom
   `EVAL_INTERVAL_H`-kadensen är justeringen falsifierad och rullas tillbaka.

## Samtidigt: Smarkets kopplas bort som andra ankare

Mätt: Smarkets har **56 030 priser på 1X2 och noll på AH, Ö/U och hörnor**.
Den kunde därför bara mäta 225 av 931 sharp-flaggor (24 %), och 271 av de
405 "kunde inte mäta"-noteringarna är just "saknar AH"/"saknar Ö/U" — brus om
ett känt strukturellt hål.

Andra ankaret tas bort ur värdemotorn och loggen. **Spärren i
`ANCHOR_SOURCES` står kvar** — den är en säkerhetsspärr, inte en användning:
utan den blir Smarkets en spelbar bok igen, vilket gav 184 av 476 felaktiga
sharp-flaggor 2026-07-25. Insamlingen fortsätter (billig, och spärren behöver
veta vad källan är), men ingen mätning hänger på den.

Borttaget påverkar **inte** urval, edge, q eller notiser — anchor2 var per
konstruktion ren skuggmätning — och därmed inte heller signalversionen.

## Vad som INTE görs

* **2–6h-fönstret lämnas orört.** Det mäter +0,07 % close-EV mot >24h:s
  +3,09 % och <2h:s +4,00 %, men 118 flaggor är för lite för att döma ut ett
  helt tidsfönster. Mät vidare (Samans beslut).
* **Ingen momentum-/trendmodell.** Se mätning 3.
