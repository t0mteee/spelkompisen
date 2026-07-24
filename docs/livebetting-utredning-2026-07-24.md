# Livebetting-tracker — genomförbarhetsutredning

**Datum:** 2026-07-24 (mätningar gjorda 19:45–22:30 UTC samma kväll)
**Frågeställning:** kan Spelkompisen läsa xG/skott från pågående matcher och rekommendera
spel när det underliggande spelet kraftigt överstiger vad ställningen visar?
**Ingen produktionskod skriven.** Endast mätskript i scratchpad; inga ändringar i
`backend/`, `frontend/`, DB eller launchd.

---

## 0. Dom

**Bygg inte en livebetting-tracker som ger spelrekommendationer. Bygg — om något —
en mätpilot som inte får rekommendera något (avsnitt 9).**

Idén vilar på en premiss som visade sig vara **omvänd** mot vad man förväntar sig:

> "latens: statistiken är alltid efter marknaden"

Det stämmer inte här. **Sofascores livestatistik är snabb (median 41 sekunder efter
skottet). Det är den sharpa referensen som är långsam:** Pinnacles gratis
guest-API ligger **6 minuter efter verkligheten i bästa fall och ~15 minuter efter
vid normal pollning**. Samtidigt prissätter Svenska Spel om sitt live-1X2 **var 46:e
sekund**.

Det betyder att projektets bärande metod — *sharp-ankrat = actionable* — inte går att
tillämpa live. Referensen är 8–20 omprissättningar gammal. Varje "edge" som räknas fram
mot den blir dominerad av fördröjningen, inte av xG-insikten. Det är exakt samma
haveri som redan inträffat en gång i det här projektet (`docs/plan.md`: *"14:52-körningen
(före live-skyddet) hann flagga live-odds mot förmatch-fair (+112 % 'edges') — 4 rader
raderade"*). Jag reproducerade det oavsiktligt i kväll, se avsnitt 6.3.

Utan sharp-ankare återstår **modell utan ankare = amber** — och amber får per
projektets egna regler aldrig generera spelförslag eller CLV-flaggor.

Och även om modellen vore perfekt: **Svenska Spels live-marginal är ~10–11 %.**
Medianpriset hos SvS ligger **−10 %** i EV mot Pinnacles live-fair. Projektets egen
fullt fittade förmatchmodell slår inte Pinnacle förmatch (`docs/plan.md`: *"nära
marknaden i Allsvenskan (±0 % bästa pris), svag Eliteserien"*). Att den skulle slå
Pinnacles **live**-modell med >10 procentenheter, i realtid, är inte ett rimligt antagande.

---

## 1. Testade källor — exakta endpoints och utfall

Allt nedan är faktiskt anropat 2026-07-24, inte hämtat ur dokumentation.

### 1.1 Sofascore — ✅ full livestatistik, inklusive xG

Kräver `curl_cffi` med Chrome-imitation (redan i projektet, `oddset_data._sofa_get`).

| Endpoint | Ger | Utfall |
|---|---|---|
| `/api/v1/sport/football/events/live` | alla pågående matcher i **ett** anrop | 88 event, 298 kB |
| `/api/v1/event/{id}/statistics` | livestatistik per period (`ALL`/`1ST`/`2ND`) | 38 fält |
| `/api/v1/event/{id}/shotmap` | **per skott**: xG, minut, typ, situation, spelare | 15 skott i testmatchen |
| `/api/v1/event/{id}` | status, ställning, `time.currentPeriodStartTimestamp`, `changes.changeTimestamp` | 10 kB |
| `/api/v1/event/{id}/incidents` | mål, kort, byten | ✅ |
| `/api/v1/event/{id}/graph` | momentum per minut | 58 punkter |

Fälten i `statistics` under pågående match (Ekstraklasa, Pogoń–Legia, 2:a halvlek):

```
Match overview: Ball possession, Expected goals, Big chances, Total shots,
                Goalkeeper saves, Corner kicks, Fouls, Passes, Tackles, Free kicks
Shots:          Total shots, Shots on target, Hit woodwork, Shots off target,
                Blocked shots, Shots inside box, Shots outside box
Attack:         Big chances missed, Touches in penalty area, Fouled in final third, Offsides
Passes:         Accurate passes, Final third entries, Final third phase, Long balls, Crosses
Duels:          Duels, Dispossessed, Ground/Aerial duels, Dribbles
Defending:      Tackles won, Interceptions, Recoveries, Clearances
Goalkeeping:    Total saves, Goals prevented, Big saves, High claims
```

Allt som idén behöver finns alltså: **Expected goals, Big chances, Total shots,
Shots on target, Shots inside box, Touches in penalty area, Corner kicks** — och
dessutom per halvlek, vilket gör det möjligt att mäta *takt* och inte bara nivå.

**Uppdateringstakt (mätt):** 9 nya skott fångades genom att polla `shotmap` var 6:e
sekund och jämföra mot Kambis sekundexakta matchklocka:

| skottets minut | matchklocka när det syntes | lag |
|---|---|---|
| 35 | 35,1 | +0,10 min |
| 37 | 36,8 | −0,20 min |
| 37 | 36,9 | −0,10 min |
| 35 | 36,1 | +1,12 min |
| 64 | 65,1 | +1,07 min |
| 86 | 85,7 | −0,32 min |
| 86 | 86,7 | +0,68 min |
| 55 | 61,8 | +6,77 min |
| 55 | 63,8 | +8,77 min |

**Median +0,68 min (~41 s).** Sju av nio inom ±1,1 minut — i praktiken realtid
(skottminuten är avrundad nedåt, så ±1 min är mätbrus). De två avvikarna gäller samma
match (irländska Premier Division) och är **retroaktiva efterregistreringar** — en
scout lade till skott i efterhand. Det betyder att aggregerad xG kan *hoppa bakåt i
tiden*: ett värde man såg för fem minuter sedan kan revideras. En livemodell måste
hantera det (avsnitt 7.4).

**Anropstakt:** 175 anrop på 45 sekunder (3,9/s) → **alla HTTP 200**. Sofascore
rate-limitar inte oss vid rimlig last. Det är inte en begränsning.

**Täckning — den verkliga begränsningen.** Av 57 pågående matcher hade **3 (5 %)**
xG i `statistics`:

```
✓ 16316944 Ekstraklasa                | Pogoń Szczecin – Legia Warszawa
✓ 15238130 Premier Division (IRL)     | St. Patrick's Athletic – Dundalk
✓ 16431092 Liga Profesional (ARG)     | Gimnasia y Esgrima – Central Córdoba
```

Lägre serier ger antingen `statistics` **utan** xG (7–10 fält i stället för 38) eller
rent 404:

```
Arborg (ISL 4. deild)     statistics HTTP 200  xG=NEJ (7 fält)    shotmap HTTP 404
Fjolnir (ISL 2. deild)    statistics HTTP 200  xG=NEJ (10 fält)   shotmap HTTP 404
Njardvik (ISL 1. deild)   statistics HTTP 404                     shotmap HTTP 404
```

5 % är dock missvisande lågt som allmän siffra — kvällens spelschema (fredag i juli)
dominerades av träningsmatcher, isländska divisioner och brasilianska U20-matcher.
**Öppen fråga som måste testas innan något byggs:** får Allsvenskan/Superettan/
Eliteserien/OBOS/MLS xG *under* matchen, eller bara efter slutsignal?
`docs/plan.md` noterar att Sofascores shotmap saknar xG-fältet för svenska matcher
(*"Eliteserien 30/30 skott med xG — Allsvenskan 0/31"*), vilket gör det direkt
troligt att svensk live-xG är svag eller obefintlig. Testbart imorgon:
Degerfors–Djurgården 2026-07-25 13:00Z (`sid 15272469`), Kalmar–Mjällby 15:30Z
(`15272471`), Kristiansund–Start 14:00Z (`15260852`).

### 1.2 Kambi / Svenska Spel — ✅ live-odds och live-scoreboard, ingen xG

```
GET https://eu-offering-api.kambicdn.com/offering/v2018/svenskaspel/
      listView/football/all/all/all/in-play.json?lang=sv_SE&market=SE
GET .../betoffer/event/{id}.json?lang=sv_SE&market=SE
```

`liveData` per event:

```json
{"matchClock": {"minute": 95, "second": 17, "period": "Andra halvlek",
                "running": true, "periodId": "SECOND_HALF"},
 "score": {"home": "2", "away": "1", "who": "HOME"},
 "statistics": {"football": {"home": {"yellowCards": 0, "redCards": 0, "corners": 6},
                             "away": {"yellowCards": 1, "redCards": 0, "corners": 3}}}}
```

Sekundexakt matchklocka — jag använde den som **referensklocka** i alla latensmätningar.
Ingen xG, inga skott.

Live-marknader (44 betOffers i en pågående Ekstraklasa-match): `Fulltid`, `Antal mål`,
`Antal hörnor`, `Gör mål`, `Korrekt resultat`, `Handicap`, `3-vägshandicap`,
`Dubbelchans`, `Första målgörare`, `Första målet`, `Andra halvlek`,
`Antal mål för {lag}`. Marknaden idén skulle bo i (`Antal mål` / `Första målet`) finns
alltså.

### 1.3 Pinnacle Arcadia — ✅ live-odds finns, ⛔ men kraftigt fördröjda

Detta är utredningens viktigaste fynd och behandlas separat i avsnitt 2.

Live-matchuper finns i utbudet men **filtreras bort av dagens klient**. `pinnacle.py`
har raden

```python
if m.get("parent") is not None or m.get("type") != "matchup":
    continue
```

och *alla* live-matchuper har `parentId` (förälder = förmatch-matchupen). Live-objektet
ser ut så här:

```json
{"id": 1632871746, "isLive": true, "status": "started", "liveMode": "danger_zone",
 "state": {"minutes": 35, "state": 3},
 "participants": [{"alignment": "home", "state": {"score": 1, "redCards": 0}}, ...],
 "parent": {"participants": [{"state": {"corners": 6, "score": 1, "yellowCards": 1}}, ...]},
 "periods": [{"period": 0, "status": "open", "cutoffAt": "2026-07-24T22:01:51Z"}, ...]}
```

`state.state` = 1 (första halvlek) / 3 (andra halvlek), verifierat mot Kambis `periodId`.
`state.minutes` = minuter in i pågående period. Hörnor och gula kort ligger på
**föräldern**, mål och röda kort på live-objektet.

**Rätt endpoint för live-priser** (viktigt — jag gick först fel):

```
✅ GET /0.1/matchups/{live_id}/markets/straight          -> LIVE-priser
❌ GET /0.1/matchups/{live_id}/markets/related/straight  -> FRUSNA förmatchpriser
```

`related/straight` returnerar familjens marknader med `matchupId` = föräldern och
`cutoffAt` = avspark. Använder man den tror man sig läsa live-odds men läser
förmatchodds från timmar tillbaka. Konkret exempel (Pogoń–Legia, 0-0 i 58:e minuten):

| | 1 | X | 2 |
|---|---|---|---|
| `related/straight` (förmatch, frusen) | 2,66 | 3,45 | 2,68 |
| `markets/straight` (live) | 3,89 | 2,11 | 2,98 |

Live-utbudet omfattar `moneyline`, `spread` (AH), `total`, `team_total` — med
live-limiter (`maxRiskStake` 50–2 250 USD). Dessutom finns **separata
live-hörnmatchuper** (`units: "Corners"`, deltagarnamn `"Lag (Corners)"`), vilket är
direkt relevant eftersom projektet redan modellerar hörnor.

### 1.4 FotMob — ⛔ blockerad (bekräftar `docs/plan.md`)

```
GET https://www.fotmob.com/api/matches?date=20260724       -> HTTP 404 (HTML)
GET https://www.fotmob.com/api/matchDetails?matchId=...    -> HTTP 404 (HTML)
```

Kräver signerad `x-mas`-header. Ingen förändring sedan 2026-07-12.

### 1.5 ESPN — ✅ skott/hörnor live, ingen xG

```
GET https://site.api.espn.com/apis/site/v2/sports/soccer/swe.1/scoreboard   (kräver --compressed)
```

9 statistikfält per lag: `totalShots`, `shotsOnTarget`, `wonCorners`, `possessionPct`,
`foulsCommitted`, `totalGoals`, `goalAssists`, `shotAssists`, `appearances`. Ingen xG.
Duger som **fallback för skottdata** i ligor där Sofascore saknar xG, men skott utan
kvalitetsvikt är en betydligt svagare signal än xG.

### 1.6 Understat — ej relevant

Publicerar efter matchslut och täcker bara topp-5-ligorna. Ingen av projektets
actionable-ligor. Inte vidare testad.

---

## 2. Färskheten — det som avgör frågan

### 2.1 Pinnacles guest-API är Cloudflare-cachat i 15 minuter

```
cache-control: public, max-age=905, must-revalidate
cf-cache-status: HIT
age: 883
```

Vid vanlig pollning av samma URL är man **fastlåst vid ett cachat objekt** som åldras
sekund för sekund tills TTL:en går ut:

```
rak URL        HTTP 200 age=242 cf=HIT
rak URL +20s   HTTP 200 age=263 cf=HIT
rak URL +40s   HTTP 200 age=283 cf=HIT
rak URL +60s   HTTP 200 age=303 cf=HIT
```

Cache-busting fungerar **inte** med godtyckliga parametrar:

```
?_t=1                          HTTP 204  (tomt svar — API:t avvisar okända parametrar)
Cache-Control: no-cache header HTTP 200 age=242 cf=HIT  (ignoreras)
?withSpecials=false            HTTP 200 cf=MISS   ← ny cache-nyckel, färskt
?primaryOnly=false             HTTP 200 cf=MISS   ← ny cache-nyckel, färskt
```

Kända parametrar skapar en ny cache-nyckel och ger **en** färsk läsning — därefter är
även den en HIT i 905 sekunder. Man kan alltså rotera ett fåtal parametrar för att
tvinga fram några extra färska läsningar per kvart. Det är cache-missbruk, det är
skört, och projektet vet redan att *"Arcadia Cloudflare-blockar i perioder på
IP-nivå — headers/TLS hjälper EJ"*. Att systematiskt busta deras cache är en bra väg
till permanent block — och därmed till att **förmatch**-flödet, som faktiskt fungerar,
dör.

### 2.2 Även en färsk läsning är 6 minuter gammal

Detta är det avgörande. Jag jämförde Pinnacles `state` mot Kambis sekundexakta
matchklocka, med **tvingad cache-MISS** så att CDN:en inte är förklaringen:

**Runda 1 (`?primaryOnly=true`, cf=MISS):**

| match | Kambis klocka | Pinnacles klocka | diff |
|---|---|---|---|
| Treaty United–Athlone Town | 72,2 | 66 | −6,2 |
| Gimnasia Mendoza–Central Córdoba | 29,9 | 24 | −5,9 |
| Kerry–Finn Harps | 70,0 | 64 | −6,0 |
| Víkingur Reykjavík–Keflavík | 12,1 | 6 | −6,1 |
| Alianza Atlético–Los Chankas | 14,5 | 8 | −6,5 |
| 2 de Mayo–Rubio Ñú | 53,6 | 48 | −5,6 |
| Odra Opole–Arka Gdynia | 57,8 | 52 | −5,8 |
| Cobh Ramblers–Bray Wanderers | 70,4 | 64 | −6,4 |
| Pogoń Szczecin–Legia Warszawa | 79,6 | 74 | −5,6 |
| St Patrick's–Dundalk | 58,0 | 52 | −6,0 |

**Median −6,0 min (n=10).** Runda 2 med en annan parameterkombination 20 sekunder
senare gav **−6,4 min** för samma tio matcher (spann −6,0 till −6,9).

Det är alltså ingen slump och ingen CDN-artefakt: **Pinnacle levererar medvetet ett
~6 minuter fördröjt live-flöde till gratis-API:t.** Vid vanlig pollning blir det
**−15,0 min** (median, n=20) när CDN-cachen läggs ovanpå.

### 2.3 Konsekvensen syns direkt i ställningen

Fördröjningen är inte abstrakt — den gör att Pinnacle visar **fel ställning**:

| match | verklig ställning (Kambi) | Pinnacles bild |
|---|---|---|
| Alianza Atlético–Los Chankas | 1-0 vid 22:36 | **0-0 vid 13'** |
| Víkingur Reykjavík–Keflavík | 2-0 vid 20:10 | **1-0 vid 11'** |
| St Patrick's–Dundalk | 1-1 (Sofascore) | **0-1** |

Ett pris som är satt för 0-0 när det står 1-0 är inte ett "något gammalt pris". Det är
ett pris för en annan match.

### 2.4 Svenska Spel prissätter om var 46:e sekund

Jag pollade Kambis in-play-lista var 8:e sekund i 10 minuter (75 pollningar,
1 803 observationer) och räknade prisändringar på `Fulltid`. Efter att esport
(FIFA/eFootball, namn som `Real Madrid (vivienne)`) filtrerats bort återstår 15 äkta
fotbollsmatcher:

- **prisändringar: median 1,32 per minut** (spann 0,91–2,13)
- **→ ett SvS live-1X2-pris lever i median 46 sekunder**
- suspension av `Fulltid`: **median 0 %, max 8 %** av observationerna

Suspension är alltså *inte* det stora hindret — marknaden är öppen nästan hela tiden.
Hindret är takten: **din referens uppdateras var 6:e–15:e minut, marknaden du spelar
mot var 46:e sekund.** Referensen ligger 8–20 omprissättningar efter.

---

## 3. Marginalerna — vad du faktiskt måste slå

Mätt på samtidiga snapshots av samma matcher och samma linjer.

| Marknad | Pinnacle förmatch | Pinnacle live | **Svenska Spel live** |
|---|---|---|---|
| 1X2 | 4,11 % (n=6) | 6,58 % (n=9) | **11,03 % (n=9)** |
| Totalen, 2-vägs | 4,03 % (n=45) | 5,67 % (n=21)¹ | **9,89 % (n=21)** |

¹ Från jämförelsen mot SvS (gemensamma linjer). Ett bredare tvärsnitt över alla
Pinnacles live-linjer samma kväll gav 4,87 % (n=49) — samma storleksordning. Skillnaden
är att SvS-jämförelsen bara innehåller linjer som *båda* böckerna erbjuder, vilket
tenderar att vara linjer längre från mitten.

Live-marginalen är alltså ~1,5× förmatchmarginalen hos Pinnacle och ~2,5× hos
Svenska Spel. På en 2-vägs marknad med 9,9 % overround måste du slå den sanna
sannolikheten med **ca 4,7 procentenheter per sida** bara för att gå jämnt upp.

Och direkt jämförelse av SvS live-priser mot Pinnacles power-devigade live-fair:

- **1X2:** median edge **−10,3 %**; endast 11 % av tecknen positiva, 7,4 % över +2 %
- **Totalen:** median edge **−9,8 %**; 40 % av sidorna "positiva"

De där 40 % är **inte** värdespel. De är fördröjningsartefakter — se 6.3.

---

## 4. Modellen — hur man skulle kvantifiera "målet är på gång"

### 4.1 Specifikation

In-play-Poisson med Gamma-Poisson-krympning av observerad xG-takt mot förmatchtakten.
Detta är den naturliga utvidgningen av det som redan finns i `oddset_model.py`.

**Tillstånd vid minut `t`:** ställning `(g_h, g_a)`, ackumulerad xG `(x_h, x_a)`,
röda kort, spelad tid.

1. **Förmatch-intensiteter** `μ_h, μ_a` (mål/90) — hämtas som idag ur den sharpa
   förmatch-totalen + supremacy (ankringen i `oddset_model._anchor_total`, som är
   settlement-medveten sedan WP1). Detta är den enda delen som är sharp-ankrad, och
   den är ankrad till en linje som är timmar gammal — vilket är helt i sin ordning,
   för den är *stängd*.

2. **Posterior måltakt.** Betrakta xG-ackumulationen som en observation av lagets sanna
   takt `θ_h`. Med Gamma-prior med medelvärde `μ_h/90` och priorstyrka `τ` minuter:

   ```
   θ̂_h = (τ · μ_h/90 + x_h) / (τ + t)
   ```

   `τ` är hela modellens knäckfråga: hur många minuters spel krävs innan observerad
   xG-takt ska väga lika tungt som förmatchbedömningen? `τ = 90` betyder att vid
   `t = 60` väger observationen 40 %.

3. **Ställningseffekter.** Ledande lag sänker takten, jagande lag höjer den. Multiplikatorer
   per måldifferens, kalibrerade separat — **inte gissade**, för de är stora nog att
   dominera xG-signalen.

4. **Kvarvarande mål:** `Λ_h = θ̂_h · (T − t)` med `T ≈ 90` + förväntad tilläggstid.

5. **Utfallsfördelning:** samma DC-korrigerade Poisson-matris som redan finns, applicerad
   på *kvarvarande* mål och adderad till nuvarande ställning.

### 4.2 Hur stor blir kanten — och varför den siffran är ett varningstecken

Användarens scenario, räknat: **1-1 i 60:e minuten, hemmalaget har 3,0 xG.**
Förmatch `μ_h = 1,45`, 35 minuter kvar.

| τ (min) | posterior takt (mål/90) | E[mål kvar] | P(hemma gör mål) |
|---|---|---|---|
| 30 | 3,48 | 1,35 | 74,2 % |
| 60 | 2,97 | 1,16 | 68,6 % |
| 90 | 2,67 | 1,04 | 64,6 % |
| 120 | 2,47 | 0,96 | 61,7 % |
| ∞ (ignorera xG) | 1,45 | 0,56 | **43,1 %** |

Att gå från "ignorera xG" till `τ = 90` flyttar sannolikheten **+21,5 procentenheter**.

Det ser ut som ett guldläge. Det är i själva verket ett larm: **21 pp ligger inte och
skräpar på en marknad som Pinnacle prissätter automatiskt med Sportradar-flöde.**
Rätt sätt att läsa tabellen är baklänges — *hur mycket av signalen måste marknaden
missa för att det ska bli spelbart?*

| marknaden fångar | kvarvarande kant | relativ EV |
|---|---|---|
| 0 % | 21,5 pp | +49,9 % |
| 50 % | 10,8 pp | +20,0 % |
| 70 % | 6,5 pp | +11,1 % |
| **85 %** | **3,2 pp** | **+5,3 %** |
| 95 % | 1,1 pp | +1,7 % |

Ställ det mot marginalerna i avsnitt 3:

- För att slå **SvS live-1X2 (11,0 %)** måste marknaden fånga **mindre än ~70 %**.
- För att slå **SvS live-totalen (9,9 %)** måste den fånga **mindre än ~72 %**.
- För att ens slå **Pinnacles egen live-totalen (5,7 %)** måste den fånga **under ~84 %**.

Frågan är alltså inte "är xG informativt?" (det är det) utan "prisar Pinnacle och Kambi
in mindre än 70 % av det?". Nästa avsnitt mäter det.

### 4.3 Hur snabbt försvinner kanten

Snabbt, av tre skäl som multipliceras:

- **Klockan.** Med 30 minuter kvar är varje minut 3,3 % av återstoden. En kant uttryckt
  i kvarvarande mål eroderar mekaniskt.
- **Nästa händelse.** Ett mål ändrar hela fördelningen och ställningseffekterna. Typiskt
  avstånd mellan mållägen i en het match är 5–10 minuter.
- **Omprissättningen.** SvS byter pris var 46:e sekund.

Halveringstiden på en in-play-kant är i praktiken **enstaka minuter**. Med en referens
som är 6–15 minuter gammal hinner kanten uppstå, prisas bort och försvinna innan din
referens ens sett att den fanns.

---

## 5. Prisar marknaden redan in det underliggande spelet?

### 5.1 Naturligt experiment: Pogoń Szczecin–Legia Warszawa

Kvällens match var exakt användarens scenario: **0-0 medan ena laget skapade allt.**

| Pinnacles klocka | ställning | xG | skott | stora chanser | live 1X2 | live totalen (0,5) |
|---|---|---|---|---|---|---|
| förmatch | – | – | – | – | 2,66 / 3,45 / 2,68 | total-λ 2,56 |
| 58' | 0-0 | 0,55–1,20 | 7–13 | 0–2 | 3,89 / **2,11** / 2,98 | 1,44 / 2,80 |
| 74' | 0-0 | 0,67–**2,16** | 7–**18** | 1–**4** | 4,54 / **1,70** / 3,89 | 1,95 / 1,89 |

**Två observationer, båda obekväma för idén.**

**(a) 1X2 är fel marknad.** Legia byggde upp 2,16 xG mot 0,67 utan att göra mål — och
deras pris gick **ut**, från 2,98 till 3,89. Draget som dominerar är klockan: oavgjort
gick från 2,11 till 1,70. "Målet är på gång" översätts alltså **inte** till värde på
lagets matchresultat. Idén kan bara bo i *kvarvarande mål* / *nästa mål* / *hörnor* —
och det är marknader där SvS tar ~10 %.

**(b) Marknaden hade redan höjt sin målförväntan.** Marknadens implicerade kvarvarande
λ, jämförd med en naiv baslinje (förmatch-λ skalad linjärt med återstående tid):

| snapshot | marknadens kvar-λ | naiv baslinje | kvot |
|---|---|---|---|
| 58' (mot Pinnacles egen klocka) | 1,08 | 0,98 | **1,10×** |
| 58' (mot verklig klocka, +6 min) | 1,08 | 0,82 | **1,32×** |
| 74' (mot Pinnacles egen klocka) | 0,68 | 0,54 | **1,24×** |
| 74' (mot verklig klocka, +6 min) | 0,68 | 0,38 | **1,78×** |

Marknaden låg alltså **1,1–1,8× över** vad ställning och tid ensamt motiverar — i just
den match där xG sprang iväg. Det är inte ett bevis för att exakt hela signalen är
inprisad, men det är direkt evidens **mot** premissen att marknaden bara tittar på
resultattavlan. Kombinerat med tabellen i 4.2 (marknaden behöver fånga <70 % för att
lämna något efter SvS-marginalen) pekar detta åt ett håll.

*Metodreservation:* Pinnacles snapshot är ~6 minuter fördröjd, så raderna
"mot verklig klocka" är den korrekta tolkningen men xG-siffran är då något färskare än
priset. Osäkerheten är i storleksordningen en tiondel av kvoten, inte tillräckligt för
att vända slutsatsen.

### 5.2 Varför man ska förvänta sig detta

Pinnacles live-priser sätts av en automatiserad modell matad med ett professionellt
realtidsflöde (Sportradar/Opta-klass) som innehåller skott, farliga anfall, position på
plan och bollinnehav — kalibrerad på miljontals matcher. Det är samma
informationsklass som Sofascores xG, fast snabbare och bredare. Antagandet att den
modellen skulle ignorera 70 % av chansskapandet är inte försvarbart.

---

## 6. Fallgropar

### 6.1 Ingen sharp-ankare — projektets dyraste lärdom, igen

`CLAUDE.md`: *"Metodregel (dyrast lärdom från vm): ENDAST marknadspriser får logga
flaggor — modellhärledda sannolikheter förorenar facitet."* Och: *"Live-skydd: startade
matcher sparas ej (odds), värderas ej, modelleras ej — och 54 live-förorenade rader
städades ur DB."*

En livebetting-tracker kräver att man **medvetet slår hål på live-skyddet**. Utan en
färsk sharp live-referens är produkten per definition **amber** — och amber får inte
generera spelförslag, notiser eller CLV-flaggor. Man skulle alltså bygga en funktion vars
enda tillåtna utdata är "titta här", i ett projekt som redan har lärt sig att sådana
lampor blir spelade på ändå.

### 6.2 Inget CLV-facit går att bygga

Live-spel har ingen meningsfull stängningslinje. Marknaden upphör vid slutsignal utan
en referenspunkt som motsvarar förmatchens closing line. Man skulle kunna använda
Pinnacles egen live-linje 6–10 minuter senare som pseudo-stängning — men **det vore
cirkulärt och trivialt**: eftersom Pinnacles flöde är 6 minuter fördröjt kan
en realtidskälla som Sofascore per konstruktion "förutsäga" den. Ett facit byggt så
skulle visa fantastiska resultat och betyda exakt ingenting. Det är den farligaste
enskilda fällan i hela idén, för den ser ut som validering.

### 6.3 Fördröjningsartefakter ser ut som enorma värdespel

Detta hände i kvällens mätning, oavsiktligt, och reproducerar `docs/plan.md`:s
*"+112 % 'edges'"*-incident nästan exakt. När jag jämförde SvS live-totalen mot
Pinnacles live-fair:

```
Víkingur Reykjavík–Keflavík  linje 3.5 | SvS 1.13/4.60 | Pin 1.76/2.07 | edge Under +111,6 %
Alianza Atlético–Los Chankas linje 1.5 | SvS 1.07/6.40 | Pin 1.34/3.09 | edge Under  +93,1 %
```

Och de verkliga ställningarna, hämtade i samma ögonblick:

| match | verkligt | Pinnacles bild |
|---|---|---|
| Víkingur–Keflavík | **2-0 vid 20:10** | 1-0 vid 11' |
| Alianza–Los Chankas | **1-0 vid 22:36** | 0-0 vid 13' |

Hela "kanten" är ett mål som Pinnacle inte sett än. **De två största "värdespelen" i
hela mätningen var de två matcher där fördröjningen råkat gömma ett mål.** Det är inte
en detalj att koda bort — det är den systematiska felkälla som en naiv implementation
skulle producera hundratals gånger per kväll, och den är korrelerad med precis de
matcher som är mest actionable (mål har just fallit, marknaden rör sig).

### 6.4 Latensen är omvänd mot det man förväntar sig

Premissen i uppdraget — "statistiken är alltid efter marknaden" — stämmer inte.
Sofascore ligger ~41 sekunder efter verkligheten; Pinnacle 6–15 minuter. Att statistiken
är *före* referensmarknaden är dock ingen fördel, för man spelar inte mot referensen.
Man spelar mot Kambi, som är i realtid. Nettoläget är: **du är i realtid mot Kambis
realtid, med en dömande instans som är 6–15 minuter efter.** Det ger ingen edge, bara
en oförmåga att veta om man har en.

### 6.5 Retroaktiva xG-revideringar

Två av nio observerade skott registrerades 6,8 och 8,8 minuter i efterhand. En
livemodell som triggar på xG-*förändring* kommer att larma på händelser som redan är
minuter gamla, och en modell som loggar tillstånd för utvärdering får ett tillstånd som
senare ändras. Alla mätningar måste vara point-in-time-stämplade med både
observationstid och den underliggande matchminuten — samma disciplin som PH2:s
`pit-v2` i poolspåret.

### 6.6 Cloudflare-risk mot befintlig drift

Att pollen live kräver aggressiv Pinnacle-trafik med cache-busting. Projektet vet att
Arcadia IP-blockerar i perioder. Att riskera det **fungerande** förmatchflödet — som är
hela Oddset-delens ryggrad — för ett live-experiment med negativ förväntad avkastning
är en dålig affär.

### 6.7 Täckning och exekvering

- Live-xG saknas i lägre serier (avsnitt 1.1) och är **oklar för Allsvenskan**.
- Live-limiterna hos Pinnacle är 50–2 250 USD; hos SvS gäller deras egna live-tak.
- Suspension är måttlig (median 0 %, max 8 %) — inte huvudproblemet, men vid exakt de
  tillfällen då signalen är starkast (efter mållägen) är sannolikheten för suspension
  som störst.

---

## 7. Genomförbarhetsbedömning

**Går det att göra +EV med gratisdata och 30–90 sekunders fördröjning?**

Frågan innehåller ett antagande som mätningen motbevisar: fördröjningen är inte 30–90
sekunder på det som betyder något. Sofascore klarar 41 sekunder, men den **sharpa
referensen är 6–15 minuter fördröjd** och det går inte att köpa sig ur med gratis-API:t.

Med det på plats:

| krav | läge |
|---|---|
| Live xG/skott gratis | ✅ Sofascore, ~41 s, 38 fält |
| Live-odds gratis | ✅ Pinnacle + Kambi |
| **Färsk sharp referens** | ⛔ 6–15 min fördröjd, ej lösbar gratis |
| Marginal att slå hos SvS | ⛔ 9,9–11,0 % |
| Modellen behöver ha rätt om marknaden | ⛔ marknaden måste fånga <70 % av xG-signalen |
| Evidens att marknaden missar signalen | ⛔ tvärtom: 1,1–1,8× över naiv baslinje |
| Möjligt att validera med CLV | ⛔ ingen ärlig stängningsreferens finns |
| Risk mot befintlig drift | ⛔ Cloudflare-block på Arcadia |

**Svaret är nej.** Inte "svårt" — strukturellt nej, av två oberoende skäl som var för sig
räcker:

1. **Referensproblemet.** Ingen färsk sharp linje ⇒ ingen mätbar edge ⇒ per projektets
   egna regler ingen actionable signal. Detta går inte att modellera bort.
2. **Marginalproblemet.** Även med perfekt information måste modellen slå Pinnacles
   live-modell med >10 procentenheter för att SvS live ska bli +EV. Projektets
   förmatchmodell ligger på ±0 % mot marknaden efter månaders arbete med bättre data
   och obegränsad betänketid.

Det som skulle krävas för ett ja: betald realtids-sharp (Pinnacle API med konto,
Betfair exchange-stream) plus en live-modell som slår den. Det är ett annat projekt,
med löpande kostnad och en helt annan riskprofil.

---

## 8. Vad som *ändå* är värt något i fyndet

Utredningen grävde fram tre saker som har värde utanför live-idén:

1. **`/matchups/{id}/markets/straight`** — per-matchup-endpointen är 8 kB mot
   bulkens 32 MB + 20 MB, och `related/straight` ger frusna förmatchmarknader.
   Det kan vara användbart för riktad förmatch-uppdatering nära avspark
   (`FAST_WITHIN_H`-varvet) utan att dra hela bulken.
2. **Att bulk-endpointen är cachad i 905 s** bör dokumenteras i `plan.md`. Dagens
   30-minutersvarv påverkas inte nämnvärt, men snabbvarvet var 4:e minut hämtar
   **samma cachade objekt flera gånger** — det är gratis att veta och kan påverka hur
   `fetched_at` ska tolkas i WP2-prisregeln.
3. **Sofascores livestatistik-endpoints** är verifierade och snabba. Om man någon gång
   vill ha *halvtidsdata* för förmatchmodellen (t.ex. andra halvlek-marknader före
   avspark på halvlek 2, eller ren efteranalys) finns underlaget.

---

## 9. Om något ändå ska byggas: mätpilot, inte tracker

Ska frågan avgöras empiriskt i stället för på argumenten ovan, är det **enda**
metodologiskt hederliga upplägget en skuggmätning som inte får rekommendera något —
i samma anda som WP5-ledgern och pool-PH2.

**Det som INTE får göras:** mäta modellen mot Pinnacles fördröjda live-linje. Det är
cirkulärt (6.2) och kommer att se ut som en succé.

**Det som kan mätas ärligt:** förutsäger vår xG-signal **Kambis egen efterföljande
rörelse**? Kambi är i realtid och är marknaden man faktiskt spelar mot, så deras
kommande pris är en giltig och icke-cirkulär måltavla.

```
backend/app/live_shadow.py          ny, isolerad — importeras aldrig av
                                     oddset.py / oddset_value.py / clv.py / main.py:s tips-vägar
  collect_live()                    var 30:e sekund under pågående matcher i
                                     ACTIONABLE_LEAGUE_KEYS:
                                       Sofascore /statistics + /shotmap + /event
                                       Kambi in-play listView (klocka, ställning, 1X2, Antal mål)
                                     -> tabell live_state_capture (append-only, PIT-stämplad
                                        med BÅDE observationstid och matchminut)
  score_state()                     in-play-Poisson enligt 4.1, τ förregistrerat
                                     -> tabell live_prediction (fryst, aldrig bakfylld)
  settle()                          T+2 min, T+5 min, T+10 min: Kambis pris för samma
                                     selektion -> live_settlement
```

**Förregistrera innan första raden samlas** (annars är facitet värdelöst):
τ, ställningseffektmultiplikatorer, vilka marknader som mäts (`Antal mål` och
`Första målet` — **inte** 1X2, enligt 5.1a), tröskeln för vad som räknas som signal,
och stoppregeln.

**Utvärderingskriterium:** korrelerar modellens signal med Kambis prisrörelse de
följande 2/5/10 minuterna, efter att man kontrollerat för ställning, matchminut och
mål som fallit i mellantiden? Klusterbootstrap per match, samma maskineri som
`oddset_ledger`.

**Stoppregel:** om signalen inte förklarar Kambis rörelse med en undre
90 %-KI-gräns > 0 efter 300 observationer, läggs spåret ner. Och även om den *gör* det
är nästa fråga fortfarande om effekten är större än 9,9 % marginal — vilket den
mycket sannolikt inte är.

**Förarbete som måste göras först, och som ensamt kan döda piloten:**
verifiera att Allsvenskan/Superettan/Eliteserien/OBOS/MLS faktiskt får **live** xG.
Testbart 2026-07-25 (matcher listade i 1.1). Utan live-xG i de actionable ligorna finns
inget att mäta.

**Vakter, ovillkorliga:**
- Egna tabeller, eget prefix, ingen skrivning till `oddset_odds`, `oddset_value_log`,
  `value_log` eller `sharp_snapshots`.
- Live-skyddet i `collect`/`attach_value`/`attach_model` rörs **inte**.
- Ingen UI-yta, inga notiser, ingen Kelly, ingen export.
- Pinnacle live pollas **inte alls** — dels för att det är cirkulärt, dels för att
  skydda förmatchflödet från Cloudflare-block.

Uppskattad omfattning: ~2 dagars arbete för piloten, plus flera veckors passiv
insamling innan något kan sägas. Förväntat utfall givet avsnitt 5: signalen finns i
datat men är redan inprisad, och den återstående kanten ligger under marginalen.

---

## 10. Rekommendation

**BYGG INTE.**

Motiveringen i en mening: *den sharpa referens som hela projektets metod vilar på är
6–15 minuter fördröjd i gratisversionen, medan marknaden man spelar mot prissätter om
var 46:e sekund — så varje "edge" man räknar fram live mäter fördröjningen, inte xG:t,
och de största "värdespelen" i min mätning var bevisligen mål som Pinnacle inte sett än.*

Om nyfikenheten kvarstår: kör **förarbetet** i avsnitt 9 (verifiera live-xG för de
svenska/norska ligorna imorgon, en timmes arbete). Faller det ut negativt är frågan
stängd till noll kostnad. Faller det ut positivt är piloten i avsnitt 9 ett
försvarbart — men fortfarande sannolikt resultatlöst — nästa steg.

Den bästa användningen av samma tid är enligt `docs/plan.md`:s egen prioritering att
auditera de första riktiga pool-v2-horisonterna och systemfrysningarna
(`docs/pool-pit-v2-2026-07-24.md`) — där finns data som redan samlas och som faktiskt
kan ändra beslut.

---

## Bilaga: reproducerbara testsnuttar

**Live-matcher med statistik (Sofascore):**
```python
from curl_cffi import requests as cffi
live = cffi.get("https://api.sofascore.com/api/v1/sport/football/events/live",
                impersonate="chrome", timeout=25).json()["events"]
st = cffi.get(f"https://api.sofascore.com/api/v1/event/{live[0]['id']}/statistics",
              impersonate="chrome", timeout=20).json()
for grp in st["statistics"]:
    if grp["period"] == "ALL":
        for g in grp["groups"]:
            for s in g["statisticsItems"]:
                print(s["name"], s["home"], s["away"])
```

**Pinnacles live-priser (rätt endpoint):**
```python
import httpx
H = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "User-Agent": "Mozilla/5.0"}
c = httpx.Client(headers=H, timeout=90)
mu = c.get("https://guest.api.arcadia.pinnacle.com/0.1/sports/29/matchups"
           "?primaryOnly=true").json()          # parametern tvingar cache-MISS
live = [m for m in mu if m.get("status") == "started"
        and m.get("type") == "matchup" and m.get("units") == "Regular"]
mk = c.get(f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{live[0]['id']}"
           "/markets/straight").json()          # INTE .../markets/related/straight
```

**Bevis för cachen:**
```bash
curl -sI -H "X-API-Key: CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R" \
  "https://guest.api.arcadia.pinnacle.com/0.1/sports/29/markets/straight" \
  | grep -iE "age|cache-control|cf-cache-status"
# cache-control: public, max-age=905, must-revalidate
# cf-cache-status: HIT
# age: 820
```

**Kambis realtidsklocka (referensklockan i alla latensmätningar):**
```bash
curl -s "https://eu-offering-api.kambicdn.com/offering/v2018/svenskaspel/listView/\
football/all/all/all/in-play.json?lang=sv_SE&market=SE" \
  | python3 -c "import json,sys
d=json.load(sys.stdin)
for e in d['events']:
    mc=(e.get('liveData') or {}).get('matchClock') or {}
    print(e['event']['homeName'], e['event']['awayName'], mc.get('minute'), mc.get('second'))"
```

Mätskripten ligger i sessionens scratchpad (`crosssec2.py`, `kambi_vs_pin.py`,
`live_totals.py`, `clockdiff.py`, `lat2.py`, `kambi_susp.py`) och är avsiktligt inte
incheckade — de är engångsmätningar, inte produktionskod.
