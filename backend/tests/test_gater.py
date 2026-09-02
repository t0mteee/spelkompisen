import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import gater
from app.storage import Storage

REQUIRED = {"spar", "namn", "status", "n", "krav", "dagar", "dagar_krav", "ci", "anm"}
SPAR = {"sharp-clv", "wp5-ledger", "v2.2", "radar-blindtest", "ph3-champion",
        "poolstyrka", "ph4-pit-v4"}


class GaterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_tom_databas_ger_en_rad_per_spar_utan_att_krascha(self):
        payload = gater.report(self.store)
        spar = {g["spar"] for g in payload["gates"]}
        self.assertTrue(SPAR <= spar, f"saknar spår: {SPAR - spar}")
        for g in payload["gates"]:
            self.assertEqual(REQUIRED, set(g))
        text = gater.format_report(payload)
        for s in SPAR:
            self.assertIn(s, text)

    def test_en_nere_modul_faller_inte_rapporten(self):
        with patch.object(gater, "_v22", side_effect=RuntimeError("manifest saknas")):
            payload = gater.report(self.store)
        fel = [g for g in payload["gates"] if g["status"] == "fel"]
        self.assertEqual(["v2.2"], [g["spar"] for g in fel])
        self.assertIn("manifest saknas", fel[0]["anm"])
        # Övriga spår lästes ändå.
        self.assertIn("ph3-champion", {g["spar"] for g in payload["gates"]})
        self.assertIn("1 kunde inte läsas", gater.format_report(payload))

    def test_formatering_av_brak_och_ki(self):
        self.assertEqual("12/50", gater._frac(12, 50))
        self.assertEqual("12", gater._frac(12, None))
        self.assertEqual("–", gater._frac(None, 50))
        self.assertEqual("[-0.010, +0.030]", gater._ci([-0.01, 0.03]))
        self.assertEqual("–", gater._ci(None))
