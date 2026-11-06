"""V2.2 v10 och poolstyrkans manifest v2 är avslutade per 2026-11-05 09:30Z.

Beslut 2026-11-06-v22-manifest-pinnacle, val 0: Pinnacle spärrar Sverige,
båda spåren var frysta mot Pinnacle. De avslutas som de är (missat är missat):
ingen ny insamling, inga ändrade rader, och hälsan på Idag larmar inte längre.
Avslutet är nycklat på shadow_version — manifestfilerna rörs aldrig.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import oddset_ledger, oddset_v22, pool_health, pool_strength_shadow
from app.storage import Storage
from app.svenskaspel import Draw, Match, Outcome

UTC = dt.timezone.utc
SLUT = "2026-11-05T09:30:00Z"
BESLUT = "2026-11-06-v22-manifest-pinnacle"


class V22AvslutadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_v10_ar_avslutad_med_slutdatum_och_beslut(self):
        self.assertEqual("v2.2-wp9c-multileague-v10",
                         oddset_v22.load_manifest()["experiment"])
        self.assertEqual("v22-fed39cbd", oddset_v22.shadow_version())
        end = oddset_v22.ended()
        self.assertEqual(SLUT, end["ended_at"])
        self.assertEqual(BESLUT, end["decision"])

    def test_halsan_larmar_inte_om_avslutad_kohort(self):
        # Runtime har anchor-v1:s sharpversioner, manifestet Pinnacles — förut
        # ett fel (source_contract_mismatch) på Idag.
        health = oddset_v22.health(self.store)
        self.assertEqual("ended", health["status"])
        self.assertEqual([], health["issues"])
        self.assertEqual(SLUT, health["ended"]["ended_at"])
        self.assertEqual("v22-fed39cbd", health["shadow_version"])

    def test_avslutad_kohort_samlar_inga_nya_rader(self):
        now = dt.datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
        match = {"id": 1, "league": "premier_league", "home": "Arsenal",
                 "away": "Chelsea", "start": "2026-11-06T15:00:00Z",
                 "books": {}}
        self.assertEqual([], oddset_v22.due_matches(self.store, [match], now=now))
        builder = MagicMock(side_effect=AssertionError("V2.2 får inte samla"))
        with patch.object(oddset_v22, "FeatureBuilder", builder):
            oddset_ledger.capture_predictions(
                self.store, [match], tiers=("sharp",), now=now)
        builder.assert_not_called()
        self.assertEqual([], self.store.oddset_v22_shadows())

    def test_audit_och_gater_visar_avslutad(self):
        from app import gater
        report = oddset_v22.audit(self.store)
        self.assertEqual("ended", report["phase"])
        self.assertIn("AVSLUTAD 2026-11-05T09:30:00Z",
                      oddset_v22.format_audit(report))
        rows = gater._v22(self.store)
        self.assertTrue(all(row["status"] == "avslutad"
                            for row in rows if row["namn"].startswith("träningsgate")))
        self.assertIn(BESLUT, rows[-1]["anm"])


def _match(event):
    outcomes = {sign: Outcome(sign, odd, odd, None, None)
                for sign, odd in zip(("1", "X", "2"), (2.0, 3.5, 4.0))}
    return Match(event, "Hammarby - AIK", "Hammarby", "AIK", None, None,
                 "Allsvenskan", "2026-11-06T17:00:00Z", False, None, outcomes)


class PoolstyrkaAvslutadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        # En verklig capture under manifest v2, med den gamla modellversionen.
        self.store.conn.execute(
            "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
            "horizon,event_number,shadow_version,model_signal_version,"
            "captured_at,target_at,delay_min,eligible) VALUES "
            "('stryktipset',1,'h3',1,'ps-8cbcf320','m-6ef4fb7a',"
            "'2026-11-04T22:02:18Z','2026-11-04T22:02:18Z',0,0)")
        self.store.conn.commit()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_manifest_v2_ar_avslutad(self):
        self.assertEqual("ps-8cbcf320", pool_strength_shadow.shadow_version())
        end = pool_strength_shadow.ended()
        self.assertEqual(SLUT, end["ended_at"])
        self.assertEqual(BESLUT, end["decision"])

    def test_poolhalsan_larmar_inte_och_rapporten_sager_avslutad(self):
        with patch("app.pool_strength_shadow.model_signal_version",
                   return_value="m-d3d8e5d0"):
            stop = pool_strength_shadow.stop_status(self.store)
            report = pool_strength_shadow.report(self.store)
            health = pool_health.report(
                self.store, now=dt.datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
                products=("stryktipset",))
        self.assertFalse(stop["stopped"])
        self.assertEqual(SLUT, stop["ended"]["ended_at"])
        self.assertEqual("avslutad", report["status"])
        self.assertIsNone(report["stopped"])
        self.assertEqual(1, report["captured"])
        self.assertNotIn("strength_shadow_stopped",
                         [issue["kind"] for issue in health["issues"]])

    def test_avslutad_kohort_fryser_inget(self):
        now = dt.datetime(2026, 11, 6, 13, 50, tzinfo=UTC)  # h3-fönstret
        draw = Draw("stryktipset", 9001, "Open", "2026-11-06T16:50:00Z",
                    None, 1.0, "2026-11-06T12:00:00Z", matches=[_match(1)])
        result = pool_strength_shadow.capture_due(
            self.store, "stryktipset", draw, {"hits": {}}, now=now)
        self.assertEqual("cohort_ended", result.get("error"))
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM pool_strength_shadow_capture").fetchone()[0])

    def test_gater_och_testkatalogen_visar_avslutad_i_arkivet(self):
        from app import gater, pool_tests
        prognos = {"stryktipset": {"ph4_oot": 8, "ph4_oot_krav": 40}}
        with patch("app.pool_strength_shadow.model_signal_version",
                   return_value="m-d3d8e5d0"), \
                patch("app.main.turnover_prognos", return_value=prognos):
            rows = gater._strength(self.store)
            catalog = pool_tests.catalog(self.store)
        self.assertTrue(all(row["status"] == "avslutad" for row in rows))
        self.assertIn(f"AVSLUTAD {SLUT} (beslut {BESLUT})", rows[0]["anm"])
        test = next(t for t in catalog["tests"] if t["id"] == "poolstyrka")
        self.assertEqual("avslutad", test["status"])
        self.assertTrue(test["archived"])
        self.assertEqual("avslutad", test["decision"]["verdict"])


if __name__ == "__main__":
    unittest.main()
