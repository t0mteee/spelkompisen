"""P4 (2026-07-28): veckodagsviktad slutomsättningsprognos ur det lokala
settlementlagret — ingen nätverkstrafik, ingen dagtypsblandning."""
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

    def test_fa_veckodagsomgangar_ger_redovisad_fallback(self):
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
        self.assertEqual("fallback", basis["mode"])

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


if __name__ == "__main__":
    unittest.main()
