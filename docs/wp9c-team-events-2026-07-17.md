# WP9c — alla lagtävlingar, vila och reseproxy

Körd 2026-07-17. Paketet samlar Sofascore-lagmatcher från alla tävlingar men
ändrar inte live-modellen, tipsen, signalerna, UI:t eller notiserna.

## Varför lagflödet behövs

Ligans vanliga eventflöde ser inte alltid cup, Europa eller träningsmatcher.
Vila och matchbelastning blir då fel. Sofascores
`/team/{team_id}/events/last/{page}` verifierades i drift och innehåller samma
lags matcher över tävlingsgränser. `/team/{team_id}` ger lagets basarena och
koordinater.

Varje aktivt lag upptäcks via verifierat fotbolls-UT och aktuell säsong. Sport
måste vara `football`; den tidigare OBOS-handbollsläxan skyddas dessutom genom
att tournament-ID nu ingår i säsongscachen. Ett gammalt cachevärde för UT 1420
kan därför inte återanvändas för fotbollens UT 22.

## Point-in-time-kontrakt

Fyra additiva tabeller sparar lag, ligascope, lyckade lagcaptures och unika
event. Varje event bär `first_seen_at` och `last_seen_at`. En featureläsning
kräver båda:

- eventets avspark är före `as_of`;
- `first_seen_at <= as_of`.

Backfillen kan därmed hjälpa alla framtida matcher, men kan aldrig användas som
bevis för vad systemet visste före 2026-07-17. Lyckat tomt svar sparas som en
capture. Ett misslyckat lag skapar ingen capture och retryas nästa pass; redan
lyckade lag hämtas inte igen förrän deras 20-timmars-TTL löpt ut.

Ordinarie drift hämtar en historiksida per lag. Engångsbackfillen hämtade två.
Lagdetaljer/arenor uppdateras högst var 30:e dag. Captures stämplas med
policyversion; första backfillen är `wp9c-6818e9c7`, medan den slutliga
feature-/identitetspolicyn är `wp9c-35c856d5`.

## Features som nu kan beräknas

För en kommande match och ett uttryckligt `as_of` kan lagret ge:

- senaste kända match och tävling;
- kickoff-till-kickoff-vila i timmar, även över uppehåll längre än 35 dagar;
- antal matcher senaste 7, 14 och 30 dagarna;
- matcher utanför huvudligan senaste 14 dagarna;
- om senaste matchen var borta;
- basarena-till-basarena-avstånd med haversine.

Resan är avsiktligt märkt `club_base_to_club_base`. Den är en proxy för den
kommande bortalagsresan, inte ett påstående om exakt arena. Neutralplan och
flyttade matcher löses inte tyst till hemmalagets arena.

## Första produktionsaudit

Databasen innehåller 94 aktiva lag, 94/94 med arenakoordinater, 94 lyckade
lagcaptures, 5 533 fångade lag-eventposter och 3 329 unika matcher i 24
tävlingar. Eventspann: 2024-10-12 till 2026-07-17.

| Liga | Lag/arena/fresh | Unika event för aktuella lag | Tävlingar | Utanför huvudligan | Kommande mapping |
|---|---:|---:|---:|---:|---:|
| Allsvenskan | 16/16/16 | 671 | 9 | 339 | 8/8 |
| Eliteserien | 16/16/16 | 661 | 9 | 330 | 8/8 |
| Superettan | 16/16/16 | 708 | 6 | 382 | 8/8 |
| OBOS-ligaen | 16/16/16 | 687 | 6 | 354 | 8/8 |
| MLS | 30/30/30 | 1 039 | 10 | 312 | 16/16 |

Ligatabellens event kan överlappa när lag möts över scope; 3 329 är den globala
unika totalsiffran. För de 48 kommande matcher som fanns vid slutauditen hade
**48/48 komplett vila, belastning, lagidentitet och reseproxy**, utan fuzzy-
automerge. MLS:s långa VM-uppehåll hittade och rättade en tidig 35-dagarsgräns.

## Begränsning och nästa beslut

WP9c är nu ett datainsamlingslager, inte en modellförbättring. Features kopplas
inte in förrän forwardhistorik finns och ett separat experiment har egen
coverage-matris, saknas-policy och fryst dom. Vi använder inte samma V2.1-test
för att prova dem i efterhand.

Kommandon:

- `cd backend && .venv/bin/python -B cli.py teamdata`
- `cd backend && .venv/bin/python -B cli.py teamdata backfill obosligaen`
