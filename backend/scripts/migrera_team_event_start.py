"""Idempotent migration: PIT-förändringsserie för lagmatchers avsparkstid.

Granskningsfix F5a (2026-07-26): `oddset_sofa_team_event`-upserten skriver över
`start_at` vid ombokning, så `oddset_sofa_team_fixtures_as_of` läste DAGENS tid
för historiska `as_of`. Serien `oddset_sofa_team_event_start` bevarar tiden som
den var känd vid varje observationsögonblick.

Seedningen sätter seen_at = first_seen_at för befintliga rader. Det är den
ärligaste möjliga starten: ombokningar som skett FÖRE denna migration kan inte
återskapas — för dem gäller nuvarande tid från first_seen_at, och det står här.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_team_event_start.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-26-fore-event-start-serie.db"


def backup_database(source: Path | str, target: Path | str) -> bool:
    target = Path(target)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source, timeout=10)
    dst = sqlite3.connect(target)
    try:
        src.execute("PRAGMA busy_timeout=10000")
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return True


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS oddset_sofa_team_event_start ("
            "event_id INTEGER NOT NULL, start_at TEXT NOT NULL, "
            "seen_at TEXT NOT NULL, PRIMARY KEY (event_id, seen_at))")
        cur = conn.execute(
            "INSERT OR IGNORE INTO oddset_sofa_team_event_start("
            "event_id, start_at, seen_at) "
            "SELECT event_id, start_at, first_seen_at "
            "FROM oddset_sofa_team_event WHERE event_id NOT IN "
            "(SELECT event_id FROM oddset_sofa_team_event_start)")
        conn.commit()
        total = conn.execute(
            "SELECT COUNT(*) FROM oddset_sofa_team_event_start").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"seeded": cur.rowcount, "total": total, "integrity": integrity}
    finally:
        conn.close()


if __name__ == "__main__":
    backed_up = backup_database(DB, BACKUP)
    report = migrate(DB)
    print(f"backup: {'skapad' if backed_up else 'fanns redan'} -> {BACKUP.name}")
    print(f"seedade rader: {report['seeded']}  totalt: {report['total']}  "
          f"integritet: {report['integrity']}")
