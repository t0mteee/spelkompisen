"""Additiv migration för live-signalens fler-källors prisobservationer.

Körning i produktion (innan ny backendkod startas):
    cd backend && .venv/bin/python -B scripts/migrera_live_signal_quotes.py

Tabellen är append-only och börjar tom. Historiska priser bakfylls aldrig.
Skriptet tar en konsistent SQLite-backup före första schemaändringen och
validerar kolumner, primärnyckel, främmande nyckel och integritet.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-18-fore-live-signal-quotes.db")
TABLE = "oddset_live_signal_quote"
EXPECTED_COLUMNS = (
    "signal_id", "source", "provider_event_id", "observed_at", "checked_at",
    "status", "line", "over_odds", "under_odds", "selected", "age_s",
)
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    signal_id          INTEGER NOT NULL,
    source             TEXT NOT NULL,
    provider_event_id  TEXT,
    observed_at        TEXT,
    checked_at         TEXT NOT NULL,
    status             TEXT NOT NULL,
    line               REAL,
    over_odds          REAL,
    under_odds         REAL,
    selected           INTEGER NOT NULL DEFAULT 0,
    age_s              INTEGER,
    PRIMARY KEY (signal_id, source),
    FOREIGN KEY (signal_id) REFERENCES oddset_live_signal(id)
);
CREATE INDEX IF NOT EXISTS idx_live_signal_quote_source
    ON {TABLE} (source, status, checked_at);
"""


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


def _validate(conn: sqlite3.Connection) -> None:
    columns = tuple(row[1] for row in conn.execute(
        f"PRAGMA table_info({TABLE})"))
    if columns != EXPECTED_COLUMNS:
        raise RuntimeError(
            f"{TABLE} har oväntat schema: {columns} != {EXPECTED_COLUMNS}")
    pk = tuple(row[1] for row in sorted(
        (row for row in conn.execute(f"PRAGMA table_info({TABLE})") if row[5]),
        key=lambda row: row[5]))
    if pk != ("signal_id", "source"):
        raise RuntimeError(f"{TABLE} har oväntad primärnyckel: {pk}")
    fks = list(conn.execute(f"PRAGMA foreign_key_list({TABLE})"))
    if not any(row[2] == "oddset_live_signal" and row[3] == "signal_id"
               and row[4] == "id" for row in fks):
        raise RuntimeError(f"{TABLE} saknar främmande nyckel till signalen")


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        if existed:
            _validate(conn)
        conn.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
        _validate(conn)
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_keys:
            raise RuntimeError(
                f"databaskontroll föll: integrity={integrity}, fk={foreign_keys}")
        return {"created": not existed, "columns": list(EXPECTED_COLUMNS),
                "count": count, "integrity": integrity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"tabell {'skapad' if result['created'] else 'fanns redan'} · "
          f"{len(result['columns'])} kolumner · {result['count']} rader · "
          f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
