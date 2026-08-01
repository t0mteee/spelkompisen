"""Migrera modellstatistik och frånvaroproveniens till datakontrakt v4.

Körning i produktion (backup tas av skriptet före första mutation):
    cd backend && .venv/bin/python -B scripts/migrera_modelldata_v4.py

Migrationen är idempotent och atomär. Den gör tre saker:

* flyttar xG/hörnor ur ``oddset_results`` till en provider-rad i
  ``oddset_result_stats`` och tar bort gamla ``+fs`` från resultatkällan;
* bygger om frånvarocaptures med explicit provider/status;
* gör spelar-id:n till namespacad TEXT (``fs:``/``sofa:``).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import ABSENCE_SCHEMA, RESULT_STATS_SCHEMA  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-01-fore-modelldata-v4.db")


def backup_database(source: Path | str, target: Path | str) -> bool:
    target = Path(target)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=10)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.execute("PRAGMA busy_timeout=10000")
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return True


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    return {row[1]: (row[2] or "").upper()
            for row in conn.execute(f"PRAGMA table_info({table})")}


def _primary_key(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in sorted(
        (row for row in conn.execute(f"PRAGMA table_info({table})") if row[5]),
        key=lambda row: row[5]))


def _table_ddl(schema: str, table: str, target: str | None = None) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {table} ("
    start = schema.index(marker)
    end = schema.index("\n);", start) + len("\n);")
    ddl = schema[start:end]
    if target:
        ddl = ddl.replace(marker, f"CREATE TABLE {target} (", 1)
    return ddl


def _execute_schema(conn: sqlite3.Connection, schema: str) -> None:
    statement = ""
    for line in schema.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                conn.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("ofullständig schemasats")


def _provider(source: str | None, xg_value,
              source_event_id: str | None = None) -> str:
    if source_event_id is not None:
        return "flashscore" if str(source_event_id).startswith("fs:") else "sofascore"
    value = str(source or "")
    if "+fs" in value:
        return "flashscore"
    if value == "sofa":
        return "sofascore"
    if xg_value is not None:
        # Före Flashscore var Sofascore projektets enda xG-källa.
        return "sofascore"
    if value == "fd":
        return "football_data"
    return "legacy"


def _result_stats_is_current(conn: sqlite3.Connection) -> bool:
    columns = _columns(conn, "oddset_result_stats")
    required = {
        "league", "date", "home", "away", "provider",
        "provider_event_id", "xg_observed_at", "corners_observed_at",
        "match_start_at", "final_home_score", "final_away_score",
        "xg_h", "xg_a", "cor_h", "cor_a",
    }
    return (required <= set(columns) and
            _primary_key(conn, "oddset_result_stats") ==
            ("league", "date", "home", "away", "provider"))


def _rebuild_result_stats(conn: sqlite3.Connection) -> bool:
    """Bygg om v1-tabellen utan att gissa familjernas observationstid.

    Det gamla ``observed_at`` gällde hela provider-raden. Om raden innehåller
    både xG och hörnor går det inte att veta om familjerna hämtades samtidigt
    eller kompletterades senare. Den tiden lämnas därför NULL för båda i det
    tvetydiga fallet. Själva statistikfälten och matchproveniensen bevaras.
    """
    columns = _columns(conn, "oddset_result_stats")
    if not columns:
        _execute_schema(conn, RESULT_STATS_SCHEMA)
        return False
    if _result_stats_is_current(conn):
        _execute_schema(conn, RESULT_STATS_SCHEMA)
        return False

    required = {"league", "date", "home", "away", "provider",
                "xg_h", "xg_a", "cor_h", "cor_a"}
    if not required <= set(columns):
        raise RuntimeError(
            "oddset_result_stats saknar "
            f"{sorted(required - set(columns))}")
    if _primary_key(conn, "oddset_result_stats") != (
            "league", "date", "home", "away", "provider"):
        raise RuntimeError("oddset_result_stats har oväntad primärnyckel")

    rows = [dict(row) for row in conn.execute(
        "SELECT * FROM oddset_result_stats")]
    conn.execute(_table_ddl(
        RESULT_STATS_SCHEMA, "oddset_result_stats", "oddset_result_stats_v4"))
    for row in rows:
        has_xg = row.get("xg_h") is not None or row.get("xg_a") is not None
        has_corners = (row.get("cor_h") is not None or
                       row.get("cor_a") is not None)
        legacy_observed = row.get("observed_at")
        xg_observed = row.get("xg_observed_at")
        corners_observed = row.get("corners_observed_at")
        if legacy_observed and has_xg and not has_corners and not xg_observed:
            xg_observed = legacy_observed
        if (legacy_observed and has_corners and not has_xg and
                not corners_observed):
            corners_observed = legacy_observed
        conn.execute(
            "INSERT INTO oddset_result_stats_v4(league,date,home,away,provider,"
            "provider_event_id,xg_observed_at,corners_observed_at,match_start_at,"
            "final_home_score,final_away_score,xg_h,xg_a,cor_h,cor_a) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["league"], row["date"], row["home"], row["away"],
             row["provider"], row.get("provider_event_id"), xg_observed,
             corners_observed, row.get("match_start_at"),
             row.get("final_home_score"), row.get("final_away_score"),
             row.get("xg_h"), row.get("xg_a"), row.get("cor_h"),
             row.get("cor_a")))
    if conn.execute(
            "SELECT COUNT(*) FROM oddset_result_stats_v4").fetchone()[0] != len(rows):
        raise RuntimeError("statistikradantal ändrades vid ombyggnad")
    conn.execute("DROP TABLE oddset_result_stats")
    conn.execute(
        "ALTER TABLE oddset_result_stats_v4 RENAME TO oddset_result_stats")
    _execute_schema(conn, RESULT_STATS_SCHEMA)
    return True


def _validate_before(conn: sqlite3.Connection) -> None:
    result = _columns(conn, "oddset_results")
    required_result = {"league", "date", "home", "away", "hg", "ag",
                       "xg_h", "xg_a", "cor_h", "cor_a", "source"}
    if not required_result <= set(result):
        raise RuntimeError(
            f"oddset_results saknar {sorted(required_result - set(result))}")
    stats = _columns(conn, "oddset_result_stats")
    if stats:
        required_stats = {"league", "date", "home", "away", "provider",
                          "xg_h", "xg_a", "cor_h", "cor_a"}
        if not required_stats <= set(stats):
            raise RuntimeError(
                "oddset_result_stats saknar "
                f"{sorted(required_stats - set(stats))}")
        if _primary_key(conn, "oddset_result_stats") != (
                "league", "date", "home", "away", "provider"):
            raise RuntimeError("oddset_result_stats har oväntad primärnyckel")
    capture = _columns(conn, "oddset_absence_capture")
    player = _columns(conn, "oddset_absence_player")
    if bool(capture) != bool(player):
        raise RuntimeError("frånvarotabellerna finns bara delvis")
    if capture:
        required_capture = {"match_id", "captured_at", "source_event_id",
                            "match_start", "confirmed", "payload_hash",
                            "home_missing", "away_missing", "missing_count"}
        required_player = {"match_id", "captured_at", "side", "player_key",
                           "player_id", "name"}
        if not required_capture <= set(capture):
            raise RuntimeError(
                f"absence_capture saknar {sorted(required_capture - set(capture))}")
        if not required_player <= set(player):
            raise RuntimeError(
                f"absence_player saknar {sorted(required_player - set(player))}")


def _migrate_result_stats(conn: sqlite3.Connection) -> int:
    _rebuild_result_stats(conn)
    before = conn.execute(
        "SELECT COUNT(*) FROM oddset_result_stats").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM oddset_results WHERE xg_h IS NOT NULL OR xg_a IS NOT NULL "
        "OR cor_h IS NOT NULL OR cor_a IS NOT NULL").fetchall()
    for row in rows:
        source = str(row["source"] or "")
        base_source = source.replace("+fs", "")
        observations: dict[str, dict] = {}
        has_xg = row["xg_h"] is not None or row["xg_a"] is not None
        has_corners = row["cor_h"] is not None or row["cor_a"] is not None

        # Historiken måste tolkas efter den skrivordning som faktiskt gällde:
        # före Flashscore skrev Sofascore xG och hörnor som ett paket och vann
        # den gamla `excluded`-upserten, även när målraden hade `source=fd`.
        # Sådana rader får stanna som ett helt Sofa-paket; att godtyckligt
        # märka hörnen som football-data skulle skapa en ny, falsk proveniens.
        if has_xg and "+fs" not in source and base_source in {"fd", "sofa"}:
            observations["sofascore"] = {
                "xg_h": row["xg_h"], "xg_a": row["xg_a"],
                "cor_h": row["cor_h"], "cor_a": row["cor_a"],
            }
        else:
            if has_xg:
                provider = "flashscore" if "+fs" in source else "legacy"
                observations.setdefault(provider, {}).update(
                    {"xg_h": row["xg_h"], "xg_a": row["xg_a"]})
            if has_corners:
                if base_source == "fd" and "+fs" not in source:
                    provider = "football_data"
                elif base_source == "sofa" and "+fs" not in source:
                    provider = "sofascore"
                else:
                    # `+fs` fyllde xG men bevarade redan lagrade hörn med
                    # COALESCE. De kan därför vara Sofa eller Flashscore. Vi
                    # märker dem legacy i stället för att fabricera en källa.
                    provider = "legacy"
                observations.setdefault(provider, {}).update(
                    {"cor_h": row["cor_h"], "cor_a": row["cor_a"]})
        for provider, stats in observations.items():
            conn.execute(
                "INSERT INTO oddset_result_stats(league,date,home,away,provider,"
                "final_home_score,final_away_score,xg_h,xg_a,cor_h,cor_a) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(league,date,home,away,provider) DO UPDATE SET "
                "final_home_score=COALESCE(oddset_result_stats.final_home_score,"
                "excluded.final_home_score), "
                "final_away_score=COALESCE(oddset_result_stats.final_away_score,"
                "excluded.final_away_score), "
                "xg_h=COALESCE(oddset_result_stats.xg_h,excluded.xg_h), "
                "xg_a=COALESCE(oddset_result_stats.xg_a,excluded.xg_a), "
                "cor_h=COALESCE(oddset_result_stats.cor_h,excluded.cor_h), "
                "cor_a=COALESCE(oddset_result_stats.cor_a,excluded.cor_a)",
                (row["league"], row["date"], row["home"], row["away"], provider,
                 row["hg"], row["ag"], stats.get("xg_h"), stats.get("xg_a"),
                 stats.get("cor_h"), stats.get("cor_a")))
            saved = conn.execute(
                "SELECT final_home_score,final_away_score,xg_h,xg_a,cor_h,cor_a "
                "FROM oddset_result_stats WHERE league=? AND date=? AND home=? "
                "AND away=? AND provider=?",
                (row["league"], row["date"], row["home"], row["away"],
                 provider)).fetchone()
            expected = {
                "final_home_score": row["hg"], "final_away_score": row["ag"],
                "xg_h": stats.get("xg_h"), "xg_a": stats.get("xg_a"),
                "cor_h": stats.get("cor_h"), "cor_a": stats.get("cor_a"),
            }
            for field, value in expected.items():
                if value is not None and saved[field] != value:
                    raise RuntimeError(
                        "motstridig legacy-statistik för "
                        f"{row['league']} {row['date']} {row['home']}–"
                        f"{row['away']} {provider}.{field}: "
                        f"{saved[field]!r} != {value!r}")
    conn.execute(
        "UPDATE oddset_results SET source=REPLACE(source,'+fs',''), "
        "xg_h=NULL,xg_a=NULL,cor_h=NULL,cor_a=NULL")
    after = conn.execute(
        "SELECT COUNT(*) FROM oddset_result_stats").fetchone()[0]
    return after - before


def _namespace_player_id(provider: str, value) -> str | None:
    if value is None:
        return None
    raw = str(value)
    if ":" in raw:
        return raw
    return f"{'fs' if provider == 'flashscore' else 'sofa'}:{raw}"


def _absence_is_current(conn: sqlite3.Connection) -> bool:
    capture = _columns(conn, "oddset_absence_capture")
    player = _columns(conn, "oddset_absence_player")
    return (capture.get("provider") == "TEXT" and
            capture.get("status") == "TEXT" and
            player.get("player_id") == "TEXT" and
            player.get("provider") == "TEXT" and
            _primary_key(conn, "oddset_absence_capture") ==
            ("match_id", "captured_at", "provider") and
            _primary_key(conn, "oddset_absence_player") ==
            ("match_id", "captured_at", "provider", "side", "player_key"))


def _rebuild_absences(conn: sqlite3.Connection) -> bool:
    if not _columns(conn, "oddset_absence_capture"):
        _execute_schema(conn, ABSENCE_SCHEMA)
        return False
    if _absence_is_current(conn):
        return False

    captures = [dict(row) for row in conn.execute(
        "SELECT * FROM oddset_absence_capture")]
    players = [dict(row) for row in conn.execute(
        "SELECT * FROM oddset_absence_player")]
    provider_by_capture = {
        (row["match_id"], row["captured_at"]): (row.get("provider") or _provider(
            None, None, row.get("source_event_id")))
        for row in captures
    }

    conn.execute(_table_ddl(
        ABSENCE_SCHEMA, "oddset_absence_capture", "oddset_absence_capture_v4"))
    conn.execute(_table_ddl(
        ABSENCE_SCHEMA, "oddset_absence_player", "oddset_absence_player_v4"))
    for row in captures:
        provider = row.get("provider") or provider_by_capture[
            (row["match_id"], row["captured_at"])]
        status = row.get("status") or "observed"
        conn.execute(
            "INSERT INTO oddset_absence_capture_v4(match_id,captured_at,provider,"
            "status,source_event_id,match_start,confirmed,payload_hash,home_missing,"
            "away_missing,missing_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (row["match_id"], row["captured_at"], provider, status,
             row.get("source_event_id"), row.get("match_start"), row["confirmed"],
             row["payload_hash"], row["home_missing"], row["away_missing"],
             row["missing_count"]))
    for row in players:
        provider = provider_by_capture[(row["match_id"], row["captured_at"])]
        player_id = _namespace_player_id(provider, row.get("player_id"))
        player_key = (player_id or
                      f"{provider}:name:{str(row.get('name') or 'okänd').casefold().strip()}")
        conn.execute(
            "INSERT INTO oddset_absence_player_v4(match_id,captured_at,provider,"
            "side,player_key,"
            "player_id,name,position,reason_code,reason,description,expected_end,"
            "appearances,rating) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row["match_id"], row["captured_at"], provider, row["side"], player_key,
             player_id, row["name"], row.get("position"), row.get("reason_code"),
             row.get("reason"), row.get("description"), row.get("expected_end"),
             row.get("appearances"), row.get("rating")))

    if conn.execute("SELECT COUNT(*) FROM oddset_absence_capture_v4").fetchone()[0] != len(captures):
        raise RuntimeError("capture-radantal ändrades vid ombyggnad")
    if conn.execute("SELECT COUNT(*) FROM oddset_absence_player_v4").fetchone()[0] != len(players):
        raise RuntimeError("spelarradantal ändrades vid ombyggnad")
    conn.execute("DROP TABLE oddset_absence_player")
    conn.execute("DROP TABLE oddset_absence_capture")
    conn.execute("ALTER TABLE oddset_absence_capture_v4 RENAME TO oddset_absence_capture")
    conn.execute("ALTER TABLE oddset_absence_player_v4 RENAME TO oddset_absence_player")
    conn.execute("CREATE INDEX idx_absence_capture_match "
                 "ON oddset_absence_capture (match_id, captured_at)")
    conn.execute("CREATE INDEX idx_absence_player_identity "
                 "ON oddset_absence_player (player_id, captured_at)")
    return True


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        _validate_before(conn)
        before_results = conn.execute("SELECT COUNT(*) FROM oddset_results").fetchone()[0]
        before_captures = (conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_capture").fetchone()[0]
            if _columns(conn, "oddset_absence_capture") else 0)
        before_players = (conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_player").fetchone()[0]
            if _columns(conn, "oddset_absence_player") else 0)
        had_stats_table = bool(_columns(conn, "oddset_result_stats"))
        stats_schema_was_current = _result_stats_is_current(conn)
        conn.execute("BEGIN IMMEDIATE")
        inserted_stats = _migrate_result_stats(conn)
        rebuilt_absences = _rebuild_absences(conn)

        if conn.execute("SELECT COUNT(*) FROM oddset_results").fetchone()[0] != before_results:
            raise RuntimeError("resultatradantal ändrades")
        if conn.execute(
                "SELECT COUNT(*) FROM oddset_absence_capture").fetchone()[0] != before_captures:
            raise RuntimeError("frånvarocapture-radantal ändrades")
        if conn.execute(
                "SELECT COUNT(*) FROM oddset_absence_player").fetchone()[0] != before_players:
            raise RuntimeError("frånvarospelare-radantal ändrades")
        if conn.execute(
                "SELECT COUNT(*) FROM oddset_results WHERE source LIKE '%+fs%' "
                "OR xg_h IS NOT NULL OR xg_a IS NOT NULL OR cor_h IS NOT NULL "
                "OR cor_a IS NOT NULL").fetchone()[0]:
            raise RuntimeError("generiska resultatrader bär fortfarande providerstatistik")
        if not _result_stats_is_current(conn):
            raise RuntimeError("providerstatistikens schema är inte v4")
        if not _absence_is_current(conn):
            raise RuntimeError("frånvaroschemat är inte v4")
        bad_ids = conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_player p "
            "WHERE p.player_id IS NOT NULL AND ((p.provider='flashscore' AND "
            "p.player_id NOT LIKE 'fs:%') OR (p.provider='sofascore' AND "
            "p.player_id NOT LIKE 'sofa:%'))").fetchone()[0]
        if bad_ids:
            raise RuntimeError(f"{bad_ids} spelare saknar provider-prefix")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check: {integrity}")
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"foreign_key_check: {fk_errors[:3]}")
        conn.execute("COMMIT")
        return {
            "result_rows": before_results,
            "stats_inserted": inserted_stats,
            "stats_rows": conn.execute(
                "SELECT COUNT(*) FROM oddset_result_stats").fetchone()[0],
            "stats_schema_rebuilt": (
                had_stats_table and not stats_schema_was_current),
            "absence_rebuilt": rebuilt_absences,
            "absence_captures": before_captures,
            "absence_players": before_players,
            "integrity": integrity,
            "foreign_keys": "ok",
        }
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(result)


if __name__ == "__main__":
    main()
