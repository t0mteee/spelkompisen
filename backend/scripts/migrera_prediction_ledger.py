"""Idempotent WP5-migration: add the fixed-horizon prediction ledger.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_prediction_ledger.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import PREDICTION_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-16-fore-wp5.db"
TABLES = {
    "oddset_prediction_capture",
    "oddset_prediction_log",
    "oddset_prediction_group_state",
}


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.executescript("BEGIN IMMEDIATE;\n" + PREDICTION_SCHEMA + "\nCOMMIT;")
        after = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = TABLES - after
        if missing:
            raise RuntimeError(f"tabeller saknas efter migration: {sorted(missing)}")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"created": sorted(TABLES - before), "integrity": integrity,
                "captures": conn.execute(
                    "SELECT COUNT(*) FROM oddset_prediction_capture").fetchone()[0],
                "rows": conn.execute(
                    "SELECT COUNT(*) FROM oddset_prediction_log").fetchone()[0]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    result = migrate(DB)
    action = ("skapade " + ", ".join(result["created"])
              if result["created"] else "redan klar")
    print(f"{action} · captures {result['captures']} · rader {result['rows']} "
          f"· integrity {result['integrity']}")


if __name__ == "__main__":
    main()
