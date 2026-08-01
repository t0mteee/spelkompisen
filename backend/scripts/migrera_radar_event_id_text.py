"""Migrera live-radarns moment-id från INTEGER-affinitet till TEXT.

Flashscores event-id är alfanumeriska. Alla provider-id:n behandlas därför som
ogenomskinliga strängar även när Sofascore och FotMob råkar använda siffror.
Migrationen bygger om enbart ``oddset_live_moment_settlement``, bevarar varje
append-only-rad och validerar schema, primärnyckel, radantal, FK och integritet
innan transaktionen får committa.

Produktionskörning (efter stoppad backend och verifierad DB-sökväg)::

    cd backend
    .venv/bin/python -B scripts/migrera_radar_event_id_text.py

Skriptet tar en konsistent SQLite-backup före förändringen och är idempotent.
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
          "stryktips-2026-08-01-fore-radar-event-id-text.db")
TABLE = "oddset_live_moment_settlement"
INDEX = "idx_live_moment_settlement_facit"
COLUMNS = Storage.LIVE_SETTLEMENT_COLUMNS
PRIMARY_KEY = ("provider", "event_id", "captured_at", "capture_version")


def backup_database(source: Path | str, target: Path | str) -> bool:
    """Ta en konsistent backup en gång; skriv aldrig över ett tidigare kvitto."""
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


def _ddl(name: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {name} ("
    start = LIVE_RADAR_SCHEMA.index(marker)
    end = LIVE_RADAR_SCHEMA.index("\n);", start) + len("\n);")
    return LIVE_RADAR_SCHEMA[start:end]


def _table_info(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({TABLE})").fetchall()


def _validate(conn: sqlite3.Connection, expected_count: int) -> dict:
    info = _table_info(conn)
    columns = {row[1]: (row[2] or "").upper() for row in info}
    if set(columns) != set(COLUMNS):
        raise RuntimeError(
            f"{TABLE} kolumner avviker: saknar "
            f"{sorted(set(COLUMNS) - set(columns)) or '–'} · extra "
            f"{sorted(set(columns) - set(COLUMNS)) or '–'}")
    if columns.get("event_id") != "TEXT":
        raise RuntimeError(
            f"event_id har typen {columns.get('event_id')!r}, väntade TEXT")
    primary_key = tuple(row[1] for row in sorted(
        (row for row in info if row[5]), key=lambda row: row[5]))
    if primary_key != PRIMARY_KEY:
        raise RuntimeError(
            f"primärnyckeln avviker: {primary_key!r} != {PRIMARY_KEY!r}")
    count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    if count != expected_count:
        raise RuntimeError(
            f"radantal ändrades vid ombyggnad: {expected_count} → {count}")
    index = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (INDEX,)).fetchone()
    if not index:
        raise RuntimeError(f"index saknas efter migration: {INDEX}")
    foreign_key_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            f"foreign_key_check gav {len(foreign_key_errors)} fel")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"integrity_check: {integrity}")
    return {"columns": columns, "primary_key": primary_key,
            "count": count, "integrity": integrity,
            "foreign_key_errors": 0}


def migrate(db: Path | str) -> dict:
    """Skapa eller bygg om tabellen atomärt; en andra körning gör inget."""
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        before = (conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
                  if exists else 0)
        old_columns = ({row[1]: (row[2] or "").upper()
                        for row in _table_info(conn)} if exists else {})
        if exists and set(old_columns) != set(COLUMNS):
            raise RuntimeError(
                f"vägrar bygga om oväntat schema i {TABLE}: "
                f"{sorted(old_columns)}")
        rebuilt = exists and old_columns.get("event_id") != "TEXT"

        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            if not exists:
                conn.execute(_ddl(TABLE))
            elif rebuilt:
                conn.execute(f"DROP INDEX IF EXISTS {INDEX}")
                conn.execute(
                    f"ALTER TABLE {TABLE} RENAME TO {TABLE}_integer_gammal")
                conn.execute(_ddl(TABLE))
                names = ",".join(COLUMNS)
                selected = ",".join(
                    "CAST(event_id AS TEXT)" if name == "event_id" else name
                    for name in COLUMNS)
                conn.execute(
                    f"INSERT INTO {TABLE}({names}) SELECT {selected} "
                    f"FROM {TABLE}_integer_gammal")
                conn.execute(f"DROP TABLE {TABLE}_integer_gammal")
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} "
                "(signal_type, signal, league)")
            validation = _validate(conn, before)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.execute("PRAGMA legacy_alter_table=OFF")
        return {"created": not exists, "rebuilt": rebuilt, **validation}
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"{TABLE}: "
          f"{'skapad' if result['created'] else 'ombyggd' if result['rebuilt'] else 'redan TEXT'}"
          f" · {result['count']} rader · PK {'/'.join(result['primary_key'])}"
          f" · FK-fel {result['foreign_key_errors']}"
          f" · integrity {result['integrity']}")


if __name__ == "__main__":
    main()
