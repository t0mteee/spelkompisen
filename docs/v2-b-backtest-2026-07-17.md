# Modell v2-B — ridge-motor och första utvecklingsdom

Körd 2026-07-17. Paketet ändrar inte live-modellen, UI, signaler eller notiser.
Det implementerar den förregistrerade residualmodellen och vägrar gå vidare
till V2-C eftersom underlaget inte klarar domen.

## Metod

V2 är multinomial ridge-logistik med Pinnacle som **offset**:

`p_v2 = softmax(log(p_sharp) + delta(features))`

Med alla koefficienter noll är V2 exakt marknadsidentiteten. Två logiter
(1 mot X, 2 mot X) fittas med deterministiska Newtonsteg och backtracking.
Kryss är referensklass. Ridge krymper alla feature- och ligakoefficienter;
endast den globala outcome-intercepten är opåverkad.

Förregistrerade inputs, inga tillägg eller feature search:

- fristående modell minus sharp i logitrymd (två frihetsgrader);
- xG-viktad attack- och försvarsskillnad;
- hemmafördel;
- minsta effektiva laghistorik, log-transformerad;
- största dataålder, log-transformerad;
- PIT-Elo-skillnad;
- ridge-krympt Eliteserien-indikator.

Varje kontinuerlig feature standardiseras endast på respektive träningsfönster.
Missing får neutral träningsmedel-imputation efter standardisering (`0`) plus
egen indikator. Raden tas aldrig bort på grund av saknad xG/Elo.

Nested walk-forward använder UTC-matchdagen som odelbart block:

- yttre development: minst 240 träningsmatcher, därefter 60 per testblock;
- inre val: högst tre expanderande fönster med minst 120 train + 40 val;
- ridge-grid: `0,001 / 0,01 / 0,1 / 1 / 10`;
- lambda väljs enbart på inre logloss; yttre blockets utfall är osynligt;
- match-ID får aldrig finnas i både train och test.

Primärt mått är parat `logloss(sharp) − logloss(v2)` med 90 % matchblock-
bootstrap. Brier och 1/X/2-kalibrering är vakter. Träff och ROI redovisas men
kan inte godkänna modellen.

## Äkta fixed-horizon-data

Prediction-ledgern har ännu **0 avgjorda, research-ready developmentmatcher** i
V2-ligorna. `cli.py v2backtest` returnerar därför `STOPP` för h24/h3/m20 och
tränar ingenting. Det är korrekt beteende; fyra kommande matcher får inte göras
om till historiskt facit.

## Historiskt upper-bound-stresstest

Football-data SWE/NOR kontrollerades först för Pinnacle-opening. De aktuella
filerna innehåller inga användbara `PSH/PSD/PSA`-rader alls (0/1 640 från 2023),
men har Pinnacle-closing. Closing används därför endast som ett namngivet,
senare **marknads-upper-bound**. Det är inte T−24 h/T−3 h/T−20 min och är
hårdkodat spärrat från promotion.

Proxybegränsningar utöver tidpunkten: historiska features är retrospektivt
rekonstruerade, målmodellen saknar liveflödets sharp-Ö/U-ankare och nuvarande
temperaturer är in-sample. Ett positivt resultat hade alltså fortfarande inte
räckt för V2-C.

Coverage:

| Liga | Källrader | Från 2023 | Pris+modell | Pris saknas | Modell saknas | xG-overlay |
|---|---:|---:|---:|---:|---:|---:|
| Allsvenskan | 1 061 | 819 | 688 | 113 | 18 | 572 |
| Eliteserien | 1 063 | 821 | 651 | 131 | 39 | 578 |

Nested-resultat: 1 339 eligible matcher, 1 097 strikt out-of-development-
prediktioner i 18 yttre foldar.

| Segment | n | Δ logloss sharp−V2 | Δ Brier V2−sharp |
|---|---:|---:|---:|
| Totalt | 1 097 | **−0,00126** | +0,00049 |
| Allsvenskan | 564 | +0,00168 | −0,00099 |
| Eliteserien | 533 | −0,00437 | +0,00205 |
| Kompletta features | 502 | +0,00230 | — |
| Minst en missing-feature | 595 | −0,00426 | — |

90 % KI för total Δ logloss: **[−0,00745, +0,00511]**. Modellen är alltså
varken bättre i medel eller statistiskt säker. Den svaga Allsvenskan-vinsten
äts upp av Eliteserien och av rader med ofullständig historisk featuretäckning.

Ridge valdes starkt konservativt: av 1 097 prediktioner kom 759 från foldar där
`λ=10`, 78 från `λ=1`, 130 från `λ=0,1`, 64 från `λ=0,01` och 66 från
`λ=0,001`. Det visar att inre validering oftast ville ligga mycket nära
marknaden.

- Träffprocent sharp/V2: 53,33 % / 53,42 %.
- Förregistrerad edge+q-redovisning: 961 markeringar, ROI +0,70 % mot samma
  closingpriser. Detta styr inte domen; sannolikhetsmåtten misslyckades.
- V2-kalibreringsbias: 1 `+1,3 pp` (ny abs bias `+0,6 pp`), X `−2,1 pp`
  (ingen ny abs bias), 2 `+0,8 pp` (abs bias förbättrad `−2,1 pp`). Ingen
  enskild kalibreringsvakt på 3 pp föll.
- Alla ridge-fittar konvergerade. Inga matchdagar eller match-ID:n överlappade
  train/test.

## Beslut

**STOPP — V2.1 går inte vidare till V2-C.**

Skäl:

1. datat är en closing-upper-bound, inte det frysta live-outer-testet;
2. total Δ logloss är negativ och 90 %-KI korsar noll;
3. resultatet håller inte när missing-feature-rader inkluderas.

Vi provar inte fler features, trösklar eller interaktioner mot samma testutfall.
Ridge-motorn och rapporten är klara och kan köras oförändrade när ledgerns
development- och senare outer-fönster mognar. Fram till dess fortsätter dagens
sharp-signaler och amber-modell precis som tidigare.

Kommandon:

- `cd backend && .venv/bin/python -B cli.py v2backtest`
- `cd backend && .venv/bin/python -B cli.py v2backtest proxy`
