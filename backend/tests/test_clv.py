"""clv.py: poolspelens CLV-facit. Stängning = sista sharp-pris FÖRE avspark;
facit hämtas högst var 6:e timme per omgång. `log_flags` går via
`analyze_draw` och täcks av analysens tester."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import clv
from app.analysis import _power_probs
from app.storage import Storage

NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.timezone.utc)


def _iso(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeSvS:
    def __init__(self, outcomes=None, fail=False):
        self.outcomes, self.fail, self.calls = outcomes, fail, 0

    def get_result(self, product, draw_number):
        self.calls += 1
        if self.fail:
            raise RuntimeError("500")
        return {"outcomes": self.outcomes} if self.outcomes else None


class ClvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now_patch = patch.object(clv, "_now", return_value=NOW)
        self.now_patch.start()

    def tearDown(self):
        self.now_patch.stop()
        self.store.close()
        self.tmp.cleanup()

    def _flag(self, event=1, sign="1", hours_to_start=-2.0, prob=0.50, streck=40):
        start = NOW + dt.timedelta(hours=hours_to_start)
        self.store.log_value_flag({
            "product": "stryktipset", "draw_number": 5000, "event_number": event,
            "sign": sign, "description": "A - B", "match_start": _iso(start),
            "flag_type": "sharp", "odds": 1 / prob, "prob": prob,
            "prob_src": "pinnacle", "streck": streck, "ratio": 1.10,
        }, _iso(NOW - dt.timedelta(hours=6)))

    def _sharp(self, event, hours_ago, odds1, oddsx, odds2):
        at = _iso(NOW - dt.timedelta(hours=hours_ago))
        for sign, odds in (("1", odds1), ("X", oddsx), ("2", odds2)):
            self.store.conn.execute(
                "INSERT INTO sharp_snapshots(product, draw_number, event_number, sign, odds, fetched_at) "
                "VALUES ('stryktipset',5000,?,?,?,?)", (event, sign, odds, at))
        self.store.conn.commit()

    def _row(self, event=1, sign="1"):
        return next(r for r in self.store.clv_rows()
                    if r["event_number"] == event and r["sign"] == sign)

    def test_stangning_ar_sista_priset_fore_avspark(self):
        self._flag(hours_to_start=-2.0)
        self._sharp(1, 3.0, 2.00, 3.50, 3.60)   # före avspark — gäller
        self._sharp(1, 1.0, 1.50, 4.00, 6.00)   # efter avspark — får inte räknas
        res = clv.resolve(self.store)
        self.assertEqual({"closings": 1, "outcomes": 0}, res)
        row = self._row()
        self.assertEqual(2.00, row["closing_odds"])
        expected = _power_probs({"1": 1 / 2.00, "X": 1 / 3.50, "2": 1 / 3.60})["1"]
        self.assertAlmostEqual(expected, row["closing_prob"], places=4)

    def test_ostartad_match_lamnas_oppen(self):
        self._flag(hours_to_start=+3.0)
        self._sharp(1, 1.0, 2.00, 3.50, 3.60)
        self.assertEqual(0, clv.resolve(self.store)["closings"])
        self.assertIsNone(self._row()["closing_prob"])

    def test_saknad_stangning_noteras_forst_efter_en_timme(self):
        self._flag(hours_to_start=-0.5)
        clv.resolve(self.store)
        self.assertIsNone(self._row()["closing_note"])
        self.store.conn.execute("UPDATE value_log SET match_start=?",
                                (_iso(NOW - dt.timedelta(hours=2)),))
        self.store.conn.commit()
        clv.resolve(self.store)
        self.assertEqual("stängningsodds saknas", self._row()["closing_note"])
        # En noterad rad prövas inte igen.
        self.assertEqual([], self.store.unresolved_closings())

    def test_facit_satts_och_hamtas_hogst_var_sjatte_timme(self):
        self._flag(event=1, sign="1")
        self._flag(event=2, sign="X")
        ss = FakeSvS(outcomes={1: "1", 2: "2"})
        res = clv.resolve(self.store, ss)
        self.assertEqual(2, res["outcomes"])
        self.assertEqual(1, ss.calls)
        self.assertEqual(1, self._row(1, "1")["outcome"])
        self.assertEqual(0, self._row(2, "X")["outcome"])
        clv.resolve(self.store, ss)
        self.assertEqual(1, ss.calls, "spärren ska stoppa ett nytt anrop inom 6 h")

    def test_kallfel_lamnar_facit_oppet_utan_att_krascha(self):
        self._flag()
        ss = FakeSvS(fail=True)
        self.assertEqual(0, clv.resolve(self.store, ss)["outcomes"])
        self.assertIsNone(self._row()["outcome"])

    def test_report_raknar_clv_och_traff(self):
        self._flag(event=1, sign="1", prob=0.50)
        self._flag(event=2, sign="2", prob=0.30)
        self.store.set_closing("stryktipset", 5000, 1, "1", prob=0.55, odds=1.8)
        self.store.set_closing("stryktipset", 5000, 2, "2", prob=0.28, odds=3.5)
        self.store.set_outcomes("stryktipset", 5000, {1: "1", 2: "X"})
        rep = clv.report(self.store)
        self.assertEqual(2, rep["n_flagged"]); self.assertEqual(2, rep["n_scored"])
        self.assertEqual(0.5, rep["beat_pct"])
        self.assertAlmostEqual(1.5, rep["avg_clv_pp"])     # (+5 − 2) / 2
        self.assertEqual(2, rep["n_judged"]); self.assertEqual(0.5, rep["hit_pct"])
        self.assertEqual(40.0, rep["avg_streck"])

    def test_report_utan_rader(self):
        rep = clv.report(self.store)
        self.assertEqual(0, rep["n_flagged"])
        self.assertIsNone(rep["beat_pct"]); self.assertIsNone(rep["hit_pct"])
