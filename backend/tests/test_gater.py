import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import gater
from app import pool_system_ledger as psl
from app.storage import Storage
from tests.test_research_gate import freeze

REQUIRED = {"spar", "namn", "status", "n", "krav", "dagar", "dagar_krav", "ci", "anm"}
SPAR = {"sharp-clv", "wp5-ledger", "v2.2", "radar-blindtest", "ph3-champion",
        "poolstyrka", "ph4-pit-v4", "pit-total-v1",
        "ph5-v4", "mathmax-v2", "reducedmax-v2", "poolopt-v1", "max40-v1 (avslutad)"}
PROGNOS = {"topptipset": {"ph4_oot": 102, "ph4_oot_krav": 40},
           "stryktipset": {"ph4_oot": 8, "ph4_oot_krav": 40}, "basis": "test"}


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
        # Versionen på researchraderna kommer ur nycklarna, aldrig ur en etikett.
        self.assertNotIn("mathmax-v1", text)

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

    def test_sharp_tier_ar_aggregat_aldrig_beslut(self):
        rep = {"sharp": {"green_ready": True, "n_resolved": 2449, "ci": [0.018, 0.025],
                         "avg_close_ev": 0.0215}, "groups": []}
        with patch("app.oddset_value.clv_report", return_value=rep):
            rows = gater._sharp_clv(self.store)
        self.assertEqual("aggregat", rows[0]["status"])
        self.assertIn("aldrig per tier", rows[0]["anm"])

    def test_research_rader_raknar_parade_omgangar_inte_kuponger(self):
        keys = [c["key"] for c in psl.PH5_FORWARD_CONFIGS]
        for draw in (5001, 5002):
            for k in keys:
                freeze(self.store, "stryktipset", draw, "h3", k, correct_max=10, payout_complete=1)
        for k in keys[:2]:
            freeze(self.store, "stryktipset", 5003, "h3", k, correct_max=10, payout_complete=1)
        rows = {r["namn"]: r for r in gater._research(self.store) if r["spar"] == "ph5-v4"}
        r = rows["stryktipset 180 min"]
        self.assertEqual(("samlar", 2, 40), (r["status"], r["n"], r["krav"]))
        self.assertIn("3 frysta omg", r["anm"])
        self.assertIn("saknad arm 1", r["anm"])
        self.assertIn("docs/ph5-forward-2026-08-15.md", r["anm"])

    def test_ph4_granskad_status_las_ur_artefakten(self):
        artefakt = Path(self.tmp.name) / "ph4.json"
        artefakt.write_text(json.dumps({
            "harvested_at": "2026-09-02T10:58:04Z",
            "products": {"topptipset": {"forward": {"d": {"n_eval_draws": 48}}}},
            "promotion_gate": {"candidate": "d", "passes": False, "checks": {
                "topptipset": {"enough_forward_draws": True, "ci_entirely_better": False},
                "stryktipset": {"enough_forward_draws": False, "ci_entirely_better": False}}},
        }), encoding="utf-8")
        with patch.object(gater, "PH4_STATUS_PATH", artefakt), \
                patch("app.main.turnover_prognos", return_value=PROGNOS):
            rows = {r["namn"]: r for r in gater._ph4_oot(self.store)}
        t = rows["out-of-time topptipset"]
        self.assertEqual(("granskad: ej stöd", 102, 40), (t["status"], t["n"], t["krav"]))
        self.assertIn("skördad 2026-09-02 vid 48 omg", t["anm"])
        self.assertIn("nytt manifest", t["anm"])
        self.assertEqual("samlar", rows["out-of-time stryktipset"]["status"])

    def test_ph4_utan_artefakt_ar_underlag_klart_inte_granskad(self):
        with patch.object(gater, "PH4_STATUS_PATH", Path(self.tmp.name) / "saknas.json"), \
                patch("app.main.turnover_prognos", return_value=PROGNOS):
            rows = {r["namn"]: r for r in gater._ph4_oot(self.store)}
        self.assertEqual("underlag klart", rows["out-of-time topptipset"]["status"])
        self.assertEqual("", rows["out-of-time topptipset"]["anm"])
