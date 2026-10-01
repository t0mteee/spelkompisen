# Facitsidan för spel-ai-kompisen (fas B)

**Status 2026-10-01:** byggd och testad i worktree `claude/spelai-facit`, inte
driftsatt. Kontraktet ovanför är `docs/spel-ai-kompisen-design.md` (v3, godkänd
2026-10-01); det här dokumentet beskriver exakt hur facitsidan uppfyller det och
är **kontraktet för agentsidan** (`agent.forslag`). Ändras något här ändras
designen först.

Facitsidan är betrodd kod i Spelkompisen (`backend/app/spelai/`). Den fryser,
validerar och rättar agentens poolförslag mot Spelkompisens egen standard.
Agenten kan läsa den men aldrig ändra den, och den kan aldrig skriva i
facitsidans tabeller.

## 1. Flödet

```
pool-tick (var 5:e min, launchd com.saman.spelkompisen.pool)
  └─ _pool_pit_freeze: PH3:s färska draw + sharp (pool-sharp-freshness-v1)
       + movement + jackpot
       ├─ spelai.indata.capture_due → spelai_input   (billigt: inga byggen,
       │                                              egen try, FÖRE PH3)
       └─ pool_system_ledger.freeze_due              (PH3, oförändrad)

spelai-tick (varje minut, launchd com.saman.spelai.schema)
  1. inkorg.las_in            ~/spel-ai-data/utkorg/*.json → spelai_inbox
  2. frysning.process_inputs  paket → standard (alla nivåer) → agent (EN körning)
  3. frysning.mark_missed     fönster utan paket → missat / pausad
  4. ratta.settle             pool_draw_settlement → spelai_pool_result
  5. notis.skicka             ntfy (SPELAI_NTFY_TOPIC), dedup, tysta timmar
```

Varje steg i `spelai-tick` isoleras: ett fel bokförs som `tick_fel` i
`spelai_event` och stoppar inte resten. Ticket tar ett fil-lås
(`backend/data/spelai-tick.lock`) och kör aldrig parallellt med sig självt.

## 2. Nivåer och format (`app/spelai/nivaer.py`)

| Produkt | Nivåer (kr = högsta radantal, radpris 1 kr) |
|---|---|
| stryktipset, europatipset | 256, 512, 5 000, 20 000, 39 366 |
| topptipset, topptipsetstryk, topptipsetextra | 256 |

Produktlistorna läses ur `svenskaspel.GAME_GROUPS`.

* `rows` (alla nivåer utom 39 366): lista av strängar, ett tecken `1`/`X`/`2`
  per match i omgångens matchordning (`events_order` i paketet), 1 till
  nivån rader, inga dubbletter.
* `msystem` (bara och alltid 39 366): `tecken` = en sträng per match med
  tecknens mängd (`"1"`, `"1X"`, `"1X2"` …); exakt 3 matcher med 1 tecken, 1 med
  2 och 9 med 3 (= 2·3⁹ = 39 366 rader). Ordningen inom en match normaliseras.
  Rättningen expanderar till rader.
* `motivering_kort` (valfri) kapas vid 500 tecken.
* Hash = sha256 över de sorterade raderna (ordningsoberoende), 16 tecken.

Valideringsfel ger en mening som orsak, t.ex. `rad 12 (1X2…) är en dubblett`.

## 3. Indatapaketet (`spelai_input`, `app/spelai/indata.py`)

Databasen sparar inte omgångens Draw-payload, så paketet fryses i poolvarvet
bredvid PH3:s `freeze_due`, ur exakt samma underlag. Ett paket per
(produkt, omgång, horisont), aldrig fler.

| Horisont | Fönster för draw-observationen | Frist för frysningen |
|---|---|---|
| `6h` (förhandsversion) | [T−6h, T−5h30] — basvarvet går var 30:e min | 30 min efter observationen |
| `30m` (officiellt) | [T−35m, T−30m] — poolvarvet tickar var 5:e min inom 2 h | 5 min efter observationen |

T = `reg_close_time` tolkad som tid. Observationstiden är `draw.fetched_at`
(när poolvarvet hämtade omgången), aldrig när paketet råkade skrivas.

**Känd marginal (6h):** basvarven ligger på väggklockans 30-minutersslottar,
så exakt ett basvarv observerar normalt draw inne i det 30 minuter breda
6h-fönstret. Hamnar hämtningen några sekunder fel sida om fönstrets kant blir
6h-förslaget `missat`. 30m-fönstret har sex poolvarv på sig och är inte utsatt.
Bredda 6h-toleransen (t.ex. till 35 min) om missarna syns i facit.

Paketets JSON (`schema: "spelai-indata-v1"`), som agenten får som fil:

```json
{
  "schema": "spelai-indata-v1",
  "input_id": 17,
  "product": "stryktipset", "draw_number": 4973, "horizon": "30m",
  "observed_at": "2026-10-03T13:27:41Z", "captured_at": "2026-10-03T13:27:41Z",
  "reg_close_time": "2026-10-03T13:59:00Z",
  "window": {"start": "2026-10-03T13:24:00Z", "end": "2026-10-03T13:29:00Z"},
  "nivaer": [256, 512, 5000, 20000, 39366],
  "n_matches": 13, "events_order": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
  "draw": { "...": "dataclasses.asdict(Draw) — svenskaspel.Draw/Match/Outcome" },
  "sharp": {"1": {"odds": {"1": 1.9, "X": 3.6, "2": 4.1}, "total": {"line": 2.5, "O": 1.9, "U": 1.95}, "...": "..."}},
  "sharp_stale_events": [7],
  "movement": [[1, "1", {"first": 2.0, "last": 1.9, "steam_pp": 1.2}], "..."],
  "turnover": {"live": 21500000.0, "used": 26659136.0, "basis": "projected"},
  "jackpot": {"value": null, "source": "verified_endpoint"},
  "underlag_tider": {"svs": "…Z", "omsattning": "…Z", "sharp": "…Z"}
}
```

* `draw` går tur och retur: `indata.draw_from_payload(payload["draw"])` ger en
  identisk `Draw` (testat).
* `sharp` är redan filtrerad av pool-sharp-freshness-v1; nycklar är
  eventnummer som strängar (`indata.decode_sharp` ger int-nycklar).
* `movement` är listan `[event, tecken, värde]` (`indata.decode_movement` ger
  `{(event, tecken): värde}` som `analyze_draw` vill ha).
* `turnover.used` = `_valuation_turnover` (prognosen om den är högre än live),
  samma tal som PH3 värderar mot. `jackpot.value` är poolvarvets jackpot.
* `underlag_tider`: odds, streck och omsättning kommer ur SAMMA draw-läsning
  (`svs`); `sharp` är senaste Pinnacle-observationen (presence eller
  förändring) — observationstidsregeln. De sparas på varje förslagsrad.

Standarden återskapar analysen exakt som PH3: `analyze_draw(draw, sharp,
movement)`, `turnover = max(live, used)`, `jackpot = max(0, value or 0)`.

## 4. Agentkontraktet (`app/spelai/sandbox.py`, `agent.sb`)

Facitsidan anropar agenten EN gång per (omgång, horisont), för alla nivåer:

```
/usr/bin/nice -n 10 /usr/bin/sandbox-exec -D HOME=… -D AGENT_DATA=… -D DB_SHM=… \
    -f backend/app/spelai/agent.sb \
    <agent_python> -B -m agent.forslag --indata <fil.json> --nivaer 256,512,5000,20000,39366
```

* Arbetskatalog: `~/spel-ai-kompisen/backend` (`SPELAI_AGENT_DIR`).
  `PYTHONPATH` = arbetskatalogen och repots rot, så paketet `agent` får ligga
  i `backend/agent/` eller i `~/spel-ai-kompisen/agent/`.
* `<agent_python>` = `~/spel-ai-kompisen/backend/.venv/bin/python`
  (`SPELAI_AGENT_PYTHON`).
* Miljön är tom utom `PATH=/usr/bin:/bin`, `HOME`, `LANG`, `TMPDIR` (egen
  temporär katalog), `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH` och `SPELAI_DB`
  (sökvägen till `stryktips.db`, för läsning med `mode=ro`).
* `--nivaer` är produktens nivåer (Topptipset-familjen bara `256`).
* **Tidsgräns** 180 s, dock aldrig längre än till fristen (30m: observation +
  5 min). Under 10 s kvar ⇒ agenten körs inte och raden blir `missat`.
* **Svar på stdout** (allt annat ska till stderr):

```json
{"version": "<strategi-id>",
 "forslag": {
   "256":   {"format": "rows", "rows": ["1X21X21X21X21", "…"], "motivering_kort": "…"},
   "512":   {"format": "rows", "rows": ["…"]},
   "5000":  {"format": "rows", "rows": ["…"]},
   "20000": {"format": "rows", "rows": ["…"]},
   "39366": {"format": "msystem", "tecken": ["1", "X", "2", "1X", "1X2", "…"],
             "motivering_kort": "…"}}}
```

| Utfall | Agentradens status |
|---|---|
| sandbox, profil, agentkatalog, agentens python eller `~/spel-ai-data` saknas | `saknas` för alla nivåer — **ingen agentkod körs** (fail closed) |
| exit ≠ 0, timeout, ogiltig JSON, inget objekt, saknad `version`/`forslag` | `ogiltigt` för alla nivåer, orsak + stderr (sista 2 000 tecken) |
| en nivå saknas eller är ogiltig | `ogiltigt` för just den nivån |
| giltig nivå | `fryst` |
| agenten svarade efter fristen | `missat` |

Standarden fryses ALLTID, före agentkörningen, även när agenten fallerar.
Strategibyten är fria: `version` sparas per rad (`strategy_version`).

### Sandboxen (`backend/app/spelai/agent.sb`)

`(allow default)` följt av: `deny network*`; `deny file-write*` utom
`~/spel-ai-data`, `/private/tmp`, `/private/var/folders`, `stryktips.db-shm` och
`/dev/null|zero|dtracehelper|tty`; `deny file-read* file-write*` för `~/.ssh`,
`~/svs`, `~/vm`, `*/.env` och `*/.env.*` (designens lista) plus `~/.config/gh`,
`~/.aws`, `~/.gnupg`, `~/.claude`, `~/Library/Keychains`, `~/.netrc` och
`~/.git-credentials` — agentkoden saknar nät här, men det den läser kan den
skriva till `~/spel-ai-data`, som agenten senare läser MED nät. Vägar ut ur
sandboxen via andra processer är stängda: `deny appleevent-send`, exec av
`launchctl`, `osascript`, `open`, `ssh` och `sandbox-exec`, samt mach-lookup
av LaunchServices och Apple Events. I SBPL vinner sista matchande regel.

**Gränsprov på servern 2026-10-01** (macOS 15.7.9, `/usr/bin/sandbox-exec`,
`backend/tests/test_spelai_sandbox.py` + torrkörningen):

| Prov | Utfall |
|---|---|
| skriva i `~/spelkompisen`, i `~/spelkompisen/backend/data/`, i `~` | nekat (EPERM) |
| skriva i `~/spel-ai-data` och i temp | tillåtet |
| läsa `~/.ssh`, `backend/.env` | nekat |
| läsa `stryktips.db` med `mode=ro` medan facitsidan håller den öppen | fungerar |
| skriva i databasen via SQL (`mode=ro`) | nekat: `attempt to write a readonly database` |
| skriva direkt i `stryktips.db-wal` | nekat |
| nätverk ut (1.1.1.1:443) och till 127.0.0.1:8002 | nekat |
| läsa `~/.claude`, `~/Library/Keychains` | nekat |
| exec av `osascript` och `open` | nekat; `/bin/ls` fungerar |
| läsa Spelkompisens kod (`~/spelkompisen/CLAUDE.md`) | tillåtet (avsiktligt) |

`launchctl submit` provades inte (uppdraget förbjöd launchctl); exec av
`/bin/launchctl` nekas av profilen.

**WAL-fyndet (designens öppna fråga 14.2):** en `mode=ro`-läsare i sandboxen
kan inte skapa `-wal`/`-shm`. När ingen annan process har databasen öppen finns
filerna inte, och läsningen misslyckas med `unable to open database file`. När
facitsidan håller en anslutning öppen (det gör `spelai-tick` under hela
agentkörningen) lyckas läsningen. Agenten ska därför läsa databasen BARA under
facitsidans anrop, eller i övrigt via sitt eget agent.db; paketet bär allt som
standarden använder. Att ge sandboxen skrivrätt på `-wal` vore farligt (agenten
kunde korrumpera databasen) och görs inte.

## 5. Standarden

Standarden = Spelkompisens byggare på samma budget, strategi medel, samma paket.
Den byggs med PH3:s egen byggväg `pool_system_ledger.build_config_rows` (utbruten
ur `freeze_due` 2026-10-01, ren refaktor) och configs som hämtas ur PH3:s
förregistrerade familjer — aldrig en kopia:

| Nivå | Config (`config_key`) | Familj | Byggare |
|---|---|---|---|
| 256 | `dr1-b256-medel` | PH3-championen | `build_ev_system`, draw-risk |
| 512 | `dr1-b512-medel` | PH3-gridens 512 medel | `build_ev_system`, draw-risk |
| 5 000 | `ph5-v4-dr1-b5000-medel` | PH5 forward (värderader) | `build_ev_system`, draw-risk |
| 20 000 | `reducedmax-v2-dr1-b20000-ev50` | reducerat max, EV medel | `build_ev_system`, fullt 3¹³-universum |
| 39 366 | `mathmax-v2-dr1-b39366-ev50` | matematiskt max, EV medel | `build_max_math_system` → M-system |

Alla har `strategy="medel"`, `value_weight=0.5`. 39 366-standarden sparas som
M-systemets tecken (kontrollerat att raderna är exakt den kartesiska
produkten). `strategy_version` = `standard:<config_key>`. Testet
`StandardLikaPH3Tests` fryser samma draw med PH3 och jämför radmängderna för
alla fem nivåer.

## 6. Status och tidsregler (`spelai_pool_proposal`)

En rad per (produkt, omgång, nivå, horisont, roll) — `UNIQUE`, så frysningen är
idempotent. Status: `fryst`, `ogiltigt`, `saknas`, `missat`, `pausad`.

* **missat** — (a) inget paket observerades i fönstret när fönstret passerat
  (+2 min marginal för ett pågående poolvarv), (b) paketet bearbetades efter
  fristen, (c) agenten svarade efter fristen. Missat bakfylls aldrig.
* **pausad** — paus (`spelai_state` nyckel `paus`) gällde när paketet skulle
  frysas eller när fönstret passerade utan paket. Ingen agentkod körs.
* **facit_start** — skrivs av migreringen. Fönster som öppnade före den räknas
  aldrig som missade (gamla `Open`-rader i `draws` finns kvar sedan juni).
* Inställda omgångar (`state` innehåller `cancel`) hoppas över.

Varje fryst rad bär `input_id`, `input_observed_at`, `obs_svs_at`,
`obs_sharp_at`, `obs_turnover_at`, `frozen_at`, `code_version` (git-hash) och
för agenten `agent_stderr`.

## 7. Rättning (`app/spelai/ratta.py`)

PH3:s kontrafaktiska rättning, nu utbruten som
`pool_system_ledger.counterfactual_settle` och använd av både PH3:s
`settle_pending` och facitsidan: officiellt utfall per eventNumber ur
`pool_event_settlement` (struken match = SvS fastställda tecken), publicerade
vinnare och belopp ur `pool_payout_tier`, egen utspädning
(`counterfactual_payout`). En nivå med 0 officiella vinnare = rullpott okänd ⇒
`payout_complete=0`, `payout_kr`/`roi` NULL — aldrig noll. Inställd omgång ⇒
`CANCELLED_NOTE`. Agent och standard rättas identiskt. Append-once i
`spelai_pool_result` (`settlement_version = spelai-v1/counterfactual-v2`).

## 8. Inkorg, svar, paus och kvot

**Utkorgsfil** (`~/spel-ai-data/utkorg/*.json`, högst 64 kB):

```json
{"id": "koord-2026-10-02-kvot", "typ": "beslut", "kalla": "Koordinatorn",
 "rubrik": "Höj taket till 10 körningar", "varfor": "…",
 "alternativ": [{"text": "Behåll 8", "rekommenderas": false, "kvot": 8},
                {"text": "Höj till 10", "rekommenderas": true, "kvot": 10}],
 "sista_tid": "2026-10-02T18:00:00Z"}
```

`typ` ∈ `beslut`, `forslag_forbattring`, `forslag_spelrad`; `id` (A–Z, 0–9,
`._:-`, högst 100) deduplicerar — samma id igen läses inte in en gång till
(filen flyttas till `inlasta/`, händelse `inkorg_dubblett`). Beslut kräver
minst ett alternativ; högst ett får rekommenderas; `sista_tid` måste ha
tidszon. Ogiltig fil ⇒ `utkorg/avvisade/<namn>` + `<namn>.orsak.txt`.

**Svar** (`POST /api/spelai/inbox/{id}/svar`, `{"val": "1", "kommentar": "…"}`):
beslut besvaras med alternativets index eller `kommentar`; förslag med `kor_nu`,
`nej` eller `kommentar`. Sparas med tid, User-Agent, X-Forwarded-For och
klientadress. **Ett svar utan webbläsar-User-Agent (`Mozilla/`) märks
`misstankt`, ger händelsen `svar_misstankt` och räknas aldrig.** Status
härleds: `besvarad` (första icke misstänkta svar som inte bara är kommentar),
`utgangen` (sista tid passerad), annars `vantar`.

**Paus:** `POST /api/spelai/paus {"paus": true|false}` — ny rad i
`spelai_state`; senaste gäller. En ändring utan webbläsar-User-Agent gäller
(att stanna är alltid säkert) men ger händelsen `paus_misstankt`.

**Klientadressen:** Vite-proxyn på 5175 (`frontend/vite.config.js`) sätter inte
`X-Forwarded-For`, så alla svar via webben kommer i dag från `127.0.0.1` utan
XFF. "Svar från servern själv" går därför ännu inte att skilja från ett
webbsvar på adressen — bara på User-Agent. Förslag: `xfwd: true` i båda
proxyblocken (fas G).

**Kvot:** `MAX_KORNINGAR_ABS = 12` per svenskt dygn står i koden
(`tillstand.py`). Godkänt tak = det senast besvarade beslutet vars valda
alternativ bär `kvot` (klippt mot 12), annars 8. Används av fas F.

## 9. Notiser (`app/spelai/notis.py`)

ntfy med ämnet i `SPELAI_NTFY_TOPIC` (gitignorerade `backend/.env`); valfri länk i
`SPELAI_NOTIS_LANK`. Utan ämne bokförs bara `spelai_event` (kind `notis`,
`skickad: false`). En notis per spel och tidpunkt (samlad för alla nivåer), per
nytt beslut och per missat förslag. Tysta timmar 23–07 svensk tid utom beslut
med sista tid; uppskjutna notiser skickas efter 07 om spelstoppet inte
passerat. Aldrig rader, insatser eller loggar. Dedup via
`spelai_event.dedup_key = notis:<händelse>`. Spelkompisens `NTFY_TOPIC` rörs inte.

## 10. API (backend 8002)

| Väg | Vad |
|---|---|
| `GET /api/spelai/pool?product=&limit=` | omgångar → nivåer → horisonter → `agent`/`standard` med status, orsak, version, rader, underlagstider, facit; `per_niva` = parade officiella omgångar (siffror, aldrig "förbättring" under 40) |
| `GET /api/spelai/inbox` | poster med härledd status, effektivt svar, kommentarer; `vantar` = väntande beslut |
| `POST /api/spelai/inbox/{id}/svar` | se 8 |
| `POST /api/spelai/spelat` | `{"typ": "pool", "forslag_id": N, "not": "…"}` eller `{"typ": "live", "spel_id": N}` — bokför bara |
| `POST /api/spelai/paus` | se 8 |
| `GET /api/spelai/korningar` | `spelai_run` + dagens kvot + paus |

GET svarar `{"tabeller": false, …}` när tabellerna saknas. POST svarar 503.

## 11. Tabeller och migrering

`backend/scripts/migrera_spelai.py [--db PATH] [--backup-dir DIR]`: onlinebackup
med SQLite:s backup-API (`<db>-<datum>-fore-spelai.db`), sedan
`CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS` i en transaktion, kontroll att
skyddade tabellers antal är oförändrade, `facit_start` första gången och
`integrity_check`. Idempotent. Ingen annan kod skapar tabellerna — `Storage`
känner inte till dem.

Tabeller: `spelai_state`, `spelai_event`, `spelai_input`,
`spelai_pool_proposal`, `spelai_pool_result`, `spelai_run`, `spelai_inbox`,
`spelai_inbox_answer`, `spelai_played` samt livetabellerna `spelai_live_price`,
`spelai_live_bet`, `spelai_live_result` (fas E, oanvända). **Append-only är
tekniskt:** varje tabell har triggrar som avbryter UPDATE och DELETE.

## 12. Torrkörning 2026-10-01 (produktionsdata, read-only)

Produktionsdatabasen öppnades `mode=ro` och kopierades med backup-API:t till en
temporär katalog; migrering och ticks kördes mot kopian, som sedan raderades.
Draw rekonstruerades ur kopians snapshots (bara i torrkörningen), sharp och
movement med poolvarvets funktioner, klockan simulerad.

* Stryktipset 4973 (stopp 2026-10-03T13:59Z): 6h-fönster 07:59–08:29Z,
  30m-fönster 13:24–13:29Z. Standarden byggdes för alla fem nivåer: 256, 512,
  5 000, 20 000 rader och M-systemet 39 366 (3 spikar, 1 halv, 9 hela), 4,4 s
  per tick. Agenten i den riktiga sandboxen gav `ogiltigt` (sidoprojektet
  saknade ännu `agent.forslag`); en falsk agent i samma sandbox gav `fryst`
  på alla nivåer.
* Topptipset Extra 1871 och Topptipset 4361: standard 256 rader på båda.
* Notiser utan ämne: bara händelser.

## 13. Utelämnat i fas B

Rollkörningar (`claude -p`) startades inte i fas B — se avsnitt 14 (fas F).
Livedelen (fas E), nya UI:t och Idag-bannern (fas G) ingår inte.

## 14. Rollkörningar (fas F)

**Status 2026-10-01:** byggd och testad i worktree `claude/spelai-roller`
(falsk körare, lokala repon, Chrome-gränsprov), inte driftsatt. `claude` har
aldrig körts av koden.

Facitsidan är klockan (princip 2). `cli.py spelai-roller` (launchd
`com.saman.spelai.roller`, var 5:e min, `Nice` 10) gör i tur och ordning:

```
spelai-roller
  1. spegel.spegla      eget lås (spelai-spegel.lock); launchd startar ingen ny
                        instans medan en körs, så under en lång rollkörning
                        (≤ 40 min) väntar spegeln till nästa varv
  2. rollåset (spelai-roller.lock) taget, annars tyst slut ("körning pågår")
     a. roller.stada_avbrutna   roll_start utan spelai_run-rad → rad med status fel
     b. roller.due              kandidater i prioritetsordning (nedan)
     c. skarmbilder.ta          bara före en veckogenomgång
     d. roller.run              HÖGST EN körning per varv
```

Notiserna skickas av `spelai-tick` som förut (avsnitt 9), ur journalen.

### Vad som är due (`app/spelai/roller.py`)

| Prioritet | Uppgift (stabil nyckel) | Roll | Modell | Tid | Turer | När |
|---|---|---|---|---|---|---|
| 1 | `motivering:<produkt>:<omgång>:<horisont>` | forskaren | sonnet | 10 min | 25 | agentens förslag (6h/30m, `fryst`) frystes de senaste 2 h och har annan `rows_hash` än standarden på minst en nivå (båda `fryst`) |
| 2 | `larm:<kind>:<key>` | driften | sonnet | 20 min | 40 | `level: error` i vaktens `vakt.json` med `since` EFTER `facit_start`; högst 3 larmkörningar per svenskt dygn |
| 3 | `morgonrunda:<YYYY-MM-DD>` | driften | sonnet | 20 min | 40 | 07:00 ≤ svensk tid < 22:00, en per dygn |
| 4 | `forskningspass:<YYYY-MM-DD>` | forskaren | opus | 40 min | 80 | 10:00 ≤ svensk tid < 22:00, en per dygn |
| 5 | `veckogenomgang:<ISO-år>-W<vv>` | anvandaren | sonnet | 15 min | 30 | söndag 11:00 ≤ svensk tid < 22:00, en per vecka |

* Så länge agenten kör `standard-v1` (samma rader som standarden) blir det
  inga motiveringar.
* Inget är due vid paus (`spelai_state` `paus`), när rollåset hålls av en
  annan process, eller när `tillstand.kvot_idag(...)["kvar"] == 0`. Då loggas
  `kvot_slut` (dedup `kvot_slut:<dag>`) med de väntande uppgifterna — bara när
  något faktiskt väntar. Taket är det besvarade beslutets `kvot` klippt mot
  `MAX_KORNINGAR_ABS = 12`, annars 8 (avsnitt 8). Kvoten räknar
  `spelai_run`-rader per svenskt dygn, så motiveringar och larm ingår.
* **En uppgift körs högst en gång:** `roll_start` skrivs FÖRE processen med
  `dedup_key = roll_start:<dedup>`; `dedup` = uppgiften, för larm uppgiften +
  `since` (ett larm som försvinner och kommer tillbaka med ny `since` är ett
  nytt larm). En körning som misslyckats görs inte om samma dag.
* Vaktens meddelande går in i larmprompten kapat till 300 tecken och märkt
  som data, inte instruktioner. Fynd om rollernas eget jobb (`key`
  `spelai-roller`, t.ex. `jobb_ej_laddat` strax efter driftsättningen) ger
  ingen körning: kör jobbet inte kan inget larm köras, och kör det är fyndet
  inaktuellt.
* Prompterna är betrodd text i koden, på svenska, med svensk tid och UTC
  injicerade, och pekar på rollbeskrivningen i agentrepots
  `.claude/agents/<roll>.md`. Alla slutar med kravet på EN rad
  `SAMMANFATTNING:` (högst 200 tecken, inga kuponger, rader eller insatser).
  Motiveringen skrivs till `~/spel-ai-data/motiveringar/<produkt>-<omgång>-<horisont>.md`
  (högst 120 ord; katalogen skapas av facitsidan före körningen).

### En körning (`roller.run`)

`roll_start` → köraren → **exakt en** `spelai_run`-rad (role, task, started_at,
ended_at, status `klar`/`fel`/`timeout`, model, usage_json, cost_usd, note) →
`roll_klar` (status klar) eller `roll_fel` (fel/timeout), båda med
`dedup_key = roll_slut:<dedup>`.

* Svaret tolkas ur `--output-format json`: `result`, `is_error`, `subtype`,
  `num_turns`, `total_cost_usd`, `usage` (`usage_json` bär `usage`,
  `num_turns`, `subtype`, `duration_ms`, `session_id`, `modelUsage`).
  `is_error`, `subtype` som börjar med `error` (t.ex. `error_max_turns`) eller
  exit ≠ 0 ⇒ `fel`. Inget JSON ⇒ `fel` med stderr (sista 300 tecken).
* `note` = SAMMANFATTNING-raden (den sista om flera; markdown tål), eller
  felet. Teckenföljder som liknar rader (`[1X2]{8,}`) ersätts med `[rad]`.
* En process som dör utan slutrad (strömavbrott, SIGKILL) får sin rad i
  efterhand av `stada_avbrutna`: status `fel`, `ended_at` NULL, not
  `avbruten: …`. Den räknas då i kvoten — den kostade ändå.

**Den riktiga köraren:** `claude -p --agent <roll> --model <model>
--permission-mode acceptEdits --permission-prompts none --output-format json
--max-turns <n> "<prompt>"`, arbetskatalog `~/spel-ai-kompisen`, egen
processgrupp (`start_new_session`), hela gruppen får TERM och efter 10 s KILL
vid tidsgränsen. Miljön är REN: `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`,
`TMPDIR` och `PATH=$HOME/.local/bin:/usr/bin:/bin` — Spelkompisens `.env`
laddas in i facitsidans process och får aldrig ärvas av agenten (testat).
SIGTERM från launchd dödar körningens grupp och ger raden `fel`/`avbruten`.
Körs aldrig i `sandbox-exec` (claude behöver nyckelringen och nät); agentens
Bash isoleras av Claude Codes sandbox enligt agentrepots `.claude/settings.json`.

### Skärmbilder åt Användaren (`app/spelai/skarmbilder.py`)

Agentens Bash når inte 127.0.0.1 (gränsprovet), så facitsidan tar bilderna
före varje `veckogenomgang`: `#/`, `#/pool`, `#/beslut`, `#/live`, `#/agent`
som `hem|pool|beslut|live|agent-390x844.png` och `…-hel.png` i
`~/spel-ai-data/skarmbilder/<YYYY-MM-DD>/`. Filnamnen (eller att inga bilder
kunde tas) står i prompten. Händelse `skarmbilder` i journalen.

Skriptet är facitsidans **betrodda kopia** `tools/spelai/skarmbild.mjs` av
agentens `tools/skarmbild.mjs` (a2fbc12), granskad rad för rad. Originalet
öppnade en DevTools-port (9300–9899) och gav sidan fri tillgång till
loopback — en sida som agenten skriver kunde alltså ha POST:at till valfri
lokal port eller tagit över webbläsaren via porten. Kopian:

* godtar bara URL:er med exakt ursprunget `SKARMBILD_ORIGIN`
  (`http://127.0.0.1:5176`, satt av Python-sidan);
* ger Chrome en död proxy (`127.0.0.1:9`) och `--proxy-bypass-list=<-loopback>;127.0.0.1:5176`
  — senare regler går före tidigare, så ordningen är avgörande;
* talar DevTools över pipe (`--remote-debugging-pipe`), ingen TCP-port;
* stänger av Chromes bakgrundstrafik och WebRTC utanför proxyn;
* skriver bara `<ut.png>` (profilen är en temporär katalog som tas bort),
  validerar sidans scrollmått och kapar helsidan vid 16 000 px.

Miljön till node är ren (`PATH=/usr/bin:/bin`, `HOME`, `LANG`, `TMPDIR`,
`SKARMBILD_ORIGIN`, `CHROME`).

**Gränsprov på servern 2026-10-01** (Chrome headless, en "app" på port A vars
sida försökte nå en annan lokal port B med `fetch` POST no-cors, `fetch` via
`localhost`, `<img>`, `sendBeacon`, `WebSocket` och DevTools-portarna
9300–9309):

| Bypass-lista | A (ursprunget) | B (annan lokal port) |
|---|---|---|
| ingen proxy (agentens original) | sidan laddas | **nås**: img, POST, beacon, WebSocket |
| `127.0.0.1:A;<-loopback>` | nekas (`ERR_PROXY_CONNECTION_FAILED`) | nekas |
| `<-loopback>;127.0.0.1:A` (kopian) | sidan och `/self` laddas | **inget** |

En URL mot 8002 avvisas med exit 2 innan Chrome startar. Riktiga bilder av
agentens app (5176, `#/pool` och `#/` som helsida) togs till `/tmp` och visar
sidan med data via appens egen proxy.

**Kvarstående (ej skärmbildernas):** agentens app på 5176 proxar
`/api/spelai` till 8002 och tjänstesandboxen `tjanst.sb` tillåter det, så
agentens egen serverkod kan redan i dag skicka ett "svar" med webbläsar-
User-Agent till beslutssidan (avsnitt 8, `xfwd`-förslaget i fas G). Det
absoluta taket begränsar skadan för kvoten.

### Spegling till GitHub (`app/spelai/spegel.py`)

Högst var 10:e minut (mätt på spegelns `FETCH_HEAD`): `git fetch` FRÅN
`~/spel-ai-kompisen` med `+refs/heads/main:refs/heads/main` till den betrodda
bara spegeln `~/spel-ai-spegel.git` (skapas vid behov, `spegel_skapad`), och om
`main` skiljer sig från senast pushade (`refs/spegel/pushad` i spegeln):
`git push git@github.com:t0mteee/spel-ai-kompisen.git refs/heads/main:refs/heads/main`
FRÅN spegeln, sedan `spegel_push` i journalen.

* git körs aldrig med agentrepot som arbetskatalog (bara `--git-dir=<spegel>`,
  cwd `~`) och alltid med `-c core.hooksPath=/dev/null` (testat: krokar i både
  spegeln och agentrepot körs inte). Miljön är ren, `GIT_TERMINAL_PROMPT=0`,
  `GIT_CONFIG_NOSYSTEM=1`, ssh i `BatchMode`.
* Push är bara fast-forward. Skriver agenten om `main` (t.ex. `reset` vid en
  återställning) avvisar GitHub pushen: `spegel_fel` loggas en gång per huvud
  och spegeln står still tills Saman bestämt (force-push eller ny gren).
* En misslyckad push görs om nästa varv, eftersom `refs/spegel/pushad` bara
  flyttas efter en lyckad push. Testat mot lokala repon, aldrig mot GitHub.

### Notiser

`notis.kandidater` läser även journalen: `roll_klar` ⇒ "Agenten: morgonrunda
klar" + sammanfattningen (kapad vid 180 tecken, radliknande följder bort),
`roll_fel` ⇒ "Agenten: forskningspass misslyckades/avbröts" utan felutskrift,
`kvot_slut` ⇒ "Agenten: dagens tak nått" (en per dygn). Samma tysta timmar
(23–07, skjuts upp) och dedup (`notis:roll:<dedup>`, `notis:kvot_slut:<dag>`).

### Drift

| Vad | Plats |
|---|---|
| launchd | `backend/scripts/com.saman.spelai.roller.plist` (StartInterval 300, RunAtLoad, Nice 10) |
| loggar | `backend/data/spelai-roller.out.log` / `.err.log` (en rad per varv där något hänt) |
| lås | `backend/data/spelai-roller.lock`, `backend/data/spelai-spegel.lock` |
| tjänst | `spelai-roller` i `tools/spelkompisen_tjanster.py` (projekt spel-ai-kompisen, ingår i gruppen `spelai`) och i vaktens `JOBS` |

Driftsättning: deploya, `cp backend/scripts/com.saman.spelai.roller.plist
~/Library/LaunchAgents/`, `tools/tjanster.sh start spelai-roller`. Första
varvet (RunAtLoad) skapar spegeln och pushar agentens `main`, och om klockan
är 07–22 startar det morgonrundan direkt. Vakten larmar `jobb_ej_laddat` för
`spelai-roller` från deploy tills plisten är laddad.

**Utelämnat i fas F:** Användarens korta körningar vid 6 h- och
30 min-förslagen (designens avsnitt 6; bara söndagens genomgång är
schemalagd), forskningspasset 15:00 från vecka 2, chattsessionen
(`com.saman.spelai.chatt`, tmux + Remote Control) och visning av rollernas
status i API/UI (finns redan i `GET /api/spelai/korningar`).
