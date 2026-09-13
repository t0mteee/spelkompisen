"""Testkatalogen: en rad per experiment, cellerna är gater-rader, inget räknas om."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pool_system_ledger as psl
from app import pool_tests
from app.storage import Storage
from tests.test_research_gate import freeze

PROGNOS = {"topptipset": {"ph4_oot": 102, "ph4_oot_krav": 40},
           "stryktipset": {"ph4_oot": 8, "ph4_oot_krav": 40}}


class PoolTestsCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _catalog(self):
        with patch("app.main.turnover_prognos", return_value=PROGNOS):
            return pool_tests.catalog(self.store)

    def test_tom_databas_ger_alla_experiment_i_katalogordning(self):
        payload = self._catalog()
        ids = [t["id"] for t in payload["tests"]]
        self.assertEqual([t["id"] for t in pool_tests.CATALOG], ids)
        for test in payload["tests"]:
            self.assertIn(test["status"], set(pool_tests.RANK))
            self.assertIsInstance(test["cells"], list)
            self.assertTrue(test["purpose"] and test["doc"])
        by_id = {t["id"]: t for t in payload["tests"]}
        self.assertEqual("avslutad", by_id["max40"]["status"])
        self.assertEqual("samlar", by_id["ph5"]["status"])
        self.assertEqual("ph5-v4", by_id["ph5"]["version"])
        self.assertEqual("pit-total-v1", by_id["total"]["version"])
        self.assertEqual(0, by_id["ph5"]["open_coupons"])
        self.assertIsNone(by_id["poolstyrka"]["open_coupons"])
        self.assertEqual("granskad: ej stöd", by_id["ph4"]["decision"]["verdict"])

    def test_oppna_kuponger_raknas_per_experiment_och_cellerna_ar_gater_rader(self):
        keys = [c["key"] for c in psl.PH5_FORWARD_CONFIGS]
        for k in keys:
            freeze(self.store, "stryktipset", 5001, "h3", k)             # öppna
            freeze(self.store, "stryktipset", 5000, "h3", k, correct_max=9, payout_complete=1)
        freeze(self.store, "topptipset", 4310, "h3", psl.CHAMPION_KEY)   # standard, öppen
        by_id = {t["id"]: t for t in self._catalog()["tests"]}
        self.assertEqual(4, by_id["ph5"]["open_coupons"])
        self.assertEqual(1, by_id["standard"]["open_coupons"])
        cell = next(c for c in by_id["ph5"]["cells"] if c["namn"] == "stryktipset 180 min")
        self.assertEqual({"spar", "namn", "status", "n", "krav", "dagar", "dagar_krav", "ci", "anm"},
                         set(cell))
        self.assertEqual((1, 40, "samlar"), (cell["n"], cell["krav"], cell["status"]))
        self.assertEqual({"n": 1, "krav": 40, "namn": "stryktipset 180 min"}, by_id["ph5"]["progress"])

    def test_rubrikstatus_ar_cellen_som_kommit_langst(self):
        self.assertEqual("granskad: ej stöd", pool_tests._headline(
            [{"status": "samlar"}, {"status": "granskad: ej stöd"}], False))
        self.assertEqual("fel", pool_tests._headline([{"status": "fel"}, {"status": "avslutad"}], False))
        self.assertEqual("avslutad", pool_tests._headline([], True))
        self.assertEqual("standard", pool_tests._test_id("ph3-champion"))
        self.assertEqual("max40", pool_tests._test_id("max40-v1 (avslutad)"))
        self.assertIsNone(pool_tests._test_id("sharp-clv"))
