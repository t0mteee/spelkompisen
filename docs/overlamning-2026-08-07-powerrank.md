# Överlämning 2026-08-07 — powerrank, drift och ligor

**LÄS FÖRST i ny session.** Ersätter `overlamning-2026-08-01-codex-hardening.md`
som aktuell överlämning; den gäller bara som historik.

## Vad som gjordes 2026-08-06/07

Allt ligger på grenen `flashscore-primar-och-signaljournal` (PR #1), pushat.

| Område | Version | Dokument |
|---|---|---|
| Sofascore urkopplad ur radarn, Flashscore ankare | radar **v6** | `live-radar-v6-2026-08-06.md` |
| Proxysignalen på fält som finns | radar **v7** | `radar-proxy-v7-forregistrering-2026-08-07.md` |
| Driftjusterad closing-estimat | sharp **v8** | `closing-drift-v8-forregistrering-2026-08-07.md` |
| Kalibrering, Europaligor, powerrank | — | `plan-powerrank-och-ligor-2026-08-07.md` |

Kortfattat, med de mätningar som motiverade besluten:

* **Radar v6/v7.** Sofascore rapporterade `xg=0.0` i stället för att utelämna
  (Paide–SK Rapid: 0,0/0,0 mot Flashscores 0,09/0,81) — urkopplad ur radarn,
  men lever kvar i resultat, modellstatistik och frånvaro. Länkningen fick
  tre steg (strikt → kontext → ett lag räcker); truppmarkörer spärrar i alla.
  Proxysignalen krävde fält som bara finns när xG finns och tillförde därför
  NOLL matcher; den använder nu `farliga skott` = på mål + blockerade.
  Klockan fryses vid 45 i paus (`STAGE_FROZEN`) i stället för att censureras —
  annars föll matchen ur "starkt chansgap" just när gapet var intressant.
* **Sharp v8.** `fair` är inte Pinnacles pris NU utan en skattning av var det
  STÄNGER. Mätt på 10 908 parade observationer: favoriter driftar −0,61 pp,
  outsiders +0,32 pp, mitten inte alls. Följden i facitet var att
  favoritflaggor gav +0,29 % close-EV (KI rymmer noll) mot outsiders +5,96 %.
  Momentum är dött (R² = 0,000) och ska inte byggas.
* **Smarkets** bortkopplad som andra ankare (56 030 priser på 1X2, NOLL på
  AH/Ö/U/hörnor). **Spärren i `ANCHOR_SOURCES` står kvar** — utan den blir den
  en spelbar bok igen (184 av 476 felaktiga flaggor 2026-07-25).
* **Europaligorna** (PL, Serie A, La Liga, Bundesliga) är fullt följda.
  `RESEARCH_LEAGUE_KEYS` är tom. De ligger utanför `MODEL_LEAGUES` eftersom
  0 av 2 897 matcher har xG.
* **MLS kalibrerad** (T=1,0, n=744). Superettan/OBOS kan INTE kalibreras —
  `FD_URLS` saknar stängningsodds för dem, de ärver poolens huvudliga.
* **Källhälsan** filtreras på `active_sources()`, härledd ur BOOKS/ANCHOR/
  SHADOW/LIVE. Både backend och UI följer den listan.

## Samans fyra punkter på powerranken — KLARA (powerrank-v2)

Fliken 🏋 Lagstyrka finns (`/api/oddset/powerrank`, `PowerRankPanel` i
App.jsx, `oddset_model.powerrank`). Alla fyra åtgärdades 2026-08-07 och
versionen gick `powerrank-v1` → **`powerrank-v2`**.

### 1. Matcher utan xG räknas inte alls (METODFELET, rättat)

`powerrank-v1` räknade `points` på **alla** matcher men `xpts` bara på
xG-täckta, och jämförde dem via skalningen `pts × (n_xg / matches)`. Den
antog att poängen fördelade sig jämnt över täckta och otäckta matcher —
ett antagande utan stöd, som gjorde avvikelsen till en approximation i
stället för en mätning.

Samans invändning var riktig: *"det är ointressant hur många poäng vissa lag
tog för några säsonger sedan om vi inte har någon xG-data att köra det mot."*

**Nu:** en match utan xG bidrar med ingenting alls — inte poäng, inte mål,
inte xPts. Alla kolumner på raden (`matches`, `points`, `xpts`, `goal_diff`,
`overperformance`) mäts på exakt samma matchmängd, så `overperformance` är
`points − xpts` rakt av. Lag helt utan xG-matcher faller ur tabellen i
stället för att visas med `–`: det finns inget att jämföra deras poäng mot,
och en tom rad inbjuder till en jämförelse som inte går att göra. Ingen
bakfyllning av xG (`MODEL_DATA_VERSION`-regeln).

`MIN_MATCHES` prövas mot HELA historiken, inte mot det säsongsfiltrerade
urvalet — annars vore varje tabell tom de första två månaderna av en säsong,
och det är inte styrkeskattningen som blivit osäker av att man tittar på en
kortare period.

Låst av `PowerRankTests` i `tests/test_oddset_model.py`, som bland annat
kontrollerar att skalningen inte kan smyga tillbaka.

### 2. Säsongsfilter (klart)

`powerrank(..., season=...)` filtrerar raderna före aggregeringen; fitten
bakom `att`/`def` ser oförändrat hela poolen med tidsvikt (halveringstid
166 d). Etiketten kommer ur `season_of()`, som avgör kalendertyp på
`FD_SEASON_CODES` — den listan finns redan och beskriver exakt samma
verklighet (höst/vår-ligor publiceras per säsongsfil), så den återanvänds i
stället för en parallell handskriven uppsättning som kan glida isär.
Nordiska ligor och MLS får `2026`, Europaligorna `2025/26`.

Endpointen svarar med `seasons` (bara säsonger som HAR xG — annars vore en
tom vy ett falskt felmeddelande) och `season` (den som faktiskt tillämpades;
en okänd säsong faller tillbaka på hela historiken). UI:t nollställer
säsongen vid ligabyte eftersom etiketterna är ligans egna.

### 3. Läsbar tabell (klart)

Zebra-nyans per rad i `.powerrank` (App.css), lagd PÅ raden så cellernas
egna färgklasser inte slås ut, plus tabular-nums och dämpad rangkolumn.

### 4. Riktiga lagnamn (klart)

Raden bär nu `name`. `_display_name()` väljer bland de RÅA namnen: diakriter
först, därefter det längsta. **Oddssidans namn läggs till som variant** via
`Storage.oddset_team_names()` — football-data strippar diakriter för en del
klubbar (`Djurgarden`), medan oddskällan skriver dem (`Djurgårdens IF`), och
båda är observerade namn. Uppslaget kräver EXAKT samma normaliserade nyckel,
aldrig fuzzy: fel klubbnamn på en i övrigt korrekt rad är värre än ett
tråkigt namn. Diakriter gissas aldrig fram.

Resultat i Allsvenskan: `Djurgårdens IF`, `BK Häcken`, `Mjällby AIF`,
`IFK Göteborg` i stället för `djurgarden`, `hacken`, `mjallby`, `goteborg`.

## Så räknas styrka, anfall och försvar

Frågat av Saman 2026-08-07; förklaringen finns nu också i UI:t
(`<details class="powerrank-method">`), med parametrarna hämtade ur
endpointens `params` så texten inte kan glida ifrån koden.

`fit_league` skattar två tal per lag genom 80 iterationer tills förväntade
mål matchar observerade:

```
λ_hemma = base_liga × hemmafördel_liga × anfall_hemma × försvar_borta
λ_borta = base_liga × anfall_borta × försvar_hemma
```

* **Anfall/försvar** är målfaktorer normaliserade så ligasnittet är 1,00.
  Anfall 1,20 = 20 % fler mål än snittlaget; försvar 0,80 = 20 % färre
  insläppta. **Lägre försvar är bättre.**
* **Styrka = anfall ÷ försvar.** Ett tal att sortera på, men det döljer
  profilen: 1,50 kan vara målrikt-med-läckande-försvar eller defensivt-med-få-mål.
* **Mål räknas xG-viktat** (`XG_WEIGHT = 0,65`), så en tursam vinst lyfter
  inte styrkan lika mycket som en dominant match.
* **Tidsvikt** exponentiell, halveringstid 166 dagar. Fitten är cross-liga
  över hela poolen och alla säsonger — upp-/nedflyttare länkar populationerna.
* Mjuk ridge 0,98 mot 1: i en pool där en liga är svagt kopplad är skalan
  oidentifierbar längs (att·c, def·c, base/c²).

**`#` är styrkerank, inte tabellplacering** — det är avsiktligt. Tabellen
säger vad som har hänt, styrkan vad modellen tror om laget, och avståndet
mellan dem är över/under-kolumnen. En rank som bara speglade tabellen vore
inget mer än tabellen.

## xG-täckningen: varför Allsvenskan har historik men PL inte

Saman noterade 2026-08-07 att Allsvenskan har xG tillbaka till 2024 trots att
projektet bara körts en säsong, och frågade varför Europaligorna saknar det.

**Svaret är att xG ÄR bakfyllt — via Sofascore.** `oddset_data.xg_backfill()`
hämtar tidigare säsonger per liga ur `SOFA_UT`, och mätt i DB:n:

| Liga | xG-rader | Från | Provider |
|---|---|---|---|
| MLS | 972 | 2024-05-12 | sofascore |
| Eliteserien | 611 | 2024-03-31 | sofascore |
| Superettan | 599 | 2024-03-30 | sofascore |
| OBOS | 597 | 2024-04-01 | sofascore |
| Allsvenskan | 574 | 2024-03-30 | sofascore |
| PL / Serie A / La Liga / Bundesliga | **0** | — | — |

`SOFA_UT` innehåller redan de fyra Europaligorna (17/23/8/35). Skälet till
nollan är alltså inte att data saknas hos providern utan att ligorna var
`research_only` fram till 2026-08-07 — Sofascore-insamlingen kördes aldrig
för dem. `oddset_results` har uteslutande `source='fd'` för dem, och
football-data bär inte xG.

**Det betyder att spärren i CLAUDE.md ("0 av 2 897 matcher har xG … xG samlas
framåt, aldrig bakåt") beskriver ett tillstånd som går att åtgärda.**
Regeln "aldrig bakåt" gäller pris- och signalobservationer, där
observationstiden är en del av mätningen. Ett avgjort matchresultat och dess
xG är däremot settlade fakta som inte ändrar sig — därför var Sofascore-
backfillen legitim för de nordiska ligorna, och samma väg är öppen här.

**Inte gjort, kräver Samans beslut:** en backfill flyttar de fyra ligorna in
i `MODEL_LEAGUES`/`FIT_POOLS`, vilket ändrar `MODEL_PARAMS["pools"]` och
därmed modellens `signal_version` — facitgruppen delas. Det är en
förregistreringsfråga, inte en sidoeffekt av en insamling.

## Regler som gäller allt ovan

* Powerranken är **AMBER**. Modellen förutsäger inte Pinnacles drift till
  stängning (r = −0,120, 90 % KI [−0,252, +0,034], R² = 1,4 %), så den får
  inte ge stödchip, lyfta ett spelkort eller påverka edge, urval eller
  notiser. Actionability kräver egen förregistrering och grind.
* **Backend har ingen auto-reload** och ägs numera av launchd:
  `launchctl kickstart -k gui/$(id -u)/com.saman.spelkompisen.backend`.
  Kill + nohup krockar med jobbet (det har `keepalive`).
* Tester: `cd backend && .venv/bin/python -B -m unittest discover -s tests`
  (570 gröna i skrivande stund).
