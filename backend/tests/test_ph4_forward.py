import unittest

from scripts import ph4_ablationer as ph4


class ForwardGateTests(unittest.TestCase):
    def test_development_draws_never_count_toward_forward_volume(self):
        data = [
            ("2026-07-20T12:00:00Z", []),
            ("2026-07-21T12:00:00Z", []),
            ("2026-07-22T12:00:00Z", []),
            ("2026-07-25T12:00:00Z", []),
            ("2026-07-26T12:00:00Z", []),
        ]
        dev, forward = ph4.evaluation_indexes(
            data, min_train=2, evaluation_start="2026-07-25T00:00:00Z")
        self.assertEqual([2], dev)
        self.assertEqual([3, 4], forward)

    def test_variant_missing_feature_is_excluded_not_zero_imputed(self):
        complete = {
            "raw_x": {
                s: {"lnp": -1.0, "streck": 0.3,
                    "streckmove": 0.0, "sharpmove": 0.01}
                for s in ph4.SIGNS
            }
        }
        missing = {
            "raw_x": {
                s: {"lnp": -1.0, "streck": 0.3,
                    "streckmove": 0.0, "sharpmove": None}
                for s in ph4.SIGNS
            }
        }
        self.assertEqual([complete], ph4._eligible(
            [complete, missing], ["lnp", "sharpmove"]))

    def test_empty_forward_phase_has_zero_gate_volume(self):
        summary = ph4.summarize([], bootstrap_n=20, rng=ph4.random.Random(1))
        self.assertEqual(0, summary["n_eval_draws"])
        self.assertEqual("no_forward_data", summary["status"])


if __name__ == "__main__":
    unittest.main()
