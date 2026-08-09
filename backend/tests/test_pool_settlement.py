import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import pool_settlement as ps
from app.storage import Storage


def _draw(n=100, state="Finalized", events=13, cancelled=(), start_odds=True,
          match_start="2026-07-18T16:00:00", status_id=None):
    return {
        "drawNumber": n, "drawState": state, "productName": "Stryktipset",
        "regCloseTime": "2026-07-18T15:59:00+02:00",
        "currentNetSale": "1234567,00", "rowPrice": "1,00",
        "drawEvents": [{
            "eventNumber": i,
            "eventDescription": f"Hemma{i} - Borta{i}",
            "cancelled": i in cancelled,
            "match": {"matchStart": match_start,
                      **({"statusId": status_id} if status_id else {}),
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


class RetryPolicyTests(unittest.TestCase):
    """Omprövningstiden (2026-08-08).

    Bakgrund: den fasta 6-timmarsbackoffen VAR hela fördröjningen. Av 30
    observerade not_finalized→ok-övergångar tog 100 % mer än 5,5 h, median
    6,21 h. Ett försök gjordes ofta innan matcherna var färdigspelade och
    blockerade därmed just det försök som hade lyckats.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime(2026, 8, 8, 18, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_matcher_som_rullar_provas_nar_de_ar_slut(self):
        """Ingen utdelning kan finnas medan matcherna pågår — fråga inte."""
        raw = _draw(state="Closed", match_start="2026-08-08T19:00:00+00:00")
        self.assertEqual(
            "2026-08-08T21:10:00Z",       # avspark 19:00 + 130 min speltid
            ps._retry_after(raw, now=self.now))

    def test_matchstart_med_svensk_offset_normaliseras_till_utc(self):
        """Europatipset 2597: 19:15+02 + 130 min är 19:25Z, inte 21:25Z.

        Ett Z-suffix får aldrig sättas på lokal väggtid utan konvertering.
        Felet höll en redan publicerad utdelning gömd i två extra timmar.
        """
        raw = _draw(state="Closed", match_start="2026-08-09T19:15:00+02:00")
        now = dt.datetime(2026, 8, 9, 18, 22, tzinfo=dt.timezone.utc)
        self.assertEqual("2026-08-09T19:25:00Z",
                         ps._retry_after(raw, now=now))

    def test_fardigspelad_omgang_provas_inom_kvarten(self):
        """DEN HÄR var buggen: Stryktipset 4965 låg Finalized hos SvS med full
        utdelning medan vi satt i en backoff till 22:30."""
        raw = _draw(state="Closed", status_id=31,
                    match_start="2026-08-08T15:00:00+00:00")
        self.assertEqual("2026-08-08T18:15:00Z",
                         ps._retry_after(raw, now=self.now))

    def test_straffavgjord_match_raknas_som_spelad(self):
        """Samma definition som livekortet — statusId 33 = slut efter straffar."""
        raw = _draw(state="Closed", status_id=33,
                    match_start="2026-08-08T15:00:00+00:00")
        self.assertEqual("2026-08-08T18:15:00Z",
                         ps._retry_after(raw, now=self.now))

    def test_taket_haller_en_avlagsen_omgang_i_schack(self):
        raw = _draw(state="Open", match_start="2026-08-20T19:00:00+00:00")
        self.assertEqual("2026-08-09T00:00:00Z",   # now + RETRY_MAX_H
                         ps._retry_after(raw, now=self.now))

    def test_okand_avspark_ger_kort_omprovning_inte_lang(self):
        """Saknad avspark är okunskap, inte ett skäl att sluta fråga."""
        raw = _draw(state="Closed", match_start=None)
        self.assertEqual("2026-08-08T18:15:00Z",
                         ps._retry_after(raw, now=self.now))

    def _log_row(self, draw_number, status, attempted_at, retry_after):
        self.store.conn.execute(
            "INSERT INTO pool_backfill_log (product, draw_number, attempted_at,"
            " status, detail, retry_after) VALUES ('stryktipset',?,?,?,NULL,?)",
            (draw_number, attempted_at, status, retry_after))
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES ('stryktipset', ?, 'Closed', '2026-01-01T12:00:00')",
            (draw_number,))
        self.store.conn.commit()

    def test_passerad_retry_after_slar_den_fasta_backoffen(self):
        """Loggraden är fem minuter gammal — men matcherna är slut, så vi
        frågar igen. Med gammal kod hade den legat kvar i sex timmar."""
        recent = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self._log_row(400, ps.NOT_FINALIZED, recent, past)
        svs = FakeSvS({400: _draw(400)}, {400: _result(400)})
        report = ps.settle_recent(self.store, svs, "stryktipset")
        self.assertEqual({"tried": 1, "ok": 1, "skipped": 0}, report)

    def test_kommande_retry_after_haller_tillbaka(self):
        future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self._log_row(401, ps.NOT_FINALIZED, future[:20], future)
        svs = FakeSvS({401: _draw(401)}, {401: _result(401)})
        report = ps.settle_recent(self.store, svs, "stryktipset")
        self.assertEqual({"tried": 0, "ok": 0, "skipped": 1}, report)
        self.assertEqual(0, svs.calls)

    def test_historisk_rad_utan_retry_after_faller_tillbaka_pa_backoffen(self):
        recent = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self._log_row(402, ps.NOT_FINALIZED, recent, None)
        svs = FakeSvS({402: _draw(402)}, {402: _result(402)})
        self.assertEqual({"tried": 0, "ok": 0, "skipped": 1},
                         ps.settle_recent(self.store, svs, "stryktipset"))

    def test_transportfel_parkerar_inte_omgangen(self):
        """Ett nätfel säger ingenting om omgången — samma princip som att ett
        källfel aldrig får markera ett pris unavailable."""
        svs = FakeSvS({403: RuntimeError("timeout")}, {})
        self.assertEqual(ps.ERROR, ps.settle_draw(
            self.store, svs, "stryktipset", 403, "test"))
        retry_after = self.store.conn.execute(
            "SELECT retry_after FROM pool_backfill_log WHERE draw_number=403"
        ).fetchone()[0]
        limit = (dt.datetime.now(dt.timezone.utc)
                 + dt.timedelta(minutes=ps.RETRY_SOON_MIN + 1)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertLess(retry_after, limit)

    def test_publicerad_men_ofullstandig_utdelning_provas_snart(self):
        svs = FakeSvS({404: _draw(404)}, {404: _result(404, complete=False)})
        self.assertEqual(ps.INCOMPLETE, ps.settle_draw(
            self.store, svs, "stryktipset", 404, "test"))
        retry_after = self.store.conn.execute(
            "SELECT retry_after FROM pool_backfill_log WHERE draw_number=404"
        ).fetchone()[0]
        limit = (dt.datetime.now(dt.timezone.utc)
                 + dt.timedelta(minutes=ps.RETRY_SOON_MIN + 1)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertLess(retry_after, limit)


if __name__ == "__main__":
    unittest.main()
