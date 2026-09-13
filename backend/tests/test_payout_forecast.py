"""Utdelningsprognosen: pott per nivå delat med förväntat antal vinnande rader
ur folkets streck, givet ställningen nu. Egen skattning, aldrig facit."""
import unittest

from app import pool_played
from app.builder import kappa_for

PLAN2 = {"ratio": 0.5, "splits": {2: 1.0}}


def state(sign=None, *, final=False, score=None, folk=None, probs=None, **extra):
    return {"sign": sign, "final": final, "score": score, "cancelled": False,
            "sign_provisional": False, "folk": folk, "prematch_probs": probs, **extra}


class PayoutForecastTests(unittest.TestCase):
    def test_avgjord_match_anvander_streck_pa_tecknet(self):
        states = [state("1", final=True, score="1-0", folk={"1": 50, "X": 30, "2": 20}),
                  state("X", final=True, score="0-0", folk={"1": 40, "X": 40, "2": 20})]
        out = pool_played.payout_forecast("test", PLAN2, states, turnover=1000, row_price=1.0)
        # P(2 rätt) = 0,5 × 0,4 = 0,2 ⇒ 200 rader av 1 000; pott 500 ⇒ 2,5 kr/rad.
        level = out["levels"][2]
        self.assertEqual(200.0, level["expected_winners"])
        self.assertEqual(500, level["pot_kr"])
        self.assertEqual(2, level["per_row_kr"])
        self.assertEqual({"decided": 2, "current": 0, "open": 0}, out["basis"])

    def test_pagaende_anvander_aktuellt_tecken_och_ospelad_marginaliseras(self):
        states = [state("1", final=False, score="1-0", folk={"1": 50, "X": 30, "2": 20}),
                  state(None, folk={"1": 40, "X": 30, "2": 30},
                        probs={"1": 0.5, "X": 0.25, "2": 0.25})]
        out = pool_played.payout_forecast("test", PLAN2, states, turnover=1000)
        # p_B = 0,5·0,4 + 0,25·0,3 + 0,25·0,3 = 0,35 ⇒ P(2) = 0,5 × 0,35 = 0,175.
        self.assertAlmostEqual(175.0, out["levels"][2]["expected_winners"])
        self.assertEqual({"decided": 0, "current": 1, "open": 1}, out["basis"])

    def test_jackpot_pa_toppnivan_kappa_och_golv_pa_en_vinnare(self):
        plan = {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}}
        states = [state("1", final=True, score="1-0", folk={"1": 90, "X": 5, "2": 5})
                  for _ in range(13)]
        out = pool_played.payout_forecast("stryktipset", plan, states, turnover=10_000,
                                          jackpot=5_000)
        top = out["levels"][13]
        expected = 10_000 * (0.9 ** 13) * kappa_for("stryktipset", 13)
        self.assertAlmostEqual(round(expected, 1), top["expected_winners"])
        self.assertEqual(round(10_000 * 0.65 * 0.40 + 5_000), top["pot_kr"])
        # Ingen nivå betalar mer än sin pott: förväntade vinnare golvas vid 1.
        few = pool_played.payout_forecast("stryktipset", plan, states, turnover=2, jackpot=5_000)
        self.assertLess(few["levels"][13]["expected_winners"], 1.0)
        self.assertEqual(few["levels"][13]["pot_kr"], few["levels"][13]["per_row_kr"])
        self.assertEqual({13, 12, 11, 10}, set(out["levels"]))

    def test_utan_streck_eller_omsattning_ingen_prognos(self):
        self.assertIsNone(pool_played.payout_forecast("test", PLAN2, [state("1", final=True)], 1000))
        self.assertIsNone(pool_played.payout_forecast(
            "test", PLAN2, [state("1", final=True, folk={"1": 50, "X": 30, "2": 20})], 0))

    def test_event_state_bar_folkets_streck(self):
        event = {"eventNumber": 1, "match": {"participants": [], "result": []},
                 "svenskaFolket": {"one": "55", "x": "25", "two": "20"}}
        self.assertEqual({"1": 55.0, "X": 25.0, "2": 20.0}, pool_played.event_state(event)["folk"])
        self.assertIsNone(pool_played.event_state({"eventNumber": 2, "match": {}})["folk"])
