# Plan: kalibrering, powerranks och Europaligorna — 2026-08-07

Skriven **innan** arbetet påbörjades, på Samans begäran. Beslut samma dag:

> "Vi måste tänka lite mer som de stora syndikaten om vi vill slå closing. De
> gillar powerranks på lag i ligor som de sedan justerar efter stats under
> säsongen." … "många ligor startar snart, av någon anledning har du kallat
> dessa view only (PL, serie A, Bundesliga etc), men vi ska såklart följa
> dessa på samma sätt som tex allsvenskan."

## Utgångsläge, mätt

### Vi HAR redan powerranks och mean reversion

`oddset_model.fit_league` fittar anfalls- och försvarsstyrka per lag
(cross-liga, ridge 0,98, exponentiell tidsvikt med halveringstid 166 d).
Allsvenskan just nu: Djurgården 1,38/0,72 (kvot 1,93), Hammarby 1,38/0,73,
Sirius 1,55/0,84.

Mean reversion finns inbyggd i `XG_WEIGHT = 0,65`: effektiva mål =
0,65·xG + 0,35·faktiska mål. **Ett lag som överpresterar mot xG dras
automatiskt ned** — precis mekanismen Saman efterfrågar. xG-täckning i
merged_results: Allsvenskan 96 %, Superettan 96 %, Eliteserien 100 %,
OBOS 97 %, MLS 73 %.

### Men modellen förutsäger inte closing

Testet hade aldrig gjorts. Korrelation mellan **modellens oenighet med
Pinnacle** (T−24h) och **Pinnacles faktiska drift till stängning**:

```
r = −0,120   90 % KI [−0,252, +0,034]   R² = 1,4 %   (126 matcher)
```

KI rymmer noll. Modellen har i dag inget att säga om vart marknaden är på
väg. Det är konsistent med att den ligger 3–8× sämre än Pinnacle i MAE och
med att momentum är dött (R² = 0,000, mätt i v8-förregistreringen).

### Men vi behöver inte slå Pinnacle — vi slår mjuka böcker

| Liga | n | Close-EV | Pinnacles egen rörlighet T−24h→close |
|---|---|---|---|
| MLS | 117 | **+5,13 %** | 1,66 pp |
| Friendlies | 208 | +3,67 % | 1,47 pp |
| Allsvenskan | 111 | +3,39 % | 1,47 pp |
| Conference League | 164 | +2,61 % | **2,41 pp** |
| Champions League | 59 | +1,63 % | — |
| Eliteserien | 33 | +1,51 % | 1,01 pp |
| Superettan | 39 | +0,70 % | 2,21 pp |
| Europa League | 38 | +0,67 % | 1,79 pp |
| **OBOS** | 38 | **−1,01 %** | — |

Mönstret: **där Pinnacle är osäker tjänar vi minst.** Vårt ankare är sämre
just där. Där Pinnacle är stabil och mjuka böcker slarvar (MLS) tjänar vi
mest. Det talar emot "leta i tunna marknader".

### Kalibreringen är gammal och ofullständig

| Liga | Temperatur T | Satt |
|---|---|---|
| Allsvenskan | 1,00 | 2026-07-12 |
| Eliteserien | 0,85 | 2026-07-12 |
| Superettan | — | **aldrig** |
| OBOS | — | **aldrig** |
| MLS | — | **aldrig** |

Tre av fem primärgrupper i CLV-facitet ärver Allsvenskans temperatur. MLS är
vår mest lönsamma marknad; OBOS vår enda förlustbringande.

### Europaligorna: odds finns, xG saknas helt

| Liga | Pinnacle | SvS | Smarkets | Resultat | varav xG |
|---|---|---|---|---|---|
| Premier League | 10 | 10 | 10 | 760 | **0** |
| Serie A | 10 | 10 | 10 | 760 | **0** |
| La Liga | 10 | 13 | 12 | 765 | **0** |
| Bundesliga | 9 | 9 | 9 | 612 | **0** |

Sharp-flaggor (Pinnacle mot SvS) är alltså **direkt möjliga** — båda priserna
finns. Det som spärrar är två saker i koden:

* `research_only: True` ⇒ `for book in (() if research_only else BOOKS)`
  hämtar **inga sidoböcker alls** (Expekt, Ninja) och inget deep/frånvaro.
* `ACTIONABLE_LEAGUE_KEYS` filtrerar bort dem före `log_and_notify`, alltså
  inga värdeflaggor, ingen CLV, inga notiser.

Modellen är en annan sak: `MODEL_LEAGUES` innehåller dem inte, och med 0 %
xG-täckning skulle `XG_WEIGHT` falla tillbaka på rena mål. xG börjar samlas
framåt så snart ligorna följs på riktigt (`flashscore_data`), aldrig bakåt.

## Arbetet

### 1. Kalibrera Superettan, OBOS och MLS

Kör `cli.py oddsetcalibrate` för de tre. Detta ändrar `cal_t` i
modellens fingeravtryck ⇒ **modellversionen byter automatiskt** och
amber-facitet börjar om för dem. Sharp-tiern är oberörd.

### 2. Powerrank + xPts som synlig, mätbar storhet

I dag är styrkorna en intern biprodukt av `fit_league`. De ska bli:

* **egen vy**: rank per liga med anfall, försvar, kvot och form,
* **per match i Oddset-vyn**: de två lagens rank och styrkekvot,
* **xPts och över/underprestation**: förväntade poäng ur modellens
  målfördelning mot faktiska poäng — måttet Saman efterfrågar för att se
  när ett lag "borde svänga".

**Metodspärr:** detta är en VISNING av en amber-storhet. Den får inte ge
stödchip, inte lyfta ett spelkort och inte påverka edge, urval eller
notiser — samma regel som fällde amber-modellen 2026-07-24 (−4,2 % close-EV).
Om powerranken ska bli actionable krävs egen förregistrering och grind.

### 3. Undersök OBOS negativa close-EV

38 flaggor, −1,01 %. Litet underlag, men det enda spåret som aktivt kostar.
Bryt ned per marknad, bok och tidsfönster innan någon åtgärd föreslås.

### 4. Europaligorna följs som Allsvenskan

`research_only` tas bort för premier_league, serie_a, la_liga, bundesliga.
Följd: sidoböcker hämtas, matcherna blir actionable (värdeflaggor, CLV,
notiser), och de får ordinarie model-capture.

**Konsekvens för V2.2 som måste redovisas:** manifest v4 listar dem under
`scope.research_only_leagues` och `collection.regular_ui: False`. V2.2:s
hypotesprövning (ridge-residual mot Pinnacle-close, mätt i logloss) berörs
inte av att SHARP-tiern börjar flagga — det är skilda spår med skilda
tabeller. Men flaggan manifestet refererar till ändras, så ändringen
dokumenteras vid experimentet och `oddset_v22`-capturen verifieras vara
oförändrad efteråt. Alias-/identitetsfingeravtrycken rörs inte.

## Vad som INTE görs

* **Ingen bakfyllning av xG** för Europaligorna. De 2 897 historiska
  matcherna förblir utan xG; modellen fittar på mål tills framåtinsamlingen
  hunnit i kapp.
* **Ingen ny signalversion för sharp** i detta arbete. Kalibreringen rör
  modellens fingeravtryck, inte sharps; ligtillägget ändrar vilka matcher som
  värderas men inte HUR de värderas.
* **Ingen momentum-/trendmodell.** Falsifierad två gånger (Close-drift v1,
  och R² = 0,000 i v8-mätningen).
