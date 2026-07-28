# Kappa i portföljsimuleringen — utredning och konsistensfix (2026-07-28)

**Utfall: ingen ny kalibrering kördes — mätningen fanns redan (PH4).**
Detta dokument började som en förregistrering av en kappa-skattning mot
Historikfacit; kartläggningen visade att exakt den mätningen gjordes
2026-07-24 i PH4-analysen (`docs/ph4-analys-2026-07-24.md`: κ per
produkt × vinstnivå på 7 754 avgjorda omgångar, era-kontrollerad i
`docs/ph4-kalibrering-era-v2.json`, U-formsfyndet dokumenterat). Att köra
om samma skattning med ny rubrik hade varit dubbelarbete och metodbrus.

## Vad som faktiskt var trasigt

PH4:s 2024+-κ ligger sedan 2026-07-24 (commit 15c1d7c) i
`builder.KAPPA` och används av **radvalets** EV
(`builder._row_expected_value`) och frontendens `evalRows` — men
**portföljsimuleringen** (`pool_mc.simulate_pool_portfolio`, WP6) körde
kvar på okalibrerat κ = 1,00. Samma system fick alltså två olika
sanningar: radvalet räknade κ-korrigerat, portföljkortet okorrigerat
(systematiskt optimistiskt, mest på nivåerna under toppen där PH4:s hela
KI ligger > 1 även 2024+).

## Fix (2026-07-28)

`simulate_pool_portfolio` tar nu `kappa_by_tier` och `/api/system` skickar
in `builder.kappa_for(product, nivå)` per vinstnivå — samma tabell,
version `kappa-ph4-2024plus`, överallt. κ ≥ 1 sänker EV och kan aldrig
blåsa upp förväntningar (PH4:s ärlighetsargument, samma motivering som
15c1d7c). Den analytiska jämförelseraden i simuleringen κ-korrigeras
också — annars jämför portföljen mot en variant som inte finns i drift.
Skalära `kappa` finns kvar som fallback för omätta nivåer och tester.

## Vad som INTE gjordes, och varför

- **Ingen ny skattning**: PH4 äger mätningen. Nästa förbättringssteg är
  redan definierade där som kandidat A (nivå-κ som challenger i
  PH3-ledgern) och kandidat B (svansjusterad P_folk ur U-formen, egen
  förregistrering) — och PH4:s förregistrerade gate kräver ≥ 40
  utvärderade omgångar EFTER 2026-07-24 innan nya runtime-varianter
  föreslås. Det fönstret ackumulerar sig självt (~höstomgångarna).
- **Ingen utfallsberoende κ** (U-formen): kandidat B:s fråga, inte
  denna fix.

Konsistensfixen är ingen ny modellvariant — den låter en redan beslutad
korrigering (15c1d7c) verka i båda värderingsvägarna i stället för en.
