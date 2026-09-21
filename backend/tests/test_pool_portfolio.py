import itertools
import unittest
from unittest.mock import patch
from dataclasses import asdict

from app import pool_portfolio as p
from scripts.prova_pool_portfolio import prepared_analysis


class PortfolioTests(unittest.TestCase):
    def test_bitset_stammer_med_bruteforce(self):
        samples = list(itertools.product(p.SIGNS, repeat=4))
        masks, all_bits = p._sample_index(samples)
        row = ("1", "X", "2", "1")
        for radius, bits in enumerate(p._coverage(row, masks, all_bits, 3)):
            expected = sum(1 << i for i, s in enumerate(samples)
                           if sum(a != b for a, b in zip(row, s)) <= radius)
            self.assertEqual(expected, bits)

    def test_samma_budget_unika_reproducerbara_rader_och_orord_referens(self):
        candidates = [(1, 1, r) for r in itertools.product(p.SIGNS, repeat=3)]
        baseline = candidates[:5]
        original = list(baseline)
        chosen, audit = p.select_portfolio(candidates, baseline, [[1/3]*3]*3, samples=512)
        again, _ = p.select_portfolio(list(reversed(candidates)), baseline, [[1/3]*3]*3, samples=512)
        self.assertEqual(chosen, again)
        self.assertEqual(5, len({r[2] for r in chosen}))
        self.assertEqual(original, baseline)
        self.assertGreater(audit["changed_rows"], 0)

    def test_teckengolv_kan_inte_tyst_brytas(self):
        candidates = [(1, 1, r) for r in itertools.product(p.SIGNS, repeat=3)]
        baseline = candidates[:5]
        chosen, audit = p.select_portfolio(candidates, baseline, [[1/3]*3]*3,
                                          samples=512, minimum_shares={(0, "1"): 1})
        self.assertEqual(baseline, chosen)
        self.assertTrue(audit["fallback"])

    def test_felaktig_sannolikhet_och_dubblett_referens_avvisas(self):
        with self.assertRaises(ValueError):
            p.sample_outcomes([[0.8, 0.3, 0.1]], 10, 1)
        with self.assertRaises(ValueError):
            p.select_portfolio([], [(1, 1, ("1",))]*2, [[1/3]*3])

    def test_ev_golvet_stoppar_for_lag_kvalitet(self):
        baseline = [(1, 100, ("1",))]
        with patch.object(p, "EV_WEIGHT", 0):
            chosen, audit = p.select_portfolio([(1, 1, ("2",))], baseline,
                                              [[.01, .01, .98]], samples=512)
        self.assertEqual(baseline, chosen)
        self.assertIn("EV-golv", audit["fallback"])

    def test_replayinput_ignorerar_facit_och_slutstreck(self):
        event = {"event_number": 1, "odds_at_freeze": {"1": 2, "X": 3, "2": 4},
                 "streck_at_freeze": {"1": 50, "X": 30, "2": 20},
                 "sharp_odds_at_freeze": {}, "total_at_freeze": None}
        detail = {"events": [event], "product": "topptipset", "draw_number": 1,
                  "turnover_used": 100000, "frozen_at": "2026-09-19T13:40:00Z"}
        first = asdict(prepared_analysis(detail, 1))
        event.update(outcome="2", cancelled=True, streck_at_close={"1": 1, "X": 1, "2": 98})
        self.assertEqual(first, asdict(prepared_analysis(detail, 1)))
        event["odds_at_freeze"]["X"] = None
        with self.assertRaises(ValueError):
            prepared_analysis(detail, 1)
