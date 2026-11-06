"""Mätningen av Betfair Exchange/BetInAsia mot Smarkets/SBOBET
(beslut driften-2026-11-06-betexplorer-per-bok, val 0). Beskrivande, inget beslut."""
import tempfile
import unittest
from pathlib import Path

from app import betexplorer_matning as bm
from app import oddset_value
from app.storage import Storage

T = "2026-11-06T12:00:00Z"


class MatningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.store.oddset_upsert_match({
            "id": "m1", "league": "premier_league", "home": "A", "away": "B",
            "start": "2026-11-06T20:00:00Z"})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _cap(self, book, market, prices, at=T, line=None, listed=True):
        self.store.oddset_save_betexplorer_capture(
            "m1", "abcdEFGH", book, market, at, True, listed=listed, line=line,
            prices=prices if listed else None,
            changed_at={k: "2026-11-06T11:30:00Z" for k in prices} if listed else None)

    def _group(self, rep, book, market):
        return next(g for g in rep["groups"] if g["book"] == book and g["market"] == market)

    def test_samma_farskhet_som_vardemotorn(self):
        self.assertEqual(oddset_value.PRICE_MAX_AGE_MIN, bm.MAX_AGE_MIN)

    def test_1x2_paras_mot_smarkets_som_det_var_vid_observationen(self):
        self.store.oddset_save_odds("m1", "smarkets", {"1": 2.0, "X": 3.5, "2": 4.0},
                                    "2026-11-06T11:40:00Z")
        # Ett Smarkets-pris EFTER observationen får aldrig användas.
        self.store.oddset_save_odds("m1", "smarkets", {"1": 1.5, "X": 4.5, "2": 7.0},
                                    "2026-11-06T12:10:00Z")
        self._cap("betfair_ex", "1x2", {"1": 2.0, "X": 3.5, "2": 4.0})
        self._cap("betinasia", "1x2", {"1": 1.9, "X": 3.6, "2": 4.3})
        rep = bm.compare(self.store)
        bf = self._group(rep, "betfair_ex", "1x2")
        self.assertEqual((1, 1, 1, 1), (bf["asked"], bf["listed"], bf["pairs"], bf["matches"]))
        self.assertEqual(0.0, bf["mae_pp"])
        self.assertEqual(30.0, bf["book_age_median_min"])
        bia = self._group(rep, "betinasia", "1x2")
        self.assertGreater(bia["bias_pp"]["1"], 0)      # 1,90 < 2,00 ⇒ högre p
        self.assertGreater(bia["mae_pp"], 0)
        self.assertIn("BetInAsia", bm.format_report(rep))

    def test_inaktuell_referens_paras_inte(self):
        self.store.oddset_save_odds("m1", "smarkets", {"1": 2.0, "X": 3.5, "2": 4.0},
                                    "2026-11-06T11:00:00Z")     # 60 min före t
        self._cap("betfair_ex", "1x2", {"1": 2.0, "X": 3.5, "2": 4.0})
        g = self._group(bm.compare(self.store), "betfair_ex", "1x2")
        self.assertEqual((1, 0), (g["listed"], g["pairs"]))

    def test_handikapp_kraver_samma_lina_som_sbobet(self):
        self.store.oddset_save_market(
            "m1", "sbobet", "ah", {"H": {"odds": 1.95, "line": -0.75},
                                   "A": {"odds": 1.95, "line": -0.75}},
            "2026-11-06T11:50:00Z")
        self._cap("betinasia", "ah", {"H": 1.95, "A": 2.04}, line=-0.75)
        self._cap("betfair_ex", "ah", {"H": 2.2, "A": 1.7}, line=-1.0)
        rep = bm.compare(self.store)
        self.assertEqual(1, self._group(rep, "betinasia", "ah")["pairs"])
        self.assertEqual(0, self._group(rep, "betfair_ex", "ah")["pairs"])
        self.assertEqual("sbobet", self._group(rep, "betinasia", "ah")["reference"])

    def test_ou_2_5_mot_smarkets_och_olistad_raknas_som_fragad(self):
        self.store.oddset_save_market(
            "m1", "smarkets", "ou", {"O": {"odds": 1.8, "line": 2.5},
                                     "U": {"odds": 2.1, "line": 2.5}},
            "2026-11-06T11:55:00Z")
        self._cap("betfair_ex", "ou", {"O": 1.77, "U": 2.14}, line=2.5)
        self._cap("betinasia", "ou", {"O": 1.8, "U": 2.1}, line=None, listed=False)
        rep = bm.compare(self.store)
        bf = self._group(rep, "betfair_ex", "ou")
        self.assertEqual((1, 1), (bf["pairs"], bf["matches"]))
        bia = self._group(rep, "betinasia", "ou")
        self.assertEqual((1, 0, 0), (bia["asked"], bia["listed"], bia["pairs"]))

    def test_fonstret_filtrerar_pa_observationstid(self):
        self.store.oddset_save_odds("m1", "smarkets", {"1": 2.0, "X": 3.5, "2": 4.0},
                                    "2026-11-06T11:40:00Z")
        self._cap("betfair_ex", "1x2", {"1": 2.0, "X": 3.5, "2": 4.0})
        g = self._group(bm.compare(self.store, since="2026-11-06T12:30:00Z"),
                        "betfair_ex", "1x2")
        self.assertEqual(0, g["asked"])


if __name__ == "__main__":
    unittest.main()
