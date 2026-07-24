import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import pool_settlement as ps
from app.storage import Storage


def _draw(n=100, state="Finalized", events=13, cancelled=(), start_odds=True):
    return {
        "drawNumber": n, "drawState": state, "productName": "Stryktipset",
        "regCloseTime": "2026-07-18T15:59:00+02:00",
        "currentNetSale": "1234567,00", "rowPrice": "1,00",
        "drawEvents": [{
            "eventNumber": i,
            "eventDescription": f"Hemma{i} - Borta{i}",
            "cancelled": i in cancelled,
            "match": {"matchStart": "2026-07-18T16:00:00",
                      "participants": [
                          {"type": "home", "name": f"Hemma{i}"},
                          {"type": "away", "name": f"Borta{i}"}]},
            "svenskaFolket": {"one": "45", "x": "30", "two": "25"},
            **({"startOdds": {"one": "2,10", "x": "3,30", "two": "3,40"}}
               if start_odds else {}),
        } for i in range(1, events + 1)],
    }


def _result(n=100, events=13, cancelled=(), complete=True):
    return {
        "currentNetSale": "1234567,00",
        "distribution": [
            {"name": "13 rätt", "winners": 2 if complete else None,
             "amount": "125000,50"},
            {"name": "12 rätt", "winners": 60, "amount": "1200,00"},
        ],
        "events": [{
            "eventNumber": i,
            "outcome": None if i in cancelled else ("1" if i % 3 else "X"),
            "cancelled": i in cancelled,
        } for i in range(1, events + 1)],
    }


class FakeSvS:
    """Fejkad API-klient: (draw, result) per omgångsnummer, räknar anrop."""

    def __init__(self, draws=None, results=None):
        self.draws = draws or {}
        self.results = results or {}
        self.calls = 0

    def raw_draw(self, product, n):
        self.calls += 1
        v = self.draws.get(n)
        if isinstance(v, Exception):
            raise v
        return v

    def raw_result(self, product, n):
        self.calls += 1
        v = self.results.get(n)
        if isinstance(v, Exception):
            raise v
        return v


class PoolSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _counts(self):
        c = self.store.conn
        return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("pool_draw_settlement", "pool_event_settlement",
                               "pool_payout_tier"))

    def test_idempotens_andra_korningen_skriver_inget(self):
        svs = FakeSvS({100: _draw()}, {100: _result()})
        self.assertEqual(ps.OK, ps.settle_draw(
            self.store, svs, "stryktipset", 100, source_version="test"))
        calls_after_first = svs.calls
        self.assertEqual((1, 13, 2), self._counts())
        self.assertEqual(ps.EXISTS, ps.settle_draw(
            self.store, svs, "stryktipset", 100, source_version="test"))
        self.assertEqual(calls_after_first, svs.calls)   # inga nya API-anrop
        self.assertEqual((1, 13, 2), self._counts())

    def test_ingen_tyst_overwrite_vid_divergens(self):
        svs = FakeSvS({100: _draw()}, {100: _result()})
        ps.settle_draw(self.store, svs, "stryktipset", 100, "test")
        canon = self.store.conn.execute(
            "SELECT payload_hash, net_sale FROM pool_draw_settlement").fetchone()
        changed = _result()
        changed["distribution"][0]["amount"] = "999999,00"
        svs2 = FakeSvS({100: _draw()}, {100: changed})
        self.assertEqual(ps.DIVERGENCE, ps.verify_draw(
            self.store, svs2, "stryktipset", 100))
        after = self.store.conn.execute(
            "SELECT payload_hash, net_sale FROM pool_draw_settlement").fetchone()
        self.assertEqual(canon, after)   # kanon orörd
        self.assertEqual(ps.DIVERGENCE, ps.latest_status(
            self.store, "stryktipset", 100))

    def test_struken_match_bokfors(self):
        svs = FakeSvS({100: _draw(cancelled={7})},
                      {100: _result(cancelled={7})})
        self.assertEqual(ps.OK, ps.settle_draw(
            self.store, svs, "stryktipset", 100, "test"))
        row = self.store.conn.execute(
            "SELECT outcome, cancelled FROM pool_event_settlement "
            "WHERE event_number=7").fetchone()
        self.assertEqual((None, 1), tuple(row))
        self.assertEqual(1, self.store.conn.execute(
            "SELECT n_cancelled FROM pool_draw_settlement").fetchone()[0])

    def test_ej_fardigspelad_ar_retrybar(self):
        svs = FakeSvS({100: _draw(state="Open")}, {})
        self.assertEqual(ps.NOT_FINALIZED, ps.settle_draw(
            self.store, svs, "stryktipset", 100, "test"))
        self.assertEqual((0, 0, 0), self._counts())
        self.assertEqual(ps.NOT_FINALIZED, ps.latest_status(
            self.store, "stryktipset", 100))

    def test_ofullstandig_distribution_ger_inga_rader(self):
        svs = FakeSvS({100: _draw()}, {100: _result(complete=False)})
        self.assertEqual(ps.INCOMPLETE, ps.settle_draw(
            self.store, svs, "stryktipset", 100, "test"))
        self.assertEqual((0, 0, 0), self._counts())

    def test_transaktionsatomicitet_vid_skrivfel(self):
        bad = _draw()
        bad["drawEvents"][5]["eventNumber"] = bad["drawEvents"][4]["eventNumber"]
        svs = FakeSvS({100: bad}, {100: _result()})   # PK-kollision mitt i
        self.assertEqual(ps.ERROR, ps.settle_draw(
            self.store, svs, "stryktipset", 100, "test"))
        self.assertEqual((0, 0, 0), self._counts())   # rollback, inga delrader

    def test_variantseparation_utan_kollision(self):
        svs = FakeSvS({100: _draw(events=8)}, {100: _result(events=8)})
        self.assertEqual(ps.OK, ps.settle_draw(
            self.store, svs, "topptipset", 100, "test"))
        self.assertEqual(ps.OK, ps.settle_draw(
            self.store, svs, "topptipsetextra", 100, "test"))
        self.assertEqual(2, self.store.conn.execute(
            "SELECT COUNT(*) FROM pool_draw_settlement "
            "WHERE draw_number=100").fetchone()[0])

    def test_startodds_provenance_ratt_null(self):
        svs = FakeSvS({100: _draw(start_odds=False), 101: _draw(101)},
                      {100: _result(), 101: _result(101)})
        ps.settle_draw(self.store, svs, "stryktipset", 100, "test")
        ps.settle_draw(self.store, svs, "stryktipset", 101, "test")
        utan, med = self.store.conn.execute(
            "SELECT draw_number, start_odds_one FROM pool_event_settlement "
            "WHERE event_number=1 ORDER BY draw_number").fetchall()
        self.assertIsNone(utan[1])
        self.assertAlmostEqual(2.10, med[1])

    def test_http_404_loggas_retrybart(self):
        svs = FakeSvS({}, {})
        self.assertEqual(ps.HTTP_404, ps.settle_draw(
            self.store, svs, "stryktipset", 100, "test"))
        self.assertEqual(ps.HTTP_404, ps.latest_status(
            self.store, "stryktipset", 100))
        self.assertEqual((0, 0, 0), self._counts())

    def test_settle_recent_tar_stangda_osettlade_och_respekterar_retryfonster(self):
        now = dt.datetime.now(dt.timezone.utc)
        old_close = (now - dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
        future_close = (now + dt.timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S")
        for n, close in ((100, old_close), (101, old_close), (102, future_close)):
            self.store.conn.execute(
                "INSERT INTO draws (product, draw_number, state, reg_close_time) "
                "VALUES ('stryktipset', ?, 'Open', ?)", (n, close))
        self.store.conn.commit()
        svs = FakeSvS({100: _draw(100), 101: _draw(101, state="Closed")},
                      {100: _result(100)})
        report = ps.settle_recent(self.store, svs, "stryktipset")
        self.assertEqual({"tried": 2, "ok": 1, "skipped": 0}, report)
        self.assertTrue(ps.is_settled(self.store, "stryktipset", 100))
        # 102 stänger i framtiden — ska inte ens ha försökts
        self.assertIsNone(ps.latest_status(self.store, "stryktipset", 102))
        # nytt varv direkt: 101 (not_finalized nyss) väntar i retryfönstret
        report2 = ps.settle_recent(self.store, svs, "stryktipset")
        self.assertEqual({"tried": 0, "ok": 0, "skipped": 1}, report2)


if __name__ == "__main__":
    unittest.main()
