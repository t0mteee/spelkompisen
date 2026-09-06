"""Summering per testkategori och liveläge i listan för 5 000-test/maxtester."""
import tempfile
import unittest
from pathlib import Path

from app import pool_played, pool_system_ledger
from app.storage import Storage


def _event(home, away, status_id=31, number=1):
    return {"eventNumber": number, "cancelled": False,
            "match": {"statusId": status_id,
                      "status": "Slut" if status_id == 31 else "Pågår",
                      "sportEventStatus": "Ended" if status_id == 31 else "Live",
                      "result": [
                          {"sportEventResultType": "Current", "home": home, "away": away},
                          {"sportEventResultType": "Halftime", "home": "0", "away": "0"}]}}


class ResearchGroupTests(unittest.TestCase):
    def _test(self, **kw):
        base = {"product": "stryktipset", "horizon": "h3", "horizon_minutes": 180,
                "config_key": "k", "method": "varderader", "label": "EV medel",
                "retired": False, "timely": True, "correct_max": None,
                "payout_complete": None, "cost_kr": 5000.0, "payout_kr": None}
        return {**base, **kw}

    def test_saldo_traffar_och_roi_per_kategori(self):
        tests = [
            self._test(correct_max=13, payout_complete=True, payout_kr=12000.0),
            self._test(correct_max=10, payout_complete=True, payout_kr=0.0),
            self._test(correct_max=11, payout_complete=False, payout_kr=None, retired=True),
            self._test(),                                   # öppen
            self._test(horizon="m20", horizon_minutes=20, correct_max=12,
                       payout_complete=True, payout_kr=800.0),
        ]
        groups = {g["key"]: g for g in pool_system_ledger.research_groups(tests)}
        g = groups["EV medel:h3"]
        self.assertEqual((4, 3, 1, 3, 2), (g["n"], g["n_active"], g["n_open"], g["n_facit"], g["n_settled"]))
        self.assertEqual({13: 1, 12: 0, 11: 1, 10: 1}, g["hits"])
        self.assertEqual((10000.0, 12000.0, 2000.0), (g["cost_kr"], g["payout_kr"], g["balance_kr"]))
        self.assertAlmostEqual(0.2, g["roi"])
        m20 = groups["EV medel:m20"]
        self.assertEqual({13: 0, 12: 1, 11: 0, 10: 0}, m20["hits"])
        self.assertAlmostEqual(-0.84, m20["roi"])
        # Sortering: samma arm, längst frystid först.
        self.assertEqual(["EV medel:h3", "EV medel:m20"],
                         [g["key"] for g in pool_system_ledger.research_groups(tests)])

    def test_topptipset_har_bara_nivan_atta(self):
        g = pool_system_ledger.research_groups(
            [self._test(product="topptipset", correct_max=8, payout_complete=True, payout_kr=500.0)])[0]
        self.assertEqual({8: 1}, g["hits"])

    def test_ph5_overview_bar_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                key = pool_system_ledger.PH5_FORWARD_CONFIGS[0]["key"]
                store.conn.execute(
                    "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
                    "config_key, frozen_at, lag_min, timely, code_version, budget, "
                    "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
                    "rows_text, rows_hash, n_events_covered, turnover_used, "
                    "turnover_basis, jackpot_used) VALUES "
                    "('stryktipset',5001,'h3',?,'2026-08-24T10:00:00Z',2,1,'test',"
                    "5000,'medel',0.5,1,5000,5000,'1','1','hash',1,1000,'live',0)", (key,))
                store.conn.commit()
                report = pool_system_ledger.ph5_overview(store)
                self.assertEqual(1, len(report["groups"]))
                self.assertEqual(1, report["groups"][0]["n_open"])
            finally:
                store.close()


class ResearchLiveOverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.key = pool_system_ledger.PH5_FORWARD_CONFIGS[0]["key"]

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _freeze(self, draw=5001, settled_at=None, rows="1X\n11", horizon="h3"):
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used, settled_at) VALUES "
            "('stryktipset',?,?,?,'2026-08-24T10:00:00Z',2,1,'test',"
            "5000,'medel',0.5,1,2,2,'1,2',?,'hash',2,1000,'live',0,?)",
            (draw, horizon, self.key, rows, settled_at))
        self.store.conn.commit()

    def test_oppna_kuponger_far_lage_och_omgangen_hamtas_en_gang(self):
        self._freeze(horizon="h3"); self._freeze(horizon="m20")
        self._freeze(draw=4000, settled_at="2026-08-01T00:00:00Z")   # avgjord: ingår inte
        calls = []
        states = [pool_played.event_state(_event("1", "0", number=1)),
                  pool_played.event_state(_event("0", "0", status_id=6, number=2))]

        def states_for(keys):
            calls.append(list(keys))
            return {("stryktipset", 5001): states}, {}
        report = pool_system_ledger.research_live_overview(self.store, "ph5", states_for)
        self.assertEqual([[("stryktipset", 5001)]], calls)
        self.assertEqual(["stryktipset:5001"], report["draws"])
        self.assertEqual(2, len(report["tests"]))
        t = report["tests"][0]
        self.assertEqual((2, 1, False), (t["n_events"], t["n_decided"], t["all_decided"]))
        self.assertEqual(1, t["best_secure"])      # raden "11" har ettan rätt
        self.assertEqual(2, t["max_possible"])
        self.assertEqual({}, report["errors"])

    def test_kallfel_pa_en_omgang_faller_inte_de_andra(self):
        self._freeze(draw=5001); self._freeze(draw=5002)
        states = [pool_played.event_state(_event("1", "0", number=1)),
                  pool_played.event_state(_event("0", "0", status_id=6, number=2))]
        report = pool_system_ledger.research_live_overview(
            self.store, "ph5",
            lambda keys: ({("stryktipset", 5002): states}, {("stryktipset", 5001): RuntimeError("503")}))
        self.assertEqual([5002], [t["draw_number"] for t in report["tests"]])
        self.assertIn("stryktipset:5001", report["errors"])

    def test_okand_familj(self):
        with self.assertRaises(ValueError):
            pool_system_ledger.research_live_overview(self.store, "finns-inte", lambda keys: ({}, {}))
