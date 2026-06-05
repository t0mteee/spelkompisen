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
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx

BASE = "https://api.spela.svenskaspel.se"
# Produkt-id 1 = Stryktipset. (2 = Europatipset, 16 = Topptipset — samma format.)
PRODUCTS = {
    "stryktipset": ("stryktipset", 1),
    "europatipset": ("europatipset", 2),
    "topptipset": ("topptipset", 16),
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
    fetched_at: str
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

    def list_draws(self, product: str = "stryktipset") -> list[dict]:
        slug, pid = PRODUCTS[product]
        data = self._get(f"/draw/{pid}/{slug}/draws")
        return data.get("draws", [])

    def current_draw_number(self, product: str = "stryktipset") -> Optional[int]:
        """Lägsta öppna omgångsnumret (närmast i tid)."""
        draws = self.list_draws(product)
        open_draws = [d for d in draws if d.get("drawState") == "Open"]
        pool = open_draws or draws
        if not pool:
            return None
        return min(d["drawNumber"] for d in pool)

    def get_draw(self, draw_number: int, product: str = "stryktipset") -> Draw:
        slug, pid = PRODUCTS[product]
        data = self._get(f"/draw/{pid}/{slug}/draws/{draw_number}")
        raw = data["draws"][0] if "draws" in data else data.get("draw", data)
        return self._parse_draw(raw, product)

    def get_current_draw(self, product: str = "stryktipset") -> Optional[Draw]:
        num = self.current_draw_number(product)
        return self.get_draw(num, product) if num is not None else None

    # --- parsning ---
    def _parse_draw(self, raw: dict, product: str) -> Draw:
        draw = Draw(
            product=product,
            draw_number=raw["drawNumber"],
            state=raw.get("drawState", ""),
            reg_close_time=raw.get("regCloseTime"),
            net_sale=_f(raw.get("currentNetSale")),
            fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
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
