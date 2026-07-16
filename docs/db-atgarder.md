# Databas-åtgärder (löpande logg)

**Processregel (granskningen runda 2, punkt 7):** varje manuell ändring av
`data/stryktips.db` sker via (1) backup i `backend/data/backups/`, (2) skript
eller dokumenterad SQL i repot, (3) post i denna fil. Ad-hoc-SQL utan spår är
förbjudet. Automatisk upptäckt av kända felmönster: `cli.py modeldata`
(identitets-audit: okopplade namn, datum-dubbletter med olika mål).

---

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
