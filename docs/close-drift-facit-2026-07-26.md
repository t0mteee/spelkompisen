# Close-drift-facit v1 — förregistrering

Datum: 2026-07-26 (Fable 5). Godkänd insats (backlog 3b, Samans fråga om att
slå Pinnacle closing). Måtten här är skrivna INNAN utfallet räknats.
Ingen runtime-ändring oavsett utfall.

## Frågan

Closing = dagens sharp + drift. Kan observerbara signaler vid capture-
tillfället förutspå driftens RIKTNING till close? En prediktor som håller
blir en 🔮-driftradar i UI (shadow), och först därefter — via vanliga
candidate/green-trappan med riktiga bokpriser — en tipsklass.

## Kohort

- `oddset_prediction_log`, `tier='sharp'`, marknader **1x2, ah, ou**
  (hörnor för tunna — redovisas som antal, ingår inte), `fair_source =
  'pinnacle'` (aldrig derived), `fair_available=1`, `fair_fresh=1`,
  `closing_fair IS NOT NULL`, målraden `eligible=1` (timingtolerans).
- Enhet: match × marknad × lina (`line_key`) × tecken × målhorisont.
- Målhorisonter: **h3** (prediktorkälla h24) och **m20** (prediktorkälla h3).
  Momentum kräver SAMMA `line_key` i käll- och målhorisont — linjebyten
  exkluderas och räknas öppet.
- Drift `d = closing_fair − fair_prob` (målhorisontens rad), i pp.
  Dödzon: |d| < 0,25 pp räknas som flat och ingår inte i riktningsträffen.

## Prediktorer v1 (båda PIT vid målhorisontens captured_at)

- **P1 Momentum** *(primär; alla tre marknader × h3/m20)*:
  `m = fair(målhorisont) − fair(källhorisont)` för samma selektion.
  Aktiv när |m| ≥ 0,5 pp. Hypotes: fortsättning — drift åt samma håll som m.
- **P2 Frånvaro-nyhet** *(primär; endast 1X2, tecken 1/2)*:
  ny ETABLERAD frånvaro (Sofascore `appearances ≥ 5` eller okänd — samma
  regel som 🚑-siffran) registrerad i `oddset_absence_capture/player` mellan
  källhorisontens och målhorisontens captured_at, på exakt EN sida.
  Hypotes: drift MOT det drabbade laget (frånvaro hemma ⇒ '1' faller,
  '2' stiger). Båda sidor drabbade ⇒ exkluderas.
- **v2-kandidater, medvetet INTE i v1:** vilodiff/rotationsrisk (borde vara
  prisad långt före h3 — hör hemma i en h24-studie när fixturdatat mognat),
  ankaroenighet Pinnacle↔Smarkets (serien för tunn, börjar 2026-07-24),
  ⇄-linjeflytt och RLM.

## Förregistrerade mått

1. **Riktningsträff** per cell (prediktor × marknad × horisont): andel
   aktiva, icke-flata selektioner där `sign(d) == predikterad riktning`.
   Kluster-bootstrap per match, 90 % KI. Nollhypotes 0,5.
2. **Signerad drift i prediktorns riktning** (pp, winsoriserad ±5 pp),
   samma bootstrap, KI mot 0.
3. **Gate till 🔮-radar (shadow)** per cell: undre 90 %-KI för
   riktningsträffen > 0,5 OCH ≥ 30 unika matcher i den aktiva delmängden.
   Radarpassage betyder VISNING i Labb/UI som shadow — actionability kräver
   därefter vanlig trappan mätt i close-EV mot riktiga bokpriser
   (befintliga CLV-maskineriet), med signal_version-disciplin.
4. Alla celler redovisas (även negativa); inga celler väljs bort i
   efterhand. Seed 42, 2 000 bootstrap-replikat.
5. Sanity som måste hålla före tolkning: momentumcellernas kohort ska ha
   ≥ 100 aktiva selektioner totalt, annars är läsningen "samlar".

## Resultat (körning 2026-07-26, efter förregistreringen ovan)

Sanity PASS: 3 303 aktiva selektioner. **Ingen cell passerar gaten.**

| cell | n (matcher) | riktningsträff | signerad drift |
|---|---|---|---|
| 1x2 h24→h3 | 1 064 (408) | 45,8 % [41,6..50,1] | −0,06 pp [−0,23..+0,10] |
| 1x2 h3→m20 | 779 (316) | 55,3 % [47,6..63,2] | +0,02 pp [−0,08..+0,12] |
| ah h24→h3 | 384 (192) | **39,8 % [32,2..47,5]** | −0,18 pp [−0,43..+0,08] |
| ah h3→m20 | 386 (193) | 51,1 % [40,0..64,4] | −0,04 pp |
| ou h24→h3 | 328 (164) | **36,5 % [28,8..44,2]** | −0,14 pp [−0,35..+0,07] |
| ou h3→m20 | 334 (167) | 52,4 % [40,5..64,3] | −0,02 pp |
| frånvaro h24→h3 | 22 (11) | 52,6 % [27,8..77,8] | samlar |
| frånvaro h3→m20 | 6 (3) | samlar | samlar |

## Tolkning

1. **Momentum-hypotesen är FALSIFIERAD för h24→h3** — och signifikant åt
   MOTSATT håll för AH och Ö/U (övre KI-gräns under 50 %): sharpens tidiga
   skift tenderar att reversera mot close. Det är ett äkta fynd, men att
   vända hypotesen till en fade-signal EFTER att ha sett datat är exakt den
   forking-paths-fälla förregistreringen finns för. En reverseringshypotes
   får bli en EGEN förregistrerad v2 på NY data (kohortstart efter
   2026-07-26).
2. **Driftmagnituderna är små** (±0,1–0,2 pp i snitt): inom 24 h rör sig
   sharpen knappt på samma lina utom vid riktiga nyheter. Värdejakten på
   drift i det fönstret är trång per konstruktion.
3. **Linjebytena ÄR driften för parmarknader**: ~500 AH-/Ö/U-selektioner
   exkluderades h24→h3 för att linan bytt — själva bytet är den stora
   rörelsen. v2 bör studera LINJEFLYTT (⇄, riktning och storlek ur
   alt-linjelagret), inte fair på samma lina.
4. **Frånvaro-nyheten är för tunn** (28 selektioner) — samlar; utöka
   fönstret bakåt när absence-historiken vuxit.

## Konsekvens

Ingen 🔮-driftradar byggs på v1 — det hade visat brus som tips. Nästa steg
(kräver godkännande): **v2 förregistrerar** (a) reverseringshypotesen på ny
kohort, (b) linjeflytt-som-drift för AH/Ö/U, (c) frånvaro med större fönster.
Labb-vyn i v3 visar under tiden studiens status i stället för en radar.

