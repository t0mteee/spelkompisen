import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import oddset_value
from app.storage import Storage


def _market(values: dict, seen: dt.datetime, available: bool = True) -> dict:
    return {**values, "available": available,
            "last_seen_at": seen.strftime("%Y-%m-%dT%H:%M:%SZ")}


class PriceFreshnessTests(unittest.TestCase):
    def test_stale_book_price_is_excluded_from_value(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1", "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"1x2": _market(
                    {"1": 2.0, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
                "svenskaspel": {"1x2": _market(
                    {"1": 2.3, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=60))},
            },
        }

        oddset_value.attach_value([match])
        self.assertFalse(match["odds"]["svenskaspel"]["1x2"]["fresh"])
        self.assertEqual({}, match["value"])

    def test_recent_confirmation_allows_value(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1", "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"1x2": _market(
                    {"1": 2.0, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
                "svenskaspel": {"1x2": _market(
                    {"1": 2.3, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
            },
        }

        oddset_value.attach_value([match])
        self.assertTrue(match["odds"]["svenskaspel"]["1x2"]["fresh"])
        self.assertIn("1", match["value"]["1x2"])


class ClosingFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _flag(self, start: dt.datetime) -> None:
        self.store.oddset_log_flag({
            "match_id": "m1", "market": "1x2", "sign": "1",
            "league": "mls", "description": "A – B",
            "match_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at": (start - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": 2.2, "fair": 0.5, "edge": 0.1,
            "book": "svenskaspel", "model_version": "s-test", "git_hash": "abc",
        })

    def test_old_unconfirmed_sharp_price_is_not_used_as_closing(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        old = (start - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, old)
        self._flag(start)

        self.assertEqual(1, oddset_value.resolve_closings(self.store))
        row = self.store.oddset_clv_rows()[0]
        self.assertIn("äldre än", row["closing_note"])
        self.assertIsNone(row["closing_fair"])

    def test_unchanged_price_confirmed_near_start_is_valid_closing(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        old = (start - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (start - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        odds = {"1": 2.0, "X": 3.5, "2": 3.8}
        self.store.oddset_save_odds("m1", "pinnacle", odds, old)
        self.store.oddset_save_odds("m1", "pinnacle", odds, recent)
        self._flag(start)

        self.assertEqual(1, oddset_value.resolve_closings(self.store))
        row = self.store.oddset_clv_rows()[0]
        self.assertIsNone(row["closing_note"])
        self.assertIsNotNone(row["closing_fair"])


if __name__ == "__main__":
    unittest.main()
