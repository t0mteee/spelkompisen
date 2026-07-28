# PH5-uppföljning: Hamming-spridning — förregistrering (2026-07-28)

**Status: FÖRREGISTRERAD före körning.** Öppnades i
`ph5-radvalsablation-256-512-2026-07-26.md` ("gles täckning via maximal
Hamming-spridning är en egen förregistrerad framtida fråga"); detta
dokument låser den frågan. Ändringar efter körning redovisas som avvikelser.

## Hypotes

H1: Vid 13-matchsbudgetarna 256/512 rader ger **gles täckning** (maximera
minsta Hammingavstånd mellan valda rader) högre kontrafaktisk ROI än
EV-rankade värderader — täthetsanalysen visade att underskottet krymper
med radantal, dvs. att metodens rader överlappar för mycket.

H0: Spridningen hjälper inte (värderader ≥ hamming).

## Arm (deterministisk, ny)

`hamming`: ur SAMMA marknadsrankade kandidatpool som slumparmen
(topp `max(8×rader, 200)` enligt marknadssannolikhet, topp-2 tecken per
match) — starta i marknadens toppard, välj därefter girigt den kandidat
som maximerar minsta Hammingavståndet till redan valda rader; lika avstånd
bryts av högre marknadssannolikhet (lägre poolindex). Ingen slump.

## Data, estimand, gate (oförändrade från PH5 v2)

- Kohort `final_only-radval-v2`, SEED 20260725, Stryk n=223 / Europa
  n=505; budgetar 256 och 512 rader; övriga armar oförändrade.
- Estimand: parad winsoriserad ROI-differens (±200 pp) per omgång,
  block-bootstrap 90 % KI (omgången som block).
- Sanity: `slump` ska ligga klart sämst; annars underkänns körningen.
- **Gate för åtgärd:** hamming slår `varderader` med hela KI90 > 0 på
  BÅDA produkterna vid minst en budget → då förregistreras ett
  byggarexperiment (spridningsläge i UI:t) som EGEN fråga. Allt annat →
  endast dokumentation. Inga runtime-ändringar ur denna körning.

## Körning

`scripts/ph5_radvalsablation.py --product stryktipset --product
europatipset --budget {256,512} --json docs/ph5-hamming-{budget}-2026-07-28.json`

## Resultat (körd 2026-07-28→29; JSON: ph5-hamming-{256,512}-2026-07-28.json)

Parad winsoriserad differens **varderader − hamming** (negativt = hamming
bättre), block-bootstrap KI90:

| Produkt | 256 rader | 512 rader |
|---|---|---|
| Stryktipset (n=223) | **−7,0 pp [−14,2..−0,0]** | +1,4 pp [−6,7..+8,9] |
| Europatipset (n=506) | −2,0 pp [−6,5..+2,7] | +1,0 pp [−3,4..+5,7] |

**DOM: grinden passeras INTE.** Hamming slår värderaderna med hela KI:t
endast för Stryktipset vid 256 (och där tangerar övre gränsen noll) —
inte för Europatipset, och ingenting vid 512. Sanity-kriteriet är
dessutom ansträngt: slump ligger inte klart sämst (Stryk 256:
varderader−slump −5,0 pp [−11,8..+1,8]), vilket förstärker bilden från
täthetsanalysen att 13-matchsbudgetarna är brusdominerade snarare än
metodskiljande. Ingen byggaråtgärd; Stryk-256-signalen får tala igen
först i en NY förregistrering på framtida omgångar om frågan väcks.
Den ärliga byggartexten för 13-matchsspelen står oförändrad kvar.
