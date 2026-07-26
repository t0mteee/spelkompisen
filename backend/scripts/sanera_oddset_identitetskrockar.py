"""Karantänsanera bevisade Oddset-identitetskrockar (2026-07-26).

Bakgrund:
`oddset_matches.pinnacle_id` kunde skrivas över och fuzzy-matchningen lät ett
perfekt lagnamn väga upp ett orelaterat motståndarlag. Därför skrevs två olika
Pinnacle-event ibland till samma canonical match. Beviskriteriet här är strikt:
samma match, källa, marknad, tecken och observationstid har fler än ett pris.

Skriptet:
* tar en SQLite-onlinebackup före första ändringen,
* tar bort ALLA signal-/modell-/facitrader för bevisat kolliderade matcher
  (closing och identitet kan inte längre styrkas),
* raderar deras falska lokala notishistorik,
* reparerar den separat verifierade Karlsruhe–Inter-kollisionen och tar bort
  hela dess råa Pinnacle-livscykel (felraden fanns före första samtidiga
  dubbelpriset, så ingen tidigare Pinnacle-rad kan styrkas),
* skapar Novara–Internazionale U23 som egen Pinnacle-identitet,
* lägger unika DB-index på externa Pinnacle-/Kambi-id:n.

Övrig rå oddshistorik bevaras som forensiskt underlag och karantänsätts av
läs-API:t. Skriptet gissar aldrig vilken av två historiska prisserier som var
rätt.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
BACKUP = (
    ROOT / "data" / "backups" /
    "stryktips-2026-07-26-fore-oddset-identitet.db"
)

KARLSRUHE_ID = "pin:1632753942"
KARLSRUHE_PINNACLE_ID = "1632753942"
NOVARA_ID = "pin:1632967000"
NOVARA_PINNACLE_ID = "1632967000"

DERIVED_TABLES = (
    "oddset_value_log",
    "oddset_prediction_log",
    "oddset_prediction_capture",
    "oddset_v2_feature_capture",
    "oddset_v22_shadow_capture",
    "oddset_absence_player",
    "oddset_absence_capture",
)


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


def _collision_matches(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "WITH collisions AS ("
        " SELECT match_id, MIN(fetched_at) AS first_collision,"
        " COUNT(*) AS collision_groups"
        " FROM ("
        "  SELECT match_id, source, market, sign, fetched_at"
        "  FROM oddset_odds"
        "  GROUP BY match_id, source, market, sign, fetched_at"
        "  HAVING COUNT(DISTINCT CAST(odds AS TEXT) || '|' ||"
        "   COALESCE(CAST(line AS TEXT), ''))>1"
        " ) GROUP BY match_id"
        ") SELECT c.*, m.league, m.home, m.away, m.start"
        " FROM collisions c JOIN oddset_matches m ON m.id=c.match_id"
        " ORDER BY c.collision_groups DESC, c.match_id"
    )]


def sanitize(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        conflicts = _collision_matches(conn)
        conflict_ids = [row["match_id"] for row in conflicts]
        target = conn.execute(
            "SELECT * FROM oddset_matches WHERE id=?",
            (KARLSRUHE_ID,)).fetchone()
        if not target:
            raise RuntimeError("Karlsruhe-matchen saknas")
        if str(target["pinnacle_id"]) not in {
                KARLSRUHE_PINNACLE_ID, NOVARA_PINNACLE_ID}:
            raise RuntimeError(
                f"oväntat Pinnacle-id på Karlsruhe: {target['pinnacle_id']}")

        marks = ",".join("?" for _ in conflict_ids)
        removed: dict[str, int] = {}
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with conn:
            # Nedströmsdata kan varken få rätt identitet eller ett säkert
            # closing-facit efter en kollision. Ta hellre bort än märk fel som
            # ett modellresultat.
            for table in DERIVED_TABLES:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE match_id IN ({marks})",
                    conflict_ids)
                removed[table] = cur.rowcount

            notice_rows = 0
            for match_id in conflict_ids:
                cur = conn.execute(
                    "DELETE FROM meta WHERE "
                    "(key LIKE 'oddset_ntfy_edge:' || ? || ':%' OR "
                    " key LIKE 'oddset_ntfy_steam:' || ? || ':%')",
                    (match_id, match_id))
                notice_rows += cur.rowcount
            removed["meta_notices"] = notice_rows

            # Karlsruhe–Inter är verifierad mot Pinnacles direkta eventfeed.
            # Den felaktiga Novara-raden syns redan FÖRE första samtidiga
            # dubbelpriset. Därför kan ingen Pinnacle-rad i matchens livscykel
            # styrkas; korrekt feed får samlas om från tom serie.
            cur = conn.execute(
                "DELETE FROM oddset_odds WHERE match_id=? "
                "AND source IN ('pinnacle','derived')",
                (KARLSRUHE_ID,))
            removed["karlsruhe_odds"] = cur.rowcount
            cur = conn.execute(
                "DELETE FROM oddset_sharp_alt WHERE match_id=?",
                (KARLSRUHE_ID,))
            removed["karlsruhe_sharp_alt"] = cur.rowcount

            conn.execute(
                "UPDATE oddset_matches SET pinnacle_id=?, updated_at=? WHERE id=?",
                (KARLSRUHE_PINNACLE_ID, now, KARLSRUHE_ID))
            conn.execute(
                "INSERT INTO oddset_matches("
                " id, league, home, away, start, pinnacle_id, status, updated_at"
                ") VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "pinnacle_id=COALESCE(oddset_matches.pinnacle_id,"
                " excluded.pinnacle_id), updated_at=excluded.updated_at",
                (NOVARA_ID, "friendlies", "Novara", "Internazionale U23",
                 "2026-07-26T15:30:00Z", NOVARA_PINNACLE_ID, "pending", now))

            # Databasen försvarar samma one-to-one-invariant som insamlaren.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_oddset_matches_pinnacle_id "
                "ON oddset_matches(pinnacle_id) WHERE pinnacle_id IS NOT NULL")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_oddset_matches_kambi_id "
                "ON oddset_matches(kambi_id) WHERE kambi_id IS NOT NULL")

        remaining_target_collisions = [
            row for row in _collision_matches(conn)
            if row["match_id"] == KARLSRUHE_ID
        ]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "conflict_matches": len(conflicts),
            "conflict_groups": sum(row["collision_groups"] for row in conflicts),
            "by_league": {
                league: sum(row["league"] == league for row in conflicts)
                for league in sorted({row["league"] for row in conflicts})
            },
            "removed": removed,
            "karlsruhe_pinnacle_id": conn.execute(
                "SELECT pinnacle_id FROM oddset_matches WHERE id=?",
                (KARLSRUHE_ID,)).fetchone()[0],
            "novara_exists": bool(conn.execute(
                "SELECT 1 FROM oddset_matches WHERE id=?",
                (NOVARA_ID,)).fetchone()),
            "karlsruhe_collisions_after": len(remaining_target_collisions),
            "unique_indexes": [
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND name LIKE 'uq_oddset_matches_%' ORDER BY name")
            ],
            "integrity": integrity,
            "audit": conflicts,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = sanitize(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(
        f"krockmatcher {result['conflict_matches']} · "
        f"krockgrupper {result['conflict_groups']} · "
        f"ligor {result['by_league']}")
    print(f"borttaget {result['removed']}")
    print(
        f"Karlsruhe Pinnacle-id {result['karlsruhe_pinnacle_id']} · "
        f"Novara egen rad {result['novara_exists']} · "
        f"Karlsruhe-krockar kvar {result['karlsruhe_collisions_after']}")
    print(
        f"unika index {result['unique_indexes']} · "
        f"integrity {result['integrity']}")
    print("audit (råhistorik bevarad):")
    for row in result["audit"]:
        print(
            f"  {row['match_id']} · {row['league']} · "
            f"{row['home']}–{row['away']} · "
            f"{row['collision_groups']} grupper från {row['first_collision']}")


if __name__ == "__main__":
    main()
