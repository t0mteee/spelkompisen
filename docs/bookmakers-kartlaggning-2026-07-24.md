# Kartläggning: spelbolag med gratis publika 1X2-odds (2026-07-24)

Uppdrag: hitta så många spelbolag som möjligt vars 1X2-odds för fotboll kan hämtas
**gratis, utan inloggning och utan API-nyckel**, för att ge Spelkompisen genuint
oberoende sidoböcker. Bakgrund: av 241 värdeflaggor kom 231 från Svenska Spel —
Expekt (Kambi) och Betinia (Altenar) bidrar i praktiken ingenting.

Allt nedan är **faktiskt testat** 2026-07-24 från denna maskin (svensk IP), inte
antaget. Ingen inloggning, ingen CAPTCHA, inget kringgående av skydd.

---

## 1. Huvudslutsats (läs denna först)

**Plattform = pris. Att lägga till fler varumärken på en plattform vi redan har
ger noll ny information.** Det är mätt, inte gissat:

### Kambi är EN prisfeed

Allsvenskan, samma stund, 1X2 från sju Kambi-operatörer:

| Match | svenskaspel | expektse | atg | ubse (Unibet SE) | paf | betmgmse | kambi/draftkings |
|---|---|---|---|---|---|---|---|
| Degerfors–Djurgården | 5,10 / 4,00 / 1,72 | **identisk** | **identisk** | **identisk** | **identisk** | 4,90 / 3,90 / 1,68 | 4,70 / 3,75 / 1,65 |
| Kalmar–Mjällby | 2,55 / 3,55 / 2,85 | **identisk** | **identisk** | **identisk** | **identisk** | 2,50 / 3,40 / 2,75 | 2,43 / 3,30 / 2,65 |
| Sirius–IFK Göteborg | 1,44 / 4,90 / 8,00 | **identisk** | **identisk** | **identisk** | **identisk** | 1,41 / 4,75 / 7,50 | 1,38 / 4,50 / 7,00 |

Genomsnittlig overround (Allsvenskan, n=7 matcher):

| Kambi-operatör | Overround |
|---|---|
| svenskaspel, expektse, atg, ubse, paf, pafse | **1,0262** (2,62 %) |
| betmgmse, betmgmuk, betmgmnl | 1,0560 |
| kambi, draftkings | 1,0889 |

Skillnaden mellan operatörerna är **ren marginalsättning på samma linje**, inte
olika åsikt. Expekt kan tas bort ur `BOOKS` utan att förlora en enda bit information.

### Altenar är också EN prisfeed

Samma mätning över elva Altenar-integrationer:

| Integration | Overround (Allsvenskan) | Kommentar |
|---|---|---|
| betinia | **1,0950** | den vi använder idag — **sämsta marginalen av alla** |
| rabona | 1,0814 | |
| nomini, boomerang, wazamba, playzilla, **ninjacasino**, betway, goldenbet, sportaza, fairspin | **1,0645** | identiska priser sinsemellan |

Linjen är densamma överallt; bara marginalen skiljer.

### Varför Svenska Spel dominerar värdeflaggorna

Svenska Spels 1X2 på Allsvenskan ligger på **2,62 % overround**. Det är i praktiken
Pinnacle-nivå och skarpare än båda börserna vi hittat. **Ingen mjuk bok kommer
någonsin att slå det priset.** 231/241-fördelningen är alltså inte ett fel i
insamlingen — den är en korrekt observation om att SvS är det vassaste
konsument-1X2-priset i Sverige.

Konsekvensen för strategin: sidoböckernas värde är **inte** "bättre pris" utan
**"oberoende sannolikhetsestimat"** som gör `fair_prob` mindre beroende av en
enda källa (Pinnacle) och gör SvS-flaggorna falsifierbara.

---

## 2. Verifierade kandidater

### 2.1 Matchbook (börs) — REKOMMENDERAS

Helt öppet REST-API, ingen nyckel, ingen inloggning, inget geoblock.

```
GET https://api.matchbook.com/edge/rest/events
    ?sport-ids=15                 # 15 = fotboll
    &market-types=one_x_two
    &tag-url-names=sweden-allsvenskan
    &states=open
    &odds-type=DECIMAL
    &exchange-type=back-lay
    &side=back
    &price-depth=3
    &per-page=200&offset=0
```

Svar: `events[].markets[]` med `market-type == "one_x_two"`,
`runners[].name` (hemmalag / bortalag / `"Draw"`) och
`runners[].prices[]` med `odds`, `side` (`back`/`lay`) och `available-amount`
(faktisk likviditet i GBP). Liga finns i `events[].meta-tags[]` med `type=COMPETITION`.

**Testresultat** (Degerfors–Djurgården, samma stund som SvS ovan):
`Degerfors 4,80 (26,95 tillgängligt) / Draw 4,00 (113,30) / Djurgården 1,83 (3,52)`.
Djup finns på andra nivån också (4,70 / 3,95 / 1,82).

Ligemappning för våra tio ligor (från `GET /edge/rest/navigation`), med antal
**öppna** event vid testtillfället:

| Vår `key` | Matchbook `tag-url-names` | id | Öppna nu |
|---|---|---|---|
| allsvenskan | `sweden-allsvenskan` | 1190794069600024 | 7 |
| superettan | `sweden-superettan` | 1190565934370024 | 1 |
| eliteserien | `norway-premier-league` | 1191686343170024 | 1 |
| obosligaen | `norway-first-division` | 1190570885750023 | 2 |
| mls | `us-major-league-soccer` | 1190793990860023 | 15 |
| friendlies | `elite-club-friendlies` | 1821096755870029 | 7 |
| premier_league | `english-premier-league` | 1931978925580001 | **0** |
| serie_a | `italy-serie-a` | 1196800111120023 | **0** |
| la_liga | `spain-la-liga` | 1529360379130003 | **0** |
| bundesliga | `germany-bundesliga` | 1194360360630023 | **0** |

Alla tio ligor **finns** i trädet, men **Matchbook öppnar marknader sent.**
Vid testet hade Smarkets redan 10 Premier League-, 10 Serie A-, 10 La Liga- och
9 Bundesliga-matcher uppe medan Matchbook hade noll, och Smarkets hade 7–8
Superettan/Eliteserien-matcher mot Matchbooks 1–2. Matchbook ger alltså **djup
nära avspark**, inte tidiga priser. Totalt 166 öppna fotbollsevent, 160 med 1X2.

Rate limits: sex snabba anrop i följd (11 MB vardera med `per-page=500`) gick på
2,5 s utan strypning och utan rate-limit-headers. Med `market-types=one_x_two`
krymper svaret till ~200 kB, med `tag-url-names` till ~650 kB per liga.

Genomsnittlig overround på back-priser över hela fotbollsutbudet: 1,0430
(bättre på likvida ligor).

### 2.2 Smarkets (börs) — REKOMMENDERAS

Öppet, dokumenterat REST-API, ingen nyckel.

```
GET https://api.smarkets.com/v3/events/?type=football_match&state=upcoming&limit=200
GET https://api.smarkets.com/v3/events/{id1,id2,...}/markets/
GET https://api.smarkets.com/v3/markets/{market_id}/contracts/
GET https://api.smarkets.com/v3/markets/{market_id}/quotes/
```

- Ligan ligger i `events[].full_slug`, fjärde segmentet
  (`/sport/football/sweden-allsvenskan/2026/07/25/...`).
- 1X2-marknaden heter **`"Full-time result"`** (inte "Match Odds").
- Priser i `quotes` är **sannolikhet × 10 000**. Decimalodds = `10000 / price`.
  Exempel Degerfors–Djurgården: offer 2041 / 2439 / 5435 → 4,90 / 4,10 / 1,84.
- `bids` = vad du kan lägga (lay-sidan), `offers` = vad du kan ta (back-sidan).
  `quantity` ger djup.
- Paginering via `pagination.next_page` (relativ URL — använd `urljoin`).

**Testresultat**: 810 kommande fotbollsevent i fem sidor. Ligetäckning verifierad:

| Vår `key` | Smarkets-slug | Antal event vid test |
|---|---|---|
| allsvenskan | `sweden-allsvenskan` | 7 |
| superettan | `sweden-superettan` | 7 |
| eliteserien | `norway-premier-league` | 7 |
| obosligaen | `norway-first-division` | 8 |
| mls | `us-major-league-soccer` | 15 |
| friendlies | `club-friendlies` | 102 |
| premier_league | `england-premier-league` | 10 |
| serie_a | `italy-serie-a` | 10 |
| la_liga | `spain-la-liga` | 10 |
| bundesliga | `germany-bundesliga` | 9 |

**Alla tio ligor täcks, och friendlies-täckningen (102) är dramatiskt bättre än
allt annat vi har.** Overround på offers, Allsvenskan: **1,0215** — skarpare än
Svenska Spel.

Rate limits: sex anrop på 0,9 s, ingen strypning, inga rate-limit-headers.

### 2.3 Sidojämförelse mot Svenska Spel (varför detta är värt något)

Allsvenskan, samma stund:

| Match | SvS (Kambi) | Matchbook back | Smarkets offer |
|---|---|---|---|
| Degerfors–Djurgården | 5,10 / 4,00 / **1,72** | 4,80 / 4,00 / **1,83** | 4,80 / 4,00 / **1,82** |
| Kalmar–Mjällby | 2,55 / 3,55 / **2,85** | 2,46 / 3,65 / **3,05** | 2,46 / 3,65 / **3,05** |
| Brommapojkarna–Hammarby | **8,00** / 5,40 / 1,40 | **7,00** / 5,30 / 1,49 | **7,00** / 5,10 / 1,47 |
| Sirius–IFK Göteborg | **1,44** / 4,90 / **8,00** | **1,50** / 5,10 / **7,00** | **1,49** / 5,00 / **6,80** |
| Malmö–Elfsborg | **1,80** / 3,85 / 4,70 | **1,93** / 3,90 / 4,40 | **1,92** / 3,85 / 4,30 |
| GAIS–Halmstad | 1,40 / 5,00 / 8,50 | 1,39 / 5,50 / 8,60 | 1,37 / 5,40 / 8,60 |
| Häcken–AIK | 1,90 / 4,10 / 3,95 | — | 1,87 / 4,10 / 3,65 |

Detta är **verklig oenighet**, inte marginalskillnad: SvS är 6–7 % kort på
favoriten i Malmö–Elfsborg och Sirius–Göteborg, men ger 14 % mer på skrällen
i Brommapojkarna–Hammarby. Exakt den sortens signal som Expekt/Betinia aldrig
kunde ge.

### 2.4 Marathonbet (traditionell bok, HTML) — VILLKORAT

Publik HTML utan skydd; 1X2 ligger i attribut, ingen JS krävs.

```
GET https://www.marathonbet.com/en/betting/Football/Sweden/Allsvenskan+-+16609/
GET https://www.marathonbet.com/en/betting/Football/          # hela utbudet
```

Odds i `data-selection-price="4.3"` bredvid
`data-selection-key="28081147@Match_Result.1|draw|3"`
(`1` = hemma, `draw` = kryss, `3` = borta).

**Testresultat**: Allsvenskan-sidan gav 45 prissatta Match_Result-selektioner
(15 matcher × 3), t.ex. 4,30 / 3,74 / 1,75. Hela fotbollssidan: 234 selektioner
i ett anrop (739 kB).

Villkor/nackdelar: (a) det är HTML-parsning, inte JSON — bräckligare än allt annat
i kodbasen; (b) lagnamn kräver en extra selektor (finns inte i samma attribut);
(c) Marathonbet är en **låg-marginal-/semi-sharp-bok** och därmed starkt korrelerad
med Pinnacle — bidrar mindre oberoende information än en mjuk bok skulle ha gjort;
(d) inte svensklicensierad.

### 2.5 Gratis marginalvinst: byt Altenar-integration

`app/altenar.py` använder `integration=betinia`, som är **sämsta marginalen**
på hela Altenar-plattformen (1,0950). Byte till `integration=ninjacasino`
(svensklicensierad, samma API, samma parametrar, samma champ-id:n) ger
**1,0645** — cirka 3 procentenheter bättre pris gratis, noll ny kod.

```
GET https://sb2frontend-altenar2.biahosted.com/api/Widget/GetEvents
    ?culture=sv-SE&timezoneOffset=-120&integration=ninjacasino
    &deviceType=1&numFormat=en-GB&countryCode=SE
    &champIds=3537&sportId=66&eventCount=50
```

Verifierade Altenar-integrationer som svarar: `betinia`, `rabona`, `nomini`,
`boomerang`, `wazamba`, `playzilla`, `ninjacasino`, `betway`, `goldenbet`,
`sportaza`, `greatwin`, `fairspin`, `stake`, `bcgame`.
(De två sista har mycket tunnare utbud — 18 sporter mot 31–36, och ingen
Allsvenskan.)

---

## 3. Avvisade kandidater (med orsak)

### 3.1 Samma plattform som vi redan har — noll informationsvinst

| Bolag | Plattform | Testresultat |
|---|---|---|
| **Expekt** (`expektse`) | Kambi | Svarar 200, **odds identiska med Svenska Spel in på decimalen.** Bör tas bort ur `BOOKS`. |
| **ATG** (`atg`) | Kambi | Svarar 200, identisk med SvS. |
| **Unibet SE** (`ubse`) | Kambi | Svarar 200, identisk med SvS. Operatörsnamnet är `ubse`, inte `unibet`. |
| **Paf** (`paf`, `pafse`) | Kambi | Svarar 200, identisk med SvS. |
| **BetMGM** (`betmgmse`, `betmgmuk`, `betmgmnl`) | Kambi | Svarar 200, samma linje med 5,6 % marginal. |
| **DraftKings** (`draftkings`) + generisk `kambi` | Kambi | Svarar 200, samma linje med 8,9 % marginal. |
| **Betinia, Rabona, Nomini, NinjaCasino, Betway, Goldenbet m.fl.** | Altenar | Svarar 200, samma linje, endast marginal skiljer. |

Kambi-operatörsnamn som **inte** är kunder (400 `Unable to resolve customer`):
`888sport`, `betmgm`, `leovegas`.
Namn som ger 429 `No access` (samma svar som ett påhittat namn — alltså inte
kunder heller): `unibet`, `betsson`, `nordicbet`, `betsafe`, `mrgreen`,
`storspelare`, `bethard`, `napoleon`, `rizk`.
`comeon` och `coolbet` svarar 200 men med **0 event** på alla marknader/språk
(sv_SE/SE, en_GB/GB, en_US/US, fi_FI, nb_NO, da_DK) — tomma skal, inte användbara.

### 3.2 Blockerade av botskydd (Cloudflare / Imperva / Incapsula / PerimeterX)

| Bolag | Plattform | Testresultat |
|---|---|---|
| **bet365** | egen | `https://www.bet365.com/defaultapi/sports-configuration` → **403** (Cloudflare). Ingen väg utan att kringgå skydd. |
| **Coolbet** (Betsson Group) | egen | `https://www.coolbet.com/api/sb/v2/*` → **Imperva "Pardon Our Interruption"** på alla vägar. |
| **Betano / Novibet / Stoiximan** (Kaizen) | egen | `https://www.betano.{de,ro}/api/*` → **403** (Incapsula) på alla vägar och alla domäner. |
| **bwin / Entain** | Entain CDS | `cds-api.bwin.com` har **ingen DNS**. `https://sports.bwin.com/cds-api/bettingoffer/fixtures` → **403** (Incapsula). Sidans JS-bundle levererar 0 byte till icke-browser-klient, så `x-bwin-accessid` går inte att läsa ut. |
| **Winamax** | egen | `api.winamax.fr` och `www.winamax.fr/paris-sportifs/*` → **403** för alla icke-browser-klienter. |
| **Interwetten** | egen | **403** Cloudflare "Just a moment…". |
| **Paddy Power / Betfair Sportsbook** | Flutter | `https://www.betfair.com/api/sportsbook/v1/events` → **403**. |
| **Fortuna** (efortuna.pl) | egen | **403**. |
| **1xBet / Melbet / Betwinner / 22bet** | 1xBet-plattformen | `1xbet.com/service-api/LineFeed/*` → **403** Cloudflare. Mirrors (`1xbet.ng`, `melbet.com`, `betwinner.com`) returnerar bara ett JS-skal (203), aldrig JSON. |

### 3.3 Kräver okänd header / auth-gateway

| Bolag | Testresultat |
|---|---|
| **Betsson, Betsafe, NordicBet** (Betsson Group) | `https://www.betsson.com/api/sb/v1/**` finns och svarar, men **alltid** `400 {"code":"E_VALIDATION_INVALIDHEADER"}` — en gateway-nivå-vakt, oberoende av väg. Testade `X-Brand`, `brand`, `X-Betsson-Brand`, `Market`, `X-Market`, `x-obg-brand`, `X-Client`, `Referer`, `Accept-Language` — alla samma svar. Headernamnet finns bara i JS-bundlen; att gräva vidare där börjar likna kringgående av skydd, så jag stannade. **Betsson Group är den enskilt intressantaste mjuka boken vi missar.** |
| **Betway** | `POST https://sports.betway.com/api/Events/v2/GetGroup` svarar men kräver giltig `BrandId`, `JurisdictionId`, `ClientIntegratorId`, `LanguageId`, `ClientTypeId`, `CategoryCName`, `SubCategoryCName`, `GroupCName`. Dessa är varumärkes-GUID:er som inte går att gissa. |
| **888sport** | Kör på **Spectate** (888:s egen plattform, `spectate-web.888sport.se`, `cdn.spectateprod.com`). Alla API-vägar på `spectate-web.888sport.se` → **403**. Övrig infra ligger bakom `safe-iplay.com`. |
| **ComeOn** | Egen plattform med **Betradar**- och **OpenBet**-signaler i sidkällan; feed-hosten är `lsbl.comeon.com` → **503 utan innehåll** för alla vägar. `comeon.se` avvisar TLS-handskakningen (`unrecognized name`). |
| **Betfair Exchange** | `https://ero.betfair.com/www/sports/exchange/readonly/v1/bymarket` svarar **200 med giltig JSON-struktur** utan auth — men kräver `marketIds`, och alla vägar att lista marknader är stängda: `navigation/facet/v1/search` ger `400 DSC-0024` (ogiltig app-nyckel) på GET och `200 {"facets":[],"results":[]}` på POST oavsett filter. Utan marknads-id:n är prisändpunkten värdelös. **Matchbook och Smarkets ger samma sorts börsdata utan detta krångel.** |

### 3.4 Geoblockerade, döda eller irrelevanta

| Bolag | Testresultat |
|---|---|
| **Cashpoint** | `www.cashpoint.com` redirectar till `merkurbets.com/restrict/...` — **geoblockerat** från Sverige. |
| **Betclic** | `offer.cdn.begmedia.com` (det historiskt kända öppna CDN:et) har **ingen DNS längre**. Även `offer.cdn.betclic.fr` saknar DNS. Endpointen är nedlagd. |
| **William Hill** | `sports.williamhill.com/betting/*` → **503**; `sportsapi.williamhill.com` → timeout. Ingår numera i 888/Spectate-infran. |
| **BetVictor** | `apiaws.betvictor.com` — **ingen DNS**. |
| **Betdaq** | `api.betdaq.com/v2/*` → 404; `www.betdaq.com/api/*` → **410 Gone**. |
| **Superbet** | `production-superbet-offer-a-primary.freetls.fastly.net` → **Fastly "unknown domain"**. Nedlagd. |
| **Tipico** | `sports.tipico.de` är numera en **parkerad annonsdomän** (taboola/content.ad), inte Tipico. |
| **LeoVegas** | `leovegas.se` → 301, ingen Kambi-operatör (`leovegas` → 400). Ingår i MGM/BetMGM-familjen, vars Kambi-brand `betmgmse` redan är samma feed som SvS. |
| **Bet-at-home** | 404 på alla testade API-vägar. |
| **Norsk Tipping, Veikkaus, Danske Spil** | Alla testade sportsbook-API-vägar → 404 eller HTML. Statliga monopol, ej relevanta för våra ligor ändå. |
| **Digitain, BetConstruct, EveryMatrix/OddsMatrix, Betby, Sportnco** | Ingen DNS eller Cloudflare-530 på publika API-hostar. Dessa är B2B-plattformar utan publik konsumentfeed. |
| **Sky Bet** | `sbapi.sbg.skybet.com` — ingen DNS. |
| **Stake / BC.Game** (via Altenar) | Svarar, men ~18 sporter och **ingen Allsvenskan** — för tunt. |

---

## 4. Rangordning

Kriterier: (a) oberoende från Svenska Spel/Kambi, (b) täckning av våra ligor,
(c) mjukhet. Notera att kriterium (c) i praktiken inte gick att uppfylla —
**varenda mjuk bok med relevant svensk närvaro är botskyddad.** De öppna
källorna är börser och lågmarginalböcker.

| # | Källa | Oberoende | Ligtäckning | Typ | Kodmängd |
|---|---|---|---|---|---|
| 1 | **Smarkets** | Total (börs) | **10/10 ligor öppna nu**, 810 event, friendlies 102 | Börs (bid/offer) | ~90 rader |
| 2 | **Matchbook** | Total (börs) | 10/10 i trädet men **öppnar sent** (0 event i stora ligor); ger likviditetsdjup | Börs (back/lay) | ~70 rader |
| 3 | **Altenar → `ninjacasino`** | Ingen (samma feed) | 3 ligor | Bok, −3 pp marginal | **1 rad** |
| 4 | **Marathonbet** | Hög (egen bok) | Allsvenskan + brett | Bok, semi-sharp, HTML | ~120 rader, bräcklig |
| 5 | Betsson Group | Total, mjuk | okänd | Bok | **Blockerad** — kräver okänd header |

---

## 5. Rekommendation

### Gör först (hög nytta/kostnad)

**1. Byt `integration=betinia` → `integration=ninjacasino` i `app/altenar.py`.**
Kodmängd: **en rad** (defaultvärdet i `league_events`) plus `BOOKS`-posten i
`oddset.py`. Ger ~3 procentenheter bättre pris från samma feed. Ingen risk.

**2. Ta bort Expekt ur `BOOKS`.**
Det är bevisligen samma tal som Svenska Spel. Att behålla det ger en falsk känsla
av att vi har två källor. Om något ska stå kvar som Kambi-syskon: `betmgmse`, som
åtminstone har annan marginal — men även det är samma linje.

**3. Implementera Smarkets (`app/smarkets.py`).**
Högsta prioritet av de nya. Enda källan som täcker alla tio ligor **och** ger
102 träningsmatcher (vår sämst täckta liga idag). Fyra GET-anrop, ren JSON,
inga nycklar, ingen strypning. Kodmängd **~90 rader** i samma mönster som
`altenar.py`: `league_events(slug)` → `[{id, home, away, start, odds{1,X,2}}]`.
Enda fällorna: priset är `10000/price`, marknaden heter `"Full-time result"`,
och pagineringen är relativ. Matchning mot Pinnacle/Kambi kan återanvända
befintlig fuzzy-matchning på namn + avspark.

**4. Implementera Matchbook (`app/matchbook.py`).**
Kodmängd **~70 rader** — enklare än Smarkets, **ett** GET-anrop per liga med
`tag-url-names` + `market-types=one_x_two`. Bonus som ingen annan källa ger:
`available-amount` per pris, alltså **faktisk likviditet**. Det är en direkt
kvalitetsvikt — ett börspris med 3 GBP bakom sig ska inte väga lika tungt som
ett med 130 GBP. Det kan i sin tur bli en ny signal (tunn börs = osäkert
konsensus).

Eftersom Matchbook öppnar sent passar den bäst i **snabbpollen**
(`FAST_WITHIN_H`-varvet i `oddset.py`) snarare än i 30-minutersinsamlingen —
den tillför mest just i lineup-/steam-fönstret där den faktiskt har priser uppe.
Smarkets bör tvärtom gå i den ordinarie insamlingen, eftersom den har priser
dagar innan.

### Gör sedan, om det behövs

**5. Marathonbet (`app/marathonbet.py`)** — bara om vi vill ha en fjärde
oberoende åsikt. **~120 rader** HTML-parsning, betydligt bräckligare än resten
av kodbasen, och semi-sharp (korrelerad med Pinnacle). Lägre värde per kodrad
än 3 och 4.

### Gör inte

- Fler Kambi-operatörer. Bevisat samma tal.
- Fler Altenar-integrationer utöver bytet i punkt 1. Bevisat samma linje.
- Betfair, bet365, Betano, Coolbet, bwin, Winamax, 1xBet-familjen. Alla kräver
  att man tar sig förbi botskydd, vilket ligger utanför projektets ramar.
- Betsson Group tills vidare. Endpointen finns och är intressantast av alla,
  men headernamnet går bara att få fram genom att gräva i deras JS-bundle —
  det är en gräns jag inte gick över.

### Metodkommentar (viktig för CLV-facitet)

Börspriser är **marknadspriser**, inte modellhärledda. Enligt metodregeln i
`CLAUDE.md` ("ENDAST marknadspriser får logga flaggor") får Smarkets och
Matchbook alltså gå in i `value_log` och CLV-facitet på samma villkor som
Pinnacle. Det är en poäng i sig: det ger oss en andra och tredje
stängningsreferens och gör 231/241-fördelningen testbar i stället för antagen.

Rekommendation för `fair_prob`-prioritetsordningen: överväg att låta ett
**konsensus** av devigade Pinnacle + Smarkets + Matchbook (viktat på
likviditet/marginal) ersätta ren Pinnacle som sharp-ankare, i stället för att
lägga in börserna som ytterligare "sidoböcker" i jämförelsevyn. Deras
overround (2,15 % Smarkets, 4,30 % Matchbook) gör dem till fair-price-källor,
inte till böcker vi ska leta värde hos.
