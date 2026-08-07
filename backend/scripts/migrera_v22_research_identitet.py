"""Slå ihop researchmatch-dubbletter skapade av Kambis placeholdertider.

Endast rena Pinnacle-rader och rena Kambi-rader i V2.2:s research-only-ligor
får länkas, och bara när hemma-/bortalagsparet är entydigt. Pinnacle-raden är
kanon eftersom dess avsparkstid redan är satt; Kambi-ID och Kambi-oddshistorik
flyttas dit. Skriptet vägrar röra en rad som hunnit få facit/features.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.oddset import _resolve_team_pair  # noqa: E402

# FRYST 2026-07-23 — de ligor som VAR research_only när migreringen skrevs.
# Läste tidigare `oddset.RESEARCH_LEAGUE_KEYS` direkt, men den blev tom när
# ligorna gjordes fullt följda 2026-08-07 och skriptet slutade tyst göra
# någonting. Ett engångsskript beskriver ett HISTORISKT tillstånd och får
# aldrig ändra beteende för att en runtime-konstant ändras — samma princip
# som kohortregeln i live_radar.
RESEARCH_LEAGUE_KEYS = frozenset(
    {"premier_league", "serie_a", "la_liga", "bundesliga"})


DB = ROOT / "data" / "stryktips.db"
BACKUP = (
    ROOT / "data" / "backups" /
    "stryktips-2026-07-23-fore-v22-research-identitet.db"
)
BLOCKING_TABLES = (
    "oddset_value_log", "oddset_prediction_capture", "oddset_prediction_log",
    "oddset_v2_feature_capture", "oddset_v22_shadow_capture",
    "oddset_absence_capture", "oddset_absence_player",
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


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        marks = ",".join("?" for _ in RESEARCH_LEAGUE_KEYS)
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM oddset_matches WHERE league IN ({marks})",
            sorted(RESEARCH_LEAGUE_KEYS))]
        pins = [row for row in rows if row.get("pinnacle_id") and
                not row.get("kambi_id")]
        kambis = [row for row in rows if row.get("kambi_id") and
                  not row.get("pinnacle_id")]
        mappings = []
        for kambi in kambis:
            candidates = [pin for pin in pins if pin["league"] == kambi["league"]]
            pin = _resolve_team_pair(
                candidates, kambi["home"], kambi["away"])
            if not pin:
                continue
            if any(existing["new_id"] == pin["id"] for existing in mappings):
                raise RuntimeError(f"oentydig målrad: {pin['id']}")
            mappings.append({
                "old_id": kambi["id"], "new_id": pin["id"],
                "kambi_id": kambi["kambi_id"], "league": kambi["league"],
                "updated_at": kambi.get("updated_at"),
            })
        with conn:
            for mapping in mappings:
                for table in BLOCKING_TABLES:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE match_id=?",
                        (mapping["old_id"],)).fetchone()[0]
                    if count:
                        raise RuntimeError(
                            f"{mapping['old_id']} har {count} rader i {table}")
                conn.execute(
                    "UPDATE oddset_odds SET match_id=? WHERE match_id=?",
                    (mapping["new_id"], mapping["old_id"]))
                # Provider-id:n är globalt unika sedan
                # sanera_oddset_identitetskrockar.py. Ta därför bort den gamla
                # ägaren INNAN id:t flyttas till canonical-raden; transaktionen
                # gör fortfarande hela operationen atomisk.
                conn.execute(
                    "DELETE FROM oddset_matches WHERE id=?",
                    (mapping["old_id"],))
                conn.execute(
                    "UPDATE oddset_matches SET kambi_id=?, "
                    "updated_at=COALESCE(?, updated_at) WHERE id=?",
                    (mapping["kambi_id"], mapping["updated_at"],
                     mapping["new_id"]))
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "merged": len(mappings),
            "by_league": {
                league: sum(row["league"] == league for row in mappings)
                for league in sorted(RESEARCH_LEAGUE_KEYS)
            },
            "remaining_pure_kambi": conn.execute(
                f"SELECT COUNT(*) FROM oddset_matches "
                f"WHERE league IN ({marks}) AND kambi_id IS NOT NULL "
                "AND pinnacle_id IS NULL", sorted(RESEARCH_LEAGUE_KEYS)
            ).fetchone()[0],
            "integrity": integrity,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"sammanslagna {result['merged']} · per liga {result['by_league']} · "
          f"kvar rena Kambi {result['remaining_pure_kambi']} · "
          f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
