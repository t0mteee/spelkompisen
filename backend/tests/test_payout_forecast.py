"""Utdelningsprognosen: pott per nivå delat med förväntat antal vinnande rader
ur folkets streck, givet ställningen nu. Egen skattning, aldrig facit."""
import unittest
from unittest import mock

from app import main, pool_played
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


STRYK = {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}}


def _stryk_states():
    # 13 avgjorda matcher där folket hade 90 % på rätt tecken
    return [state("1", final=True, score="1-0", folk={"1": 90, "X": 5, "2": 5})
            for _ in range(13)]


class MinimumPayoutTests(unittest.TestCase):
    """Statusauditen 2026-09-24: prognoser under Svenska Spels minimiutdelning
    visades fast SvS betalar 0 (Europatipset 2606: 11 rätt 12 kr, 10 rätt 5 kr
    mot publicerat 0)."""

    def test_nivå_under_15_kr_visas_som_noll_med_ra_prognos(self):
        out = pool_played.payout_forecast("stryktipset", STRYK, _stryk_states(),
                                          turnover=10_000)
        self.assertEqual(15.0, out["min_payout_kr"])
        self.assertEqual("belagd", out["min_payout_basis"])
        low = out["levels"][10]
        raw = 10_000 * 0.65 * 0.25 / low["expected_winners"]
        self.assertLess(raw, 15.0)
        self.assertEqual(0, low["per_row_kr"])
        self.assertTrue(low["below_min_payout"])
        self.assertAlmostEqual(round(raw, 1), low["raw_per_row_kr"], places=0)
        # potten och förväntade vinnare är oförändrade — bara visningen
        self.assertEqual(round(10_000 * 0.65 * 0.25), low["pot_kr"])

    def test_nivå_över_gränsen_betalas_som_förut(self):
        # folket hade 40 % på rätt tecken: 10 rätt ≈ 20 kr, 13 rätt ≈ 70 000 kr
        states = [state("1", final=True, score="1-0", folk={"1": 40, "X": 30, "2": 30})
                  for _ in range(13)]
        out = pool_played.payout_forecast("stryktipset", STRYK, states,
                                          turnover=20_000_000)
        for level, entry in out["levels"].items():
            self.assertNotIn("below_min_payout", entry, level)
            self.assertGreaterEqual(entry["per_row_kr"], 15)

    def test_gransen_jamfors_oavrundat(self):
        states = [state("1", final=True, score="1-0", folk={"1": 50, "X": 30, "2": 20}),
                  state("X", final=True, score="0-0", folk={"1": 40, "X": 40, "2": 20})]
        # PLAN2: 500 kr pott på 200 rader = exakt 2,5 kr per rad
        with mock.patch.dict(pool_played.MIN_PAYOUT_KR, {"test": 2.5}):
            at = pool_played.payout_forecast("test", PLAN2, states, turnover=1000)
        with mock.patch.dict(pool_played.MIN_PAYOUT_KR, {"test": 2.51}):
            under = pool_played.payout_forecast("test", PLAN2, states, turnover=1000)
        self.assertNotIn("below_min_payout", at["levels"][2])
        self.assertEqual(2, at["levels"][2]["per_row_kr"])
        self.assertTrue(under["levels"][2]["below_min_payout"])
        self.assertEqual(0, under["levels"][2]["per_row_kr"])

    def test_topptipset_ar_antagen_och_okand_produkt_utan_regel(self):
        plan = {"ratio": 0.70, "splits": {8: 1.0}}
        states = [state("1", final=True, score="1-0", folk={"1": 60, "X": 20, "2": 20})
                  for _ in range(8)]
        for product in ("topptipset", "topptipsetstryk", "topptipsetextra"):
            out = pool_played.payout_forecast(product, plan, states, turnover=100_000)
            self.assertEqual("antagen", out["min_payout_basis"])
            self.assertEqual(15.0, out["min_payout_kr"])
        out = pool_played.payout_forecast("test", PLAN2, [
            state("1", final=True, score="1-0", folk={"1": 50, "X": 30, "2": 20}),
            state("X", final=True, score="0-0", folk={"1": 40, "X": 40, "2": 20})],
            turnover=1000)
        self.assertIsNone(out["min_payout_kr"])
        self.assertNotIn("below_min_payout", out["levels"][2])


class GuaranteeTests(unittest.TestCase):
    """Garantin (t.ex. ensamvinnargaranti) är en EGEN rad och går aldrig in i
    prognosen: Stryktipset 4970 — prognos 2,66 Mkr, publicerat 10 Mkr."""

    def test_ensamvinnargaranti_ar_egen_rad_och_rör_inte_prognosen(self):
        guarantees = [{"type": "SingelWinner", "description": "Ensamvinnargaranti",
                       "amount": 10_000_000.0},
                      {"type": "Okand", "description": None, "amount": 0}]
        without = pool_played.payout_forecast("stryktipset", STRYK, _stryk_states(),
                                              turnover=26_762_377)
        with_g = pool_played.payout_forecast("stryktipset", STRYK, _stryk_states(),
                                             turnover=26_762_377,
                                             guarantees=guarantees)
        self.assertEqual(without["levels"], with_g["levels"])
        self.assertEqual([], without["guarantees"])
        self.assertEqual([{"level": 13, "type": "SingelWinner",
                           "description": "Ensamvinnargaranti",
                           "amount_kr": 10_000_000, "sole_winner": True}],
                         with_g["guarantees"])

    def test_draw_forecast_skickar_med_garantier(self):
        pots = {"turnover": 26_762_377.0, "jackpot": 0.0, "plan": STRYK,
                "observed_at": "2026-09-12T13:50:00Z", "per_level": {}}
        g = [{"type": "SingelWinner", "description": "x", "amount": 10_000_000.0}]
        with mock.patch.object(main, "_draw_pots", return_value=pots), \
                mock.patch.object(main, "_draw_guarantees", return_value=g) as src:
            out = main._draw_forecast(None, "stryktipset", 4970, _stryk_states())
        src.assert_called_once_with("stryktipset", 4970)
        self.assertTrue(out["guarantees"][0]["sole_winner"])

    def test_garantifel_ger_tom_lista_utan_gissning(self):
        class Boom:
            def __enter__(self):
                raise RuntimeError("källan svarar inte")

            def __exit__(self, *exc):
                return False
        with mock.patch.object(main, "SvenskaSpel", return_value=Boom()), \
                self.assertLogs(main.logger, level="WARNING"):
            self.assertEqual([], main._draw_guarantees("stryktipset", 4970))

    def test_garantier_lases_ur_delade_jackpotcachen(self):
        payload = {"jackpots": [{"productId": 1, "drawNumber": 4970,
                                 "guaranteedJackpots": [
                                     {"guaranteedJackpotType": "SingelWinner",
                                      "description": "Ensamvinnargaranti",
                                      "jackpotAmountSek": "10000000,00"}]}]}

        class Source:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def jackpots_payload(self):
                return payload

            def get_guarantees(self, product, draw, data):
                from app.svenskaspel import SvenskaSpel
                return SvenskaSpel.get_guarantees(self, product, draw, data)
        main._jackpots_cache.clear()
        try:
            with mock.patch.object(main, "SvenskaSpel", return_value=Source()), \
                    mock.patch.dict("app.svenskaspel.PRODUCTS",
                                    {"stryktipset": {"pid": 1}}):
                got = main._draw_guarantees("stryktipset", 4970)
        finally:
            main._jackpots_cache.clear()
        self.assertEqual([{"type": "SingelWinner", "description": "Ensamvinnargaranti",
                           "amount": 10_000_000.0}], got)
