import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.storage import Storage
from scripts import close_drift_facit, close_drift_facit_v2


class CloseDriftVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _save(self, *, version: str, horizon: str, line: float,
              closing_line: float | None = None) -> None:
        self.store.conn.execute(
            "INSERT INTO oddset_prediction_log("
            "match_id,horizon,tier,market,sign,line,line_key,match_start,"
            "target_at,captured_at,offset_minutes,fair_prob,fair_source,"
            "fair_available,fair_fresh,book_available,book_fresh,eligible,"
            "is_flag,signal_version,base_version,closing_fair,closing_line) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("m1", horizon, "sharp", "ou", "O", line,
             int(round(line * 1000)), "2026-08-02T12:00:00Z",
             "2026-08-02T09:00:00Z", "2026-08-02T09:01:00Z", 179.0,
             0.5, "pinnacle", 1, 1, 0, 0, 1, 0, version, "base",
             0.52, closing_line))
        self.store.conn.commit()

    def test_rows_keep_versions_out_of_the_same_keyspace(self):
        self._save(version="sharp-a", horizon="h3", line=2.5)
        self._save(version="sharp-b", horizon="h3", line=2.5)

        a = close_drift_facit._rows(self.store, "sharp-a")
        b = close_drift_facit._rows(self.store, "sharp-b")

        self.assertEqual(1, len(a))
        self.assertEqual(1, len(b))
        self.assertEqual("sharp-a", next(iter(a))[0])
        self.assertEqual("sharp-b", next(iter(b))[0])

    def test_default_rows_use_the_current_sharp_version(self):
        self._save(version="current", horizon="h3", line=2.5)
        self._save(version="legacy", horizon="h3", line=2.5)
        with patch.object(
                close_drift_facit.oddset_ledger, "prediction_versions",
                return_value={"sharp": {"signal_version": "current"}}):
            rows = close_drift_facit._rows(self.store)
        self.assertEqual({"current"}, {key[0] for key in rows})

    def test_line_move_join_never_crosses_versions(self):
        self._save(version="sharp-a", horizon="h24", line=2.0)
        self._save(version="sharp-b", horizon="h3", line=2.5,
                   closing_line=3.0)
        self.assertEqual([], list(close_drift_facit_v2._line_move_rows(
            self.store, "ou", "O", "sharp-b")))

        self._save(version="sharp-a", horizon="h3", line=2.5,
                   closing_line=3.0)
        rows = list(close_drift_facit_v2._line_move_rows(
            self.store, "ou", "O", "sharp-a"))
        self.assertEqual(1, len(rows))
        self.assertEqual("m1", rows[0]["match_id"])

    def test_wide_absence_window_includes_same_day_iso_timestamp(self):
        self.store.oddset_save_absence_capture({
            "match_id": "m1", "captured_at": "2026-08-01T12:00:00Z",
            "provider": "sofascore", "status": "observed",
            "source_event_id": "1", "match_start": "2026-08-02T12:00:00Z",
            "confirmed": 0, "payload_hash": "at-upper-bound",
        }, [])

        row = close_drift_facit_v2._wide_absence_base(
            self.store, "m1", "2026-08-02T12:00:00Z",
            "2026-08-01T18:00:00Z")

        self.assertIsNotNone(row)
        self.assertEqual("2026-08-01T12:00:00Z", row[0])


if __name__ == "__main__":
    unittest.main()
