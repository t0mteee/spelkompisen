"""Idempotent V2-A-migration: immutabla point-in-time-featurecaptures.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_v2_features.py

Skriptet kräver en namngiven backup. Befintliga ledgercaptures rekonstrueras
efteråt men märks ``reconstructed`` och kan därför aldrig kvalificera outer-test.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import V2_FEATURE_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-17-fore-v2a.db"
TABLE = "oddset_v2_feature_capture"
# Endast featureversioner skapade lokalt under den ännu ocommittade V2-A-
# utvecklingen. De har aldrig lästs av appen eller använts som facit.
OBSOLETE_DEVELOPMENT_VERSIONS = ("f-f96ee90d", "f-97ea96d2", "f-ee0ef61f")


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        existed = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone() is not None
        conn.executescript("BEGIN IMMEDIATE;\n" + V2_FEATURE_SCHEMA + "\nCOMMIT;")
        marks = ",".join("?" for _ in OBSOLETE_DEVELOPMENT_VERSIONS)
        removed = conn.execute(
            f"DELETE FROM {TABLE} WHERE feature_version IN ({marks}) "
            "AND capture_mode='reconstructed'", OBSOLETE_DEVELOPMENT_VERSIONS
        ).rowcount
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"created": not existed, "removed_development": removed,
                "integrity": integrity,
                "rows": conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    result = migrate(DB)
    print(f"{'skapade' if result['created'] else 'redan klar'} {TABLE} · "
          f"rader {result['rows']} · rensade utvecklingsrader "
          f"{result['removed_development']} · integrity {result['integrity']}")


if __name__ == "__main__":
    main()
