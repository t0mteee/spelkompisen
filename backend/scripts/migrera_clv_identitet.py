"""Idempotent WP4-migration av Oddset-facitets identitet.

Ny identitet: (match_id, market, sign, line_key, model_version). Därmed kan
samma selektion loggas på flera linor och under flera signalversioner utan att
första raden eller best-edge blandas ihop.

Körning:
    cd backend && .venv/bin/python scripts/migrera_clv_identitet.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-16-fore-wp4.db"
NO_LINE_KEY = 2_147_483_647
TARGET_PK = ["match_id", "market", "sign", "line_key", "model_version"]

DDL = """
CREATE TABLE oddset_value_log_v2 (
    match_id TEXT NOT NULL, market TEXT NOT NULL, sign TEXT NOT NULL,
    line REAL, line_key INTEGER NOT NULL, league TEXT, description TEXT,
    match_start TEXT, first_at TEXT, first_odds REAL, first_fair REAL,
    first_edge REAL, best_edge REAL, best_at TEXT, closing_fair REAL,
    closing_odds REAL, closing_line REAL, line_delta REAL,
    line_move_score REAL, closing_note TEXT, book TEXT,
    tier TEXT DEFAULT 'sharp', model_version TEXT NOT NULL DEFAULT 'legacy',
    git_hash TEXT,
    PRIMARY KEY (match_id, market, sign, line_key, model_version)
)
"""


def _pk(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("PRAGMA table_info(oddset_value_log)").fetchall()
    return [r[1] for r in sorted((r for r in rows if r[5]), key=lambda r: r[5])]


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = conn.execute("SELECT COUNT(*) FROM oddset_value_log").fetchone()[0]
        if _pk(conn) == TARGET_PK:
            return {"before": before, "after": before, "reset_line_moved": 0,
                    "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
                    "changed": False}
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(oddset_value_log)").fetchall()}
        reset = conn.execute(
            "SELECT COUNT(*) FROM oddset_value_log WHERE closing_note='linje flyttad'"
        ).fetchone()[0]
        closing_line = "closing_line" if "closing_line" in cols else "NULL"
        line_delta = "line_delta" if "line_delta" in cols else "NULL"
        move_score = "line_move_score" if "line_move_score" in cols else "NULL"
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DROP TABLE IF EXISTS oddset_value_log_v2")
        conn.execute(DDL)
        conn.execute(f"""
            INSERT INTO oddset_value_log_v2(
                match_id, market, sign, line, line_key, league, description,
                match_start, first_at, first_odds, first_fair, first_edge,
                best_edge, best_at, closing_fair, closing_odds, closing_line,
                line_delta, line_move_score, closing_note, book, tier,
                model_version, git_hash)
            SELECT match_id, market, sign, line,
                CASE WHEN line IS NULL THEN {NO_LINE_KEY}
                     ELSE CAST(ROUND(line * 1000) AS INTEGER) END,
                league, description, match_start, first_at, first_odds,
                first_fair, first_edge, best_edge, best_at, closing_fair,
                closing_odds, {closing_line}, {line_delta}, {move_score},
                CASE WHEN closing_note='linje flyttad' THEN NULL ELSE closing_note END,
                book, COALESCE(tier, 'sharp'),
                COALESCE(model_version, 'legacy'), git_hash
            FROM oddset_value_log
        """)
        after = conn.execute("SELECT COUNT(*) FROM oddset_value_log_v2").fetchone()[0]
        if after != before:
            raise RuntimeError(f"radantal ändrades {before}→{after}")
        conn.execute("DROP TABLE oddset_value_log")
        conn.execute("ALTER TABLE oddset_value_log_v2 RENAME TO oddset_value_log")
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"before": before, "after": after, "reset_line_moved": reset,
                "integrity": integrity, "changed": True}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    r = migrate(DB)
    print(f"facitrader {r['before']}→{r['after']} · "
          f"linjeflytt återöppnad {r['reset_line_moved']} · "
          f"integrity {r['integrity']} · {'migrerad' if r['changed'] else 'redan klar'}")


if __name__ == "__main__":
    main()
