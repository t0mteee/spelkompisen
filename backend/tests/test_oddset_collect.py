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


class ResearchLeagueIsolationTests(unittest.TestCase):
    def test_fast_research_poll_uses_known_moneyline_single_endpoint(self) -> None:
        class Pin:
            def _get(self, path):
                self.path = path
                return [{
                    "matchupId": 7, "period": 0, "type": "moneyline",
                    "prices": [
                        {"designation": "home", "price": -110},
                        {"designation": "draw", "price": 250},
                        {"designation": "away", "price": 300},
                    ],
                }]

        pin = Pin()
        rows = oddset.pinnacle_known_moneylines(pin, 1980, [{
            "id": "pin:7", "pinnacle_id": "7", "home": "Home",
            "away": "Away", "start": "2026-08-21T19:00:00Z",
        }])

        self.assertEqual("/leagues/1980/markets/straight", pin.path)
        self.assertEqual(1, len(rows))
        self.assertAlmostEqual(1.91, rows[0]["odds"]["1"])
        self.assertAlmostEqual(3.5, rows[0]["odds"]["X"])
        self.assertAlmostEqual(4.0, rows[0]["odds"]["2"])

    def test_research_leagues_are_hidden_from_regular_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            start = (now + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                store.oddset_upsert_match({
                    "id": "public", "league": "allsvenskan", "home": "A",
                    "away": "B", "start": start,
                })
                store.oddset_upsert_match({
                    "id": "research", "league": "premier_league", "home": "C",
                    "away": "D", "start": start,
                })

                regular = oddset.matches_payload(store, light=True)
                internal = oddset.matches_payload(
                    store, light=True, include_research=True)
            finally:
                store.close()

        self.assertEqual(["public"], [row["id"] for row in regular["matches"]])
        self.assertNotIn("premier_league", {
            row["key"] for row in regular["leagues"]})
        self.assertEqual({"public", "research"}, {
            row["id"] for row in internal["matches"]})

    def test_research_leagues_skip_deep_markets_and_sidebooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            start = (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            league = next(row for row in oddset.LEAGUES
                          if row["key"] == "premier_league")
            event = {"id": "k-eu", "home": "Home", "away": "Away",
                     "start": start, "odds": {"1": 2.0, "X": 3.5, "2": 4.0}}
            try:
                with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                        mock.patch.object(oddset, "pinnacle_league_index",
                                          return_value=[]), \
                        mock.patch.object(oddset.kambi, "league_events",
                                          return_value=[event]), \
                        mock.patch.object(oddset.kambi, "event_markets") as deep:
                    oddset.collect(store, leagues=[league], deep=False)
            finally:
                store.close()

        deep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
