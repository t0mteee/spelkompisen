"""PH2/PH3 v2-migration: presence-ledger, jackpotproveniens och korrekt facit.

Additiv och idempotent. Befintliga pit-v1-rader rörs inte; de får aldrig
omtolkas som presence-bekräftade. Skriptet tar SQLite-backup före första
ändringen och verifierar schema + integrity_check.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_pool_capture_v2.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / \
    "stryktips-2026-07-24-fore-pool-capture-v2.db"


def backup_database(source: Path, target: Path) -> bool:
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


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _add(conn: sqlite3.Connection, table: str, definition: str) -> bool:
    name = definition.split()[0]
    if name in _columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
    return True


def main() -> None:
    if not DB.exists():
        sys.exit(f"AVBRYTER: {DB} saknas.")
    fresh = backup_database(DB, BACKUP)
    print(f"backup: {BACKUP.name} ({'skapad' if fresh else 'fanns redan'})")

    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("pool_draw_snapshot", "pool_pit_draw_features",
                          "pool_pit_match_features", "pool_system_ledger")
        }
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pool_market_capture (
                    product         TEXT NOT NULL,
                    draw_number     INTEGER NOT NULL,
                    source          TEXT NOT NULL
                                      CHECK (source IN ('svs', 'sharp')),
                    event_number    INTEGER NOT NULL,
                    fetched_at      TEXT NOT NULL,
                    status          TEXT NOT NULL,
                    odds_complete   INTEGER NOT NULL,
                    streck_complete INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY
                      (product, draw_number, source, event_number, fetched_at)
                );
                CREATE INDEX IF NOT EXISTS idx_pool_market_capture_asof
                    ON pool_market_capture
                       (product, draw_number, source, event_number,
                        fetched_at DESC);
            """)
            changes = [
                ("pool_draw_snapshot",
                 "jackpot_source TEXT NOT NULL DEFAULT 'legacy_unverified'"),
                ("pool_pit_draw_features", "timing_policy TEXT"),
                ("pool_pit_match_features",
                 "svs_eligible INTEGER NOT NULL DEFAULT 0"),
                ("pool_pit_match_features",
                 "sharp_eligible INTEGER NOT NULL DEFAULT 0"),
                ("pool_system_ledger",
                 "jackpot_source TEXT NOT NULL DEFAULT 'legacy_unverified'"),
                ("pool_system_ledger", "published_payout_kr REAL"),
                ("pool_system_ledger", "payout_complete INTEGER"),
                ("pool_system_ledger", "settlement_version TEXT"),
            ]
            added = [f"{table}.{definition.split()[0]}"
                     for table, definition in changes
                     if _add(conn, table, definition)]

        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in before
        }
        if before != after:
            sys.exit(f"AVBRYTER: migration ändrade befintliga radantal: "
                     f"{before} -> {after}")
        required = {
            "pool_draw_snapshot": {"jackpot_source"},
            "pool_pit_draw_features": {"timing_policy"},
            "pool_pit_match_features": {"svs_eligible", "sharp_eligible"},
            "pool_system_ledger": {
                "jackpot_source", "published_payout_kr",
                "payout_complete", "settlement_version",
            },
        }
        for table, columns in required.items():
            missing = columns - _columns(conn, table)
            if missing:
                sys.exit(f"AVBRYTER: {table} saknar {sorted(missing)}")
        print("tillägg:", ", ".join(added) if added else "inga (redan migrerad)")
        print("pool_market_capture:",
              conn.execute("SELECT COUNT(*) FROM pool_market_capture").fetchone()[0],
              "rader")
        print("befintliga radantal oförändrade:", after)
        print("integrity_check:",
              conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
