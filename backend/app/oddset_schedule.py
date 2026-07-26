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
    "obosligaen": {
        "asane fotball": "asane", "egersunds": "egersund",
        "sogndal": "sogndal il", "ranheim": "ranheim il",
        "odd": "odds", "stabaek": "stabak fotball", "hodd": "hodd il",
    },
    "mls": {"d c united": "dc united"},
    "premier_league": {
        "hull": "hull city", "leeds": "leeds united",
        "nottingham": "nottingham forest", "tottenham": "tottenham hotspur",
        "brighton": "brighton & hove albion",
    },
    "serie_a": {
        "napoli": "ssc napoli", "roma": "as roma",
        "internazionale": "inter",
    },
    "la_liga": {
        "racing santander": "real racing club", "levante": "levante ud",
        "dep la coruna": "deportivo de a coruna",
        "deportivo la coruna": "deportivo de a coruna",
        "athletic bilbao": "athletic club",
        "alaves": "deportivo alaves",
    },
    "bundesliga": {
        "stuttgart": "vfb stuttgart",
        "bayer leverkusen": "bayer 04 leverkusen",
        "elversberg": "sv 07 elversberg", "hamburg": "hamburger sv",
        "mainz 05": "1 fsv mainz 05",
        "werder bremen": "sv werder bremen",
    },
}
VENUE_COORD_OVERRIDE = {
    # Sofascore venue 2443 saknar venueCoordinates. Koordinaten verifierades
    # 2026-07-23 mot OpenStreetMap/Nominatim way 28537290.
    2443: {
        "latitude": 50.8615471, "longitude": -0.0836931,
        "source": "openstreetmap:nominatim:way/28537290",
    },
}
# TURNERINGSVIKT (2026-07-25) för "har laget en viktigare match strax efter?".
# Rankingen är en EXPLICIT tabell, aldrig en gissning ur namnet: europeiskt
# gruppspel/slutspel väger tyngst, därefter europakval, sedan inhemsk cup, sedan
# ligan, sist träningsmatcher. Sofascores uniqueTournament-id:n är stabila.
# Okänd turnering får ligans vikt — vi antar aldrig att något är viktigare än
# ligan utan att veta det.
# Id:na är LÄSTA ur vår egen `oddset_sofa_team_event`, inte gissade.
TOURNAMENT_WEIGHT = {
    7: 5,        # UEFA Champions League
    679: 4,      # UEFA Europa League
    17015: 4,    # UEFA Conference League
    465: 4,      # UEFA Super Cup
    498: 4,      # CONCACAF Champions Cup
    853: 0,      # Club Friendly Games
}
# Inhemska cuper i vår data fångas av slug-hintarna nedan: FA Cup (19),
# EFL Cup (21), NM Cup (29), Svenska Cupen (80), US Open Cup (495).
LEAGUE_WEIGHT = 2          # ligan vi analyserar
CUP_WEIGHT = 3             # inhemsk cup (identifieras via country_code + slug)
UNKNOWN_WEIGHT = LEAGUE_WEIGHT
CUP_SLUG_HINTS = ("cup", "cupen", "svenska-cupen", "norgesmesterskapet",
                  "us-open-cup", "coppa", "copa", "pokal")
# Sofascores klocka kan ligga minuter från Kambis för SAMMA match — utan
# marginal blir matchen vi analyserar sin egen "nästa match" (hours_to_next≈0).
# Inget lag spelar två matcher inom sex timmar.
FORWARD_SELF_GUARD_H = 6

# Schema 4 (2026-07-26, granskningsfix F5b): insamlingen tar sedan 2026-07-25
# även notstarted/inprogress och features() bär forwardfälten — det ÄR en
# kontraktsändring och ska synas i versionen, inte smygas in under schema 3.
# Forwardvikterna ingår i fingeravtrycket eftersom de påverkar featurevärdena.
POLICY = {
    "schema": 4,
    "source": "sofascore-team-events-all-competitions",
    "event_status_scope": ("finished", "notstarted", "inprogress"),
    "scope": tuple(sorted(oddset_data.SOFA_UT.items())),
    "team_alias": SCHEDULE_TEAM_ALIAS,
    "team_identity": "explicit-aliases-as-undirected-equivalence-components",
    "venue_coordinate_override": VENUE_COORD_OVERRIDE,
    "pit": ("history:event-start<as-of-and-first-seen<=as-of; "
            "fixtures:first-seen<=as-of-and-start-as-known-at-as-of>as-of"),
    "start_time_series": "oddset_sofa_team_event_start-change-series",
    "history": {"regular_pages": REGULAR_PAGES, "backfill_pages": BACKFILL_PAGES},
    "load_windows_days": (7, 14, 30),
    "rest": "target-kickoff-minus-last-known-kickoff-hours",
    "travel": "club-base-to-club-base-haversine-proxy-no-neutral-venue-claim",
    "forward": {
        "tournament_weight": tuple(sorted(TOURNAMENT_WEIGHT.items())),
        "league_weight": LEAGUE_WEIGHT, "cup_weight": CUP_WEIGHT,
        "unknown_weight": UNKNOWN_WEIGHT, "cup_slug_hints": CUP_SLUG_HINTS,
        "heavier_within_h": 120, "congested_after_days": 7,
        "self_guard_h": FORWARD_SELF_GUARD_H,
    },
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
    override = VENUE_COORD_OVERRIDE.get(venue.get("id"))
    if (lat is None or lon is None) and override:
        lat, lon = override["latitude"], override["longitude"]
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
    # KOMMANDE MATCHER SPARAS OCKSÅ (2026-07-25). Tidigare släpptes bara
    # `finished` igenom, vilket gjorde vilodatan enkelriktad: vi kunde se att ett
    # lag spelat tre matcher på nio dagar, men inte att NÄSTA match är en
    # Champions League-kval om tre dagar — och det är just då lag vilar spelare.
    # Statusen bevaras så PIT-läsningen kan skilja avslutad från planerad. En rad
    # som senare spelas uppdateras till finished via `last_seen_at`, medan
    # `first_seen_at` behåller när vi FÖRST såg fixturen — det är den tiden
    # as-of-läsningen får lita på.
    status_type = (raw.get("status") or {}).get("type")
    if (sport != "football"
            or status_type not in ("finished", "notstarted", "inprogress")
            or raw.get("id") is None or home.get("id") is None
            or away.get("id") is None):
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
        "event_id": int(raw["id"]), "start_at": start,
        "status": ("finished" if status_type == "finished"
                   else "inprogress" if status_type == "inprogress"
                   else "scheduled"),
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
            # KOMMANDE MATCHER (2026-07-25): `last` ger bara spelade matcher, så
            # vilodatan var enkelriktad — vi såg belastningen bakåt men inte att
            # nästa match är en Champions League-kval om tre dagar. Det är just
            # då lag vilar spelare. EN sida räcker: vi behöver nästa match och
            # veckan efter, inte hela säsongen.
            try:
                nxt = _paced_get(f"/team/{team_id}/events/next/0")
                pages += 1
                raw_events.extend(nxt.get("events") or [])
            except Exception as exc:  # noqa: BLE001 — historiken får inte falla
                report["errors"].append(
                    f"next {team_id}: {type(exc).__name__}")
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
    wanted = norm_team(name)
    equivalent = {wanted}
    pending = [wanted]
    while pending:
        current = pending.pop()
        neighbours = {
            right for left, right in aliases.items() if left == current
        } | {
            left for left, right in aliases.items() if right == current
        }
        for neighbour in neighbours - equivalent:
            equivalent.add(neighbour)
            pending.append(neighbour)
    matches = []
    seen = set()
    for row in store.oddset_sofa_teams(league):
        if row["team_id"] in seen:
            continue
        seen.add(row["team_id"])
        if row["team_key"] in equivalent:
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


def tournament_weight(event: dict, primary_tournament_id: int) -> int:
    """Hur tungt väger turneringen mot den liga vi analyserar?"""
    ut = event.get("unique_tournament_id")
    if ut is not None and int(ut) == int(primary_tournament_id):
        return LEAGUE_WEIGHT
    if ut is not None and int(ut) in TOURNAMENT_WEIGHT:
        return TOURNAMENT_WEIGHT[int(ut)]
    slug = (event.get("tournament_slug") or "").casefold()
    if any(hint in slug for hint in CUP_SLUG_HINTS):
        return CUP_WEIGHT
    return UNKNOWN_WEIGHT


def _forward_features(upcoming: list[dict], team_id: int,
                      target: dt.datetime, primary_tournament_id: int) -> dict:
    """Nästa match EFTER den vi analyserar — grunden för rotationsrisk.

    Ett lag med Champions League-kval tre dagar senare vilar spelare i ligan.
    Featuren är beskrivande, inte en prognos: den säger vad som väntar, inte att
    laget kommer att rotera. Bara fixturer som ligger EFTER `target` räknas, och
    bara sådana vi observerat före as-of (filtreringen sker i lagret).
    """
    guard = target + dt.timedelta(hours=FORWARD_SELF_GUARD_H)
    later = [e for e in upcoming if _parse(e["start_at"]) >= guard]
    later.sort(key=lambda e: e["start_at"])
    nxt = later[0] if later else None
    if not nxt:
        return {"next_match_at": None, "hours_to_next": None,
                "next_tournament": None, "next_weight": None,
                "next_is_heavier": None, "congested_after": None}
    hours = round((_parse(nxt["start_at"]) - target).total_seconds() / 3600, 1)
    weight = tournament_weight(nxt, primary_tournament_id)
    return {
        "next_match_at": nxt["start_at"],
        "hours_to_next": hours,
        "next_tournament": nxt.get("tournament_name"),
        "next_weight": weight,
        # tyngre turnering INOM fem dygn = klassisk rotationsrisk
        "next_is_heavier": bool(weight > LEAGUE_WEIGHT and hours <= 120),
        "congested_after": sum(
            _parse(e["start_at"]) <= target + dt.timedelta(days=7)
            for e in later),
    }


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
        # Rotationsrisk: vad väntar EFTER matchen vi analyserar? Läses ur samma
        # PIT-disciplin (first_seen_at <= as_of) och blandas aldrig in i
        # historikfeaturena — de svarar på olika frågor.
        payload[side].update(_forward_features(
            store.oddset_sofa_team_fixtures_as_of(team["team_id"], as_of),
            team["team_id"], target, primary))
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
