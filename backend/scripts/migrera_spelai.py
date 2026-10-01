"""Idempotent migrering: facitsidans tabeller för spel-ai-kompisen.

Körning (vid driftsättning, se docs/spelai-facit.md):
    cd backend && .venv/bin/python -B scripts/migrera_spelai.py [--db PATH]

1. Onlinebackup med SQLite:s backup-API (en gång per dag och databas).
2. `CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS` för alla `spelai_*` i EN
   transaktion — ingen befintlig tabell rörs (antalen kontrolleras före/efter).
3. `facit_start` skrivs i `spelai_state` FÖRSTA gången: fönster som öppnade
   före den markeras aldrig som missade.
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

from app.spelai import schema, tillstand  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
PROTECTED_TABLES = ("snapshots", "sharp_snapshots", "draws",
                    "pool_draw_settlement", "pool_event_settlement",
                    "pool_system_ledger")


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


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    out = {}
    for table in PROTECTED_TABLES:
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
        existed = [t for t in schema.TABLES if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (t,)).fetchone()]
        before = _counts(conn)
        schema.apply_schema(conn)
        if not schema.tables_exist(conn):
            raise RuntimeError("spelai-tabellerna saknas efter migreringen")
        after = _counts(conn)
        if after != before:
            raise RuntimeError(f"skyddade tabellantal ändrades: före={before}, "
                               f"efter={after}")
        start = tillstand.hamta(conn, tillstand.FACIT_START_KEY)
        start_written = False
        if start is None:
            tillstand.satt(conn, tillstand.FACIT_START_KEY, tillstand.iso(now),
                           source="migrera_spelai", now=now)
            start = tillstand.iso(now)
            start_written = True
        triggers = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
            "AND name LIKE 'trg_spelai_%'").fetchone()[0]
        check = (conn.execute("PRAGMA integrity_check").fetchone()[0]
                 if integrity else "hoppad")
        return {"created": [t for t in schema.TABLES if t not in existed],
                "existed": existed, "triggers": triggers,
                "facit_start": start, "facit_start_written": start_written,
                "protected_counts": after, "integrity": check,
                "schema_version": schema.SCHEMA_VERSION}
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
    target = backup_dir / f"{db.stem}-{today}-fore-spelai.db"
    if args.utan_backup:
        print("backup: HOPPAD (--utan-backup)")
    else:
        made = backup_database(db, target)
        print(f"backup {'skapad' if made else 'fanns redan'}: {target}")
    result = migrate(db)
    print(f"skapade tabeller: {', '.join(result['created']) or '—'}")
    print(f"fanns redan: {', '.join(result['existed']) or '—'}")
    print(f"append-only-triggrar: {result['triggers']}")
    print(f"facit_start: {result['facit_start']}"
          f"{' (skriven nu)' if result['facit_start_written'] else ' (fanns)'}")
    print(f"skyddade tabeller oförändrade: {result['protected_counts']}")
    print(f"integrity {result['integrity']} · {result['schema_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
