import itertools
import unittest
from unittest.mock import patch
from dataclasses import asdict

from app import pool_portfolio as p
from scripts.prova_pool_portfolio import prepared_analysis


class PortfolioTests(unittest.TestCase):
    def test_manually_valbar_byggare_haller_budget_och_redovisar_standard(self):
        from app import builder, main
        event = {"event_number": 1, "odds_at_freeze": {"1": 2, "X": 3, "2": 4},
                 "streck_at_freeze": {"1": 50, "X": 30, "2": 20},
                 "sharp_odds_at_freeze": {}, "total_at_freeze": None}
        analysis = prepared_analysis({"events": [{**event,"event_number":i} for i in range(1,9)],
            "product":"topptipset","draw_number":1,"turnover_used":1000000,
            "frozen_at":"2026-09-21T15:00:00Z"},1)
        plan=main.PRIZE_PLANS['topptipset']
        baseline=builder.build_ev_system(analysis,'medel',32,row_price=1,value_weight=.5,plan=plan,jackpot=0)
        before=asdict(analysis)
        system,audit=p.build_manual_test(analysis,'medel',32,1,.5,plan,0)
        self.assertEqual(32,system.num_rows)
        self.assertEqual(32,len({tuple(row) for row in system.rows}))
        self.assertEqual(before,asdict(analysis))
        self.assertTrue(0<audit['baseline_top_chance']<=1)
        self.assertTrue(0<audit['selected_top_chance']<=1)
        self.assertEqual(audit['changed_rows'],len(set(map(tuple,system.rows))-set(map(tuple,baseline.rows))))
        with self.assertRaises(ValueError):
            p.build_manual_test(analysis,'medel',513,1,.5,plan,0)

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
