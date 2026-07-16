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


class OddsetValueIdentityTests(unittest.TestCase):
    def test_line_and_signal_version_are_independent_identities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                base = {
                    "match_id": "m1", "market": "ah", "sign": "H",
                    "league": "mls", "description": "A – B",
                    "match_start": "2026-07-17T10:00:00Z",
                    "at": "2026-07-16T10:00:00Z", "odds": 2.1,
                    "fair": 0.5, "edge": 0.05, "book": "svenskaspel",
                    "tier": "sharp", "git_hash": "abc",
                }
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v1"})
                store.oddset_log_flag({**base, "line": -0.75, "model_version": "s-v1"})
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v2"})
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v1",
                                       "edge": 0.08, "at": "2026-07-16T10:30:00Z"})

                rows = store.oddset_clv_rows()
                self.assertEqual(3, len(rows))
                v1 = next(r for r in rows if r["line"] == -0.5
                          and r["model_version"] == "s-v1")
                self.assertEqual(0.05, v1["first_edge"])
                self.assertEqual(0.08, v1["best_edge"])
            finally:
                store.close()


class OddsetAbsenceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_latest_capture_roundtrips_player_identity_and_position(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "15171583", "match_start": "2026-07-17T02:30:00Z",
            "confirmed": False, "payload_hash": "hash-1",
        }
        players = [{
            "side": "away", "player_id": 794516, "name": "Yohei Takaoka",
            "position": "G", "reason_code": 13, "reason": "avstängd",
            "description": "red_card_suspension",
            "expected_end": "2026-07-17T03:30:00+00:00",
            "apps": 13, "rating": 6.91,
        }]

        self.assertEqual(1, self.store.oddset_save_absence_capture(capture, players))
        latest = self.store.oddset_latest_absences(["m1"])["m1"]

        self.assertFalse(latest["confirmed"])
        self.assertEqual("15171583", latest["source_event_id"])
        self.assertEqual([], latest["home"])
        self.assertEqual(794516, latest["away"][0]["player_id"])
        self.assertEqual("G", latest["away"][0]["position"])
        self.assertEqual(13, latest["away"][0]["reason_code"])

    def test_empty_new_capture_replaces_current_list_but_preserves_history(self) -> None:
        base = {
            "match_id": "m1", "source_event_id": "1",
            "match_start": "2026-07-17T02:30:00Z", "confirmed": False,
        }
        self.store.oddset_save_absence_capture(
            {**base, "captured_at": "2026-07-16T10:00:00Z", "payload_hash": "h1"},
            [{"side": "home", "player_id": 7, "name": "A", "reason": "skada"}])
        self.store.oddset_save_absence_capture(
            {**base, "captured_at": "2026-07-16T12:00:00Z", "payload_hash": "h2"}, [])

        latest = self.store.oddset_latest_absences(["m1"])["m1"]
        history = self.store.oddset_absence_history("m1")

        self.assertEqual([], latest["home"])
        self.assertEqual([], latest["away"])
        self.assertEqual(2, len(history))
        self.assertEqual(1, history[0]["missing_count"])
        self.assertEqual(0, history[1]["missing_count"])

    def test_same_capture_is_idempotent(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "1", "match_start": None, "confirmed": False,
            "payload_hash": "h1",
        }
        players = [{"side": "home", "name": "No id", "reason": "skada"}]

        self.assertEqual(1, self.store.oddset_save_absence_capture(capture, players))
        self.assertEqual(0, self.store.oddset_save_absence_capture(capture, players))
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_player").fetchone()[0])

    def test_invalid_player_rolls_back_capture_atomically(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "1", "match_start": None, "confirmed": False,
            "payload_hash": "h1",
        }
        with self.assertRaises(ValueError):
            self.store.oddset_save_absence_capture(
                capture, [{"side": "unknown", "name": "A"}])

        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_capture").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
