import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import pool_capture_refresh as refresh, pool_dataset, sharp_service
from app.pinnacle import Pinnacle
from app.storage import Storage

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 14, 16, 37, tzinfo=UTC)
ODDS = {"1": 2.0, "X": 3.0, "2": 4.0}
TOTAL = {"line": 2.5, "O": 1.9, "U": 1.95}


class DetailCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.draw = SimpleNamespace(draw_number=4333, reg_close_time="2026-09-14T16:59:00Z",
            matches=[SimpleNamespace(event_number=1, cancelled=False)])
        self.result = {"fetched_at": "2026-09-14T16:27:50Z",
                       "hits": {1: {"id": "123", "odds": ODDS, "total": TOTAL}}}
        self.quote = {"odds": ODDS, "total": TOTAL, "retrieved_at": "2026-09-14T16:37:01Z",
                      "fetched_at": "2026-09-14T16:35:00Z", "cache_age_s": 121,
                      "cache_age_valid": True}
        self.mock = patch.object(refresh, "Pinnacle")
        self.pin = self.mock.start().return_value.__enter__.return_value
        self.pin.prematch_quote.side_effect = lambda _: dict(self.quote)
        self.varv = sharp_service.VarvIndex()

    def tearDown(self):
        self.mock.stop()
        self.store.close()
        self.tmp.cleanup()

    def run_capture(self, now=NOW, product="topptipset", varv=None, **kwargs):
        return refresh.capture_missing(self.store, product, self.draw, self.result,
            varv or self.varv, now=now, **kwargs)

    def test_70_sekunders_luckan_raddas_med_riktig_pristid(self):
        result = self.run_capture()
        self.assertEqual(1, result["captured"])
        cap = self.store.conn.execute("SELECT fetched_at,status,odds_complete FROM pool_market_capture").fetchone()
        self.assertEqual(("2026-09-14T16:35:00Z", "matched", 1), tuple(cap))
        rows = self.store.conn.execute("SELECT DISTINCT fetched_at FROM sharp_snapshots").fetchall()
        self.assertEqual([("2026-09-14T16:35:00Z",)], [tuple(r) for r in rows])
        pool_dataset.build_total_draw(self.store, "topptipset", 4333, self.draw.reg_close_time,
                                     now=NOW + dt.timedelta(hours=1))
        row = self.store.conn.execute("SELECT total_eligible,line FROM pool_pit_total_features WHERE horizon='m20'").fetchone()
        self.assertEqual((1, 2.5), tuple(row))

    def test_gammal_eller_framtida_eller_ofullstandig_quote_avvisas(self):
        variants = [dict(fetched_at="2026-09-14T16:27:50Z"),
                    dict(fetched_at="2026-09-14T16:40:00Z"),
                    dict(retrieved_at="2026-09-14T16:40:00Z"),
                    dict(total=None), dict(cache_age_valid=False), dict(odds={"1": 2, "X": 3}),
                    dict(total={**TOTAL, "O": float("nan")})]
        original = dict(self.quote)
        for change in variants:
            with self.subTest(change=change):
                self.store.conn.execute("DELETE FROM meta")
                self.store.conn.commit()
                self.quote = {**original, **change}
                result = self.run_capture(varv=sharp_service.VarvIndex())
                self.assertEqual(0, result["captured"])
        self.assertEqual(0, self.store.conn.execute("SELECT count(*) FROM pool_market_capture").fetchone()[0])

    def test_utanfor_fonstret_ingen_trafik(self):
        for delta in (-9, 3):
            self.run_capture(now=NOW + dt.timedelta(minutes=delta))
        self.pin.prematch_quote.assert_not_called()

    def test_giltig_bulk_och_giltig_tidigare_capture_ger_ingen_extrafragning(self):
        self.result["fetched_at"] = "2026-09-14T16:33:00Z"
        self.assertEqual(0, self.run_capture()["attempted"])
        self.result["fetched_at"] = "2026-09-14T16:27:50Z"
        self.assertEqual(1, self.run_capture()["captured"])
        self.assertEqual(0, self.run_capture(varv=sharp_service.VarvIndex())["attempted"])
        self.assertEqual(1, self.pin.prematch_quote.call_count)

    def test_samma_provider_id_delas_mellan_produkter_och_speglas(self):
        self.run_capture()
        self.result["hits"][1]["swapped"] = True
        self.run_capture(product="topptipsetextra")
        self.assertEqual(1, self.pin.prematch_quote.call_count)
        row = self.store.conn.execute("SELECT odds FROM sharp_snapshots WHERE product='topptipsetextra' AND sign='1'").fetchone()
        self.assertEqual(4, row[0])

    def test_kallfel_skaper_inte_falsk_franvaro_och_far_cooldown(self):
        self.pin.prematch_quote.side_effect = TimeoutError()
        self.assertEqual(1, self.run_capture()["errors"])
        self.run_capture(varv=sharp_service.VarvIndex())
        self.assertEqual(1, self.pin.prematch_quote.call_count)
        self.assertEqual(0, self.store.conn.execute("SELECT count(*) FROM pool_market_capture").fetchone()[0])

    def test_tidsbudget_och_matchtak(self):
        self.varv.detail_deadline = 10
        self.run_capture(clock=lambda: 11)
        self.pin.prematch_quote.assert_not_called()
        self.varv.detail_deadline = None
        self.varv.detail_quotes = {str(i): None for i in range(refresh.MAX_REQUESTS)}
        self.run_capture()
        self.pin.prematch_quote.assert_not_called()

    def test_aterlast_bulk_far_inte_backa_snapshots(self):
        # Även oförändrat 1X2: ingen ny 1X2-punkt vid reservhämtningen.
        self.store.save_sharp_snapshot("topptipset", 4333, {1: {"odds": ODDS}},
                                       "2026-09-14T16:20:00Z")
        self.run_capture()
        self.store.save_sharp_snapshot("topptipset", 4333,
            {1: {"odds": {**ODDS, "1": 6}, "total": {**TOTAL, "line": 3.5}}},
            "2026-09-14T16:27:50Z")
        self.assertEqual(3, self.store.conn.execute("SELECT count(*) FROM sharp_snapshots").fetchone()[0])
        self.assertEqual(1, self.store.conn.execute("SELECT count(*) FROM sharp_total_snapshots").fetchone()[0])


class QuoteParserTests(unittest.TestCase):
    def test_bara_exakt_id_helmatch_och_oppna_marknader(self):
        rows = [dict(matchupId=123, period=0, type="moneyline", status="open", prices=[
            dict(designation="home", price=100), dict(designation="draw", price=200),
            dict(designation="away", price=300)]),
            dict(matchupId=123, period=0, type="total", status="open", prices=[
            dict(designation="over", price=-110, points=2.5),
            dict(designation="under", price=-110, points=2.5)])]
        with Pinnacle() as pin, patch.object(Pinnacle, "_get", return_value=rows) as get:
            pin.last_age_s = 121
            result = pin.prematch_quote("123")
            self.assertEqual(ODDS, result["odds"])
            self.assertEqual(2.5, result["total"]["line"])
            get.assert_called_once_with("/matchups/123/markets/straight", attempts=1)
            self.assertEqual(121, (pool_dataset._parse(result["retrieved_at"]) - pool_dataset._parse(result["fetched_at"])).total_seconds())
            self.assertIsNone(pin.prematch_quote("999")["odds"])
            rows[0]["status"] = "suspended"
            self.assertIsNone(pin.prematch_quote("123")["odds"])
