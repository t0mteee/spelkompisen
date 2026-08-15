import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.builder import (_poisson_binomial, _prize_pools,
                         _row_expected_value, build_ev_system,
                         build_complementary_ev_systems,
                         ev_candidate_signs)


class PrizePoolTests(unittest.TestCase):
    @staticmethod
    def _eight_match_analysis():
        probabilities = [
            (0.70, 0.20, 0.10), (0.62, 0.24, 0.14),
            (0.56, 0.27, 0.17), (0.52, 0.28, 0.20),
            (0.48, 0.30, 0.22), (0.45, 0.31, 0.24),
            (0.43, 0.32, 0.25), (0.41, 0.33, 0.26),
        ]
        matches = []
        for event_number, probs in enumerate(probabilities, 1):
            outcomes = {
                sign: SimpleNamespace(
                    fair_prob=probability, sharp_prob=probability,
                    streck=probability * 100, tags=[], value=0)
                for sign, probability in zip(("1", "X", "2"), probs)
            }
            matches.append(SimpleNamespace(
                event_number=event_number, cancelled=False,
                outcomes=outcomes, open_score=30 + event_number * 5,
                favourite="1", favourite_prob=probs[0],
                spik_score=probs[0] * 100, best_value_sign=None,
                description=f"Lag {event_number} A – Lag {event_number} B"))
        return SimpleNamespace(
            turnover=100_000.0, matches=matches, product="topptipset")

    def test_ev_candidate_space_expands_to_cap_without_exceeding_it(self) -> None:
        matches = [SimpleNamespace(event_number=i, open_score=100 - i)
                   for i in range(13)]
        analysis = SimpleNamespace(matches=matches)

        with patch("app.builder._signs_by_score", return_value=["1", "X", "2"]):
            candidates, universe = ev_candidate_signs(analysis, value_weight=0.5)

        # 2^13, därefter fyra öppna matcher × 3/2 = 41 472. En femte
        # helgardering hade gett 62 208 och ska därför stoppas av 60k-taket.
        self.assertEqual(41_472, universe)
        self.assertEqual(4, sum(len(signs) == 3 for signs in candidates.values()))
        self.assertTrue(all(signs in (["1", "X"], ["1", "X", "2"])
                            for signs in candidates.values()))

    def test_jackpot_is_added_only_to_top_tier(self) -> None:
        plan = {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12}}
        pools = _prize_pools(1_000_000, plan, jackpot=250_000)

        self.assertEqual(510_000, pools[13])
        self.assertEqual(97_500, pools[12])
        self.assertEqual(78_000, pools[11])

    def test_negative_jackpot_cannot_reduce_pool(self) -> None:
        plan = {"ratio": 0.70, "splits": {8: 1.0}}
        self.assertEqual({8: 700}, _prize_pools(1_000, plan, jackpot=-50))

    def test_ev_builder_records_jackpot_used_for_row_selection(self) -> None:
        outcomes = {
            sign: SimpleNamespace(
                fair_prob=prob, sharp_prob=None, streck=streck, tags=[], value=0)
            for sign, prob, streck in (("1", 0.60, 60), ("X", 0.25, 25), ("2", 0.15, 15))
        }
        match = SimpleNamespace(
            event_number=1, cancelled=False, outcomes=outcomes, open_score=50,
            favourite="1", favourite_prob=0.60, spik_score=70,
            best_value_sign=None, description="A – B")
        analysis = SimpleNamespace(turnover=1_000.0, matches=[match])

        plan = {"ratio": 0.70, "splits": {1: 1.0}}
        with patch("app.builder._prize_pools", wraps=_prize_pools) as prize_pools:
            system = build_ev_system(
                analysis, budget=2, row_price=1, plan=plan, jackpot=500)

        prize_pools.assert_called_once_with(1_000.0, plan, 500)
        self.assertEqual(500, system.jackpot)
        self.assertIn("Jackpot 500 kr ingår", system.rule)

    def test_complementary_system_builds_two_genuinely_different_anchors(self) -> None:
        analysis = self._eight_match_analysis()
        plan = {"ratio": 0.70, "splits": {8: 1.0}}

        ordinary_before = build_ev_system(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)
        # Regressionen som syntes på Topptipset: basförslaget saknar spikar
        # vid 256 rader, men parbyggaren ska ändå skapa egna ankare.
        self.assertFalse(any(len(pick.signs) == 1
                             for pick in ordinary_before.picks))
        primary, alternative, metadata = build_complementary_ev_systems(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)
        ordinary_after = build_ev_system(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)

        # Det frivilliga parläget får ändra A, men den vanliga enkelbyggaren
        # ska förbli byte-för-byte oförändrad före och efter anropet.
        self.assertEqual(ordinary_before.rows, ordinary_after.rows)
        self.assertIsNotNone(alternative)
        self.assertTrue(metadata["available"])
        self.assertEqual(primary.num_rows, alternative.num_rows)
        self.assertEqual(primary.cost, alternative.cost)
        primary_spikes = {p.event_number for p in primary.picks if len(p.signs) == 1}
        alternative_spikes = {
            p.event_number for p in alternative.picks if len(p.signs) == 1}
        self.assertTrue(primary_spikes)
        self.assertTrue(alternative_spikes)
        self.assertFalse(primary_spikes & alternative_spikes)
        self.assertGreaterEqual(metadata["primary_quality_ratio"], 0.75)
        self.assertGreaterEqual(metadata["alternative_quality_ratio"], 0.75)
        self.assertLessEqual(metadata["row_overlap_pct"], 0.10)

        # Varje kupong får använda den andras ankartecken på högst hälften av
        # raderna. Detta låser regressionen där 90 % följde samma favoriter.
        event_indexes = {
            match.event_number: index
            for index, match in enumerate(analysis.matches)
        }
        for anchor in metadata["primary_spikes"]:
            index = event_indexes[anchor["event_number"]]
            same = sum(row[index] == anchor["sign"] for row in alternative.rows)
            self.assertLessEqual(same, primary.num_rows // 2)
        for anchor in metadata["alternative_spikes"]:
            index = event_indexes[anchor["event_number"]]
            same = sum(row[index] == anchor["sign"] for row in primary.rows)
            self.assertLessEqual(same, primary.num_rows // 2)

    def test_complementary_system_is_deterministic(self) -> None:
        analysis = self._eight_match_analysis()
        plan = {"ratio": 0.70, "splits": {8: 1.0}}

        first = build_complementary_ev_systems(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)
        second = build_complementary_ev_systems(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)

        self.assertEqual(first[0].rows, second[0].rows)
        self.assertEqual(first[1].rows, second[1].rows)
        self.assertEqual(first[2], second[2])

    def test_poisson_binomial_is_normalized_and_exact(self) -> None:
        distribution = _poisson_binomial([0.6, 0.25])

        self.assertAlmostEqual(1.0, sum(distribution), places=12)
        self.assertEqual([0.3, 0.55, 0.15],
                         [round(value, 10) for value in distribution])

    def test_row_ev_uses_pool_division_and_our_hit_probability(self) -> None:
        # En match: vi träffar med 60 %, fältet med 50 %. Tio fältrader ger
        # förväntad utdelning 100/(10*0,5+1), viktad med vår träffchans.
        pf = _poisson_binomial([0.6])
        pk = _poisson_binomial([0.5])

        value = _row_expected_value(pf, pk, {1: 100.0}, field=10.0)

        self.assertAlmostEqual(10.0, value, places=10)


if __name__ == "__main__":
    unittest.main()
