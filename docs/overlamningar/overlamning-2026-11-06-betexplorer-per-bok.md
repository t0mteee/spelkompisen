# Överlämning 2026-11-06 — Betfair Exchange och BetInAsia via Betexplorer

Beslut `driften-2026-11-06-betexplorer-per-bok`, val 0: "Ja: samla Betfair Exchange och
BetInAsia (1X2, Ö/U 2,5, AH) för poolligorna, högst ett anrop per match och marknad och
timme, och mät dem mot Smarkets/SBOBET innan något ankare ändras". Genomfört automatiskt
(beslut koordinatorn-2026-10-14-genomfor-beslut-automatiskt).

## Källan

Samma `/match-odds/<id>/0/<1x2|ou|ah>/odds/`-svar som bet365 läses ur
(`docs/overlamningar/overlamning-2026-11-06-betexplorer-bet365.md`). Uppmätt 2026-11-06
~11:28Z på Everton–Coventry: svaret bär 18 böcker, bland dem
`data-bookie="betfair exchange"` (börsen) och `data-bookie="betinasia"`. Sportboken
`data-bookie="betfair"` är en annan rad och läses aldrig (matchningen är exakt sträng med
avslutande citattecken). Betfair själv spärrar Sverige; här läses bara Betexplorers publika
sammanställning, inget anrop går till Betfair. `/archive-odds/` används fortfarande aldrig.

Linor i provet: Betfair Exchange 25 Ö/U-linor och 28 handikapplinor, BetInAsia 9 + 9.
Huvudlinan i handikappet var −0,75 hos alla tre (bet365 1,85/2,00, BFX 1,88/1,99,
BIA 1,95/2,04). BetInAsias handikapp hade ~0,3 % marginal, Betfair Exchange ~3,4 %
(1X2 ~4 %) — det är Betexplorers återgivna priser, inte börsens rena mitt.

## Vad som ändrats

- `betexplorer.BOOKS` = bet365, `betfair_ex`, `betinasia`. `parse_books` läser alla böcker
  ur ett svar; `Betexplorer.odds(event_id, marknad, books, referer)` returnerar
  `{bok: parsed}`.
- Ö/U: bet365 behåller huvudlinan (mest balanserad); de nya böckerna sparar EXAKT 2,5
  (`OU_FIXED_LINE`, beslutets "Ö/U 2,5"). Saknas 2,5 hos boken markeras marknaden
  unavailable — ingen annan lina sparas. Handikapp: huvudlinan för alla.
- `oddset._collect_betexplorer`: ett anrop per match och marknad, en prisrad
  (`oddset_odds`, svarets observationstid) och en presence-rad
  (`oddset_betexplorer_capture`) per BOK. Transportfel bokförs för alla tre utan att
  markera frånvaro. Källhälsa per bok och liga. Summeringen bär `listed` per bok.
- **Takten:** kortaste intervallet 25 → **60 min** (≤ 3 h till avspark), övriga 115/715 min
  oförändrade — högst ett anrop per match och marknad och timme, som beslutet kräver och
  som svarens egen `max-age=3600` antyder. Takten är gemensam: senaste anropet om matchen
  oavsett bok styr, så de nya böckerna utlöser aldrig egna anrop.
- `oddset_value.REFERENCE_BOOKS` = bet365, betfair_ex, betinasia → i `ANCHOR_SOURCES` och
  `passive_sources()`: aldrig bok att slå, aldrig ankare. `ANCHOR_BY_MARKET` (anchor-v1)
  och `sharp_params()` är orörda, alltså oförändrade sharp- och modellversioner (låst i
  `tests/test_betexplorer.py::RollTests`).
- Oddset-vyn: raderna `BFX` och `BIA` mellan SBO och 365 (1X2, Ö/U, AH), tooltip med bokens
  ändringstid; källhälsan har två nya rader.

## Mätningen (`app/betexplorer_matning.py`, `cli.py betexplorer-matning [--sedan ISO]`)

`betexplorer-matning-v1`, read-only. Varje lyckad capture där boken listades paras med
referensen SOM DEN VAR vid observationen: per tecken senaste `oddset_odds`-raden med
`fetched_at` ≤ t, bekräftad inom 45 min före t (`PRICE_MAX_AGE_MIN`) och på exakt samma
lina. Referenser: Smarkets för 1X2 och Ö/U 2,5 (Smarkets har halva linor), SBOBET för
handikapp. `available` läses inte (flaggan skrivs om på senaste raden och säger inget om
läget vid t). Mått per bok × marknad: frågat, listat, par, matcher, medel |Δp| (pp), max,
snedhet per tecken, bokens och referensens marginal, median prisålder (t minus Betexplorers
ändringstid) — det sista mäter om aggregatet släpar. Paren är inte oberoende (samma match
upp till en gång i timmen); `matcher` är underlaget. Ingen grind och inget beslut: att
göra någon bok till ankare är ett eget beslut och en ny signalversion.

## Poolligorna

Insamlingen följer Betexplorers belagda ligor (`LEAGUE_PATHS`, 15), som täcker
poolspelens Oddset-ligor (Premier League, Championship, Serie A, La Liga, Bundesliga,
Ligue 1, Champions League, Allsvenskan m.fl.). Att begränsa de nya böckerna till en
delmängd hade inte sparat ett enda anrop — samma svar bär dem. Poolmatcher i ligor utan
Oddset-rad (League One/Two m.fl.) och Europa/Conference League (inte belagda ännu) får
inget: referensen skapar aldrig matchidentiteter.

## Inte gjort

- Poolanalysen visar inte BFX/BIA (pool-reference-v1 är Smarkets/SBOBET, "bara visning");
  att lägga till dem där är ett eget val.
- Första mätningen kan läsas först när djupvarven samlat captures (de nya böckerna har
  ingen historik före driftsättningen; inget bakfylls).
