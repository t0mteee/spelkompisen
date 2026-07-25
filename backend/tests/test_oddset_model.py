import unittest

from app import oddset_model


class AsianSettlementTests(unittest.TestCase):
    @staticmethod
    def _simple_total_matrix() -> list[list[float]]:
        matrix = [[0.0] * 5 for _ in range(5)]
        matrix[1][1] = 0.2  # total 2
        matrix[2][1] = 0.3  # total 3
        matrix[2][2] = 0.5  # total 4
        return matrix

    def test_pair_fair_handles_push(self) -> None:
        fair = oddset_model.pair_fair(
            self._simple_total_matrix(), "ou", 3.0, ("O", "U"))
        self.assertEqual(1.4, fair["O"])
        self.assertEqual(3.5, fair["U"])
        self.assertAlmostEqual(0.7143, fair["pO"], places=4)
        self.assertAlmostEqual(0.2857, fair["pU"], places=4)

    def test_pair_fair_handles_quarter_line(self) -> None:
        fair = oddset_model.pair_fair(
            self._simple_total_matrix(), "ou", 2.75, ("O", "U"))
        self.assertEqual(1.31, fair["O"])
        self.assertEqual(4.25, fair["U"])
        self.assertAlmostEqual(0.7647, fair["pO"], places=4)
        self.assertAlmostEqual(0.2353, fair["pU"], places=4)

    def test_anchor_roundtrips_settlement_probability_after_temperature(self) -> None:
        temperature = 0.85
        source = oddset_model.temper(
            oddset_model.dc_matrix(1.55, 1.05), temperature)

        for line in (2.5, 3.0, 2.75, 3.25):
            with self.subTest(line=line):
                target = oddset_model.pair_fair(source, "ou", line, ("O", "U"))["pO"]
                mu_h, mu_a = oddset_model._anchor_total(
                    0.9, 1.45, line, target, temperature=temperature)
                anchored = oddset_model.temper(
                    oddset_model.dc_matrix(mu_h, mu_a), temperature)
                actual = oddset_model.pair_fair(
                    anchored, "ou", line, ("O", "U"))["pO"]
                self.assertAlmostEqual(target, actual, delta=1e-3)

    def test_corner_poisson_pair_handles_push_and_is_complementary(self) -> None:
        pair = oddset_model.corner_pair(10.0, 10.0)

        self.assertIsNotNone(pair)
        self.assertAlmostEqual(1.0, pair["pO"] + pair["pU"], places=4)
        self.assertAlmostEqual(1 / pair["O"], pair["pO"], places=2)
        self.assertAlmostEqual(1 / pair["U"], pair["pU"], places=2)


class ModelTransparencyTests(unittest.TestCase):
    def test_market_comparison_devigs_all_sources_and_reports_pp(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "1x2": {"1": 2.0, "X": 4.0, "2": 4.0, "fresh": True},
                    "ou": {"O": 1.8, "U": 2.0, "line": 3.0, "fresh": True},
                },
                "svenskaspel": {
                    "1x2": {"1": 2.1, "X": 3.8, "2": 3.9, "fresh": True},
                    "ou": {"O": 2.0, "U": 1.8, "line": 2.5, "fresh": True},
                },
            },
            "sharp_alt": {
                "ou": {
                    2500: {
                        "O": 1.9, "U": 1.9, "available": True,
                        "last_seen_at": "2026-07-25T10:00:00Z",
                    },
                },
            },
        }
        model = {
            "p": {"1": 0.55, "X": 0.24, "2": 0.21},
            "ou": {"line": 2.5, "pO": 0.54, "pU": 0.46},
        }
        now = oddset_model.dt.datetime(
            2026, 7, 25, 10, 10, tzinfo=oddset_model.dt.timezone.utc)

        result = oddset_model.market_comparisons(match, model, now=now)

        self.assertAlmostEqual(0.5, result["1x2"]["sharp"]["1"], places=4)
        self.assertEqual(5.0, result["1x2"]["model_vs_sharp_pp"]["1"])
        self.assertEqual("pinnacle_alt", result["ou"]["sharp_source"])
        self.assertAlmostEqual(0.5, result["ou"]["sharp"]["O"], places=4)
        self.assertEqual(4.0, result["ou"]["model_vs_sharp_pp"]["O"])
        self.assertIsNotNone(result["ou"]["svs"])

    def test_pair_never_compares_different_lines_without_alt_price(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "ah": {"H": 1.9, "A": 1.9, "line": -0.5, "fresh": True},
                },
                "svenskaspel": {
                    "ah": {"H": 1.9, "A": 1.9, "line": -0.25, "fresh": True},
                },
            },
        }
        model = {"ah": {"line": -0.25, "pH": 0.52, "pA": 0.48}}

        result = oddset_model.market_comparisons(match, model)

        self.assertIsNone(result["ah"]["sharp"])
        self.assertIn("exakt lina", result["ah"]["sharp_note"])

    def test_corner_comparison_uses_the_frozen_sharp_line(self) -> None:
        match = {
            "odds": {
                "pinnacle": {
                    "cor": {"O": 1.9, "U": 1.9, "line": 9.5, "fresh": True},
                },
                "svenskaspel": {
                    "cor": {"O": 2.0, "U": 1.8, "line": 9.5, "fresh": True},
                },
            },
        }
        model = {
            "cor": {"line": 9.5, "pO": 0.55, "pU": 0.45},
        }

        result = oddset_model.market_comparisons(match, model)["cor"]

        self.assertEqual(5.0, result["model_vs_sharp_pp"]["O"])
        self.assertIsNotNone(result["svs"])


if __name__ == "__main__":
    unittest.main()
