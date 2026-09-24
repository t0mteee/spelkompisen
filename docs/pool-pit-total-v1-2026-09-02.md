# pit-total-v1 — Pinnacles huvudtotal point-in-time i poolen

Datum: 2026-09-02. Status: fryst före första insamlingen.

**Datumnot 2026-09-14 (Samans beslut: samma version, ingen pit-total-v2).**
Insamlingen rättades utan att presence-regeln ändrades: fönstret ± toleransen,
bygge först när fönstret stängt + 16 min, ett Pinnacle-index per basvarv,
Oddsets namnregel i poolmatcharen (`docs/pool-tackning-2026-09-13.md`,
`overlamning-2026-09-13-pooltackning.md`). Omgångar före 2026-09-14 är
samlade under den glesare regimen (h3: 2/40 kompletta Topptipsomgångar) —
redovisa datumet vid skörd, blanda inte regimerna i samma bootstrap utan att
säga det.

## Varför

**Datumnot 2026-09-24, pool-name-v6:** i drift från 2026-09-24T19:51:01Z. Poolmatcharen lägger
truppmarkörer ur Pinnacles liganamn (U15–U23, damformer, reserv- och ungdomsligor) på
kandidatens lagnamn. En U21- eller damrad med samma lagnamn och avspark kan därför
varken göra seniormatchen tvetydig eller länkas i dess ställe. Inga av dagens länkar
ändrades. Tidsankare, nivåer och trösklar är oförändrade; skilj v5/v6 vid skörd.

**Datumnot 2026-09-24, pool-name-v5 (Samans beslut 1A):** i drift från 2026-09-24T14:30:53Z, första basvarv 14:57Z. Poolmatcharen kräver med känd
SvS-avspark en Pinnacle-avspark inom 15 min och väljer på nivå (exakt,
exakt + generiskt delnamn, delnamn båda, stavning). Landslag känns igen på
svenskt landsnamn och matchas bara exakt; klubbar får aldrig landsnamn.
Samtidigt använder m20-reserven redan hämtade svar när budgeten är slut.
Total och 1X2 följer fortfarande samma match-id. Ingen ny oddskälla eller
historisk bakfyllning; skilj v4/v5 vid skörd.
Se `docs/overlamningar/overlamning-2026-09-24-poolnamn-v5.md`.

**Datumnot 2026-09-21, pool-name-v4:** två belagda kopplingar i Topptipset
4346 rättas (Cuiaba Esporte/Cuiaba och kontextbundet Estudiantes/La Plata
mot Lanus med känd avspark ±15 min). Total och 1X2 följer samma match-id.
Ingen ny oddskälla eller historisk bakfyllning; skilj v3/v4 vid skörd.
Se `docs/overlamningar/overlamning-2026-09-21-poolnamn-v4.md`.

**Datumnot 2026-09-21, pool-name-v3:** åtta poolspecifika alias rättar
belagda namnfel från Stryktipset 4971. Hörn-/kort-event får inte länka
målodds; fem avvisade sökledtrådar sparas i stället för bara en. Tolerans,
presence och gamla frysningar oförändrade. Redovisa regimen vid skörd.
Se `docs/overlamningar/overlamning-2026-09-21-pool-odds-reducering.md`.

**Datumnot 2026-09-15, pool-capture-v2:** begränsad per-match-reserv före
m20 observerar 1X2 och huvudtotal atomiskt, på exakt samma provider-id.
Giltig HTTP Age och ursprunglig tidsregel krävs. Ingen bakfyllning eller
ändring av eligibility; redovisa den nya insamlingsregimen vid skörd.
Se `docs/overlamningar/overlamning-2026-09-15-poolkadens.md`.

**Datumnot 2026-09-15:** `pool-name-v2` stoppar obekräftade delnamn och
tvetydiga kandidat-/orienteringsval även för totalen (samma fysiska match
som 1X2). `ambiguous` innebär inga kopplade odds. Samma serie enligt
insamlingsbeslutet ovan; ingen bakfyllning. Redovisa datumet vid skörd.
Se `docs/overlamningar/overlamning-2026-09-15-poolmatchning.md`.

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
