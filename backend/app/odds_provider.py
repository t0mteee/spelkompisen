"""Extern oddskälla via the-odds-api.com — komplement för matcher där Svenska
Spel ännu inte satt odds, och som *sharp-referens* (Pinnacle).

Aktiveras genom miljövariabeln ODDS_API_KEY (gratis nyckel: the-odds-api.com).
Utan nyckel är allt avstängt och endpoints svarar {"enabled": false}.

Matchning av lag mellan källorna är heuristisk:
* Landslag: Svenska Spel anger ISO-kod (t.ex. DEU) -> engelskt namn via pycountry,
  så "Tyskland" matchar "Germany".
* Klubbar: fuzzy namnmatchning (difflib).
Vi accepterar bara matchningar över en konfidenströskel och injicerar aldrig
osäkra odds — låg konfidens flaggas istället.
"""
from __future__ import annotations

import datetime as dt
import difflib
import os
import re
import unicodedata
from typing import Optional

import httpx

try:
    import pycountry
except ImportError:  # pragma: no cover
    pycountry = None

API_BASE = "https://api.the-odds-api.com/v4"
SHARP_PREFERENCE = ("pinnacle", "betfair_ex_eu", "marathonbet")
HOME_AWAY_MIN = 0.60     # minsta likhet per sida
COMBINED_MIN = 0.72      # minsta snittlikhet
TIME_WINDOW_H = 36       # extern match måste starta inom X timmar från SS-matchen

# Football-specifika ISO->namn-överstyrningar där pycountry skiljer sig från
# hur oddsbolagen (Pinnacle m.fl.) skriver landslagsnamnen
_ISO_OVERRIDE = {
    "KOR": "South Korea", "PRK": "North Korea", "USA": "USA",
    "GBR": "England", "CZE": "Czech Republic", "RUS": "Russia",
    "IRN": "Iran", "BOL": "Bolivia", "VEN": "Venezuela",
    "CIV": "Ivory Coast", "CPV": "Cape Verde", "CUW": "Curacao",
    "COD": "DR Congo", "TUR": "Turkey", "MKD": "North Macedonia",
}


def api_key() -> Optional[str]:
    return os.environ.get("ODDS_API_KEY")


def enabled() -> bool:
    return bool(api_key())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"\b(fc|if|sk|bk|fk|cf|sc|ac|fk|club|cd)\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def english_name(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    if iso in _ISO_OVERRIDE:
        return _ISO_OVERRIDE[iso]
    if pycountry:
        c = pycountry.countries.get(alpha_3=iso) or pycountry.countries.get(alpha_2=iso)
        if c:
            return getattr(c, "common_name", None) or c.name
    return None


def _parse_time(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours_apart(a: Optional[str], b: Optional[str]) -> Optional[float]:
    ta, tb = _parse_time(a), _parse_time(b)
    if ta is None or tb is None:
        return None
    return abs((ta - tb).total_seconds()) / 3600.0


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# NAMNREGELN (2026-09-14, beslut d i docs/overlamningar/overlamning-2026-09-13-
# pooltackning.md): samma regel som Oddsets identitetsmatchning. Ren
# SequenceMatcher fällde korrekta par där Svenska Spel skriver kortnamnet
# och Pinnacle hela klubbnamnet — `Leeds` mot `Leeds United` 0,588 < 0,60,
# `Nottingham`/`Tottenham` mot `Nottingham Forest`/`Tottenham Hotspur`
# kombinerat 0,716 < 0,72, `Frankfurt` mot `Eintracht Frankfurt`,
# `Sabah Masazir` mot `Sabah FK`. Oddsets `norm_team` (suffix, alias) +
# delsträngsregel tar alla fyra. Skyddet mot falska par är tre lager:
# truppmarkörer är identitet (`Inter` ≠ `Inter U23`), kända falska par ur
# `TEAM_REJECTED_LINKS` fälls alltid, och båda sidorna måste passera var
# för sig inom tidsfönstret. Trösklarna är oförändrade.
_SQUAD_MARKERS = frozenset({"b", "ii", "reserve", "reserves", "academy",
                            "youth", "women", "damer"})
_norm_cache: dict[str, str] = {}
_rejected_pairs: set[frozenset] | None = None


def _norm_team(name: str) -> str:
    cached = _norm_cache.get(name)
    if cached is None:
        from .oddset import norm_team      # lat: oddset importerar pinnacle
        cached = _norm_cache[name] = norm_team(name)
    return cached


def _squad(normalized: str) -> frozenset[str]:
    return frozenset(token for token in normalized.split()
                     if token in _SQUAD_MARKERS
                     or (token.startswith("u") and token[1:].isdigit()))


def _rejected() -> set[frozenset]:
    global _rejected_pairs
    if _rejected_pairs is None:
        from .oddset_data import TEAM_REJECTED_LINKS
        _rejected_pairs = {frozenset(pair) for pairs in TEAM_REJECTED_LINKS.values()
                           for pair in pairs}
    return _rejected_pairs


def team_sim(a: Optional[str], b: Optional[str]) -> float:
    """Namnlikhet 0–1 med Oddsets regel: lika eller delsträng efter
    normalisering ⇒ 1,0; olika truppmarkörer eller känt falskt par ⇒ 0,0;
    annars SequenceMatcher på de normaliserade namnen."""
    if not a or not b:
        return 0.0
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return 0.0
    if _squad(na) != _squad(nb):
        return 0.0
    if frozenset((na, nb)) in _rejected():
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return _ratio(na, nb)


def _best_side(candidates: list[str], target: str) -> float:
    return max((team_sim(c, target) for c in candidates if c), default=0.0)


class ExternalOdds:
    """the-odds-api, credit-snålt: matcha via gratis /events, betala bara odds
    för matchade matcher (1 credit/match med en region)."""

    def __init__(self, regions: str = "eu", timeout: float = 25.0):
        self.regions = regions          # EN region = 1 credit per event
        self._client = httpx.Client(timeout=timeout)
        self.requests_remaining: Optional[str] = None  # uppdateras vid varje anrop

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, path: str, **params):
        params["apiKey"] = api_key()
        r = self._client.get(f"{API_BASE}{path}", params=params)
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            self.requests_remaining = rem
        r.raise_for_status()
        return r.json()

    # --- GRATIS: lista ligor + events ---
    def soccer_sports(self) -> list[str]:
        sports = self._get("/sports")
        return [s["key"] for s in sports
                if s.get("active") and s.get("key", "").startswith("soccer_")]

    def event_index(self, max_sports: int = 25) -> list[dict]:
        """Alla kommande soccer-events (utan odds). Kostar inga credits."""
        index: list[dict] = []
        for sport in self.soccer_sports()[:max_sports]:
            try:
                events = self._get(f"/sports/{sport}/events")
            except httpx.HTTPStatusError:
                continue
            for ev in events:
                index.append({"sport": sport, "id": ev.get("id"),
                              "home": ev.get("home_team"), "away": ev.get("away_team"),
                              "commence_time": ev.get("commence_time")})
        return index

    def match_event(self, home: str, away: str, home_iso: Optional[str],
                    away_iso: Optional[str], index: list[dict],
                    match_start: Optional[str] = None) -> Optional[dict]:
        """Hitta bästa matchande event (ingen kostnad). Returnerar sport+id+konfidens.

        Kräver både namnlikhet och — om match_start anges — att den externa
        matchen startar inom TIME_WINDOW_H timmar. Tidsfönstret stänger ute
        fel fixtures (t.ex. samma lag i en annan omgång)."""
        home_cands = [home, english_name(home_iso)]
        away_cands = [away, english_name(away_iso)]
        best, best_score = None, 0.0
        for ev in index:
            if match_start:
                gap = _hours_apart(match_start, ev.get("commence_time"))
                if gap is None or gap > TIME_WINDOW_H:
                    continue
            sh = _best_side(home_cands, ev["home"])
            sa = _best_side(away_cands, ev["away"])
            if sh < HOME_AWAY_MIN or sa < HOME_AWAY_MIN:
                continue
            score = (sh + sa) / 2
            if score > best_score:
                best, best_score = ev, score
        if not best or best_score < COMBINED_MIN:
            return None
        return {**best, "confidence": round(best_score, 3)}

    # --- KOSTAR 1 credit per anrop ---
    def event_odds(self, sport: str, event_id: str) -> dict[str, dict]:
        ev = self._get(f"/sports/{sport}/events/{event_id}/odds",
                       regions=self.regions, markets="h2h", oddsFormat="decimal")
        home, away = ev.get("home_team"), ev.get("away_team")
        books: dict[str, dict] = {}
        for bk in ev.get("bookmakers", []):
            m = next((mk for mk in bk.get("markets", []) if mk.get("key") == "h2h"), None)
            if not m:
                continue
            o = {x["name"]: x["price"] for x in m.get("outcomes", [])}
            books[bk["key"]] = {"1": o.get(home), "X": o.get("Draw"), "2": o.get(away)}
        return books

    @staticmethod
    def pick_book(books: dict[str, dict]) -> Optional[str]:
        if not books:
            return None
        return next((b for b in SHARP_PREFERENCE if b in books), next(iter(books)))
