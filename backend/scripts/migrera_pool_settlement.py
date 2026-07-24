"""PH1-migration 2026-07-24: skapa immutable settlementlager för poolspelen.

Fyra nya tabeller (pool_draw_settlement, pool_event_settlement,
pool_payout_tier, pool_backfill_log) enligt granskade förslaget i
docs/ph1-settlement-schema-forslag-2026-07-24.md. Ingen befintlig tabell
eller data rörs; ingen data skrivs här (backfillen är ett separat skript).

Körning (idempotent):
    cd backend && .venv/bin/python -B scripts/migrera_pool_settlement.py
Tar först en konsistent SQLite-backup med backup-API:t.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-24-fore-ph1-settlement.db"
TABLES = ("pool_draw_settlement", "pool_event_settlement",
          "pool_payout_tier", "pool_backfill_log")


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

    from app.storage import Storage   # noqa: E402 — skapar tabellerna vid öppning
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
        ok = store.conn.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"integrity_check: {ok}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
