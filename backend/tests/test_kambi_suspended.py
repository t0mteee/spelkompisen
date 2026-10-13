"""Kambis suspended-status för 1X2 före match och Pinnacles Age per prisrad.

Beslut granskaren-2026-10-11-kambi-suspended (Saman, val 0): `league_events`
läste varken erbjudandets `suspended` eller utfallens status, så ett avstängt
Svenska Spel-pris sparades som bekräftat. Pinnacles fetched_at var bakåtdaterad
med Age utan att Age sparades.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import kambi, oddset
from app.storage import Storage


def _offer(*, suspended=False, statuses=("OPEN", "OPEN", "OPEN"), label="Fulltid"):
    types = ("OT_ONE", "OT_CROSS", "OT_TWO")
    return {"criterion": {"label": label}, "suspended": suspended,
            "outcomes": [{"type": t, "odds": o, "status": st}
                         for t, o, st in zip(types, (2100, 3400, 3500), statuses)]}


def _list_view(*offers):
    return {"events": [{"event": {"id": 7, "homeName": "AIK", "awayName": "Hammarby",
                                  "start": "2026-10-20T17:00:00Z"},
                        "betOffers": list(offers)}]}


class LeagueEventsTests(unittest.TestCase):
    def events(self, payload):
        response = mock.MagicMock(headers={}, json=mock.Mock(return_value=payload))
        with mock.patch.object(kambi.httpx, "get", return_value=response):
            return kambi.league_events("football/sweden/allsvenskan", strict=True)

    def test_oppet_pris_ar_inte_suspenderat(self):
        row = self.events(_list_view(_offer()))[0]
        self.assertFalse(row["suspended"])
        self.assertEqual({"1": 2.1, "X": 3.4, "2": 3.5}, row["odds"])

    def test_suspenderat_erbjudande_eller_stangt_utfall(self):
        for offer in (_offer(suspended=True), _offer(statuses=("OPEN", "SUSPENDED", "OPEN")),
                      _offer(statuses=("CLOSED", "OPEN", "OPEN"))):
            row = self.events(_list_view(offer))[0]
            self.assertTrue(row["suspended"], offer)
            self.assertEqual(2.1, row["odds"]["1"])          # diagnostik, oförändrat

    def test_utfall_utan_status_och_andra_marknader_rors_inte(self):
        row = self.events(_list_view(_offer(statuses=(None, None, None)),
                                     _offer(suspended=True, label="Halvtid")))[0]
        self.assertFalse(row["suspended"])


class _Pin:
    def __init__(self, age_s: int = 0) -> None:
        self.last_age_s = age_s

    def reset_cache_age(self) -> None:
        pass

    def close(self) -> None:
        pass


class CollectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime.now(dt.timezone.utc)
        self.start = (self.now + dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.league = {"key": "test", "name": "Test", "pin_id": 1,
                       "kambi": "football/test", "altenar": None}
        self.store.oddset_upsert_match({
            "id": "m1", "league": "test", "home": "AIK", "away": "Hammarby",
            "start": self.start, "pinnacle_id": "p1", "kambi_id": "k1"})

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def collect(self, kambi_rows, pin_rows=(), age_s=0):
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin(age_s)), \
                mock.patch.object(oddset, "pinnacle_league_index",
                                  mock.Mock(return_value=list(pin_rows))), \
                mock.patch.object(oddset.kambi, "league_events", return_value=kambi_rows), \
                mock.patch.object(oddset.kambi, "event_markets", return_value={}), \
                mock.patch.object(oddset, "BOOKS", []):
            return oddset.collect(self.store, leagues=[self.league], deep=False)

    def kambi_row(self, suspended):
        return {"id": "k1", "home": "AIK", "away": "Hammarby", "start": self.start,
                "odds": {"1": 2.1, "X": 3.4, "2": 3.5}, "suspended": suspended}

    def test_suspenderat_pris_sparas_inte_som_bekraftat(self):
        self.collect([self.kambi_row(False)])
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertTrue(market["available"])
        report = self.collect([self.kambi_row(True)])
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertFalse(market["available"])
        self.assertEqual(1, report["kambi_suspended"])
        # Öppnar det igen blir samma pris spelbart på nytt.
        self.collect([self.kambi_row(False)])
        self.assertTrue(self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]["available"])

    def test_suspenderat_utan_tidigare_pris_skriver_inget(self):
        self.collect([self.kambi_row(True)])
        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE source='svenskaspel'").fetchone()[0])

    def test_pinnacles_age_sparas_per_ny_rad(self):
        pin = {"id": "p1", "home": "AIK", "away": "Hammarby", "start": self.start,
               "status": "open", "odds_source": "pinnacle", "ah": None,
               "ou": {"O": 1.9, "U": 1.95, "line": 2.5}, "cor": None, "alt": {},
               "odds": {"1": 2.0, "X": 3.5, "2": 3.8}}
        self.collect([], [pin], age_s=420)
        ages = {(r[0], r[1]) for r in self.store.conn.execute(
            "SELECT market, cache_age_s FROM oddset_odds WHERE source='pinnacle'")}
        self.assertEqual({("1x2", 420), ("ou", 420)}, ages)
        # Andra källor och äldre rader bär NULL: inte mätt.
        self.store.oddset_save_odds("m1", "svenskaspel", {"1": 2.1, "X": 3.4, "2": 3.5},
                                    self.now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertEqual({None}, {r[0] for r in self.store.conn.execute(
            "SELECT cache_age_s FROM oddset_odds WHERE source='svenskaspel'")})


if __name__ == "__main__":
    unittest.main()
