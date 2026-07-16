import datetime as dt
import math
import random
import unittest

from app import oddset_v2_model as v2


def _row(index: int, attack: float | None = 0.0,
         outcome: str = "X", league: str = "allsvenskan") -> dict:
    day = dt.date(2024, 1, 1) + dt.timedelta(days=index // 2)
    return {
        "match_id": f"m-{index}", "match_start": f"{day.isoformat()}T12:00:00Z",
        "league": league, "horizon": "proxy_open", "outcome": outcome,
        "sharp": {"1": 0.44, "X": 0.29, "2": 0.27},
        "model": {"1": 0.44, "X": 0.29, "2": 0.27},
        "model_market_log_residual": {"1": 0.0, "X": 0.0, "2": 0.0},
        "features": {
            "attack_log_ratio": attack, "defence_log_ratio": -0.1,
            "home_adv_log": 0.2, "effective_n_home": 12,
            "effective_n_away": 10, "data_age_home_days": 7,
            "data_age_away_days": 12, "elo_diff": 25,
        },
    }


def _draw_outcome(rng: random.Random, probabilities: dict) -> str:
    value = rng.random()
    running = 0.0
    for sign in v2.SIGNS:
        running += probabilities[sign]
        if value <= running:
            return sign
    return "2"


class RidgeResidualTests(unittest.TestCase):
    def test_zero_delta_is_exact_market_identity(self) -> None:
        sharp = {"1": 0.5000001, "X": 0.2999999, "2": 0.2}

        identity = v2.identity_predict(sharp)

        self.assertLess(max(abs(identity[sign] - sharp[sign])
                            for sign in v2.SIGNS), 1e-12)
        self.assertAlmostEqual(1.0, sum(identity.values()), places=12)

    def test_preprocessor_uses_training_only_and_keeps_missing_indicator(self) -> None:
        train = [_row(0, 0.0), _row(1, 2.0), _row(2, None)]
        test = _row(3, 1000.0)

        preprocessor = v2.fit_preprocessor(train)
        missing_vector = v2.transform(train[2], preprocessor)
        test_vector = v2.transform(test, preprocessor)
        names = preprocessor["feature_names"]

        self.assertEqual(1.0, preprocessor["continuous"]["attack_log_ratio"]["mean"])
        self.assertEqual(1, preprocessor["continuous"]["attack_log_ratio"]["missing"])
        self.assertEqual(0.0, missing_vector[names.index("attack_log_ratio")])
        self.assertEqual(1.0, missing_vector[names.index("attack_log_ratio__missing")])
        self.assertGreater(test_vector[names.index("attack_log_ratio")], 900)

    def test_ridge_learns_small_residual_on_synthetic_data(self) -> None:
        rng = random.Random(20260717)
        rows = []
        for index in range(600):
            attack = rng.uniform(-1.5, 1.5)
            row = _row(index, attack)
            eta_1 = math.log(row["sharp"]["1"] / row["sharp"]["X"]) + 0.55 * attack
            eta_2 = math.log(row["sharp"]["2"] / row["sharp"]["X"]) - 0.25 * attack
            pivot = max(0.0, eta_1, eta_2)
            values = {"1": math.exp(eta_1 - pivot), "X": math.exp(-pivot),
                      "2": math.exp(eta_2 - pivot)}
            total = sum(values.values())
            truth = {sign: values[sign] / total for sign in v2.SIGNS}
            row["outcome"] = _draw_outcome(rng, truth)
            rows.append(row)

        model = v2.fit(rows[:450], 0.01)
        market_loss = sum(-math.log(row["sharp"][row["outcome"]])
                          for row in rows[450:]) / 150
        v2_loss = sum(-math.log(v2.predict(model, row)[row["outcome"]])
                      for row in rows[450:]) / 150
        attack_index = model["preprocessor"]["feature_names"].index("attack_log_ratio")

        self.assertTrue(model["converged"])
        self.assertGreater(model["beta_1"][attack_index], 0)
        self.assertLess(model["beta_2"][attack_index], 0)
        self.assertLess(v2_loss, market_loss)


class NestedWalkForwardTests(unittest.TestCase):
    def test_accuracy_and_roi_are_reported_but_not_used_as_gate(self) -> None:
        prediction = {
            "match_id": "bet-1", "outcome": "1",
            "sharp": {"1": 0.48, "X": 0.30, "2": 0.22},
            "v2": {"1": 0.52, "X": 0.28, "2": 0.20},
            "book_odds": {"1": 2.1, "X": 3.2, "2": 4.5},
        }

        metrics = v2._metric_block([prediction])

        self.assertEqual(1.0, metrics["accuracy_v2"])
        self.assertEqual(1, metrics["bets"])
        self.assertAlmostEqual(1.1, metrics["bet_roi"])

    def test_negative_incomplete_rows_trigger_preregistered_guardrail(self) -> None:
        prediction = {
            "match_id": "missing-1", "match_start": "2026-01-01T12:00:00Z",
            "league": "allsvenskan", "outcome": "1", "complete_features": False,
            "sharp": {"1": 0.6, "X": 0.25, "2": 0.15},
            "v2": {"1": 0.5, "X": 0.3, "2": 0.2}, "book_odds": None,
        }
        walk = {"policy_version": v2.policy_version(), "horizon": "h24",
                "n_eligible": 1, "predictions": [prediction], "folds": [],
                "penalty_counts": {}}

        report = v2.evaluation_report(walk, "historical_closing_upper_bound")

        self.assertIn("incomplete_feature_guardrail_failed",
                      report["decision"]["reasons"])

    def test_date_blocks_and_nested_folds_never_overlap(self) -> None:
        rng = random.Random(7)
        rows = []
        for index in range(90):
            row = _row(index, rng.uniform(-1, 1), ("1", "X", "2")[index % 3],
                       "eliteserien" if index % 2 else "allsvenskan")
            rows.append(row)
        policy = {
            "outer_min_train_matches": 40, "outer_test_matches": 20,
            "inner_min_train_matches": 20, "inner_validation_matches": 10,
            "inner_folds": 2, "same_utc_date_is_one_block": True,
        }

        walk = v2.nested_walk_forward(rows, "proxy_open", (0.01, 0.1), policy)

        self.assertGreaterEqual(len(walk["folds"]), 2)
        self.assertEqual(walk["n_predictions"], len(walk["predictions"]))
        for fold in walk["folds"]:
            self.assertLess(fold["train_end"], fold["test_start"])
            for inner in fold["inner_folds"]:
                self.assertLess(inner["train_end"], inner["validation_start"])

    def test_proxy_dataset_can_never_pass_promotion_gate(self) -> None:
        walk = {"policy_version": v2.policy_version(), "n_eligible": 0,
                "predictions": [], "folds": [], "penalty_counts": {}}

        report = v2.evaluation_report(walk, "historical_opening_proxy")

        self.assertFalse(report["decision"]["pass"])
        self.assertIn("dataset_is_not_frozen_live_outer_test",
                      report["decision"]["reasons"])


if __name__ == "__main__":
    unittest.main()
