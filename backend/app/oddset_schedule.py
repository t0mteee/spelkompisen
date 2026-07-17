"""WP9c: Sofascore-lagmatcher i alla tävlingar, vila och reseproxy.

Lagmatcherna är ett separat forskningslager. De påverkar inte live-modellen.
Varje event får `first_seen_at`; en point-in-time-läsning kräver därför både
att matchen spelats och att eventet faktiskt hade observerats vid `as_of`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import time
from typing import Optional

from . import oddset_data
from .oddset import norm_team
from .storage import Storage


EVENT_TTL_H = 20
DETAIL_TTL_H = 24 * 30
DISCOVERY_TTL_H = 20
REGULAR_PAGES = 1
BACKFILL_PAGES = 2
PACE_S = 0.7
SCHEDULE_TEAM_ALIAS = {
    "eliteserien": {"kfum": "kfum oslo", "viking stavanger": "viking"},
    "mls": {"d c united": "dc united"},
}
POLICY = {
    "schema": 1,
    "source": "sofascore-team-events-all-competitions",
    "scope": tuple(sorted(oddset_data.SOFA_UT.items())),
    "team_alias": SCHEDULE_TEAM_ALIAS,
    "pit": "event-start<as-of-and-first-seen<=as-of",
    "history": {"regular_pages": REGULAR_PAGES, "backfill_pages": BACKFILL_PAGES},
    "load_windows_days": (7, 14, 30),
    "rest": "target-kickoff-minus-last-known-kickoff-hours",
    "travel": "club-base-to-club-base-haversine-proxy-no-neutral-venue-claim",
    "model_input": False,
}


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def policy_version() -> str:
    digest = hashlib.sha256(_canonical(POLICY).encode()).hexdigest()[:8]
    return f"wp9c-{digest}"


def _iso(timestamp) -> Optional[str]:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return None
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _fresh(value: Optional[str], now: dt.datetime, ttl_h: float) -> bool:
    if not value:
        return False
    try:
        return (now - _parse(value)).total_seconds() <= ttl_h * 3600
    except ValueError:
        return False


def _paced_get(path: str) -> dict:
    payload = oddset_data._sofa_get(path)
    time.sleep(PACE_S)
    return payload


def _team_entry(raw: dict, detail_at: Optional[str] = None) -> Optional[dict]:
    sport = (raw.get("sport") or {}).get("slug")
    if sport != "football" or raw.get("id") is None or not raw.get("name"):
        return None
    venue = raw.get("venue") or {}
    coordinates = venue.get("venueCoordinates") or {}
    country = raw.get("country") or venue.get("country") or {}
    try:
        lat = float(coordinates["latitude"]) if coordinates.get("latitude") is not None else None
        lon = float(coordinates["longitude"]) if coordinates.get("longitude") is not None else None
    except (TypeError, ValueError):
        lat = lon = None
    return {
        "team_id": int(raw["id"]), "team_key": norm_team(raw["name"]),
        "name": raw["name"], "country_code": country.get("alpha3"),
        "sport": sport, "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "venue_city": (venue.get("city") or {}).get("name"),
        "venue_lat": lat, "venue_lon": lon,
        "detail_fetched_at": detail_at,
    }


def _event_entry(raw: dict, team_id: int) -> Optional[dict]:
    home, away = raw.get("homeTeam") or {}, raw.get("awayTeam") or {}
    sport = ((home.get("sport") or {}).get("slug") or
             (((raw.get("tournament") or {}).get("category") or {})
              .get("sport") or {}).get("slug"))
    if (sport != "football" or raw.get("status", {}).get("type") != "finished" or
            raw.get("id") is None or home.get("id") is None or away.get("id") is None):
        return None
    home_id, away_id = int(home["id"]), int(away["id"])
    if team_id not in (home_id, away_id):
        return None
    start = _iso(raw.get("startTimestamp"))
    if not start:
        return None
    tournament = raw.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    category = tournament.get("category") or {}
    home_score, away_score = raw.get("homeScore") or {}, raw.get("awayScore") or {}
    return {
        "event_id": int(raw["id"]), "start_at": start, "status": "finished",
        "home_team_id": home_id, "away_team_id": away_id,
        "tournament_id": tournament.get("id"),
        "unique_tournament_id": unique.get("id"),
        "tournament_name": unique.get("name") or tournament.get("name"),
        "tournament_slug": unique.get("slug") or tournament.get("slug"),
        "country_code": ((category.get("country") or {}).get("alpha3") or
                         category.get("alpha2")),
        "home_score": home_score.get("normaltime", home_score.get("current")),
        "away_score": away_score.get("normaltime", away_score.get("current")),
    }


def _discover(store: Storage, now: dt.datetime, force: bool,
              leagues: Optional[set[str]] = None) -> dict:
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {"leagues": {}, "teams": 0, "errors": []}
    seen: set[tuple[int, str, int]] = set()
    for league, tournament_id in oddset_data.SOFA_UT.items():
        if leagues is not None and league not in leagues:
            continue
        key = f"oddset_team_discovery_at:{league}"
        if not force and not oddset_data._stale(store, key, DISCOVERY_TTL_H):
            report["leagues"][league] = "fresh"
            continue
        season_id = oddset_data._sofa_season(store, league)
        if not season_id:
            report["leagues"][league] = "ingen säsong"
            continue
        events, successful = [], 0
        for direction in ("next", "last"):
            try:
                payload = _paced_get(
                    f"/unique-tournament/{tournament_id}/season/{season_id}/"
                    f"events/{direction}/0")
                events.extend(payload.get("events") or [])
                successful += 1
            except Exception as exc:  # noqa: BLE001 — ligan retryas nästa pass
                report["errors"].append(
                    f"discovery {league}/{direction}: {type(exc).__name__}")
        added = 0
        for event in events:
            for side in ("homeTeam", "awayTeam"):
                team = _team_entry(event.get(side) or {})
                if not team:
                    continue
                identity = (team["team_id"], league, int(season_id))
                if identity in seen:
                    continue
                store.oddset_save_sofa_team(
                    team, captured_at, league=league, season_id=int(season_id))
                seen.add(identity)
                added += 1
        if successful == 2:
            oddset_data._mark(store, key)
        report["leagues"][league] = {
            "season_id": int(season_id), "source_events": len(events),
            "teams": added, "complete": successful == 2,
        }
        report["teams"] += added
    return report


def refresh(store: Storage, force: bool = False, backfill: bool = False,
            leagues: Optional[set[str]] = None) -> dict:
    """Upptäck ligalag och hämta deras senaste matcher i alla tävlingar.

    Lyckade lag hoppas över individuellt tills TTL löpt ut. Ett lagfel skapar
    ingen capture och retryas därför i nästa ordinarie 30-minuterspass.
    """
    now = oddset_data._now()
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    unknown = set(leagues or ()) - set(oddset_data.SOFA_UT)
    if unknown:
        raise ValueError(f"okända WP9c-ligor: {sorted(unknown)}")
    discovery = _discover(store, now, force or backfill, leagues)
    scoped = store.oddset_sofa_teams()
    teams = {}
    for row in scoped:
        if leagues is not None and row["league"] not in leagues:
            continue
        teams.setdefault(row["team_id"], row)
    report = {
        "policy_version": policy_version(), "discovery": discovery,
        "scoped_teams": len(teams), "details": 0, "teams_due": 0,
        "captures": 0, "events": 0, "errors": list(discovery["errors"]),
    }
    for team_id, stored in sorted(teams.items()):
        if force or not _fresh(stored.get("detail_fetched_at"), now, DETAIL_TTL_H):
            try:
                raw = (_paced_get(f"/team/{team_id}").get("team") or {})
                team = _team_entry(raw, detail_at=captured_at)
                if not team:
                    raise ValueError("inte verifierat fotbollslag")
                store.oddset_save_sofa_team(team, captured_at)
                report["details"] += 1
            except Exception as exc:  # noqa: BLE001 — retrybar separat från events
                report["errors"].append(f"team {team_id}: {type(exc).__name__}")
        latest = store.oddset_sofa_team_latest_capture(team_id)
        if not (force or backfill or not _fresh(latest, now, EVENT_TTL_H)):
            continue
        report["teams_due"] += 1
        pages, raw_events = 0, []
        try:
            max_pages = BACKFILL_PAGES if backfill else REGULAR_PAGES
            for page in range(max_pages):
                payload = _paced_get(f"/team/{team_id}/events/last/{page}")
                pages += 1
                raw_events.extend(payload.get("events") or [])
                if not payload.get("hasNextPage"):
                    break
            events_by_id = {}
            for raw in raw_events:
                event = _event_entry(raw, team_id)
                if event:
                    events_by_id[event["event_id"]] = event
            events = sorted(events_by_id.values(), key=lambda row: (
                row["start_at"], row["event_id"]))
            payload_hash = hashlib.sha256(_canonical(events).encode()).hexdigest()
            store.oddset_save_sofa_team_event_capture({
                "team_id": team_id, "captured_at": captured_at,
                "policy_version": policy_version(),
                "page_count": pages, "raw_event_count": len(raw_events),
                "payload_hash": payload_hash,
            }, events)
            report["captures"] += 1
            report["events"] += len(events)
        except Exception as exc:  # noqa: BLE001 — ingen capture => nästa pass retryar
            report["errors"].append(f"events {team_id}: {type(exc).__name__}")
    return report


def resolve_team(store: Storage, league: str, name: str) -> Optional[dict]:
    """Exakt eller explicit aliasverifierad identitet; aldrig tyst fuzzy."""
    aliases = {**oddset_data._alias_map(store, league),
               **SCHEDULE_TEAM_ALIAS.get(league, {})}
    wanted = aliases.get(norm_team(name), norm_team(name))
    matches = []
    seen = set()
    for row in store.oddset_sofa_teams(league):
        if row["team_id"] in seen:
            continue
        seen.add(row["team_id"])
        candidate = aliases.get(row["team_key"], row["team_key"])
        if candidate == wanted:
            matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _haversine_km(a_lat: float, a_lon: float,
                  b_lat: float, b_lon: float) -> float:
    radius = 6371.0088
    lat1, lat2 = math.radians(a_lat), math.radians(b_lat)
    dlat, dlon = lat2 - lat1, math.radians(b_lon - a_lon)
    value = (math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) *
             math.sin(dlon / 2) ** 2)
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _side_features(events: list[dict], team_id: int, target: dt.datetime,
                   primary_tournament_id: int) -> dict:
    last = events[-1] if events else None
    def count(days: int) -> int:
        cutoff = target - dt.timedelta(days=days)
        return sum(_parse(event["start_at"]) >= cutoff for event in events)
    return {
        "last_match_at": last["start_at"] if last else None,
        "last_tournament": last.get("tournament_name") if last else None,
        "last_was_away": (last.get("away_team_id") == team_id if last else None),
        "rest_hours": (round((target - _parse(last["start_at"])).total_seconds() /
                             3600, 1) if last else None),
        "matches_7d": count(7), "matches_14d": count(14),
        "matches_30d": count(30),
        "outside_primary_14d": sum(
            _parse(event["start_at"]) >= target - dt.timedelta(days=14) and
            event.get("unique_tournament_id") != primary_tournament_id
            for event in events),
    }


def features(store: Storage, league: str, home: str, away: str,
             match_start: str, as_of: str) -> dict:
    """Beräkna ännu icke-modellkopplade, tidsäkra WP9c-features."""
    target, known_at = _parse(match_start), _parse(as_of)
    if known_at >= target:
        raise ValueError("WP9c-features måste fångas före avspark")
    home_team = resolve_team(store, league, home)
    away_team = resolve_team(store, league, away)
    issues = []
    if not home_team:
        issues.append("home_team_identity_missing")
    if not away_team:
        issues.append("away_team_identity_missing")
    payload = {
        "policy_version": policy_version(), "league": league,
        "match_start": match_start, "as_of": as_of,
        "identity": {
            "home_team_id": home_team.get("team_id") if home_team else None,
            "away_team_id": away_team.get("team_id") if away_team else None,
        },
        "home": None, "away": None, "travel_proxy": None, "issues": issues,
    }
    primary = oddset_data.SOFA_UT.get(league)
    for side, team in (("home", home_team), ("away", away_team)):
        if not team or primary is None:
            continue
        history = store.oddset_sofa_team_events_as_of(
            team["team_id"], as_of)
        payload[side] = _side_features(history, team["team_id"], target, primary)
        if not history:
            issues.append(f"{side}_history_missing")
    coordinates = None
    if home_team and away_team:
        values = (home_team.get("venue_lat"), home_team.get("venue_lon"),
                  away_team.get("venue_lat"), away_team.get("venue_lon"))
        if all(value is not None for value in values):
            distance = round(_haversine_km(*map(float, values)), 1)
            coordinates = {
                "mode": "club_base_to_club_base", "neutral_venue_resolved": False,
                "base_distance_km": distance, "home_km": 0.0, "away_km": distance,
            }
        else:
            issues.append("venue_coordinates_missing")
    payload["travel_proxy"] = coordinates
    payload["issues"] = sorted(set(issues))
    return payload


def coverage(store: Storage, now: Optional[dt.datetime] = None) -> dict:
    now = now or oddset_data._now()
    rows = {}
    for league, primary in oddset_data.SOFA_UT.items():
        scoped, teams = store.oddset_sofa_teams(league), {}
        for row in scoped:
            teams.setdefault(row["team_id"], row)
        ids = sorted(teams)
        captures = sum(_fresh(store.oddset_sofa_team_latest_capture(team_id), now,
                              EVENT_TTL_H + 4) for team_id in ids)
        events = []
        if ids:
            marks = ",".join("?" for _ in ids)
            events = [dict(row) for row in store.conn.execute(
                "SELECT DISTINCT * FROM oddset_sofa_team_event WHERE "
                f"home_team_id IN ({marks}) OR away_team_id IN ({marks})",
                ids + ids).fetchall()]
        upcoming = store.oddset_matches(
            since=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            until=(now + dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        league_matches = [match for match in upcoming if match["league"] == league]
        mapped = sum(bool(resolve_team(store, league, match["home"]) and
                          resolve_team(store, league, match["away"]))
                     for match in league_matches)
        rows[league] = {
            "teams": len(ids),
            "venue_coordinates": sum(team.get("venue_lat") is not None and
                                     team.get("venue_lon") is not None
                                     for team in teams.values()),
            "fresh_team_captures": captures,
            "events": len(events),
            "oldest_event": min((event["start_at"] for event in events), default=None),
            "newest_event": max((event["start_at"] for event in events), default=None),
            "tournaments": len({event.get("unique_tournament_id") or
                                ("name", event.get("tournament_name"))
                                for event in events}),
            "outside_primary_events": sum(
                event.get("unique_tournament_id") != primary for event in events),
            "upcoming_matches": len(league_matches), "mapped_matches": mapped,
        }
    return {"policy_version": policy_version(), "leagues": rows}


def format_coverage(report: dict) -> str:
    lines = [f"WP9c {report['policy_version']} · team-events (ej modellinput)"]
    for league, row in report["leagues"].items():
        lines.append(
            f"{league:12} lag {row['teams']:2} · arena {row['venue_coordinates']:2} · "
            f"fresh {row['fresh_team_captures']:2} · event {row['events']:4} · "
            f"tävlingar {row['tournaments']:2} · utanför liga "
            f"{row['outside_primary_events']:3} · kommande mapping "
            f"{row['mapped_matches']}/{row['upcoming_matches']}")
    return "\n".join(lines)
