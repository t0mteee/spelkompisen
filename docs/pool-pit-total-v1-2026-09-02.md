# pit-total-v1 — Pinnacles huvudtotal point-in-time i poolen

Datum: 2026-09-02. Status: fryst före första insamlingen.

## Varför

Ö/U i poolen är i dag ENBART X-skyddet (`pool-draw-risk-v1`): total ≤ 2,25
sänker X-tröskeln från 32 % till 29,5 %. Det är en tröskelregel, inte en
modell — och den valdes på en mänsklig granskning av Europatipset 2603, inte
på uppmätt data. Frågan "hur mycket bär huvudtotalen för P(X) utöver
Pinnacles eget X-pris?" går inte att ställa förrän totalen finns fryst vid
samma horisonter som resten av PIT-datasetet.

`sharp_total_snapshots` (förändringsserie sedan 2026-08-31) och
`pool_market_capture` (presence) finns redan. Det som saknas är frysningen.

## Vad som registreras

- Ny tabell `pool_pit_total_features` med `feature_version =
  "pit-total-v1"`, horisonter h24/h3/m20 (samma `HORIZONS` och
  `TIMING_TOLERANCE_MIN` som pit-v4).
- **Syskonserie, inte ny kolumn i pit-v4.** pit-v4:s datagenererande process
  rörs inte: PH4:s Stryk-/Europa-grindar (6–11/40) fortsätter fyllas under
  sin egen version, och `pool_pit_match_features` får ingen ny kolumn.
- Presence-regeln är pit-v4:s `sharp_eligible`: en Pinnacle-capture inom
  toleransen med status matched/derived och komplett 1X2 bevisar att Pinnacle
  lästes vid as-of. Totalen är då senaste förändringspunkt ≤ capture-tiden.
  Capture utan totalpunkt ⇒ rad med `total_eligible=0` och NULL (vi frågade,
  Pinnacle hade ingen total). Ingen capture ⇒ ingen rad (vi frågade aldrig).
- `p_over`/`p_under` är power-devigade ur samma `_power_probs` som 1X2.
- Byggs i `build_recent` varje pool-varv, egen idempotens per version.
  Aldrig bakfylld: horisonter som passerat före driftsättningen får ingen rad.

## Frågan som ska ställas — inte förrän data finns

Kandidat (förregistreras skarpt i ett eget manifest när volymen finns):
`logit P(X) = a + b·ln(p_sharp_X) + c·(line − 2,5)` mot referensen
`a + b·ln(p_sharp_X)`, walk-forward per produkt, Δlogloss med
blockbootstrap per omgång — samma metod som PH4. Skörd tidigast vid **≥ 40
Topptipsomgångar med `total_eligible` på alla 8 matcher**. Grinden läggs in i
`cli.py gater` när första raden finns.

Om totalen inte tillför något (KI90 täcker noll) står X-skyddet kvar som den
riskregel det är — men då vet vi att det är en riskregel, inte en modell.
