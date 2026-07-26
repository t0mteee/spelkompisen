# Devig-ablation: power vs proportionell vs Shin — förregistrering

Datum: 2026-07-26 (Fable 5). Godkänd insats (backlog C2). Måtten i denna
sektion är skrivna INNAN något resultat räknats. Uppföljningen som
rekommenderades i `docs/tva-ankare-2026-07-25.md`: två ankare-mätningen testar
ankar-oenighet — detta testar devigmetodens EGET bidrag, helt offline på
Pinnacles egna priser. Ingen runtime-ändring; `SHARP_PARAMS` orörd.

## Frågan

Flaggtröskeln är 2 % medan devigmetodvalet flyttar fair med ~3 pp. Hur stor
del av de loggade sharp-1X2-flaggorna finns bara därför att vi valde
power-metoden — och presterar de metodberoende flaggorna sämre mot close?

## Kohort

- `oddset_value_log`: `tier='sharp'`, `market='1x2'`, `closing_fair IS NOT
  NULL`, `first_odds` sparad.
- Pinnacles råa 1X2-trio rekonstrueras ur förändringsserien `oddset_odds`
  (source=pinnacle): per tecken sista prisändring med `fetched_at ≤ T`, där
  T = `first_at` respektive matchstart (stängningsregeln: sista ändring före
  avspark). Flaggor där trion inte kan rekonstrueras vid båda tidpunkterna
  exkluderas och RÄKNAS ÖPPET.
- Selektionsbias erkänd: kohorten valdes under power. Ablationen svarar på
  "hur många av VÅRA flaggor är devig-artefakter", inte "vilka flaggor hade
  metod M valt fritt".

## Metoder

- **power** (dagens): lös k så att Σ(1/odds)^k = 1 — projektets `_power_probs`
  återanvänds, ingen tredje implementation.
- **proportionell**: p_i = (1/odds_i) / Σ(1/odds).
- **Shin**: p_i = (√(z² + 4(1−z)·π_i²/B) − z) / (2(1−z)) med π_i = 1/odds_i,
  B = Σπ; z löses med bisektion så att Σp = 1.

## Förregistrerade mått

1. **Sanity-grind före tolkning:** rekonstruerad power-fair vid first ska
   matcha lagrad `first_fair` (median |Δ| < 0,5 pp). Faller den är
   rekonstruktionen fel och inget annat får tolkas.
2. **Överlevnad per metod:** andel flaggor med
   `p_M(first) × first_odds − 1 ≥ 2 %` (= `EDGE_LOG`, samma tröskel som
   loggningen).
3. **Close-EV per metod:** `p_M(close) × first_odds − 1`, winsoriserad ±20 %,
   kluster-bootstrap per match, 90 % KI — exakt `_tier_stats`-estimanden.
4. **Huvudjämförelse:** close-EV (power-estimanden, punkt 3 med M=power) för
   (a) flaggor som överlever ALLA tre metoder mot (b) flaggor som bara
   överlever power. Om (b) har klart sämre close-EV än (a) är
   devig-tvetydighet en äkta filtersignal (stöder tvåankartanken); om inte,
   blåser power inte upp facitet.
5. Seed 42 för bootstrap; 2 000 replikat.

## Beslutsregel

Detta är en forskningsläsning, ingen gate: ingen runtime-ändring oavsett
utfall. Ett eventuellt "kräv överlevnad under flera devigmetoder"-filter är en
selektionsändring som kräver signal_version-bump och går via samma
förregistrerade process som två ankare-gaten (n ≥ 50, veckokadens).

## Resultat (körning 2026-07-26, efter förregistreringen ovan)

Kohort: **172 stängda flaggor, 89 matcher, 0 exkluderade** (trion kunde
rekonstrueras för samtliga). Sanity-grinden PASSERADE med marginal:
median |rekonstruerad − lagrad first_fair| = **0,002 pp**.

| metod | överlever ≥ 2 %-tröskeln | close-EV (egen fair, alla 172) |
|---|---|---|
| power (dagens) | 172/172 (100 %)* | +3,09 % [+1,90..+4,37] |
| Shin | 148/172 (86 %) | +3,32 % [+2,20..+4,55] |
| proportionell | 125/172 (73 %) | +3,76 % [+2,64..+4,93] |

\* per konstruktion — flaggorna loggades under power.
Kolumn 3 jämför INTE metoder mot varandra (varje metod dömer mot sin egen
close-fair); den visar bara att facitet är positivt under alla tre.

**Huvudjämförelsen (förregistrerat mått 4, power-estimand för båda grupperna):**

- **Överlever alla tre metoder: 125 flaggor / 70 matcher —
  close-EV +4,40 % [+2,54..+6,14].**
- **Bara power: 24 flaggor / 23 matcher —
  close-EV −0,49 % [−3,50..+2,45].**

## Tolkning

27 % av flaggorna överlever inte proportionell devigning, och de
metodberoende flaggorna bär i snitt INGET värde (punktestimat under noll, KI
över noll kan inte uteslutas men konsensusgruppens undre KI-gräns ligger klart
över hela bara-power-gruppens punktestimat). Devig-tvetydighet är alltså en
äkta filtersignal — samma mönster som två ankare-mätningens första flagga
(Pinnacle +2,6 % / Smarkets −0,4 %). Facitets +2,4–3 % är INTE en
devig-artefakt: konsensuskärnan är starkare än helheten, inte svagare.

## Konsekvens (ingen runtime-ändring nu)

Fyndet KONVERGERAR med två ankare-spåret: båda pekar mot ett konsensusfilter
vid selektion. Beslutet tas när två ankare-gaten utvärderas enligt den
förregistrerade regeln i `docs/tva-ankare-2026-07-25.md` (n ≥ 50,
veckokadens): om gaten promoteras bör multi-devig-överlevnad värderas som del
av SAMMA signal_version-bump (en bump, inte två). Fram till dess ändras
ingenting — flaggvolymen och facitgrupperna är heliga.

