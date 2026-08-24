# Topptips X-balans v1 — förregistrering och historisk screening

Datum: 2026-08-24. Skriven efter att Topptipset 4289 visat fyra X men **före**
den nya kandidatens historiska resultat körs. Efteråt kördes ett tekniskt
tre-omgångars smoke-test; det är inte ett resultat och användes inte för att
ändra den låsta kandidaten. Huvudkandidaten `topptips-radform-v1` har en egen
förregistrering eftersom full marknadskalibrering är ett avsiktligt trubbigt
stresstest.

## Frågan

Den faktiskt spelade 384-raderskupongen på Topptipset 4289 bar i genomsnitt
1,00 X per rad och noll rader med fyra X, trots att sharp-marknaden implicerade
2,15 X i genomsnitt och cirka 14 procent sannolikhet för minst fyra X.

Är detta bara en enskild miss, eller kan en portfölj som kalibrerar antalet X
mot marknaden förbättra träffchansen utan att förstöra radvalets beräknade och
faktiska utdelning?

## Kandidaten är låst före körningen

Version: `topptips-xbalans-v1`.

1. Samtliga `3^8 = 6 561` Topptipsrader får exakt samma EV- och
   träffchansscore som ordinarie `build_ev_system` med värdevikt 0,5.
2. Sharp-först-sannolikheten för X tas från samma analysobjekt som byggaren.
3. Poisson-binomial ger marknadens sannolikhet för exakt 0, 1, …, 8 X.
4. Kupongens 384 platser fördelas mellan dessa grupper med största-rest-metoden.
5. Inom varje X-grupp väljs raderna med högst ordinarie score.
6. Inga resultat, lag, ligaetiketter eller manuella X-bonusvärden används.

Det finns alltså ingen tröskel som har kunnat trimmas mot historiskt facit.
Ordinarie byggare lämnas oförändrad.

## Låst utvärdering

- Produkter: Topptipset Dagens, Stryk och Extra; familjen redovisas även samlat.
- Primär budget: 384 rader, samma som den motiverande spelade kupongen.
- Kohort: kompletta, ej inställda åttamatchsomgångar med odds, slutstreck,
  facit, omsättning och identifierbar åttarättsutdelning.
- Omgångar med datum 2026-08-24 eller senare är uteslutna. Omgång 4289 kan
  därför inte bli både motivation och testfacit.
- Äldsta 70 procent redovisas som utvecklingsperiod och senaste 30 procent som
  orörd holdout. Kandidaten har inga parametrar som väljs på utvecklingsdelen;
  uppdelningen mäter tidsstabilitet.
- Alla armar ser öppningsodds och slutstreck. Det är `final_only`, inte ett
  point-in-time-bevis. Endast en framtida separat nyckel kan ge det beviset.
- Historisk jackpot är inte komplett och sätts därför lika till noll för alla
  armar.

Tre armar jämförs:

1. `current`: ordinarie värderader, värdevikt 0,5.
2. `x_balanced`: kandidaten ovan, samma värdevikt.
3. `low_ev`: ordinarie byggare med värdevikt 0,0, för att direkt besvara om
   användaren kan lösa problemet med reglaget.

## Mått och beslut

Primära mått på holdout för hela Topptipsfamiljen:

- andel omgångar med exakt 8 rätt;
- parad skillnad i 8-rättsträff mellan `x_balanced` och `current`, med 90 %
  bootstrap-KI och omgången som block;
- parad ROI-skillnad, winsoriserad ±200 procentenheter med 90 % KI;
- marknadsberäknad träffsannolikhet för minst en av kupongens rader;
- systemets genomsnittliga antal X mot marknadens förväntade antal X;
- antal omgångar där det faktiska antalet X överstiger alla systemrader.

Historiken får starta en separat forward-arm om kandidaten:

1. minskar det genomsnittliga absoluta X-gapet med minst 50 procent;
2. inte har lägre punktskattad åttarättsfrekvens på holdout;
3. har högst 5 procentenheters lägre punktskattad winsoriserad ROI än current;
4. inte visar ett uppenbart tidsbrott där utveckling och holdout pekar åt olika
   håll i både träff och ROI.

Historiken får **aldrig** ensam byta standardbyggare. Skarp promotion kräver en
ny `config_key`, start på en ännu ofryst omgång och minst 40 parade
point-in-time-omgångar. Om kandidaten faller ändras inte parametrarna efteråt;
en ny idé blir en ny version.

## Reproducerbar körning

```bash
cd backend
.venv/bin/python -B scripts/backtest_topptips_xbalans.py \
  --db /sökväg/till/fixerad-snapshot.db \
  --budget 384 --bootstrap-iters 2000 \
  --json ../docs/topptips-xbalans-v1-resultat.json
```

Databasen öppnas read-only. Resultatfilen ska bära per-omgångsrader så att nya
summeringar inte kräver en ny tung körning.
