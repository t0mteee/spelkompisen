"""Correct the first WP5 capture's Git stamp after a staging race.

Launchd captured at 13:30:07Z while the final WP5 tree was staged but five
minutes before commit 4cd0bb0 was created. `_code_version()` therefore wrote
the parent 6156f74 even though the executing WP5 source files are exactly the
tree in 4cd0bb0. This narrow, guarded correction preserves the real prices and
fixes reproducibility metadata; it does not alter predictions or timestamps.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "backend" / "data" / "stryktips.db"
BACKUP = (ROOT / "backend" / "data" / "backups" /
          "stryktips-2026-07-16-fore-wp5-githash.db")
FROM_HASH = "6156f74"
TO_HASH = "4cd0bb0"
CAPTURED_AT = "2026-07-16T13:30:07Z"
EXPECTED_ROWS = 220
CORE_PATHS = (
    "backend/app/main.py", "backend/app/oddset.py",
    "backend/app/oddset_ledger.py", "backend/app/oddset_value.py",
    "backend/app/storage.py", "frontend/src/App.jsx", "frontend/src/App.css",
)


def _verify_tree() -> None:
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    if head != TO_HASH:
        sys.exit(f"AVBRYTER: HEAD är {head}, förväntade {TO_HASH}")
    clean = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--quiet", TO_HASH, "--", *CORE_PATHS])
    if clean.returncode != 0:
        sys.exit("AVBRYTER: WP5-källträdet skiljer sig från commit 4cd0bb0")


def correct(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before = conn.execute(
            "SELECT COUNT(*) FROM oddset_prediction_log WHERE git_hash=? "
            "AND captured_at=?", (FROM_HASH, CAPTURED_AT)).fetchone()[0]
        already = conn.execute(
            "SELECT COUNT(*) FROM oddset_prediction_log WHERE git_hash=? "
            "AND captured_at=?", (TO_HASH, CAPTURED_AT)).fetchone()[0]
        if before == 0 and already == EXPECTED_ROWS:
            return {"changed": 0, "integrity": "ok", "already": True}
        if before != EXPECTED_ROWS or already:
            raise RuntimeError(
                f"oväntat urval: {before} från-rader, {already} redan rättade")
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "UPDATE oddset_prediction_log SET git_hash=? WHERE git_hash=? "
            "AND captured_at=?", (TO_HASH, FROM_HASH, CAPTURED_AT))
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {"changed": cur.rowcount, "integrity": integrity, "already": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP})")
    _verify_tree()
    result = correct(DB)
    print(f"git-hash {FROM_HASH}→{TO_HASH}: {result['changed']} rader · "
          f"integrity {result['integrity']} · "
          f"{'redan klar' if result['already'] else 'korrigerad'}")


if __name__ == "__main__":
    main()
