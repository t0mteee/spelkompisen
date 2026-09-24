# Databasbackup

Beslut: Saman 2026-09-24 ("backup ja"). Före detta fanns inga schemalagda
kopior; de enda låg i `backend/data/backups/` från migreringar, på samma disk.

## Vad som körs

- **Jobb:** LaunchAgent `com.saman.spelkompisen.backup`
  (`backend/scripts/com.saman.spelkompisen.backup.plist`), varje natt 04:15
  lokal tid. Syns i `tools/tjanster.sh status` som `backup`.
- **Skript:** `backend/scripts/backup_db.py` (`db-backup-v1`).
  1. Onlinekopia med SQLites backup-API i ett steg. Aldrig filkopiering av en
     aktiv databas.
  2. `PRAGMA quick_check` på kopian. En kopia som inte är `ok` sparas inte.
  3. gzip och sha256. De 14 senaste dagskopiorna sparas i
     `~/Backups/spelkompisen/daily/`, var och en med en manifestfil.
  4. Den senaste kopian publiceras till det **privata** repot
     `t0mteee/spelkompisen-backup`, delad i delar på 45 MB. Repot skrivs om
     varje natt till en enda commit, så det växer inte.
- **Status:** `~/Backups/spelkompisen/status.json` (`ok` avser den lokala
  kopian, `pushed` publiceringen) och `backup.log` i samma katalog.

Lokala kopior skyddar mot en felaktig migrering eller ett misstag. Kopian på
GitHub skyddar mot diskfel och stöld. Storlek 2026-09-24: databasen cirka
810 MB, komprimerad cirka 150 MB.

## Regler

- Databasen innehåller spelade kuponger och insatser. Den får **aldrig**
  läggas i `spelkompisen`-repot, som är publikt. Skriptet vägrar publicera
  till något annat repo än `spelkompisen-backup` (`ALLOWED_REMOTES`).
- Databasen kontrollerades 2026-09-24 före första uppladdningen: inga
  nyckelmönster, inga lösenordskolumner och inget av värdena i
  `backend/.env`. Lägg aldrig hemligheter i databasen.
- Kör manuellt vid behov:
  `cd backend && .venv/bin/python -B scripts/backup_db.py`
  (`--no-push` för bara lokal kopia).

## Återställa

Ur GitHub (klona repot) eller ur `~/Backups/spelkompisen/daily/`:

```sh
cat stryktips-*.db.gz.part-* > stryktips.db.gz   # bara för GitHub-delarna
shasum -a 256 stryktips.db.gz                    # jämför med manifestet
gunzip stryktips.db.gz
sqlite3 stryktips.db "PRAGMA integrity_check"
```

En återställning till produktion är en DB-åtgärd: stoppa insamlingen med
`tools/tjanster.sh stopp snapshot pool`, ta en `.backup` av den nuvarande
databasen, byt fil, starta tjänsterna och bokför åtgärden i
`docs/db-atgarder.md`. Tänk på att allt som samlats efter kopians tid saknas
och aldrig får bakfyllas.
