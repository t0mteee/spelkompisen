# Överlämning 2026-09-15 — pool-capture-v2, tidsluckan inför m20

## Uppdrag

Saman bad rätta den återstående tidsluckan efter `ba16dfe`. Den första
ändringen blockerades av sessionsgränsen innan något sparades; därefter
återupptogs arbetet. Bas på server och worktree: `ba16dfe`.

## Vad som ändrats

1. `pool_tick_due` tar hänsyn till ALLA öppna horisontfönster, inte bara
   30-minutersintervallet och sista två timmarna. H24/h3 kunde tidigare
   ligga öppna samtidigt som femminutersticken avstod. Inget nytt launchd-jobb
   eller nytt schema; bulkindexet delas fortsatt av hela varvet.
2. `pool_capture_refresh.capture_missing`, version `pool-capture-v2`, är en
   begränsad reserv för PIT under [m20-as-of − 10 min, m20-as-of]. Kör bara
   när en redan entydigt länkad match saknar giltig capture/bulkobservation.
   `soccer_index`/`match_index` lämnar nu vidare Pinnacles opaka match-id.
3. Reserven frågar `/matchups/{id}/markets/straight`, ett försök, 2 s timeout
   per nätverksfas. Max 13 id:n och 12 sekunders **startbudget** per delat
   varv; sista påbörjade anropet kan gå utanför budgeten. Samma id återanvänds
   mellan produkter och får högst ett nytt försök per 240 s över varven.
   Tvåsekunderstimeout är inte en hård totalgräns för hela HTTP-anropet.
4. Kräver exakt id, öppet period-0-1X2 och komplett total i samma svar.
   HTTP Age måste finnas och vara giltig. Både verklig hämtningstid och
   Age-justerad pristid ska ligga senast vid as-of; pristiden dessutom inom
   den ursprungliga tiominuterstoleransen och senare än bulkpriset.
   Inga efterhandspriser används. Saknad total ger konservativt avslag för
   att gamla totalpriser inte ska få låna ny 1X2-närvaro.
5. Odds speglas vid omvänt hemma/borta, sedan sparas förändringspunkt och
   presence atomiskt på sin egen pristid. Bulkens `hits` och `sharp_odds`
   ändras inte; dagens tips/styrke-shadow får alltså inte en utbytt payload.
   Konsumenter av sharp-historiken kan läsa de nya verkliga observationerna,
   inklusive PIT-testernas pris- och totalserier.
6. `save_sharp_snapshot` tillåter inte att en äldre bulkcache skriver bakåt
   efter en färsk reservobservation. Klockan läses över 1X2, total och
   presence — även oförändrat 1X2 räknas.
7. HTTP-hämtningstid sätts direkt när svaret mottagits, före parser/
   härledningsarbete. Tidigare poolkod använde tidpunkten före hela hämtningen.
8. Loggen skiljer nu `sharp överhoppad`, `sharp KÄLLFEL` och lyckad hämtning
   med pristid/hämtningstid/Age. Reservens attempted/captured/rejected/errors
   skrivs per omgång. Ett bulkfel delas inom varvet i stället för att upprepas
   för varje produkt; nästa varv försöker igen.

## Felsökning och begränsningar

- Topptipset 4333: as-of 16:39 UTC, senaste bulkpunkt 16:27:50, alltså 70 s
  utanför gränsen. Nästa bulkpunkt 16:43:01 var för sen. Testet reproducerar
  precis detta och visar att en riktig 16:35-observation kan fylla luckan.
- Den historiska h3-luckan 10:40–14:56 UTC var **inte en stoppad poolprocess**:
  serverns `pool-snapshot.log` visar körning var femte minut under perioden.
  Några basvarv gav sharp 0, mellanvarven avstod. Gamla loggen dolde
  skip/källfel; exakt orsaken till alla saknade sharp-observationer är därför
  inte fastställd. Den nya loggen ger evidens om det upprepas.
- Ett läsande prematchprov på servern gav rätt 1X2/total på exakt id och
  Age 502 s. Reservendpointen är alltså också cachad. Den är en extra chans
  till giltig observation, **ingen garanti**. Källstopp, tvetydig identitet,
  gamla priser eller förbrukad budget får fortfarande ge en lucka.
- Ingen manuell DB-ändring, inga tabellmigreringar och ingen bakfyllning.
  Försöksmetadata lagras av appen i `meta` som `pool_detail_attempt:<id>`
  med version, tider, Age och status. Det är senaste försöket, inte ett
  komplett append-only-försöksfacit; loggen bär varvutfallen.
- Samma `pit-v4`/`pit-total-v1` inom Samans insamlingsfix, med daterade
  manifestnoter. V2.2/lagmodell/byggarparametrar oförändrade. Vid skörd ska
  datumen för respektive insamlingsregim redovisas.

## Verifiering och drift

Riktade tester: tidsluckan, sena/gamla/ofullständiga/missande-Age-svar,
horisontgränser, ingen onödig trafik vid giltig bulk, återanvändning mellan
produkter, spegling, fel/cooldown, tids-/matchbudget, monoton historik även
med oförändrat 1X2 samt exakt id/period/status i parsern. Schedulerregression
för h24/h3 och fel-delning utan falska captures.

Före push körs hela `tools/kontroll.sh`. Servern ska ff-pullas när ren,
backendens LaunchAgent startas om, riktade tester köras där och
`/api/health` kontrolleras. Pooljobbet läser ny kod vid nästa ordinarie tick.
Inga tjänster ska startas på gamla datorn. Slutlig driftverifiering läggs
till efter leveransen.

## Nästa uppföljning

Läs `m20-reserv` och källfel i `backend/data/pool-snapshot.log`. Kontrollera
försökstider/Age i `pool_detail_attempt:<id>` och verkliga captures kring
as-of; dessa är sanningen, inte antalet lyckade HTTP-svar. Kör read-only
`scripts/pool_tackning_rapport.py --sedan 2026-09-15` efter nya avslutade
omgångar. Rapportens datumfilter gäller spelstopp, så dagens äldre horisonter
kan fortfarande höra till gamla insamlingen. Redovisa kompletta omgångar
och varje horisont separat. Behåll den planerade större skörden omkring 21/9.
