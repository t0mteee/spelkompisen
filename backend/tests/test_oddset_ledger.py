import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import oddset_ledger
from app.storage import Storage


UTC = dt.timezone.utc


def _market(values, line=None, fresh=True):
    return {**values, "line": line, "available": fresh, "fresh": fresh,
            "last_seen_at": "2026-07-16T10:00:00Z"}


class PredictionCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime(2026, 7, 16, 10, tzinfo=UTC)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _match(self) -> dict:
        return {
            "id": "m1", "league": "allsvenskan", "home": "A", "away": "B",
            "start": "2026-07-16T12:00:00Z",
            "odds": {
                "pinnacle": {"1x2": _market({"1": 2.0, "X": 3.5, "2": 4.0})},
                "svenskaspel": {"1x2": _market({"1": 2.1, "X": 3.4, "2": 3.8})},
            },
            "model": {"p": {"1": 0.52, "X": 0.27, "2": 0.21},
                      "anchored": False},
        }

    def test_horizon_is_current_bucket_and_capture_is_idempotent(self) -> None:
        versions = {
            "sharp": {"signal_version": "s-ledger", "base_version": "s-base"},
            "model": {"signal_version": "m-ledger", "base_version": "m-base"},
        }
        with patch.object(oddset_ledger, "prediction_versions", return_value=versions):
            first = oddset_ledger.capture_predictions(
                self.store, [self._match()], now=self.now)
            second = oddset_ledger.capture_predictions(
                self.store, [self._match()], now=self.now + dt.timedelta(minutes=2))

        self.assertEqual({"captures": 2, "rows": 6, "empty": 0}, first)
        self.assertEqual({"captures": 0, "rows": 0, "empty": 0}, second)
        captures = self.store.oddset_prediction_captures()
        self.assertEqual({"h3"}, {row["horizon"] for row in captures})
        rows = self.store.oddset_prediction_rows()
        self.assertTrue(any(not row["is_flag"] for row in rows))  # control group
        self.assertEqual({"sharp", "model"}, {row["tier"] for row in rows})
        self.assertTrue(all(row["delay_minutes"] == 60 for row in rows))

    def test_empty_capture_is_not_backfilled_late(self) -> None:
        match = {**self._match(), "odds": {}}
        versions = {
            "sharp": {"signal_version": "s-ledger", "base_version": "s-base"},
            "model": {"signal_version": "m-ledger", "base_version": "m-base"},
        }
        with patch.object(oddset_ledger, "prediction_versions", return_value=versions):
            first = oddset_ledger.capture_predictions(
                self.store, [match], tiers=("sharp",), now=self.now)
            late = oddset_ledger.capture_predictions(
                self.store, [self._match()], tiers=("sharp",),
                now=self.now + dt.timedelta(minutes=5))

        self.assertEqual({"captures": 1, "rows": 0, "empty": 1}, first)
        self.assertEqual({"captures": 0, "rows": 0, "empty": 0}, late)
        self.assertEqual(0, len(self.store.oddset_prediction_rows()))

    def test_version_change_gets_independent_capture(self) -> None:
        match = self._match()
        v1 = {"sharp": {"signal_version": "s-v1", "base_version": "s-base"},
              "model": {"signal_version": "m-v1", "base_version": "m-base"}}
        v2 = {"sharp": {"signal_version": "s-v2", "base_version": "s-base2"},
              "model": {"signal_version": "m-v2", "base_version": "m-base2"}}
        with patch.object(oddset_ledger, "prediction_versions", return_value=v1):
            oddset_ledger.capture_predictions(
                self.store, [match], tiers=("sharp",), now=self.now)
        with patch.object(oddset_ledger, "prediction_versions", return_value=v2):
            oddset_ledger.capture_predictions(
                self.store, [match], tiers=("sharp",), now=self.now)
        self.assertEqual(6, len(self.store.oddset_prediction_rows()))

    def test_horizon_boundaries_never_backfill(self) -> None:
        start = "2026-07-17T10:00:00Z"
        self.assertEqual(("h24", 1440), oddset_ledger.horizon_at(start, self.now))
        self.assertEqual(("h3", 180), oddset_ledger.horizon_at(
            start, dt.datetime(2026, 7, 17, 8, tzinfo=UTC)))
        self.assertEqual(("m20", 20), oddset_ledger.horizon_at(
            start, dt.datetime(2026, 7, 17, 9, 50, tzinfo=UTC)))
        self.assertIsNone(oddset_ledger.horizon_at(
            start, dt.datetime(2026, 7, 16, 9, 59, tzinfo=UTC)))


class PredictionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _resolved_flag(self, match_id: str, horizon: str,
                       captured: dt.datetime, start: dt.datetime,
                       *, market: str = "1x2", version: str = "s-test",
                       closing_fair: float = 0.55) -> None:
        capture = {
            "match_id": match_id, "horizon": horizon, "tier": "sharp",
            "signal_version": version, "base_version": "s-base",
            "league": "allsvenskan", "description": f"{match_id} A – B",
            "match_start": oddset_ledger._iso(start),
            "target_at": oddset_ledger._iso(captured),
            "captured_at": oddset_ledger._iso(captured),
            "offset_minutes": 180.0, "delay_minutes": 0.0, "git_hash": "abc",
        }
        prediction = {
            "market": market, "sign": "1" if market == "1x2" else "O",
            "line": None if market == "1x2" else 2.5,
            "line_key": (Storage.ODDSET_NO_LINE_KEY if market == "1x2" else 2500),
            "fair_prob": 0.55,
            "fair_source": "pinnacle", "fair_available": True,
            "fair_fresh": True, "model_anchored": None,
            "book": "svenskaspel", "book_odds": 2.0,
            "book_available": True, "book_fresh": True,
            "edge": 0.10, "eligible": True, "is_flag": True,
        }
        self.store.oddset_capture_predictions(capture, [prediction])
        row = next(row for row in self.store.oddset_prediction_rows()
                   if row["match_id"] == match_id and row["horizon"] == horizon
                   and row["signal_version"] == version)
        self.store.oddset_set_prediction_closing(row, closing_fair, 1.8, None)

    def test_primary_group_requires_out_of_time_confirmation(self) -> None:
        base = dt.datetime(2026, 5, 1, 12, tzinfo=UTC)
        horizons = ("h24", "h3", "m20")
        for i in range(50):
            match_no = i % 30
            start = base + dt.timedelta(days=match_no)
            self._resolved_flag(
                f"pre-{match_no}", horizons[i // 30], start - dt.timedelta(hours=3), start)

        candidate_now = dt.datetime(2026, 6, 15, 12, tzinfo=UTC)
        report = oddset_ledger.prediction_report(
            self.store, update_states=True, now=candidate_now)
        group = report["groups"][0]
        self.assertEqual("candidate", group["status"])
        self.assertEqual(50, group["n_resolved"])
        self.assertEqual(30, group["n_matches"])
        self.assertGreaterEqual(group["span_days"], 28)
        self.assertEqual(0, group["post_candidate_matches"])

        for i in range(15):
            captured = candidate_now + dt.timedelta(days=i + 1)
            self._resolved_flag(
                f"post-{i}", "h3", captured,
                captured + dt.timedelta(hours=3))
        green = oddset_ledger.prediction_report(
            self.store, update_states=True,
            now=candidate_now + dt.timedelta(days=20))["groups"][0]
        self.assertEqual("green", green["status"])
        self.assertEqual(15, green["post_candidate_matches"])
        self.assertGreater(green["post_candidate_ci"][0], 0)

    def test_bh_fdr_applies_only_to_exploratory_groups(self) -> None:
        groups = [
            {"key": ("model", "a", "1x2", "v"), "primary": False,
             "testable": True, "p_value": 0.01},
            {"key": ("model", "b", "ah", "v"), "primary": False,
             "testable": True, "p_value": 0.04},
            {"key": ("model", "c", "ou", "v"), "primary": False,
             "testable": True, "p_value": 0.20},
            {"key": ("sharp", "a", "1x2", "v"), "primary": True,
             "testable": True, "p_value": 0.001},
        ]
        passed = oddset_ledger._bh_pass(groups)
        self.assertEqual({groups[0]["key"], groups[1]["key"]}, passed)

    def test_friendlies_are_not_a_preregistered_primary_league(self) -> None:
        self.assertNotIn("friendlies", oddset_ledger.PRIMARY_LEAGUES)

    def test_report_never_aggregates_signal_versions(self) -> None:
        start = dt.datetime(2026, 7, 20, 12, tzinfo=UTC)
        captured = start - dt.timedelta(hours=3)
        self._resolved_flag("v1-match", "h3", captured, start, version="s-v1")
        self._resolved_flag("v2-match", "h3", captured, start, version="s-v2")

        groups = oddset_ledger.prediction_report(self.store)["groups"]

        self.assertEqual({"s-v1", "s-v2"}, {group["version"] for group in groups})
        self.assertTrue(all(group["n_resolved"] == 1 for group in groups))

    def test_candidate_state_is_per_market_group_not_whole_tier(self) -> None:
        base = dt.datetime(2026, 5, 1, 12, tzinfo=UTC)
        for i in range(50):
            start = base + dt.timedelta(days=i % 30)
            captured = start - dt.timedelta(hours=3)
            horizon = "h3" if i < 30 else "h24"
            self._resolved_flag(f"good-{i % 30}", horizon, captured, start)
            self._resolved_flag(
                f"bad-{i % 30}", horizon, captured, start,
                market="ou", closing_fair=0.40,
            )

        groups = oddset_ledger.prediction_report(
            self.store, update_states=True,
            now=dt.datetime(2026, 6, 15, 12, tzinfo=UTC))["groups"]
        status = {group["market"]: group["status"] for group in groups}

        self.assertEqual("candidate", status["1x2"])
        self.assertEqual("amber", status["ou"])


class ClusterBootstrapTests(unittest.TestCase):
    def test_correlated_flags_in_one_match_do_not_create_false_certainty(self) -> None:
        rows = [
            {"match_id": "positive", "close_ev_w": 0.20}
            for _ in range(100)
        ] + [
            {"match_id": "negative-1", "close_ev_w": -0.20},
            {"match_id": "negative-2", "close_ev_w": -0.20},
        ]

        ci, _ = oddset_ledger._bootstrap(rows, ("cluster-test",), iters=1000)

        self.assertIsNotNone(ci)
        self.assertLess(ci[0], 0)


if __name__ == "__main__":
    unittest.main()
