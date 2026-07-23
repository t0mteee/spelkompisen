"""Idempotent, additiv migration för V2.2:s isolerade shadowledger.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_v22_shadow.py

Produktionskörningen tar först en konsistent SQLite-backup med backup-API:t.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import V22_SHADOW_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-23-fore-v22-shadow.db"
SAFETY_BACKUP = (
    ROOT / "data" / "backups" /
    "stryktips-2026-07-23-fore-v22-tomtabell-stadning.db"
)
TABLE = "oddset_v22_shadow_capture"


def backup_database(source: Path | str, target: Path | str) -> bool:
    target = Path(target)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=10)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.execute("PRAGMA busy_timeout=10000")
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return True


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        conn.executescript("BEGIN IMMEDIATE;\n" + V22_SHADOW_SCHEMA + "\nCOMMIT;")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        return {"created": not existed, "rows": rows, "integrity": integrity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def remove_empty_precreated_table(db: Path | str) -> bool:
    """Städa en tom tabell som Storage-grundschemat hann skapa före migration.

    Funktionen vägrar röra tabellen om en enda shadowrad finns.
    """
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        if not exists:
            return False
        rows = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        if rows:
            raise RuntimeError(
                f"vägrar städa {TABLE}: tabellen innehåller {rows} rader")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"DROP TABLE {TABLE}")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    safety = backup_database(DB, SAFETY_BACKUP)
    cleaned = False
    if not BACKUP.exists():
        cleaned = remove_empty_precreated_table(DB)
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"säkerhetsbackup {'skapad' if safety else 'fanns redan'}: "
          f"{SAFETY_BACKUP.name}")
    print(f"tom förhandskopiad tabell {'städad' if cleaned else 'ej funnen/behölls'}")
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"{'skapade' if result['created'] else 'redan klar'} {TABLE} · "
          f"rader {result['rows']} · integrity {result['integrity']}")


if __name__ == "__main__":
    main()
