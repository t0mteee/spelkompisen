import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import oddset_v2_proxy
from app.storage import Storage


class HistoricalProxyTests(unittest.TestCase):
    def test_rounded_zero_strength_becomes_missing_instead_of_crashing(self) -> None:
        fit = {
            "teams": {"a": {"att": 0.0, "def": 1.0, "n": 10},
                      "b": {"att": 1.0, "def": 1.0, "n": 10}},
            "home_adv": {"allsvenskan": 1.2},
        }

        features, _ = oddset_v2_proxy._fit_features(
            fit, [], "allsvenskan", "2023-01-01", "a", "b", None, None)

        self.assertIsNone(features["attack_log_ratio"])
        self.assertIsNone(features["defence_log_ratio"])

    def test_proxy_uses_requested_price_and_strictly_prior_results_only(self) -> None:
        history = []
        base = dt.date(2022, 10, 1)
        for index in range(45):
            history.append({
                "date": (base + dt.timedelta(days=index)).isoformat(),
                "home": "a", "away": "b", "hg": index % 3,
                "ag": (index + 1) % 3, "ps_close": [2.1, 3.4, 3.6],
            })
        target = {"date": "2023-03-01", "home": "a", "away": "b",
                  "hg": 2, "ag": 0, "ps_close": [2.0, 3.5, 4.0]}

        def source(league, min_season):
            return history + [target] if league == "allsvenskan" else []

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with patch.object(oddset_v2_proxy.oddset_backtest, "fetch_rows",
                                  side_effect=source), patch.object(
                                      oddset_v2_proxy.oddset_data, "merged_results",
                                      return_value=[]):
                    proxy = oddset_v2_proxy.build_historical_proxy(store)
            finally:
                store.close()

        self.assertEqual(1, len(proxy["rows"]))
        row = proxy["rows"][0]
        self.assertEqual("1", row["outcome"])
        self.assertEqual(45, row["feature_source"]["history_rows"])
        self.assertEqual("historical_closing_upper_bound", row["dataset_kind"])
        self.assertEqual("proxy_close", row["horizon"])
        self.assertFalse(row["promotion_ready"])
        self.assertIn("pinnacle_closing_is_after_target_horizons", row["issues"])
        self.assertAlmostEqual(1.0, sum(row["sharp"].values()))


if __name__ == "__main__":
    unittest.main()
