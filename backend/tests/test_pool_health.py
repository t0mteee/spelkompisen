import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pool_health, pool_system_ledger
from app.pool_system_ledger import benchmarks_for
from app.storage import Storage


NOW = dt.datetime(2026, 8, 9, 13, 0, tzinfo=dt.timezone.utc)


class PoolHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _draw(self, product="stryktipset", number=5000, hours=8):
        close = NOW + dt.timedelta(hours=hours)
        self.store.conn.execute(
            "INSERT INTO draws(product,draw_number,state,reg_close_time) "
            "VALUES (?,?,?,?)", (product, number, "Open", close.isoformat()))
        return close

    def _snapshot(self, product="stryktipset", number=5000, minutes_ago=2):
        at = NOW - dt.timedelta(minutes=minutes_ago)
        self.store.conn.execute(
            "INSERT INTO pool_draw_snapshot"
            "(product,draw_number,fetched_at,net_sale,jackpot,jackpot_source) "
            "VALUES (?,?,?,?,?,?)",
            (product, number, pool_health._iso(at), 1000, 0, "test"))

    def test_fresh_snapshot_for_future_draw_is_healthy(self):
        self._draw()
        self._snapshot()
        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        self.assertEqual("ok", rep["status"])
        self.assertEqual([], rep["issues"])

    def test_defined_future_draw_does_not_require_snapshots_or_freezes(self):
        close = NOW + dt.timedelta(hours=8)
        self.store.conn.execute(
            "INSERT INTO draws(product,draw_number,state,reg_close_time) "
            "VALUES (?,?,?,?)",
            ("stryktipset", 5001, "Defined", close.isoformat()))

        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))

        self.assertEqual("ok", rep["status"])
        self.assertEqual([], rep["issues"])

    def test_stale_snapshot_is_visible_end_to_end(self):
        self._draw()
        self._snapshot(minutes_ago=60)
        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        self.assertIn("stale_snapshots", {i["kind"] for i in rep["issues"]})

    def test_due_horizon_requires_the_whole_benchmark_family(self):
        self._draw(hours=1)       # h3 har varit öppet länge; m20 ännu inte
        self._snapshot()
        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        freezes = [i for i in rep["issues"] if i["kind"] == "freeze_incomplete"]
        self.assertEqual(1, len(freezes))
        self.assertIn("h3 har 0/12", freezes[0]["message"])
        kinds = {i["kind"] for i in rep["issues"]}
        self.assertIn("ph5_freeze_incomplete", kinds)
        self.assertIn("mathmax_freeze_incomplete", kinds)
        self.assertIn("reducedmax_freeze_incomplete", kinds)

    def test_researchrader_kan_inte_maskera_saknade_benchmarksystem(self):
        self._draw(hours=1)
        self._snapshot()
        for config in pool_system_ledger.research_configs_for(
                "stryktipset", 5000):
            self.store.conn.execute(
                "INSERT INTO pool_system_ledger (product,draw_number,horizon,"
                "config_key,frozen_at,lag_min,timely,code_version,budget,"
                "strategy,value_weight,n_rows,cost_kr,events_order,rows_text,"
                "rows_hash) VALUES ('stryktipset',5000,'h3',?,?,0,1,'test',"
                "?,?,?,?,1,'1','h','hash')",
                (config["key"], pool_health._iso(NOW), config["budget"],
                 config["strategy"], config["value_weight"], 1))
        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        messages = [i["message"] for i in rep["issues"]
                    if i["kind"] == "freeze_incomplete"]
        self.assertEqual(["h3 har 0/12 frysta system"], messages)
        self.assertFalse(any(i["kind"].endswith("_freeze_incomplete")
                             and i["kind"] != "freeze_incomplete"
                             for i in rep["issues"]))

    def test_researchfamiljer_larmar_separat(self):
        self._draw(hours=1)
        self._snapshot()
        for config in pool_system_ledger.PH5_FORWARD_CONFIGS:
            self.store.conn.execute(
                "INSERT INTO pool_system_ledger (product,draw_number,horizon,"
                "config_key,frozen_at,lag_min,timely,code_version,budget,"
                "strategy,value_weight,n_rows,cost_kr,events_order,rows_text,"
                "rows_hash) VALUES ('stryktipset',5000,'h3',?,?,0,1,'test',"
                "?,?,?,?,1,'1','h','hash')",
                (config["key"], pool_health._iso(NOW), config["budget"],
                 config["strategy"], config["value_weight"], 1))

        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        kinds = {i["kind"] for i in rep["issues"]}

        self.assertNotIn("ph5_freeze_incomplete", kinds)
        self.assertIn("mathmax_freeze_incomplete", kinds)
        self.assertIn("reducedmax_freeze_incomplete", kinds)

    def test_h3_alarm_waits_for_one_allowed_base_interval(self):
        close = self._draw(hours=3)
        self._snapshot()
        before = pool_health.report(
            self.store, now=close - dt.timedelta(minutes=180) + dt.timedelta(minutes=20),
            products=("stryktipset",))
        after = pool_health.report(
            self.store, now=close - dt.timedelta(minutes=180) + dt.timedelta(minutes=31),
            products=("stryktipset",))
        self.assertNotIn("freeze_incomplete", {i["kind"] for i in before["issues"]})
        self.assertIn("freeze_incomplete", {i["kind"] for i in after["issues"]})

    def test_missed_freeze_after_close_is_history_not_current_outage(self):
        self._draw("topptipset", 4274, hours=-1)
        self.store.meta_set("latest_topptipset", "4274")

        rep = pool_health.report(
            self.store, now=NOW, products=("topptipset",))

        freezes = [i for i in rep["issues"]
                   if i["kind"] == "freeze_incomplete"]
        self.assertEqual("ok", rep["status"])
        self.assertTrue(freezes)
        self.assertTrue(all(i["level"] == "warning" for i in freezes))
        # Antalet är familjens egen längd (9 benchmark + sannolikhetsbas-
        # utmanaren sedan 2026-09-02) — en ny utmanare ska höja talet här,
        # aldrig tysta larmet.
        n = len(benchmarks_for("topptipset"))
        self.assertEqual(10, n)
        self.assertEqual(
            [f"3 timmar före spelstopp: 0 av {n} testsystem sparades",
             f"20 minuter före spelstopp: 0 av {n} testsystem sparades"],
            [i["message"] for i in freezes])

    def test_scanhint_must_not_lag_observed_draw(self):
        self._draw("topptipset", 4300, 8)
        self._snapshot("topptipset", 4300)
        self.store.meta_set("latest_topptipset", "4299")
        rep = pool_health.report(
            self.store, now=NOW, products=("topptipset",))
        self.assertIn("seed_behind", {i["kind"] for i in rep["issues"]})

    def test_scanankare_under_ratt_raseed_ar_inte_ett_fel(self):
        self._draw("topptipset", 4267, 8)
        self._snapshot("topptipset", 4267)
        self.store.conn.execute(
            "INSERT INTO draws(product,draw_number,state,reg_close_time) "
            "VALUES ('topptipset',4275,'Finalized',NULL)")
        self.store.meta_set("latest_topptipset", "4275")
        self.assertEqual(4275, self.store.stored_seed("topptipset"))

        # Simulera det avsiktligt lägre scanankaret. Hälsan ska läsa det råa
        # högstavärdet 4275, inte ankaret 4267.
        with patch.object(self.store, "seed_hint", return_value=4267):
            rep = pool_health.report(
                self.store, now=NOW, products=("topptipset",))
        self.assertNotIn("seed_behind", {i["kind"] for i in rep["issues"]})

    def test_expired_settlement_retry_is_an_error(self):
        self.store.conn.execute(
            "INSERT INTO pool_played_coupon "
            "(product,draw_number,played_at,row_price,n_rows,cost_kr,"
            "events_order,rows_text,rows_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            ("stryktipset", 4999, pool_health._iso(NOW - dt.timedelta(hours=5)),
             1, 1, 1, "1", "1", "hash"))
        retry = pool_health._iso(NOW - dt.timedelta(minutes=30))
        self.store.conn.execute(
            "INSERT INTO pool_backfill_log "
            "(product,draw_number,attempted_at,status,retry_after) "
            "VALUES (?,?,?,?,?)",
            ("stryktipset", 4999,
             pool_health._iso(NOW - dt.timedelta(hours=1)),
             "not_finalized", retry))
        rep = pool_health.report(
            self.store, now=NOW, products=("stryktipset",))
        self.assertIn("settlement_overdue", {i["kind"] for i in rep["issues"]})



class PoolHealthFreshnessTests(unittest.TestCase):
    """2026-09-24: färsk Pinnacle-täckning nära spelstopp och stoppad
    styrkeshadow är VARNINGAR som gäller nu — inte historiska bortfall."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _open_draw(self, number=5000, hours=20, events=4, product="stryktipset"):
        close = NOW + dt.timedelta(hours=hours)
        self.store.conn.execute(
            "INSERT INTO draws(product,draw_number,state,reg_close_time) "
            "VALUES (?,?,?,?)", (product, number, "Open", close.isoformat()))
        self.store.conn.execute(
            "INSERT INTO pool_draw_snapshot"
            "(product,draw_number,fetched_at,net_sale,jackpot,jackpot_source) "
            "VALUES (?,?,?,?,?,?)",
            (product, number, pool_health._iso(NOW - dt.timedelta(minutes=2)),
             1000, 0, "test"))
        for event in range(1, events + 1):
            for sign in ("1", "X", "2"):
                self.store.conn.execute(
                    "INSERT INTO snapshots(product,draw_number,event_number,sign,"
                    "odds,start_odds,streck,fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                    (product, number, event, sign, 2.5, 2.5, 33,
                     pool_health._iso(NOW - dt.timedelta(hours=5))))
        self.store.conn.commit()

    def _price(self, event, minutes_ago, number=5000):
        self.store.save_sharp("stryktipset", number, [{
            "event_number": event, "bookmaker": "pinnacle",
            "odds": {"1": 2.0, "X": 3.4, "2": 3.8}, "total": None,
            "confidence": 1.0, "matched": "H - B",
            "fetched_at": pool_health._iso(NOW - dt.timedelta(minutes=minutes_ago))}])

    def _capture(self, event, minutes_ago, status, number=5000):
        self.store.conn.execute(
            "INSERT INTO pool_market_capture (product,draw_number,source,"
            "event_number,fetched_at,status,odds_complete) VALUES (?,?,?,?,?,?,?)",
            ("stryktipset", number, "sharp", event,
             pool_health._iso(NOW - dt.timedelta(minutes=minutes_ago)), status,
             int(status == "matched")))
        self.store.conn.commit()

    def _coverage(self, rep):
        return [i for i in rep["issues"] if i["kind"] == "sharp_link_coverage"]

    def test_lag_farsk_pinnacletackning_nara_spelstopp_ar_en_varning(self):
        self._open_draw()
        self._price(1, 10)
        self._capture(1, 10, "matched")
        self._price(2, 40)
        self._capture(2, 10, "ambiguous")      # länken tappad efter priset
        self._price(3, 300)                    # för gammalt
        self._capture(4, 10, "not_listed")     # aldrig länkad
        rep = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        issues = self._coverage(rep)
        self.assertEqual(1, len(issues))
        self.assertEqual("ok", rep["status"])  # en varning fäller inte hälsan
        self.assertEqual("warning", issues[0]["level"])
        self.assertEqual(5000, issues[0]["draw_number"])
        self.assertNotIn("scope", issues[0])
        self.assertEqual(
            "färsk Pinnacle för 1 av 4 matcher (25 %, gräns 70 %) · "
            "tvetydig 1 · ej listad/namn 1 · för gammal 1", issues[0]["message"])
        self.assertEqual({"ambiguous": 1, "not_listed": 1, "too_old": 1},
                         issues[0]["reasons"])

    def test_tackningen_provas_bara_inom_48_timmar_och_under_70_procent(self):
        self._open_draw(number=5000, hours=60)           # utanför 48 h
        self._open_draw(number=5001, hours=20)           # 3/4 = 75 % färska
        for event in (1, 2, 3):
            self._price(event, 10, number=5001)
        rep = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        self.assertEqual([], self._coverage(rep))
        self._price(1, 100, number=5001)                 # 2/4 = 50 %
        rep = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        self.assertEqual([5001], [i["draw_number"] for i in self._coverage(rep)])

    def test_stoppad_styrkeshadow_varnar_bara_nar_spaaret_har_samlat(self):
        manifest = {"source_versions": {"model_signal_version": "m-old"}}
        with patch("app.pool_strength_shadow.load_manifest", return_value=manifest), \
                patch("app.pool_strength_shadow.shadow_version", return_value="ps-test"), \
                patch("app.pool_strength_shadow.model_signal_version",
                      return_value="m-new"):
            empty = pool_health.report(self.store, now=NOW, products=("stryktipset",))
            self.store.conn.execute(
                "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
                "horizon,event_number,shadow_version,model_signal_version,"
                "captured_at,target_at,delay_min,eligible) "
                "VALUES ('stryktipset',1,'h3',1,'ps-test','m-old',"
                "'2026-08-21T20:12:09Z','2026-08-21T20:12:09Z',0,0)")
            self.store.conn.commit()
            stopped = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        with patch("app.pool_strength_shadow.load_manifest", return_value=manifest), \
                patch("app.pool_strength_shadow.shadow_version", return_value="ps-test"), \
                patch("app.pool_strength_shadow.model_signal_version",
                      return_value="m-old"):
            running = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        kinds = lambda rep: [i["kind"] for i in rep["issues"]]
        self.assertEqual([], kinds(empty))
        self.assertEqual([], kinds(running))
        issue = next(i for i in stopped["issues"]
                     if i["kind"] == "strength_shadow_stopped")
        self.assertEqual(("warning", "poolstyrka"), (issue["level"], issue["product"]))
        self.assertIn("modellversionen byttes (m-old → m-new), senaste capture "
                      "21/8 22:12", issue["message"])
        self.assertEqual("2026-08-21T20:12:09Z", issue["last_capture_at"])
        self.assertEqual("ok", stopped["status"])

    def test_historiska_bortfall_skiljs_fran_aktuella_varningar(self):
        self.store.conn.execute(
            "INSERT INTO draws(product,draw_number,state,reg_close_time) "
            "VALUES ('stryktipset',4999,'Open',?)",
            ((NOW - dt.timedelta(hours=1)).isoformat(),))
        self._open_draw()
        rep = pool_health.report(self.store, now=NOW, products=("stryktipset",))
        history = [i for i in rep["issues"] if i.get("scope") == "history"]
        self.assertTrue(history)
        self.assertTrue(all(i["kind"].endswith("freeze_incomplete") and
                            i["draw_number"] == 4999 for i in history))
        text = pool_health.format_report(rep)
        self.assertLess(text.index("VARNINGAR:"), text.index("HISTORISKA BORTFALL:"))
        current = text[text.index("VARNINGAR:"):text.index("HISTORISKA BORTFALL:")]
        self.assertIn("omg 5000: färsk Pinnacle för 0 av 4 matcher", current)
        self.assertNotIn("4999", current)


if __name__ == "__main__":
    unittest.main()


class BackupAlarmTests(unittest.TestCase):
    """Nattlig backup: larm när kopian saknas, är gammal eller inte publicerats."""

    NOW = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc)

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "status.json"

    def tearDown(self):
        self.tmp.cleanup()

    def kinds(self, status=None):
        import json
        issues = []
        if status is not None:
            self.path.write_text(json.dumps(status))
        pool_health._backup_issues(issues, self.path, self.NOW)
        return [issue["kind"] for issue in issues]

    def test_farsk_publicerad_backup_ar_tyst(self):
        self.assertEqual([], self.kinds({"last_ok_at": "2026-09-26T02:15:10Z",
                                         "last_pushed_at": "2026-09-26T02:15:10Z"}))

    def test_saknad_gammal_och_opublicerad_backup_larmar(self):
        self.assertEqual(["backup_missing"], self.kinds())
        self.assertEqual(["backup_stale"], self.kinds({"last_ok_at": "2026-09-24T13:55:10Z",
                                                       "last_pushed_at": "2026-09-24T13:55:10Z",
                                                       "error": "RuntimeError: x"}))
        self.assertEqual(["backup_not_pushed"], self.kinds(
            {"last_ok_at": "2026-09-26T02:15:10Z", "last_pushed_at": "2026-09-24T13:55:10Z"}))

    def test_rapporten_laser_bara_backup_nar_sokvagen_skickas(self):
        from app.storage import Storage
        store = Storage(Path(self.tmp.name) / "t.db")
        try:
            quiet = pool_health.report(store, now=self.NOW, products=())
            loud = pool_health.report(store, now=self.NOW, products=(),
                                      backup_status_path=self.path)
        finally:
            store.close()
        self.assertNotIn("backup_missing", [i["kind"] for i in quiet["issues"]])
        self.assertIn("backup_missing", [i["kind"] for i in loud["issues"]])

    def test_samma_rot_som_backupskriptet(self):
        from scripts import backup_db
        self.assertEqual(backup_db.DEFAULT_ROOT / "status.json",
                         pool_health.BACKUP_STATUS_PATH)
