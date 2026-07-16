import unittest

from cli import _winner_kappa


class WinnerKappaTests(unittest.TestCase):
    def test_kappa_is_exposure_weighted_ratio_not_mean_of_draw_ratios(self) -> None:
        samples = [(1, 1, 1), (2, 20, 10)]

        estimate, _, _ = _winner_kappa(samples, bootstrap=0)

        self.assertAlmostEqual(21 / 11, estimate)

    def test_bootstrap_is_exact_when_every_draw_has_same_ratio(self) -> None:
        samples = [(1, 2, 1), (2, 8, 4), (3, 20, 10)]

        estimate, lo, hi = _winner_kappa(samples, bootstrap=200)

        self.assertEqual((2.0, 2.0, 2.0), (estimate, lo, hi))

    def test_invalid_rows_are_excluded_and_empty_input_is_rejected(self) -> None:
        self.assertEqual((2.0, 2.0, 2.0),
                         _winner_kappa([(1, 4, 2), (2, 3, 0)], bootstrap=0))
        with self.assertRaises(ValueError):
            _winner_kappa([(1, 0, 0)])


if __name__ == "__main__":
    unittest.main()
