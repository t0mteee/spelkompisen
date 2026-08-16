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

    @staticmethod
    def _concentrated_thirteen_match_analysis():
        """Omgången som visade att 75-procentskravet kunde ge upp helt."""
        rows = [
            (80.1, "2", .3817, 23.8, "2", (.3344, .2839, .3817),
             (.3367, .2850, .3783), (39, 31, 30),
             (("stigande_odds", "rörelse_upp"), (),
              ("värdestreck", "fallande_odds", "sharp_värde", "rörelse_ner"))),
            (0.0, "2", .5819, 47.9, None, (.1945, .2236, .5819),
             (.2035, .2302, .5663), (16, 19, 65),
             (("stigande_odds",), ("stigande_odds", "rörelse_upp"), ())),
            (35.6, "2", .4752, 27.8, "1", (.2660, .2588, .4752),
             (.2729, .2659, .4613), (21, 26, 53),
             (("stigande_odds", "sharp_värde", "rörelse_upp"),
              ("stigande_odds",), ("fallande_odds",))),
            (39.1, "1", .4679, 17.9, "2", (.4679, .2901, .2420),
             (.4513, .2962, .2525), (63, 24, 13),
             ((), (), ("värdestreck", "sharp_värde"))),
            (58.7, "1", .4267, 7.0, None, (.4267, .2588, .3145),
             (.4134, .2605, .3261), (45, 26, 29),
             (("rörelse_upp",), (), ())),
            (0.0, "2", .5523, 56.1, None, (.2078, .2399, .5523),
             (.1900, .2328, .5771), (18, 21, 61),
             (("stigande_odds", "rörelse_upp"), ("rörelse_upp",),
              ("fallande_odds", "rörelse_ner"))),
            (61.3, "2", .4212, 13.6, None, (.3142, .2646, .4212),
             (.2879, .2711, .4410), (25, 26, 49),
             (("värdestreck", "stigande_odds", "rörelse_upp", "rlm_fade"),
              (), ("fallande_odds",))),
            (0.0, "1", .6782, 79.2, "2", (.6782, .1860, .1359),
             (.6693, .1846, .1461), (83, 11, 6),
             (("favorit",), ("värdestreck", "sharp_värde"),
              ("värdestreck", "sharp_värde"))),
            (76.1, "2", .3902, 0.0, None, (.3149, .2949, .3902),
             (.2978, .2913, .4110), (25, 30, 45),
             (("värdestreck", "rörelse_upp"), ("rlm_go",), ())),
            (91.5, "1", .3579, 0.0, None, (.3579, .2908, .3512),
             (.3448, .2931, .3621), (38, 29, 33),
             (("rörelse_upp",), (), ())),
            (3.2, "2", .5433, 37.7, "1", (.2312, .2255, .5433),
             (.2502, .2430, .5068), (19, 19, 62),
             (("sharp_värde",), ("rörelse_ner", "rlm_go"),
              ("rörelse_upp", "rlm_fade"))),
            (0.0, "2", .5895, 49.9, "1", (.1867, .2239, .5895),
             (.2066, .2238, .5696), (11, 19, 70),
             (("värdestreck", "sharp_värde"),
              ("stigande_odds", "rörelse_upp"), ())),
            (45.6, "1", .4542, 30.3, None, (.4542, .2553, .2904),
             (.4866, .2356, .2778), (57, 21, 22),
             (("fallande_odds", "rörelse_ner"),
              ("stigande_odds", "rörelse_upp"),
              ("värdestreck", "stigande_odds", "rörelse_upp"))),
        ]
        descriptions = [
            "Arsenal – Man City", "Lens – Paris SG", "Racing – Villarreal",
            "Espanyol – Levante", "GAIS – Malmö", "Kalmar – Hammarby",
            "Burnley – West Ham", "Ajax – Heerenveen", "Raal La L – Gent",
            "Mechelen – Standard", "Lyngby – Midtjylland",
            "Randers – FC Köpenhamn", "Molde – Tromsö",
        ]
        matches = []
        for event_number, (row, description) in enumerate(zip(rows, descriptions), 1):
            (open_score, favourite, favourite_prob, spik_score, best_value_sign,
             fair, sharp, streck, tags) = row
            outcomes = {
                sign: SimpleNamespace(
                    fair_prob=fair[index], sharp_prob=sharp[index],
                    streck=streck[index], tags=list(tags[index]), value=0)
                for index, sign in enumerate(("1", "X", "2"))
            }
            matches.append(SimpleNamespace(
                event_number=event_number, cancelled=False,
                outcomes=outcomes, open_score=open_score,
                favourite=favourite, favourite_prob=favourite_prob,
                spik_score=spik_score, best_value_sign=best_value_sign,
                description=description))
        return SimpleNamespace(
            turnover=5_090_169.0, matches=matches, product="europatipset")

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
        self.assertFalse(metadata["below_preferred_quality"])

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

    def test_complementary_system_uses_visible_minimum_on_concentrated_draw(self) -> None:
        analysis = self._concentrated_thirteen_match_analysis()
        plan = {
            "ratio": 0.65,
            "splits": {13: 0.39, 12: 0.22, 11: 0.12, 10: 0.25},
        }

        primary, alternative, metadata = build_complementary_ev_systems(
            analysis, budget=256, row_price=1, value_weight=0.5, plan=plan)

        self.assertTrue(metadata["available"])
        self.assertIsNotNone(alternative)
        self.assertEqual(0.60, metadata["quality_floor"])
        self.assertEqual(0.75, metadata["preferred_quality_floor"])
        self.assertTrue(metadata["below_preferred_quality"])
        self.assertGreaterEqual(metadata["primary_quality_ratio"], 0.60)
        self.assertGreaterEqual(metadata["alternative_quality_ratio"], 0.60)
        self.assertLess(metadata["primary_quality_ratio"], 0.75)
        self.assertLess(metadata["alternative_quality_ratio"], 0.75)
        self.assertEqual(primary.num_rows, alternative.num_rows)
        self.assertLessEqual(metadata["row_overlap_pct"], 0.10)

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
