# AI-överlämning — server-MacBooken

> **Starta här.** Det här är den gemensamma drifthandboken för de tre
> projekt som körs på MacBooken: **Spelkompisen**, **Chartervakt** och
> **Bonusvakt/SAS**. Dokumentet beskriver servermiljön, hur projekten är
> installerade, hur de fungerar, var deras data och loggar ligger och hur en AI
> säkert tar över arbetet.
>
> Senast verifierad: **2026-08-11**. Maskin: `saman@192.168.50.100`.
> Versionsstyrt original:
> `/Users/saman/spelkompisen/docs/AI-OVERLAMNING-SERVER.md`. En identisk
> startkopia finns som `/Users/saman/AI-OVERLAMNING.md`.

## 1. Viktigast först

Alla tre apparna är i produktion på denna MacBook och nås på hemnätet:

| Projekt | Adress | Kod | Databas | Tjänst |
|---|---|---|---|---|
| Spelkompisen | `http://192.168.50.100:5175` | `/Users/saman/spelkompisen` | `backend/data/stryktips.db` | flera `com.saman.spelkompisen.*` |
| Chartervakt | `http://192.168.50.100:3100` | `/Users/saman/charter` | `chartervakt.db` | `com.saman.chartervakt` |
| Bonusvakt/SAS | `http://192.168.50.100:3000` | `/Users/saman/sas` | `sas-monitor.db` | `com.saman.bonusvakt` |

Snabb kontroll:

```bash
launchctl list | grep com.saman
curl -fsS http://127.0.0.1:8002/api/health
curl -fsS http://127.0.0.1:5175/ >/dev/null
curl -fsS http://127.0.0.1:3100/ >/dev/null
curl -fsS http://127.0.0.1:3000/v1/health
```

Viktiga skyddsregler:

1. **Kör aldrig samma datainsamlare samtidigt på den gamla och den nya
   datorn.** Det får bara finnas en skrivande produktionsinstans per projekt.
2. **Kopiera aldrig en aktiv SQLite-fil med vanlig filkopiering.** Använd
   SQLite-kommandot `.backup`, eftersom databaserna kan ha aktiva WAL-filer.
3. **Döda aldrig processer med `pkill -f`.** Projekten har snarlika Python-
   och Node-processer. Starta om exakt den LaunchAgent som avses.
4. **Skriv aldrig ut eller checka in hemligheter.** Miljöfiler får inspekteras
   endast med maskerade värden. Bonusvakts ntfy-ämne är en hemlighet.
5. **Exponera inte port 3000, 3100, 5175 eller 8002 direkt mot internet.**
   Använd ett privat nät, helst Tailscale, när fjärråtkomst införs.
6. **Rör aldrig `/Users/saman/svs` eller `/Users/saman/vm`.** De ligger
   utanför dessa tre projekt och är uttryckligen skyddade.
7. Lägg aldrig spel automatiskt. Spelkompisen analyserar och föreslår;
   användaren fattar och utför alltid beslutet.

## 2. Servern och installationen

### Maskin och konto

- MacBook Pro 2018, Intel x86_64, 2,2 GHz i7, 16 GB RAM, 256 GB disk.
- macOS 15.7.9 vid senaste verifieringen.
- Driftskonto: `saman`, UID 501.
- LAN-adress: `192.168.50.100`, för närvarande utdelad via DHCP.
- Chrome finns i
  `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.
- Command Line Tools är installerade.
- Python och Node installerades användarlokalt under
  `/Users/saman/.local/spelkompisen-runtime` för att undvika beroende av
  Homebrew och administratörsrättigheter.
- Spelkompisens Pythonpaket ligger separat i
  `/Users/saman/spelkompisen/backend/.venv`.

### Hur projekten flyttades hit

Koden och respektive databas flyttades från huvuddatorn. De gamla skrivande
processerna stoppades innan de slutliga databasbackuperna togs. Databaserna
kopierades med SQLite-onlinebackup, verifierades med `integrity_check` på båda
datorerna och aktiverades därefter här. Beroenden installerades lokalt på den
nya datorn; `node_modules` och Pythonmiljöer ska alltså betraktas som
maskinspecifika och kan återskapas.

Vid flytten klarade:

- Spelkompisen: 647 backendtester, 5 frontendtester och produktionsbygge.
- Chartervakt: 176 tester samt riktiga läsande prov mot Ving och TUI.
- Bonusvakt: 102 tester samt ett riktigt läsande SAS-prov med HTTP 200.

De ursprungliga projektmapparna och databaserna finns kvar på huvuddatorn som
rollback, men de är inte aktuellt produktionsfacit efter flytten.

### Autostart, inloggning och vila

Allt körs som LaunchAgents i:

```text
/Users/saman/Library/LaunchAgents/
```

Det innebär att `saman` måste logga in efter en full omstart innan tjänsterna
startar. Automatisk inloggning är avstängd. `com.saman.spelkompisen.awake`
kör `caffeinate -s`, vilket hindrar vanlig systemvila på nätström. Ett stängt
lock kan fortfarande försätta en laptop i vila: håll locket öppet eller använd
ett korrekt clamshell-upplägg.

Serverns menyradsapp visar en lokal tjänstestack med `✓` när alla tre
apparna, insamlarna och sömnskyddet är friska. Källan finns i:

```text
/Users/saman/spelkompisen/tools/spelkompisen_menubar.py
```

Menyraden är ett hjälpmedel, inte driftfacit. Kontrollera loggar och API om den
varnar.

## 3. Gemensam drift med launchd

Lista alla projekttjänster:

```bash
launchctl list | grep com.saman
```

Visa full status för en tjänst:

```bash
launchctl print gui/501/com.saman.spelkompisen.backend
```

Starta om en enda tjänst, säkert och målinriktat:

```bash
launchctl kickstart -k gui/501/com.saman.spelkompisen.backend
launchctl kickstart -k gui/501/com.saman.spelkompisen.frontend
launchctl kickstart -k gui/501/com.saman.chartervakt
launchctl kickstart -k gui/501/com.saman.bonusvakt
```

### Start och stopp med `tjanster.sh`

Spelkompisens `start.sh`/`stop.sh` duger inte på den här datorn. De frigör bara
portarna, och varje långlivad tjänst har `KeepAlive = true`, så launchd startar
om processen inom sekunder. Använd driftverktyget i stället; det täcker alla
registrerade tjänster för de tre apparna och serverdriften:

```bash
/Users/saman/spelkompisen/tools/tjanster.sh status
/Users/saman/spelkompisen/tools/tjanster.sh omstart backend
/Users/saman/spelkompisen/tools/tjanster.sh stopp charter
/Users/saman/spelkompisen/tools/tjanster.sh start all
```

Tjänstnamn: `backend`, `frontend`, `snapshot`, `pool`, `charter`, `bonus`,
`awake`, `kalltest`, `menubar`. Grupperna är `all`, `spelkompisen`,
`chartervakt`, `bonusvakt` och `server`. I menyerna visas de som:

- **Spelkompisen:** API, Webb, Oddset-insamling, Pool & live.
- **Chartervakt:** Chartervakt.
- **Bonusvakt:** Bonusvakt.
- **Server & övervakning:** Sömnskydd, Källprov (IP och datakällor),
  Serverkontroll.

Ett vanligt `stopp` gör `bootout` — tjänsten kommer tillbaka vid nästa
inloggning. `stopp <tjänst> --permanent` lägger till `launchctl disable`, så
stoppet överlever omstart; enda vägen tillbaka är `start`, som häver disablen.
Verktyget kräver bekräftelse innan det stoppar något som samlar data, och
vägrar köra utan `--ja` när stdin inte är en terminal. Ett stoppat jobb visas
som `stoppad`, ett permanent avstängt som `avstängd (överlever omstart)`.

All logik ligger i `tools/spelkompisen_tjanster.py`. Menyraden går genom samma
modul och har Starta / Stoppa / Starta om / Stoppa permanent per tjänst under
**Tjänster**, plus *Starta allt som ligger nere*. Projektrubrikerna är
synliga och orden för kör/väntar respektive stopp/fel är gröna och röda.
Huvudöversikten använder mörkare, adaptiva statusfärger eftersom dess
bakgrund är ljusare än undermenyn. Varje tjänst har en macOS-hjälptext som
visas när muspekaren hålls över den. `Serverkontroll` visas både i översikten
och under **Tjänster**.
Skriv aldrig en parallell launchd-implementation — lägestexterna och
tjänstlistan ska ha en enda källa.

De tre generella servertjänsterna betyder:

- **Sömnskydd:** håller MacBooken vaken på nätström så att alla insamlare kan
  fortsätta.
- **Källprov:** provar var sjätte timme att serverns IP når externa
  datakällor och sparar facit; det är inte den ordinarie oddsinsamlingen.
- **Serverkontroll:** den lokala menyradsappen för status och start/stopp.
  Stängs den fortsätter övriga insamlare att arbeta.

Schemalagda jobb som `snapshot`, `pool` och `kalltest` har normalt ingen PID
mellan körningarna. Ett `-` i PID-kolumnen och exitstatus 0 är friskt, inte ett
stoppat jobb. `backend`, `frontend`, `awake`, `menubar`, `chartervakt` och
`bonusvakt` ska däremot normalt ha levande processer.

Efter en omstart av hela MacBooken:

1. Logga in som `saman` och anslut nätström.
2. Vänta ungefär en minut.
3. Kontrollera `launchctl list | grep com.saman`.
4. Öppna de tre lokala adresserna eller kör snabbkontrollen ovan.
5. Kontrollera att `com.saman.spelkompisen.awake` har PID.
6. Starta inte motsvarande gamla processer på huvuddatorn.

## 4. Projekt 1 — Spelkompisen

### Syfte

Spelkompisen är ett lokalt analys- och beslutsstöd för svensk fotbollstipping
och odds. Det samlar marknadspriser, streck, poolinformation, resultat,
lagstyrka och matchstatistik; bygger systemförslag; följer live-matcher och
journalför signaler; samt mäter modellens förslag mot stängningsmarknaden och
utfall. Det lägger aldrig spel.

Huvuddelar:

- **Pool:** Stryktipset, Europatipset och Topptipset; historik,
  systemkonfigurationer, simulering, utdelning och automatisk rättning.
- **Oddset:** matcher, odds från flera källor, värdesignaler, modell mot sharp
  och SvS, rörelser och modelltransparens.
- **Live:** providerseparerad statistik från bland annat FotMob, Flashscore
  och Sofascore; signaler baserade på skapade chanser snarare än bara
  ställningen; efterföljande utfall sparas för utvärdering.
- **Modell/data:** historiska matcher, xG, Elo/lagstyrka, prediction ledger,
  close-facit, versionsmärkning och backtester.

### Läsordning för en AI

Innan kod ändras, läs i denna ordning:

1. `/Users/saman/spelkompisen/AGENTS.md`
2. `/Users/saman/spelkompisen/CLAUDE.md`
3. `/Users/saman/spelkompisen/docs/plan.md` — statussammanfattningen överst
   är projektets aktuella sanning.
4. `/Users/saman/spelkompisen/docs/macbook-server-2026-08-11.md`
5. Den aktuella överlämning som `AGENTS.md` pekar ut.
6. `/Users/saman/spelkompisen/docs/granskning-2026-07-13.md`
7. `/Users/saman/spelkompisen/docs/db-atgarder.md`

`CLAUDE.md` innehåller den detaljerade arkitekturen, källornas egenheter,
domänformler, modellregler och UI-konventioner. Duplicera inte den texten till
nya instruktioner; den ska vara gemensamt facit för AI-klienter.

### Teknik och struktur

- Backend: Python/FastAPI/Uvicorn i `backend/`.
- Frontend: React/Vite i `frontend/`; produktion serverar den byggda `dist/`.
- Databas: SQLite i `backend/data/stryktips.db`, med WAL.
- Backend lyssnar bara på `127.0.0.1:8002`.
- Frontend lyssnar på `0.0.0.0:5175` och proxar API till backend.
- Insamlingsskript och LaunchAgent-mallar: `backend/scripts/`.
- Driftsmonitor: `tools/`.

Viktiga källfamiljer inkluderar Svenskaspel, Pinnacle/sharp, Kambi,
Sofascore, FotMob, Flashscore och Altenar. Källor har olika täckning och får
inte blandas som om de vore samma mätserie. Framför allt ska live- och xG-data
behålla providerproveniens.

### Tjänster och schema

| Label | Uppgift | Schema/beteende | Logg |
|---|---|---|---|
| `com.saman.spelkompisen.backend` | API på 8002 | kontinuerlig | `backend/data/backend-server.{out,err}.log` |
| `com.saman.spelkompisen.frontend` | Vite preview på 5175 | kontinuerlig | `backend/data/frontend-server.{out,err}.log` |
| `com.saman.spelkompisen.snapshot` | Oddset och smart snapshot | :00 och :30 | `backend/data/launchd.{out,err}.log` |
| `com.saman.spelkompisen.pool` | pool, settlement och liveradar | var 5:e minut, :02-offset | `backend/data/pool-launchd.{out,err}.log` |
| `com.saman.spelkompisen.kalltest` | fristående IP-/källprov | var 6:e timme | `backend/data/kalltest-macbook.{out,err}.log` och JSONL |
| `com.saman.spelkompisen.awake` | `caffeinate -s` | kontinuerlig | `backend/data/awake.{out,err}.log` |
| `com.saman.spelkompisen.menubar` | lokal serverkontroll | kontinuerlig Aqua-app på servern | `backend/data/menubar.{out,err}.log` |

Installerade plist-filer finns i `~/Library/LaunchAgents`; versionsstyrda
mallar finns i `backend/scripts`. Serverns menyrad ska använda mallen
`com.saman.spelkompisen.server-menubar.plist`, inte fjärrmallen för
huvuddatorn.

På huvuddatorn finns ingen ständig monitor. Genvägen
`~/Desktop/Serverkontroll.app` startar fjärrversionen vid behov, skiljd från
serverversionen med en utåtriktad pil i tjänstestack-ikonen. Den hindrar
dubbelstart och avslutas automatiskt efter 15 minuter utan menyaktivitet.
Fjärr-plisten `com.saman.spelkompisen.menubar.plist` är endast en valfri
mall med `RunAtLoad=false` och `KeepAlive=false`; den ska inte installeras på
huvuddatorn.

Apppaketet ligger i `tools/Serverkontroll.app` och installeras/uppdateras med
`tools/installera_serverkontroll_app.sh`. Den 2026-08-11 flyttades även de
gamla lokala `snapshot`-, `pool`- och `menubar`-plisterna från
`~/Library/LaunchAgents` till `~/Library/LaunchAgents.disabled`. Huvuddatorn
ska alltså varken samla Spelkompisen-data eller köra Chartervakt/Bonusvakt;
den är bara en klient mot MacBook-servern.

### Utveckling och verifiering

Backendtester:

```bash
cd /Users/saman/spelkompisen/backend
.venv/bin/python -B -m unittest discover -s tests -v
```

Frontendtester och bygge:

```bash
cd /Users/saman/spelkompisen/frontend
/Users/saman/.local/spelkompisen-runtime/bin/npm test
/Users/saman/.local/spelkompisen-runtime/bin/npm run build
```

Efter backendändring i serverdrift:

```bash
launchctl kickstart -k gui/501/com.saman.spelkompisen.backend
curl -fsS http://127.0.0.1:8002/api/health
```

Efter frontendändring: kör tester och `npm run build`, starta sedan om
`com.saman.spelkompisen.frontend`. Frontendtjänsten bygger inte automatiskt;
den serverar befintlig `dist/` via Vite preview.

Om beroenden måste återskapas:

```bash
cd /Users/saman/spelkompisen/frontend
/Users/saman/.local/spelkompisen-runtime/bin/npm ci

cd /Users/saman/spelkompisen/backend
/Users/saman/.local/spelkompisen-runtime/bin/python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Kontrollera först vilken Python som tidigare skapade venv och läs projektets
instruktioner innan miljön ersätts. Radera inte en fungerande venv i onödan.

### Databas- och modellregler

- Ingen ad hoc-ändring av produktionsdatabasen.
- En databasändring ska göras med ett repeterbart skript, föregås av backup
  och dokumenteras i `docs/db-atgarder.md`.
- Algoritm- eller databehandlingsändringar ska bumpa relevant
  `DATA_VERSION`/`MODEL_PARAMS` enligt projektinstruktionen.
- En signal blir inte ”grön” bara för att en bred tier ser bra ut. Beslut tas
  per signalgrupp med förregistrerade kriterier och osäkerhet.
- Historisk modellutvärdering ska undvika framtidsläckage och mätas mot
  korrekt stängningslinje/-pris.
- Providerseparerade råserier får inte tyst blandas.
- Bevara auditspår; automatiska identitetsbeslut ska vara förklarliga.

### Aktuellt driftläge och kända punkter

- Produktionsskiftet skedde 2026-08-11. Datainsamling och skrivjobb på den
  gamla datorn ska vara avstängda.
- Topptipsets UI uppdaterar numera en öppen kupongs livestatus var 60:e sekund
  efter att ett engångsfel tidigare kunde fastna tills omladdning.
- Settlement väntar avsiktligt till ungefär senaste avspark + 130 minuter;
  ”väntar” medan sena matcher pågår är inte i sig ett fel.
- Produktionsarbetskatalogen hade vid flytten lokala, ej committade ändringar
  och `backend/data/` är produktionsdata. Kör aldrig `git reset --hard`,
  `git checkout -- .`, `git clean` eller `git add .` utan noggrann kontroll.
- Lägg aldrig hela `backend/data/` i Git.

## 5. Projekt 2 — Chartervakt

### Syfte

Chartervakt söker och bevakar charterpaket, normaliserar olika arrangörers
format, filtrerar på resa/hotell/pris och larmar om nya eller billigare
alternativ. En enda Nodeprocess serverar webbgränssnittet och kör
schedulern.

Aktivt i produktion:

- Ving via SSR-sida + GraphQL.
- TUI via GraphQL.
- Apollo är avstängt i serverkonfigurationen. Det kräver ett synligt
  Chrome-fönster för Cloudflare och ska inte slås på utan att först läsa
  begränsningarna.
- Åtta befintliga bevakningar fanns vid flytten.
- Push var okonfigurerat vid flytten; webb och historik fungerar ändå.

### Läsordning för en AI

1. `/Users/saman/charter/README.md`
2. `/Users/saman/charter/API-NOTES.md`
3. `/Users/saman/charter/DRIFT-MACBOOK-2026-08-11.md`
4. `package.json` och därefter `src/server.mjs`, `src/poller.mjs`,
   `src/db.mjs` samt relevant leverantörsadapter.

README-filen innehåller viktiga, verifierade domänregler: skillnaden mellan
plan och filter, betygsskalor, provtagning av breda datumperioder,
förstagångskörningar, klockslag kontra intervall och varför ett tomt
källsvar inte alltid är bevis på att ett erbjudande försvunnit.

### Teknik, data och drift

- Kod: `/Users/saman/charter`
- Node 22, inga ramverk.
- SQLite via Node `node:sqlite`.
- Databas: `/Users/saman/charter/chartervakt.db` med WAL.
- Webb: port 3100 på alla lokala gränssnitt.
- Konfiguration: `charter.env`; visa aldrig hemliga värden.
- Tjänst: `com.saman.chartervakt`.
- Plistmall: `/Users/saman/charter/com.saman.chartervakt.plist`.
- Loggar:
  - `/Users/saman/charter/server-launchd.out.log`
  - `/Users/saman/charter/server-launchd.err.log`
- Vid varje serverstart skapas automatiskt en DB-backup i
  `/Users/saman/charter/backups`; de tio senaste behålls.

Viktiga koddelar:

- `src/server.mjs`: webb, API och scheduler.
- `src/poller.mjs`: en bevaknings hela insamlingskedja.
- `src/db.mjs`: schema, historik och förändringsdetektering.
- `src/model.mjs` och `src/filter.mjs`: gemensam paketmodell och filter.
- `src/ving.mjs`, `src/tui.mjs`, `src/apollo.mjs`: källadaptrar.
- `src/browser.mjs`: Chrome för källor som kräver webbläsare.
- `src/notify.mjs`: push.

### Test, uppdatering och kontroll

```bash
cd /Users/saman/charter
/Users/saman/.local/spelkompisen-runtime/bin/npm test
launchctl kickstart -k gui/501/com.saman.chartervakt
curl -fsS http://127.0.0.1:3100/ >/dev/null
tail -n 100 server-launchd.err.log
```

Installera om beroenden endast vid behov:

```bash
cd /Users/saman/charter
/Users/saman/.local/spelkompisen-runtime/bin/npm ci
```

Gör inte breda skarpa sökprov mot alla datum/arrangörer bara för att testa
en kodändring. Använd tester och ett litet, läsande prov. Källorna är
odokumenterade boknings-API:er och ska behandlas varsamt.

## 6. Projekt 3 — Bonusvakt/SAS

### Syfte

Bonusvakt bevakar SAS EuroBonus-bonusplatser och larmar när nya platser
dyker upp. Den vanliga bevakningen använder SAS publika award feed och kräver
ingen inloggning. Projektet har också en separat partnersökning för SAS och
SkyTeam, som använder en manuellt inloggad SAS-session i synligt Chrome.

En enda Nodeprocess serverar webbgränssnittet, `/v1`-API:t och schedulern.
Det finns även en native iOS-klient i projektets `ios/`-mapp.

Vid flytten fanns fyra vanliga bevakningar och en partnerfavorit. Favoriten
var inte schemalagd. ntfy var aktivt och konfigurationen flyttades utan att
hemligheten dokumenterades här.

### Läsordning för en AI

1. `/Users/saman/sas/HANDOVER.md`
2. `/Users/saman/sas/README.md`
3. `/Users/saman/sas/REVIEW-2026-08-02.md`
4. `/Users/saman/sas/API-NOTES.md`
5. `/Users/saman/sas/PLAN.md`
6. `/Users/saman/sas/PUBLIK-VERSION.md` om en fleranvändartjänst diskuteras.
7. `/Users/saman/sas/DRIFT-MACBOOK-2026-08-11.md`

HANDOVER och REVIEW innehåller lastbärande invariants kring
förändringsdetektering, kabinplatser, partnerlås, rate limit, inloggningsstatus
och skillnaden mellan notishistorik och aktuell tillgänglighet. Ändra inte
dessa delar genom ”förenkling” utan att förstå regressionerna de förhindrar.

### Två datavägar

1. **Publik award feed:** inloggningsfri, returnerar kalenderdata för
   destinationer från en origin. Detta är den automatiska, schemalagda
   bevakningen. Kalenderdata är en signal, inte ett bokningslöfte; SAS
   bokningsflöde är slutligt facit.
2. **Partner-API:** kräver en inloggad EuroBonus-session och gör ett
   rate-limitat anrop per rutt/datum. Manuell som standard. Schemaläggning är
   uttryckligt opt-in och kan innebära risk för kontot enligt SAS villkor.

Vanlig bevakning fungerar fullt ut utan SAS-lösenord. Projektet sparar aldrig
SAS-lösenordet. Den gamla Chromeprofilen kopierades medvetet inte, eftersom
cookies är krypterade mot den gamla datorns nyckelring. För partnersökning:

1. Öppna Bonusvakt på MacBooken.
2. Gå till partnersidan och välj att logga in till SAS.
3. Använd ”Glömt lösenord” hos SAS om kontouppgifterna inte är kända.
4. Logga in manuellt i Chrome och låt det fönstret vara tillgängligt.

Frånvaro av denna inloggning påverkar inte de fyra automatiska publika
bevakningarna.

### Teknik, data och drift

- Kod: `/Users/saman/sas`.
- Projektet hade ingen Git-repository vid flytten; behandla varje ändring extra
  varsamt och skapa backup/diff innan redigering.
- Node 22, inga ramverk, SQLite via `node:sqlite`, Playwright Core och riktig
  Chrome.
- Databas: `/Users/saman/sas/sas-monitor.db` med WAL.
- Webb/API: port 3000 på alla lokala gränssnitt.
- Hälsa: `GET /v1/health`.
- Konfiguration: `/Users/saman/sas/bonusvakt.env`; läs inte ut eller logga
  hemliga värden.
- Tjänst: `com.saman.bonusvakt` som interaktiv Aqua-LaunchAgent, eftersom
  partnerflödet kan behöva öppna ett synligt Chrome-fönster.
- Plistmall: `/Users/saman/sas/com.saman.bonusvakt.plist`.
- Loggar:
  - `/Users/saman/sas/server-launchd.out.log`
  - `/Users/saman/sas/server-launchd.err.log`

LaunchAgenten överstyr tills vidare `PUBLIC_URL` till
`http://192.168.50.100:3000`. MacBooken saknade Tailscale vid senaste kontroll,
så appen och pushlänkarna fungerar på hemnätet men inte utanför det.

Viktiga koddelar:

- `src/server.mjs`: webb, `/v1`-API, scheduler och lås för partnersökning.
- `src/sas-client.mjs`: publik feed, kabinlogik och reseparning.
- `src/poller.mjs`: bevakning till ruttplan och förändringsdetektering.
- `src/db.mjs`: schema, transaktioner, state och diff.
- `src/partner.mjs`: autentiserad session via Chrome/CDP.
- `src/partner-search.mjs`: planering, pacing och rate limit.
- `src/notify.mjs`: ntfy/Telegram; importordningen runt miljön är viktig.
- `ios/`: SwiftUI-klient mot `/v1`.

### Test, uppdatering och kontroll

```bash
cd /Users/saman/sas
/Users/saman/.local/spelkompisen-runtime/bin/npm test
/Users/saman/.local/spelkompisen-runtime/bin/npm run check-fetch
launchctl kickstart -k gui/501/com.saman.bonusvakt
curl -fsS http://127.0.0.1:3000/v1/health
tail -n 100 server-launchd.err.log
```

`npm run check-fetch` gör ett riktigt läsande SAS-prov och ska användas
med omdöme. Kör inte breda eller upprepade partnerprov automatiskt.

Installera om beroenden endast vid behov:

```bash
cd /Users/saman/sas
/Users/saman/.local/spelkompisen-runtime/bin/npm ci
```

## 7. Databaser, backup och återställning

### Säker SQLite-backup

Stoppa normalt inte tjänsten för backup. Låt SQLite skapa en konsistent
onlinebackup:

```bash
sqlite3 /absolut/sokvag/app.db \
  ".timeout 30000" \
  ".backup /absolut/sokvag/backups/app-YYYYMMDD-HHMMSS.db"
```

Verifiera backupen:

```bash
sqlite3 /absolut/sokvag/backups/app-YYYYMMDD-HHMMSS.db \
  "PRAGMA integrity_check; PRAGMA foreign_key_check;"
```

Förväntat första svar är `ok` och inga foreign-key-rader. Om en databas
verkligen ska ersättas: stoppa exakt berörd LaunchAgent, ta backup av både
källa och mål, verifiera, ersätt, starta tjänsten och verifiera igen.

Databaser:

```text
/Users/saman/spelkompisen/backend/data/stryktips.db
/Users/saman/charter/chartervakt.db
/Users/saman/sas/sas-monitor.db
```

### Rollback till huvuddatorn

Rollback är möjlig, men den gamla databasen är inte längre aktuell efter att
MacBooken började skriva ny data.

1. Stoppa först berörd skrivande tjänst på MacBooken.
2. Ta en verifierad SQLite-onlinebackup av den senaste MacBook-databasen.
3. För över backupen till huvuddatorn och verifiera den där.
4. Aktivera den som databas på huvuddatorn.
5. Starta först därefter den gamla instansen.
6. Kontrollera att MacBook-instansen fortfarande är avstängd.

För Spelkompisen är `snapshot` och `pool` de kritiska skrivarna. För
Chartervakt respektive Bonusvakt är deras enda serverprocess både webb och
scheduler. Kör aldrig ett överlappande ”snabbtest” på den gamla datorn med
produktionsdatabasen.

## 8. Felsökningsordning

När en app ser trasig ut, gör detta i ordning:

1. **Avgör omfattningen:** svarar webbsidan, lokala API:t och porten?
2. **Kontrollera LaunchAgent:** `launchctl print gui/501/<label>`.
3. **Läs stderr och stdout:** börja med de senaste 100 raderna.
4. **Kontrollera datans färskhet:** en levande webbsida bevisar inte att
   schedulern lyckas.
5. **Kontrollera källan separat:** skilj ett externt källfel från ett fel i
   vår kod.
6. **Kör minsta relevanta testsvit.** Kör full svit innan distribution när
   ändringen rör gemensam data, DB, scheduler eller modell.
7. **Starta om bara rätt tjänst.** Bekräfta hälsa efteråt.
8. **Dokumentera rotorsak och fix** i projektets befintliga plan/överlämning.

Användbara kontroller:

```bash
/Users/saman/spelkompisen/tools/tjanster.sh status
lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(3000|3100|5175|8002)'
df -h /
pmset -g assertions
tail -n 100 /Users/saman/spelkompisen/backend/data/backend-server.err.log
tail -n 100 /Users/saman/spelkompisen/backend/data/pool-launchd.err.log
tail -n 100 /Users/saman/charter/server-launchd.err.log
tail -n 100 /Users/saman/sas/server-launchd.err.log
```

### Vanliga feltolkningar

- Schemalagt launchd-jobb utan PID är normalt mellan körningar.
- En poolkupong kan korrekt vänta på settlement tills sista matchen plus
  matchmarginal har passerat.
- Ett tomt externt källsvar är inte automatiskt bevis på noll utbud/data.
- Bonusvakts notiser är historik; aktuell platstillgänglighet är en separat
  vy och kan ha ändrats sedan notisen.
- Chartervakts breda datumspann kan vara gles provtagning, inte kontroll av
  varje avresedag. UI och README beskriver exakt vilka dagar som frågas.
- Ett grönt webb-HTTP-svar säger inget om den senaste externa insamlingen;
  kontrollera status, logg och färskhet.

## 9. Git och ändringsdisciplin

**Stående order sedan 2026-08-11: committa färdigt arbete utan att fråga om
lov.** Den ersätter den tidigare regeln "committa endast på begäran" och gäller
projekt som har Git. Det är bara *tillståndet att committa* som ändras — allt
annat står kvar: committa BARA filer du själv ändrat, kör aldrig `git add .`,
och lägg aldrig databas, loggar, produktionsdata eller hemligheter i en commit.
Andras ocommittade ändringar i arbetskatalogen ska bevaras, inte sopas in i din
egen commit.

### Spelkompisen

Detta är ett Git-projekt. Innan arbete:

```bash
cd /Users/saman/spelkompisen
git status --short
git log -1 --oneline
```

Arbetskatalogen kan innehålla Samans, Claudes eller Codex pågående
ändringar. Bevara dem — den stående ordern gäller ditt eget arbete, inte
någon annans. `backend/data/` är produktionsdata och hör aldrig hemma i en
commit. Commitmeddelanden ska vara på svenska med imperativ rubrik och korrekt
`Co-Authored-By` enligt `AGENTS.md`.

### Chartervakt

Detta är ett Git-projekt och den stående ordern gäller. Kontrollera alltid
`git status` och bevara driftdokument/plist/loggar som kan ligga utanför
versionsstyrningen. Lägg inte databas eller loggar i en commit; `.gitignore`
täcker databasen och `charter.env` men INTE `server-launchd.{out,err}.log`,
så lägg aldrig till dem oavsiktligt.

### Bonusvakt/SAS

Mappen saknade Git vid flytten, så **den stående ordern gäller inte här** —
det finns inget att committa till. Innan större arbete: ta en separat kopia
eller inför Git på ett medvetet sätt med korrekt `.gitignore` för databas, WAL,
miljöfil, Chromeprofil, loggar och beroenden. Initiera inte och committa inte
hela mappen slentrianmässigt; det finns hemligheter och runtime-data.

## 10. Säkerhet och externa tjänster

- Alla webbgränssnitt är avsedda för privat LAN/Tailscale. De saknar den
  autentisering som krävs för publik internetexponering.
- Tailscale var inte installerat vid senaste verifieringen. När det
  installeras: uppdatera Bonusvakts `PUBLIC_URL` till den nya datorns privata
  Tailscale-adress och kontrollera pushlänkar från mobilnät. Publicera inga
  portar i routern.
- Reservera `192.168.50.100` för MacBookens nätverkskort i routern. Annars kan
  DHCP byta adress och bryta mobilgenvägar, plist-konfiguration och menyrad.
- Miljöfiler och notifieringskanaler är hemligheter. Vid diagnostik, rapportera
  endast om en variabel finns och om kanalen är aktiv — aldrig dess värde.
- SAS partnersökning är kontobunden och rate-limitad. Automatisera inte
  aggressivt och kringgå inte avslag.
- Projekten använder gratis källor. Inför inte betalda API:er eller nycklar
  utan Samans uttryckliga beslut.

## 11. Kvarstående serverarbete

Prioriterad driftlista, inte ett tillstånd att göra allt automatiskt:

1. Reservera LAN-adressen `192.168.50.100` i routern.
2. Installera Tailscale om Saman vill nå apparna utanför hemmet; uppdatera
   därefter `PUBLIC_URL` och mobilgenvägar.
3. Bestäm om LaunchAgents ska ersättas med systemtjänster för drift före
   användarinloggning. Det kräver lokal administratörsbehörighet och noggrann
   testning av Aqua-beroendena för menyrad/Chrome.
4. Håll MacBooken på nätström med locket öppet eller korrekt clamshell.
5. Återställ SAS-inloggningen manuellt endast om partnersökning ska användas.
6. Inför backup utanför datorns interna disk. Lokala startbackuper skyddar
   inte mot diskfel eller stöld.

## 12. Definition av en säker AI-överlämning

En AI som tar över ska före första ändringen kunna svara på:

- Vilket av de tre projekten berörs, och vilken process äger dess scheduler?
- Vilken databas är produktionsfacit och finns en verifierad backup?
- Finns lokala, ocommittade ändringar som måste bevaras?
- Vilket projektinstruktionsdokument ska läsas först?
- Är felet i vår kod, i tjänsten eller hos en extern källa?
- Vilka tester och vilken hälsokontroll visar att ändringen är säker?
- Hur startas exakt rätt tjänst om utan att stoppa de andra?
- Kan åtgärden starta en andra skrivare, lägga ett spel, exponera en port,
  läcka en hemlighet eller göra aggressiva anrop mot en extern tjänst?

Om någon av dessa punkter är oklar ska AI:n fortsätta med läsande
diagnostik och dokumentation, inte gissa eller göra irreversibla ingrepp.

---

**Dokumentets kanoniska, versionsstyrda plats på servern:**
`/Users/saman/spelkompisen/docs/AI-OVERLAMNING-SERVER.md`

**Lättfunnen startkopia i hemkatalogen:**
`/Users/saman/AI-OVERLAMNING.md`

Projektens egna README-, plan- och överlämningsfiler är fortfarande det
detaljerade facit för kod och domänlogik. Den här filen binder ihop dem och är
startpunkten för serverdrift.
