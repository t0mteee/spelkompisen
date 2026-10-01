"""Rättning: PH3:s kontrafaktiska facit med egen utspädning, append-once."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app import pool_system_ledger as ph3  # noqa: E402
from app.spelai import nivaer, ratta  # noqa: E402

UTC = dt.timezone.utc
NOW = START + dt.timedelta(days=3)


class RattaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.conn = self.store.conn

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _forslag(self, role, *, product="topptipset", number=100, level=256,
                 rows=None, tecken=None, status="fryst"):
        n = 13 if tecken else 8
        fmt = "msystem" if tecken else ("rows" if rows else None)
        n_rows = (len(nivaer.expandera(tecken)) if tecken else
                  (len(rows) if rows else None))
        cur = self.conn.execute(
            "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, horizon, "
            "role, status, format, events_order, rows_text, msystem_json, n_rows, "
            "cost_kr, reg_close_time, frozen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (product, number, level, "30m", role, status, fmt,
             ",".join(str(i) for i in range(1, n + 1)),
             "\n".join(rows) if rows else None,
             json.dumps(tecken) if tecken else None, n_rows,
             float(n_rows) if n_rows else None, "2026-10-03T13:59:00Z",
             "2026-10-03T13:29:00Z"))
        self.conn.commit()
        return cur.lastrowid

    def _facit(self, outcomes, tiers, product="topptipset", number=100,
               state="Finalized"):
        self.conn.execute(
            "INSERT INTO pool_draw_settlement (product, draw_number, draw_state, "
            "net_sale, source_version, payload_hash, fetched_at) "
            "VALUES (?, ?, ?, 100000, 't', 'h', '2026-10-03T20:00:00Z')",
            (product, number, state))
        for i, outcome in enumerate(outcomes, start=1):
            self.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, outcome, cancelled) VALUES (?, ?, ?, ?, 0)",
                (product, number, i, outcome))
        for correct, winners, amount in tiers:
            self.conn.execute(
                "INSERT INTO pool_payout_tier (product, draw_number, tier_name, "
                "correct, winners, amount) VALUES (?, ?, ?, ?, ?, ?)",
                (product, number, f"{correct} rätt", correct, winners, amount))
        self.conn.commit()

    def _resultat(self, proposal_id):
        return dict(self.conn.execute("SELECT * FROM spelai_pool_result WHERE "
                                      "proposal_id=?", (proposal_id,)).fetchone())

    def test_utspadning_som_ph3_och_samma_for_agent_och_standard(self):
        rows = ["11111111", "1111111X", "X1111111"]
        agent = self._forslag("agent", rows=rows)
        standard = self._forslag("standard", rows=rows[:1])
        self._facit(["1"] * 8, [(8, 10, 500.0)])
        rep = ratta.settle(self.store, now=NOW)
        self.assertEqual(2, rep["rattade"])
        a = self._resultat(agent)
        # en egen vinnande rad: observerad pott 5 000 delas på 11 vinnare
        self.assertEqual(8, a["correct_max"])
        self.assertAlmostEqual(5000 / 11, a["payout_kr"], places=2)
        self.assertEqual(500.0, a["published_payout_kr"])
        self.assertEqual({"7": 2, "8": 1}, json.loads(a["correct_dist"]))
        self.assertAlmostEqual(round(round(5000 / 11, 2) / 3 - 1, 4), a["roi"], places=4)
        expected = ph3.counterfactual_settle(self.store, "topptipset", 100,
                                             list(range(1, 9)), rows, 3.0)
        self.assertAlmostEqual(expected["payout"], a["payout_kr"], places=2)
        s = self._resultat(standard)
        self.assertAlmostEqual(5000 / 11, s["payout_kr"], places=2)
        self.assertTrue(a["settlement_version"].startswith("spelai-v1/"))

    def test_append_once(self):
        self._forslag("agent", rows=["11111111"])
        self._facit(["1"] * 8, [(8, 10, 500.0)])
        ratta.settle(self.store, now=NOW)
        self.assertEqual(0, ratta.settle(self.store, now=NOW)["rattade"])
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_pool_result").fetchone()[0])

    def test_msystem_expanderas_och_rullpott_ar_ofullstandig(self):
        tecken = ["1", "X", "2", "1X"] + ["1X2"] * 9
        pid = self._forslag("standard", product="stryktipset", number=200,
                            level=39366, tecken=tecken)
        outcomes = ["1", "X", "2", "1"] + ["2"] * 9
        # 13 rätt: 0 officiella vinnare (rullpott okänd) ⇒ ofullständigt facit
        self._facit(outcomes, [(13, 0, 0.0), (12, 40, 900.0), (11, 500, 80.0),
                               (10, 4000, 15.0)], product="stryktipset", number=200)
        ratta.settle(self.store, now=NOW)
        r = self._resultat(pid)
        self.assertEqual(13, r["correct_max"])
        self.assertEqual(0, r["payout_complete"])
        self.assertIsNone(r["payout_kr"])
        self.assertIsNone(r["roi"])
        self.assertEqual(39366, sum(json.loads(r["correct_dist"]).values()))

    def test_installd_omgang_och_bara_frysta(self):
        pid = self._forslag("agent", rows=["11111111"])
        self._forslag("standard", status="missat")
        self._facit(["1"] * 8, [], state="Cancelled")
        rep = ratta.settle(self.store, now=NOW)
        self.assertEqual(1, rep["installda"])
        self.assertEqual(ph3.CANCELLED_NOTE, self._resultat(pid)["note"])
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_pool_result").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
