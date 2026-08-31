import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pool_health, pool_system_ledger
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
        self.assertEqual(
            ["3 timmar före spelstopp: 0 av 9 testsystem sparades",
             "20 minuter före spelstopp: 0 av 9 testsystem sparades"],
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


if __name__ == "__main__":
    unittest.main()
