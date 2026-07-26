"""Idempotent migration för Matchbook-likviditetstabellen (ren skuggserie).

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_matchbook.py

Produktionskörningen tar först en konsistent SQLite-backup med backup-API:t.
Tabellen `oddset_matchbook_liquidity` bär Matchbooks tillgängliga back-
likviditet (EUR) per selektion i snabbfönstret — append-serie med monotonisk
seen_at (se MATCHBOOK_SCHEMA i app/storage.py). Lagret läses av inget
runtime-flöde: inga tips, notiser, CLV, steam eller modellinput — bara det
frysta shadow-facitet efter >= 28 dagar (docs/bookmaker-kallplan-2026-07-25.md).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import MATCHBOOK_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / \
    "stryktips-2026-07-27-fore-matchbook.db"
TABLE = "oddset_matchbook_liquidity"


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


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (TABLE,)).fetchone() is not None
        conn.executescript("BEGIN IMMEDIATE;\n" + MATCHBOOK_SCHEMA + "\nCOMMIT;")
        columns = [row[1] for row in conn.execute(
            f"PRAGMA table_info({TABLE})").fetchall()]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        count = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
        return {"created": not existed, "columns": columns,
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
