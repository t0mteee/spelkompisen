import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.storage import Storage
from scripts import backfill_elohistorik


CSV = """Rank,Club,Country,Level,Elo,From,To
None,Hammarby,SWE,1,1507.6638,2026-07-13,2026-07-19
"""

ALIAS_CSV = """Rank,Club,Country,Level,Elo,From,To
None,Bodo Glimt,NOR,1,1709.2,2026-07-13,2026-07-19
"""


class EloBackfillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    @mock.patch.object(backfill_elohistorik, "_discover",
                       return_value=({"hammarby": "Hammarby"}, []))
    @mock.patch.object(backfill_elohistorik.oddset_data, "fetch_elo_csv",
                       return_value=CSV)
    def test_success_is_resumable_and_idempotent(self, fetch, _discover) -> None:
        first = backfill_elohistorik.run(self.store, pause_seconds=0)
        second = backfill_elohistorik.run(self.store, pause_seconds=0)

        self.assertEqual(1, first["done"])
        self.assertEqual(1, first["changed"])
        self.assertEqual(1, second["skipped"])
        self.assertEqual(1, fetch.call_count)
        self.assertIsNotNone(self.store.meta_get("oddset_elo_backfill:hammarby"))
        self.assertEqual({"hammarby": 1508},
                         self.store.oddset_elo_as_of("2026-07-16"))

    @mock.patch.object(backfill_elohistorik, "_discover",
                       return_value=({"hammarby": "Hammarby"}, []))
    @mock.patch.object(backfill_elohistorik.oddset_data, "fetch_elo_csv",
                       side_effect=RuntimeError("temporary"))
    def test_failure_is_not_marked_done(self, _fetch, _discover) -> None:
        result = backfill_elohistorik.run(self.store, pause_seconds=0)

        self.assertEqual(0, result["done"])
        self.assertEqual(1, len(result["errors"]))
        self.assertIsNone(self.store.meta_get("oddset_elo_backfill:hammarby"))

    @mock.patch.object(backfill_elohistorik, "_discover",
                       return_value=({"bodoe glimt": "Bodoe Glimt"}, []))
    @mock.patch.object(backfill_elohistorik.oddset_data, "fetch_elo_csv",
                       return_value=ALIAS_CSV)
    def test_single_provider_identity_may_be_canonicalized_to_anchor(self, _fetch,
                                                                     _discover) -> None:
        result = backfill_elohistorik.run(self.store, pause_seconds=0)

        self.assertEqual(1, result["done"])
        self.assertEqual({"bodoe glimt": 1709},
                         self.store.oddset_elo_as_of("2026-07-16"))
        self.assertIn('"provider_club_key": "bodo glimt"',
                      self.store.meta_get("oddset_elo_backfill:bodoe glimt"))


if __name__ == "__main__":
    unittest.main()
