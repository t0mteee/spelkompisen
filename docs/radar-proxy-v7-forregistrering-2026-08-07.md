# Förregistrering: proxysignal v7 (`chance-gap-shadow-v7`)

Skriven **innan** koden ändrades. Beslut: Saman, 2026-08-07 ("Kör").

## Problemet, mätt

Efter att Sofascore kopplades bort ur radarn (v6) är proxysignalen i praktiken
död. Mätt på 37 matcher/24 h respektive 35 matcher efter fälttillägget:

| Fält | Täckning |
|---|---|
| skott på mål, totala skott, hörnor | **100 %** |
| skott utanför, blockerade, bollinnehav | **100 %** (nya fält, 2026-08-06) |
| xG, stora chanser, skott i box, touches i box | **43 %** |

Proxyns aktiveringsvillkor är

```
big_chances − mål ≥ 1,5   ELLER   (skott på mål − mål ≥ 5  OCH  skott i box ≥ 8)
```

— alltså två fält som **bara finns när xG också finns**. Konsekvensen:

* matcher där proxyn tillför något utöver xG-signalen: **0 av 37**
* matcher som aldrig kan få NÅGON signal: **22 av 37 (59 %)**

Proxyn fungerade före v6 på Sofascores bredare täckning av `big_chances`
och `touches_box`.

## Vad som INTE görs, och varför

**Proxyn görs inte om till en xG-skattning.** Det var första idén: regressera
xG på skottmåtten och använda xG-signalens trösklar. Passningen på de 15
matcher som har båda måtten (30 oberoende lagobservationer) gav

```
xG ≈ 0,197·på mål + 0,139·utanför + 0,087·blockerade − 0,061·hörnor
medelabsolutfel 0,481 xG (median-xG i materialet: 0,51)
```

Hörnkoefficienten är **negativ**, vilket är fysiskt omöjligt, och felet är
lika stort som signalen själv. 30 observationer räcker inte, och en
modellhärledd storhet som presenteras i mål-enheter är precis den
uppblåsning projektet gång på gång blivit bränt av (DC alt-totaler +40–55 %,
hörnor +120 %). Proxyn förblir därför ett **enhetslöst index** med eget
fältnamn (`proxy_index`), aldrig `chance_gap`.

## Ändringen

Minsta möjliga: **ett fält som saknas byts mot ett som finns.** Inga nya
frihetsgrader, inga nya tröskelvärden.

```
farliga skott := skott på mål + blockerade skott
```

Aktivering blir

```
big_chances − mål ≥ 1,5   ELLER   (skott på mål − mål ≥ 5  OCH  farliga ≥ 8)
```

Indexet får `blockerade · 0,05` — en vikt mellan skott på mål (0,12) och
skott i box (0,025), eftersom ett blockerat skott var på väg mot mål men
stoppades. Övriga vikter är oförändrade.

### Varför "farliga skott" ersätter "skott i box"

Validerat på 1 342 observationer där båda måtten finns:

| Mått | Värde |
|---|---|
| korrelation | **0,890** |
| medel, skott i box | 4,46 |
| medel, farliga skott | 4,18 |
| samma svar vid tröskel ≥ 8 | **91 %** |

Måtten är alltså nära utbytbara vid just den tröskel som redan används.

### Frekvenskalibrering (INTE utfallskalibrering)

Tröskelparet valdes på hur ofta det utlöser, aldrig på om utfallet blev bra —
utfallet är vad blindkohorten ska avgöra. Mätt på 877 captures i fönstret
20–78 min över 35 matcher:

| på mål − mål | farliga | matcher som utlöser |
|---|---|---|
| ≥ 3 | ≥ 5 | 28/35 (80 %) |
| ≥ 4 | ≥ 8 | 16/35 (46 %) |
| **≥ 5** | **≥ 8** | **10/35 (29 %)** |

Det valda paret är dessutom identiskt med dagens tröskelvärden. Frekvensen
ligger nära xG-signalens på samma kväll.

## Förregistrerade villkor

1. **Signalversion `chance-gap-shadow-v7`** från deklarerat startögonblick.
   Blindkohorten nollställs; v6 blandas aldrig in. Kohortregeln gäller som
   vanligt (rad hör till vN bara om vN-koden producerade den OCH den
   observerades i vN:s fönster).
2. **Ingen bakfyllning.** Historiska captures räknas aldrig om.
3. **Grinden är oförändrad:** minst 200 oddssatta och avgjorda signalmatcher,
   minst 60 dagar, och undre KI90 > 0 innan proxyn får stödja något.
4. **Proxyn förblir shadow.** Den påverkar inte tips, Kelly, CLV, notiser
   eller systemförslag.
5. **Ingen ny tröskeljustering utan ny version.** Om frekvensen visar sig fel
   är det en ny förregistrering, inte en tyst ändring.

## Förväntat utfall

Andelen matcher som kan få en signal går från 43 % till ~100 %; andelen som
faktiskt utlöser väntas hamna kring 29 % av matcherna i det spelbara
minutfönstret. Om proxyn saknar prediktiv kraft ska blindkohorten visa det —
den är byggd för att kunna falsifiera, och `Close-drift v1` är prejudikatet
på att ett spår läggs ned när facit säger nej.

---

## Utfall av implementationen (mätt efteråt)

Kohortstart: **2026-08-06T21:40:00Z**. Mätt genom att köra `radar_signal` över
samtliga captures observerade efter fälttillägget (35 matcher):

| | Före | Efter |
|---|---|---|
| Matcher som kan få NÅGON signal | 15/35 (43 %) | **35/35 (100 %)** |
| varav via xG | 15/35 | 15/35 (oförändrat) |
| Matcher som utlöste watch/strong | — | **10/35 (29 %)** |
| Proxy-only-matcher som utlöste | 0 | 1 |

Utlösningsfrekvensen 29 % är exakt den som frekvenskalibreringen förutsade.
Att bara 1 av de 20 proxy-only-matcherna faktiskt utlöste är väntat och
avsiktligt: tröskeln är oförändrat strikt, vilket är rätt för en signal som
ännu inte har något facit.

`_stats_rank` följde med: nivå 2 ("raden kan bära en proxysignal") måste
använda samma villkor som aktiveringen, annars hade en rad som visst kan
signalera rankats som partiell och kunnat döljas av en sämre källa.

563 tester gröna (3 nya som låser tröskelvärdena, den rikare grenen och
rankningen).
