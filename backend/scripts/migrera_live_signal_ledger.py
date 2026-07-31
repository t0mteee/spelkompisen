"""Idempotent migration för live-radarns signal- och resultatledger.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_live_signal_ledger.py

Produktionskörningen tar en konsistent SQLite-backup före schemaändringen.
Inga historiska liveodds bakfylls: tabellerna börjar samla framåt först när
migrationen är klar.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import LIVE_RADAR_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-07-31-fore-live-signal-ledger.db")
TABLES = ("oddset_live_signal", "oddset_live_signal_result")


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
        before = {table: conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone() is not None for table in TABLES}
        conn.executescript("BEGIN IMMEDIATE;\n" + LIVE_RADAR_SCHEMA + "\nCOMMIT;")
        tables = {}
        for table in TABLES:
            columns = [row[1] for row in conn.execute(
                f"PRAGMA table_info({table})").fetchall()]
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            tables[table] = {"created": not before[table],
                             "columns": columns, "count": count}
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"tables": tables, "integrity": integrity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    for table, info in result["tables"].items():
        print(f"{table}: {'skapad' if info['created'] else 'fanns redan'} · "
              f"{len(info['columns'])} kolumner · {info['count']} rader")
    print(f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
