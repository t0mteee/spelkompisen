"""Förbered V2.2:s fyra research-only-ligor med spårbar DB-backfill.

Skriptet gör inga schemaändringar. Det tar en konsistent SQLite-backup och
hämtar därefter:

* resultat från football-data (2024/25 och framåt),
* innevarande Sofascore-resultat/xG,
* dagens ClubElo-ranking för alla sex berörda länder,
* WP9c-lag, arenor och lagens matcher i alla tävlingar.

Körning:
    cd backend && .venv/bin/python -B scripts/forbered_v22_multiliga.py
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import oddset, oddset_data, oddset_schedule, oddset_v22  # noqa: E402
from app.storage import Storage  # noqa: E402


DB = ROOT / "data" / "stryktips.db"
BACKUP = (
    ROOT / "data" / "backups" /
    "stryktips-2026-07-23-fore-v22-multiliga.db"
)
LEAGUES = set(oddset_data.RESEARCH_MODEL_LEAGUES)


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


def _counts(store: Storage) -> dict:
    marks = ",".join("?" for _ in LEAGUES)
    args = sorted(LEAGUES)
    return {
        "results": store.conn.execute(
            f"SELECT COUNT(*) FROM oddset_results WHERE league IN ({marks})",
            args).fetchone()[0],
        "scoped_teams": store.conn.execute(
            f"SELECT COUNT(*) FROM oddset_sofa_team_scope "
            f"WHERE league IN ({marks})", args).fetchone()[0],
        "team_event_captures": store.conn.execute(
            "SELECT COUNT(*) FROM oddset_sofa_team_event_capture"
        ).fetchone()[0],
        "team_events": store.conn.execute(
            "SELECT COUNT(*) FROM oddset_sofa_team_event"
        ).fetchone()[0],
        "elo_history": store.conn.execute(
            f"SELECT COUNT(*) FROM oddset_elo_history "
            f"WHERE country IN ({marks})",
            sorted(oddset_data.ELO_COUNTRIES -
                   {"SWE", "NOR"})).fetchone()[0],
    }


def repair_missing_venues(store: Storage) -> dict:
    repaired, errors = [], []
    for team in store.oddset_sofa_teams():
        if (team["league"] not in LEAGUES or
                (team.get("venue_lat") is not None and
                 team.get("venue_lon") is not None)):
            continue
        try:
            raw = (oddset_data._sofa_get(
                f"/team/{team['team_id']}").get("team") or {})
            parsed = oddset_schedule._team_entry(
                raw, detail_at=oddset_data._now().strftime("%Y-%m-%dT%H:%M:%SZ"))
            if not parsed or parsed.get("venue_lat") is None:
                raise ValueError("källor saknar verifierad koordinat")
            store.oddset_save_sofa_team(parsed, parsed["detail_fetched_at"])
            repaired.append(team["team_id"])
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"{team['team_id']} {team['name']}: {type(exc).__name__}: {exc}")
    return {"repaired_team_ids": repaired, "errors": errors}


def run(store: Storage) -> dict:
    before = _counts(store)
    results = oddset_data.refresh_results(store, force=True)
    xg = oddset_data.refresh_xg(store, force=True)
    elo = oddset_data.refresh_elo(store, force=True)
    schedule = oddset_schedule.refresh(
        store, force=True, backfill=True, leagues=LEAGUES)
    venues = repair_missing_venues(store)
    after = _counts(store)
    integrity = store.conn.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "leagues": sorted(LEAGUES),
        "before": before, "after": after,
        "delta": {key: after[key] - before[key] for key in before},
        "results": {key: value for key, value in results.items()
                    if key in LEAGUES},
        "xg": {key: value for key, value in xg.items() if key in LEAGUES},
        "elo_current_rows": elo,
        "schedule": schedule, "venues": venues,
        "v22": {
            "shadow_version": oddset_v22.shadow_version(),
            "feature_version": oddset_v22.feature_version(store),
            "model_source_version": oddset_v22.model_source_version(store),
        },
        "integrity": integrity,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--venues-only", action="store_true")
    parser.add_argument("--odds-only", action="store_true")
    args = parser.parse_args()
    backed_up = backup_database(DB, BACKUP)
    store = Storage()
    try:
        if args.venues_only:
            report = {
                "venues": repair_missing_venues(store),
                "integrity": store.conn.execute(
                    "PRAGMA integrity_check").fetchone()[0],
            }
        elif args.odds_only:
            configs = [league for league in oddset.LEAGUES
                       if league.get("research_only")]
            report = oddset.collect(store, leagues=configs, deep=False)
            report["integrity"] = store.conn.execute(
                "PRAGMA integrity_check").fetchone()[0]
        else:
            report = run(store)
    finally:
        store.close()
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
