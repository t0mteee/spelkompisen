"""Kupongdetaljen markerar ett sharppris som var inaktuellt vid frysningen.

`system_detail` visar "Sharpodds vid frysning" ur förändringsserien
`sharp_snapshots` och kunde inte se att länken var tappad eller priset för
gammalt. Regeln är tillägget 2026-09-24 i
docs/ph3-sannolikhetsbas-v1-2026-09-02.md med pool-sharp-freshness-v1:s
konstanter; före driftsättningen användes priset ändå, efter den inte.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pool_sharp_freshness as freshness, pool_system_ledger
from app.storage import Storage

PRODUCT = "stryktipset"
BEFORE_RULE = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
AFTER_RULE = dt.datetime(2026, 9, 24, 16, 0, tzinfo=dt.timezone.utc)


def _iso(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class Fixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.store = Storage(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def capture(self, draw, event, fetched_at, status, source="sharp", complete=None):
        if complete is None:
            complete = status in ("matched", "derived") if source == "sharp" else True
        self.store.conn.execute(
            "INSERT INTO pool_market_capture (product, draw_number, source, "
            "event_number, fetched_at, status, odds_complete, streck_complete) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (PRODUCT, draw, source, event, fetched_at, status, int(complete)))
        self.store.conn.commit()

    def price(self, draw, event, fetched_at, odds=(2.0, 3.4, 3.8)):
        self.store.save_sharp(PRODUCT, draw, [{
            "event_number": event, "bookmaker": "pinnacle",
            "odds": dict(zip(("1", "X", "2"), odds)), "total": None,
            "confidence": 1.0, "matched": f"H{event} - B{event}",
            "fetched_at": fetched_at}])
        self.store.save_sharp_snapshot(
            PRODUCT, draw, {event: {"odds": dict(zip(("1", "X", "2"), odds))}},
            fetched_at)


class StaleAtFreezeTests(Fixture, unittest.TestCase):
    """Kupongdetaljen: inaktuellt Pinnacle-underlag vid frysningen."""

    def ledger(self, draw, frozen):
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used) VALUES (?,?,'h3',?,?,1,1,'test',256,"
            "'medel',0.5,1.0,1,1.0,'1,2,3,4,5,6','1,1,1,1,1,1','h',6,1000,"
            "'live',0)", (PRODUCT, draw, pool_system_ledger.CHAMPION_KEY,
                          _iso(frozen)))
        self.store.conn.commit()

    def fixture(self, draw, frozen):
        ago = lambda minutes: _iso(frozen - dt.timedelta(minutes=minutes))  # noqa: E731
        self.ledger(draw, frozen)
        for event in (1, 2, 3, 5, 6):   # förändringsserien först, captures sedan
            self.price(draw, event, ago(120))
        self.capture(draw, 1, ago(10), "matched")                 # färskt
        self.capture(draw, 2, ago(40), "matched")                 # tappad före frysningen
        self.capture(draw, 2, ago(13), "ambiguous")
        self.capture(draw, 3, ago(120), "matched")                # för gammal
        self.capture(draw, 4, ago(30), "not_listed")              # aldrig länkad
        self.capture(draw, 5, ago(40), "matched")                 # tappad EFTER frysningen
        self.capture(draw, 5, _iso(frozen + dt.timedelta(minutes=5)), "not_listed")
        # +02:00 som sträng "senare" än frysningen men som tid 5 min före.
        self.capture(draw, 6, ago(120), "matched")
        local = (frozen - dt.timedelta(minutes=5)).astimezone(
            dt.timezone(dt.timedelta(hours=2))).isoformat()
        self.capture(draw, 6, local, "matched")

    def detail(self, draw):
        detail = pool_system_ledger.system_detail(
            self.store, PRODUCT, draw, "h3", pool_system_ledger.CHAMPION_KEY)
        return {e["event_number"]: e for e in detail["events"]}

    def test_regeln_per_match_efter_farskhetsregeln_anvandes_inte(self):
        self.fixture(7, AFTER_RULE)
        events = self.detail(7)
        ago = lambda minutes: _iso(AFTER_RULE - dt.timedelta(minutes=minutes))  # noqa: E731
        self.assertIsNone(events[1]["sharp_stale_at_freeze"])
        self.assertEqual({"reason": "ambiguous", "label": "tvetydig",
                          "last_seen": ago(40), "used": False},
                         events[2]["sharp_stale_at_freeze"])
        self.assertEqual({"reason": "too_old", "label": "för gammal",
                          "last_seen": ago(120), "used": False},
                         events[3]["sharp_stale_at_freeze"])
        self.assertIsNone(events[4]["sharp_stale_at_freeze"], "aldrig länkad räknas inte")
        self.assertIsNone(events[5]["sharp_stale_at_freeze"], "captures efter frysningen räknas inte")
        self.assertIsNone(events[6]["sharp_stale_at_freeze"], "tider jämförs som tider")
        # Priset visas fortfarande (grått i UI:t), bara markerat.
        self.assertEqual(2.0, events[2]["sharp_odds_at_freeze"]["1"])

    def test_fore_farskhetsregeln_anvandes_priset_anda(self):
        self.fixture(8, BEFORE_RULE)
        events = self.detail(8)
        self.assertTrue(events[2]["sharp_stale_at_freeze"]["used"])
        self.assertTrue(events[3]["sharp_stale_at_freeze"]["used"])
        self.assertEqual(
            dt.datetime(2026, 9, 24, 14, 11, 9, tzinfo=dt.timezone.utc),
            freshness._parse(freshness.IN_EFFECT_FROM))

    def test_gransen_ar_driftsattningen(self):
        just_before = freshness._parse(freshness.IN_EFFECT_FROM) - dt.timedelta(seconds=1)
        self.ledger(9, just_before)
        self.capture(9, 1, _iso(just_before - dt.timedelta(minutes=100)), "matched")
        stale = pool_system_ledger._sharp_stale_at_freeze(
            self.store, PRODUCT, 9, _iso(just_before))
        self.assertTrue(stale[1]["used"])
        stale = pool_system_ledger._sharp_stale_at_freeze(
            self.store, PRODUCT, 9, freshness.IN_EFFECT_FROM)
        self.assertFalse(stale[1]["used"])


if __name__ == "__main__":
    unittest.main()
