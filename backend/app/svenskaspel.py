"""Klient mot Svenska Spels öppna draw-API.

Endpoints (oinofficiella men publika):
  GET /draw/1/stryktipset/draws          -> alla öppna omgångar (lista)
  GET /draw/1/stryktipset/draws/{num}    -> en specifik omgång med full detalj

Datat innehåller per match: aktuellt odds, startodds (öppning),
svenska folkets streckfördelning (med referensvärde = förra mätningen)
samt provider-id:n (Kambi/BetRadar) som vi kan korsreferera mot andra
oddskällor senare (t.ex. Pinnacle).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

BASE = "https://api.spela.svenskaspel.se"
API_VER = 1  # path-prefix är alltid 1 (API-version), slugen styr produkten

# listing=True: /draw/1/{slug}/draws listar alla omgångar.
# listing=False (topptipset): ingen listnings-route -> vi scannar omgångsnummer
# runt ett känt/cachat nummer (seed = fallback om inget cachat finns).
# "Topptipset" är egentligen flera produkter (visas ihop på svenskaspel.se):
#   topptipset (pid25) dagliga, topptipsetstryk (pid23) helgkupong med
#   Stryktipsets matcher, topptipsetextra (pid24). Var och en har egen nummerserie.
PRODUCTS = {
    "stryktipset":     {"slug": "stryktipset",     "pid": 1,  "listing": True,  "matches": 13, "name": "Stryktipset"},
    "europatipset":    {"slug": "europatipset",    "pid": 2,  "listing": True,  "matches": 13, "name": "Europatipset"},
    "topptipset":      {"slug": "topptipset",      "pid": 25, "listing": False, "matches": 8,  "name": "Topptipset", "seed": 4177},
    "topptipsetstryk": {"slug": "topptipsetstryk", "pid": 23, "listing": False, "matches": 8,  "name": "Topptipset Stryk", "seed": 966},
    "topptipsetextra": {"slug": "topptipsetextra", "pid": 24, "listing": False, "matches": 8,  "name": "Topptipset Extra", "seed": 1840},
}

# Spel-grupper i UI: en flik kan samla flera produkter (delade omgångsväljaren).
GAME_GROUPS = {
    "topptipset": ["topptipset", "topptipsetstryk", "topptipsetextra"],
    "stryktipset": ["stryktipset"],
    "europatipset": ["europatipset"],
}
_HEADERS = {"User-Agent": "Mozilla/5.0 (stryktips-helper/0.1)"}


def _f(v: Optional[str]) -> Optional[float]:
    """Tolka ett svenskt decimaltal ('5,50') eller None till float."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", ".").replace("\xa0", "").strip())
    except ValueError:
        return None


def _i(v: Optional[str]) -> Optional[int]:
    f = _f(v)
    return int(round(f)) if f is not None else None


@dataclass
class Outcome:
    """Ett av tre utfall (1, X, 2) för en match."""
    sign: str               # "1" | "X" | "2"
    odds: Optional[float]   # aktuellt odds
    start_odds: Optional[float]  # öppningsodds
    streck: Optional[int]   # svenska folkets % nu
    streck_ref: Optional[int]    # svenska folkets % vid förra mätningen


@dataclass
class Match:
    event_number: int
    description: str         # "USA - Tyskland"
    home: str
    away: str
    home_iso: Optional[str]   # ISO-landskod (landslag), t.ex. "DEU"
    away_iso: Optional[str]
    league: str
    match_start: Optional[str]
    cancelled: bool
    kambi_id: Optional[str]
    outcomes: dict[str, Outcome]  # nyckel "1"/"X"/"2"


@dataclass
class Draw:
    product: str
    draw_number: int
    state: str              # "Open", "Finalized", ...
    reg_close_time: Optional[str]
    net_sale: Optional[float]
    row_price: Optional[float]
    fetched_at: str
    jackpot: Optional[float] = None     # extrapengar/rullpott till toppnivån
    extra_info: Optional[str] = None    # SvS egen text, t.ex. "Jackpot ca 10 mkr"
    matches: list[Match] = field(default_factory=list)


class SvenskaSpel:
    def __init__(self, timeout: float = 20.0):
        self._client = httpx.Client(timeout=timeout, headers=_HEADERS)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SvenskaSpel":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- råa anrop ---
    def _get(self, path: str) -> dict:
        r = self._client.get(f"{BASE}{path}")
        r.raise_for_status()
        return r.json()

    def _get_or_none(self, path: str) -> Optional[dict]:
        r = self._client.get(f"{BASE}{path}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def bomben_draws(self) -> list[dict]:
        """Råa Bomben-omgångar (annan struktur än tipsspelen: exakt resultat,
        inga odds, folk-fördelning per mål). bomben.py parsar dem."""
        data = self._get_or_none(f"/draw/{API_VER}/bomben/draws")
        return (data or {}).get("draws", []) if data else []

    @staticmethod
    def _summary(raw: dict, product: str) -> dict:
        return {
            "product": product,
            "draw_number": raw.get("drawNumber"),
            "state": raw.get("drawState"),
            "reg_close_time": raw.get("regCloseTime"),
            "comment": raw.get("drawComment"),
            "num_events": len(raw.get("drawEvents", [])),
        }

    def _draw_summary(self, product: str, n: int) -> Optional[dict]:
        slug = PRODUCTS[product]["slug"]
        data = self._get_or_none(f"/draw/{API_VER}/{slug}/draws/{n}")
        if not data:
            return None
        if data.get("draws"):
            raw = data["draws"][0]
        elif data.get("draw"):
            raw = data["draw"]
        else:
            return None
        if not raw.get("drawNumber"):
            return None
        return self._summary(raw, product)

    def _scan_draws(self, product: str, start_hint: Optional[int] = None,
                    back: int = 8, gap: int = 3, max_scan: int = 80) -> list[dict]:
        """Scanna omgångsnummer (för produkter utan listnings-route, t.ex.
        topptipset). Börjar något före start_hint och går framåt tills `gap`
        sammanhängande 404 efter senaste träff.

        back=8: hintet är MAX-numret vi någonsin sett, och Svenska Spel
        publicerar upp till ~5-6 dagliga omgångar i förväg — med back=4
        hamnade DAGENS ännu öppna omgångar under scanfönstret och försvann
        ur omgångsväljaren (buggen 2026-07-24: 4227/4228 saknades medan
        4229–4233 visades)."""
        cfg = PRODUCTS[product]
        start = (start_hint or cfg.get("seed") or 1)
        n = max(1, start - back)
        found: list[dict] = []
        misses = scanned = 0
        while scanned < max_scan:
            s = self._draw_summary(product, n)
            if s is None:
                misses += 1
                if found and misses >= gap:
                    break
            else:
                misses = 0
                found.append(s)
            n += 1
            scanned += 1
        return found

    def list_draws(self, product: str = "stryktipset",
                   start_hint: Optional[int] = None) -> list[dict]:
        """Sammanfattningar av tillgängliga omgångar (sorterade på nummer)."""
        cfg = PRODUCTS[product]
        if cfg["listing"]:
            data = self._get(f"/draw/{API_VER}/{cfg['slug']}/draws")
            draws = [self._summary(d, product) for d in data.get("draws", [])]
        else:
            draws = self._scan_draws(product, start_hint)
        return sorted(draws, key=lambda d: d["draw_number"])

    def open_draws(self, product: str = "stryktipset",
                   start_hint: Optional[int] = None) -> list[dict]:
        return [d for d in self.list_draws(product, start_hint) if d["state"] == "Open"]

    # --- råa payloads (PH1-settlement: hashbara, oparsade) ---
    def raw_draw(self, product: str, draw_number: int) -> Optional[dict]:
        """Rå draw-json för en omgång (draws[0]/draw), eller None vid 404."""
        slug = PRODUCTS[product]["slug"]
        data = self._get_or_none(f"/draw/{API_VER}/{slug}/draws/{draw_number}")
        if not data:
            return None
        raw = (data.get("draws") or [None])[0] if data.get("draws") \
            else data.get("draw")
        return raw if raw and raw.get("drawNumber") else None

    def raw_result(self, product: str, draw_number: int) -> Optional[dict]:
        """Rå result-json (result-objektet), eller None vid 404/tomt."""
        slug = PRODUCTS[product]["slug"]
        data = self._get_or_none(
            f"/draw/{API_VER}/{slug}/draws/{draw_number}/result")
        if not data:
            return None
        result = data.get("result")
        if isinstance(result, list):
            result = result[0] if result else None
        return result or None

    # --- resultat / utdelning ---
    def get_result(self, product: str, draw_number: int) -> Optional[dict]:
        """Utdelning per prisnivå för en avgjord omgång, eller None."""
        slug = PRODUCTS[product]["slug"]
        data = self._get_or_none(f"/draw/{API_VER}/{slug}/draws/{draw_number}/result")
        if not data:
            return None
        r = data.get("result")
        if isinstance(r, list):
            r = r[0] if r else None
        if not r or not r.get("distribution"):
            return None
        tiers = []
        for g in r["distribution"]:
            name = g.get("name", "")
            try:
                correct = int(str(name).split()[0])
            except (ValueError, IndexError):
                correct = None
            tiers.append({"name": name, "correct": correct,
                          "winners": g.get("winners"),
                          "amount": _f(g.get("amount"))})
        # facit: rätt tecken per match (underlag för backtest/kalibrering)
        outcomes: dict[int, str] = {}
        cancelled: list[int] = []
        for e in (r.get("events") or []):
            en = e.get("eventNumber")
            if e.get("cancelled"):
                cancelled.append(en)
            if e.get("outcome") in ("1", "X", "2"):
                outcomes[en] = e["outcome"]
        return {"draw_number": draw_number, "outcomes": outcomes,
                "cancelled": cancelled,
                "turnover": _f(r.get("currentNetSale")),
                "tiers": tiers}

    def get_jackpot(self, product: str, draw_number: int) -> Optional[float]:
        """Riktig jackpot/rullpott från /jackpots-endpointen (fund-fältet på
        draws är opålitligt — t.ex. 6 Mkr-jackpot syns bara här). Matchar på
        productId eftersom productName byter skepnad (Europatipset = 'VM-tipset')."""
        data = self._get_or_none(f"/draw/{API_VER}/jackpots")
        if not data:
            return None
        pid = PRODUCTS.get(product, {}).get("pid")
        if pid is None:
            return None
        total = 0.0
        for j in data.get("jackpots") or []:
            if j.get("productId") == pid and j.get("drawNumber") == draw_number:
                for x in j.get("jackpots") or []:
                    total += _f(x.get("jackpotAmount")) or 0.0
        return total or None

    def latest_payouts(self, product: str = "stryktipset",
                       from_number: Optional[int] = None, back: int = 12) -> Optional[dict]:
        """Senaste avgjorda omgångens utdelning (scanna bakåt från from_number)."""
        start = from_number or self.current_draw_number(product) or PRODUCTS[product].get("seed")
        if not start:
            return None
        for n in range(start, max(1, start - back), -1):
            res = self.get_result(product, n)
            if res:
                return res
        return None

    def current_draw_number(self, product: str = "stryktipset",
                            start_hint: Optional[int] = None) -> Optional[int]:
        """Närmaste öppna omgång (lägsta öppna numret)."""
        opens = self.open_draws(product, start_hint)
        if opens:
            return min(d["draw_number"] for d in opens)
        alld = self.list_draws(product, start_hint)
        return max((d["draw_number"] for d in alld), default=None)

    def get_draw(self, draw_number: int, product: str = "stryktipset") -> Draw:
        slug = PRODUCTS[product]["slug"]
        data = self._get(f"/draw/{API_VER}/{slug}/draws/{draw_number}")
        raw = data["draws"][0] if "draws" in data else data.get("draw", data)
        return self._parse_draw(raw, product)

    def get_current_draw(self, product: str = "stryktipset",
                         start_hint: Optional[int] = None) -> Optional[Draw]:
        num = self.current_draw_number(product, start_hint)
        return self.get_draw(num, product) if num is not None else None

    # --- parsning ---
    @staticmethod
    def _parse_jackpot(raw: dict) -> Optional[float]:
        """Jackpot/rullpott ur 'fund' (form okänd — defensivt) eller extraInfo-texten."""
        f = raw.get("fund")
        if isinstance(f, (int, float)) and f > 0:
            return float(f)
        if isinstance(f, dict):
            for k in ("amount", "jackpot", "value", "fundSum", "extraMoney"):
                v = _f(f.get(k))
                if v:
                    return v
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(miljon|milj|mkr)", raw.get("extraInfo") or "", re.I)
        if m:
            return float(m.group(1).replace(",", ".")) * 1_000_000
        return None

    def _parse_draw(self, raw: dict, product: str) -> Draw:
        draw = Draw(
            product=product,
            draw_number=raw["drawNumber"],
            state=raw.get("drawState", ""),
            reg_close_time=raw.get("regCloseTime"),
            net_sale=_f(raw.get("currentNetSale")),
            row_price=_f(raw.get("rowPrice")) or 1.0,
            fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            jackpot=self._parse_jackpot(raw),
            extra_info=raw.get("extraInfo") or None,
        )
        for ev in raw.get("drawEvents", []):
            draw.matches.append(self._parse_match(ev))
        return draw

    def _parse_match(self, ev: dict) -> Match:
        match = ev.get("match", {})
        parts = {p.get("type"): p for p in match.get("participants", [])}
        home = parts.get("home", {}).get("name", "")
        away = parts.get("away", {}).get("name", "")
        home_iso = parts.get("home", {}).get("isoCode")
        away_iso = parts.get("away", {}).get("isoCode")

        odds = ev.get("odds") or {}
        start = ev.get("startOdds") or {}
        folk = ev.get("svenskaFolket") or {}

        key = {"1": "one", "X": "x", "2": "two"}
        outcomes: dict[str, Outcome] = {}
        for sign, k in key.items():
            ref_key = {"1": "refOne", "X": "refX", "2": "refTwo"}[sign]
            outcomes[sign] = Outcome(
                sign=sign,
                odds=_f(odds.get(k)),
                start_odds=_f(start.get(k)),
                streck=_i(folk.get(k)),
                streck_ref=_i(folk.get(ref_key)),
            )

        kambi = None
        for p in ev.get("providerIds", []) or []:
            if p.get("provider") == "Kambi":
                kambi = p.get("id")
                break

        league = match.get("league", {}).get("name", "")
        return Match(
            event_number=ev.get("eventNumber"),
            description=ev.get("eventDescription", f"{home} - {away}"),
            home=home,
            away=away,
            home_iso=home_iso,
            away_iso=away_iso,
            league=league,
            match_start=match.get("matchStart"),
            cancelled=ev.get("cancelled", False),
            kambi_id=kambi,
            outcomes=outcomes,
        )


def draw_to_dict(draw: Draw) -> dict:
    d = asdict(draw)
    return d
