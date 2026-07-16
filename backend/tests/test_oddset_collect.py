import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset
from app.storage import Storage


class _Pin:
    def close(self) -> None:
        pass


class CollectionPresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime.now(dt.timezone.utc)
        self.start = (self.now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.league = {"key": "test", "name": "Test", "pin_id": 1,
                       "kambi": "football/test", "altenar": None}
        self.store.oddset_upsert_match({
            "id": "m1", "league": "test", "home": "Home", "away": "Away",
            "start": self.start, "pinnacle_id": "p1", "kambi_id": "k1",
        })
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8},
            self.now.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _collect(self, pin_rows) -> dict:
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", pin_rows), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[]), \
                mock.patch.object(oddset, "BOOKS", []):
            return oddset.collect(self.store, leagues=[self.league], deep=False)

    def test_failed_source_does_not_suspend_last_confirmed_price(self) -> None:
        report = self._collect(mock.Mock(side_effect=RuntimeError("blocked")))

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertTrue(market["available"])
        self.assertTrue(any("blocked" in e for e in report["errors"]))
        health = next(r for r in self.store.oddset_source_health()
                      if r["source"] == "pinnacle")
        self.assertFalse(health["ok"])

    def test_successful_response_without_event_suspends_price(self) -> None:
        self._collect(mock.Mock(return_value=[]))

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertFalse(market["available"])

    def test_fast_poll_fetches_deep_markets_inside_three_hours(self) -> None:
        event = {"id": "k1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.2, "X": 3.4, "2": 3.3}}
        deep = {"ah": {"H": 1.9, "A": 1.95, "line": -0.25},
                "ou": {"O": 1.88, "U": 1.98, "line": 2.75}}
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[event]), \
                mock.patch.object(oddset.kambi, "event_markets", return_value=deep) as markets, \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(oddset.time, "sleep"):
            oddset.collect(self.store, leagues=[self.league], deep=False)

        markets.assert_called_once()
        latest = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]
        self.assertTrue(latest["ah"]["available"])
        self.assertTrue(latest["ou"]["available"])


if __name__ == "__main__":
    unittest.main()
