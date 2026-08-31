import math
import unittest
from types import SimpleNamespace

from app.analysis import _normalize_odds
from app.builder import (DRAW_RISK_VERSION, build_ev_system,
                         build_math_system, build_max_math_system,
                         build_reduced_system,
                         draw_risk_values)


SIGNS = ("1", "X", "2")


def _analysis(probabilities, totals=None, product="stryktipset"):
    totals = totals or [None] * len(probabilities)
    matches = []
    for event_number, (probs, total) in enumerate(
            zip(probabilities, totals), 1):
        outcomes = {
            sign: SimpleNamespace(
                fair_prob=probability, sharp_prob=probability,
                streck=probability * 100, tags=[], value=0,
                value_sharp=0)
            for sign, probability in zip(SIGNS, probs)
        }
        favourite = max(SIGNS, key=lambda sign: outcomes[sign].sharp_prob)
        favourite_prob = outcomes[favourite].sharp_prob
        matches.append(SimpleNamespace(
            event_number=event_number, description=f"Match {event_number}",
            cancelled=False, outcomes=outcomes, favourite=favourite,
            favourite_prob=favourite_prob, spik_score=favourite_prob * 100,
            open_score=(1.0 - favourite_prob) * 100,
            best_value_sign=None, total_line=total,
        ))
    return SimpleNamespace(
        matches=matches, turnover=1_000_000.0, product=product)


class DrawRiskThresholdTests(unittest.TestCase):
    def test_frozen_thresholds_and_missing_total(self):
        self.assertTrue(draw_risk_values(0.295, 2.25)["protected"])
        self.assertFalse(draw_risk_values(0.2949, 2.25)["protected"])
        self.assertFalse(draw_risk_values(0.3199, 2.50)["protected"])
        self.assertTrue(draw_risk_values(0.32, None)["protected"])
        self.assertFalse(draw_risk_values(0.3199, None)["protected"])

    def test_europatipset_2603_m20_prices_reconstruct_both_matches(self):
        # Exakt senaste sparade Pinnacle-1X2 före m20-frysningen. Totalerna
        # 2,0/2,25 observerades i samma förhandsmarknad; historiska totaler
        # bakfylls inte i DB efter införandet.
        deportivo = _normalize_odds({"1": 2.66, "X": 2.99, "2": 3.16})
        celta = _normalize_odds({"1": 2.74, "X": 3.26, "2": 2.81})

        first = draw_risk_values(deportivo["X"], 2.0)
        second = draw_risk_values(celta["X"], 2.25)

        self.assertAlmostEqual(0.3254966, deportivo["X"], places=6)
        self.assertAlmostEqual(0.2976548, celta["X"], places=6)
        self.assertTrue(first["protected"])
        self.assertTrue(second["protected"])
        self.assertEqual(DRAW_RISK_VERSION, second["version"])


class DrawRiskBuilderTests(unittest.TestCase):
    def test_protected_half_guard_contains_x_and_likeliest_non_draw(self):
        analysis = _analysis([(0.45, 0.30, 0.25)], [2.25])

        system = build_math_system(
            analysis, strategy="medel", budget=2.0,
            enumerate_rows=True, value_weight=0.8)

        self.assertEqual(["1", "X"], system.picks[0].signs)
        self.assertIn("X-skydd", system.picks[0].reason)

    def test_regular_math_spends_available_guards_on_protected_matches_first(self):
        analysis = _analysis([
            (0.45, 0.30, 0.25),
            (0.35, 0.31, 0.34),
            (0.55, 0.25, 0.20),
        ], [2.25, 2.0, 3.0])

        system = build_math_system(
            analysis, strategy="medel", budget=4.0,
            enumerate_rows=True, value_weight=0.8)
        by_event = {pick.event_number: pick for pick in system.picks}

        self.assertEqual(["1", "X"], by_event[1].signs)
        self.assertEqual(["1", "X"], by_event[2].signs)
        self.assertEqual("spik", by_event[3].role)

    def test_ev_portfolio_meets_each_protected_match_floor(self):
        analysis = _analysis([
            (0.45, 0.30, 0.25),
            (0.35, 0.31, 0.34),
            (0.55, 0.25, 0.20),
            (0.52, 0.27, 0.21),
            (0.48, 0.28, 0.24),
        ], [2.25, 2.0, 3.0, 3.0, 3.0])
        system = build_ev_system(
            analysis, budget=100.0, row_price=1.0, value_weight=0.8,
            plan={"ratio": 0.65, "splits": {5: 1.0}})

        for index, probability in ((0, 0.30), (1, 0.31)):
            required = math.ceil(
                system.num_rows
                * draw_risk_values(probability, analysis.matches[index].total_line)[
                    "minimum_x_share"])
            self.assertGreaterEqual(
                sum(row[index] == "X" for row in system.rows), required)

    def test_full_universe_reserves_x_candidates_before_final_ranking(self):
        probabilities = [(0.45, 0.30, 0.25)] * 3 + [
            (0.55, 0.25, 0.20),
        ] * 8
        analysis = _analysis(
            probabilities, [2.0] * 3 + [3.0] * 8)
        # Gör X hårt överstreckat i just skyddsmatcherna. En ren global
        # toppheap kan då rensa bort kandidaterna före X-golvet appliceras.
        for match in analysis.matches[:3]:
            match.outcomes["X"].streck = 90

        system = build_ev_system(
            analysis, budget=100.0, row_price=1.0, value_weight=0.8,
            plan={"ratio": 0.65, "splits": {11: 1.0}},
            full_universe=True)

        for index in range(3):
            self.assertGreaterEqual(
                sum(row[index] == "X" for row in system.rows), 15)

    def test_no_qualifying_match_leaves_ev_rows_unchanged(self):
        analysis = _analysis([
            (0.55, 0.25, 0.20),
            (0.50, 0.28, 0.22),
            (0.45, 0.29, 0.26),
        ], [2.5, 3.0, None])
        kwargs = dict(
            budget=64.0, row_price=1.0, value_weight=0.5,
            plan={"ratio": 0.65, "splits": {3: 1.0}})

        protected = build_ev_system(analysis, draw_risk=True, **kwargs)
        baseline = build_ev_system(analysis, draw_risk=False, **kwargs)

        self.assertEqual(baseline.rows, protected.rows)

    def test_reduced_system_keeps_x_floor_after_deviation_reduction(self):
        analysis = _analysis([
            (0.45, 0.30, 0.25),
            (0.55, 0.25, 0.20),
            (0.50, 0.28, 0.22),
            (0.48, 0.27, 0.25),
        ], [2.25, 3.0, 3.0, 3.0])

        system = build_reduced_system(
            analysis, strategy="medel", budget=16.0,
            value_weight=0.5)
        minimum = draw_risk_values(0.30, 2.25)["minimum_x_share"]

        self.assertGreaterEqual(
            sum(row[0] == "X" for row in system.rows),
            math.ceil(system.num_rows * minimum))
        self.assertIn(DRAW_RISK_VERSION, system.rule)

    def test_math_max_has_exact_shape_and_does_not_spike_protected_match(self):
        probabilities = [(0.70 - index * 0.01, 0.20, 0.10 + index * 0.01)
                         for index in range(13)]
        # Match 1 ser annars ut som bästa ankaret men skyddas av X/total.
        probabilities[0] = (0.60, 0.30, 0.10)
        analysis = _analysis(probabilities, [2.0] + [3.0] * 12)

        system = build_max_math_system(analysis, value_weight=0.5)
        roles = {pick.event_number: pick.role for pick in system.picks}

        self.assertEqual(39_366, system.num_rows)
        self.assertEqual(39_366, len(system.rows))
        self.assertEqual(39_366, len({tuple(row) for row in system.rows}))
        self.assertEqual(3, sum(role == "spik" for role in roles.values()))
        self.assertEqual(1, sum(
            role == "halvgardering" for role in roles.values()))
        self.assertEqual(9, sum(
            role == "helgardering" for role in roles.values()))
        self.assertNotEqual("spik", roles[1])


if __name__ == "__main__":
    unittest.main()
