import json
import tempfile
import unittest
from pathlib import Path

from app import pool_played
from app.storage import Storage


def _event(home, away, status_id=31, cancelled=False, number=1):
    """Ett drawEvent i SvS-form: result[Current] + statusId 31 = Slut."""
    return {
        "eventNumber": number, "cancelled": cancelled,
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


def _seed_facit(store, product, draw_number, outcomes):
    """Officiellt facit i settlementlagret: {eventNumber: '1'|'X'|'2'|None}."""
    for number, outcome in outcomes.items():
        store.conn.execute(
            "INSERT INTO pool_event_settlement (product, draw_number, "
            "event_number, outcome, cancelled) VALUES (?,?,?,?,?)",
            (product, draw_number, number, outcome, int(outcome is None)))
    store.conn.commit()


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
        states = [pool_played.event_state(_event("1", "0", number=1)),
                  pool_played.event_state(_event("0", "0", status_id=6, number=2)),
                  pool_played.event_state(_event("0", "1", number=3))]
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

    def test_tecken_paras_pa_eventnummer_inte_payloadordning(self):
        # Granskningsfix F4: payloaden kommer i omvänd ordning. Kolumn 1 = match
        # 1 ('1' efter 1-0), kolumn 2 = match 2 ('2' efter 0-1). Positionsvis
        # zip hade gett 0 säkra; eventNumber-join ger 2.
        states = [pool_played.event_state(_event("0", "1", number=2)),
                  pool_played.event_state(_event("1", "0", number=1))]
        coupon = {"rows_text": "12",
                  "events_order": json.dumps([1, 2]), "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(2, status["best_secure"])
        self.assertTrue(status["all_decided"])

    def test_saknad_match_trunkeras_inte_tyst(self):
        # Granskningsfix F4: payloaden har färre event än kupongen har kolumner.
        # Kolumnen utan match är oavgjord — omgången får ALDRIG bli all_decided.
        states = [pool_played.event_state(_event("1", "0", number=1))]
        coupon = {"rows_text": "11", "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(2, status["n_events"])
        self.assertFalse(status["all_decided"])
        self.assertEqual(1, status["best_secure"])
        self.assertEqual(1, status["alive_per_level"][2])   # kan ännu bli 2 rätt

    def test_struken_match_ar_oavgjord_i_livevyn(self):
        # Granskningsfix F4: SvS FASTSTÄLLER tecknet för en struken match i
        # settlementet — livevyn får inte räkna den som rätt för alla rader.
        states = [pool_played.event_state(
                      _event(None, None, cancelled=True, number=1)),
                  pool_played.event_state(_event("1", "0", number=2))]
        coupon = {"rows_text": "21", "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(1, status["best_secure"])
        self.assertFalse(status["all_decided"])
        self.assertEqual(1, status["alive_per_level"][2])


class SettleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _spelad(self, rows=("111", "112", "121"), events_order=None):
        payload = {"product": "topptipset", "draw_number": 4302,
                   "row_price": 1.0, "rows": list(rows)}
        if events_order:
            payload["events_order"] = events_order
        return pool_played.record(self.store, payload)

    def test_utdelning_anvander_publicerat_belopp_utan_utspadning(self):
        """En spelad kupong ligger REDAN i potten — publicerat belopp per
        vinnare inkluderar oss. Utspädning hör till kontrafaktiska system."""
        kupong = self._spelad()
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong,
                                 tiers={3: (120, 500.0), 2: (3000, 20.0)})
        self.assertTrue(res["settled"])
        self.assertTrue(res["complete"])
        # en rad med 3 rätt (500) + två rader med 2 rätt (2 × 20) = 540
        self.assertEqual(540.0, res["payout_kr"])
        self.assertAlmostEqual((540.0 - 3.0) / 3.0, res["roi"], places=4)

    def test_utan_settlement_settlas_inget(self):
        kupong = self._spelad()
        res = pool_played.settle(self.store, kupong, tiers={3: (1, 1.0)})
        self.assertFalse(res["settled"])

    def test_facit_paras_pa_eventnummer_via_events_order(self):
        # Granskningsfix F4: kupongens kolumnordning [2, 1] mot facit 1:'1',
        # 2:'2'. Rad "21" = kolumn 1 → match 2 ('2' rätt), kolumn 2 → match 1
        # ('1' rätt) ⇒ 2 rätt. Positionsvis zip hade gett 0.
        kupong = self._spelad(rows=("21",), events_order=[2, 1])
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "2"})
        res = pool_played.settle(self.store, kupong, tiers={2: (10, 100.0)})
        self.assertTrue(res["complete"])
        self.assertEqual(2, res["correct_max"])
        self.assertEqual(100.0, res["payout_kr"])

    def test_struken_match_med_faststallt_tecken_raknas_som_tecknet(self):
        # SvS fastställer tecknet för strukna matcher — det gäller, inte
        # "rätt för alla rader".
        kupong = self._spelad(rows=("11", "12"))
        for number, outcome, cancelled in ((1, "1", 0), (2, "2", 1)):
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, outcome, cancelled) VALUES (?,?,?,?,?)",
                ("topptipset", 4302, number, outcome, cancelled))
        self.store.conn.commit()
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["complete"])
        # bara raden "12" träffar den strukna matchens fastställda tecken
        self.assertEqual({2: 1, 1: 1}, res["correct_dist"])
        self.assertEqual(50.0, res["payout_kr"])

    def test_struken_utan_utfall_blir_ofullstandig_aldrig_ratt_for_alla(self):
        kupong = self._spelad(rows=("11",))
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: None})
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["settled"])
        self.assertFalse(res["complete"])
        self.assertIsNone(res["payout_kr"])
        self.assertIn("utfall saknas", res["reason"])
        self.assertEqual(0, pool_played.summary(self.store)["n_settled"])

    def test_breddfel_settlar_aldrig_tyst(self):
        # Kupongen har 2 tecken/rad men omgången 3 matcher — permanent
        # bokföringsfel, markeras ofullständigt i stället för att trunkeras.
        kupong = self._spelad(rows=("11",))
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["settled"])
        self.assertFalse(res["complete"])
        self.assertIn("breddfel", res["reason"])

    def test_saknat_belopp_ger_ofullstandigt_facit_inte_noll(self):
        kupong = self._spelad()
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong,
                                 tiers={3: (0, None), 2: (3000, 20.0)})
        self.assertFalse(res["complete"])
        self.assertIsNone(res["payout_kr"])
        self.assertIsNone(res["roi"])
        # ROI-summeringen får inte räkna in den
        self.assertEqual(0, pool_played.summary(self.store)["n_settled"])


if __name__ == "__main__":
    unittest.main()
