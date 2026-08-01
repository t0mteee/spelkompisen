"""Idempotent WP8-migration: tidsstämplade frånvaro-captures och spelarrader.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_franvarohistorik.py

Kräver namngiven backup. Befintliga senaste-payloads i meta backfylls som
legacy-captures utan påhittade provider-ID:n eller positioner.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import ABSENCE_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-07-16-fore-wp8-franvaro.db")


def _player_key(player: dict, provider: str = "sofascore") -> str:
    player_id = player.get("player_id")
    if player_id is not None:
        raw = str(player_id)
        return raw if ":" in raw else f"{'fs' if provider == 'flashscore' else 'sofa'}:{raw}"
    return (f"{provider}:name:" +
            str(player.get("name") or "okänd").casefold().strip())


def _execute_schema(conn: sqlite3.Connection) -> None:
    statement = ""
    for line in ABSENCE_SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                conn.execute(statement)
            statement = ""


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("BEGIN IMMEDIATE")
        _execute_schema(conn)
        inserted_captures = inserted_players = legacy_payloads = 0
        for key, raw in conn.execute(
                "SELECT key, value FROM meta WHERE key LIKE 'oddset_abs:%'").fetchall():
            legacy_payloads += 1
            try:
                rec = json.loads(raw)
            except (TypeError, ValueError):
                continue
            match_id = key.removeprefix("oddset_abs:")
            captured_at = rec.get("at")
            if not match_id or not captured_at:
                continue
            match = conn.execute(
                "SELECT start FROM oddset_matches WHERE id=?", (match_id,)).fetchone()
            home, away = rec.get("home") or [], rec.get("away") or []
            canonical = json.dumps(rec, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
            source_event_id = rec.get("source_event_id")
            provider = ("flashscore" if str(source_event_id or "").startswith("fs:")
                        else "sofascore")
            cur = conn.execute(
                "INSERT OR IGNORE INTO oddset_absence_capture(match_id, captured_at, "
                "provider, status, source_event_id, match_start, confirmed, "
                "payload_hash, home_missing, away_missing, missing_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (match_id, captured_at, provider, "observed", source_event_id,
                 match[0] if match else None, int(bool(rec.get("confirmed"))),
                 hashlib.sha256(canonical.encode()).hexdigest(),
                 len(home), len(away), len(home) + len(away)))
            if cur.rowcount == 0:
                continue
            inserted_captures += 1
            for side, players in (("home", home), ("away", away)):
                for player in players:
                    conn.execute(
                        "INSERT INTO oddset_absence_player(match_id, captured_at, provider, side, "
                        "player_key, player_id, name, position, reason_code, reason, "
                        "description, expected_end, appearances, rating) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (match_id, captured_at, provider, side,
                         _player_key(player, provider),
                         (_player_key(player, provider)
                          if player.get("player_id") is not None else None),
                         player.get("name") or "okänd",
                         player.get("position"), player.get("reason_code"),
                         player.get("reason"), player.get("description"),
                         player.get("expected_end"), player.get("apps"),
                         player.get("rating")))
                    inserted_players += 1
        conn.execute("COMMIT")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "legacy_payloads": legacy_payloads,
            "inserted_captures": inserted_captures,
            "inserted_players": inserted_players,
            "captures": conn.execute(
                "SELECT COUNT(*) FROM oddset_absence_capture").fetchone()[0],
            "players": conn.execute(
                "SELECT COUNT(*) FROM oddset_absence_player").fetchone()[0],
            "integrity": integrity,
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
    print(f"legacy {result['legacy_payloads']} · nya captures "
          f"{result['inserted_captures']} · nya spelarrader "
          f"{result['inserted_players']} · totalt {result['captures']}/"
          f"{result['players']} · integrity {result['integrity']}")


if __name__ == "__main__":
    main()
