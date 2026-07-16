import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.builder import _prize_pools, build_ev_system


class PrizePoolTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
