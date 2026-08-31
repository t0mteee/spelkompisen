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


def _totals_by_child(markets: list[dict]) -> tuple[dict[int, list[dict]], set[int]]:
    """Öppna helmatchs-totaler per matchup-id, plus vilka som ÖVER HUVUD TAGET
    hade en totalmarknad.

    Skillnaden bär statusen: en matchup som saknas i `seen_total` har ingen
    totalmarknad (`not_offered`), medan en som finns där men saknar öppna
    priser är suspenderad. Delas av bulkvägen och per-matchup-vägen så att de
    två aldrig kan tolka samma payload olika.
    """
    by_child: dict[int, list[dict]] = {}
    seen_total: set[int] = set()
    for market in markets:
        if market.get("period") != 0 or market.get("type") != "total":
            continue
        child_id = market.get("matchupId")
        if child_id is None:
            continue
        seen_total.add(child_id)
        if str(market.get("status") or "open").lower() != "open":
            continue
        sides: dict[float, dict] = {}
        for price in market.get("prices") or []:
            side = price.get("designation")
            if side not in {"over", "under"}:
                continue
            try:
                line = float(price["points"])
                decimal = american_to_decimal(price.get("price"))
            except (KeyError, TypeError, ValueError):
                continue
            if decimal is not None:
                sides.setdefault(line, {})[side] = decimal
        for line, pair in sides.items():
            if pair.get("over") and pair.get("under"):
                by_child.setdefault(child_id, []).append({
                    "line": line, "O": pair["over"], "U": pair["under"],
                })
    return by_child, seen_total


def _moneylines_by_child(markets: list[dict]) -> tuple[dict[int, dict], set[int]]:
    """Öppna helmatchs-1X2 per live-matchup, plus observerade marknader.

    Pinnacles livefeed innehåller även tvåvägs-moneylines och specialmarknader.
    Bara period 0 med de tre uttryckliga designationerna home/draw/away är
    matchens 1X2. En stängd eller ofullständig marknad får aldrig bli pris.
    """
    by_child: dict[int, dict] = {}
    seen: set[int] = set()
    for market in markets:
        if market.get("period") != 0 or market.get("type") != "moneyline":
            continue
        child_id = market.get("matchupId")
        if child_id is None:
            continue
        prices = {price.get("designation"): american_to_decimal(price.get("price"))
                  for price in market.get("prices") or []
                  if price.get("designation") in {"home", "draw", "away"}}
        # En moneyline utan alla tre designationer kan vara en annan
        # speltyp. Den räknas inte ens som observerad 1X2.
        if not all(prices.get(side) for side in ("home", "draw", "away")):
            continue
        seen.add(child_id)
        if str(market.get("status") or "open").lower() != "open":
            continue
        by_child[child_id] = {
            "1": prices["home"], "X": prices["draw"], "2": prices["away"],
        }
    return by_child, seen


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
        #
        # `Cache-Control: no-cache` PRÖVADES 2026-08-18 och gör INGENTING:
        # samma matchup gav 49/49/49 s och 224/224/224 s med och utan headern.
        # De enda nollorna kom när VÅR egen miss populerade cachen. Lägg inte
        # tillbaka den i tron att den ger ett färskare pris.
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
        totals_by_match, _seen_totals = _totals_by_child(markets)

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
            total_offers = totals_by_match.get(mid) or []
            main_total = min(
                total_offers,
                key=lambda offer: abs(offer["O"] - 2.0)
                + abs(offer["U"] - 2.0),
                default=None,
            )
            out.append({"home": home, "away": away, "start": m.get("startTime"),
                        "odds": odds, "odds_source": source,
                        "total": main_total,
                        "home_xg": round(xg[0], 3) if xg else None,
                        "away_xg": round(xg[1], 3) if xg else None})
        return out

    def refresh_live_total(self, matchup_ids: list[str]) -> Optional[dict]:
        """Hämta EN matchs live-totaler direkt, förbi bulkens CDN-fönster.

        UPPMÄTT 2026-08-18. Bulkvägarna `/matchups/live` och
        `/markets/live/straight` bär samma `max-age=905` som prematch-bulken.
        Observerade åldrar i ett enda anropsblock: 791 s respektive 47 s. Vid
        en slumpmässig tidpunkt i cachecykeln är åldern ungefär likformig över
        0–905 s, alltså i snitt ~450 s — och `PINNACLE_LIVE_MAX_AGE_S` är 90.
        Bulkpriset diskvalificerades därför som för gammalt i ungefär nio fall
        av tio, vilket gjorde Pinnacle till en nästan tom kolumn i live-facitet.

        Per-matchup-vägen är en annan och kortare cache: `max-age=419`, och vid
        miss saknas `age`-headern helt (mätt på tre av fyra live-matcher; den
        fjärde var i själva verket prematch och kom ur 905-cachen). Ett förnyat
        anrop 20 s senare gav `age=20` — räknaren tickade alltså från VÅR
        hämtning, svaret kom färskt från origin.

        Uppmätt effekt i drift samma dag, fyra samtidiga livematcher: bulken
        340 s för alla fyra (alltså `stale` rakt igenom), per-matchup 82, 181,
        233 och 391 s. På Vélez Sarsfield–Defensa y Justicia skilde sig inte
        bara åldern utan LINAN: bulken bar Ö2,5 @ 1,89 medan den färska var
        Ö2,25 @ 1,78. Bulkpriset var alltså inte ett gammalt pris på rätt lina
        utan ett pris på en lina som marknaden lämnat.

        Det här är en förbättring, inte en lösning: medianåldern ligger
        fortfarande över `PINNACLE_LIVE_MAX_AGE_S`. Att sänka kravet i stället
        vore att flytta bevisribban för att få mer data att kvalificera sig.

        Anropet görs bara för matcher som faktiskt bär en signal (~11 per dygn),
        så kostnaden är några 8 kB-svar per varv. Returnerar None när inget
        anrop lyckades; anroparen behåller då bulkobservationen.
        """
        for matchup_id in matchup_ids:
            try:
                markets = self._get(f"/matchups/{matchup_id}/markets/straight")
            except Exception:  # noqa: BLE001 — en död matchup får inte fälla varvet
                continue
            age_s = self.last_age_s
            by_child, seen_total = _totals_by_child(markets)
            offers_by_line: dict[float, dict] = {}
            for offers in by_child.values():
                for offer in offers:
                    offers_by_line.setdefault(float(offer["line"]), offer)
            offers = sorted(offers_by_line.values(), key=lambda x: x["line"])
            main = min(offers, key=lambda x: abs(x["O"] - 2.0) + abs(x["U"] - 2.0),
                       default=None)
            if not offers and not seen_total:
                # Marknaden fanns inte alls i svaret — pröva nästa barn-id
                # hellre än att skriva "inte erbjuden" på en halv observation.
                continue
            return {
                "status": "captured" if main else "suspended",
                "ou": main, "offers": offers, "age_s": age_s,
            }
        return None

    def refresh_live_1x2(self, matchup_ids: list[str]) -> Optional[dict]:
        """Färskt live-1X2 för en redan identifierad fysisk match.

        Samma per-matchup-väg som totalsrefreshern används för att undvika
        bulkens cirka 15 minuter långa cache. Alla barn provas: ett
        ``danger_zone``-barn kan vara stängt samtidigt som ``live_delay`` är
        öppet. Returen bär HTTP Age så anroparen kan avslå gamla priser.
        """
        captured = []
        suspended_age = None
        for matchup_id in matchup_ids:
            try:
                markets = self._get(f"/matchups/{matchup_id}/markets/straight")
            except Exception:  # noqa: BLE001 — ett dött barn får inte fälla nästa
                continue
            age_s = self.last_age_s
            by_child, seen = _moneylines_by_child(markets)
            for prices in by_child.values():
                captured.append({"status": "captured", "odds": prices,
                                 "age_s": age_s})
            if seen:
                suspended_age = age_s
        if captured:
            # Två live-mode-barn kan båda vara öppna men bära olika CDN-ålder.
            # Den första i bulken är inte nödvändigtvis den färskaste.
            return min(captured, key=lambda item: item["age_s"])
        if suspended_age is not None:
            return {"status": "suspended", "odds": None,
                    "age_s": suspended_age}
        return None

    def soccer_live_totals(self) -> list[dict]:
        """Pågående fotbollsmatcher och öppna live-totaler.

        Arcadia har separata livevägar. Varje fysisk match kan där förekomma
        som två barn (`live_delay` och `danger_zone`) under samma parent-id.
        Vi grupperar därför på parent-id och föredrar `live_delay`; annars
        skulle samma match bli två kandidater och identitetsvakten korrekt
        stoppa båda. Alla öppna linor behålls så att live-ledgern kan jämföra
        exakt samma lina mellan böcker i stället för att jämföra olika risk.
        `last_age_s` avser marknadssvaret, alltså själva prisets CDN-ålder.
        """
        self.reset_cache_age()
        matchups = self._get(f"/sports/{SOCCER}/matchups/live")
        markets = self._get(f"/sports/{SOCCER}/markets/live/straight")
        market_age_s = self.last_age_s

        by_child, seen_total = _totals_by_child(markets)
        moneyline_by_child, seen_moneyline = _moneylines_by_child(markets)

        grouped: dict[str, list[dict]] = {}
        for matchup in matchups:
            if matchup.get("status") != "started" or matchup.get("type") != "matchup":
                continue
            parent = matchup.get("parent") or {}
            parent_id = str(matchup.get("parentId") or parent.get("id")
                            or matchup.get("id"))
            grouped.setdefault(parent_id, []).append(matchup)

        out = []
        for parent_id, children in grouped.items():
            children.sort(key=lambda item: item.get("liveMode") != "live_delay")
            base = children[0]
            parent = base.get("parent") or {}
            participants = parent.get("participants") or base.get("participants") or []
            names = {p.get("alignment"): p.get("name") for p in participants}
            if not names.get("home") or not names.get("away"):
                continue

            # För varje lina används den föredragna live-mode-raden. Samma
            # provider får aldrig artificiellt konkurrera med sig själv.
            offers_by_line: dict[float, dict] = {}
            for child in children:
                for offer in by_child.get(child.get("id"), []):
                    offers_by_line.setdefault(float(offer["line"]), offer)
            offers = sorted(offers_by_line.values(), key=lambda x: x["line"])
            main = min(
                offers,
                key=lambda x: abs(x["O"] - 2.0) + abs(x["U"] - 2.0),
                default=None,
            )
            had_total = any(child.get("id") in seen_total for child in children)
            odds = next((moneyline_by_child.get(child.get("id"))
                         for child in children
                         if moneyline_by_child.get(child.get("id"))), None)
            had_moneyline = any(child.get("id") in seen_moneyline
                                for child in children)
            out.append({
                "id": parent_id,
                "matchup_ids": [str(child.get("id")) for child in children],
                "home": names["home"], "away": names["away"],
                "start": parent.get("startTime") or base.get("startTime"),
                "status": "captured" if main else (
                    "suspended" if had_total else "not_offered"),
                "ou": main, "offers": offers, "age_s": market_age_s,
                "odds_status": "captured" if odds else (
                    "suspended" if had_moneyline else "not_offered"),
                "odds": odds,
            })
        self.last_age_s = market_age_s
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
                # totalen är orienteringsoberoende och ska följa exakt samma
                # fysiska match som 1X2-träffen.
                "total": best.get("total"),
                # rå xg i Pinnacles orientering — bomben.py speglar vid swapped
                "home_xg": best.get("home_xg"), "away_xg": best.get("away_xg")}
