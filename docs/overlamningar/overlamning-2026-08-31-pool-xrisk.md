# Överlämning — poolens X-risk v1 och matematiskt max v2

Datum: 2026-08-31

## Kort besked

Samans observation om de spanska lågmålsmatcherna är införd som en gemensam
regel för **alla automatiska poolsystem**, inte som ett specialfall i
maxtesterna. När marknaden samtidigt visar cirka 30 procents krysschans och
låg över/under-lina får X inte längre försvinna bara för att 1 eller 2 har
bättre streckvärde.

Matematiskt max v2 är exakt 3 spikar + 1 halvgardering + 9
helgarderingar: `1^3 × 2 × 3^9 = 39 366` unika rader. V1:s 41 472-radersform
utan spikar ligger kvar som avslutad historik och skrivs aldrig om.

Detta är en framåtriktad riskregel, inte ett påstående om positiv ROI och
inte automatisk spelinlämning.

## Driftstatus

Driftsatt på servern 2026-08-31 från kodcommit `2ea3f3f`. Den additiva
databasmigreringen skapade backup, lade till totalfälten och den tomma
forwardtabellen utan historisk bakfyllning; `integrity_check=ok`. Frontend
byggdes på servern, alla fyra Spelkompisen-tjänster startades och både
`/api/health` och poolkontrollen svarade `ok`. Exakt migrationsutfall finns i
`docs/db-atgarder.md`.

## Fryst regel

Version: `pool-draw-risk-v1`.

En match skyddas när deviggad sharp X-sannolikhet är minst 29,5 procent och
Pinnacles huvudtotal är högst 2,25, eller när X-sannolikheten är minst 32
procent utan användbar total. Den första gränsen beskrivs som cirka 30
procent. Exakt bakgrund, slutlig korrigering av avrundningsklippan och
acceptans finns i `docs/pool-xrisk-v1-mathmax-v2-2026-08-31.md`.

Effekt per automatisk byggväg:

- halvgardering blir X + sannolikaste 1/2;
- vanliga matematiska/reducerade system avsätter tillgängliga garderingar
  till skyddade matcher först utan att överskrida budget;
- EV-, radform-, färg- och A/B-portföljer har ett deterministiskt X-golv på
  10–20 procent per skyddad match;
- stora full-universe-system reserverar X-kandidater innan 1,59 miljoner
  rader grovsorteras, så golvet inte faller bort före slutrankningen;
- R-system prioriterar skyddade matcher som garderingar;
- uttryckliga manuella färg-/teckenbeslut skrivs inte över i tysthet.

Om en mycket liten budget inte räcker till samtliga skydd prioriteras högst
X-sannolikhet. Systemet höjer aldrig insatsen automatiskt.

## Data och point-in-time

`Pinnacle.soccer_index()` skickar nu med den balanserade huvudtotalen från
exakt samma match som 1X2-träffen. `sharp_odds` bär aktuell senast observerad
total och den nya append-only-tabellen `sharp_total_snapshots` sparar endast
verkliga förändringar med observationstid. Inga historiska totaler bakfylls.

Migration: `backend/scripts/migrera_pool_totaler.py`. Den är additiv,
idempotent, tar SQLite-onlinebackup och kör `integrity_check`.
Produktionsutfallet är loggat i `docs/db-atgarder.md`.

Detalj-API/UI visar nu Ö/U-lina, Över-/Under-pris och om X-skyddet var aktivt
för den frysta configversionen. Historiska kuponger kan märkas ”ny regel:
X-skydd” för audit, men deras rader ändras inte.

## Nya forwardidentiteter

- ordinarie benchmark: `dr1-b*` och champion `dr1-b256-medel`;
- PH5: `ph5-v4-dr1-*`;
- matematiskt max: `mathmax-v2-dr1-b39366-*`;
- reducerat max: `reducedmax-v2-dr1-b20000-*`.

Start utan bakfyllning: Stryktipset 4969 och Europatipset 2604 för PH5/max.
Gamla benchmark-, PH5- och maxnycklar är pensionerade men fullt läsbara.
Favoritraden i PH5 förblir en orörd kontroll utan X-skydd.

Den publicerade lokala Topptipsoptimeraren v1 och PH5-v3-ablationen körs
uttryckligen med `draw_risk=False`; deras gamla resultat får inte skrivas om.
En framtida optimerare v2 får testa den nya forwardstandarden separat.

## Matematiskt max v2

Tre tydligaste oskyddade ankare blir spikar när minst tre sådana finns. Den
bästa återstående ankarmatchen blir halv och nio matcher helgarderas.
EV medel och EV högt är fortsatt separata parade researcharmar.

UI/API/hälsolarm säger nu 39 366. Den historiska v1-sidan visar fortfarande
41 472 på de gamla kupongraderna.

## Sidofix

Poolhälsan kräver inte längre snapshots eller systemfrysningar för en
framtida SvS-omgång i tillståndet `Defined`. Bara `Open` kan vara ett aktuellt
insamlingstapp. Det tar bort det falska driftlarm som sågs före arbetet.

## Verifiering

- Europatipset 2603 m20 rekonstruerat från sparade priser:
  Deportivo–Valencia 2,66/2,99/3,16 → X 32,550 procent, total 2,0;
  Celta–Athletic 2,74/3,26/2,81 → X 29,765 procent, total 2,25. Båda
  skyddas. Båda faktiska matcher slutade utan X, så regeln är inte
  facitpassad.
- 39 366 unika rader, exakt 3/1/9-form och skyddad match inte spikad när tre
  oskyddade ankare finns.
- tröskel-, saknad-total-, portföljgolv-, reducerings-, point-in-time-,
  migration-, UI- och `Defined`-hälsotester.
- hela backend: 837 tester gröna; frontend: lint, 13 tester och
  produktionsbygge gröna.

## Nästa metodiska steg

1. Låt nya point-in-time-serier frysa riktiga h3/m20-kuponger.
2. Granska i Max-tester att totalsiffran och X-vikten motsvarar prisbilden.
3. Jämför v2 endast framåt mot pensionerad v1 som historisk referens;
   blanda inte nycklar i samma ROI-grupp.
4. Ändra inga trösklar före förregistrerad minsta kohort. Avvikelser ska
   först bli frågor/audit, inte efterhandsjusteringar.
