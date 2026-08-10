"""Idempotent migrering för poolens framåtriktade styrkemodell-shadow.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_pool_strength_shadow.py

Inga historiska sannolikheter bakfylls. Tabellen börjar tom och fylls endast
vid en verklig h24/h3/m20-observation med ett lyckat Pinnacle-svar.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import POOL_STRENGTH_SHADOW_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-10-fore-pool-strength-shadow.db")
TABLE = "pool_strength_shadow_capture"
EXPECTED_COLUMNS = (
    "product", "draw_number", "horizon", "event_number", "shadow_version",
    "model_signal_version", "captured_at", "target_at", "delay_min",
    "match_start", "league_raw", "league", "home", "away", "eligible",
    "issue", "p_sharp_1", "p_sharp_x", "p_sharp_2", "p_model_1",
    "p_model_x", "p_model_2", "p_blend10_1", "p_blend10_x",
    "p_blend10_2", "p_blend20_1", "p_blend20_x", "p_blend20_2",
)
EXPECTED_PK = ("product", "draw_number", "horizon", "event_number",
               "shadow_version")
PROTECTED_TABLES = ("snapshots", "sharp_snapshots", "pool_event_settlement",
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


def _shape(conn: sqlite3.Connection) -> tuple[tuple[str, ...], tuple[str, ...]]:
    info = conn.execute(f"PRAGMA table_info({TABLE})").fetchall()
    columns = tuple(row[1] for row in info)
    primary = tuple(row[1] for row in sorted(
        (row for row in info if row[5]), key=lambda row: row[5]))
    return columns, primary


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in PROTECTED_TABLES}


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        if existed:
            columns, primary = _shape(conn)
            if columns != EXPECTED_COLUMNS or primary != EXPECTED_PK:
                raise RuntimeError(
                    f"{TABLE} avviker före migration: "
                    f"kolumner={columns}, pk={primary}")
        before = _counts(conn)
        conn.executescript("BEGIN IMMEDIATE;\n" +
                           POOL_STRENGTH_SHADOW_SCHEMA + "\nCOMMIT;")
        columns, primary = _shape(conn)
        if columns != EXPECTED_COLUMNS or primary != EXPECTED_PK:
            raise RuntimeError(
                f"{TABLE} avviker efter migration: "
                f"kolumner={columns}, pk={primary}")
        after = _counts(conn)
        if after != before:
            raise RuntimeError(
                f"skyddade tabellantal ändrades: före={before}, efter={after}")
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        return {"created": not existed, "columns": len(columns), "count": count,
                "protected_counts": after, "integrity": integrity,
                "foreign_key_errors": len(foreign_keys)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"{TABLE}: {'skapad' if result['created'] else 'fanns redan'} · "
          f"{result['columns']} kolumner · {result['count']} rader")
    print(f"skyddade tabeller oförändrade: {result['protected_counts']}")
    print(f"integrity {result['integrity']} · "
          f"foreign_key_errors {result['foreign_key_errors']}")


if __name__ == "__main__":
    main()
