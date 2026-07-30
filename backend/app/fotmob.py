"""FotMob — live-radarns PRIMÄRA statistikkälla (Samans beslut 2026-07-28).

Varför källan finns: Sofascore saknar xG HELT för Allsvenskan (uppmätt 0/31 i
WP9b), och live-radarns 220-matcherstest visade att en ren skottsignal inte
förutsäger mål. FotMob levererar `expected_goals`, xGOT, xG open play/set play
och stora chanser för både Allsvenskan och Eliteserien — verifierat live
2026-07-25 (Degerfors–Djurgården 62': xG 0,73–1,29, xGOT 0,00–0,76).
Inkopplad som andra öga 25/26; PRIMÄR sedan 28/7 eftersom Sofascore oftast
saknar chansmåtten helt i våra ligor. Sofascore är kvar som reserv och bär
signalen bara när den har strikt bättre statistik (live_radar.payload).

METODGRÄNSER som gäller här:
* **xG blandas ALDRIG mellan providers** (WP9a-regeln). FotMob-data ligger i en
  EGEN tabell med egna id:n; ingen rad blandas med Sofascores, och en radarserie
  för en match använder en och samma provider hela vägen — annars blir
  xG-deltat mellan två ticks skillnaden mellan två modeller, inte mellan två
  minuter.
* **Observationstid per anrop** (🕐-regeln): varje detaljsvar tidsstämplas efter
  sitt eget anrop, aldrig en gång per varv. `Age`-headern dras av när den finns
  (endpointen är `max-age=10`, så den är normalt försumbar — men den läses).
* Shadow: ingenting härifrån får bli tips, Kelly, notiser, CLV eller
  modellinput utan ett nytt uttalat beslut.
* Publika JSON-endpoints, artig timeout, matchtak och tidsbudget. Ingen
  challenge-lösning, inga cookies, ingen DOM-skrapning.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

import httpx

BASE = "https://www.fotmob.com/api/data"
TIMEOUT_S = 8.0          # shadow får aldrig hänga varvet
# Taket höjdes 12→20 (2026-07-28) när träningsmatcherna kom in i scopet,
# och 20→60 samma kväll (Samans beslut) när europacuperna kom in: en
# kvaltorsdag spelar 43 Conference- + 10 EL-matcher samtidigt, alla med
# ligaprioritet 0, så tak 20 hade klippt ~33 cupmatcher — inte friendlies.
# 60 rymmer hela kvällens slate; FotMob är radarns EGEN källa (delas inte
# med den spelbara pipelinen) så kostnaden är ren artighet: värsta fall
# ~60 detaljanrop per varv, sekventiellt, väl inom tidsbudgeten nedan.
# Riktiga ligor sorteras före friendlies (_rank), så ett eventuellt klipp
# tar turnématcher först. Bortklippta räknas i `skipped` och redovisas i
# tick-loggen; inga tysta tak.
MAX_MATCHES = 60         # tak per varv
BUDGET_S = 60.0          # total väggklocka
CAPTURE_VERSION = "fotmob-live-v1"

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 "
                   "Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

# FotMobs liganamn → projektets liganycklar. Explicit tabell, aldrig fuzzy:
# handbolls-läxan gäller även här (ett liganamn kan bära en annan sport).
LEAGUE_NAMES = {
    ("SWE", "Allsvenskan"): "allsvenskan",
    ("SWE", "Superettan"): "superettan",
    ("NOR", "Eliteserien"): "eliteserien",
    ("NOR", "OBOS-ligaen"): "obosligaen",
    ("NOR", "1. Division"): "obosligaen",
    ("USA", "MLS"): "mls",
    # Club Friendlies är GLOBAL (som Sofascores UT 853) och går därför genom
    # samma Oddset-spärr som Sofascore-varvet (_scope_friendlies) — utan den
    # hade varje turnématch i världen ätit varvets matchtak.
    ("INT", "Club Friendlies"): "friendlies",
    # Europacuperna (2026-07-28). FotMob delar upp kval och huvudturnering i
    # SEPARATA ligor (kvalen verifierade live: id 10611/10613/10615) — båda
    # namnen mappas till samma nyckel. Huvudsäsongsnamnen är antagna tills
    # ligafasen startar i september; verifiera då mot dagslistan.
    ("INT", "Champions League"): "champions_league",
    ("INT", "Champions League Qualification"): "champions_league",
    ("INT", "Europa League"): "europa_league",
    ("INT", "Europa League Qualification"): "europa_league",
    ("INT", "Conference League"): "conference_league",
    ("INT", "Conference League Qualification"): "conference_league",
}

# FotMob-statistiknyckel → vår kolumn. Endast kumulativa ALL-värden.
STAT_KEYS = {
    "expected_goals": ("xg_home", "xg_away"),
    "expected_goals_on_target": ("xgot_home", "xgot_away"),
    "expected_goals_open_play": ("xg_open_home", "xg_open_away"),
    "big_chance": ("big_chances_home", "big_chances_away"),
    "total_shots": ("shots_home", "shots_away"),
    "ShotsOnTarget": ("shots_on_home", "shots_on_away"),
    "shots_inside_box": ("shots_inside_home", "shots_inside_away"),
}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _observed_at(response: httpx.Response, requested_at: dt.datetime) -> str:
    """Observationstid = hämtningstid − HTTP Age (🕐-regeln, punkt 2)."""
    try:
        age = int(response.headers.get("age") or 0)
    except ValueError:
        age = 0
    return _iso(requested_at - dt.timedelta(seconds=max(0, age)))


def _f(value) -> Optional[float]:
    """FotMob skickar xG som strängar ('0.73') och skott som heltal."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


class FotMob:
    """Egen HTTP-väg — delas medvetet inte med någon spelbar pipeline."""

    def __init__(self, timeout: float = TIMEOUT_S):
        self._client = httpx.Client(timeout=timeout, headers=_HEADERS,
                                    follow_redirects=True)

    def __enter__(self) -> "FotMob":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def matches(self, date: Optional[dt.date] = None) -> tuple[list[dict], str]:
        """Dagens matcher i VÅRA ligor + observationstiden för listan."""
        day = (date or _now().date()).strftime("%Y%m%d")
        requested_at = _now()
        response = self._client.get(f"{BASE}/matches", params={"date": day})
        response.raise_for_status()
        observed_at = _observed_at(response, requested_at)
        out = []
        for league in (response.json().get("leagues") or []):
            key = LEAGUE_NAMES.get((league.get("ccode"),
                                    (league.get("name") or "").strip()))
            if not key:
                continue
            for match in league.get("matches") or []:
                status = match.get("status") or {}
                out.append({
                    "fotmob_id": match.get("id"),
                    "league": key,
                    "tournament": league.get("name"),
                    "home": (match.get("home") or {}).get("name"),
                    "away": (match.get("away") or {}).get("name"),
                    "start_at": match.get("status", {}).get("utcTime"),
                    "started": bool(status.get("started")),
                    "finished": bool(status.get("finished")),
                    "cancelled": bool(status.get("cancelled")),
                    "minute_label": (status.get("liveTime") or {}).get("short"),
                    "score": status.get("scoreStr"),
                })
        return out, observed_at

    def details(self, fotmob_id) -> tuple[dict, str]:
        """Kumulativ ALL-statistik för en match + dess EGEN observationstid."""
        requested_at = _now()
        response = self._client.get(f"{BASE}/matchDetails",
                                    params={"matchId": fotmob_id})
        response.raise_for_status()
        return response.json(), _observed_at(response, requested_at)


def parse_stats(payload: dict) -> dict:
    """Plocka ALL-periodens kumulativa värden ur matchDetails.

    FotMob upprepar samma nyckel i flera grupper (och ibland med None-värden i
    en rubrikrad). Första kompletta paret vinner; None skriver aldrig över.
    """
    out: dict[str, Optional[float]] = {}
    periods = ((payload.get("content") or {}).get("stats") or {}).get("Periods") or {}
    for group in ((periods.get("All") or {}).get("stats") or []):
        for item in group.get("stats") or []:
            mapping = STAT_KEYS.get(item.get("key"))
            if not mapping:
                continue
            values = item.get("stats") or []
            if len(values) != 2:
                continue
            home, away = _f(values[0]), _f(values[1])
            if home is None or away is None:
                continue
            for column, value in zip(mapping, (home, away)):
                out.setdefault(column, value)
    return out


def parse_minute(payload: dict) -> Optional[int]:
    """Matchminut ur headerns liveTime ('62’'), None när klockan saknas."""
    header = payload.get("header") or {}
    label = ((header.get("status") or {}).get("liveTime") or {}).get("short")
    if not label:
        return None
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    if not digits:
        return None
    try:
        return min(120, int(digits[:3]))
    except ValueError:
        return None


def _start_ts(match: dict) -> Optional[int]:
    """FotMobs utcTime (ISO) → epoksekunder; None när formatet är okänt."""
    raw = match.get("start_at")
    if not raw:
        return None
    try:
        return int(dt.datetime.fromisoformat(
            str(raw).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None


def _scope_friendlies(store, live: list[dict],
                      known_matches: Optional[list[dict]]) -> list[dict]:
    """Släpp bara in träningsmatcher som finns i Oddset — SAMMA delade spärr
    (inkl. spegelvänd hemma/borta) som Sofascore-varvet, tillämpad FÖRE
    detaljanropen så att bortfiltrerade matcher inte kostar trafik."""
    from .live_radar import known_friendly
    if not any(m["league"] == "friendlies" for m in live):
        return live
    if known_matches is None:
        now = _now()
        known_matches = store.oddset_matches(
            _iso(now - dt.timedelta(hours=6)),
            _iso(now + dt.timedelta(hours=6)))
    friendlies = [m for m in known_matches
                  if m.get("league") == "friendlies"]
    return [m for m in live
            if m["league"] != "friendlies"
            or known_friendly(m.get("home") or "", m.get("away") or "",
                              _start_ts(m), friendlies)]


def _rank(match: dict) -> tuple:
    """Riktiga ligor före friendlies, mest kvarvarande speltid först — taket
    ska klippa det som betyder minst, aldrig Allsvenskan (samma princip som
    Sofascore-varvets sortering)."""
    from .live_radar import LEAGUE_PRIORITY
    minute = _minute_from_label(match.get("minute_label")) or 0
    return (LEAGUE_PRIORITY.get(match["league"], 9), minute)


def collect(store, known_matches: Optional[list[dict]] = None,
            date: Optional[dt.date] = None) -> dict:
    """Ett radarvarv mot FotMob — radarns primära källa. Sparar bara
    PÅGÅENDE matcher i våra ligor + Oddset-spärrade träningsmatcher.

    known_matches (Oddset-vyn) kan skickas in av anroparen; annars hämtas
    den ur store när listan innehåller träningsmatcher.
    """
    started_at = time.monotonic()
    saved = skipped = 0
    errors: list[str] = []
    with FotMob() as api:
        try:
            listing, _listed_at = api.matches(date)
        except Exception as exc:                      # noqa: BLE001
            return {"saved": 0, "skipped": 0, "live": 0,
                    "error": f"{type(exc).__name__}: {str(exc)[:80]}"}
        live = [m for m in listing
                if m["started"] and not m["finished"] and not m["cancelled"]]
        live = _scope_friendlies(store, live, known_matches)
        # Dagens lista innehåller även kommande och avslutade matcher. När den
        # lyckats och inte är helt tom kan vi därför säkert registrera vilka
        # tidigare aktiva event som just lämnat live-läget. Payloaden tar då
        # bort dem utan att vänta ut capture-TTL:n; nätfel ändrar ingen state.
        if listing:
            from .live_radar import FOTMOB_PRESENCE_KEY, record_presence
            record_presence(
                store, FOTMOB_PRESENCE_KEY,
                [match.get("fotmob_id") for match in live], _listed_at)
        live.sort(key=_rank)
        for match in live[:MAX_MATCHES]:
            if time.monotonic() - started_at > BUDGET_S:
                skipped += 1
                continue
            try:
                payload, observed_at = api.details(match["fotmob_id"])
            except Exception as exc:                  # noqa: BLE001
                errors.append(f"{match['home']}: {type(exc).__name__}")
                continue
            stats = parse_stats(payload)
            if not stats:
                continue        # ingen statistik = ingen rad, aldrig nollor
            home_goals, away_goals = _score_pair(match.get("score"))
            store.live_fotmob_save({
                "fotmob_id": int(match["fotmob_id"]),
                "captured_at": observed_at,
                "capture_version": CAPTURE_VERSION,
                "league": match["league"],
                "tournament": match["tournament"],
                "home": match["home"], "away": match["away"],
                "start_at": match.get("start_at"),
                "minute": parse_minute(payload) or _minute_from_label(
                    match.get("minute_label")),
                "home_score": home_goals, "away_score": away_goals,
                **stats})
            saved += 1
        skipped += max(0, len(live) - MAX_MATCHES)
    return {"saved": saved, "skipped": skipped, "live": len(live),
            "partial_errors": errors}


def _minute_from_label(label) -> Optional[int]:
    if not label:
        return None
    digits = "".join(ch for ch in str(label) if ch.isdigit())
    return int(digits[:3]) if digits else None


def _score_pair(score) -> tuple[Optional[int], Optional[int]]:
    """'0 - 1' → (0, 1). Okänt format ger (None, None), aldrig gissade nollor."""
    if not score:
        return None, None
    parts = str(score).replace("–", "-").split("-")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except ValueError:
        return None, None
