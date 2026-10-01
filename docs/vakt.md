# Vakten — deterministisk driftvakt (vakt-v1, 2026-10-01)

**Varför:** Sofascore svarade 403 i varje källprov från 2026-09-25T10:43:18Z i sex
dygn utan att något syntes i appen. Testsviten var röd ett dygn 2026-09-02 utan
att någon såg det, och en kupongkrasch (`NameError` i backend) låg kvar 24–27/9.
Vakten ska upptäcka sådant före Saman och visa det på **Idag** — aldrig som
ntfy/push (Samans beslut 2026-09-02).

**Vad den inte gör:** ingen AI, inga anrop till datakällor (Pinnacle, Svenska Spel,
Sofascore …), inga skrivningar i databasen (den öppnas `mode=ro`), inga omstarter
och inga spel. Den LÄSER artefakter som redan finns och skriver ett läge.

## Körning

| Vad | Hur |
|---|---|
| Schema | launchd `com.saman.spelkompisen.vakt` (`backend/scripts/com.saman.spelkompisen.vakt.plist`), `StartInterval` 1800 s + `RunAtLoad` |
| Manuellt | `cd backend && .venv/bin/python -B cli.py vakt` (utskrift med per-kontroll-tider i terminal) |
| Testsviten nu | `cli.py vakt --tester-nu` (annars en gång per natt) |
| Prov utan sidoeffekter | `cli.py vakt --utan-tester --utan-fetch --status-dir /tmp/x` (+ `--data`, `--db`, `--repo` för andra sökvägar) |
| Tjänst | `tools/tjanster.sh status vakt` · `start vakt` · `stopp vakt` (grupp *Server & övervakning*) |

En körning åt gången (`flock` på `<status>/.vakt.lock`). En kontroll som kraschar
fäller aldrig de andra: den ger `vakt_check_failed` (warning) med undantagstypen,
och kontrollens senaste kända fynd och tillstånd bärs oförändrade (`carried`).

## Var läget skrivs och hur man läser det

- `backend/data/vakt/vakt.json` — senaste läget, skrivs atomiskt (tmp + `os.replace`):
  `version` (`vakt-v1`), `checked_at`, `counts`, `findings`, `checks` (per kontroll:
  `ok`, `ms`, detaljer eller `error`), `paths` och `state` (loggoffsets, senaste
  testkörning, experimentens senaste status). Katalogen kan styras med
  `SPELKOMPISEN_VAKT_DIR`.
- `backend/data/vakt/vakt-logg.jsonl` — EN rad per körning (tid, antal per nivå,
  `level:kind:key` per fynd, kraschade kontroller). Append-only.
- `backend/data/vakt-launchd.{out,err}.log` — launchd; utskriften är kort (fynd +
  kraschade kontroller).

Ett fynd: `{level: error|warning|info, area, kind, key, message, since, last_seen,
check, …detaljer}`. `since` = när felet först sågs; det bärs mellan körningar på
`kind` + `key`. Där kontrollen vet starttiden ur sina data (källprovets första
felkörning, testsvitens första röda natt) anges den direkt. `held: true` = fyndet
sågs inte i den här körningen men ligger kvar (se *hålltid*).

**I appen:** `/api/health` läser `vakt.json` via `pool_health._vakt_issues`:
fel/varningar blir `pools.issues` med `product: "server"` och fyndets `kind`;
info-fynd blir ALDRIG issues (frontendens `splitPoolIssues` räknar allt som inte är
`warning` som fel) utan ligger i `vakt: {checked_at, version, notes}` på toppnivån.
Idag visar `⚠️ Driften behöver tillsyn` (fel), en ihopfälld `Drift att se över: …`
(varningar) och `Vakten noterade senaste 7 dygnen: …` (info). Databasbackupens
varningar (också `product: "server"`) flyttade från "Poolunderlag" till samma
driftrubrik. Saknas `vakt.json` ⇒ `vakt_missing`; äldre än 90 min ⇒ `vakt_stale`
(senaste kända fynd visas ändå); oläslig ⇒ `vakt_unreadable`.
`cli.py kallhalsa` visar samma sak i poolhälsans utskrift.

## Kontrollerna och trösklarna

| Kontroll | Fynd (`kind`) | Nivå | Tröskel / regel |
|---|---|---|---|
| **A. källor** — `backend/data/kalltest-macbook-192.168.50.100.jsonl` | `kalla_nere` (key = källa) | error | källan fallerat (`outcome: source_error`) i ≥ 2 källprov i rad; `since` = första felkörningens `at`, meddelandet bär senaste `note`. Bara källor som finns i senaste körningen bedöms |
| | `natverk_nere` (key `kalltest`) | warning, error vid ≥ 2 i rad | körningar med `infrastructure_error`/DNS-fel. Sådana rader är ingen observation av källan: de varken bryter eller förlänger en källas felserie |
| | `kalltest_stale` | warning | senaste körning äldre än 2 × 6 h = 12 h, eller loggen saknas |
| **B. jobb** — `launchctl list` via `tools/spelkompisen_tjanster.py` (`Launchd.state`) för backend, frontend, snapshot, pool, backup, kalltest, vakt | `jobb_ej_laddat` | error (warning om avstängd med `--permanent`) | tjänsten är inte laddad |
| | `jobb_nere` | error | KeepAlive-tjänst (backend/frontend) utan PID |
| | `jobb_exit` | warning | schemalagt jobb med senaste exit ≠ 0. Källprovet avslutar med 1 när en kritisk källa fallerar — meddelandet hänvisar då till `kalla_nere` |
| **B. insamling** — append-only-tabeller, databasen `mode=ro` | `insamling_star_still` (key `pool`/`oddset`) | error | senaste `pool_market_capture.fetched_at` (bara när en öppen omgång finns) resp. Pinnacles icke-live-rad i `oddset_source_health_log` äldre än **90 min** |
| **C. backend** — `backend-server.out.log` (accesslogg) | `backend_5xx` (key `access`) | warning | ≥ 5 svar 5xx sedan förra körningen, eller ≥ 3 på samma endpoint (sökväg utan querysträng); visar de värsta |
| — `backend-server.err.log` | `backend_traceback` (key `err`) | warning | ≥ 1 nytt slutligt undantag som inte är nät; visar sista undantagsraden |
| | `natverk_nere` (key `backend`) | warning | ≥ 1 nytt `ConnectError`/DNS-fel (`nodename nor servname` m.fl.) — nätet, inte en bugg. Timeouts räknas bara i sammanfattningen |
| **D. drift** — git/ps i driftkopian | `backend_kor_gammal_kod` | warning | senaste commit i `backend/app` > backendprocessens start + 5 min |
| | `appen_ej_byggd` | warning | senaste commit i `frontend/src` > mtime på `frontend/dist/index.html` + 5 min, eller dist saknas |
| | `main_ej_utcheckad` | warning | `origin/main` har commits som HEAD saknar (efter `git fetch --quiet origin`, 30 s timeout; hämtfel noteras i `checks.drift.fetch` men larmar inte) |
| | `opushade_commits` | warning | HEAD har commits som `origin/main` saknar |
| | `ocommittat_i_driftkopian` | warning | ändrade SPÅRADE filer (`git status --porcelain --untracked-files=no`) |
| **E. tester** — `tools/kontroll.sh` | `tester_roda` (key `kontroll`) | error | senaste nattliga körning röd eller timeout; `since` = första röda natten i serien |
| **F. server** | `disk_lag` | warning < 10 GB, error < 3 GB | ledigt på volymen med `backend/data`; databasens storlek står i `checks.server.db_bytes` |
| **G. experiment** — `pool_tests.catalog()` (samma som `/api/pool/tests`) | `test_status_andrad` (key `id:före->efter`) | info | ett tests rubrikstatus bytte sedan förra körningen |
| | `avlasningspunkt_nadd` (key = test) | info | underlaget PASSERADE kravet (`n/krav` gick från under till på/över) medan testet fortfarande `samlar` |

**Hålltider:** info-fynd ligger kvar 7 dygn efter senaste observation;
`backend_5xx`, `backend_traceback` och backendens `natverk_nere` ligger kvar 24 h
(annars syns ett skov bara i 30 min). Övriga fynd försvinner när orsaken är borta.

## Detaljer och medvetna avvägningar

- **Insamlingens liv mäts INTE på `snapshots`/`sharp_snapshots`.** De är
  förändringsserier (observationstidsregeln 1): under normal drift 17/9–1/10 hade
  de luckor på 150 resp. 187 min, medan `pool_market_capture` och Pinnacles rader i
  `oddset_source_health_log` aldrig hade mer än 30 min. 90 min = tre missade
  basvarv. `oddset_health` larmar redan efter 45 min på meta-stämplarna; vaktens
  kontroll är ett oberoende bakstopp på själva artefakterna.
- **Senaste tid jämförs som tid**: de 200 senast inskrivna raderna (rowid) tolkas
  och den största tiden väljs — databasen blandar `Z`, `+00:00` och mikrosekunder,
  så SQL:s `MAX` över text räcker inte.
- **Backendloggarna läses inkrementellt.** Byte-offset och inode sparas i
  `state.backend_log`. Krympt fil eller ny inode ⇒ läs om från 0. Första körningen
  läser högst de sista 5 MB (halv första rad kapas) och dess fynd hålls inte kvar:
  de beskriver gamla skov, inte vad som hänt sedan vakten började. Bara hela rader
  konsumeras. En undantagskedja (`The above exception was the direct cause…`)
  räknas som EN händelse, och ett undantag som skrivs just när vakten läser
  (ramar men ingen undantagsrad ännu) läses om nästa gång i stället för att tappas.
- **Backendprocessens starttid** = nu − `ps -o etime=` (förfluten tid) i stället för
  `lstart`: ingen lokal tidszon eller locale att tolka, och testbar med injicerad
  klocka. 5 min marginal eftersom `etime`/`%ct` har sekundupplösning (backend
  startades 2026-09-29T23:47:33Z, commit 23:47:34Z — samma omstart) och
  "redigera → starta om → committa" inte ska larma. `backend/cli.py` ingår inte:
  uvicorn läser den inte, launchd-jobben startar den på nytt varje varv.
- **git i driftkopian** körs med `--no-optional-locks` så att vakten inte skriver
  index eller lås. `git fetch` skriver däremot `origin/main` och `FETCH_HEAD` — det
  är hela poängen med D3; `--utan-fetch` stänger av det.
- **Testsviten** körs en gång per lokalt dygn (Europe/Stockholm): första körningen
  efter 03:00 när senaste start ligger före dagens 03:00. Den körs ALDRIG i
  driftkopian: `git worktree add --detach <tmp>/wt HEAD`, symlänkar till
  driftkopians `backend/.venv` och `frontend/node_modules`, `tools/kontroll.sh`
  (som sätter `SPELKOMPISEN_DB` till en temporär fil), timeout 15 min med hela
  processgruppen dödad, och alltid `git worktree remove --force` + `prune` efteråt.
  Resultatet (`ok`, `exit_code`, `head`, sammanfattningsraderna, första felraderna,
  tid) sparas i `state.tests` och bärs mellan körningar.
- **Experimentkatalogen läses skrivskyddat**: `Storage(path, read_only=True)`
  (`mode=ro`, inget schema, ingen mkdir). `gater._ph4_oot` → `main.turnover_prognos()`
  öppnar en egen `Storage()`; under katalogläsningen byts `main.Storage` mot en
  skrivskyddad fabrik till samma databas och återställs direkt efteråt.
  `avlasningspunkt_nadd` noterar bara ÖVERGÅNGEN: poolopt står på 62/40 efter sin
  avläsning vid 40 och ska inte läsas av igen förrän vid 120 (Samans beslut 5aA),
  så ett permanent "nått" vore en inbjudan att titta. Första körningen är baslinje.

## Driftsättning (efter merge till main)

1. `cd ~/spelkompisen/frontend && npm run build` (Idag-vyn har ny driftsektion).
2. `cp ~/spelkompisen/backend/scripts/com.saman.spelkompisen.vakt.plist ~/Library/LaunchAgents/`
   och `tools/tjanster.sh start vakt` (= `launchctl bootstrap gui/501 …`; `RunAtLoad`
   kör första kontrollen direkt — inklusive testsviten om klockan är efter 03:00).
3. `tools/tjanster.sh omstart backend` (nya `/api/health`-fält).
4. Kontroll: `cat backend/data/vakt/vakt.json | head`, `tools/tjanster.sh status vakt`
   och Idag i appen.

Första kontrollen läser loggarnas sista 5 MB och kan därför visa gamla 5xx-/
undantagsskov i 30 min, märkta "vaktens första läsning".
