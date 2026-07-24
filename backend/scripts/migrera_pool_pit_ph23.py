"""PH2/PH3-migration 2026-07-24: PIT-dataset- och systemledger-tabeller.

Fyra nya tabeller (pool_draw_snapshot, pool_pit_draw_features,
pool_pit_match_features, pool_system_ledger). Ingen befintlig tabell rörs;
ingen data skrivs här. Dataset-helsvepet görs av scripts/bygg_pit_dataset.py;
frysning/settling sker löpande i snapshotvarvet.

Körning (idempotent):
    cd backend && .venv/bin/python -B scripts/migrera_pool_pit_ph23.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-24-fore-ph23-pit.db"
TABLES = ("pool_draw_snapshot", "pool_pit_draw_features",
          "pool_pit_match_features", "pool_system_ledger")


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


def main() -> None:
    if not DB.exists():
        sys.exit(f"AVBRYTER: {DB} saknas.")
    fresh = backup_database(DB, BACKUP)
    print(f"backup: {BACKUP.name} ({'skapad' if fresh else 'fanns redan'})")
    from app.storage import Storage   # noqa: E402 — skapar tabellerna
    store = Storage()
    try:
        existing = {name for (name,) in store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        missing = [t for t in TABLES if t not in existing]
        if missing:
            sys.exit(f"AVBRYTER: tabeller saknas efter migration: {missing}")
        for t in TABLES:
            n = store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} rader")
        print("integrity_check:",
              store.conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        store.close()


if __name__ == "__main__":
    main()
