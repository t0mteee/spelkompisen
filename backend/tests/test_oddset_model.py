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


if __name__ == "__main__":
    unittest.main()
