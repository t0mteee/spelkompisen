import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset_data
from app.storage import Storage


def _event(event_id: int = 123) -> dict:
    return {
        "id": event_id,
        "status": {"type": "finished"},
        "startTimestamp": 1_720_000_000,
        "homeTeam": {"name": "Montreal"},
        "awayTeam": {"name": "Atlanta United"},
        "homeScore": {"current": 6, "normaltime": 2},
        "awayScore": {"current": 7, "normaltime": 2},
    }


class SofaIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_transient_statistics_error_is_retried(self) -> None:
        event = _event()
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=RuntimeError("temporary")):
            completed = oddset_data._ingest_event(self.store, "mls", event)

        self.assertFalse(completed)
        self.assertIsNone(self.store.meta_get("oddset_sofa_seen:123"))
        retry = json.loads(self.store.meta_get("oddset_sofa_retry:123"))
        self.assertEqual(1, retry["attempts"])
        self.assertEqual(1, len(self.store.oddset_results("mls")))

        statistics = {"statistics": [{"groups": [{"statisticsItems": [
            {"name": "Expected goals", "home": "1.4", "away": "0.9"},
            {"name": "Corner kicks", "home": "6", "away": "3"},
        ]}]}]}
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get", return_value=statistics):
            completed = oddset_data._ingest_event(self.store, "mls", event)

        self.assertTrue(completed)
        self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:123"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:123"))
        row = self.store.oddset_results("mls")[0]
        self.assertEqual(2, row["hg"])
        self.assertEqual(2, row["ag"])
        self.assertAlmostEqual(1.4, row["xg_h"])
        self.assertAlmostEqual(0.9, row["xg_a"])

    def test_normaltime_excludes_penalty_shootout(self) -> None:
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get", return_value={}):
            self.assertTrue(oddset_data._ingest_event(self.store, "mls", _event(456)))

        row = self.store.oddset_results("mls")[0]
        self.assertEqual((2, 2), (row["hg"], row["ag"]))

    def test_permanent_missing_statistics_does_not_retry_forever(self) -> None:
        class MissingStatistics(RuntimeError):
            response = type("Response", (), {"status_code": 404})()

        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=MissingStatistics("missing")):
            completed = oddset_data._ingest_event(self.store, "mls", _event(789))

        self.assertTrue(completed)
        self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:789"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:789"))


if __name__ == "__main__":
    unittest.main()
