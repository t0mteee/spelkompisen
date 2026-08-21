"""FotMob — live-radarns andra statistikkälla (primär 2026-07-28–31).

Varför källan finns: Sofascore saknar xG HELT för Allsvenskan (uppmätt 0/31 i
WP9b), och live-radarns 220-matcherstest visade att en ren skottsignal inte
förutsäger mål. FotMob levererar `expected_goals`, xGOT, xG open play/set play
och stora chanser för både Allsvenskan och Eliteserien — verifierat live
2026-07-25 (Degerfors–Djurgården 62': xG 0,73–1,29, xGOT 0,00–0,76).
Inkopplad som andra öga 25/7 och primär 28–31/7. Flashscore är primär sedan
1/8, men faktisk fälttäckning står alltid över källordningen i
``live_radar.payload``.

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
CAPTURE_VERSION = "fotmob-live-v2"
MAX_SCORE_STATS_SKEW_S = 15

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
    ("ISL", "Besta deild karla"): "bestadeild",
    ("ISL", "Besta deild"): "bestadeild",
    # Aktuellt FotMob-namn 2026-08-09 (id 215). De äldre varianterna finns
    # kvar eftersom providern har växlat namn mellan säsonger/dagslistor.
    ("ISL", "Besta deildin"): "bestadeild",
    ("USA", "MLS"): "mls",
    ("ENG", "Premier League"): "premier_league",
    ("ITA", "Serie A"): "serie_a",
    ("ESP", "LaLiga"): "la_liga",
    ("ESP", "La Liga"): "la_liga",
    ("GER", "Bundesliga"): "bundesliga",
    # Verifierade mot FotMobs dagslistor 2026-08-09–18.
    ("DEN", "Superligaen"): "danish_superliga",
    ("BEL", "Belgian Pro League"): "belgian_pro_league",
    ("POR", "Liga Portugal"): "primeira_liga",
    ("BOL", "Primera División"): "bolivian_primera",
    # Ligue 1 (2026-08-21). Avläst ur FotMobs EGNA dagsfeed, inte gissad:
    # ccode "FRA", ligarubrik "Ligue 1". Ligue 2 är matarliga utan modell och
    # ingår inte i radarscopet.
    ("FRA", "Ligue 1"): "ligue_1",
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
        payload = response.json()
        # TRANSPORTREGELN: status 200 utan den dokumenterade rosterformen är
        # ett källfel, inte ett positivt besked om att inga matcher är live.
        # Framför allt får `{}`/`leagues: null` aldrig tömma presence.
        if (not isinstance(payload, dict) or "leagues" not in payload or
                not isinstance(payload["leagues"], list)):
            raise ValueError("FotMobs dagslista saknar leagues-lista")
        out = []
        for league in payload["leagues"]:
            if not isinstance(league, dict):
                raise ValueError("FotMobs dagslista har ogiltig ligarad")
            key = LEAGUE_NAMES.get((league.get("ccode"),
                                    (league.get("name") or "").strip()))
            if not key:
                continue
            matches = league.get("matches")
            if not isinstance(matches, list):
                raise ValueError(
                    "FotMobs dagslista saknar matchlista för känd liga")
            for match in matches:
                if not isinstance(match, dict):
                    raise ValueError("FotMobs dagslista har ogiltig matchrad")
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


def parse_score(payload: dict) -> tuple[Optional[int], Optional[int]]:
    """Ställning ur SAMMA matchDetails-svar som minut och statistik."""
    status = (payload.get("header") or {}).get("status") or {}
    return _score_pair(status.get("scoreStr"))


def _at(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


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
    """Ett radarvarv mot FotMob — radarns andra källa. Sparar bara
    PÅGÅENDE matcher i våra ligor + Oddset-spärrade träningsmatcher.

    known_matches (Oddset-vyn) kan skickas in av anroparen; annars hämtas
    den ur store när listan innehåller träningsmatcher.
    """
    started_at = time.monotonic()
    saved = skipped = stats_ok = 0
    errors: list[str] = []
    with FotMob() as api:
        try:
            listing, _listed_at = api.matches(date)
        except Exception as exc:                      # noqa: BLE001
            checked_at = _iso(_now())
            error = f"{type(exc).__name__}: {str(exc)[:80]}"
            store.oddset_record_source_health(
                "fotmob", "-", "live", checked_at, False, 0, error)
            return {"saved": 0, "skipped": 0, "live": 0,
                    "health_ok": False, "error": error}
        def active(rows: list[dict]) -> list[dict]:
            return _scope_friendlies(store, [
                m for m in rows if m["started"] and not m["finished"]
                and not m["cancelled"]], known_matches)

        live = active(listing)
        # Dagens lista innehåller även kommande och avslutade matcher. När den
        # lyckats och inte är helt tom kan vi därför säkert registrera vilka
        # tidigare aktiva event som just lämnat live-läget. Payloaden tar då
        # bort dem utan att vänta ut capture-TTL:n; nätfel ändrar ingen state.
        from .live_radar import FOTMOB_PRESENCE_KEY, record_presence
        record_presence(
            store, FOTMOB_PRESENCE_KEY,
            [match.get("fotmob_id") for match in live], _listed_at)
        live.sort(key=_rank)
        live_by_id = {str(match["fotmob_id"]): match for match in live}
        for queued in live[:MAX_MATCHES]:
            if time.monotonic() - started_at > BUDGET_S:
                skipped += 1
                continue
            match = live_by_id.get(str(queued["fotmob_id"]))
            if match is None:
                continue
            try:
                payload, observed_at = api.details(match["fotmob_id"])
                stats_ok += 1
            except Exception as exc:                  # noqa: BLE001
                errors.append(f"{match['home']}: {type(exc).__name__}")
                continue
            stats = parse_stats(payload)
            if not stats:
                continue        # ingen statistik = ingen rad, aldrig nollor
            home_goals, away_goals = parse_score(payload)
            if home_goals is None or away_goals is None:
                skew_s = abs((_at(observed_at) - _at(_listed_at)).total_seconds())
                if skew_s > MAX_SCORE_STATS_SKEW_S:
                    # Listans ställning är för gammal för detaljsvarets
                    # statistik. Förnya hela indexet så även kommande
                    # matcher använder den nya listans rad/tid.
                    try:
                        refreshed, refreshed_at = api.matches(date)
                        refreshed_live = active(refreshed)
                        record_presence(
                            store, FOTMOB_PRESENCE_KEY,
                            [item.get("fotmob_id") for item in refreshed_live],
                            refreshed_at)
                        live_by_id = {
                            str(item["fotmob_id"]): item
                            for item in refreshed_live}
                        _listed_at = refreshed_at
                        match = live_by_id.get(str(queued["fotmob_id"]))
                    except Exception as exc:          # noqa: BLE001
                        match = None
                        errors.append(
                            f"{queued['home']}: roster-refresh "
                            f"{type(exc).__name__}")
                    if match is None:
                        continue
                    skew_s = abs(
                        (_at(observed_at) - _at(_listed_at)).total_seconds())
                    if skew_s > MAX_SCORE_STATS_SKEW_S:
                        errors.append(
                            f"{match['home']}: metadata {int(skew_s)} s "
                            "från stats")
                        continue
                home_goals, away_goals = _score_pair(match.get("score"))
            if home_goals is None or away_goals is None:
                # Okänd ställning är inte 0–0 och kan inte ge chansgap.
                continue
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
    checked_at = _iso(_now())
    health_error = "; ".join(errors[:5]) or None
    if live and stats_ok == 0:
        health_error = health_error or "ingen live-match hade läsbar statistik"
    if skipped:
        note = f"{skipped} matcher hoppade över (tidsbudget/matchtak)"
        health_error = f"{health_error}; {note}" if health_error else note
    # En enda lyckad detalj får inte maskera fel för övriga matcher. `ok`
    # betyder en komplett, ren kontroll; feltexten ligger kvar i payload/UI.
    health_ok = (not live or stats_ok > 0) and health_error is None
    store.oddset_record_source_health(
        "fotmob", "-", "live", checked_at, health_ok, len(live), health_error)
    store.meta_set("live_radar_fotmob_last_run", checked_at)
    return {"saved": saved, "skipped": skipped, "live": len(live),
            "stats_ok": stats_ok, "health_ok": health_ok,
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
