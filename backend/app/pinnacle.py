"""Pinnacle som sharp-källa via deras publika "Arcadia"-API (samma som
pinnacle.se använder). Gratis och utan credit-system — och täcker bl.a.
internationella vänskapsmatcher som the-odds-api saknar.

Två gratis-anrop räcker för hela utbudet:
  GET /sports/29/matchups          -> alla soccer-matcher (sport 29 = Soccer)
  GET /sports/29/markets/straight  -> alla raka marknader (vi tar moneyline)

Odds returneras i amerikanskt format och konverteras till decimalodds.
Inofficiellt API — kan ändras utan förvarning.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional

import httpx

from .odds_provider import (_best_side, _hours_apart, english_name,
                            COMBINED_MIN, HOME_AWAY_MIN, TIME_WINDOW_H)
from .derive import derive_1x2, goal_expectations

BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
GUEST_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # publik guest-nyckel som webben använder
SOCCER = 29
HEADERS = {"X-API-Key": GUEST_KEY, "User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def cache_adjusted_iso(retrieved_at: str, age_s) -> str:
    """Returnera CDN-objektets ungefärliga observationstid i UTC.

    Arcadias bulkendpoints exponerar HTTP `Age`. Utan korrigering får ett
    kvartsgammalt objekt felaktigt en ny observationsstämpel vid varje poll.
    """
    parsed = dt.datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    try:
        seconds = max(0.0, float(age_s or 0))
    except (TypeError, ValueError):
        seconds = 0.0
    observed = parsed.astimezone(dt.timezone.utc) - dt.timedelta(seconds=seconds)
    return observed.strftime("%Y-%m-%dT%H:%M:%SZ")


def american_to_decimal(a: Optional[float]) -> Optional[float]:
    if a is None:
        return None
    return round(1 + a / 100, 2) if a > 0 else round(1 + 100 / (-a), 2)


class Pinnacle:
    def __init__(self, timeout: float = 30.0):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS)
        # Ålder (sekunder) på CDN-objektet i senaste lyckade svar — se _get.
        self.last_age_s = 0

    def reset_cache_age(self) -> None:
        """Nollställ före ett logiskt anropsblock."""
        self.last_age_s = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _get(self, path: str):
        # Försök igen vid tillfälliga nätfel (launchd-pollen råkade ut för
        # ConnectError ibland). OBS: Cloudflare ger periodvis 403 (HTML) för
        # datacenter-/VPN-IP:n — det är IP-baserat, headers/TLS hjälper EJ.
        # Vi retryar inte 403 (lönlöst) utan låter den bubbla → sharp_service
        # fångar, loggar block i meta och degraderar.
        last = None
        for attempt in range(3):
            try:
                r = self._client.get(f"{BASE}{path}")
                r.raise_for_status()
                # CDN-CACHE (uppmätt 2026-07-24): bulk-endpointerna svarar
                # `cache-control: public, max-age=905` och objektet är ofta
                # redan flera minuter gammalt (observerat age=469 s). Priset
                # vi ser kan alltså vara upp till ~15 min äldre än hämtningen
                # — hämtningstid ≠ pristid, samma klass av fel som pit-v1:s
                # förändringstid ≠ observationstid. Bokför åldern så att
                # färskhetsregler och PIT-capture kan korrigera för den i
                # stället för att anta att svaret är färskt. Konsekvens för
                # kadensen: snabbvarv oftare än ~15 min ger Pinnacle SAMMA
                # objekt igen (se FAST_SLEEP_S i oddset.py).
                try:
                    age_s = max(0, int(r.headers.get("age") or 0))
                except (TypeError, ValueError):
                    age_s = 0
                self.last_age_s = age_s
                return r.json()
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise last

    def soccer_index(self, include_without_odds: bool = False) -> list[dict]:
        """Alla soccer-matcher i decimalodds (2 gratis-anrop).

        Använder Pinnacles moneyline (1X2) i första hand; saknas den men spread+
        total finns härleds 1X2 (odds_source='derived'). include_without_odds=True
        tar även med matcher helt utan odds — för coverage-status."""
        self.reset_cache_age()
        matchups = self._get(f"/sports/{SOCCER}/matchups")
        markets = self._get(f"/sports/{SOCCER}/markets/straight")
        ml: dict = {}
        spread: dict[int, list] = {}
        total: dict[int, list] = {}
        for x in markets:
            if x.get("period") != 0:
                continue
            mid, t = x.get("matchupId"), x.get("type")
            if t == "moneyline":
                ml[mid] = x
            elif t == "spread":
                spread.setdefault(mid, []).extend(x.get("prices", []))
            elif t == "total":
                total.setdefault(mid, []).extend(x.get("prices", []))

        out: list[dict] = []
        for m in matchups:
            if m.get("parent") is not None or m.get("type") != "matchup":
                continue
            parts = {p.get("alignment"): p.get("name") for p in m.get("participants", [])}
            home, away = parts.get("home"), parts.get("away")
            if not home or not away:
                continue
            mid = m["id"]
            mk = ml.get(mid)
            if mk:
                prices = {p["designation"]: american_to_decimal(p.get("price"))
                          for p in mk.get("prices", [])}
                odds = {"1": prices.get("home"), "X": prices.get("draw"), "2": prices.get("away")}
                source = "pinnacle"
            else:
                odds = derive_1x2(spread.get(mid, []), total.get(mid, []))
                source = "derived" if odds else None
                odds = odds or {"1": None, "X": None, "2": None}
            has_odds = odds["1"] is not None or odds["2"] is not None
            if not has_odds and not include_without_odds:
                continue
            # förväntade mål (för Bombens resultatmodell) ur spread+total
            xg = goal_expectations(spread.get(mid, []), total.get(mid, []))
            out.append({"home": home, "away": away, "start": m.get("startTime"),
                        "odds": odds, "odds_source": source,
                        "home_xg": round(xg[0], 3) if xg else None,
                        "away_xg": round(xg[1], 3) if xg else None})
        return out

    def match(self, home: str, away: str, home_iso: Optional[str],
              away_iso: Optional[str], index: list[dict],
              match_start: Optional[str] = None) -> Optional[dict]:
        """Bästa matchande Pinnacle-match (namn via ISO/fuzzy + tidsfönster).

        Testar båda lagorienteringarna; om Pinnacle har hemma/borta omvänt
        speglas oddsen (1↔2) så att '1' alltid = Svenska Spels hemmalag."""
        home_cands = [home, english_name(home_iso)]
        away_cands = [away, english_name(away_iso)]
        best, best_score, best_swapped = None, 0.0, False
        for g in index:
            if match_start:
                gap = _hours_apart(match_start, g.get("start"))
                if gap is None or gap > TIME_WINDOW_H:
                    continue
            # rätt orientering
            sh, sa = _best_side(home_cands, g["home"]), _best_side(away_cands, g["away"])
            normal = (sh + sa) / 2 if (sh >= HOME_AWAY_MIN and sa >= HOME_AWAY_MIN) else 0.0
            # omvänd orientering
            sh2, sa2 = _best_side(home_cands, g["away"]), _best_side(away_cands, g["home"])
            swapped = (sh2 + sa2) / 2 if (sh2 >= HOME_AWAY_MIN and sa2 >= HOME_AWAY_MIN) else 0.0
            score, is_swapped = (swapped, True) if swapped > normal else (normal, False)
            if score > best_score:
                best, best_score, best_swapped = g, score, is_swapped
        if not best or best_score < COMBINED_MIN:
            return None
        odds = best["odds"]
        if best_swapped:
            odds = {"1": odds["2"], "X": odds["X"], "2": odds["1"]}
        return {"home": best["home"], "away": best["away"], "start": best.get("start"),
                "odds": odds, "confidence": round(best_score, 3),
                "swapped": best_swapped, "odds_source": best.get("odds_source"),
                # rå xg i Pinnacles orientering — bomben.py speglar vid swapped
                "home_xg": best.get("home_xg"), "away_xg": best.get("away_xg")}
