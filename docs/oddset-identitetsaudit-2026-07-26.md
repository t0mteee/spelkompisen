# Oddset-identitetsaudit — 2026-07-26

## Händelsen

UI:t visade **Karlsruher SC–Inter, 1 @ 6,40** som cirka +187–206 % edge.
Svenska Spels pris hörde till rätt match, men Pinnacle-identiteten på samma
canonical rad hade skrivits över med **Novara–Internazionale U23**. Kortets
matematik var korrekt på felaktigt ihopkopplade matcher och därför farlig.

Rotorsaken bestod av två oberoende fel:

1. fuzzy-matchningen tog medelvärdet av hemma- och bortalag. Ett exakt
   `Inter`↔`Internazionale U23` (1,00) kunde väga upp det orelaterade
   `Karlsruher`↔`Novara` (0,25);
2. `oddset_upsert_match` lät ett nytt externt id skriva över ett redan satt
   Pinnacle-/Kambi-id.

`bekräftat kvar` var tekniskt sant för SvS-priset men verifierade aldrig att
sharp- och bokpriset avsåg samma event.

## Auditresultat

Det strikta beviskriteriet var: samma canonical match, källa, marknad, tecken
och `fetched_at` innehåller fler än ett distinkt odds/linje-par.

- 34 matcher hade detta felmönster före saneringen.
- 15 826 kollisionsgrupper hittades.
- Fördelning: 32 träningsmatcher, 1 MLS, 1 Superettan.
- Karlsruhe stod för 231 grupper. Efter riktad rådatasanering har den 0.
- 33 äldre matcher har råhistoriken kvar för forensik (31 träningsmatcher,
  1 MLS, 1 Superettan) men läs-API:t karantänsätter dem. Alla ligger utanför
  den nuvarande UI-perioden.

Auditens största äldre fall är `svs:1025806524` Los Angeles FC–Real Salt Lake
(4 099 grupper), `pin:1632695679` Boston United–Peterborough (699) och
`pin:1632515841` Stockton Town–Darlington (602). Den fulla deterministiska
listan skrivs av
`backend/scripts/sanera_oddset_identitetskrockar.py`.

Vi relänkar inte de 33 historiska matcherna automatiskt. Rådatan bevisar att
identiteten är trasig men inte, utan respektive gamla providerpayload, vilken
av serierna som är den rätta. Att gissa skulle skapa ett nytt tyst datafel.

## Skydd som nu gäller

- Minsta likhet krävs **per lag** (0,55) och parets score måste vara ≥0,75.
- Exakt provider-id jämförs globalt och är write-once.
- Ett provider-id har ett unikt partiellt DB-index och kan inte delas av två
  canonical matcher.
- Sidoböcker och Smarkets har one-to-one-claim per insamlingsvarv.
- Läs-API:t kontrollerar canonical suffix, delade provider-id:n och samtidiga
  prisvarianter. Krock ger `data_conflict`.
- `data_conflict` stoppar värde, steam, modellfit, prediction-ledger, CLV och
  notiser för matchen. UI:t visar i stället `⚠ datakrock · inga signaler`.
- Karlsruhe–Inter och Novara–Internazionale U23 är nu separata matcher.
  Hela Karlsruhes gamla Pinnacle-livscykel togs bort; korrekt serie måste
  observeras på nytt. SvS/Expekt/Smarkets behölls.
- När ett nytt korrekt Pinnacle-varv kom in gav Karlsruhe 1X2
  `3,74/5,69/1,49` och Novara `1,80/3,33/3,70`, på varsin identitet.
  Karlsruhe fick då en reell Pinnacle-edge +25,6 % mot SvS 5,60, men det
  oberoende Smarkets-ankaret värderade samma spel till −6,9 %. UI:t märker
  därför sådana fall **OMTVISTAD EDGE / ⚓ Smarkets säger …**. Detta ändrar
  inte urvalet i smyg; tvåankargaten är fortsatt förregistrerad shadow tills
  beslutsvolymen nås.
- Databehandlingsversionen är bumpad `DATA_VERSION 2 → 3`, så facit före och
  efter identitetsfixen blandas inte under samma semantiska signalversion.

## Databasutfall

Backup:
`backend/data/backups/stryktips-2026-07-26-fore-oddset-identitet.db`.

Borttaget som ej längre styrkbart:

- 30 `oddset_value_log`
- 598 `oddset_prediction_log`
- 84 `oddset_prediction_capture`
- 103 frånvarospelarrader + 20 frånvarocaptures
- 80 falska lokala notisposter
- Karlsruhe: 1 015 Pinnacle/derived-oddsrader totalt över två idempotenta
  saneringspass och 1 354 sharp-alt-rader

Efterkontroll: `PRAGMA integrity_check = ok`, Karlsruhe har korrekt
`pinnacle_id=1632753942`, Novara har egen `pin:1632967000`, inga
Karlsruhe-kollisioner och inga signaler utan ett nytt färskt Pinnacle-pris.

## Separat live-statistikfix

GIF Sundsvall–Falkenberg doldes trots att FotMob hade skottdata, eftersom
fallbacken krävde FotMob-xG. Källvalet är nu `xG > skott/chansmått >
no_stats`; hela kortet och signalen använder samma provider. Verifierat live
vid 85 minuter: FotMob, skott 10–7, skott på mål 5–3, ingen xG. Matchen
visades och `hidden_by_league` innehöll därefter bara två träningsmatcher utan
någon chansstatistik. Ett separat regressionstest säkrar också det hårdare
fallet: en färsk FotMob-match med chansdata men ingen Sofascore-rad visas som
ett eget `fotmob:<id>`-kort. Ett andra test säkrar att FotMob-xG inte döljs i
halvtid bara för att FotMobs minutvärde är tomt; då kompletteras endast
matchklockan från den länkade Sofascore-raden, aldrig chansstatistiken.

## Verifiering

- 311 backendtester gröna.
- Frontendens produktionsbygge grönt.
- Live-API verifierat efter omstart: Brommapojkarna–Hammarby valde FotMob-xG
  `0,22–0,96` i halvtid trots tom FotMob-minut; GIF Sundsvall–Falkenberg
  visade FotMob-skott utan xG.
- `git diff --check` grönt.
