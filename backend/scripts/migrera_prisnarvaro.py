"""Idempotent WP2-migration: prisbekräftelse, availability och källhälsa.

Körning:
    cd backend && .venv/bin/python scripts/migrera_prisnarvaro.py

Kräver den namngivna backupen. Migrationen raderar eller skriver aldrig om
prishistorik: befintliga rader får last_seen_at=fetched_at och available=1.
Nästa lyckade källvarv uppdaterar den verkliga bekräftelsetiden/statusen.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-16-fore-wp2.db"


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(oddset_odds)")}


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = conn.execute("SELECT COUNT(*) FROM oddset_odds").fetchone()[0]
        cols = _columns(conn)
        if "last_seen_at" not in cols:
            conn.execute("ALTER TABLE oddset_odds ADD COLUMN last_seen_at TEXT")
        if "available" not in cols:
            conn.execute(
                "ALTER TABLE oddset_odds ADD COLUMN available INTEGER NOT NULL DEFAULT 1")
        backfilled = conn.execute(
            "UPDATE oddset_odds SET last_seen_at=fetched_at WHERE last_seen_at IS NULL"
        ).rowcount
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oddset_source_health (
                source TEXT NOT NULL, league TEXT NOT NULL, scope TEXT NOT NULL,
                checked_at TEXT NOT NULL, ok INTEGER NOT NULL,
                event_count INTEGER NOT NULL DEFAULT 0, error TEXT,
                PRIMARY KEY (source, league, scope)
            )
        """)
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM oddset_odds").fetchone()[0]
        null_seen = conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE last_seen_at IS NULL").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"oddsrader {before}→{after} · backfill {backfilled} · "
              f"NULL last_seen_at {null_seen} · integrity {integrity}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
