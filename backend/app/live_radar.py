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

# TAKET (omdimensionerat 2026-07-25). Det gamla taket 14 var satt efter en
# GISSNING om tidsbudgeten. Uppmätt kostar ett statistik-anrop **0,06 s**, så
# 90-sekundersbudgeten räcker till över tusen matcher — tiden var alltså aldrig
# den bindande gränsen, och taket klippte i onödan (43 behöriga
# träningsmatcher en lördag).
#
# Det som ÄR en verklig kostnad är antalet anrop mot en DELAD källa: radarn
# pollar var 5:e minut, så varje matchplats kostar 12 anrop/timme mot Sofascore
# — samma källa som matar den SPELBARA xG-pipelinen och frånvarodatan. Att
# fyrdubbla lasten för en shadow-funktion är precis den risk radarn en gång
# fick egen klient för att undvika.
#
# Lösningen är sortering, inte ett högre tak. Matcher vi REDAN VET saknar
# chansmått läggs sist (`_known_empty_events`), så taket klipper dem i stället
# för Allsvenskan. Uppmätt läge: av ~47 behöriga matcher har ~8 chansdata.
# Med sorteringen räcker 30 platser för ALLA som har data — och de som klipps
# är just de som ändå hade dolts i vyn. Ett tak på 60 hade gett samma SYNLIGA
# lista till dubbla antalet anrop.
# De tomma pollas fortfarande när det finns plats kvar, så vi märker om
# statistik dyker upp sent; ett hårt skip hade gjort oss permanent blinda.
MAX_MATCHES = 30
BUDGET_S = 90.0             # backstopp, inte den styrande gränsen
EMPTY_AFTER_MIN = 25        # först efter denna minut räknas "saknar chansmått"
                            # som ett besked; tidigare är tomt helt normalt


def _live_get(path: str):
    """Sofascore-anrop för radarn — medvetet skild från modellens klient."""
    from curl_cffi import requests as cffi
    r = cffi.get(f"https://api.sofascore.com/api/v1{path}",
                 impersonate="chrome", timeout=LIVE_TIMEOUT_S)
    r.raise_for_status()
    return r.json()

# Träningsmatcher ingår i Oddset men saknar en enda stabil ligaidentitet.
TARGET_UT = {tournament_id: league for league, tournament_id in SOFA_UT.items()}
# Sofascore delar upp träningsmatcher på MÅNGA turneringar. 853 (Club Friendly
# Games) täckte 117 av 463 livematcher 2026-07-25, men de nationella
# träningsturneringarna låg helt utanför radarn: England 20 live, Bulgarien 11,
# Polen 8, Serbien 8, Kroatien 5, Tyskland 5. Alla går genom samma spärr som 853
# (`_known_friendly`) — endast matcher som redan finns i Oddset släpps in.
for _friendly_ut in (853, 35960, 27113, 27120, 32053, 32366, 27118):
    TARGET_UT[_friendly_ut] = "friendlies"
FRIENDLY_UT = frozenset({853, 35960, 27113, 27120, 32053, 32366, 27118})

# Taket delas av ALLA ligor, så en lördag med 43 behöriga träningsmatcher kunde
# tränga ut Allsvenskan helt — och urvalet blev det Sofascore råkade returnera
# först. Riktiga ligor går därför före träningsmatcher, och inom gruppen väljs
# de matcher som har mest kvar att spela (en match i 85:e minuten kan inte längre
# ge en signal).
LEAGUE_PRIORITY = {"allsvenskan": 0, "superettan": 0, "eliteserien": 0,
                   "obosligaen": 0, "mls": 0, "friendlies": 1}

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


def _known_empty_events(store: Storage,
                        now: dt.datetime) -> dict[int, int]:
    """{event_id: 0 har haft chansmått · 2 bevisat tom} ur vår EGEN historik.

    Används bara för att sortera taket rättvist. Matcher som inte finns i
    svaret är okända (tier 1) och behandlas som möjliga — en tidig match utan
    statistik får aldrig straffas för att den är tidig, därför kravet på
    minut > EMPTY_AFTER_MIN i den tomma kategorin.
    """
    since = (now - dt.timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict[int, int] = {}
    for event_id, had, late_empty in store.conn.execute(
            "SELECT event_id, "
            "  MAX(CASE WHEN shots_on_home IS NOT NULL "
            "        OR big_chances_home IS NOT NULL "
            "        OR shots_inside_home IS NOT NULL "
            "        OR xg_home IS NOT NULL THEN 1 ELSE 0 END), "
            "  MAX(CASE WHEN minute > ? AND shots_on_home IS NULL "
            "        AND big_chances_home IS NULL "
            "        AND shots_inside_home IS NULL "
            "        AND xg_home IS NULL THEN 1 ELSE 0 END) "
            "FROM oddset_live_capture WHERE captured_at >= ? GROUP BY event_id",
            (EMPTY_AFTER_MIN, since)):
        if had:
            out[int(event_id)] = 0
        elif late_empty:
            out[int(event_id)] = 2
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
        # EN rad, inte två. "Källan saknar chansmått" + "därför räknas ingen
        # signal" sa samma sak dubbelt, och kortets statsrad visar redan
        # "xG saknas · stora chanser –––". Kvar blir det enda som INTE syns
        # ovanför: att detta är källans gräns, inte vår.
        return {
            "level": "info", "kind": "no_stats", "score": 0.0,
            "remaining_min": remaining,
            "reason": "Källan rapporterar inga skott- eller chansmått.",
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
        # TEXTEN SKA MATCHA SIGNALEN (2026-07-25). "Trycker på" stod på varje
        # kort, även när nivån var FÖLJER — en match i 9:e minuten med ett skott
        # fick alltså en dramatisk mening om ingenting. Nu talar raden bara när
        # det finns ett utstick, och den namnger gapet i stället för att upprepa
        # statsraden. Ordet "proxy" är borta ur korttexten: det är vårt
        # internord, och att xG saknas står redan ovanför. Förbehållet om att
        # skottmåttet är oprövat hör i radarns fotnot, en gång.
        "reason": (
            f"{team}: {big} stora chanser, {on_target} skott på mål "
            f"men {int(goals[index])} mål"
            if active else
            f"{team} leder chansräkningen — inget utstick ännu"),
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
            if unique.get("id") in FRIENDLY_UT and not _known_friendly(
                    event, known_friendlies):
                continue
            scoped.append(event)

    # Tak per varv: en lördagseftermiddag kan ge fler livematcher än vi hinner
    # med inom tickens fem minuter. Hellre ett ärligt redovisat urval än ett
    # varv som drar över och blockerar nästa poolinsamling.
    # URVALET är dock inte längre "de 14 Sofascore råkade lista först" (uppmätt
    # 2026-07-25: 43 behöriga träningsmatcher kunde tränga ut Allsvenskan).
    # Riktiga ligor först, därefter mest återstående speltid.
    known_empty = _known_empty_events(store, now)

    def _rank(event: dict) -> tuple:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        league = TARGET_UT.get(unique.get("id"), "friendlies")
        # 0 = har haft chansmått, 1 = ännu okänt (ny match — får inte straffas
        # för att den är tidig), 2 = bevisat tom efter EMPTY_AFTER_MIN.
        tier = known_empty.get(int(event["id"]), 1)
        return (tier, LEAGUE_PRIORITY.get(league, 9), _minute(event, now) or 0)

    scoped.sort(key=_rank)
    dropped_by_league: dict[str, int] = {}
    for event in scoped[MAX_MATCHES:]:
        unique = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        league = TARGET_UT.get(unique.get("id"), "friendlies")
        dropped_by_league[league] = dropped_by_league.get(league, 0) + 1
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
        # INGA TYSTA TAK: vad som föll bort, och ur vilken liga, ska stå i
        # källhälsan. Ett dolt urval läser som "det här var allt som fanns".
        detail = ", ".join(f"{league} {n}"
                           for league, n in sorted(dropped_by_league.items()))
        note = (f"{skipped} matcher hoppade"
                + (" (tidsbudget)" if budget_hit else " (matchtak)")
                + (f": {detail}" if detail else ""))
        partial = f"{partial}; {note}" if partial else note
    store.oddset_record_source_health(
        "sofascore", "-", "live", captured_at, health_ok, len(scoped), partial)
    store.meta_set("live_radar_last_run", captured_at)
    store.meta_set("live_radar_dropped", ", ".join(
        f"{league} {n} över taket"
        for league, n in sorted(dropped_by_league.items())))
    return {"at": captured_at, "live": len(scoped), "stats_ok": stats_ok,
            "saved": saved, "skipped": skipped, "partial_errors": errors}


def previous_capture(earlier: list[dict],
                     current_at: dt.datetime) -> Optional[dict]:
    """Jämförelsepunkten ~RECENT_MINUTES före observationen, inom tolerans.

    DELAD av API-payloaden och settlementet (app/live_settlement.py): signalens
    15-minutersdelta ska väljas på exakt samma sätt var den än räknas — en
    andra implementation hade förr eller senare divergerat.
    """
    target = current_at - dt.timedelta(minutes=RECENT_MINUTES)
    candidate = min(
        earlier,
        key=lambda row: abs((
            dt.datetime.fromisoformat(
                row["captured_at"].replace("Z", "+00:00")) - target
        ).total_seconds()),
        default=None)
    if candidate is None:
        return None
    candidate_at = dt.datetime.fromisoformat(
        candidate["captured_at"].replace("Z", "+00:00"))
    if abs(candidate_at - target) > dt.timedelta(
            minutes=RECENT_TOLERANCE_MIN):
        return None
    return candidate


def _same_team(a: str, b: str) -> bool:
    """Konservativ namnlänkning MELLAN källor (Sofascore ↔ FotMob).

    `norm_team` klarar 'Degerfors' ↔ 'Degerfors IF' men inte svensk genitiv:
    'Djurgården' ↔ 'Djurgårdens IF' blir djurgarden ↔ djurgardens. Prefixregeln
    med minst fyra tecken täcker det utan att öppna för allmän likhetsmatchning.
    Ingen träff = matchen visas utan FotMob-data; vi gissar aldrig.
    """
    x, y = norm_team(a or ""), norm_team(b or "")
    if len(x) < 4 or len(y) < 4:
        return x == y and bool(x)
    return x.startswith(y) or y.startswith(x)


def _fotmob_series(store: Storage, since: str) -> list[list[dict]]:
    """FotMob-captures grupperade per match, i tidsordning."""
    from .fotmob import CAPTURE_VERSION as FOTMOB_VERSION
    grouped: dict[int, list[dict]] = {}
    for row in store.live_fotmob_captures(since, FOTMOB_VERSION):
        grouped.setdefault(int(row["fotmob_id"]), []).append(row)
    return list(grouped.values())


def _fotmob_for(match: dict, series: list[list[dict]],
                claimed: Optional[set[int]] = None) -> Optional[list[dict]]:
    """Hitta FotMob-serien för en Sofascore-match: samma liga, samma två lag.

    En provider-match får bara kopplas en gång. Om Sofascore råkar innehålla
    dubbletter blir den kvarvarande FotMob-serien i stället ett eget kort,
    aldrig statistik på två olika matcher.
    """
    for captures in series:
        head = captures[-1]
        fotmob_id = int(head["fotmob_id"])
        if claimed is not None and fotmob_id in claimed:
            continue
        if head.get("league") != match.get("league"):
            continue
        if (_same_team(head.get("home"), match.get("home")) and
                _same_team(head.get("away"), match.get("away"))):
            return captures
    return None


_FOTMOB_VIEW_KEYS = (
    "xg_home", "xg_away", "xgot_home", "xgot_away",
    "big_chances_home", "big_chances_away",
    "shots_home", "shots_away",
    "shots_on_home", "shots_on_away",
    "shots_inside_home", "shots_inside_away",
    "minute", "captured_at",
)


def _stats_rank(row: dict) -> int:
    """Ranka faktiskt rapporterad statistik, oberoende av matchklockan."""
    if row.get("xg_home") is not None and row.get("xg_away") is not None:
        return 2
    proxy_keys = (
        "big_chances_home", "big_chances_away",
        "shots_on_home", "shots_on_away",
        "shots_inside_home", "shots_inside_away",
    )
    return 1 if any(row.get(key) is not None for key in proxy_keys) else 0


def _fotmob_signal(captures: list[dict],
                   match_fallback: Optional[dict] = None) -> tuple[dict, dict]:
    """Signal + visningsfält ur en enda, sammanhängande FotMob-serie."""
    current = captures[-1]
    current_at = dt.datetime.fromisoformat(
        current["captured_at"].replace("Z", "+00:00"))
    previous = previous_capture(captures[:-1], current_at)
    signal_row = current
    # FotMob lämnar ibland minuten tom precis i halvtid trots att xG:n är
    # färsk. Klocka och resultattavla är matchmetadata, inte chansmått, och får
    # därför hämtas från den redan verifierade Sofascore-länken. Själva
    # signalens xG/skott kommer fortfarande uteslutande från FotMob-serien.
    if match_fallback and (
            current.get("minute") is None or
            current.get("home_score") is None or
            current.get("away_score") is None):
        signal_row = dict(current)
        for key in ("minute", "home_score", "away_score"):
            if signal_row.get(key) is None:
                signal_row[key] = match_fallback.get(key)
    signal = radar_signal(signal_row, previous)
    signal["stats_source"] = "fotmob"
    signal["xg_source"] = "fotmob" if signal.get("kind") == "xg" else None
    view = {key: current.get(key) for key in _FOTMOB_VIEW_KEYS}
    return signal, view


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
    fotmob_series = _fotmob_series(store, since)
    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["event_id"]), []).append(row)
    matches = []
    claimed_fotmob: set[int] = set()
    for captures in grouped.values():
        current = captures[-1]
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        previous = previous_capture(captures[:-1], current_at)
        signal = radar_signal(current, previous)
        signal["stats_source"] = "sofascore"
        signal["xg_source"] = (
            "sofascore" if signal.get("kind") == "xg" else None)
        extra: dict = {}
        # ANDRA KÄLLAN (2026-07-25/26): Sofascore saknar ofta xG — och kan
        # även sakna ALL chansstatistik — för de nordiska ligorna. FotMob får
        # därför bära HELA signalen även när den bara har skottmått. Valordning:
        # xG > skottproxy > ingen statistik; vid lika bra data behålls
        # Sofascore för att undvika onödiga providerbyten. Provider-rader
        # blandas aldrig: både nuläge och delta kommer från samma serie.
        fm = _fotmob_for(current, fotmob_series, claimed_fotmob)
        if fm:
            fm_current = fm[-1]
            claimed_fotmob.add(int(fm_current["fotmob_id"]))
            fm_signal, extra["fotmob"] = _fotmob_signal(fm, current)
            if _stats_rank(fm_current) > _stats_rank(current):
                signal = fm_signal
        matches.append({**current, **extra, "signal": signal,
                        "is_signal": signal["level"] in {"watch", "strong"}})

    # FotMob är inte bara en statistikreserv för Sofascore. Om Sofascore helt
    # saknar en match men FotMob har en färsk serie ska matchen ändå synas.
    # Detta stänger den sista luckan i löftet "stats finns → kort visas".
    # Det namespacade event-id:t kan aldrig krocka med Sofascores heltals-id.
    for fm in fotmob_series:
        current = fm[-1]
        fotmob_id = int(current["fotmob_id"])
        if fotmob_id in claimed_fotmob:
            continue
        current_at = dt.datetime.fromisoformat(
            current["captured_at"].replace("Z", "+00:00"))
        if now - current_at > dt.timedelta(minutes=MAX_DISPLAY_AGE_MIN):
            continue
        signal, view = _fotmob_signal(fm)
        matches.append({
            **current,
            "event_id": f"fotmob:{fotmob_id}",
            "fotmob": view,
            "signal": signal,
            "is_signal": signal["level"] in {"watch", "strong"},
        })
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
    # DÖLJ MATCHER UTAN MÄTBAR CHANSINFORMATION (Samans beslut 2026-07-25).
    # Skillnaden som gör detta säkert: `no_stats` sätts bara när ALLA
    # chansfält är None, dvs källan rapporterar dem inte alls. En match i
    # 4:e minuten med noll skott har värdet 0, inte None, och får en
    # proxysignal — den döljs alltså aldrig för att den är tidig.
    # Uppmätt: 0 av 56 träningsmatcher har xG och bara 4 har skott, så det här
    # är främst 50-talet försäsongsmatcher som bara rapporterar hörnor.
    # Captures fortsätter samlas — filtret gäller VISNINGEN, inte insamlingen,
    # så täckningsmätningar och framtida facit påverkas inte.
    hidden = [row for row in matches if row["signal"].get("kind") == "no_stats"]
    matches = [row for row in matches if row["signal"].get("kind") != "no_stats"]
    hidden_leagues: dict[str, int] = {}
    for row in hidden:
        league = row.get("league") or "?"
        hidden_leagues[league] = hidden_leagues.get(league, 0) + 1
    return {
        "version": RADAR_VERSION,
        "mode": "shadow",
        "last_run": store.meta_get("live_radar_last_run"),
        "matches": matches,
        "signal_count": sum(row["is_signal"] for row in matches),
        # inga tysta filter: antalet dolda och ur vilka ligor redovisas
        "hidden_no_stats": len(hidden),
        "hidden_by_league": ", ".join(f"{lg} {n}" for lg, n
                                      in sorted(hidden_leagues.items())),
        "coverage": {
            "xg": sum(row["signal"]["kind"] == "xg" for row in matches),
            "proxy": sum(row["signal"]["kind"] == "proxy" for row in matches),
            "fotmob_xg": sum(row["signal"].get("xg_source") == "fotmob"
                             for row in matches),
        },
        # INGA TYSTA TAK: står här av samma skäl som i källhälsan — ett dolt
        # urval läser som "det här var allt som fanns live".
        "dropped": store.meta_get("live_radar_dropped") or "",
        "disclaimer": (
            "Informationsradar. Påverkar inte tips, Kelly, facit eller notiser."),
    }
