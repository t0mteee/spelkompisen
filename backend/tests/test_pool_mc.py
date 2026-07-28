import math
import unittest
from types import SimpleNamespace

from app.pool_mc import (expected_poisson_reciprocal, materialize_system_rows,
                         simulate_pool_portfolio)


def _analysis(probabilities, draw_number=123):
    matches = []
    for index, probs in enumerate(probabilities, 1):
        outcomes = {
            sign: SimpleNamespace(fair_prob=prob, streck=prob * 100)
            for sign, prob in zip(("1", "X", "2"), probs)
        }
        matches.append(SimpleNamespace(event_number=index, outcomes=outcomes))
    return SimpleNamespace(matches=matches, draw_number=draw_number)


class PoissonShareTests(unittest.TestCase):
    def test_zero_external_winners_split_pool_between_own_rows(self) -> None:
        self.assertEqual(0.25, expected_poisson_reciprocal(0, 4))

    def test_one_own_winner_uses_closed_poisson_formula(self) -> None:
        for expected in (0.001, 0.1, 1.0, 12.0, 1_000_000.0):
            exact = -math.expm1(-expected) / expected
            self.assertAlmostEqual(
                exact, expected_poisson_reciprocal(expected, 1), places=14)

    def test_quadrature_matches_direct_poisson_sum(self) -> None:
        expected, own = 5.0, 17
        probability = math.exp(-expected)
        direct = probability / own
        winners = 0
        while winners < 100:
            winners += 1
            probability *= expected / winners
            direct += probability / (winners + own)

        self.assertAlmostEqual(
            direct, expected_poisson_reciprocal(expected, own), places=13)


class PortfolioSimulationTests(unittest.TestCase):
    def test_one_match_exhaustive_result_matches_hand_calculation(self) -> None:
        analysis = _analysis([(0.6, 0.3, 0.1)])
        report = simulate_pool_portfolio(
            analysis, [["1"]], {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=10, row_price=1, simulations=100,
        )

        conditional_payout = 7 * expected_poisson_reciprocal(6, 1)
        expected_return = 0.6 * conditional_payout
        self.assertEqual("exhaustive", report["method"])
        self.assertEqual(3, report["iterations"])
        self.assertAlmostEqual(expected_return, report["mean_return"], places=2)
        self.assertEqual(0.4, report["probability_zero"])
        self.assertEqual(0.6, report["probability_profit"])
        self.assertAlmostEqual(expected_return,
                               report["top_tier"]["poisson_exact_return"], places=2)

    def test_kappa_per_niva_sanker_ev_som_builderns_radvardering(self) -> None:
        """PH4-κ per nivå (2026-07-28): portföljvärderingen ska använda samma
        kalibrering som builder._row_expected_value — κ > 1 ger fler externa
        medvinnare, lägre utdelning, lägre EV. Konsistens, inte ny modell."""
        analysis = _analysis([(0.6, 0.3, 0.1)])
        base = simulate_pool_portfolio(
            analysis, [["1"]], {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=10, row_price=1, simulations=100,
        )
        corrected = simulate_pool_portfolio(
            analysis, [["1"]], {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=10, row_price=1, simulations=100,
            kappa_by_tier={1: 1.10},
        )
        self.assertLess(corrected["mean_return"], base["mean_return"])
        self.assertEqual({"1": 1.1}, corrected["kappa_by_tier"])
        self.assertIsNone(base["kappa_by_tier"])
        # nivå utan mätning faller tillbaka på skalära kappa (1,0)
        fallback = simulate_pool_portfolio(
            analysis, [["1"]], {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=10, row_price=1, simulations=100,
            kappa_by_tier={0: 1.10},
        )
        self.assertAlmostEqual(base["mean_return"], fallback["mean_return"],
                               places=6)

    def test_own_rows_compete_on_lower_prize_tier(self) -> None:
        analysis = _analysis([(0.5, 0.3, 0.2), (0.5, 0.3, 0.2)])
        report = simulate_pool_portfolio(
            analysis, [["1", "1"], ["1", "X"]],
            {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=10, row_price=1, simulations=100,
        )

        self.assertGreater(report["own_competition_drag"], 0)
        self.assertGreater(report["own_competition_drag_pct"], 0)
        self.assertLessEqual(report["tier_returns"]["1"], 7.0)

    def test_sampled_portfolio_is_reproducible(self) -> None:
        analysis = _analysis([(0.5, 0.3, 0.2)] * 9)
        args = (analysis, [["1"] * 9], {"ratio": 0.70, "splits": {9: 1.0}})

        first = simulate_pool_portfolio(
            *args, turnover=1_000, simulations=200, seed=42)
        second = simulate_pool_portfolio(
            *args, turnover=1_000, simulations=200, seed=42)

        self.assertEqual("monte_carlo", first["method"])
        self.assertEqual(first, second)

    def test_top_tier_poisson_correction_is_close_to_large_field_formula(self) -> None:
        analysis = _analysis([(0.6, 0.3, 0.1)])
        report = simulate_pool_portfolio(
            analysis, [["1"]], {"ratio": 0.70, "splits": {1: 1.0}},
            turnover=1_000, simulations=100,
        )

        self.assertLess(abs(report["top_tier"]["difference"]), 0.05)

    def test_math_system_rows_are_materialized_with_cap(self) -> None:
        system = SimpleNamespace(
            rows=[], picks=[SimpleNamespace(signs=["1", "X"]),
                            SimpleNamespace(signs=["1", "2"])])

        self.assertEqual(
            [["1", "1"], ["1", "2"], ["X", "1"], ["X", "2"]],
            materialize_system_rows(system),
        )
        self.assertIsNone(materialize_system_rows(system, cap=3))


if __name__ == "__main__":
    unittest.main()
