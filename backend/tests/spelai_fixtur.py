"""Gemensamma fixturer för test_spelai_*.py (ingen testfil i sig)."""
from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from app.spelai import schema, tillstand
from app.spelai.sandbox import AgentSvar
from app.storage import Storage
from app.svenskaspel import Draw, Match, Outcome

UTC = dt.timezone.utc
# facitsidan "driftsattes" här; alla fönster i testerna öppnar efter den
START = dt.datetime(2026, 10, 1, 6, 0, tzinfo=UTC)


def iso(t: dt.datetime) -> str:
    return tillstand.iso(t)


def ny_store(tmp: tempfile.TemporaryDirectory, *, med_tabeller: bool = True,
             start: dt.datetime = START) -> Storage:
    store = Storage(Path(tmp.name) / "spelai.db")
    if med_tabeller:
        schema.apply_schema(store.conn)
        tillstand.satt(store.conn, tillstand.FACIT_START_KEY, iso(start),
                       source="test", now=start)
    return store


def draw_fixture(close: dt.datetime, observed: dt.datetime, *,
                 product: str = "stryktipset", number: int = 5000,
                 n_events: int = 13) -> Draw:
    draw = Draw(product=product, draw_number=number, state="Open",
                reg_close_time=close.isoformat(), net_sale=2_500_000.0,
                row_price=1.0, fetched_at=observed.isoformat(), jackpot=0.0)
    for i in range(1, n_events + 1):
        odds = {"1": 1.6 + 0.15 * (i % 4), "X": 3.5 + 0.1 * (i % 3), "2": 4.2 + 0.2 * (i % 5)}
        streck = {"1": 50 + (i % 7), "X": 27 - (i % 5), "2": 23 - (i % 7) + (i % 5)}
        outcomes = {s: Outcome(sign=s, odds=odds[s], start_odds=odds[s],
                               streck=streck[s], streck_ref=streck[s])
                    for s in ("1", "X", "2")}
        draw.matches.append(Match(
            event_number=i, description=f"H{i} - B{i}", home=f"H{i}", away=f"B{i}",
            home_iso=None, away_iso=None, league="Test",
            match_start=close.isoformat(), cancelled=False, kambi_id=None,
            outcomes=outcomes))
    return draw


def lagg_till_omgang(store: Storage, product: str, number: int,
                     close: dt.datetime, state: str = "Open") -> None:
    store.conn.execute(
        "INSERT OR REPLACE INTO draws (product, draw_number, state, reg_close_time) "
        "VALUES (?,?,?,?)", (product, number, state, close.isoformat()))
    store.conn.commit()


def giltigt_svar(payload: dict, nivaer: list[int], timeout: float) -> AgentSvar:
    """Falsk agent: giltiga förslag för alla begärda nivåer."""
    n = payload["n_matches"]
    forslag = {}
    for level in nivaer:
        if level == 39366:
            forslag[str(level)] = {"format": "msystem",
                                   "tecken": ["1", "X", "2", "1X"] + ["1X2"] * (n - 4)}
        else:
            rows = []
            for k in range(min(level, 50)):
                digits = []
                value = k
                for _ in range(n):
                    digits.append("1X2"[value % 3])
                    value //= 3
                rows.append("".join(digits))
            forslag[str(level)] = {"format": "rows", "rows": rows,
                                   "motivering_kort": "test"}
    return AgentSvar("ok", data={"version": "falsk-v1", "forslag": forslag})


class Klocka:
    """Injicerad klocka som går framåt en sekund per avläsning."""

    def __init__(self, start: dt.datetime, steg_s: float = 1.0):
        self.t = start
        self.steg = dt.timedelta(seconds=steg_s)

    def __call__(self) -> dt.datetime:
        self.t += self.steg
        return self.t
