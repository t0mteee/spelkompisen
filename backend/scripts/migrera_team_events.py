"""Idempotent WP9c-migration för Sofascore-lag, arenor och alla tävlingar.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_team_events.py

Produktionskörningen tar först en konsistent SQLite-backup med backup-API:t.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import TEAM_EVENT_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-17-fore-wp9c.db"
TABLES = (
    "oddset_sofa_team", "oddset_sofa_team_scope",
    "oddset_sofa_team_event_capture", "oddset_sofa_team_event",
)
DEVELOPMENT_POLICY = "wp9c-6818e9c7"


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
        before = {name for name, in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.executescript("BEGIN IMMEDIATE;\n" + TEAM_EVENT_SCHEMA + "\nCOMMIT;")
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(oddset_sofa_team_event_capture)").fetchall()}
        added_columns = []
        if "policy_version" not in columns:
            conn.execute(
                "ALTER TABLE oddset_sofa_team_event_capture ADD COLUMN "
                f"policy_version TEXT NOT NULL DEFAULT '{DEVELOPMENT_POLICY}'")
            added_columns.append("policy_version")
            conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {table: conn.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in TABLES}
        return {"created": [table for table in TABLES if table not in before],
                "added_columns": added_columns,
                "counts": counts, "integrity": integrity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"skapade {result['created'] or 'inga nya tabeller'} · "
          f"kolumner {result['added_columns'] or 'inga'} · "
          f"rader {result['counts']} · integrity {result['integrity']}")


if __name__ == "__main__":
    main()
