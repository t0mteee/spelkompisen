# Överlämning 2026-08-01 — Flashscore inkörd + signaljournalen härdad

> **ERSATT SAMMA DAG.** Detta dokument beskriver den första Flashscore-piloten
> och behålls endast som historik. v3, den gamla källordningen och
> “första observationen vinner” får inte användas som aktuella instruktioner.
> Läs `docs/overlamning-2026-08-01-codex-hardening.md` och STATUS-blocket i
> `docs/plan.md` i stället.

## Vad som hände (fyra leveranser)

### 1. Codex-committen 38a45ff granskad och härdad (`a352cbd`)

Multi-agent-granskning av live-signaljournalen gav **17 verifierade fynd**,
alla åtgärdade samma dag medan lagret bara hade en rad.

* **Kritiskt:** Kambis betOffer-nivå-`suspended` spärras nu. Utfallen kan stå
  kvar som `OPEN` under en suspension (livereproducerat), så ospelbara priser
  kunde bokföras som spelbara och förorena blindgatens ROI.
* **Allvarligt:** `match_key` är låst per fysisk match (`_locked_key`) — sen
  kanonisk länkning eller källbyte mitt i matchen kunde dubblera
  blindkohorten. Officiellt FT-resultat bevisar numera BÅDA utfallen för
  fler-mål-före-FT; tidigare censurerades bara sanna ettor (nedåtbias).
* Övrigt: `suspended` som eget statusvärde, per-rad-tidsstämplar,
  klockproveniens (`clock_source`/`clock_observed_at`), capture-fel i
  launchd-loggen, `ag=NULL`-vakt, svensk facit-enum, migration som validerar
  före mutation inklusive UNIQUE-vakten.

Fixarna verifierades adversariellt av tre oberoende skeptiker som **fällde och
skärpte tre av dem**. Full rapport: `docs/granskning-codex-38a45ff-2026-08-01.md`.

### 2. Historisk pilot: Flashscore som första livekälla (`5e69c84`)

Saman upptäckte att Chelsea–Tottenham saknade chansdata. Varken FotMob (tomt
stats-block, tom shotmap) eller Sofascore (bara innehav/hörnor/kort) hade
siffror — Flashscore hade full xG, xGOT, skott och stora chanser.

Ny `app/flashscore.py` med egen klient, egen tabell och egen härledd klocka
(stadiets starttid, validerad mot FotMob; okänt stadium ⇒ ingen minut).
**Källvalet rankar DATAKVALITET först** (xG > skott > inget) och låter
Flashscore vinna vid lika, så en match där FotMob har xG nedgraderas aldrig.
Piloten stämplades `chance-gap-shadow-v3`; versionen är numera ogiltig
historik och ersatt av v4 från 21:00Z.

### 3. Flashscore som modelldatakälla (`a6287fd`)

Head-to-head över 8 dygn: **noll bekräftade fall** där Sofascore har statistik
och Flashscore saknar den. Flashscore har dessutom xG för Allsvenskan (10 av
10) där Sofascore ger 0 — och Sofascores egen Allsvenskan-serie har stannat.

Ny `app/flashscore_data.py` fyller saknad xG och hämtar frånvarande spelare
med orsak via Flashscores publika persisted query (hash observerad i deras
egen trafik — inom källgränsen).

### 4. Historisk källordning, ersatt av providerlagret v4 (`440bb64`)

Ordningen ensam räckte inte — den som skrev sist vann. Två spärrar gör
prioriteringen verklig: `oddset_save_result` är nu **första observationen
vinner** för xG/hörnor, och Sofascores frånvarohämtning hoppar över matcher
med färsk `fs:`-capture.

## Driftläge vid överlämningen

* Backend kör på 8002, frontend på 5175.
* launchd: `com.saman.spelkompisen.snapshot` och `.pool` laddade och kör.
* 430 backendtester gröna. Frontend-build grön. Arbetskatalogen ren.
* Backuper tagna före varje DB-ändring, alla i `backend/data/backups/`.
* Serierna rullar redan: 537 Flashscore-captures, 127 frånvarocaptures med
  `fs:`-proveniens, 8 xG-luckor fyllda, 8 signaler under v3.
* Repot har 231 spårade filer. Ser din git-klient tusentals är det venv och
  `node_modules` — de är korrekt ignorerade och ska aldrig committas.

## Öppna trådar

1. **Sofascores Allsvenskan-xG har stannat** — 0 av de 19 senaste matcherna
   mot 63 % historiskt. Flashscore täcker luckan nu, men orsaken är inte
   utredd. Värt en titt: har deras endpoint ändrats eller har vår hämtning
   tystnat?
2. **Serverfrågan — KORRIGERAD 2026-08-11, se
   `docs/serverfragan-avslutad-2026-08-11.md`.** Den provade AWS-adressen fick
   403 på Sofascores live-endpoint, men modellens faktiska endpoint-typer
   testades aldrig. Ett korrekt omtest gjordes därefter på en ny Lightsail-IP:
   samtliga åtta modell-endpoints gav 403. AWS Stockholm är därmed avfärdat
   för nuvarande arkitektur; annan leverantör/region är fortfarande oprövad.
   Nedan är den ursprungliga formuleringen, kvar som historik och inte som
   aktuell slutsats.

   **Serverfrågan.** AWS Lightsail testad med `backend/scripts/kalltest_ip.py`:
   sex av sju källor rena, men **Sofascore ger 403 challenge** från
   datacenter-IP (källgränsen förbjuder att kringgå det). Flashscore fungerar
   därifrån. Mätningen tickar var 20:e minut på 51.21.134.29 —
   `--rapport` visar utfallet per källa. Eftersom Flashscore nu täcker nästan
   allt Sofascore gav, är molnspåret mindre blockerat än tidigare, men
   frånvaro och cupresultat skulle behöva verifieras först. Pi-spåret hemma
   står kvar som enkla alternativet.
3. **v3 hann producera pilotdata** — vid den dåvarande överlämningen 8
   signaler i 8 matcher, varav 3 oddssatta och avgjorda. De är nu ogiltig
   historik och får inte räknas mot blindgaten. Ren gate börjar med v4 från
   21:00Z.
4. **Flashscores säsongsfeeds finns** (`tr_1_181_<tid>_185_<sida>_2_sv_1` på
   `23.flashscore.ninja`) och når hela säsongen med full xG. De används
   MEDVETET inte — historik ska samlas framåt, inte bakfyllas. Om du någon
   gång vill bygga historik måste det förregistreras som ett eget experiment.

## Då föreslaget arbete — ersatt av nya överlämningen

* Låt serierna växa. Kontrollera veckovis: signaljournalens statusfördelning
  (`suspended`/`not_offered`/`source_error`), Flashscores xG-fyllnadsgrad och
  frånvarotäckning per liga.
* Utred Sofascores Allsvenskan-stopp (punkt 1 ovan) — den är oberoende av
  allt annat och kan lösas när som helst.
* Rör inte trösklar eller signalversion utan förregistrering.

## Viktiga filer

* `backend/app/flashscore.py`, `backend/app/flashscore_data.py`
* `backend/app/live_radar.py`, `backend/app/live_signal_ledger.py`
* `backend/scripts/migrera_flashscore.py`, `backend/scripts/kalltest_ip.py`
* `docs/granskning-codex-38a45ff-2026-08-01.md`
* `docs/live-radar-2026-07-25.md`, `docs/db-atgarder.md`
