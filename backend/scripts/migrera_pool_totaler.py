"""Lägg till poolens point-in-time Pinnacle-totaler med onlinebackup.

Additiv och idempotent migrering. Inga historiska totaler bakfylls: tabellen
börjar beskriva verkliga observationer först efter driftsättningen.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "stryktips.db"
DEFAULT_BACKUP = (
    ROOT / "data" / "backups"
    / "stryktips-2026-08-31-fore-pool-totaler.db"
)


def backup_database(source: Path, target: Path) -> bool:
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=30)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.execute("PRAGMA busy_timeout=30000")
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return True


def migrate(db: Path, backup: Path) -> dict:
    created_backup = backup_database(db, backup)
    conn = sqlite3.connect(db, timeout=30)
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(sharp_odds)")}
        added = []
        for name in ("total_line", "over_odds", "under_odds"):
            if name not in columns:
                conn.execute(f"ALTER TABLE sharp_odds ADD COLUMN {name} REAL")
                added.append(name)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sharp_total_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                draw_number INTEGER NOT NULL,
                event_number INTEGER NOT NULL,
                line REAL NOT NULL,
                over_odds REAL,
                under_odds REAL,
                fetched_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sharptotal_lookup
                ON sharp_total_snapshots (
                    product, draw_number, event_number, fetched_at);
        """)
        conn.commit()
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(f"integrity_check: {check}")
        rows = conn.execute(
            "SELECT COUNT(*) FROM sharp_total_snapshots").fetchone()[0]
        return {
            "backup_created": created_backup,
            "backup": str(backup),
            "columns_added": added,
            "historical_rows_backfilled": 0,
            "total_snapshot_rows": int(rows),
            "integrity_check": check,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup", type=Path, default=DEFAULT_BACKUP)
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error(f"databasen saknas: {args.db}")
    print(migrate(args.db.resolve(), args.backup.resolve()))


if __name__ == "__main__":
    main()
