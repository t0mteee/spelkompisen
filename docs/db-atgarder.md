# Databas-åtgärder (löpande logg)

**Processregel (granskningen runda 2, punkt 7):** varje manuell ändring av
`data/stryktips.db` sker via (1) backup i `backend/data/backups/`, (2) skript
eller dokumenterad SQL i repot, (3) post i denna fil. Ad-hoc-SQL utan spår är
förbjudet. Automatisk upptäckt av kända felmönster: `cli.py modeldata`
(identitets-audit: okopplade namn, datum-dubbletter med olika mål).

---

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
