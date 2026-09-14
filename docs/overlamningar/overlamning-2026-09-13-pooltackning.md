# Pooltäckning 2026-09-13 — var och varför Pinnacle saknas vid frysningarna

Datum: 2026-09-13 (Claude). Del A i Codex plan
(`overlamning-2026-09-13-modell-ui-plan.md`): read-only rapport över
1X2-/Ö/U-bortfall, samma omgångar vid 180 och 20 min, uppföljning av
Brighton/Millwall-fyndet. Datarapport: `docs/pool-tackning-2026-09-13.md`
(+ `.json`), genererad av `backend/scripts/pool_tackning_rapport.py` — kör den
igen när som helst; den läser databasen read-only och ändrar inget. **Ingen
provider-, tids- eller matchningsregel har ändrats**: allt nedan är fynd och
⚖-beslut för Saman.

## Kort svar

1. **Ö/U-täckningen ÄR 1X2-täckningen.** Där 1X2 var giltigt observerad efter
   2026-09-02 saknades totalen i noll fall (`total_saknas` = 0 i alla celler).
   Flaskhalsen är Pinnacle-presence vid horisonten, inte totalen.
2. **Topptipset vid 180 min har giltig sharp i 12 % av matcherna** (60/496),
   vid 20 min 59 %; Stryktipset 54 %, Europatipset 48 % vid 180 min.
   Forwardtesternas egna omgångar ligger på samma nivå.
3. **Tre mekanismer i vår egen insamling står för nästan hela bortfallet.**
   Namnmatchningen (Brighton/Millwall-spåret) är verklig men liten: fyra
   unika par.

## Mekanismerna, i storleksordning

### M1 · Horisontfönstret ligger EFTER as-of (dominerande)

`pool_dataset.horizon_window_open` tvingar Pinnacle-hämtningen förbi
dubbeltrafikspärren när `cutoff ≤ now ≤ cutoff + tolerans`. pit-v4 räknar bara
en capture i `[cutoff − tolerans, cutoff]`. Den tvingade observationen hamnar
alltså per konstruktion på FEL sida av as-of och räknas bara när CDN-Age råkar
backdatera stämpeln förbi as-of. Docstringen säger "±"; koden gör "+".

Topptipset-familjen, 75 omgångar sedan 2026-08-15: capture på rätt sida vid
h24 22, h3 16, m20 48 omgångar — BARA på fel sida 50, 56 respektive 25.
Se tabellen "Observationsfönstret" i datarapporten.

### M2 · Bara första produkten får ordinarie sharp-captures

Basvarvet loopar produkterna och anropar `collect_pinnacle` per öppen omgång.
Dubbeltrafikspärren (`PINNACLE_MIN_INTERVAL_S` = 600 s, global meta-nyckel)
hoppar därför över alla produkter efter den första i samma varv, och en
överhoppad hämtning skriver — korrekt enligt observationstidsregeln 6 — ingen
capture. Uppmätt: distinkta sharp-observationer per dygn (median) —
Stryktipset 48, Topptipset 14, Europatipset 6, Extra 3, Topptipset Stryk 2.
Utanför fönstren observeras Topptipset-familjen alltså sällan, och därför
finns nästan aldrig en capture 0–45 min FÖRE as-of att räkna.

### M3 · Featurebygget hinner före fönstercapturen

`build_recent` körs i `_settle_pass` på VARJE tick, även utan basvarv, så snart
`cutoff ≤ now`. Den tvingade hämtningen (M1) kommer i nästa basvarv,
backdateras av Age till före as-of — men pit-raden är redan byggd och byggs
aldrig om (idempotent per nyckel/version). Klass `pit_byggd_fore_capture`:
22 rader i två omgångar (4322, 4329). Små tal, men mekanismen slår varje gång
M1:s tvingade capture faktiskt hade räknats.

### M4 · Poolmatcharen fäller korrekta par (Brighton/Millwall-spåret)

64 unika matcher var aldrig matchade vid 20 min. Replay av `pinnacle.match`
offline mot Oddsets sparade Pinnacle-namn för samma match:

- **51** — ingen Pinnacle-rad hos Oddset: ligor Oddset inte följer (League One,
  Colombia, Brasilien, Argentina, Mexiko …). Om Pinnacle listade dem vet vi
  inte.
- **9** — Pinnacle listade bevisligen matchen dagar före spelstopp (Oddset hade
  odds), men Oddset-raden bär Kambis namn (`oddset_upsert_match(prefer_names)`),
  så vilket namn poolmatcharen avvisade är okänt. Bl.a. Millwall–Bolton,
  Leeds–Brentford, Tottenham–Newcastle, Cagliari–Inter, Real Madrid–Inter.
- **4** — korrekt par fälls av tröskeln (sida ≥ 0,60, kombinerat ≥ 0,72):
  Brighton–Leeds (`Leeds` mot `Leeds United` 0,588), Nottingham–Tottenham
  (kombinerat 0,716), Manchester United–Sabah Masazir (`Sabah FK` 0,556),
  Mainz–Frankfurt (`Eintracht Frankfurt` 0,643; kombinerat 0,706). Oddsets
  `norm_team` (substrängsregel + suffixstrippning) hade tagit alla fyra.

Svar på frågan om 20-minutersobservationen: den löser **inga** av dessa —
85 av 85 `aldrig_matchad` vid 180 min förblir det vid 20 min; ett par som
matcharen avvisar avvisas i varje varv. Däremot löser 20 min 309 av 462
`capture_sen` från 180 min, eftersom täta ticks och Age oftare hamnar rätt.

### M5 · Övrigt

`ingen_capture` (Topptipset h3 24, m20 16 matcher): omgångar som listades
sent eller aldrig scannades (4287 och 4311 saknar sharp helt; 4275 sågs
2,5 h före stopp). Topptipset h24: omgången syns ofta först ~24 h före stopp
(4329: första capture en minut efter h24-as-of) — h24 är strukturellt svår
för dagsomgångar.

## Vad det betyder för mätningarna

- **PH4 Topptipset** (skördad 2026-09-02, ej stöd) är mätt på en presence där
  h3 sällan var giltig. Domen står — grinden krävde bättre än Pinnacle och
  det blev sämre — men effekten är mätt på gles data.
- **pit-total-v1** når inte 40 kompletta Topptipsomgångar vid h3 med dagens
  insamling: gater visar 2/40 (av 27 observerade sedan 2026-09-02), m20 10/40.
- **PH3 sannolikhetsbas** (`dr1-b256-medel-sharp`) och **poolopt** fryses på
  samma presence: där Pinnacle saknas faller byggaren tillbaka, och
  jämförelsen mot championen blir i de matcherna en jämförelse av fallback.

## ⚖ Beslut för Saman — inget av detta är gjort

a–c ändrar HUR OFTA en observation blir giltig, inte VAD giltig betyder
(`timing_policy` oförändrad). Jag rekommenderar ändå att de bokförs som ny
featureversion (`pit-v5`, samma regler) från driftsättningsdatumet, så PH4:s
Stryk/Europa-kohorter (8 respektive 14 av 40) inte får en glidande presence
mitt i serien. Alternativet — behåll pit-v4 och notera datumet i manifestet —
är billigare men blandar två insamlingsregimer i samma kohort.

a) **Fönster före as-of.** Öppna `horizon_window_open` i
   `[cutoff − tolerans, cutoff]` (eller ±) så den tvingade hämtningen kan
   räknas. Rättar M1. En rad kod, men det är en tidsregel.
b) **Bygg efter fönstret.** Låt `build_recent`/`build_total_draw` bygga en
   horisont först när `cutoff + tolerans + marginal` passerats. Rättar M3.
c) **En Pinnacle-hämtning per varv.** Hämta `soccer_index` en gång per
   basvarv och matcha alla produkter mot samma index; spärren står kvar men
   biter inte på produkt 2–5. Rättar M2 med färre anrop, inte fler.
d) **Poolmatcharens namnregel.** Ge `pinnacle.match` samma substrängs-/
   suffixregel som Oddsets `norm_team`, eller en pool-aliastabell. Rättar
   M4:s fyra kända par framåt; historik bakfylls aldrig.
e) **Diagnostisk logg.** Spara närmaste Pinnacle-kandidat med sidopoäng när
   matcharen avvisar (egen tabell, påverkar ingen serie). Gör klassen
   "namnform okänd" mätbar i stället för gissad.

Ordning om allt godkänns: c → a → b i ett paket under ny version, d och e
separat. Efter driftsättning: kör `pool_tackning_rapport.py --sedan
<driftsättningsdatum>` och jämför tabellen "Observationsfönstret".

## Reproduktion

`cd backend && .venv/bin/python -B scripts/pool_tackning_rapport.py
[--sedan 2026-08-15] [--out docs/pool-tackning-ÅÅÅÅ-MM-DD]` — read-only URI,
~10 s. Replayen behöver inget nätverk (`Pinnacle.match` är ren). Klasserna
definieras i skriptets docstring; `--sedan` sätter vilka sluträttade omgångar
som ingår.

## Beslut och genomförande 2026-09-14

Saman 2026-09-14: kör a–e, **behåll pit-v4** (och pit-total-v1) med datumnot,
namnregel och diagnostik enligt rekommendationen. Genomfört samma dag:

- a) `pool_dataset.horizon_window_open`: fönstret är ± toleransen kring as-of.
- b) `pool_dataset.horizon_ready` + `BUILD_AFTER_WINDOW_MIN = 16`: `build_draw`
  och `build_total_draw` bygger en horisont först när fönstret stängt och
  Pinnacles max-age (905 s) inte längre kan backdatera en capture in i det.
- c) `sharp_service.VarvIndex`: ett Pinnacle-index per basvarv, delat av alla
  produkter och omgångar; `cli._any_horizon_window_open` avgör `force` före
  första produkten; `cmd_snapshot(product, varv)`.
- d) `odds_provider.team_sim`: Oddsets `norm_team` + delsträng ⇒ 1,0, olika
  truppmarkörer eller känt falskt par (`TEAM_REJECTED_LINKS`) ⇒ 0,0, annars
  SequenceMatcher; trösklarna 0,60/0,72 oförändrade. Replay av de fyra kända
  paren träffar.
- e) `pinnacle.match_index(..., diag)` + tabellen `pool_match_diagnostic`
  (upsert per event och kandidat, räknar varv). `docs/db-atgarder.md`.

Datumnot i `docs/pool-ph4-forward-manifest-v3.json` (`collection_notes`) och i
`docs/pool-pit-total-v1-2026-09-02.md`; regel 10 i CLAUDE.md. Nio nya tester
(`backend/tests/test_tackning_ae.py`), hela sviten grön.

**Uppföljning:** kör `scripts/pool_tackning_rapport.py --sedan 2026-09-14`
efter en vecka. Förväntat: kolumnen "capture före as-of (räknas)" för
Topptipset h3/h24 går från ~20–30 % av omgångarna till de flesta, och
klassen "namnform okänd" kan ersättas av `pool_match_diagnostic`.

**Första varvet i drift (2026-09-14 kl. 10:12):** alla tio öppna omgångar fick
sharp-captures med samma observationstid (delat index); Stryktipset 4971 gick
från 6 till 11 matchade av 13, Europatipset 2608 13 av 13. Diagnostiken fann
direkt tre par som fortfarande föll på sidolikheten trots samma motståndare
och avspark — CR Brasil/CRB, Royale Union SG/Union Saint-Gilloise, Milton
Keynes Dons/MK Dons — nu bekräftade alias i `TEAM_ALIASES`. Kvarvarande
`not_listed` (Birmingham–Middlesbrough, Lincoln–Swansea, Internacional de
Bogotá–Atlético Nacional) hade ingen kandidat alls: Pinnacle hade inte listat
dem ännu.
