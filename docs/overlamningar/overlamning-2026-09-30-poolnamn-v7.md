# Överlämning 2026-09-30 — pool-name-v7 (driftsatt 2026-09-29T23:47:34Z)

## Uppdrag och beslut

Saman frågade 2026-09-30 vilka Topptipsodds som inte samlats in. Genomgången
fann att kvällens omgång 4359, damernas Champions League, hade 2 av 8 matcher
länkade till Pinnacle fastän fyra av de sex olänkade raderna fanns i Pinnacles
index med exakt avspark. Saman frågade varför det inte gick att rätta inne i
v6 (svar: det går, men ändringen måste bära nytt namn och tidpunkt för att
täckningen ska gå att läsa regim för regim) och beslutade "Ok" på v7 med
dam-regeln och tre namnluckor i samma version.

## Problemet i v6

v6 lägger truppmarkörer ur Pinnacles liganamn på kandidatens lagnamn. Ligan
"UEFA - Women's Champions League" gav "Hacken women", Svenska Spels namn
"Häcken" saknade markör, och truppregeln avvisade. Kommentaren i koden sade
att en dammatch hos SvS inte länkas "som v5", men det stämde bara för märkta
namn (Rangers LFC): omärkta namn (Häcken–Juventus, Lyon–Chelsea) länkade i v5
på nivå A. Topptipset har haft damcupen tre gånger sedan 22/9 (4347, 4348,
4359, 12 matcher) och matchdagarna fortsätter varje onsdag i höst.

Svenska Spels egen praxis (hela poolhistoriken): damlandslag skrivs ALLTID med
"Dam" (Kina Dam 12 matcher, Ryssland Dam 5, Wales/Chile/Tjeckien Dam …),
damklubbar med WFC/LFC/Ladies/dam eller ingenting alls, ofta bara på ena laget
("Paris FC – Arsenal WFC", "Tjeckien Dam – Spanien").

## Regeln pool-name-v7

1. **SvS egna damformer är truppmarkörer.** `_norm_team` normaliserar tokens
   Dam/Damer/Women/Ladies/WFC/LFC/Frauen/Femenino m.fl. till `women`, så
   "Rangers LFC" = "rangers women" och `_squad` ser markören. En damform på
   ena laget gäller matchen: båda SvS-namnen får markören innan kandidaterna
   byggs. Ett märkt SvS-lag länkas därför aldrig till en omärkt Pinnacle-rad,
   på någon väg (även Bomben och v4-vägen, där ligan inte läses).
2. **Ligans dammarkör är veto för landslag och för märkta SvS-namn** (som v6):
   "Kina – Japan" länkas aldrig till en damrad, "Kina Dam – Japan Dam" bara
   till en damrad.
3. **För omärkta klubbnamn är ligans dammarkör en skiljeregel:** damrader ur
   ligan kvalificerar utan markören men flaggas; finns en herrrad som
   kvalificerar på NÅGON nivå inom ankaret faller alla damrader bort (v6:s
   val, även när herrraden ligger på lägre nivå). Först utan herrrad
   konkurrerar damraderna sinsemellan på vanligt sätt (två ⇒ `ambiguous`).
4. **U-åldrar, reserv och ungdom är veto överallt**, som i v6. En damliga med
   U19 i namnet länkas aldrig till ett omärkt namn.
5. Tidsankare (±15 min), nivåer A/B/C/F, trösklar, ISO-regler, presence och
   bakfyllning är oförändrade.

## Aliasen

| SvS | Pinnacle | Belägg |
|---|---|---|
| Sporting Jax | Sporting Club Jacksonville | 4360 #6, exakt avspark, stavning 0,579 strax under 0,60; namnet ensamt i indexet sedan 14/9 |
| Junior | Junior de Barranquilla | 4360 #8, exakt avspark; SvS "Junior" i alla 8 poolmatcher sedan maj = den colombianska klubben; inget annat lag normaliseras till "junior" |
| Estudiantes mot Platense | Estudiantes de La Plata | 4361 #2, exakt avspark; kontextalias som för Lanús |

## Tester

`tests/test_pool_name_v7.py` (nytt): normaliseringen, damklubb utan/med
herrrad, herrrad på lägre nivå vinner, två damrader tvetydiga, U19/reserv/
ungdom veto, SvS-märkning länkar bara damrad (även ensidig och speglad),
damlandslag med och utan Dam, aliasen, Bomben/v4-vägen, sharp_service
änd-till-änd. `test_pool_name_v6.py` uppdaterad där v7 ändrar utfallet
(Chelsea–Arsenal WSL utan herrrad, Pachuca–Santos Liga MX Femenil, "Chelsea
Dam"); landslagsfallen är oförändrade. Versionssträngen i v5-, v6- och
4346-testerna. Hela kontrollen grön: backend, lint och frontend.

## Offline-prov (matcharen som ren funktion, Pinnacles rader ur diagnostiken)

| Fall | v6 | v7 |
|---|---|---|
| Häcken–Juventus mot damcupsraden | avslag | A |
| Lyon–Chelsea | avslag | A |
| Paris FC–Arsenal WFC | avslag | A |
| Rangers LFC–Hammarby mot damrad / herrrad | avslag / avslag | A / avslag |
| Benfica–Bayern München | avslag | F (stavning München/Munich) |
| Kina–Japan omärkt mot damrad | avslag | avslag |
| Kina Dam–Japan Dam mot damrad / herrrad | avslag / avslag | A / avslag |
| Miami FC–Sporting Jax, Atlético Nacional–Junior, Platense–Estudiantes | avslag | A |
| Boca Juniors mot Junior de Barranquilla | avslag | avslag |

## Driftsättning

Byggd i egen arbetskopia (worktree) tills kontrollen var grön, eftersom
pool-ticken kör ocommittad kod inom fem minuter. Commit `626f604`, ff-merge
till main 2026-09-29T23:47:34Z (i drift för nästa pooltick), backend
omstartad 23:47:39Z, push genom kroken (allt grönt).

## Första basvarvet med v7 (2026-09-29T23:57:43Z)

| Omgång | Sista varvet med v6 | Första varvet med v7 |
|---|---|---|
| Topptipset 4359 (damernas CL) | 2 av 8 | 6 av 8 |
| Topptipset 4360 | 5 av 8 | 7 av 8 |
| Topptipset 4361 | 4 av 8 | 5 av 8 |
| Europatipset 2612 | 13 av 13 | 13 av 13 |
| Topptipset Extra 1871 | 8 av 8 | 8 av 8 |

Av de 45 matcherna i de öppna omgångarna hade 38 oförändrad status och de sju
ändrade gick alla från `not_listed` till `matched`: Häcken–Juventus, Paris FC–
Arsenal, Lyon–Chelsea och Benfica–Bayern Munich (dam-regeln) samt Miami FC–
Sporting Club Jacksonville, Atlético Nacional–Junior de Barranquilla och Platense–
Estudiantes de La Plata (aliasen). Ingen länk tappades. Kvar olistade hos Pinnacle:
Malmö FF–St. Pölten och Rangers LFC–Hammarby (ingen kandidat alls i diagnostiken,
alltså Pinnacles lucka), Panama–Nya Zeeland och de tre landskamperna 2/10.

## Regimgräns att redovisa vid skörd

**2026-09-29T23:47:34Z** pool-name-v7: pit-v4, pit-total-v1 och PH3 (fler
länkade damklubbsmatcher; herrmatcher oförändrade). Datumnot i
`docs/pool-ph4-forward-manifest-v3.json` och `docs/pool-pit-total-v1-2026-09-02.md`.

## Kvarvarande risker och avslag

- Herr- och damrad med samma lagnamn inom 15 minuter: herrraden vinner, som
  i v6. Om SvS-matchen är dammatchen blir det fel odds — samma exponering som
  v6 hade, inte ny.
- Ett omärkt damlandslag hos SvS länkas aldrig (SvS skriver Dam, så det är
  avsiktligt).
- Estudiantes får bara kontextalias per motståndare; ett generellt alias är
  Samans beslut (se backlog punkt 20).
- Malmö FF–St. Pölten i 4359 fanns inte i Pinnacles index alls.
- Bayern München mot Pinnacles "Bayern Munich" länkar på nivå F (stavning),
  inte A; ett poolalias vore renare men är inte belagt bortom denna match.

## Filer

`backend/app/odds_provider.py`, `backend/app/pinnacle.py`,
`backend/tests/test_pool_name_v7.py`, `backend/tests/test_pool_name_v5.py`,
`backend/tests/test_pool_name_v6.py`, `backend/tests/test_pool_names_4346.py`,
`docs/pool-ph4-forward-manifest-v3.json`, `docs/pool-pit-total-v1-2026-09-02.md`,
`docs/plan.md`, `docs/backlog.md`, `CLAUDE.md`.
