import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import oddset_health
from app.storage import Storage

NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.timezone.utc)


def _iso(at: dt.datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class OddsetHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self._fresh()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _check(self, source, minutes_ago, ok=True, scope="1x2", error=None):
        self.store.oddset_record_source_health(
            source, "allsvenskan", scope, _iso(NOW - dt.timedelta(minutes=minutes_ago)),
            ok, 7, error)

    def _fresh(self):
        """Allt friskt: stämplar 5 min gamla, en lyckad kontroll per källa."""
        self.store.meta_set("oddset_last_run", _iso(NOW - dt.timedelta(minutes=5)))
        self.store.meta_set("pool_tick_last_run", _iso(NOW - dt.timedelta(minutes=3)))
        for src in oddset_health.core_sources():
            self._check(src, 5)
        for src in oddset_health.LIVE_SOURCES:
            self._check(src, 4, scope="live")

    def kinds(self):
        return sorted(i["kind"] for i in oddset_health.report(self.store, now=NOW)["issues"])

    def test_allt_friskt_ger_inga_larm(self):
        payload = oddset_health.report(self.store, now=NOW)
        self.assertEqual("ok", payload["status"])
        self.assertEqual([], payload["issues"])
        self.assertEqual(len(oddset_health.core_sources()), len(payload["sources"]))

    def test_karnkallorna_ar_ankaret_svs_och_bockerna(self):
        self.assertIn("pinnacle", oddset_health.core_sources())
        self.assertIn("svenskaspel", oddset_health.core_sources())
        self.assertNotIn("smarkets", oddset_health.core_sources())
        self.assertNotIn("matchbook", oddset_health.core_sources())

    def test_tyst_oddsetvarv_larmar(self):
        self.store.meta_set("oddset_last_run", _iso(NOW - dt.timedelta(minutes=70)))
        self.assertIn("run_stale", self.kinds())

    def test_stampel_som_aldrig_satts_larmar(self):
        self.store.conn.execute("DELETE FROM meta WHERE key='pool_tick_last_run'")
        self.assertIn("run_never", self.kinds())

    def test_tyst_poolbasvarv_larmar_aven_utan_oppen_omgang(self):
        # Stämpeln skrivs bara efter lyckat basvarv (30 min); 40 min är
        # innanför gränsen, 50 utanför.
        self.store.meta_set("pool_tick_last_run", _iso(NOW - dt.timedelta(minutes=40)))
        self.assertEqual([], self.kinds())
        self.store.meta_set("pool_tick_last_run", _iso(NOW - dt.timedelta(minutes=50)))
        self.assertIn("run_stale", self.kinds())

    def test_kallas_tystnad_larmar_medan_andra_ar_farska(self):
        # Expekt kontrollerades senast för två timmar sedan — resten är färska.
        self.store.conn.execute(
            "DELETE FROM oddset_source_health_log WHERE source='expekt'")
        self._check("expekt", 120)
        payload = oddset_health.report(self.store, now=NOW)
        silent = [i for i in payload["issues"] if i["kind"] == "source_silent"]
        self.assertEqual(["expekt"], [i["source"] for i in silent])

    def test_kalla_utan_kontroll_pa_ett_dygn_larmar(self):
        self.store.conn.execute(
            "DELETE FROM oddset_source_health_log WHERE source='pinnacle'")
        self.assertIn("source_never", self.kinds())

    def test_kalla_som_fragas_men_aldrig_svarar_larmar(self):
        # Kontrollerna är färska men alla misslyckade sedan två timmar.
        self.store.conn.execute(
            "DELETE FROM oddset_source_health_log WHERE source='pinnacle'")
        for m in (100, 60, 30, 5):
            self._check("pinnacle", m, ok=False, error="ConnectError")
        payload = oddset_health.report(self.store, now=NOW)
        failing = [i for i in payload["issues"] if i["kind"] == "source_failing"]
        self.assertEqual(1, len(failing))
        self.assertIn("ConnectError", failing[0]["message"])
        self.assertNotIn("source_silent", self.kinds())

    def test_ett_enstaka_fel_larmar_inte(self):
        self._check("pinnacle", 2, ok=False, error="TimeoutException")
        self.assertEqual([], self.kinds())

    def test_diagnostikkalla_larmar_inte(self):
        self._check("smarkets", 600, ok=False)
        self.assertEqual([], self.kinds())

    def test_tyst_livekalla_larmar_med_egen_grans(self):
        self.store.conn.execute(
            "DELETE FROM oddset_source_health_log WHERE source='flashscore'")
        self._check("flashscore", 25, scope="live")
        self.assertEqual(["live_silent"], self.kinds())

    def test_liveraden_far_inte_lasas_som_oddsetkontroll(self):
        # En livekälla har bara live-scope; en kärnkälla bedöms bara på
        # sina icke-live-scopes.
        self._check("pinnacle", 1, scope="live")
        self.store.conn.execute(
            "DELETE FROM oddset_source_health_log WHERE source='pinnacle' AND scope='1x2'")
        self.assertIn("source_never", self.kinds())

    def test_format_report_namner_varje_fel(self):
        self.store.meta_set("oddset_last_run", _iso(NOW - dt.timedelta(minutes=70)))
        text = oddset_health.format_report(oddset_health.report(self.store, now=NOW))
        self.assertIn("oddset-varv", text)
        self.assertIn("✗", text)
