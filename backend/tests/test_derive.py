"""derive.py: 1X2 ur Pinnacles spread + total. Helt ren matematik — men den
matar både `P~`-odds i Oddset och Bombens målmodell, och hade noll tester."""
import unittest

from app import derive


def _spread(*lines):
    """lines: (home_points, home_price, away_price). Pinnacles amerikanska pris."""
    out = []
    for pts, hp, ap in lines:
        out.append({"points": pts, "designation": "home", "price": hp})
        out.append({"points": -pts, "designation": "away", "price": ap})
    return out


def _total(*lines):
    out = []
    for pts, over, under in lines:
        out.append({"points": pts, "designation": "over", "price": over})
        out.append({"points": pts, "designation": "under", "price": under})
    return out


# Balanserad total 2,5: (2,0 → over 58 %), (2,5 → 50 %), (3,0 → 42 %).
TOTAL_25 = _total((2.0, -150, 130), (2.5, -110, -110), (3.0, 130, -150))
# Balanserad linje 0 = jämna lag.
SPREAD_EVEN = _spread((0.0, -105, -105), (0.5, -150, 130), (1.0, -220, 180))
# Balanserad linje −1,0 = hemma är ett mål bättre.
SPREAD_HOME_FAV = _spread((-1.5, 130, -150), (-1.0, -105, -105), (-0.5, -150, 130))


class AmericanToProbTests(unittest.TestCase):
    def test_negativt_och_positivt_pris(self):
        self.assertAlmostEqual(2 / 3, derive.american_to_prob(-200))
        self.assertAlmostEqual(0.4, derive.american_to_prob(150))
        self.assertIsNone(derive.american_to_prob(None))


class CrossAtHalfTests(unittest.TestCase):
    def test_exakt_traff_och_interpolation(self):
        self.assertAlmostEqual(0.0, derive._cross_at_half([(-1, 0.3), (0, 0.5), (1, 0.7)]))
        self.assertAlmostEqual(0.0, derive._cross_at_half([(-0.5, 0.4), (0.5, 0.6)]))
        self.assertAlmostEqual(0.25, derive._cross_at_half([(0.0, 0.4), (0.5, 0.6)]))

    def test_utan_korsning_valjs_narmaste(self):
        self.assertEqual(1.0, derive._cross_at_half([(0.0, 0.7), (1.0, 0.6)]))
        self.assertIsNone(derive._cross_at_half([]))


class GoalExpectationTests(unittest.TestCase):
    def test_jamna_lag_delar_totalen_lika(self):
        self.assertEqual((1.25, 1.25), derive.goal_expectations(SPREAD_EVEN, TOTAL_25))

    def test_supremacy_flyttar_mal_till_favoriten(self):
        h, a = derive.goal_expectations(SPREAD_HOME_FAV, TOTAL_25)
        self.assertAlmostEqual(1.75, h)
        self.assertAlmostEqual(0.75, a)
        self.assertAlmostEqual(2.5, h + a)

    def test_underlag_saknas_ger_none(self):
        self.assertIsNone(derive.goal_expectations([], TOTAL_25))
        self.assertIsNone(derive.goal_expectations(SPREAD_EVEN, []))
        # En enda linje räcker inte för att hitta balanspunkten.
        self.assertIsNone(derive.goal_expectations(_spread((0.0, -105, -105)), TOTAL_25))


class Derive1x2Tests(unittest.TestCase):
    def test_jamna_lag_ger_symmetriska_odds_utan_marginal(self):
        odds = derive.derive_1x2(SPREAD_EVEN, TOTAL_25)
        self.assertEqual(odds["1"], odds["2"])
        # Härledda odds är rättvisa: ingen overround.
        self.assertAlmostEqual(1.0, sum(1 / o for o in odds.values()), places=2)
        # P(X) vid λ=1,25/1,25 ≈ 0,27.
        self.assertAlmostEqual(0.27, 1 / odds["X"], delta=0.02)

    def test_favoriten_far_lagre_odds(self):
        odds = derive.derive_1x2(SPREAD_HOME_FAV, TOTAL_25)
        self.assertLess(odds["1"], odds["X"])
        self.assertLess(odds["1"], odds["2"])

    def test_utan_underlag_none(self):
        self.assertIsNone(derive.derive_1x2([], []))
