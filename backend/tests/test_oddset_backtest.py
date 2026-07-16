import unittest

from app import oddset_backtest


class OddsColumnTests(unittest.TestCase):
    def test_closing_columns_are_preferred_with_opening_fallback(self) -> None:
        columns = (("close", ("CH", "CD", "CA")),
                   ("open", ("H", "D", "A")))
        row = {"CH": "2.1", "CD": "3.4", "CA": "3.8",
               "H": "2.2", "D": "3.3", "A": "3.6"}

        odds, timing = oddset_backtest._odds_from_sets(row, columns)

        self.assertEqual([2.1, 3.4, 3.8], odds)
        self.assertEqual("close", timing)
        row["CH"] = ""
        self.assertEqual(
            ([2.2, 3.3, 3.6], "open"),
            oddset_backtest._odds_from_sets(row, columns),
        )


class QualityBacktestTests(unittest.TestCase):
    def test_backtest_probabilities_use_the_live_temperature(self) -> None:
        prediction = {"mu_h": 2.0, "mu_a": 0.8}

        base = oddset_backtest._model_probs(prediction, -0.01, 1.0)
        tempered = oddset_backtest._model_probs(prediction, -0.01, 0.85)

        self.assertAlmostEqual(1.0, sum(tempered.values()), places=10)
        self.assertNotEqual(base, tempered)

    def test_q_penalizes_the_same_edge_at_high_odds(self) -> None:
        self.assertGreater(
            oddset_backtest._quality(0.03, 2.0),
            oddset_backtest._quality(0.03, 10.0),
        )

    def test_policy_applies_edge_floor_and_reports_draw_bias(self) -> None:
        preds = []
        results = ("1", "X", "1", "2", "1", "X")
        for i, result in enumerate(results):
            preds.append({
                "match_id": f"m{i}", "res": result,
                "mkt": {"1": 0.50, "X": 0.30, "2": 0.20},
                "b365": {"1": 2.20, "X": 3.10, "2": 5.20},
                "b365_timing": "close",
            })

        report = oddset_backtest.quality_report(preds)
        policy = report["grid"][f"{oddset_backtest.Q_POLICY:.4f}"]

        # Ettan har edge 10 % och q 8,3 %; tvåan har edge 4 % men q under
        # policygränsen. Kryss har negativ edge. Bara ettan ska väljas.
        self.assertEqual(6, policy["n"])
        self.assertEqual(6, policy["n_matches"])
        self.assertEqual(0, report["policy_by_sign"]["X"]["n"])
        self.assertAlmostEqual(2 / 6, report["draw"]["actual"], places=4)
        self.assertEqual(0.30, report["draw"]["sharp"])
        self.assertEqual({"close": 6, "open": 0}, report["soft_timing"])
        self.assertEqual(1.0, report["coverage"])

    def test_quality_report_rejects_sharp_opening_as_closing_facit(self) -> None:
        prediction = {
            "match_id": "m-opening", "res": "1", "ps_timing": "open",
            "mkt": {"1": 0.50, "X": 0.30, "2": 0.20},
            "b365": {"1": 2.20, "X": 3.10, "2": 5.20},
            "b365_timing": "close",
        }

        report = oddset_backtest.quality_report([prediction])

        self.assertEqual(0, report["n_priced"])
        self.assertEqual(0, report["grid"][f"{oddset_backtest.Q_POLICY:.4f}"]["n"])


if __name__ == "__main__":
    unittest.main()
