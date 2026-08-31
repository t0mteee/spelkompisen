import math
import unittest

from app import builder
from app.analysis import analyze_draw
from scripts import optimera_topptips256 as optimizer
from scripts import ph5_radvalsablation as ph5


def _historical_draw(draw_number=4300):
    # Medvetet varierade odds/streck så rankningen saknar artificiella ties.
    events = []
    facit = ("1", "X", "2", "1", "X", "2", "1", "X")
    for index in range(8):
        odds = (1.72 + index * 0.031,
                3.05 + index * 0.043,
                4.60 - index * 0.071)
        streck = (57 - index, 25 + index // 2, 18 + index - index // 2)
        events.append((
            index + 1, f"Lag {index} A - Lag {index} B", facit[index], 0,
            *streck, *odds,
        ))
    return {
        "product": "topptipset", "draw": draw_number,
        "close": f"2026-08-{10 + draw_number % 10:02d}T18:00:00Z",
        "net_sale": 2_000_000.0, "row_price": 1.0,
        "events": events, "tiers": {8: (100, 10_000.0)},
    }


class ConfigTests(unittest.TestCase):
    def test_generator_is_deterministic_unique_and_starts_with_champion(self):
        first = optimizer.generate_configs(100)
        second = optimizer.generate_configs(100)

        self.assertEqual(first, second)
        self.assertEqual(optimizer.CHAMPION_ID, first[0]["id"])
        self.assertEqual(100, len({row["id"] for row in first}))

    def test_history_split_is_global_chronological(self):
        rows = [_historical_draw(4300 + index) for index in range(10)]
        rows.reverse()
        parts = optimizer.split_history(rows)

        self.assertEqual((6, 2, 2), tuple(len(parts[key]) for key in (
            "development", "validation", "test")))
        flat = parts["development"] + parts["validation"] + parts["test"]
        self.assertEqual(sorted(flat, key=optimizer._close_key), flat)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.item = _historical_draw()
        self.prepared = optimizer._prepare(self.item)

    def test_champion_reproduces_production_builder_exactly(self):
        draw, _facit = ph5.as_draw("topptipset", self.item)
        analysis = analyze_draw(draw)
        production = builder.build_ev_system(
            analysis, strategy="medel", budget=256, row_price=1.0,
            value_weight=0.5, plan=ph5.prize_plan("topptipset"), jackpot=0.0,
            draw_risk=False)
        selected = optimizer.select_rows(
            self.prepared, optimizer.champion_config())
        optimized_rows = [optimizer.ALL_ROWS[index] for index in selected]

        self.assertEqual(256, len(selected))
        self.assertEqual([tuple(row) for row in production.rows], optimized_rows)

    def test_full_x_quota_meets_each_market_bucket_minimum(self):
        config = {**optimizer.champion_config(), "id": "quota", "x_quota": 1.0}
        selected = optimizer.select_rows(self.prepared, config)
        counts = {x: sum(optimizer.X_COUNTS[index] == x for index in selected)
                  for x in range(9)}

        self.assertEqual(256, len(selected))
        for x_count, probability in enumerate(self.prepared["x_distribution"]):
            self.assertGreaterEqual(counts[x_count], int(256 * probability))

    def test_sign_cap_is_hard(self):
        config = {**optimizer.champion_config(), "id": "cap", "sign_cap": 0.65}
        selected = optimizer.select_rows(self.prepared, config)
        cap = math.ceil(256 * 0.65)

        self.assertEqual(256, len(selected))
        for column in range(8):
            for sign in optimizer.SIGNS:
                self.assertLessEqual(
                    sum(optimizer.ALL_ROWS[index][column] == sign
                        for index in selected), cap)

    def test_evaluation_has_exact_cost_and_known_facit(self):
        selected = optimizer.select_rows(
            self.prepared, optimizer.champion_config())
        result = optimizer.evaluate_selected(self.prepared, selected)

        self.assertTrue(result["valid"])
        self.assertIn(result["hit"], (0, 1))
        self.assertIsNotNone(result["roi"])
        self.assertGreater(result["expected_hit"], 0)

    def test_rolled_pool_has_no_candidate_dependent_roi(self):
        selected = optimizer.select_rows(
            self.prepared, optimizer.champion_config())
        for hit in (False, True):
            prepared = {**self.prepared, "winners": 0, "amount": 0.0}
            prepared["facit_index"] = (
                selected[0] if hit
                else next(index for index in range(len(optimizer.ALL_ROWS))
                          if index not in set(selected)))
            result = optimizer.evaluate_selected(prepared, selected)

            self.assertEqual(int(hit), result["hit"])
            self.assertIsNone(result["roi"])


class SurvivorTests(unittest.TestCase):
    def test_champion_survives_even_when_challengers_rank_higher(self):
        rows = []
        for index, config in enumerate(optimizer.generate_configs(8)):
            rows.append({
                **config, "passes_floor": True, "balanced_score": float(index),
                "hits": index, "expected_hit_ratio": 1 + index / 100,
                "reference_ev_ratio": 1 + index / 100,
                "paired_winsor_roi_delta": index / 100,
            })
        kept = optimizer.select_survivors(rows, 3)

        self.assertEqual(3, len(kept))
        self.assertIn(optimizer.CHAMPION_ID, kept)

    def test_final_audit_is_paired_and_deterministic(self):
        challenger = "challenger"
        details = {}
        for index, (champion_hit, challenger_hit) in enumerate(
                ((0, 1), (1, 1), (1, 0))):
            details[f"draw:{index}"] = {
                optimizer.CHAMPION_ID: {
                    "valid": True, "hit": champion_hit, "roi": -0.5,
                },
                challenger: {
                    "valid": True, "hit": challenger_hit, "roi": 0.25,
                },
            }

        first = optimizer.final_audit(
            details, [optimizer.CHAMPION_ID, challenger])
        second = optimizer.final_audit(
            details, [optimizer.CHAMPION_ID, challenger])

        self.assertEqual(first, second)
        self.assertEqual(3, first[challenger]["n_draws"])
        self.assertAlmostEqual(0.0, first[challenger]["mean_hit_delta"])
        self.assertAlmostEqual(
            0.75, first[challenger]["mean_winsor_roi_delta"])
        self.assertIsNotNone(
            first[challenger]["hit_delta_ci90_unadjusted"])
        self.assertEqual(
            [0.0, 0.0],
            first[optimizer.CHAMPION_ID]["winsor_roi_delta_ci90_unadjusted"])


if __name__ == "__main__":
    unittest.main()
