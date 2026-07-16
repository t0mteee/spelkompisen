import tempfile
import unittest
from pathlib import Path

from app.storage import Storage


class BulkTransactionTests(unittest.TestCase):
    def test_bulk_rolls_back_all_writes_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with self.assertRaises(RuntimeError):
                    with store.bulk():
                        store.meta_set("first", "1")
                        store.meta_set("second", "2")
                        raise RuntimeError("abort")
                self.assertIsNone(store.meta_get("first"))
                self.assertIsNone(store.meta_get("second"))
            finally:
                store.close()


class OddsetPresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_unchanged_price_updates_confirmation_without_movement_row(self) -> None:
        odds = {"1": 2.1, "X": 3.4, "2": 3.2}
        self.assertEqual(3, self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:00:00Z"))
        self.assertEqual(0, self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:30:00Z"))

        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE match_id='m1'").fetchone()[0]
        self.assertEqual(3, count)
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertTrue(market["available"])
        self.assertEqual("2026-07-16T10:30:00Z", market["last_seen_at"])
        self.assertEqual("2026-07-16T10:00:00Z", market["fetched_at"])

    def test_missing_selection_suspends_market_and_reappearance_restores_it(self) -> None:
        odds = {"1": 2.1, "X": 3.4, "2": 3.2}
        self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:00:00Z")
        self.store.oddset_save_odds(
            "m1", "svenskaspel", {**odds, "X": None}, "2026-07-16T10:10:00Z")
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertFalse(market["available"])
        self.assertFalse(market["selections"]["X"]["available"])

        self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:20:00Z")
        restored = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertTrue(restored["available"])
        self.assertEqual("2026-07-16T10:20:00Z", restored["last_seen_at"])

    def test_available_derived_market_replaces_suspended_direct_market(self) -> None:
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.6},
            "2026-07-16T10:00:00Z")
        self.store.oddset_mark_market_unavailable("m1", "pinnacle", "1x2")
        self.store.oddset_save_odds(
            "m1", "derived", {"1": 2.1, "X": 3.4, "2": 3.4},
            "2026-07-16T10:10:00Z")

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertTrue(market["available"])
        self.assertTrue(market["derived"])
        self.assertEqual(2.1, market["1"])

    def test_source_health_roundtrips_error_state(self) -> None:
        self.store.oddset_record_source_health(
            "pinnacle", "mls", "markets", "2026-07-16T10:00:00Z",
            False, 0, "blocked")
        health = self.store.oddset_source_health()
        self.assertEqual(1, len(health))
        self.assertFalse(health[0]["ok"])
        self.assertEqual("blocked", health[0]["error"])


if __name__ == "__main__":
    unittest.main()
