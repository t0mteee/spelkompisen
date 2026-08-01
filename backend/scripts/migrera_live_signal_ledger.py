"""Idempotent migration för live-radarns signal- och resultatledger.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_live_signal_ledger.py

Produktionskörningen tar en konsistent SQLite-backup före schemaändringen.
Inga historiska liveodds bakfylls: tabellerna börjar samla framåt först när
migrationen är klar.

Historik:
* 2026-07-31 grundschema (42/13 kolumner), backup
  ``stryktips-2026-07-31-fore-live-signal-ledger.db``.
* 2026-08-01 additiva kolumner ``clock_source`` + ``clock_observed_at``
  (klockproveniens) och skärpt validering: (1) valideringen körs FÖRE någon
  mutation — en avvikande befintlig tabell fällde tidigare migrationen först
  efter att schema/ALTER redan committats; (2) utöver kolumnnamnen valideras
  att UNIQUE-vakten (match_key × signal_version × signal_type × signal_level)
  faktiskt finns — utan den är append-once-kontraktet tyst brutet.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import LIVE_RADAR_SCHEMA, Storage  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-01-fore-live-signal-clock-source.db")
# Samma additiva lista som Storage.__init__ kör — hålls i synk så att en DB
# som bara migrerats via skriptet får identiskt schema med en serverstartad.
ALTERS = ("ALTER TABLE oddset_live_signal ADD COLUMN clock_source TEXT",
          "ALTER TABLE oddset_live_signal ADD COLUMN clock_observed_at TEXT")
ADDITIVE = frozenset({"clock_source", "clock_observed_at"})
EXPECTED = {
    "oddset_live_signal": frozenset(("id",) + Storage.LIVE_SIGNAL_COLUMNS),
    "oddset_live_signal_result": frozenset(Storage.LIVE_SIGNAL_RESULT_COLUMNS),
}
UNIQUE_GUARD = ("oddset_live_signal",
                ("match_key", "signal_version", "signal_type", "signal_level"))


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


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(
        f"PRAGMA table_info({table})").fetchall()]


def _has_unique_guard(conn: sqlite3.Connection) -> bool:
    table, guard_columns = UNIQUE_GUARD
    for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
        if not index[2]:  # kolumn "unique"
            continue
        columns = tuple(row[2] for row in conn.execute(
            f"PRAGMA index_info({index[1]})").fetchall())
        if columns == guard_columns:
            return True
    return False


def _validate(conn: sqlite3.Connection, *, allow_missing_additive: bool) -> None:
    """Fäll hellre migrationen än låt drift tappa signaler mot fel schema.

    Körs FÖRE mutation (befintliga tabeller får avvika endast med de kända
    additiva kolumnerna) och EFTER (exakt likhet + UNIQUE-vakt)."""
    for table, expected in EXPECTED.items():
        columns = set(_columns(conn, table))
        if not columns:
            continue  # tabellen saknas — skapas av schemat
        missing = expected - columns
        extra = columns - expected
        if extra or (missing and not (
                allow_missing_additive and missing <= ADDITIVE)):
            raise RuntimeError(
                f"{table} avviker från Storage-schemat: "
                f"saknar {sorted(missing) or '–'} · extra {sorted(extra) or '–'}")
        if table == UNIQUE_GUARD[0] and not _has_unique_guard(conn):
            raise RuntimeError(
                f"{table} saknar UNIQUE-vakten {UNIQUE_GUARD[1]} — "
                "append-once-kontraktet vore tyst brutet")


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = {table: conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone() is not None for table in EXPECTED}
        # Validera INNAN någon mutation — en fälld migration får inte lämna
        # DB:n halvmigrerad.
        _validate(conn, allow_missing_additive=True)
        conn.executescript("BEGIN IMMEDIATE;\n" + LIVE_RADAR_SCHEMA + "\nCOMMIT;")
        for statement in ALTERS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # kolumnen finns redan (ny DB eller redan migrerad)
        conn.commit()
        _validate(conn, allow_missing_additive=False)
        tables = {}
        for table in EXPECTED:
            columns = _columns(conn, table)
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
