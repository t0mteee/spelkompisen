# Historik-vyn: ombyggnad 2026-08-05

Beställare: Saman. Mål med hans egna ord: **förenkla och förtydliga.**
Dokumentet är skrivet i två delar — nuläget mättes INNAN någon rad ändrades,
efterläget efter. Utan före-siffror går det inte att säga om ombyggnaden
faktiskt gjorde sidan enklare.

---

## Del 1 — NULÄGET (mätt före ombyggnad)

### Sidan som helhet

Mätt i preview (1280×720, `document.body.scrollHeight`):

| Element | y | Höjd |
|---|---|---|
| `playedbox` — egna bokförda kuponger | 83 | 348 px |
| `v3histbar` — produktknapparna | 430 | 25 px |
| `v3note` — förklaringstext | 465 | 53 px |
| `📋 Systemfacit` rubrik | 544 | |
| systemfacit-tabell (30 grupper) | 629 | 964 px |
| `details` Senaste frysningarna (40) | 1607 | 1275 px |
| KPI-rad | 1656 | 74 px |
| omsättningsgraf | 1743 | 99 px |
| **omsättningstabell (401 rader)** | 1853 | **12 480 px** |

**Total sidhöjd 14 433 px.** Omsättningstabellen ensam är 86 % av sidan.

### De sju problemen, verifierade

1. **Produktknapparna "gör inget".** De FUNGERAR — `setProduct` hämtar om
   `/api/pool/history?product=…`. Men de sitter på y=430 och styr bara
   tabellen på y=1853, alltså 1 400 px och två stora sektioner längre ner.
   Systemfacit däremellan struntar helt i dem. Visuellt ser knapparna ut att
   höra till kupongtabellen ovanför, som de inte påverkar.

2. **Insatsen "varierar hejvilt" — den varierar inte alls.** `cost_kr` är
   ackumulerad summa över utvärderbara omgångar, inte insats per omgång.
   Radpriset är 1,00 kr för samtliga produkter, så budget i kronor = antal
   rader. Alla observerade tal följer budget × antal omgångar:

   | Visat | Budget | Omgångar | Produkt |
   |---|---|---|---|
   | 150 kr | 50 | 3 | europatipset |
   | 768 kr | 256 | 3 | europatipset |
   | 512 kr | 256 | 2 | stryktipset |
   | 1 100 kr | 50 | **22** | topptipset |

   Topptipsets "spel över 1 000 kr" är alltså 50 kr × 22 omgångar.
   Kolumnrubriken hette "Insats" men visade ackumulerat satsat.

3. **`ev50-tuff-vw80` är oläsbart.** Tre parametrar i en sträng:
   budget 50 kr · strategi *tuff* · värdevikt 80 %. Inget av talen är procent
   utom `vw`. Saman läste rimligen `vw50` som *vecka 50* och `ev50` som
   *50 %* — därav frågan "är inte tuff högre än 50 %?".

4. **Horisonten visas som nyckel.** Brödtexten säger T−3 h och T−20 min,
   tabellen säger `h3` och `m20`. API:t levererar redan minuter
   (`horizons.h3.minutes = 180`, `m20 = 20`) — UI:t använder dem bara inte.

5. **Frysta/Jämförbara är odefinierade i UI:t.** Ur aggregatet i
   `pool_system_ledger.py`: *Frysta* = alla bokförda förslag för gruppen.
   *Jämförbara* = de som frystes i tid (`timely=1`) OCH har känt resultat OCH
   fullständig utdelningsdata — alltså de ROI faktiskt räknas på.

6. **Bokförda kuponger saknar förslagstyp.** `pool_played_coupon` HAR redan
   kolumnerna `build_kind`, `strategy`, `value_weight`, `budget`, men
   POST:en i `CouponPanel` hårdkodar `build_kind:'kupong'` och skickar aldrig
   de övriga. Alla 9 bokförda kuponger har därför NULL. Värdena finns i scope
   i `PoolV3` precis intill `<CouponPanel>`.

7. **Pool-data ligger i Labb.** Två kort:
   `📋 PH3-systemledger` (100 % pool, dubblerar Historikens Systemfacit fast
   grundare) och `🧬 Modellhälsa` (blandat — prognosfel per produkt och
   PH4-κ-OOT ur `/api/pool/turnover-prognos` är pool, utfalls-facit sharp ur
   `/api/oddset/clv` är odds). Historik var däremot redan 100 % pool.

### Champion-etiketten stämde inte

`BENCHMARKS` hade `ev50-medel-vw50` som `primary: True` — alltså champion,
definierad som "dagens byggare". Men appens eget budgetreglage stod på
**128 kr** (`useState(saved.budget || 128)`). Championen speglade alltså inte
byggaren den påstod sig spegla.

### Mätt byggkostnad

`builder.build_ev_system` mot stryktipset #4964, med vinstplan:

| Budget | Rader | Sekunder |
|---|---|---|
| 50 | 50 | 0,12 |
| 144 | 144 | 0,14 |
| 256 | 256 | 0,12 |
| 512 | 512 | 0,12 |
| 1024 | 1024 | 0,12 |

Kostnaden är oberoende av budgeten. 12 konfigurationer × 5 produkter × 2
horisonter ≈ **15 s per varv** — antalet benchmarks är alltså inte
begränsat av tid.

### Underlag som redan finns (ingen ny insamling behövs)

- `pool_system_ledger` lagrar `rows_text` och `events_order` per frysning, så
  de faktiskt föreslagna raderna är återskapbara.
- Samtliga 33 frysta omgångar har odds OCH streck i `snapshots`
  (100–220 distinkta tidpunkter var). `snapshots` är en förändringsserie, så
  värdet vid T−3 h är sista raden med `fetched_at <= T−3h`.
- Slutstreck finns i settlementlagret och visas redan i omgångsdetaljen.

Klick-in på ett fryst system mot facit — inklusive folkets procent vid
frysning och vid spelstopp — kräver därför **noll ny datainsamling**.

---

## Del 2 — BESLUTEN

Fattade av Saman 2026-08-05 efter genomgång av mätningarna ovan.

1. **Historik = 100 % pool, Labb = 100 % odds.** PH3-kortet tas bort ur Labb
   (dubblett). Pool-halvan av Modellhälsa flyttas till Historik. Labb behåller
   utfalls-facit sharp.
2. **Systemsummeringen** svarar på "vad ska jag spela?" och "ska jag ändra
   inställningar?" i EN tabell: per produkt champion mot bästa utmanare.
   Alternativet att summera per konfiguration över alla produkter valdes bort
   — det blandar vinstplaner (Stryk 59,8 %, Europa 63,7 %, Topptipset 70 %),
   så ett snitt över dem betyder ingenting.
3. **Omsättningshistoriken** visas öppen med senaste 20 omgångar och "visa
   alla".
4. **Konfigurationen delas i egna kolumner** (Budget · Strategi · Värdevikt),
   varje fryst rad visar vilken omgång och vilket datum den gäller, och raden
   går att klicka upp mot facit med odds och streck.
5. **Ny benchmarkmatris: full grid 4 × 3 = 12.**
   Budget 144/256/512/1024 × risk säker (vw 20) / medel (vw 50) / tuff (vw 80).
   Gamla `ev50-*`/`ev256-*` pensioneras — nya `config_key` bildar egna grupper,
   så ingen data behöver röras. Priset är statistiskt: 12 × 5 produkter = 60
   jämförelser, där ~3 ser signifikanta ut av ren slump. Möts med **BH-FDR
   över utmanarfamiljen**, samma metod som Oddset-sidan redan använder.
   Alla 12 fryses varje omgång och når n=40 samtidigt — matrisen försenar
   alltså inte grinden.
6. **Champion = 256 kr / medel**, och appens standardbudget flyttas
   128 → 256 så att "champion = dagens byggare" blir sant. 144 läggs till i
   reglagets budgetsteg.

### Vad som medvetet INTE görs

- Ingen bakfyllning av förslagstyp på de 9 befintliga kupongerna. De var inte
  observerade och förblir okända.
- Ingen sammanslagning av gamla och nya benchmarkkohorter. Matrisbytet är en
  processändring; kohorterna hålls isär av `config_key`.

---

## Del 3 — EFTERLÄGET

### Sidhöjd

Mätt likadant som före (`document.body.scrollHeight`, 1280×720, orörd sida
efter omladdning):

| Vy | Före | Efter |
|---|---|---|
| Historik (Stryktipset) | 14 433 px | **7 721 px** |
| Historik (Topptipset) | — | 7 265 px |
| Historik (Alla spel) | — | 7 351 px |

**−47 %.** Den enskilt största posten försvann: omsättningstabellen var
12 480 px (401 rader) och är nu 20 rader med "visa alla".

Kvarvarande höjd är innehåll, inte spill: Systemfacit 3 550 px (metodtext +
konfigurationstabell + frysningslista), kuponger 918 px, prognosträff
1 038 px, omsättning 487 px.

### Punkt för punkt

1. **Produktknapparna.** Filtret ligger överst och styr HELA sidan — kuponger,
   systemfacit, prognosträff och omsättning. Ett nytt läge "Alla spel" ger
   tvärsnittet; där visar omsättningssektionen en rad per spel som går att
   klicka för att byta filter. Verifierat: filtrerat till Stryktipset visar
   kupongtabellen bara Stryktipset-rader.
2. **Insatsen.** Två skilda kolumner: *Insats/omgång* (budgeten, t.ex.
   `256 kr`) och *Totalt satsat* (ackumulerat, `512 kr`). Topptipsets
   "1 100 kr" var 50 kr × 22 omgångar och läses nu direkt som det.
3. **`ev50-tuff-vw80`** är borta ur UI:t. Tre kolumner i stället: Budget ·
   Strategi · Värdevikt. `_bench()` läser parametrarna ur matrisen, annars ur
   den frysta radens egna kolumner — aldrig tolkade ur nyckelsträngen.
4. **Horisonten** visas som `180 min` / `20 min` ur API:ts `horizons.*.minutes`.
   Nyckeln `h3`/`m20` når inte längre användaren.
5. **Frysta/Jämförbara** heter *Bokförda* och *Med facit*, med tooltip som
   säger exakt vad som krävs (fryst i tid + känt resultat + känd utdelning).
6. **Kupongerna** är sorterbara på alla kolumner inklusive spel, och har en
   kolumn *Förslagstyp*. Nya kuponger bär byggarens inställningar; de nio
   gamla visar "okänd" med förklarande tooltip och bakfylls aldrig.
7. **Omsättningshistoriken** visar senaste 20 med "visa alla N omgångar".
   KPI-raden och grafen ligger kvar ovanför eftersom de ÄR sammanfattningen.
8. **Historik = pool, Labb = odds.** `📋 PH3-systemledger` togs bort ur Labb
   (dubblett). Pool-halvan av `🧬 Modellhälsa` — prognosfel och PH4-κ — ligger
   nu i Historik som `🧬 Prognosträff och κ-fönster`. Labb-kortet heter
   `🎯 Utfalls-facit (sharp)` och är rent odds.

### Nytt utöver beställningen

- **Klick-in på ett fryst system mot facit.** Varje rad i frysningslistan
  öppnar en vy match för match: vilka tecken systemet täckte, vad som gick in,
  och folkets streck vid frysningen med rörelsen fram till spelstopp. Missade
  matcher är rödmarkerade. Driftverifierat på Stryktipset #4964: 3 missar,
  match 3 Lyngby–Århus där systemet spelade 1 och 2 men X gick in
  (streck 30/25/45). Ingen ny insamling — allt fanns redan.
- **Champion mot bästa utmanare** per spel och horisont, parat över omgångar
  där båda har facit, med sign-flip-bootstrap och BH-FDR över hela
  utmanarfamiljen. `promotable` kräver BÅDE FDR-pass och ≥40 parade omgångar.

### Benchmarkmatrisen

Generation 2 aktiv: `b{144,256,512,1024}-{saker,medel,tuff}`, champion
`b256-medel`. Appens budgetreglage flyttades 128 → 256 och fick 144 som nytt
steg, så "champion = dagens byggare" är sant igen.

Generation 1 (`ev50-*`, `ev256-*`) är pensionerad. Raderna ligger kvar under
sina egna `config_key` och visas märkta "(gammal)" — en `config_key` ändras
aldrig i efterhand, så ingen datamigrering behövdes. Kryssrutan döljer dem.

**Mätt kostnad:** byggaren tar 0,12 s oavsett budget, alltså ~15 s för hela
matrisen per varv. Det statistiska priset — 60 utmanarjämförelser — möts med
BH-FDR (`FDR_Q = 0.10`).

### En bugg som fångades under arbetet

`SortableTable` sorterar internt. Att kapa `rows` före anropet gav "20
godtyckliga rader, prydligt sorterade" — det ser ut som en topplista utan att
vara det. Kapningen ligger nu i komponenten som `limit`, efter sorteringen.

### Verifiering

- 552 backend-tester gröna (6 nya: championrapportens parade jämförelse,
  p-värde-spärren vid små n, pensionerade parametrar, systemdetaljens missade
  match, streck-vid-frysning ur förändringsserien, okänt system).
- `vite build` exitkod 0.
- Driftverifierat i preview: produktfiltret styr alla fyra sektioner,
  klick-in fungerar, omsättningstabellen kapad till 20 rader.

### Kvar att göra

- Championjämförelsen är tom tills nästa frysning — nya matrisen har inga
  omgångar än. UI:t säger det uttryckligen i stället för att visa en tom yta.
- De nio gamla kupongernas förslagstyp förblir okänd.
