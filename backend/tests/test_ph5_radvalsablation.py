import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts import ph5_radvalsablation as ph5


class Ph5DensitySweepTests(unittest.TestCase):
    def test_fixed_cohort_requires_every_planned_tier(self) -> None:
        plan = {"splits": {13: 0.4, 12: 0.3, 11: 0.2, 10: 0.1}}

        self.assertTrue(ph5._tiers_identifiable(
            {13: (2, 1000), 12: (5, 100), 11: (20, 20), 10: (50, 5)},
            plan))
        self.assertFalse(ph5._tiers_identifiable(
            {13: (0, None), 12: (5, 100), 11: (20, 20), 10: (50, 5)},
            plan))
        self.assertFalse(ph5._tiers_identifiable(
            {13: (2, 1000), 12: (5, 100), 11: (20, 20)}, plan))

    def test_builder_random_uses_exact_builder_universe_without_hamming(self) -> None:
        matches = [SimpleNamespace(event_number=1), SimpleNamespace(event_number=2)]
        draw = SimpleNamespace(
            product="stryktipset", draw_number=1234,
            matches=matches, row_price=1.0)
        analysis = SimpleNamespace(matches=matches)
        system = SimpleNamespace(rows=[["1", "1"], ["X", "X"], ["1", "2"]])
        candidate_signs = {1: ["1", "X"], 2: ["1", "X", "2"]}

        with (patch.object(ph5, "analyze_draw", return_value=analysis),
              patch.object(ph5.builder, "ev_candidate_signs",
                           return_value=(candidate_signs, 6)),
              patch.object(ph5.builder, "build_ev_system", return_value=system),
              patch.object(ph5, "_candidate_rows",
                           return_value=[("1", "1"), ("X", "X"), ("1", "2")])):
            result = ph5.arms(
                draw, 3, random.Random(123), {"splits": {2: 1.0}},
                include_hamming=False)

        exact_universe = {
            (first, second)
            for first in candidate_signs[1]
            for second in candidate_signs[2]
        }
        self.assertEqual(3, len(result["byggarslump"]))
        self.assertTrue(set(result["byggarslump"]).issubset(exact_universe))
        self.assertEqual(6, result["_builder_universe_n"])
        self.assertNotIn("hamming", result)


if __name__ == "__main__":
    unittest.main()
