from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from app.pool_input_health import report


def match(number=1, svs=True, sharp=True, total=True, source="odds"):
    return NS(event_number=number, description=f"Lag {number} – Borta", prob_source=source,
              outcomes={s: NS(odds=2.5 if svs else None, sharp_odds=2.6 if sharp else None)
                        for s in ("1", "X", "2")},
              total_line=2.5 if total else None,
              total_over_odds=1.9 if total else None, total_under_odds=1.9 if total else None)


def analysis(*matches):
    return NS(product="test", draw_number=12, fetched_at="2026-09-21T10:00:00Z",
              matches=list(matches), turnover=1000, row_price=1)


class InputHealthTests(unittest.TestCase):
    def test_fullstandigt_underlag_ar_tyst(self):
        r = report(analysis(match()))
        self.assertEqual("ok", r["level"])
        self.assertEqual([], r["issues"])

    def test_pin_saknas_utan_att_pasta_att_allt_saknas(self):
        r = report(analysis(match(sharp=False, total=False), match(2)))
        self.assertEqual("warning", r["level"])
        self.assertEqual((1, 0, 0, 1), tuple(r[k] for k in
            ("missing_sharp", "missing_svs", "missing_all", "missing_total")))
        self.assertEqual("odds", r["issues"][0]["prob_source"])

    def test_delvisa_priser_godkanns_inte_som_komplett(self):
        m = match(sharp=False, source="streck")
        m.outcomes["X"].odds = None
        r = report(analysis(m))
        self.assertEqual("error", r["level"])
        self.assertEqual(1, r["missing_all"])
        self.assertTrue(r["issues"][0]["no_complete_1x2"])

    def test_sharp_reserv_ou_och_ogiltiga_priser(self):
        for value in (None, 0, 1, float("nan"), float("inf"), "3.5", True):
            m = match()
            m.outcomes["X"].odds = value
            self.assertEqual(1, report(analysis(m))["missing_svs"])
        r = report(analysis(match(svs=False, source="sharp")))
        self.assertEqual("warning", r["level"])
        self.assertEqual(0, r["missing_all"])
        m = match()
        m.total_under_odds = None
        self.assertEqual(1, report(analysis(m))["missing_total"])

    def test_analysis_api_bifogar_utan_att_andra_analysen(self):
        from app import main
        a = analysis(match(sharp=False))
        with patch.object(main, "_analyze", return_value=a), \
                patch.object(main, "analysis_to_dict", return_value={"existing": "untouched"}):
            r = main.analysis("test", 12)
        self.assertEqual("untouched", r["existing"])
        self.assertEqual(1, r["input_health"]["missing_sharp"])

    def test_system_api_anvander_just_bygganropets_input(self):
        from app import main
        a = analysis(match(svs=False, sharp=False, source="streck"))
        with patch.object(main, "_analyze", return_value=a), \
                patch.object(main, "build_math_system", return_value=NS()), \
                patch.object(main, "system_to_dict", return_value={"rows": ["1"]}):
            r = main.system(product="test", draw=12, row_model="standard", jackpot=0)
        self.assertEqual(["1"], r["rows"])
        self.assertEqual("error", r["input_health"]["level"])
        self.assertEqual(a.fetched_at, r["input_health"]["analysis_fetched_at"])
