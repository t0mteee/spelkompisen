# Överlämning 2026-09-02 — Championship i Oddset och liveradarn

## Kort besked

Championship var inte trasig hos liveleverantörerna. Projektet hade medvetet
bara ligan som football-data-matarliga och saknade den i alla synliga
odds-/livekartor. Den är nu införd som en fullt följd sharp-liga och som nytt
scope i liveradarn.

## Genomfört

- `oddset.LEAGUES`: Pinnacle 1977, Kambi
  `football/england/the_championship`, Ninja/Altenar 2937.
- `smarkets.LEAGUE_SLUGS`: `england-championship`.
- Flashscore: `ENGLAND: Championship`.
- FotMob: `(ENG, Championship)`; providerliga 938218 observerades.
- Ny radarversion `chance-gap-shadow-v12` med ren start
  `2026-09-02T22:00:00Z` och explicit settlementspärr.
- Championship har normal liveprioritet 0 och kan inte klippas som en
  träningsmatch.
- Första produktionsvarvet hittade providerparen
  `Queens Park Rangers`/`QPR` och
  `Birmingham City`–`Wolverhampton`/`Birmingham`–`Wolves`. Explicita alias
  stoppar nya dubbletter; det spårbara engångsskriptet
  `backend/scripts/migrera_championship_identitet.py` slår ihop de två redan
  skapade raderna efter backup och vägrar om annat än oddshistorik hunnit
  referera till dem.
- Dynamiska liga-/UI-listor får den nya ligan utan en frontendkopia.

Alla provideridentiteter verifierades mot aktuella publika svar före
implementation. Detaljer och metodkontrakt:
`docs/radar-scope-v12-2026-09-02.md`.

## Avgränsning

`MODEL_LEAGUES`, `SOFA_UT` och V2.2:s `SCOPE_LEAGUES` är orörda. Det är
avsiktligt: liveunderlag och marknadsodds kan samlas direkt, medan en ny
xG-baserad målmodell kräver egen täckningsaudit, temperaturkalibrering och i
V2.2-fallet ett nytt manifest. Football-data `E1` fortsätter ge avgjorda
resultat.

Inga gamla liveobservationer eller priser har bakfyllts och inga riktiga spel
har lagts.

## Verifiering och drift

Gatekontrollen före den nya kohorten läste 40 grindar utan läsfel; radarens
föregående blindtest stod på 112/200 matcher och 11/30 dagar. Den gemensamma
`tools/kontroll.sh` är grön: hela backendtestsviten, frontendlint och
frontendtester passerar. Driftskvitto och produktionshash fylls på efter
serverns fast-forward.

## Nästa kontroll

Kör `cli.py lanklucka` efter första Championship-omgången som faktiskt varit
live. Bekräftade presentationsskillnader ska in i `LIVE_TEAM_ALIASES`; okända
par ska inte lösas med en generell fuzzy-regel. Målmodell/xG-historik är ett
separat beslut efter täckningsaudit, inte en del av v12.
