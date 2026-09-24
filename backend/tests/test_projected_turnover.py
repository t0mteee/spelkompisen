"""P4 (2026-07-28) + tp2 (2026-09-24): slutomsättningsprognos ur det lokala
settlementlagret — ingen nätverkstrafik. tp2: sann median, dagtypsläget som
tredje kandidat i samma backtest, veckodag i svensk tid, versionerad cache."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import main
from app.storage import Storage


def _seed(store, product, rows):
    for i, (close_iso, sale) in enumerate(rows):
        store.conn.execute(
            "INSERT INTO pool_draw_settlement (product, draw_number,"
            " draw_state, reg_close_time, net_sale, row_price,"
            " source_version, payload_hash, fetched_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (product, 1000 + i, "Finalized", close_iso, sale, 1.0,
             "test", f"h{i}", close_iso))
    store._commit()


class ProjectedTurnoverTests(unittest.TestCase):
    def _store_factory(self, tmp):
        path = Path(tmp) / "t.db"
        return lambda: Storage(path)

    def test_medianen_tas_fran_samma_veckodag(self):
        """Europatipsets onsdagsomgångar (~1 M) får inte späs ut av
        söndagens (~7 M) — och tvärtom."""
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._store_factory(tmp)
            seedstore = factory()
            rows = []
            # 4 söndagar à 7 M och 4 onsdagar à 1 M, växelvis bakåt i tiden
            base = dt.datetime(2026, 7, 26, 17, 0,
                               tzinfo=dt.timezone.utc)   # en söndag
            for week in range(4):
                rows.append(((base - dt.timedelta(days=7 * week))
                             .strftime("%Y-%m-%dT%H:%M:%SZ"), 7_000_000))
                rows.append(((base - dt.timedelta(days=7 * week + 4))
                             .strftime("%Y-%m-%dT%H:%M:%SZ"), 1_000_000))
            _seed(seedstore, "europatipset", rows)
            seedstore.close()
            with mock.patch.object(main, "Storage", factory):
                sunday = main._projected_turnover(
                    "europatipset", 100.0,
                    close_iso="2026-08-02T17:00:00Z")   # söndag
                wednesday = main._projected_turnover(
                    "europatipset", 100.0,
                    close_iso="2026-08-05T17:00:00Z")   # onsdag
        self.assertEqual(7_000_000, sunday)
        self.assertEqual(1_000_000, wednesday)

    def test_fa_veckodagsomgangar_ger_redovisad_blandad_median(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._store_factory(tmp)
            seedstore = factory()
            base = dt.datetime(2026, 7, 25, 15, 0, tzinfo=dt.timezone.utc)
            _seed(seedstore, "stryktipset",
                  [((base - dt.timedelta(days=7 * w))
                    .strftime("%Y-%m-%dT%H:%M:%SZ"), 12_000_000)
                   for w in range(4)])
            seedstore.close()
            with mock.patch.object(main, "Storage", factory):
                # målomgången stänger en MÅNDAG — inga jämförbara finns
                got = main._projected_turnover(
                    "stryktipset", 100.0, close_iso="2026-08-03T18:00:00Z")
                basis = main._projection_basis(
                    "stryktipset", "2026-08-03T18:00:00Z")
        self.assertEqual(12_000_000, got)
        self.assertEqual("blandad", basis["mode"])

    def test_prognosen_ligger_aldrig_under_liveomsattningen(self):
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._store_factory(tmp)
            seedstore = factory()
            _seed(seedstore, "stryktipset",
                  [("2026-07-25T15:00:00Z", 5_000_000)] )
            seedstore.close()
            with mock.patch.object(main, "Storage", factory):
                got = main._projected_turnover("stryktipset", 9_000_000.0)
        self.assertEqual(9_000_000.0, got)


class TurnoverProjectionTp2Tests(unittest.TestCase):
    """tp2 (2026-09-24): statusauditens två fel — övre median och att
    vardagsomgångar antingen krävde exakt samma veckodag eller blandades med
    söndagar (Europatipset 2610: 9,0 Mkr mot vardagarnas 6,2–7,1)."""

    def _factory(self, tmp):
        path = Path(tmp) / "t.db"
        return lambda: Storage(path)

    def test_sann_median_ar_medel_av_mittvardena(self):
        self.assertEqual(2.5, main._true_median([4, 1, 3, 2]))
        self.assertEqual(3, main._true_median([5, 1, 3]))
        self.assertIsNone(main._true_median([]))
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._factory(tmp)
            seedstore = factory()
            base = dt.datetime(2026, 7, 26, 17, 0, tzinfo=dt.timezone.utc)
            _seed(seedstore, "europatipset",
                  [((base - dt.timedelta(days=7 * w))
                    .strftime("%Y-%m-%dT%H:%M:%SZ"), sale)
                   for w, sale in enumerate(
                       (1_000_000, 2_000_000, 3_000_000, 4_000_000))])
            seedstore.close()
            with mock.patch.object(main, "Storage", factory):
                got = main._projected_turnover(
                    "europatipset", 100.0, close_iso="2026-08-02T17:00:00Z")
        # tp1 tog det övre mittvärdet (3 M)
        self.assertEqual(2_500_000, got)

    def test_dagtyp_valjs_nar_vardagsomgangar_byter_veckodag(self):
        """Vardagsomgångarna växlar onsdag/torsdag och växer med säsongen;
        söndagarna ligger högre. Samma veckodag är 16 veckor gammal, blandad
        drar in söndagar — samma dagtyp vinner backtesten."""
        rows = []
        start = dt.datetime(2026, 3, 1, 13, 0, tzinfo=dt.timezone.utc)  # söndag
        for week in range(30):
            sunday = start + dt.timedelta(days=7 * week)
            midweek = sunday + dt.timedelta(days=3 if week % 2 else 4)
            rows.append((sunday.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         10_000_000 + 200_000 * week))
            rows.append((midweek.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         4_000_000 + 200_000 * week))
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._factory(tmp)
            seedstore = factory()
            _seed(seedstore, "europatipset", rows)
            seedstore.close()
            target = "2026-09-24T18:44:00Z"            # torsdag
            with mock.patch.object(main, "Storage", factory):
                got = main._projected_turnover("europatipset", 100.0,
                                               close_iso=target)
                basis = main._projection_basis("europatipset", target)
        self.assertEqual("dagtyp", basis["mode"])
        self.assertEqual("vardag", basis["daytype"])
        self.assertEqual(main.TURNOVER_PROJECTION_VERSION, basis["version"])
        fel = basis["backtest_fel"]
        self.assertLess(fel["dagtyp"], fel["veckodag"])
        self.assertLess(fel["dagtyp"], fel["blandad"])
        # de 8 senaste vardagsomgångarna (vecka 22–29): 8,4–9,8 M
        midweek = sorted(4_000_000 + 200_000 * w for w in range(22, 30))
        self.assertAlmostEqual(main._true_median(midweek), got)

    def test_gammal_cache_lever_inte_kvar_efter_metodbytet(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            factory = self._factory(tmp)
            seedstore = factory()
            base = dt.datetime(2026, 7, 26, 17, 0, tzinfo=dt.timezone.utc)
            _seed(seedstore, "europatipset",
                  [((base - dt.timedelta(days=7 * w))
                    .strftime("%Y-%m-%dT%H:%M:%SZ"), 5_000_000)
                   for w in range(4)])
            now = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc)
            # tp1:s nyckel med ett färskt, felaktigt värde
            seedstore.meta_set("finalturn_europatipset:wd6", json.dumps(
                {"ts": now.isoformat(), "median": 9_000_000.0,
                 "weekday": 6, "n": 6, "mode": "blandad"}))
            seedstore.close()
            with mock.patch.object(main, "Storage", factory):
                got = main._projected_turnover(
                    "europatipset", 100.0, close_iso="2026-08-02T17:00:00Z",
                    now=now)
            self.assertEqual(5_000_000, got)
            key = main._finalturn_key("europatipset", 6)
            self.assertIn(main.TURNOVER_PROJECTION_VERSION, key)
            self.assertNotEqual("finalturn_europatipset:wd6", key)
            # nya nyckelns cache används inom 6 h och räknas om efter
            store = factory()
            store.meta_set(key, json.dumps(
                {"ts": now.isoformat(), "median": 7_000_000.0,
                 "version": main.TURNOVER_PROJECTION_VERSION}))
            store.close()
            with mock.patch.object(main, "Storage", factory):
                fresh = main._projected_turnover(
                    "europatipset", 100.0, close_iso="2026-08-02T17:00:00Z",
                    now=now + dt.timedelta(hours=5))
                stale = main._projected_turnover(
                    "europatipset", 100.0, close_iso="2026-08-02T17:00:00Z",
                    now=now + dt.timedelta(hours=7))
        self.assertEqual(7_000_000, fresh)
        self.assertEqual(5_000_000, stale)

    def test_veckodagen_ar_svensk_tid_aven_for_utc(self):
        # Topptipset med stopp 00:29 lördag svensk tid: ledgern skickar UTC
        self.assertEqual(5, main._close_weekday("2026-09-26T00:29:00+02:00"))
        self.assertEqual(5, main._close_weekday("2026-09-25T22:29:00+00:00"))
        self.assertEqual(5, main._close_weekday("2026-09-25T22:29:00Z"))
        self.assertEqual("helg", main._day_type(5))
        self.assertEqual("vardag", main._day_type(4))
        self.assertIsNone(main._close_weekday(None))

    def test_rader_sorteras_som_tider_inte_strangar(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                # 02:10+01:00 (01:10Z) är SENARE än 02:30+02:00 (00:30Z)
                _seed(store, "stryktipset",
                      [("2026-10-25T02:30:00+02:00", 1.0),
                       ("2026-10-25T02:10:00+01:00", 2.0)])
                rows = main._settled_turnover_rows(store, "stryktipset")
            finally:
                store.close()
        self.assertEqual([2.0, 1.0], [sale for _, sale in rows])

    def test_skickad_store_anvands_och_stangs_inte(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                _seed(store, "stryktipset",
                      [("2026-07-25T15:00:00Z", 5_000_000)])

                def _no_own_storage(*_a, **_k):
                    raise AssertionError("egen Storage() öppnades")
                with mock.patch.object(main, "Storage", _no_own_storage):
                    got = main._projected_turnover(
                        "stryktipset", 100.0, close_iso="2026-08-01T13:59:00Z",
                        store=store)
                    basis = main._projection_basis(
                        "stryktipset", "2026-08-01T13:59:00Z", store=store)
                # fortfarande öppen
                store.conn.execute("SELECT 1").fetchone()
            finally:
                store.close()
        self.assertEqual(5_000_000, got)
        self.assertEqual("blandad", basis["mode"])     # en omgång < 3


if __name__ == "__main__":
    unittest.main()
