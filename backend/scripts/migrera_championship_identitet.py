"""Slå ihop verifierade Championship-dubbletter efter scopeöppningen v12.

Första produktionsvarvet 2026-09-02 visade två rena providerpar:

* Pinnacle `Queens Park Rangers` ↔ Kambi `QPR`;
* Pinnacle `Birmingham City`/`Wolverhampton` ↔ Kambi
  `Birmingham`/`Wolves`.

Runtime-aliasen förhindrar nya dubbletter, men externt provider-id är
write-once och därför kan ett senare varv inte självläka redan skapade rader.
Skriptet flyttar endast en ren Kambi-rad till en ren Pinnacle-rad när båda
normaliserade lag är exakt lika, båda tider kan tolkas och avsparken skiljer
högst 15 minuter. Minsta oklarhet lämnas orörd. Endast oddshistorik får ha
hunnit skrivas; alla andra matchreferenser stoppar hela transaktionen.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.oddset import norm_team  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (
    ROOT / "data" / "backups" /
    "stryktips-2026-09-02-fore-championship-identitet.db"
)
LEAGUE = "championship"
MAX_START_DELTA_MIN = 15
MOVABLE_TABLES = frozenset({"oddset_odds"})


def backup_database(source: Path | str, target: Path | str) -> bool:
    """Skapa en konsistent SQLite-backup; en befintlig backup skrivs aldrig över."""
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


def _parse(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _same_fixture(pin: dict, kambi: dict) -> bool:
    pin_at, kambi_at = _parse(pin.get("start")), _parse(kambi.get("start"))
    if pin_at is None or kambi_at is None:
        return False
    if abs((pin_at - kambi_at).total_seconds()) > MAX_START_DELTA_MIN * 60:
        return False
    return (
        norm_team(pin.get("home") or "") == norm_team(kambi.get("home") or "")
        and norm_team(pin.get("away") or "") == norm_team(kambi.get("away") or "")
    )


def _mappings(rows: list[dict]) -> list[dict]:
    pins = [row for row in rows if row.get("pinnacle_id") and
            not row.get("kambi_id")]
    kambis = [row for row in rows if row.get("kambi_id") and
              not row.get("pinnacle_id")]
    out = []
    claimed_targets: set[str] = set()
    for kambi in kambis:
        matches = [pin for pin in pins if _same_fixture(pin, kambi)]
        if len(matches) > 1:
            raise RuntimeError(f"oentydig målrad för {kambi['id']}")
        if not matches:
            continue
        pin = matches[0]
        if pin["id"] in claimed_targets:
            raise RuntimeError(f"flera Kambi-rader pekar på {pin['id']}")
        claimed_targets.add(pin["id"])
        out.append({"old": kambi, "new": pin})
    return out


def _referencing_tables(conn: sqlite3.Connection) -> set[str]:
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    return {
        table for table in tables
        if any(col[1] == "match_id"
               for col in conn.execute(f"PRAGMA table_info({table})"))
    }


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        before_matches = conn.execute(
            "SELECT COUNT(*) FROM oddset_matches WHERE league=?", (LEAGUE,)
        ).fetchone()[0]
        before_odds = conn.execute("SELECT COUNT(*) FROM oddset_odds").fetchone()[0]
        rows = [dict(row) for row in conn.execute(
            "SELECT * FROM oddset_matches WHERE league=?", (LEAGUE,))]
        mappings = _mappings(rows)
        blocked_tables = sorted(_referencing_tables(conn) - MOVABLE_TABLES)

        with conn:
            for mapping in mappings:
                old, new = mapping["old"], mapping["new"]
                for table in blocked_tables:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE match_id=?",
                        (old["id"],)).fetchone()[0]
                    if count:
                        raise RuntimeError(
                            f"{old['id']} har {count} rader i {table}")
                conn.execute(
                    "UPDATE oddset_odds SET match_id=? WHERE match_id=?",
                    (new["id"], old["id"]))
                # Provider-id:t har ett globalt unikhetsindex. Ta bort den
                # gamla ägaren före flytten; transaktionen gör stegen atomiska.
                conn.execute("DELETE FROM oddset_matches WHERE id=?", (old["id"],))
                conn.execute(
                    "UPDATE oddset_matches SET kambi_id=?, home=?, away=?, "
                    "updated_at=COALESCE(?, updated_at) WHERE id=?",
                    (old["kambi_id"], old["home"], old["away"],
                     old.get("updated_at"), new["id"]))

        after_matches = conn.execute(
            "SELECT COUNT(*) FROM oddset_matches WHERE league=?", (LEAGUE,)
        ).fetchone()[0]
        after_odds = conn.execute("SELECT COUNT(*) FROM oddset_odds").fetchone()[0]
        remaining = _mappings([dict(row) for row in conn.execute(
            "SELECT * FROM oddset_matches WHERE league=?", (LEAGUE,))])
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if before_odds != after_odds:
            raise RuntimeError(
                f"oddshistorik ändrades i antal: {before_odds} -> {after_odds}")
        if before_matches - after_matches != len(mappings):
            raise RuntimeError("oväntad förändring av Championship-matchantal")
        return {
            "merged": len(mappings),
            "pairs": [(m["old"]["id"], m["new"]["id"]) for m in mappings],
            "matches_before": before_matches,
            "matches_after": after_matches,
            "odds_before": before_odds,
            "odds_after": after_odds,
            "remaining_alias_duplicates": len(remaining),
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
    print(
        f"sammanslagna {result['merged']} {result['pairs']} · "
        f"matcher {result['matches_before']}->{result['matches_after']} · "
        f"odds {result['odds_before']}->{result['odds_after']} · "
        f"kvar {result['remaining_alias_duplicates']} · "
        f"integrity {result['integrity']}"
    )


if __name__ == "__main__":
    main()
