"""bomben.py: Poisson-målmodell + kolumnbaserad byggare. Modellen är amber
och utanför CLV, men den bygger rader som Saman kan spela — noll tester förut."""
import unittest
from unittest.mock import patch

from app import bomben

FOLK = [{"score": "0-0", "home": "20,0", "away": "30,0"},
        {"score": "1-1", "home": "50,0", "away": "40,0"},
        {"score": "2-2", "home": "30,0", "away": "30,0"},
        {"score": "F-F", "home": "0,0", "away": "0,0"}]


def _draw(n=3):
    return {"drawNumber": 900, "drawState": "Open", "regCloseTime": "2026-09-05T13:59:00Z",
            "currentNetSales": "10000,00", "matchCount": n,
            "fund": {"rolloverIn": "500,00", "extraMoney": "0,00"},
            "events": [{"eventNumber": i + 1, "eventDescription": f"Lag{i}A - Lag{i}B",
                        "svenskaFolket": FOLK,
                        "match": {"matchStart": "2026-09-05T15:00:00Z",
                                  "participants": [{"type": "home", "name": f"Lag{i}A", "isoCode": "SE"},
                                                   {"type": "away", "name": f"Lag{i}B", "isoCode": "SE"}]}}
                       for i in range(n)]}


class FakePinnacle:
    """Attrapp: alla matcher får λ 1,5/0,8; match 2 spegelvänd (swapped)."""
    def __init__(self):
        self.closed = False

    def match(self, home, away, hiso, aiso, index, match_start=None):
        return {"home": home, "away": away, "home_xg": 1.5, "away_xg": 0.8,
                "swapped": home == "Lag1A"}

    def close(self):
        self.closed = True


class PoissonTests(unittest.TestCase):
    def test_pmf_normaliseras_med_svansen_i_sista_rutan(self):
        pmf = bomben._poisson_pmf(1.0)
        self.assertEqual(bomben.MAX_GOALS + 1, len(pmf))
        self.assertAlmostEqual(1.0, sum(pmf), places=9)
        self.assertGreater(pmf[bomben.MAX_GOALS], 0)


class FolkMarginalTests(unittest.TestCase):
    def test_marginaler_normaliseras_och_ff_hoppas(self):
        h, a = bomben._folk_marginals(FOLK)
        self.assertEqual(3, len(h))
        self.assertAlmostEqual(1.0, sum(h)); self.assertAlmostEqual(1.0, sum(a))
        self.assertAlmostEqual(0.5, h[1]); self.assertAlmostEqual(0.3, a[0])

    def test_tom_folkdata(self):
        h, a = bomben._folk_marginals([])
        self.assertEqual([0.0], h); self.assertEqual([0.0], a)


class AnalyzeTests(unittest.TestCase):
    def test_utan_pinnacle_bara_folk(self):
        res = bomben.analyze_bomben(_draw(), pin_index=None)
        self.assertEqual(900, res["draw_number"])
        self.assertEqual(10000.0, res["turnover"])
        self.assertEqual(500.0, res["rullpott"])
        m = res["matches"][0]
        self.assertFalse(m["has_model"])
        self.assertTrue(all(g["model"] is None for g in m["grid"]))
        self.assertEqual("1-1", m["top_folk"][0]["score"])   # 0,5 × 0,4

    def test_med_modell_summerar_rutnatet_till_ett_och_speglar_swapped(self):
        fake = FakePinnacle()
        with patch.object(bomben, "Pinnacle", return_value=fake):
            res = bomben.analyze_bomben(_draw(), pin_index=[{"id": 1}])
        self.assertTrue(fake.closed)
        m0, m1 = res["matches"][0], res["matches"][1]
        self.assertTrue(m0["has_model"])
        self.assertAlmostEqual(1.0, sum(g["model"] for g in m0["grid"]), places=3)
        self.assertEqual((1.5, 0.8), (m0["home_xg"], m0["away_xg"]))
        self.assertEqual((0.8, 1.5), (m1["home_xg"], m1["away_xg"]))
        self.assertTrue(all(g["ratio"] is not None for g in m0["top_value"]))
        self.assertEqual("1-0", m0["top_model"][0]["score"])


class BuildTests(unittest.TestCase):
    def _analysis(self):
        with patch.object(bomben, "Pinnacle", return_value=FakePinnacle()):
            return bomben.analyze_bomben(_draw(), pin_index=[{"id": 1}])

    def test_radantal_ar_kolumnprodukten_och_ryms_i_budget(self):
        sysm = bomben.build_bomben_system(self._analysis(), budget=50.0, row_price=1.0)
        self.assertLessEqual(sysm["num_rows"], 50)
        prod = 1
        for u in sysm["used"]:
            prod *= len(u["home_goals"]) * len(u["away_goals"])
        self.assertEqual(prod, sysm["num_rows"])
        self.assertEqual(sysm["num_rows"], len(sysm["rows"]))
        self.assertEqual(sysm["num_rows"], sysm["manual_rows"])
        self.assertEqual(sysm["cost"], sysm["num_rows"] * 1.0)
        self.assertEqual(sysm["ev"], sysm["ev_payout"] - sysm["cost"])
        # Raderna är EV-sorterade och varje rad har positiv modellsannolikhet.
        evs = [d["ev"] for d in sysm["detail"]]
        self.assertEqual(evs, sorted(evs, reverse=True))
        self.assertTrue(all(d["p"] > 0 for d in sysm["detail"]))
        self.assertEqual(3, len(sysm["rows"][0]))

    def test_budget_for_en_rad_ger_exakt_en_rad(self):
        sysm = bomben.build_bomben_system(self._analysis(), budget=1.0, row_price=1.0)
        self.assertEqual(1, sysm["num_rows"])
        self.assertEqual(["1-0", "0-1", "1-0"], sysm["rows"][0])

    def test_storre_budget_ger_aldrig_lagre_ev_utdelning(self):
        a = self._analysis()
        small = bomben.build_bomben_system(a, budget=10.0)
        big = bomben.build_bomben_system(a, budget=100.0)
        self.assertGreaterEqual(big["ev_payout"], small["ev_payout"])
        self.assertGreater(big["num_rows"], small["num_rows"])

    def test_tom_analys(self):
        self.assertEqual("Ingen data.", bomben.build_bomben_system({"matches": []})["note"])
