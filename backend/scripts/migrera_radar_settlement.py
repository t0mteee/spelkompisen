"""Idempotent migration för radarns ögonblicks-settlement (shadow-facit).

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_radar_settlement.py

Produktionskörningen tar först en konsistent SQLite-backup med backup-API:t.
Tabellen är append-once: settlade ögonblick skrivs aldrig om, och lagret läses
bara av `radar-facit` — aldrig av tips, Kelly, notiser, CLV eller modellinput.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import LIVE_RADAR_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / \
    "stryktips-2026-07-26-fore-radar-settlement.db"
TABLE = "oddset_live_moment_settlement"


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
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        conn.executescript("BEGIN IMMEDIATE;\n" + LIVE_RADAR_SCHEMA + "\nCOMMIT;")
        columns = [row[1] for row in conn.execute(
            f"PRAGMA table_info({TABLE})").fetchall()]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        return {"created": not existed, "columns": columns,
                "count": count, "integrity": integrity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"tabell {'skapad' if result['created'] else 'fanns redan'} · "
          f"{len(result['columns'])} kolumner · {result['count']} rader · "
          f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
