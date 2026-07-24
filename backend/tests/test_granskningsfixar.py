"""Regressionsskydd för granskningsfixarna 2026-07-24.

Varje test låser ett fel som faktiskt fanns i produktion och som hittades
genom att mäta mot settlementlagret eller CLV-facitet.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import builder, main, oddset_ledger, oddset_value
from app.storage import Storage


class VinstplanTests(unittest.TestCase):
    """Uppmätt mot 150 avgjorda omgångar per produkt (PH1-settlementlagret)."""

    def test_europatipset_har_egen_plan_inte_stryktipsets(self):
        stryk = main.PRIZE_PLANS["stryktipset"]["splits"]
        europa = main.PRIZE_PLANS["europatipset"]["splits"]
        # 12-rätt var kopierad från Stryktipset och underskattade potten ~47 %
        self.assertAlmostEqual(0.15, stryk[12])
        self.assertAlmostEqual(0.22, europa[12])
        self.assertNotEqual(stryk, europa)

    def test_payout_ratio_ar_det_som_faktiskt_betalas_ut(self):
        # splits summerar < 1; resten går till jackpotfonder och betalas inte
        # ut i omgången. Uppmätt: Stryk 0,597, Europa 0,636, Topp 0,700.
        for product, expected in (("stryktipset", 0.598),
                                  ("europatipset", 0.637),
                                  ("topptipset", 0.700)):
            got = main._payout_ratio(main.PRIZE_PLANS[product])
            self.assertAlmostEqual(expected, got, places=2, msg=product)
            self.assertLess(got, main.PRIZE_PLANS[product]["ratio"] + 1e-9)

    def test_hurdle_ar_hogre_an_gamla_rubriksiffran_antydde(self):
        ratio = main._payout_ratio(main.PRIZE_PLANS["stryktipset"])
        hurdle = 1.0 / ratio - 1.0
        self.assertGreater(hurdle, 0.66)   # +67 %, inte +54 % som 0,65 gav


class KappaTests(unittest.TestCase):
    """κ ur PH4-analysen (7 754 omgångar) — sänker EV, kan aldrig höja den."""

    def _ev(self, product):
        n = 13 if product in ("stryktipset", "europatipset") else 8
        pf = [0.0] * (n + 1)
        pf[n] = 0.001
        pk = [0.0] * (n + 1)
        pk[n] = 0.0001
        return builder._row_expected_value(
            pf, pk, {n: 1_000_000.0}, 500_000.0, product)

    def test_kappa_sanker_ev_for_alla_produkter(self):
        for product in builder.KAPPA:
            with_k = self._ev(product)
            without_k = self._ev(None)
            self.assertLess(with_k, without_k, msg=product)

    def test_okand_produkt_ger_oforandrat_beteende(self):
        self.assertEqual(1.0, builder.kappa_for(None, 13))
        self.assertEqual(1.0, builder.kappa_for("bomben", 13))
        self.assertEqual(1.0, builder.kappa_for("stryktipset", 9))

    def test_alla_kappavarden_ar_over_ett(self):
        # PH4 mätte κ > 1 genomgående; ett värde < 1 vore en optimistisk
        # korrektion och kräver egen förregistrering.
        for product, levels in builder.KAPPA.items():
            for correct, k in levels.items():
                self.assertGreaterEqual(k, 1.0, msg=f"{product} {correct}")


class ClvFacitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_clv_rows_default_ar_hela_historiken(self):
        for i in range(320):
            self.store.conn.execute(
                "INSERT INTO oddset_value_log (match_id, market, sign, "
                "line_key, tier, first_at, first_odds, first_edge) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"m{i}", "1x2", "1", 0, "sharp",
                 f"2026-01-01T00:{i % 60:02d}:00Z", 2.0, 0.03))
        self.store.conn.commit()
        # default utan argument måste ge ALLA rader — tidigare LIMIT 300 gjorde
        # facitet till ett rullande fönster med survivorship
        self.assertEqual(320, len(self.store.oddset_clv_rows()))
        self.assertEqual(50, len(self.store.oddset_clv_rows(limit=50)))

    def test_snitt_och_ki_mater_samma_estimand(self):
        rows = []
        for i in range(40):
            # en extrem svans som winsoriseringen skär bort
            ev = 5.0 if i == 0 else 0.01
            rows.append({"match_id": f"m{i}", "close_ev": ev,
                         "close_ev_w": max(-0.20, min(0.20, ev)),
                         "line_move_score": None})
        stats = oddset_value._tier_stats(rows)
        self.assertEqual(f"winsoriserad ±20 %", stats["estimand"])
        # huvudsiffran ska vara den winsoriserade — annars kan KI:t utesluta
        # sitt eget medelvärde (observerat: +6,6 % med KI [1,1..4,1])
        self.assertLess(stats["avg_close_ev"], 0.20)
        self.assertGreater(stats["avg_close_ev_raw"], 0.10)
        lo, hi = stats["ci"]
        self.assertLessEqual(lo, stats["avg_close_ev"] + 1e-9)
        self.assertGreaterEqual(hi, stats["avg_close_ev"] - 1e-9)

    def test_censurerade_linjeflyttar_redovisas_och_blockerar_gront(self):
        rows = []
        for i in range(60):        # stängda, starkt positiva
            rows.append({"match_id": f"ok{i}", "close_ev": 0.05,
                         "close_ev_w": 0.05, "line_move_score": None})
        for i in range(80):        # censurerade: linjen flyttade
            rows.append({"match_id": f"cens{i}", "close_ev": None,
                         "close_ev_w": None, "line_move_score": 0.5})
        stats = oddset_value._tier_stats(rows)
        self.assertEqual(60, stats["n_resolved"])
        self.assertEqual(80, stats["n_censored"])
        self.assertEqual(80, stats["n_censored_favorable"])
        self.assertLess(stats["resolved_share"], 0.5)
        # positivt snitt + KI över noll räcker INTE när majoriteten censurerats
        self.assertGreater(stats["avg_close_ev"], 0)
        self.assertFalse(stats["green_ready"])

    def test_gront_slapper_igenom_nar_facitet_ar_representativt(self):
        rows = [{"match_id": f"ok{i}", "close_ev": 0.05, "close_ev_w": 0.05,
                 "line_move_score": None} for i in range(60)]
        rows += [{"match_id": f"c{i}", "close_ev": None, "close_ev_w": None,
                  "line_move_score": 0.5} for i in range(10)]
        stats = oddset_value._tier_stats(rows)
        self.assertGreaterEqual(stats["resolved_share"], 0.5)
        self.assertTrue(stats["green_ready"])


class EvalKadensTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_statusbeslut_ar_kadensstyrda_inte_per_varv(self):
        now = dt.datetime(2026, 7, 24, 12, tzinfo=dt.timezone.utc)
        # inget tidigare beslut => första utvärderingen får ske
        self.assertTrue(oddset_ledger._evaluation_due(self.store, now))
        self.store.meta_set(oddset_ledger.EVAL_META_KEY,
                            oddset_ledger._iso(now))
        # samma dag: nej (annars sekventiell testning vid varje 30-min-varv)
        self.assertFalse(oddset_ledger._evaluation_due(
            self.store, now + dt.timedelta(hours=6)))
        self.assertFalse(oddset_ledger._evaluation_due(
            self.store, now + dt.timedelta(days=6)))
        # efter intervallet: ja
        self.assertTrue(oddset_ledger._evaluation_due(
            self.store, now + dt.timedelta(hours=oddset_ledger.EVAL_INTERVAL_H)))


class StrukenMatchTests(unittest.TestCase):
    """Uppmätt 2026-07-24: strukna matcher avgörs med riktigt resultat (mest
    streckade tecknet vinner 52,8 % — som 52,1 % i ostrukna) och ger INTE
    fler toppvinnare per omsatt krona. Tvingad helgardering var slöseri."""

    def test_ingen_tvingad_helgardering_for_struken_match(self):
        import inspect
        src = inspect.getsource(builder)
        self.assertNotIn("c = 3", src)
        self.assertNotIn("list(SIGNS) if m.cancelled", src)


class GarantiTests(unittest.TestCase):
    def test_garantier_summeras_inte_in_i_jackpot(self):
        # get_guarantees ska vara ett EGET fält; get_jackpot får inte ändras
        import inspect
        from app import svenskaspel
        src = inspect.getsource(svenskaspel.SvenskaSpel.get_jackpot)
        self.assertNotIn("guaranteedJackpots", src)
        self.assertIn("guaranteedJackpots",
                      inspect.getsource(svenskaspel.SvenskaSpel.get_guarantees))


if __name__ == "__main__":
    unittest.main()
