"""Big 9 i appen (beslut 2026-11-04-big9-i-byggaren): omgångslistan, matchvyn
och byggaren läser ATG-insamlingen och bygger med standardens byggare."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import ny_store  # noqa: E402
from test_atg_big9 import CLOSE, record  # noqa: E402
from app import atg, big9_builder, big9_view  # noqa: E402
from app.spelai import big9, nivaer  # noqa: E402


class Big9ViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.conn = self.store.conn
        atg.apply_schema(self.conn)
        self.now = CLOSE - dt.timedelta(hours=10)
        old = record(serial=500, status="FINALIZED", close=CLOSE - dt.timedelta(days=7),
                     results=["1O"] * 8 + ["*"])
        atg.store_offering(self.conn, [record(), old], {"http_status": 200},
                           fetched_at=self.now, reason="test")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_omgangslistan_skiljer_oppna_och_stangda(self):
        out = big9_view.rounds(self.conn, now=self.now)
        self.assertTrue(out["available"])
        self.assertEqual([600], [r["serial"] for r in out["open"]])
        self.assertEqual([500], [r["serial"] for r in out["recent"]])
        self.assertEqual("Big 9", out["open"][0]["name"])
        self.assertEqual(800_000.0, out["open"][0]["turnover_kr"])
        self.assertEqual("https://www.atg.se/sport/big9", out["atg_url"])
        # efter spelstopp är omgången inte längre öppen, även om ATG säger SELL_OPEN
        later = big9_view.rounds(self.conn, now=CLOSE + dt.timedelta(minutes=1))
        self.assertEqual([], later["open"])

    def test_utan_tabeller(self):
        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp)
        try:
            self.assertFalse(big9_view.rounds(store.conn, now=self.now)["available"])
            self.assertIsNone(big9_view.round_view(store.conn, "sp96", 600, now=self.now))
        finally:
            store.close()
            tmp.cleanup()

    def test_matchvyn_har_odds_streck_och_sex_celler(self):
        view = big9_view.round_view(self.conn, "sp96", 600, now=self.now)
        self.assertTrue(view["open"])
        self.assertFalse(view["wildcard"])
        self.assertEqual(9, len(view["matches"]))
        m = view["matches"][0]
        self.assertEqual("H1", m["home"])
        self.assertEqual(30.0, m["streck"]["1O"])
        self.assertEqual(list(big9_builder.CELLS), [c["cell"] for c in m["cells"]])
        self.assertAlmostEqual(1.0, sum(c["p"] for c in m["cells"]), places=3)
        self.assertEqual("odds", m["p_source"])
        self.assertIsNone(m["outcome"])         # platshållarresultat är inget utfall
        done = big9_view.round_view(self.conn, "sp96", 500, now=self.now)
        self.assertEqual(["1O"] * 8 + ["*"], [m["outcome"] for m in done["matches"]])
        self.assertIsNone(big9_view.round_view(self.conn, "sp96", 999, now=self.now))
        self.assertIsNone(big9_view.round_view(self.conn, "stryktipset", 600, now=self.now))

    def test_byggaren_ar_standardens_byggare(self):
        out = big9_view.build_system(self.conn, "sp96", 600, budget=256,
                                     strategy="medel", now=self.now)
        self.assertEqual(512, out["n_rows"])
        self.assertEqual(256.0, out["cost"])
        self.assertEqual(big9.STANDARD_KEYS["sp96"][256], out["standard_key"])
        # samma rader som facitsidans standard ur samma paket
        obs = atg.latest_observation(self.conn, "sp96", 600)
        payload = big9.build_payload(self.conn, "sp96", obs, None, self.now)
        self.assertIsNone(payload["window"])
        self.assertEqual(big9.build_standard(payload, 256)["rows"], out["rows"])
        nivaer.validera("sp96", 256, {"format": "rows", "rows": out["rows"]})
        self.assertEqual(9, len(out["coverage"]))
        self.assertNotIn("W", out["coverage"][0])
        self.assertTrue(all(sum(c.values()) == 512 for c in out["coverage"]))

    def test_strategi_och_budget(self):
        safe = big9_view.build_system(self.conn, "sp96", 600, budget=16,
                                      strategy="säker", now=self.now)
        self.assertEqual(32, safe["n_rows"])
        self.assertEqual(0.2, safe["value_weight"])
        self.assertIsNone(safe["standard_key"])
        with self.assertRaises(ValueError):
            big9_view.build_system(self.conn, "sp96", 600, budget=100,
                                   strategy="medel", now=self.now)
        with self.assertRaises(ValueError):
            big9_view.build_system(self.conn, "sp96", 600, budget=256,
                                   strategy="tuff", now=self.now)

    def test_stangd_och_okand_omgang(self):
        with self.assertRaises(big9_view.Stangd):
            big9_view.build_system(self.conn, "sp96", 500, budget=256,
                                   strategy="medel", now=self.now)
        with self.assertRaises(big9_view.Stangd):
            big9_view.build_system(self.conn, "sp96", 600, budget=256, strategy="medel",
                                   now=CLOSE + dt.timedelta(seconds=1))
        with self.assertRaises(LookupError):
            big9_view.build_system(self.conn, "sp96", 999, budget=256,
                                   strategy="medel", now=self.now)


if __name__ == "__main__":
    unittest.main()
