import unittest

from app.analysis import _normalize_odds, _power_probs


class PowerDevigTests(unittest.TestCase):
    def test_probabilities_sum_to_one_and_keep_order(self) -> None:
        inv = {"1": 1 / 1.55, "X": 1 / 4.4, "2": 1 / 7.5}

        probs = _power_probs(inv)

        self.assertAlmostEqual(1.0, sum(probs.values()), places=12)
        self.assertGreater(probs["1"], probs["X"])
        self.assertGreater(probs["X"], probs["2"])

    def test_power_method_corrects_favourite_longshot_bias(self) -> None:
        inv = {"1": 1 / 1.55, "X": 1 / 4.4, "2": 1 / 7.5}
        proportional = {sign: value / sum(inv.values())
                        for sign, value in inv.items()}

        probs = _power_probs(inv)

        self.assertGreater(probs["1"], proportional["1"])
        self.assertLess(probs["2"], proportional["2"])

    def test_fair_market_is_unchanged_and_incomplete_market_is_rejected(self) -> None:
        fair = {"1": 0.5, "X": 0.3, "2": 0.2}

        probs = _power_probs(fair)

        for sign in fair:
            self.assertAlmostEqual(fair[sign], probs[sign], places=10)
        self.assertEqual(
            {"1": None, "X": None, "2": None},
            _normalize_odds({"1": 2.0, "X": None, "2": 4.0}),
        )


if __name__ == "__main__":
    unittest.main()
