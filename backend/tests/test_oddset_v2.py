import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import oddset_v2
from app.storage import Storage


UTC = dt.timezone.utc


class V2DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.match = {
            "id": "m1", "league": "allsvenskan", "home": "A", "away": "B",
            "start": "2026-07-20T12:00:00Z", "pinnacle_id": "101",
        }
        self.store.oddset_upsert_match(self.match)
        base = dt.date(2026, 5, 1)
        for index in range(45):
            day = (base + dt.timedelta(days=index)).isoformat()
            self.store.oddset_save_result({
                "league": "allsvenskan", "date": day,
                "home": "a", "away": "b", "hg": index % 3,
                "ag": (index + 1) % 3, "xg_h": 1.1 + (index % 4) / 10,
                "xg_a": 0.9 + (index % 3) / 10, "source": "fd",
            })
        self.store.oddset_save_elo_history([
            {"club_key": "a", "club_raw": "A", "country": "SWE", "level": 1,
             "elo": 1510, "valid_from": "2026-07-01", "valid_to": "2026-07-31"},
            {"club_key": "b", "club_raw": "B", "country": "SWE", "level": 1,
             "elo": 1480, "valid_from": "2026-07-01", "valid_to": "2026-07-31"},
        ], "2026-07-16T10:00:00Z")
        self.capture_base = {
            "match_id": "m1", "horizon": "h24", "league": "allsvenskan",
            "description": "A – B", "match_start": self.match["start"],
            "target_at": "2026-07-19T12:00:00Z",
            "captured_at": "2026-07-19T12:00:00Z",
            "offset_minutes": 1440.0, "delay_minutes": 0.0,
            "base_version": "base", "git_hash": "abc",
        }

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    @staticmethod
    def _rows(probabilities: dict, tier: str) -> list[dict]:
        return [{
            "market": "1x2", "sign": sign, "line": None,
            "line_key": Storage.ODDSET_NO_LINE_KEY, "fair_prob": probability,
            "fair_source": "pinnacle" if tier == "sharp" else "model",
            "fair_available": True, "fair_fresh": True,
            "model_anchored": None if tier == "sharp" else 0,
            "book": None, "book_odds": None, "book_available": False,
            "book_fresh": False, "edge": None, "eligible": True, "is_flag": False,
        } for sign, probability in probabilities.items()]

    def _save_capture(self, tier: str, version: str, probabilities: dict) -> dict:
        capture = {**self.capture_base, "tier": tier, "signal_version": version}
        self.store.oddset_capture_predictions(
            capture, self._rows(probabilities, tier))
        return capture

    def test_feature_capture_excludes_same_day_and_freezes_sources(self) -> None:
        # Ett färdigt resultat på capture-dagen kan inte tidsordnas säkert när
        # resultattabellen bara har datum och ska därför inte ingå.
        self.store.oddset_save_result({
            "league": "allsvenskan", "date": "2026-07-19",
            "home": "a", "away": "b", "hg": 9, "ag": 0,
            "xg_h": 8.0, "xg_a": 0.1, "source": "fd",
        })
        capture = self._save_capture(
            "model", "m-v1", {"1": 0.50, "X": 0.30, "2": 0.20})

        inserted = oddset_v2.FeatureBuilder(self.store).capture(
            self.match, capture, "live")
        frozen = self.store.oddset_v2_features()[0]
        payload = __import__("json").loads(frozen["payload_json"])

        self.assertTrue(inserted)
        self.assertEqual("2026-06-14", payload["source"]["input_max_date"])
        self.assertEqual(45, payload["source"]["input_rows"])
        self.assertLess(payload["source"]["input_max_date"],
                        payload["source"]["cutoff_day"])
        self.assertIsNotNone(payload["features"]["attack_log_ratio"])
        self.assertEqual(30, payload["features"]["elo_diff"])
        self.assertTrue(payload["identity"]["all_fit_links_verified"])

    def test_verified_alias_chain_beats_fuzzy_provider_guess(self) -> None:
        link = oddset_v2._link(
            "IFK Göteborg", ("goeteborg",),
            {"ifk goteborg": "goteborg", "goteborg": "goeteborg"})

        self.assertEqual("goeteborg", link["key"])
        self.assertEqual("alias", link["method"])
        self.assertTrue(link["verified"])

    def test_identity_model_is_exact_and_outcome_is_label_only(self) -> None:
        sharp = self._save_capture(
            "sharp", "s-v1", {"1": 0.50, "X": 0.30, "2": 0.20})
        model = self._save_capture(
            "model", "m-v1", {"1": 0.48, "X": 0.31, "2": 0.21})
        self.assertEqual(sharp["captured_at"], model["captured_at"])
        oddset_v2.FeatureBuilder(self.store).capture(self.match, model, "live")
        self.store.oddset_save_result({
            "league": "allsvenskan", "date": "2026-07-20",
            "home": "a", "away": "b", "hg": 2, "ag": 1, "source": "fd",
        })

        dataset = oddset_v2.build_dataset(self.store)
        row = dataset["rows"][0]
        report = oddset_v2.audit(
            self.store, now=dt.datetime(2026, 7, 21, tzinfo=UTC))

        self.assertEqual("1", row["outcome"])
        self.assertLess(row["identity_max_abs"], 1e-10)
        self.assertAlmostEqual(0.0, sum(row["model_market_log_residual"].values()))
        self.assertTrue(row["promotion_ready"])
        self.assertTrue(row["evaluation_ready"])
        self.assertEqual([], report["checks"]["post_kickoff_or_feature_leak_rows"])
        self.assertLess(report["checks"]["identity_logloss_max_abs"], 1e-10)
        self.assertEqual(0, report["checks"]["duplicate_match_horizon_rows"])
        self.assertEqual([], report["checks"]["train_test_overlap_matches"])
        feature_names = {item["feature"] for item in report["feature_coverage"]}
        self.assertIn("attack_log_ratio", feature_names)
        self.assertIn("model_market_log_residual", feature_names)

    def test_missing_market_capture_stays_in_dataset_denominator(self) -> None:
        model = self._save_capture(
            "model", "m-v1", {"1": 0.48, "X": 0.31, "2": 0.21})
        oddset_v2.FeatureBuilder(self.store).capture(
            self.match, model, "reconstructed")

        row = oddset_v2.build_dataset(self.store)["rows"][0]

        self.assertIn("sharp_capture_missing", row["issues"])
        self.assertIn("features_reconstructed", row["issues"])
        self.assertFalse(row["research_ready"])
        self.assertFalse(row["promotion_ready"])

    def test_earliest_capture_version_wins_without_duplicate_row(self) -> None:
        self._save_capture("sharp", "s-first", {"1": 0.5, "X": 0.3, "2": 0.2})
        later = {**self.capture_base, "tier": "sharp", "signal_version": "s-later",
                 "captured_at": "2026-07-19T12:03:00Z", "delay_minutes": 3.0}
        self.store.oddset_capture_predictions(
            later, self._rows({"1": 0.4, "X": 0.3, "2": 0.3}, "sharp"))
        model = self._save_capture(
            "model", "m-v1", {"1": 0.48, "X": 0.31, "2": 0.21})
        oddset_v2.FeatureBuilder(self.store).capture(self.match, model, "live")

        rows = oddset_v2.build_dataset(self.store)["rows"]

        self.assertEqual(1, len(rows))
        self.assertEqual("s-first", rows[0]["sharp_version"])
        self.assertAlmostEqual(0.5, rows[0]["sharp"]["1"])


if __name__ == "__main__":
    unittest.main()
