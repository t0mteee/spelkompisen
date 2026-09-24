# Överlämning — färskhetsregel för poolens Pinnacle-priser och synliga stopp (2026-09-24)

**Driftsatt 2026-09-24T14:11:09Z** (första pooltick 14:12Z), på Samans order att rätta missade och gamla odds. PH3-nycklarna är oförändrade med datumnot.

Gjort i grenen `pool-farskhet` (worktree `/tmp/spk-fresh`) från main
`0ec4e72`. Inte mergat, inte pushat, inte driftsatt. Alla beteendeändringar nedan
gäller från DRIFTSÄTTNINGEN — skriv in datum och commit i `docs/plan.md` och
i skördeprotokollen när det sker. `docs/plan.md` och `CLAUDE.md` är orörda.
Main har sedan fått fem commits (`d123e6c`…`eb6c869`, backup och avläsningsregler);
ingen av dem rör grenens filer.

## Bakgrund (audit samma dag)

`sharp_odds` är en latest-state-tabell. Den skrivs bara när poolmatcharen
träffar och rensas aldrig när länken tappas (`ambiguous`/`not_listed` i
`pool_market_capture`). Analysen, byggaren, PH3-frysningen, CLV-loggen,
notiserna och Ö/U-reserven läste den via `Storage.get_sharp` utan
ålderskontroll. Belagda fall: Europatipset 2610 match 10 visade ett pris från
08:17Z fast länken avvisats (`ambiguous`) sedan 08:47Z; Stryktipset 4971
frystes 19/9 med priser från 15/9 06:13Z på 9 matcher vars länk varit
`not_listed` sedan 15/9 06:43Z (plus en match som aldrig länkats); vid
PH3-frysningarna sedan 10/9 var senaste sharp-capture inte `matched` för cirka
18 % av matcherna. Oddsvarningen `pool-input-health-v1` sa ”ok” eftersom den
bara prövade att ett pris fanns. Styrkeshadowen `pool-strength-blend-v1` har
inte samlat sedan 2026-08-21 20:12Z (modellversionen byttes, `capture_due`
returnerar tyst `model_source_version_changed`) men status sa ”samlar”.

## Regeln `pool-sharp-freshness-v1` (`backend/app/pool_sharp_freshness.py`)

Ett cachat Pinnacle-pris för en match är användbart vid tiden t om och endast om

- (a) `sharp_odds.fetched_at ≥ t − SHARP_MAX_AGE_MIN` (90 min), och
- (b) ingen sharp-capture för matchen med `sharp_odds.fetched_at < fetched_at ≤ t`
  har en status utanför `{matched, derived}` — då har länken observerats tappad
  EFTER priset.

Utan capture-rader gäller bara åldersregeln. 90 min: ett länkat pris är i median
7–9 min gammalt vid frysning; basvarvet går var 30:e min, spärren kan skjuta en
hämtning 10 min och CDN-åldern är upp till 15 min, så ett friskt pris kan vara
~55 min strax före nästa varv. 90 min tål ett missat basvarv, inte två.

- `fresh_sharp(store, product, draw_number, now)` → `(fresh, stale)`. `fresh` har
  exakt `get_sharp`-formen. `stale[event]` = `reason` (`link_lost`|`too_old`),
  `last_seen` (= `sharp_odds.fetched_at`), `status`/`status_at` (senaste capture ≤ t)
  och för `link_lost` även `lost_status`/`lost_at` (första capturen efter priset
  som inte bar länken — det är den ”sedan”-tiden UI:t visar).
- Tider parsas (Z, `+00:00`, `+02:00`, mikrosekunder) och jämförs som tider.
  Klockan injiceras alltid; utan `datetime` kastar funktionen `TypeError`.
- Statusvärden i prod (read-only 2026-09-24): `matched` 67 073, `not_listed`
  22 871, `ambiguous` 429 (sedan 15/9), `no_moneyline` 13, `derived` 8 (senast 4/9).
  **Avvikelse från uppdraget:** `derived` räknas som bibehållen länk (uppdraget
  sa ≠ `matched`). En `derived`-träff skriver `sharp_odds` i samma observation, så
  den kan aldrig ligga efter priset — i praktiken ingen skillnad.
- `coverage(...)` ger andel färska + orsaker för pool_health. `explain(...)` ger
  svensk text i svensk tid: ”Pinnacle-länken tappad (tvetydig) sedan 10:47”,
  ”Pinnacle-priset äldre än 90 min (senast 15/9 10:17)”.
- Regeln LÄSER bara. Inget raderas i `sharp_odds`, inget bakfylls, ingen ny nättrafik.

## Var regeln används (alla tidigare `get_sharp`-läsare)

| Väg | Före | Nu |
|---|---|---|
| `main._analyze` (`/api/analysis`, `/api/system`, `/api/spikar`) | rå cache | färska priser; matcher med borttaget pris bär `sharp_stale` (+ `text`, `version`) |
| `cli._pool_pit_freeze` → PH3 `freeze_due` | rå cache | färska priser vid FRYSNINGENS klocka (samma `now` stämplar `frozen_at`/lag) |
| `cli.cmd_system` (`cli.py rad`) | rå cache, hårdkodat `"stryktipset"` | rätt produkt + regeln; skriver ut orsaken per borttagen match |
| `clv.log_flags` (poolens `value_log`) | rå cache | färska priser vid loggtiden |
| `notify.check_movers` (pausat spår) | rå cache | färska priser; `now` injicerbar |
| `pool_reserve.collect` | total i rå cache höll reserven borta | inaktuell total räknas som saknad; `now` injicerbar |

Kvar som rå `get_sharp`: bara inne i färskhetsmodulen (docstring på
`Storage.get_sharp` säger att analys/beslut ska gå via regeln).

Följdändringar:

- **Rörelse:** `steam.movement_with_steam(..., stale=)` ger inaktuella matcher
  SvS-oddsens serie (som när sharp saknas) och inget steam-skift; övriga matcher
  och steam-trösklarna orörda. `/api/steam` (Steam-panelen) utesluter inaktuella
  matcher ur ”nu”-tabellen.
- **Stängd omgång** (bara `/api/analysis` och `/api/steam`): bedöms vid
  spelstoppet (`as_of = min(nu, spelstopp)`), så en avgjord omgång visar läget
  vid stopp i stället för att allt kallas för gammalt. Öppna omgångar och alla
  insamlings-/frysvägar använder exakt `now`. (Eget tillägg — säg till om det
  inte önskas.)
- **Captureordning i `cmd_snapshot`:** varvets sharp-capture bokförs direkt efter
  Pinnacle-hämtningen (samma rader, samma observationstid; `_pool_pit_freeze`
  gör om anropet utan effekt tack vare `INSERT OR IGNORE`). Annars såg reserven,
  notiserna och CLV-loggen, som körs före frysningen, en tappad länk först ett
  varv senare. (Eget tillägg.)
- **Revisionsnot i PH3:** `build_note` får
  `pool-sharp-freshness-v1: cachad Pinnacle ej använd i N matcher (2: tvetydig, …).`
  när regeln tog bort något. `rows_hash` och radformatet är orörda. (Eget tillägg,
  eftersom `system_detail` rekonstruerar sharp ur `sharp_snapshots` och annars
  inte kan visa att ett pris inte användes.)
- **Oddsvarningen** (`pool_input_health`, fortfarande `pool-input-health-v1`):
  borttagna priser räknas som saknade, varje issue har `reason` och `sharp_stale`,
  rapporten har `stale_sharp` och `freshness_version`. Nivålogiken är oförändrad.
- **UI:** `PoolInputWarning` visar ”Orsak: …”, granskningstexten tar med orsaken.
  Analystabellen visar ”P –” (grå) med title-tooltip i stället för ett inaktuellt
  pris; legenden och Sharp-panelens ”ej ompollad”-text förklarar det.

## Synliga stopp

- `pool_strength_shadow.stop_status()` (billig: manifest + meta + captures) och
  `report()`: bytt `model_signal_version` ⇒ status **`stoppad`** med
  `stopped.text` = ”modellversionen byttes (m-a6a54189 → m-6ef4fb7a), senaste
  capture 21/8 22:12”. `stoppad` ersätter bara `samlar`; en nådd datagrind
  (`candidate`) står kvar (underlaget finns redan) men `stopped` redovisas ändå.
- `gater._strength`: raden `stoppad` med ”STOPPAD: …” i anmärkningen, horisont-
  cellerna `stoppad` om de inte nått grinden. `pool_tests.RANK["stoppad"] = 8`
  (strax under `fel`), så testkatalogens rubrik blir `stoppad`. Frontend: röd ton,
  räknas som nyhet på Idag, `LabbPill` STOPPAD, och Historik → Tester →
  Poolstyrka (PoolmodellCard) visar ”Insamlingen står still: …”.
- `pool_health.report` (fortfarande helt lokal, inga nätanrop; +~13 ms varm):
  - `strength_shadow_stopped` (warning, produkt `poolstyrka`) när spåret är
    stoppat OCH har samlat någon gång (en tom databas har inget stopp att larma om).
  - `sharp_link_coverage` (warning) för öppna omgångar som stänger inom 48 h där
    under 70 % av matcherna (matchlista = omgångens SvS-`snapshots`) har färsk
    sharp; meddelandet räknar orsakerna (tvetydig, ej listad/namn, för gammal,
    ingen 1X2, aldrig observerad) och issue bär `fresh`/`n`/`reasons`.
  - Historiska frysbortfall (stängd omgång) märks `scope: "history"`. Idag visar
    aktuella varningar i en EGEN ruta (”Poolunderlag att se över: …”) — tidigare
    hamnade alla varningar under ”Historisk testdata saknas – dagens insamling
    fungerar”. `format_report`/`cli.py kallhalsa` har rubriken VARNINGAR.
  - Hälsans `status` påverkas inte av varningar (som förut).

## Beteendeändringar som påverkar mätningar — datera vid driftsättning

1. **PH3-frysningar (alla familjer: championen `dr1-b256-medel`, utmanarna inkl.
   `dr1-b256-medel-sharp`, PH5, mathmax, reducedmax, poolopt).** Från
   driftsättningen får bygget bara färsk Pinnacle. För en match med inaktuellt pris:
   ingen `sharp_prob`/`value_sharp`/edge-tagg/spik-boost från Pinnacle; utan
   SvS-odds faller sannolikhetsbasen till streck i stället för det gamla
   Pinnacle-priset; Pinnacle-totalen saknas, så X-skyddet (`pool-draw-risk-v1`)
   använder 32 %-gränsen i stället för 29,5 % vid låg total; rörelsen kommer ur
   SvS-serien och steam-skiftet saknas; sharp-utmanaren faller tillbaka på SvS.
   Samma `config_key`, samma hash-format — alltså en REGIM inne i löpande
   serier, som pool-name-v3/v4. Varje berörd frysning bär revisionsnoten i
   `build_note`. **Driftsättningstiden (UTC, sekund) är en förregistrerad
   gräns:** tillägget 2026-09-24 i `docs/ph3-sannolikhetsbas-v1-2026-09-02.md`
   (Samans beslut 5bA, på main i `d123e6c`, efter den här grenens bas) låter
   `dr1-b256-medel-sharp` fortsätta med samma nyckel och utesluter i primär
   jämförelse parade omgångar frysta FÖRE driftsättningen av
   `pool-sharp-freshness-v1` med inaktuellt underlag; frysningar efter den
   utesluts aldrig. Skriv därför in exakt tid och commit. Den retroaktiva
   definitionen där räknar bara `matched` som länkad, medan live-regeln här
   även godtar `derived` (se ovan) — ingen praktisk skillnad sedan 4/9.
   **Beslut för Saman:** räcker regimdatering även för championen, PH5,
   mathmax, reducedmax och poolopt (poolopt lästes av vid 40 omgångar
   2026-09-24, nästa och sista avläsning vid 120 hamnar i den nya regimen)?
2. **Poolens CLV-logg (`value_log`, `clv.log_flags`).** Sharp-edge-flaggor loggas
   inte längre för matcher med inaktuell Pinnacle; värdeflaggor för sådana
   matcher får SvS-sannolikhet och `prob_src='svenskaspel'` i stället för det
   gamla Pinnacle-priset. first/best-semantiken är orörd. Stängningen
   (`clv.resolve`) är OFÖRÄNDRAD — se öppna frågor.
3. **Ö/U-reserven (`pool-reserve-ou-v1`).** Matcher vars cachade Pinnacle-total
   är inaktuell räknas nu som saknade och kan få Kambi-anrop (inom oförändrad
   budget 3/varv och 15 min cooldown). Journalens urval av matcher ändras; den är
   fortfarande presentation, aldrig bygginput. Analysen visar reserven för dessa
   matcher eftersom `total_line` nu saknas.
4. **Appens analys och bygge** (`/api/analysis`, `/api/system`): samma som punkt 1
   för användarens egna byggen; fler oddsvarningar (inaktuella priser räknas).
5. **Poolhälsan och testkatalogen:** nya varningar enligt ovan; poolstyrkan
   visas som `stoppad` överallt (backdaterat faktum: stoppet började 21/8).
6. **Notiser** (pausade) och **Steam-panelen:** bara färsk sharp.

PIT-serierna (pit-v4, pit-total-v1), m20-reserven och styrkeshadowens capture
påverkas INTE — de läser captures/snapshots eller varvets egen hämtning, aldrig
`sharp_odds`.

## Verifiering

- Tester: backend 986 → **1017** (31 nya: regeln, analysvägen, PH3-vägen,
  notisvägen, rörelse/steam, oddsvarningens text, CLV-logg, Ö/U-reserv,
  styrkeshadowens status inkl. gater/katalog, två hälso-issues och
  history-scope). Frontend 47 → **51** (splitPoolIssues, stoppad-ton/nyhet,
  orsak i rubrik/granskningstext). `tools/kontroll.sh` i worktreen: ALLT GRÖNT.
  Frontendbunten byggs (`vite build`). Ingen browserkontroll: inget är
  driftsatt och worktreen har ingen riktig databas.
- Prod read-only (`mode=ro`, 2026-09-24 13:57Z), omgångar med spelstopp i
  framtiden (12 av 108 `Open`-rader i `draws`):

| Omgång | Stänger (sv. tid) | Matcher | Färsk | Inaktuell | Utan pris | Orsaker |
|---|---|---|---|---|---|---|
| Europatipset 2610 | 24/9 20:44 | 13 | 12 | 1 | 0 | match 10 link_lost, tvetydig sedan 10:47 (pris 08:17Z) |
| Topptipset Extra 1869 | 24/9 20:44 | 8 | 8 | 0 | 0 | – |
| Topptipset 4349 | 25/9 20:44 | 8 | 6 | 1 | 1 | match 3 tvetydig sedan 10:47; ej listad/namn 1 |
| Topptipset 4350 | 26/9 00:29 | 8 | 5 | 0 | 3 | ej listad/namn 3 |
| Stryktipset 4972 | 26/9 15:59 | 13 | 0 | 1 | 12 | ej listad/namn 12; match 1 tvetydig sedan 10:47 |
| Topptipset Stryk 982 | 26/9 15:59 | 8 | 0 | 1 | 7 | ej listad/namn 7; match 1 tvetydig sedan 10:47 |
| Topptipset 4351 | 26/9 20:44 | 8 | 5 | 1 | 2 | ej listad/namn 2; match 1 tvetydig sedan 10:47 |
| Topptipset 4352 | 27/9 02:29 | 8 | 7 | 0 | 1 | ej listad/namn 1 |
| Topptipset 4353 | 27/9 20:44 | 8 | 8 | 0 | 0 | – |
| Topptipset 4354 | 28/9 00:59 | 8 | 3 | 0 | 5 | ej listad/namn 5 |
| Topptipset 4355 | 28/9 20:44 | 8 | 7 | 0 | 1 | ej listad/namn 1 |
| Topptipset 4356 | 28/9 23:59 | 8 | 1 | 0 | 7 | ej listad/namn 7 |

  Alla fem inaktuella priser har pris 08:17Z och `ambiguous` sedan 08:47Z — samma
  varv tappade flera länkar samtidigt (värt en egen titt i `pool_match_diagnostic`).
  `pool_health.report` read-only gav just då två nya varningar: Topptipset 4350
  (5/8 = 62 %) och poolstyrkan (stoppad). Stryktipset 4972 och Topptipset Stryk
  982 låg på 48,0 h, precis utanför 48 h-fönstret, och varnar när de kommer in.
- Retro (approximation, pris vid frysning ≈ senaste lyckade capture ≤ frystid):
  Stryktipset 4971 vid både 180 och 20 min — regeln hade tagit bort 9 priser
  (`not_listed` sedan 15/9 06:43Z), 3 färska, 1 match utan pris.

## Öppna frågor och osäkerheter

- PH3-nycklar: regimdatering eller nya nycklar (punkt 1 ovan).
- `clv.resolve` stänger fortfarande mot sista Pinnacle-pris före avspark ur
  `sharp_snapshots`, även om länken tappades dagar före avspark. En inaktuell
  stängning är ett eget facitproblem som inte rörts här.
- `system_detail` (kupongdetaljen) rekonstruerar `sharp_odds_at_freeze` ur
  `sharp_snapshots` och visar därför priser som frysningar efter driftsättningen
  inte använde; revisionsnoten i `build_note` är enda spåret tills vidare.
- `/api/history` (matchgrafen) och `/api/movement` (oddstooltipen) visar hela
  Pinnacle-serien med tidsstämplar — historik, inte ”nu” — och är orörda.
- `/api/external-odds` (Sharp-panelens ↻) skriver `sharp_odds` utan capture
  (sedan tidigare). Ett sådant lyckat pris förnyar `fetched_at` och räknas som
  färskt; regeln hanterar det, men presence-ledgern ser det inte.
- Täckningskontrollen kan inte se strukna matcher lokalt; en struken match utan
  Pinnacle räknas som ”ej listad/namn”.
- `as_of` för stängda omgångar, den tidigare captureordningen i varvet och
  revisionsnoten är egna tillägg utöver uppdraget (se ovan).
- Styrkeshadowen: kräver nytt manifest (change_policy) för att samla vidare, eller
  ett beslut att avsluta. Varningen på Idag står kvar tills dess.

## Nästa steg

1. Granska och merga `pool-farskhet`; driftsätt enligt serverflödet (pull,
   `npm run build`, `tools/tjanster.sh omstart backend|frontend`).
2. Skriv driftsättningens datum/commit i `docs/plan.md` STATUS och i
   skördeprotokollen för PH3/poolopt/PH5 (regim), CLV-loggen och Ö/U-reserven.
3. Kontrollera efter första basvarvet: Idag visar ”Poolunderlag att se över”,
   Historik → Tester → Poolstyrka visar STOPPAD, analystabellen visar ”P –” för
   Europatipset 2610 match 10 (om länken fortfarande är tappad).
4. Besluta om styrkeshadowen (nytt manifest eller avslut).
