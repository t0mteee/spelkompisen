# Topptips radform v1 — förregistrering

Datum: 2026-08-24. Skriven innan `topptips-radform-v1` körs på historiska
resultat. Topptipset 4289 motiverade frågan men ingår varken i träning eller
holdout.

## Problem och hypotes

Den faktiskt spelade 384-raderskupongen på Topptipset 4289 hade i genomsnitt
1,00 X per rad och ingen rad med fyra X. Sharp-marknaden implicerade samtidigt
2,15 X och cirka 14 procents sannolikhet för minst fyra X. Det bevisar inte att
kupongen var matematiskt fel: de mest sannolika 384 exakta utfallen kan mycket
väl ha färre X än ett slumpmässigt marknadsutfall.

Den belagda modellbristen ligger i stället i utdelningsdelen. Ordinarie modell
antar en enda medvinnarkorrektion (kappa) per produkt. PH4 visade att
medvinnarna är U-formade efter radens popularitet. Hypotesen är att en separat
kappa för rader med 0, 1, 2, 3 respektive 4+ X rankar Topptipsrader bättre.

## Kandidaten låses före körning

Version: `topptips-radform-v1`.

1. Matchsannolikheter, kandidattecken, värdevikt 0,5, budget och all annan
   radscore är exakt samma som i `build_ev_system`.
2. Utvecklingsperioden räknar, per X-grupp, faktisk mängd åttarättsvinnare
   dividerat med nuvarande prognos: fältstorlek × slutstreckens produktsannolikhet
   × produktens befintliga 2024+-kappa.
3. Kvoten blir en familjegemensam multiplikator på respektive produkts
   befintliga kappa. Det bevarar nivåskillnaden mellan Dagens, Stryk och Extra.
4. Gruppen 4 betyder fyra eller fler X. En grupp med mindre än 100
   modellprognostiserade vinnare faller stängt tillbaka till multiplikator 1,0.
5. Multiplikatorn säkerhetsbegränsas till intervallet 0,5–1,5.
6. Modellen tvingar inte in X och har ingen manuell X-bonus. Den ändrar bara
   prognosen för hur många andra vinnare en exakt rad väntas dela potten med.
7. Samtliga 3^8 = 6 561 Topptipsrader kan fullrankas. Kandidaten används inte
   i produktionsförslag utan ett separat beslut efter historik och forwardtest.

## Låst datadelning

- Produkter: `topptipset`, `topptipsetstryk`, `topptipsetextra`.
- Period: 2024-01-01 till men inte med 2026-08-24.
- Inom varje produkt är äldsta 70 procent utveckling och senaste 30 procent
  orörd holdout. Multiplikatorerna skattas gemensamt på de tre
  utvecklingsdelarna och används oförändrade på holdout.
- Kohorten kräver åtta matcher, odds, slutstreck, facit, omsättning och
  åttarättsnivå. Noll officiella vinnare får bidra till kappa och träffmått,
  men ROI redovisas bara när den observerade potten är identifierbar.
- Historisk jackpot är ofullständig och sätts lika till noll för alla armar.
- Databasen öppnas read-only från en fixerad snapshot.

## Armar och mått

Fyra lika dyra 384-raderssystem jämförs:

1. `current`: ordinarie värderader, värdevikt 0,5.
2. `row_shape`: kandidaten ovan.
3. `x_balanced`: det förregistrerade stresstestet som fördelar antal X exakt
   som marknaden; diagnostik, inte huvudkandidat.
4. `low_ev`: ordinarie byggare med värdevikt 0,0, för frågan om reglaget hade
   löst dagens miss.

Primärt på familjens holdout redovisas exakt åttarättsträff, kandidatspecifika
träffar/förluster mot current, parade träffskillnader, marknadsberäknad
portföljträff, systemets X-profil och parad ROI-skillnad winsoriserad till
±200 procentenheter. 90-procents bootstrap-KI använder omgången som block.

`row_shape` klarar historikgrinden endast om den på holdout:

1. har minst lika många åttarättsträffar som current;
2. inte har lägre marknadsberäknad portföljträff med mer än 5 procent relativt;
3. har en punktskattad winsoriserad ROI-skillnad som inte är sämre än
   −5 procentenheter;
4. faktiskt väljer andra rader i minst någon omgång.

Historiken är `final_only`: armarna ser öppningsodds och slutstreck, inte det
verkliga point-in-time-läget när kupongen spelades. Ett godkänt resultat får
därför bara starta en separat forward-nyckel. Standardbyggaren byts inte förrän
minst 40 senare, parade point-in-time-omgångar uppfyller projektets befintliga
grind. En underkänd kandidat trimmas inte mot holdout; nästa idé får ett nytt
versionsnamn och en ny förregistrering.

## Reproducerbar körning

```bash
cd backend
.venv/bin/python -B scripts/backtest_topptips_xbalans.py \
  --db /sökväg/till/fixerad-snapshot.db \
  --budget 384 --bootstrap-iters 2000 \
  --json ../docs/topptips-radform-v1-resultat.json
```

