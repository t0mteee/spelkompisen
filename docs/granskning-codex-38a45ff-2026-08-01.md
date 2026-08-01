# Granskning av Codex-committen 38a45ff + åtgärder (2026-08-01)

Saman bad om granskning av `38a45ff` ("Spåra live-radarns signaler till
slutresultat", Codex GPT-5, 2026-07-31) och därefter att allt åtgärdas.
Granskningen kördes som multi-agent-review (6 dimensioner: metodregler,
observationstid, settlement, backend-buggar, frontend, tester/migration) med
adversariell verifiering av varje fynd — **17 bekräftade, 0 motbevisade**,
varav det kritiska reproducerades mot Kambis skarpa API av två oberoende
verifierare.

## Helhetsomdöme av Codex-leveransen

Genuint välbyggd: överlämningens påståenden höll vid kontroll (363 tester
gröna, DB-schema/backup korrekta, shadow-status utan läckage till beslutsytor,
blindgaten exakt enligt förregistrering, Asian-kvartslinjematematiken korrekt,
M20-lärdomen respekterad, append-only konsekvent). Men ett kritiskt och två
allvarliga fel fanns — alla i klasser projektet redan har regler för.

## Fynd → åtgärd (allt åtgärdat 2026-08-01)

### 🔴 Kritiskt

1. **Suspenderade Kambi-priser bokfördes som spelbara.** `live_total`
   filtrerade bara utfallens `status != "OPEN"` men läste aldrig
   betOffer-nivåns `suspended`-flagga; live-repro visade event där ALLA
   offers var `suspended: True` med utfallen `OPEN` — och parsern returnerade
   pris. Suspension korrelerar systematiskt med signalögonblicken (mål/VAR)
   → blindgatens ROI hade byggts på ospelbara odds.
   **Fix:** `kambi.py` spärrar `offer["suspended"]`; sedd-men-stängd marknad
   returneras som `{"reason": "suspended"}` och bokförs som eget
   odds_status-värde `suspended` (skilt från `not_offered` — M20-klassen).
   Test: `test_offer_level_suspension_blocks_open_outcomes`.

### 🟠 Allvarliga

2. **`match_key` instabil → dubbletter i blindkohorten.** Nyckeln löstes om
   varje tick; sen kanonisk länkning mitt i matchen (oddskollektorn upsertar
   startade matcher) eller fotmob↔sofascore-flip gav samma fysiska match två
   nycklar — "första aktiva signalen per match" kunde räknas dubbelt och en
   prissatt eskalering slinka in i 200-kravet.
   **Fix:** `_locked_key` i `live_signal_ledger.py` + två storage-uppslag:
   nyckeln låses till först bokförda radens `match_key` via providrarnas
   event-id (kortet kan bära båda) och i sista hand lagjämförelse med fyra
   spärrar (skärpta av verifieringsrundan, se nedan): provider-exklusion
   (samma provider utan id-träff = bevisat annan match), spegling accepteras,
   startgap >3 h låser aldrig, tvetydighet låser aldrig. Tester: sen
   kanonisk länkning, källflip, spegling, U23-prefixkrock, dubbelmöte,
   tvetydighet.

3. **Asymmetrisk censur i `outcome_more_before_ft`.** Injicerat officiellt
   FT-resultat kunde bevisa 0 men aldrig 1 → endast sanna ettor censurerades
   (sena mål efter sista capturen) och `more_before_ft_rate` biasades
   systematiskt nedåt.
   **Fix:** `live_settlement._outcome_more_before_ft` låter slutstatusens
   total bevisa båda utfallen (`==` ⇒ 0, `>` ⇒ 1). Momentfacitet opåverkat
   (final ligger där i `later`). 15-minutersfönstret censureras fortsatt
   ärligt (målens tidpunkt okänd). Test:
   `test_official_final_proves_a_late_goal_before_ft`.

### 🟡 Mindre (alla åtgärdade)

4. **Suspenderad ≠ saknad marknad** — egna statusvärden (se fynd 1) +
   UI-text "Ö/U var suspenderat vid signalen".
5. **`recorded_at`/`settled_at` sattes per varv** (observationstidsregeln
   p.3) — stämplas nu per rad, efter oddsanropet.
6. **Lånad klocka utan spår** — journalen speglar nu EXAKT signalens
   beräkningsbas (samma per-fält-regel som `_fotmob_signal`: FotMobs egna
   värden behålls, bara saknade fält lånas) och lånet bokförs i två nya
   kolumner: `clock_source` (inkl. 'fotmob+sofascore' för blandat) och
   `clock_observed_at` (de lånade fältens egen observationstid). DB-åtgärd
   med skript + backup + rapport, se `docs/db-atgarder.md` 2026-08-01.
   (En första "atomärt helpar"-variant fälldes av verifieringsrundan — den
   gav rader vars ställning motsade signal_score och settlementets
   providerserie.)
7. **Tysta capture-fel** — `report["errors"]` skrivs nu ut i launchd-loggen
   (`cli.py`), och hela kandidatkroppen (inkl. `_selected_source`) ligger i
   per-kandidat-skyddet så ett trasigt kort aldrig fäller varvet.
8. **`ag=NULL`-krasch** — resultatrad med bara ena målkolumnen satt hoppar
   över i `_result_for` i stället för att fälla hela settlingspasset
   permanent. Test: `test_null_away_goals_neither_crashes_nor_settles`.
9. **Oöversatt facit-enum** — `win/half_win/push/half_loss/loss` visas nu
   som vinst/halvvinst/återbetald/halvförlust/förlust i Labb.
10. **Blindgatens pass/no_support-gren otestad** — nya tester når båda
    grenarna (patchade trösklar) samt eskaleringsdedup i kohorten.
11. **Otestade felgrenar** — source_error-status, Age-avdraget på
    `odds_observed_at`, score-regress-vakten och saknat serieögonblick har
    egna tester.
12. **Migration tyst no-op på avvikande schema** — `migrate()` validerar nu
    kolumnuppsättningen mot `Storage`-kolumnerna och felar högt; testad mot
    deviant tabell och mot 07-31-schema utan `clock_source`.
13. **Backup-efter-materialisering-mönstret** (dokumenterad processrisk):
    allt som läggs i `_SCHEMA` materialiseras av första processtart — en
    datamuterande framtida migration måste ta backup FÖRE ny kod driftsätts.
    Noterat här och i db-åtgärdsloggen; ingen kodändring (ingen data fanns).

## Adversariell verifieringsrunda av fixarna (samma dag)

Efter första fixomgången kördes tre oberoende skeptiker mot diffen med
uppdrag att motbevisa den. De fällde tre delar av de egna fixarna, som
omarbetades innan något committades:

1. **Lagfallbacken i nyckellåset var för lös.** En 8 h-fönstrad
   prefix-jämförelse utan starttids- eller provider-spärr kunde låsa FEL
   match (dubbelmöten; 'Inter'↔'Inter U23' — prod-DB:ns friendlies domineras
   av just U21/B-lag) och därmed TYST TAPPA den nya matchens signal, samt
   missade spegelvänd orientering. **Omfix:** provider-exklusion (samma
   provider utan id-träff = bevisat annan match), spegling accepteras,
   startgap >3 h låser aldrig, fönstret 3 h, tvetydighet låser aldrig —
   allt testat.
2. **"Atomärt" klocklån motsade signalens beräkningsbas.** Signalnivån
   räknas per-fält i `_fotmob_signal` (FotMob-mål behålls); helparslånet
   kunde journalföra en annan ställning än signalen räknades på och ge
   motsägelsefulla facit-rader. **Omfix:** per-fält identiskt med
   signalbasen + `clock_source`/`clock_observed_at` som proveniens.
3. **Migrationens skärpning var själv ofullständig.** Ensidigt ÖPPEN marknad
   felmärktes som `suspended` (fabricerad stängningsobservation — M20-
   klassen); valideringen kollade bara kolumnnamn (en constraint-lös kopia
   bryter append-once tyst) och muterade DB:n INNAN den fällde. **Omfix:**
   `suspended` kräver observerad stängning; UNIQUE-vakten valideras;
   valideringen körs före mutation — alla tre testade.

## Verifiering efter åtgärd

- **390 backendtester gröna** (27 nya regressionstester).
- Frontend-build grön; Labb verifierad i browser (desktop + 375 px:
  ingen sidscroll, inga konsolfel) mot produktions-API.
- Migration körd mot prod: backup
  `stryktips-2026-08-01-fore-live-signal-clock-source.db`, 44/13 kolumner,
  `integrity_check=ok`, nattens rad intakt.
- Backend omstartad på 8002; `/api/oddset/radar-facit` svarar korrekt
  (mode=shadow, gate collecting 0/200 · 0/60).

## Läget i serien

Första skarpa signalen bokfördes i natt (01:02Z, av 38a45ff-koden): MLS,
New York City FC–Toronto FC, minut 57, 1–1, Följer·xG, prissatt Ö 3,5 @ 2,30,
kanonisk nyckel `pin:1632638189`, osettlad. Raden är frisk men dess pris
observerades FÖRE suspension-vakten — förbehållet gäller exakt denna rad
(`clock_source=NULL` markerar även "före 2026-08-01"). Ingen städning behövs;
settlingen sker med den fixade koden.

## Kvarstående medvetna begränsningar (inga dolda)

- 15-minutersutfallet kan fortfarande bara bevisas av captures som täcker
  fönstret — FT-totalen kan inte tidsbestämma målen. Ärlig censur, redovisas
  i facitet.
- Nyckellåsets lagfallback: kvarvarande dubblettrisk är cross-provider-flip
  där BÅDA korten saknar start_at och laguppslaget är tvetydigt eller
  dubbelmötet ligger inom 3 h — bedöms försumbart och felriktningen är då
  dubblering (syns i journalen), inte tyst bortfall.
- Klockfältens lån journalförs med källa och observationstid, men radens
  `captured_at` förblir statistikkällans tid — det är avsiktligt
  (xG-måtten ÄR från den tiden) och nu rekonstruerbart ur raden.
- En omdöpt Kambi-etikett/borttagen tagg ger `not_offered` (rå payload
  sparas inte). Veckokontrollen av statusfördelningen (överlämningens
  punkt 1) är fortsatt rätt vakt: en abrupt spik i
  `suspended`/`not_offered` ska utredas som transportfel innan den tolkas
  som marknadsbeteende.
