"""Read-only readiness-audit för V2.2:s fyra europeiska forskningsligor."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (kambi, oddset_data, oddset_model, oddset_schedule, oddset_v2,
                 oddset_v22)  # noqa: E402
from app.oddset import LEAGUES  # noqa: E402
from app.storage import Storage  # noqa: E402


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(store: Storage, use_stored: bool = False) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    configs = [league for league in LEAGUES if league.get("research_only")]
    matches, errors = [], []
    if use_stored:
        matches = [
            {**row, "odds": {}} for row in store.oddset_matches(
                since=_iso(now))
            if row["league"] in oddset_data.RESEARCH_MODEL_LEAGUES and
            row.get("pinnacle_id") and row.get("kambi_id")
        ]
    else:
        for league in configs:
            try:
                rows = kambi.league_events(league["kambi"], strict=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{league['key']}: {type(exc).__name__}: {exc}")
                rows = []
            matches.extend({
                "id": f"audit:{league['key']}:{row['id']}",
                "league": league["key"], "home": row["home"], "away": row["away"],
                "start": row["start"], "odds": {},
            } for row in rows if row.get("start") and row["start"] > _iso(now))
    oddset_model.attach_model(
        store, matches, allowed_leagues=set(oddset_data.RESEARCH_MODEL_LEAGUES),
        fit_pools=oddset_v22.FIT_POOLS)
    builder = oddset_v2.FeatureBuilder(store, fit_pools=oddset_v22.FIT_POOLS)
    rows = []
    for match in matches:
        capture = {
            "match_id": match["id"], "horizon": "audit",
            "signal_version": "read-only", "match_start": match["start"],
            "captured_at": _iso(now), "target_at": _iso(now),
        }
        base = builder.payload(match, capture, "audit")
        schedule = oddset_schedule.features(
            store, match["league"], match["home"], match["away"],
            match["start"], _iso(now))
        issues = []
        if not match.get("model"):
            issues.append("standalone_model_missing")
        if not base["identity"]["all_fit_links_verified"]:
            issues.append("fit_identity")
        if not base["identity"]["all_elo_links_verified"]:
            issues.append("elo_identity")
        if schedule["issues"]:
            issues.extend(f"wp9c:{issue}" for issue in schedule["issues"])
        missing_base = sorted(
            key for key, value in base["features"].items() if value is None)
        if missing_base:
            issues.extend(f"feature:{key}" for key in missing_base)
        rows.append({
            "league": match["league"], "home": match["home"],
            "away": match["away"], "start": match["start"],
            "fit_home": base["identity"]["fit_home"],
            "fit_away": base["identity"]["fit_away"],
            "elo_home": base["identity"]["elo_home"],
            "elo_away": base["identity"]["elo_away"],
            "wp9c_identity": schedule["identity"],
            "issues": sorted(set(issues)),
        })
    by_league = {}
    for league in oddset_data.RESEARCH_MODEL_LEAGUES:
        subset = [row for row in rows if row["league"] == league]
        by_league[league] = {
            "fixtures": len(subset),
            "complete": sum(not row["issues"] for row in subset),
            "issue_rows": sum(bool(row["issues"]) for row in subset),
        }
    return {
        "as_of": _iso(now), "by_league": by_league,
        "complete": sum(not row["issues"] for row in rows),
        "fixtures": len(rows), "errors": errors,
        "issues": [row for row in rows if row["issues"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--stored", action="store_true")
    args = parser.parse_args()
    store = Storage()
    try:
        report = run(store, use_stored=args.stored)
        if args.compact:
            report["issues"] = [{
                "league": row["league"], "home": row["home"],
                "away": row["away"], "issues": row["issues"],
            } for row in report["issues"]]
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
