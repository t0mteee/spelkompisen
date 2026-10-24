"""Idempotent migrering: ATG-insamlingens tabeller (Big 9 och SP96).

Beslut driften-2026-10-24-big9-atg (val 0). Körning:
    cd backend && .venv/bin/python -B scripts/migrera_atg.py [--db PATH]

1. Onlinebackup med SQLite:s backup-API (en gång per dag och databas).
2. `CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS` för `atg_offering_capture` och
   `atg_round_observation` i EN transaktion — ingen befintlig tabell rörs
   (antalen kontrolleras före/efter).
3. `facit_start_big9` skrivs i `spelai_state` FÖRSTA gången (när
   facitsidans tabeller finns): Big 9-fönster som öppnade före den markeras
   aldrig som missade.
Rapporten hör hemma i docs/db-atgarder.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import atg  # noqa: E402
from app.spelai import big9, schema as spelai_schema, tillstand  # noqa: E402
from scripts.migrera_spelai import PROTECTED_TABLES, backup_database  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
COUNTED = (*PROTECTED_TABLES, "spelai_input", "spelai_pool_proposal")


def _counts(conn: sqlite3.Connection) -> dict:
    out = {}
    for table in COUNTED:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name=?", (table,)).fetchone()
        out[table] = (conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      if exists else None)
    return out


def migrate(db: Path | str, *, now: dt.datetime | None = None,
            integrity: bool = True) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = [t for t in atg.TABLES if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (t,)).fetchone()]
        before = _counts(conn)
        atg.apply_schema(conn)
        if not atg.tables_exist(conn):
            raise RuntimeError("atg-tabellerna saknas efter migreringen")
        after = _counts(conn)
        if after != before:
            raise RuntimeError(f"skyddade tabellantal ändrades: före={before}, "
                               f"efter={after}")
        start, written = None, False
        if spelai_schema.tables_exist(conn):
            start = tillstand.hamta(conn, big9.START_KEY)
            if start is None:
                tillstand.satt(conn, big9.START_KEY, tillstand.iso(now),
                               source="migrera_atg", now=now)
                start, written = tillstand.iso(now), True
        triggers = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'trg_atg_%'").fetchone()[0]
        check = (conn.execute("PRAGMA integrity_check").fetchone()[0]
                 if integrity else "hoppad")
        return {"created": [t for t in atg.TABLES if t not in existed],
                "existed": existed, "triggers": triggers,
                "facit_start_big9": start, "facit_start_written": written,
                "protected_counts": after, "integrity": check}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DB), help="databas (default: produktion)")
    parser.add_argument("--backup-dir", default=None,
                        help="katalog för backupen (default: <db-katalog>/backups)")
    parser.add_argument("--utan-backup", action="store_true",
                        help="ENDAST för temporära kopior och tester")
    args = parser.parse_args(argv)
    db = Path(args.db)
    if not db.exists():
        print(f"databasen finns inte: {db}")
        return 2
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    backup_dir = Path(args.backup_dir) if args.backup_dir else db.parent / "backups"
    target = backup_dir / f"{db.stem}-{today}-fore-atg.db"
    if args.utan_backup:
        print("backup: HOPPAD (--utan-backup)")
    else:
        made = backup_database(db, target)
        print(f"backup {'skapad' if made else 'fanns redan'}: {target}")
    result = migrate(db)
    print(f"skapade tabeller: {', '.join(result['created']) or '—'}")
    print(f"fanns redan: {', '.join(result['existed']) or '—'}")
    print(f"append-only-triggrar: {result['triggers']}")
    print(f"facit_start_big9: {result['facit_start_big9']}"
          f"{' (skriven nu)' if result['facit_start_written'] else ''}")
    print(f"skyddade tabeller oförändrade: {result['protected_counts']}")
    print(f"integrity {result['integrity']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
