"""Shadow-radar för livefotboll: chansskapande som överstiger utdelningen.

Radarn är informationsstöd, inte en spelmodell. Den läser publika, kumulativa
Sofascore-stats för projektets ligor, sparar observerade snapshots och visar
en försiktig xG- eller proxyflagga. Inga liveodds läses och inga automatiska
spel/notiser skapas.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

from .oddset import norm_team
from .oddset_data import SOFA_UT
from .storage import Storage

CAPTURE_VERSION = "sofa-live-v2"
RADAR_VERSION = "chance-gap-shadow-v2"
RECENT_MINUTES = 15
RECENT_TOLERANCE_MIN = 6
MAX_DISPLAY_AGE_MIN = 12

# EGEN HTTP-VÄG (2026-07-25). Radarn använde `oddset_data._sofa_get` — samma
# klient som matar xG/hörnor till den SPELBARA modellen. En shadow-funktion som
# pollar var femte minut kunde alltså strypa den spelbara pipelinen om
# Sofascore ratelimitar. Radarn har nu egen kortare timeout, eget matchtak och
# egen tidsbudget så att den varken kan hänga varvet eller äta källkvoten.
LIVE_TIMEOUT_S = 8.0        # kortare än modellens 20 s — shadow får inte hänga
MAX_MATCHES = 14            # tak per varv; överskjutande rapporteras
BUDGET_S = 90.0             # total väggklocka för ett radarvarv


def _live_get(path: str):
    """Sofascore-anrop för radarn — medvetet skild från modellens klient."""
    from curl_cffi import requests as cffi
    r = cffi.get(f"https://api.sofascore.com/api/v1{path}",
                 impersonate="chrome", timeout=LIVE_TIMEOUT_S)
    r.raise_for_status()
    return r.json()

# Träningsmatcher ingår i Oddset men saknar en enda stabil ligaidentitet.
TARGET_UT = {tournament_id: league for league, tournament_id in SOFA_UT.items()}
TARGET_UT[853] = "friendlies"

STAT_KEYS = {
    "expectedGoals": ("xg_home", "xg_away"),
    "bigChanceCreated": ("big_chances_home", "big_chances_away"),
    "totalShotsOnGoal": ("shots_home", "shots_away"),
    "shotsOnGoal": ("shots_on_home", "shots_on_away"),
    "totalShotsInsideBox": ("shots_inside_home", "shots_inside_away"),
    "touchesInOppBox": ("touches_box_home", "touches_box_away"),
    "cornerKicks": ("corners_home", "corners_away"),
}


def _iso(timestamp: Optional[int]) -> Optional[str]:
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(
        int(timestamp), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _score(event: dict, side: str) -> int:
    value = (event.get(f"{side}Score") or {}).get("current")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _minute(event: dict, now: dt.datetime) -> Optional[int]:
    status = (event.get("status") or {}).get("description") or ""
    label = status.casefold()
    if "halftime" in label or "half time" in label:
        return 45
    if "finished" in label or "ended" in label:
        return 90
    period_start = (event.get("time") or {}).get("currentPeriodStartTimestamp")
    if period_start is None:
        return None
    elapsed = max(0, int(now.timestamp()) - int(period_start)) // 60
    if "2nd" in label or "second" in label:
        return min(90, 45 + elapsed)
    if "extra" in label:
        return min(120, 90 + elapsed)
    return min(45, elapsed)


def _all_stats(payload: dict) -> dict[str, tuple[float | int, float | int]]:
    out = {}
    periods = payload.get("statistics") or []
    all_period = next((period for period in periods
                       if period.get("period") == "ALL"), None)
    for group in (all_period or {}).get("groups") or []:
        for item in group.get("statisticsItems") or []:
            key = item.get("key")
            if key not in STAT_KEYS or key in out:
                continue
            home, away = item.get("homeValue"), item.get("awayValue")
            if home is not None and away is not None:
                out[key] = (home, away)
    return out


def _known_friendly(event: dict, known: list[dict]) -> bool:
    """Tränings-UT 853 är global: ta bara matcher som redan finns i Oddset."""
    home = norm_team((event.get("homeTeam") or {}).get("name") or "")
    away = norm_team((event.get("awayTeam") or {}).get("name") or "")
    start = event.get("startTimestamp")
    for match in known:
        if (norm_team(match.get("home") or "") != home or
                norm_team(match.get("away") or "") != away):
            continue
        if start is None or not match.get("start"):
            return True
        try:
            known_start = dt.datetime.fromisoformat(
                match["start"].replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return True
        if abs(known_start - int(start)) <= 2 * 3600:
            return True
    return False


def parse_capture(event: dict, stats_payload: Optional[dict], *,
                  captured_at: str,
                  now: Optional[dt.datetime] = None) -> dict:
    """Normalisera ett liveevent och dess kumulativa ALL-statistik."""
    now = now or dt.datetime.now(dt.timezone.utc)
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    tournament_id = unique.get("id")
    capture = {
        "event_id": int(event["id"]),
        "captured_at": captured_at,
        "capture_version": CAPTURE_VERSION,
        "league": TARGET_UT[int(tournament_id)],
        "tournament": unique.get("name") or tournament.get("name"),
        "home": (event.get("homeTeam") or {}).get("name") or "?",
        "away": (event.get("awayTeam") or {}).get("name") or "?",
        "start_at": _iso(event.get("startTimestamp")),
        "status": (event.get("status") or {}).get("description") or "Live",
        "minute": _minute(event, now),
        "home_score": _score(event, "home"),
        "away_score": _score(event, "away"),
    }
    parsed_stats = _all_stats(stats_payload or {})
    for source_key, (home_key, away_key) in STAT_KEYS.items():
        values = parsed_stats.get(source_key)
        capture[home_key] = values[0] if values else None
        capture[away_key] = values[1] if values else None
    return capture


def _num(row: dict, key: str) -> float:
    value = row.get(key)
    return float(value) if value is not None else 0.0


def radar_signal(current: dict, previous: Optional[dict] = None) -> dict:
    """Härled en tydligt shadow-märkt radarflagga ur observerad statistik."""
    minute = current.get("minute")
    if minute is None:
        return {"level": "info", "kind": "no_clock", "score": 0.0,
                "reason": "Matchklockan saknas i källan."}
    remaining = max(0, 90 - int(minute))
    goals = [_num(current, "home_score"), _num(current, "away_score")]
    xg = [current.get("xg_home"), current.get("xg_away")]
    sides = ("home", "away")

    if all(value is not None for value in xg):
        xg_values = [float(value) for value in xg]
        gaps = [xg_values[i] - goals[i] for i in range(2)]
        index = 0 if gaps[0] >= gaps[1] else 1
        recent_xg = 0.0
        if previous and previous.get(f"xg_{sides[index]}") is not None:
            recent_xg = max(
                0.0, xg_values[index] -
                float(previous[f"xg_{sides[index]}"]))
        total_gap = sum(xg_values) - sum(goals)
        score = max(gaps[index], total_gap * 0.65) + recent_xg * 0.5
        active = (15 <= minute <= 78 and remaining >= 12 and
                  (gaps[index] >= 0.65 or total_gap >= 1.0))
        level = ("strong" if active and
                 (gaps[index] >= 1.15 or total_gap >= 1.65)
                 else "watch" if active else "info")
        team = current["home"] if index == 0 else current["away"]
        return {
            "level": level, "kind": "xg", "team": team,
            "side": sides[index], "score": round(score, 3),
            "chance_gap": round(gaps[index], 2),
            "total_gap": round(total_gap, 2),
            "recent_xg": round(recent_xg, 2),
            "remaining_min": remaining,
            "reason": (
                f"{team}: {xg_values[index]:.2f} xG men "
                f"{int(goals[index])} mål"
                + (f" · +{recent_xg:.2f} xG senaste {RECENT_MINUTES} min"
                   if recent_xg > 0 else "")),
        }

    proxy_keys = (
        "big_chances_home", "big_chances_away",
        "shots_on_home", "shots_on_away",
        "shots_inside_home", "shots_inside_away",
        "touches_box_home", "touches_box_away",
    )
    if all(current.get(key) is None for key in proxy_keys):
        return {
            "level": "info", "kind": "no_stats", "score": 0.0,
            "remaining_min": remaining,
            "reason": "Källan saknar xG och användbara chansmått för matchen.",
            "warning": "Ingen chanssignal räknas från saknade värden.",
        }

    # Allsvenskan saknar ofta xG. Proxyflaggan är medvetet strikt och märks
    # som observationssignal; Claudes 220-matcherstest gav inget stöd för att
    # rena skott förutsäger mål i nästa 15 minuter.
    proxy = []
    for side in sides:
        proxy.append(
            _num(current, f"big_chances_{side}") * 0.40
            + _num(current, f"shots_on_{side}") * 0.12
            + _num(current, f"shots_inside_{side}") * 0.025
            + _num(current, f"touches_box_{side}") * 0.008)
    gaps = [proxy[i] - goals[i] for i in range(2)]
    index = 0 if gaps[0] >= gaps[1] else 1
    side = sides[index]
    big = int(_num(current, f"big_chances_{side}"))
    on_target = int(_num(current, f"shots_on_{side}"))
    inside = int(_num(current, f"shots_inside_{side}"))
    active = (20 <= minute <= 78 and remaining >= 12 and
              (big - goals[index] >= 1.5 or
               (on_target - goals[index] >= 5 and inside >= 8)))
    team = current["home"] if index == 0 else current["away"]
    return {
        "level": "watch" if active else "info",
        "kind": "proxy", "team": team, "side": side,
        # EGET fältnamn: xG-varianten rapporterar `chance_gap` i MÅL. Proxyn
        # är ett enhetslöst index och får därför `proxy_index` — samma namn
        # för olika enheter inbjöd till felläsning.
        "score": round(gaps[index], 3),
        "proxy_index": round(gaps[index], 2),
        "remaining_min": remaining,
        "reason": (
            f"{team}: xG saknas · {big} stora chanser, "
            f"{on_target} skott på mål, {inside} skott i box"),
        "warning": "Proxy – historiken har ännu inte visat prediktiv mållyft.",
    }


def collect(store: Storage, *, now: Optional[dt.datetime] = None) -> dict:
    """Samla ett snapshot för alla pågående matcher i projektets ligor."""
    now = now or dt.datetime.now(dt.timezone.utc)
    started = time.monotonic()
    # `captured_at` för varvet används bara till hälsorad och meta. VARJE
    # capture får sin EGEN observationstid längre ner — annars stämplas sista
    # matchen med loopens starttid. Samma fel som pit-v1 (förändringstid ≠
    # observationstid) och Pinnacles CDN-Age (hämtningstid ≠ pristid); det ska
    # inte återuppstå i varje ny insamlare.
    captured_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    events = _live_get("/sport/football/events/live").get("events") or []
    known = store.oddset_matches(
        (now - dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        (now + dt.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    known_friendlies = [
        match for match in known if match.get("league") == "friendlies"]
    scoped = []
    for event in events:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        if (unique.get("id") in TARGET_UT and
                (event.get("status") or {}).get("type") == "inprogress"):
            if unique.get("id") == 853 and not _known_friendly(
                    event, known_friendlies):
                continue
            scoped.append(event)

    # Tak per varv: en lördagseftermiddag kan ge fler livematcher än vi hinner
    # med inom tickens fem minuter. Hellre ett ärligt redovisat urval än ett
    # varv som drar över och blockerar nästa poolinsamling.
    skipped = max(0, len(scoped) - MAX_MATCHES)
    scoped = scoped[:MAX_MATCHES]

    saved, stats_ok, errors = 0, 0, []
    budget_hit = False
    for event in scoped:
        if time.monotonic() - started > BUDGET_S:
            budget_hit = True
            skipped += 1
            continue
        stats = None
        try:
            stats = _live_get(f"/event/{event['id']}/statistics")
            stats_ok += 1
        except Exception as exc:  # noqa: BLE001 — coverage varierar per liga
            errors.append(f"{event['id']}: {type(exc).__name__}")
        # Observationstid per event, satt EFTER anropet.
        event_at = dt.datetime.now(dt.timezone.utc)
        capture = parse_capture(
            event, stats,
            captured_at=event_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            now=event_at)
        saved += store.oddset_save_live_capture(capture)

    partial = "; ".join(errors[:5]) if errors else None
    health_ok = not scoped or stats_ok > 0
    if scoped and stats_ok == 0:
        partial = partial or "ingen live-match hade läsbar statistik"
    if skipped:
        note = (f"{skipped} matcher hoppade"
                + (" (tidsbudget)" if budget_hit else " (matchtak)"))
        partial = f"{partial}; {note}" if partial else note
    store.oddset_record_source_health(
        "sofascore", "-", "live", captured_at, health_ok, len(scoped), partial)
    store.meta_set("live_radar_last_run", captured_at)
    return {"at": captured_at, "live": len(scoped), "stats_ok": stats_ok,
            "saved": saved, "skipped": skipped, "partial_errors": errors}


def payload(store: Storage, *,
            now: Optional[dt.datetime] = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    # Läs även äldre historik för 15-minutersdeltat, men visa bara matcher vars
    # SENASTE observation är färsk. Annars försvinner jämförelsepunkten just
    # när den behövs eller en femminuterspunkt felmärks som "senaste 15 min".
    since = (now - dt.timedelta(
        minutes=MAX_DISPLAY_AGE_MIN + RECENT_MINUTES +
        RECENT_TOLERANCE_MIN)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    rows = store.oddset_live_captures(since, CAPTURE_VERSION)
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["event_id"]), []).append(row)
    matches = []
    for captures in grouped.values():
        current = captures[-1]
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        target = current_at - dt.timedelta(minutes=RECENT_MINUTES)
        candidate = min(
            captures[:-1],
            key=lambda row: abs((
                dt.datetime.fromisoformat(
                    row["captured_at"].replace("Z", "+00:00")) - target
            ).total_seconds()),
            default=None)
        previous = candidate
        if candidate:
            candidate_at = dt.datetime.fromisoformat(
                candidate["captured_at"].replace("Z", "+00:00"))
            if abs(candidate_at - target) > dt.timedelta(
                    minutes=RECENT_TOLERANCE_MIN):
                previous = None
        signal = radar_signal(current, previous)
        matches.append({**current, "signal": signal,
                        "is_signal": signal["level"] in {"watch", "strong"}})
    # SORTERING (2026-07-25): xG-signalen mäts i MÅL, proxyn är ett enhetslöst
    # viktat index — att ranka dem mot varandra på samma `score` jämför äpplen
    # med päron. Grupperna hålls därför isär: xG-matcher först, proxy under,
    # och sortering på score sker bara INOM en grupp.
    matches.sort(key=lambda row: (
        not row["is_signal"],
        0 if row["signal"]["level"] == "strong" else 1,
        0 if row["signal"].get("kind") == "xg" else 1,
        -float(row["signal"].get("score") or 0),
    ))
    return {
        "version": RADAR_VERSION,
        "mode": "shadow",
        "last_run": store.meta_get("live_radar_last_run"),
        "matches": matches,
        "signal_count": sum(row["is_signal"] for row in matches),
        "coverage": {
            "xg": sum(row["signal"]["kind"] == "xg" for row in matches),
            "proxy": sum(row["signal"]["kind"] == "proxy" for row in matches),
        },
        "disclaimer": (
            "Informationsradar. Påverkar inte tips, Kelly, facit eller notiser."),
    }
