import json
import tempfile
import unittest
from pathlib import Path

from app import pool_played
from app.storage import Storage


def _event(home, away, status_id=31, cancelled=False):
    """Ett drawEvent i SvS-form: result[Current] + statusId 31 = Slut."""
    return {
        "eventNumber": 1, "cancelled": cancelled,
        "match": {
            "statusId": status_id,
            "status": "Slut" if status_id == 31 else "Pågår",
            "sportEventStatus": "Ended" if status_id == 31 else "Live",
            "result": [
                {"sportEventResultType": "Current", "home": home, "away": away},
                {"sportEventResultType": "Halftime", "home": "0", "away": "0"},
            ],
        },
    }


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _kupong(self, rows=("111", "11X", "1X1")):
        return pool_played.record(self.store, {
            "product": "topptipset", "draw_number": 4300, "row_price": 1.0,
            "rows": list(rows), "build_kind": "värderader", "strategy": "medel",
            "value_weight": 0.5, "budget": 3.0})

    def test_bokfor_och_idempotens(self):
        first = self._kupong()
        self.assertEqual(3, first["n_rows"])
        self.assertEqual(3.0, first["cost_kr"])
        self._kupong()          # samma rader igen
        self.assertEqual(1, len(pool_played.all_coupons(self.store)))

    def test_rader_kan_skickas_som_listor_eller_strangar(self):
        a = pool_played.normalize_rows([["1", "X", "2"], "1x2", "1,X,2"])
        self.assertEqual(["1X2", "1X2", "1X2"], a)

    def test_olika_radlangd_avvisas(self):
        with self.assertRaisesRegex(ValueError, "olika antal"):
            pool_played.record(self.store, {
                "product": "topptipset", "draw_number": 4301,
                "row_price": 1.0, "rows": ["111", "11"]})

    def test_glomma_bort_fungerar_bara_innan_settlement(self):
        kupong = self._kupong()
        self.store.conn.execute(
            "UPDATE pool_played_coupon SET settled_at='2026-07-25T00:00:00Z' "
            "WHERE id=?", (kupong["id"],))
        self.store.conn.commit()
        self.assertFalse(pool_played.forget(self.store, kupong["id"]))


class LiveStatusTests(unittest.TestCase):
    """Livestatus för reducerade system — kärnan i Samans andra önskan."""

    def test_pagaende_match_halls_oppen_for_alla_tecken(self):
        # match 1 klar (1-0 ⇒ '1'), match 2 pågår 0-0, match 3 klar (0-1 ⇒ '2')
        states = [pool_played.event_state(_event("1", "0")),
                  pool_played.event_state(_event("0", "0", status_id=6)),
                  pool_played.event_state(_event("0", "1"))]
        self.assertEqual(("1", True), (states[0]["sign"], states[0]["final"]))
        self.assertEqual(("X", False), (states[1]["sign"], states[1]["final"]))

        coupon = {"rows_text": "1X2\n112\n221", "cost_kr": 3.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(3, status["n_events"])
        self.assertEqual(2, status["n_decided"])
        self.assertFalse(status["all_decided"])
        # Raderna "1X2" och "112" har båda match 1 och 3 rätt ⇒ 2 säkra, och
        # match 2 är oavgjord så BÅDA kan nå 3 rätt — poängen med livestatus är
        # just att en oavgjord match håller alla tecken öppna. "221" har missat
        # två och kan bara nå 1.
        self.assertEqual(2, status["best_secure"])
        self.assertEqual(2, status["alive_per_level"][3])
        self.assertEqual(3, status["alive_per_level"][1])

    def test_struken_match_raknas_som_ratt(self):
        states = [pool_played.event_state(_event(None, None, cancelled=True)),
                  pool_played.event_state(_event("1", "0"))]
        coupon = {"rows_text": "21", "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(2, status["best_secure"])


class SettleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _spelad(self):
        return pool_played.record(self.store, {
            "product": "topptipset", "draw_number": 4302, "row_price": 1.0,
            "rows": ["111", "112", "121"]})

    def test_utdelning_anvander_publicerat_belopp_utan_utspadning(self):
        """En spelad kupong ligger REDAN i potten — publicerat belopp per
        vinnare inkluderar oss. Utspädning hör till kontrafaktiska system."""
        kupong = self._spelad()
        states = [pool_played.event_state(_event("1", "0")),
                  pool_played.event_state(_event("1", "0")),
                  pool_played.event_state(_event("1", "0"))]   # facit 111
        res = pool_played.settle(self.store, kupong, states,
                                 tiers={3: (120, 500.0), 2: (3000, 20.0)})
        self.assertTrue(res["settled"])
        self.assertTrue(res["complete"])
        # en rad med 3 rätt (500) + två rader med 2 rätt (2 × 20) = 540
        self.assertEqual(540.0, res["payout_kr"])
        self.assertAlmostEqual((540.0 - 3.0) / 3.0, res["roi"], places=4)

    def test_oavgjord_omgang_settlas_inte(self):
        kupong = self._spelad()
        states = [pool_played.event_state(_event("1", "0")),
                  pool_played.event_state(_event("0", "0", status_id=6)),
                  pool_played.event_state(_event("1", "0"))]
        self.assertFalse(pool_played.settle(
            self.store, kupong, states, tiers={3: (1, 1.0)})["settled"])

    def test_saknat_belopp_ger_ofullstandigt_facit_inte_noll(self):
        kupong = self._spelad()
        states = [pool_played.event_state(_event("1", "0"))] * 3
        res = pool_played.settle(self.store, kupong, states,
                                 tiers={3: (0, None), 2: (3000, 20.0)})
        self.assertFalse(res["complete"])
        self.assertIsNone(res["payout_kr"])
        self.assertIsNone(res["roi"])
        # ROI-summeringen får inte räkna in den
        self.assertEqual(0, pool_played.summary(self.store)["n_settled"])


if __name__ == "__main__":
    unittest.main()
