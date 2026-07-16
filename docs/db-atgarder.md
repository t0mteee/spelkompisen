# Databas-åtgärder (löpande logg)

**Processregel (granskningen runda 2, punkt 7):** varje manuell ändring av
`data/stryktips.db` sker via (1) backup i `backend/data/backups/`, (2) skript
eller dokumenterad SQL i repot, (3) post i denna fil. Ad-hoc-SQL utan spår är
förbjudet. Automatisk upptäckt av kända felmönster: `cli.py modeldata`
(identitets-audit: okopplade namn, datum-dubbletter med olika mål).

---

## 2026-07-16 — WP8 dagliga Elo-captures och PIT-historik

- **Skript:** `backend/scripts/migrera_elohistorik.py` (additivt schema,
  legacy endast när capture-tabellen är tom, idempotent) och
  `backend/scripts/backfill_elohistorik.py` (återupptagningsbar klubbbackfill;
  lyckat nätanrop krävs innan en klubb markeras klar).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp8-elo.db`
  (18 MB SQLite online-backup, `integrity_check = ok`, 0 Elo-tabeller före
  migrationen).
- **Vad:** `oddset_elo_capture` + `oddset_elo_rating` bevarar observerade
  dagrankingar och payload-hash. `oddset_elo_history` bevarar ClubElos
  inkluderande `From`/`To`-intervall; `get_elo(..., as_of=datum)` läser enbart
  intervallet som gällde den dagen. Meta-rankingen är kompatibilitetscache.
- **Migration:** befintlig meta-ranking → 1 legacy-capture + 32 ratings.
  Identisk omkörning 0/0. En verifieringskörning efter att meta flyttats hittade
  och rensade 1 sekundnära redundant legacy/daily-capture från en tidig
  skriptversion; nästa körning rensade 0 och skapade 0. Kvar: 1 legacy, 2
  backfill-ankare och 1 daily-capture (128 ratings totalt).
- **Backfill:** rankningar 2024-07-01, 2025-07-01 och 2026-07-16 gav 39 unika
  klubbar. Full klubbhistorik lyckades för 36; tillsammans med ankarintervallen
  finns 4 197 intervall för alla 39 klubbnycklar. KFUM Oslo, Odd Grenland och
  Sirius har bara 1–3 ankarintervall eftersom fulla endpoints timeoutade; deras
  `oddset_elo_backfill:*`-markörer saknas avsiktligt så nästa körning retryar.
- **Täckning:** med samma namnmatchning som modellen får 507/581 Allsvenskan-
  matcher och 483/587 Eliteserien-matcher båda lagens as-of-Elo. Superettan
  19/600 och OBOS 11/600 — ett dokumenterat skäl att inte behandla Elo som
  heltäckande feature i andradivisionerna. Slutlig `integrity_check = ok`.

## 2026-07-16 — WP8 tidsstämplad frånvarohistorik

- **Skript:** `backend/scripts/migrera_franvarohistorik.py` (idempotent,
  additiva tabeller/index, legacy-backfill utan påhittade identiteter).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp8-franvaro.db`
  (18 MB SQLite online-backup, `integrity_check = ok`, tagen innan tabellerna
  fanns och innan backenden startades med ny kod).
- **Vad:** `oddset_absence_capture` sparar varje lyckat lineup-svar, även tom
  frånvarolista, med match/event/tid/bekräftelsestatus och payload-hash.
  `oddset_absence_player` sparar sida, Sofascore player-ID, position, orsakskod,
  beskrivning/slutdatum samt säsongsmatcher/rating. Detta gör frånvaron point-in-
  time och möjlig att koppla till samma matchs oddshistorik.
- **Backfill:** 15 befintliga `meta oddset_abs:*` → 15 legacy-captures och 77
  spelarrader. Gamla payloads saknade ID/position; dessa lämnades NULL i stället
  för att fyllas med namnmatchade gissningar. Identisk omkörning gav 0/0.
- **Första livevarv:** 16 matcher kontrollerades, 14 hade lineup-svar och gav
  14 nya captures + 75 spelarrader; **75/75 hade både provider-ID och position**.
  Två källsvar saknades och skapade ingen falsk tom-observation. Totalt efter
  varvet: 29 captures, 152 spelarrader, 15 matcher; `integrity_check = ok`.
- **Källkorrigering:** råfälten verifierades mot Sofascore-lineups. Kod 0 =
  annat; 1 = skada; 11/12/13 = kortavstängningar (tidigare visades 11 felaktigt
  som "annat"). Rå `description` lagras också för framtida omklassning.

## 2026-07-16 — WP5 prediction ledger

- **Skript:** `backend/scripts/migrera_prediction_ledger.py` (idempotent,
  kräver backup; enbart additiva tabeller/index).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp5.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** skapade `oddset_prediction_capture`, `oddset_prediction_log` och
  `oddset_prediction_group_state`. Capture är unik per match × horisont × tier
  × semantisk kompositversion och skrivs även vid noll prediktionsrader;
  ledgerrader är immutabla point-in-time-observationer.
- **Migrering:** 0 gamla rader bakfylldes (avsiktligt — historiska odds kan inte
  göras om till äkta T−24h/T−3h/T−20m-snapshots),
  `PRAGMA integrity_check = ok`.
- **Kopietest före live:** 58 aktuella matcher gav 30 tier-captures och 220
  prediktioner (8 captures i 3h-bucket, 22 i 24h-bucket); identisk omkörning
  gav 0 captures/0 rader. Dessa kopierader är testdata och finns inte i
  produktionsdatabasen.
- **Första live-capture:** launchd skrev 30 tier-captures/220 prediktioner
  2026-07-16 13:30:07Z. Timingvakten godkände 4/13 3h-captures och 0/17
  bootstrap-24h-captures; sena rader finns kvar för coverage men kan inte
  kvalificera en grupp. 220/220 prediktionsidentiteter är unika.
- **Staging-race, metadata-only:** launchd hann köra fem minuter innan commit
  `4cd0bb0` skapades och `_code_version()` skrev därför föräldrahashen
  `6156f74`, trots att det exekverade WP5-trädet var exakt det staged träd som
  blev `4cd0bb0`. `backend/scripts/korrigera_wp5_githash.py` verifierar HEAD,
  diff på alla kärnfiler, exakt capture-tid och exakt 220 rader innan den ändrar
  enbart `git_hash`. Separat backup:
  `backend/data/backups/stryktips-2026-07-16-fore-wp5-githash.db`.
  Utfall: 220 rader `6156f74→4cd0bb0`, `integrity_check = ok`.

## 2026-07-16 — WP4 CLV-identitet och linjeflytt

- **Skript:** `backend/scripts/migrera_clv_identitet.py` (idempotent, kräver
  backup och recreatar tabellen atomärt).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp4.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** primärnyckeln byttes från `(match_id, market, sign)` till
  `(match_id, market, sign, line_key, model_version)`. `line_key` är
  `round(line×1000)`; marknader utan lina använder sentinel `2147483647`.
  Closing-facitet fick `closing_line`, `line_delta` och `line_move_score`, där
  positivt score betyder att marknaden rörde sig med selektionen.
- **Migrering:** 110→110 rader, 110 unika nya identiteter,
  `PRAGMA integrity_check = ok`. En tidigare censurerad Ö3,25-rad
  (Djurgården–Halmstad) öppnades för omkörning och klassades mot slutlinan
  3,50 som `linje flyttad`, delta/score `+0,25`; inget close-EV skapades eftersom
  exakt-line-priset inte var färskt nog.
- **Efterkontroll:** produktionen accepterade 41 nya version/lina-identiteter
  (totalt 151/151 unika rader) som den gamla nyckeln hade blockerat. Rapporten
  visar linjeflytten separat från de 16 jämförbara close-EV-raderna.

## 2026-07-16 — WP2 prisnärvaro och källhälsa

- **Skript:** `backend/scripts/migrera_prisnarvaro.py` (idempotent, kräver backup).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-wp2.db` (SQLite
  online-backup före schemaändringen).
- **Vad:** `oddset_odds` fick `last_seen_at` och `available`; befintliga 16 400
  rader backfillades konservativt med `last_seen_at=fetched_at`, `available=1`.
  Tabellen `oddset_source_health` skapades. Inga prisrader raderades eller
  skrevs om. `PRAGMA integrity_check = ok`, 0 NULL efter migrering.
- **Efterkontroll:** ett fullt live-varv gav 27 källhälsorader utan fel,
  349/349 aktuellt visade marknader färska och 72 nya prisförändringsrader
  (16 400→16 472). Notifiering var avstängd; 0 pushar.

## 2026-07-16 — Versionsmigration av signal-facitet

- **Skript:** `backend/scripts/migrera_signalversion.py` (idempotent, kräver backup).
- **Backup:** `backend/data/backups/stryktips-2026-07-16-fore-versionsmigration.db`.
- **Vad:** `model_version` bytte betydelse från git-hash till semantiskt
  signal-fingeravtryck (`s-`/`m-`-prefix per tier); git-hashen flyttades till nya
  kolumnen `git_hash`. Rader stämplade `5cfe78f` (43 st: 19 sharp → `s-c32b7065`,
  24 modell → `m-8bf25277`) loggades under exakt de parametrar dagens
  fingeravtryck beskriver (ingen algoritm-/parameter-/kalibrerings-/dataändring
  sedan ffc6d04) → infogade i nuvarande version utan regimblandning.
  66 rader med NULL (loggade före versionsstämpling OCH före identitetsfixen =
  annan dataregim) lämnades som legacy (`-`).

## 2026-07-13 — Sanering av straff-kontaminerade MLS-resultat

- **Upptäckt:** identitetsmergens målvakt (b11a7e8) flaggade Montreal–Atlanta
  som "olika mål — mergas ej"; skanning visade ett kluster av slutspelsrader
  där Sofascores `current`-score inkluderade straffläggning. **Rotorsaksfix:**
  `_ingest_event` läser nu `normaltime` (fallback `current`).
- **Backup:** `backend/data/backups/stryktips-2026-07-13-fore-sanering.db`
  (tagen som analys-kopia FÖRE åtgärden; flyttad hit 2026-07-16).
- **Urvalsregel:** sofa-rad med fd-motpart ±1 dygn och avvikande mål ⇒ rätta
  till fd (officiellt FT-resultat); utan fd-motpart men hg+ag ≥ 9 och datum
  okt–dec (MLS-slutspel) ⇒ radera (bevisligt straff-kontaminerad, facit saknas).
- **Berörda rader** (alla `league='mls'`, `source='sofa'`; PK = league+date+home+away):

| Åtgärd | date | home | away | före | efter |
|---|---|---|---|---|---|
| UPDATE | 2024-10-22 | montreal | atlanta united | 6-7 | 2-2 (fd 2024-10-23) |
| DELETE | 2024-10-29 | seattle sounders | houston dynamo | 5-4 | — |
| DELETE | 2024-10-30 | real salt lake | minnesota united | 4-5 | — |
| DELETE | 2024-11-03 | houston dynamo | seattle sounders | 7-8 | — |
| DELETE | 2024-11-03 | new york red bulls | columbus crew | 7-6 | — |
| DELETE | 2024-11-09 | cincinnati | new york city | 5-6 | — |
| DELETE | 2025-10-26 | philadelphia union | chicago fire | 6-4 | — |
| DELETE | 2025-11-01 | new york city | charlotte | 6-7 | — |
| DELETE | 2025-11-02 | portland timbers | san diego | 5-4 | — |
| DELETE | 2025-11-08 | minnesota united | seattle sounders | 10-9 | — |
| DELETE | 2025-11-23 | vancouver whitecaps | los angeles | 6-5 | — |

- **Reproducerbar SQL** (mot backupen ger exakt dagens läge):

```sql
UPDATE oddset_results SET hg=2, ag=2
 WHERE league='mls' AND source='sofa' AND date='2024-10-22'
   AND home='montreal' AND away='atlanta united';
DELETE FROM oddset_results
 WHERE league='mls' AND source='sofa' AND hg+ag>=9
   AND strftime('%m', date) IN ('10','11','12')
   AND (date, home, away) IN (VALUES
   ('2024-10-29','seattle sounders','houston dynamo'),
   ('2024-10-30','real salt lake','minnesota united'),
   ('2024-11-03','houston dynamo','seattle sounders'),
   ('2024-11-03','new york red bulls','columbus crew'),
   ('2024-11-09','cincinnati','new york city'),
   ('2025-10-26','philadelphia union','chicago fire'),
   ('2025-11-01','new york city','charlotte'),
   ('2025-11-02','portland timbers','san diego'),
   ('2025-11-08','minnesota united','seattle sounders'),
   ('2025-11-23','vancouver whitecaps','los angeles'));
```

- **Anmärkning (processavvikelse):** saneringen kördes 2026-07-13 som direkta
  SQL-satser i sessionen — skript/backup-i-repo fanns inte då. Denna fil +
  processregeln är åtgärden; framtida saneringar följer regeln från start.
- **Kvarvarande osäkerhet:** Superettan 2025-11-23 örebro–hammarby talang 7-4
  och Eliteserien 2025-11-30 kongsvinger–aalesunds 4-5 är kvalmatcher utan
  fd-motpart — kan inte verifieras, lämnade orörda (normaltime-fixen skyddar
  framåt).
