"""Idempotent WP8-migration: dagliga ClubElo-captures och PIT-historik.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_elohistorik.py

Kräver namngiven backup. Befintlig senaste-ranking i meta blir en legacy-
capture utan påhittat rånamn eller land. Historiska intervall fylls separat av
backfill_elohistorik.py.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import ELO_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-07-16-fore-wp8-elo.db")


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.executescript("BEGIN IMMEDIATE;\n" + ELO_SCHEMA)
        # Tidig utvecklingsversion kunde skapa en ny legacy-capture när meta-
        # cachen senare flyttades av en riktig daily-capture. Rensa endast den
        # bevisliga varianten: samma requested_date och högst två sekunder isär.
        duplicate_legacy = [r[0] for r in conn.execute(
            "SELECT l.captured_at FROM oddset_elo_capture l "
            "WHERE l.source='legacy' AND EXISTS (SELECT 1 FROM oddset_elo_capture d "
            "WHERE d.source='daily' AND d.requested_date=l.requested_date "
            "AND ABS((julianday(d.captured_at)-julianday(l.captured_at))*86400)<=2)"
        ).fetchall()]
        for captured_at in duplicate_legacy:
            conn.execute("DELETE FROM oddset_elo_rating WHERE captured_at=?",
                         (captured_at,))
            conn.execute("DELETE FROM oddset_elo_capture WHERE captured_at=?",
                         (captured_at,))
        raw_row = conn.execute(
            "SELECT value FROM meta WHERE key='oddset_elo'").fetchone()
        at_row = conn.execute(
            "SELECT value FROM meta WHERE key='oddset_elo_at'").fetchone()
        inserted_capture = inserted_ratings = 0
        has_capture = conn.execute(
            "SELECT 1 FROM oddset_elo_capture LIMIT 1").fetchone()
        if raw_row and at_row and not has_capture:
            try:
                elo = json.loads(raw_row[0])
            except (TypeError, ValueError):
                elo = {}
            captured_at = at_row[0]
            requested_date = captured_at[:10]
            if isinstance(elo, dict) and elo and len(requested_date) == 10:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO oddset_elo_capture(captured_at, "
                    "requested_date, source, payload_hash, row_count) VALUES(?,?,?,?,?)",
                    (captured_at, requested_date, "legacy",
                     hashlib.sha256(raw_row[0].encode()).hexdigest(), len(elo)))
                if cur.rowcount:
                    inserted_capture = 1
                    for club_key, value in elo.items():
                        try:
                            rating = float(value)
                        except (TypeError, ValueError):
                            continue
                        conn.execute(
                            "INSERT INTO oddset_elo_rating(captured_at, club_key, "
                            "club_raw, country, level, elo, valid_from, valid_to) "
                            "VALUES(?,?,?,?,?,?,?,?)",
                            (captured_at, club_key, club_key, None, None, rating,
                             requested_date, requested_date))
                        inserted_ratings += 1
                    conn.execute(
                        "UPDATE oddset_elo_capture SET row_count=? WHERE captured_at=?",
                        (inserted_ratings, captured_at))
        conn.execute("COMMIT")
        return {
            "inserted_capture": inserted_capture,
            "inserted_ratings": inserted_ratings,
            "removed_duplicate_legacy": len(duplicate_legacy),
            "captures": conn.execute(
                "SELECT COUNT(*) FROM oddset_elo_capture").fetchone()[0],
            "ratings": conn.execute(
                "SELECT COUNT(*) FROM oddset_elo_rating").fetchone()[0],
            "history": conn.execute(
                "SELECT COUNT(*) FROM oddset_elo_history").fetchone()[0],
            "integrity": conn.execute("PRAGMA integrity_check").fetchone()[0],
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    if not BACKUP.exists():
        sys.exit(f"AVBRYTER: backup saknas ({BACKUP}) — ta backup först.")
    result = migrate(DB)
    print(f"ny legacy-capture {result['inserted_capture']} · nya ratings "
          f"{result['inserted_ratings']} · totalt captures/ratings/history "
          f"{result['captures']}/{result['ratings']}/{result['history']} · "
          f"rensade legacy-dubbletter {result['removed_duplicate_legacy']} · "
          f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
