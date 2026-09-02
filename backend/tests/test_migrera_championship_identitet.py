import tempfile
import unittest
from pathlib import Path

from app.storage import Storage
from scripts import migrera_championship_identitet as migration


class ChampionshipIdentityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"

    def tearDown(self):
        self.tmp.cleanup()

    def _seed(self, *, blocked: bool = False) -> None:
        store = Storage(self.db)
        store.oddset_upsert_match({
            "id": "pin:1", "league": "championship",
            "home": "Birmingham City", "away": "Wolverhampton",
            "start": "2026-09-05T11:00:00Z", "pinnacle_id": "1",
        })
        store.oddset_upsert_match({
            "id": "svs:2", "league": "championship",
            "home": "Birmingham", "away": "Wolves",
            "start": "2026-09-05T11:00:00Z", "kambi_id": "2",
        })
        store.oddset_save_odds(
            "pin:1", "pinnacle", {"1": 2.0, "X": 3.4, "2": 3.7},
            "2026-09-02T20:00:00Z")
        store.oddset_save_odds(
            "svs:2", "svenskaspel", {"1": 2.1, "X": 3.3, "2": 3.6},
            "2026-09-02T20:00:00Z")
        if blocked:
            store.conn.execute(
                "INSERT INTO oddset_absence_capture(match_id,captured_at,provider,"
                "status,source_event_id,match_start,confirmed,payload_hash,"
                "home_missing,away_missing,missing_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("svs:2", "2026-09-02T20:00:00Z", "test", "observed",
                 "event", "2026-09-05T11:00:00Z", 1, "hash", 0, 0, 0))
            store.conn.commit()
        store.close()

    def test_moves_odds_and_provider_id_without_losing_rows(self):
        self._seed()

        result = migration.migrate(self.db)

        self.assertEqual(1, result["merged"])
        self.assertEqual(2, result["matches_before"])
        self.assertEqual(1, result["matches_after"])
        self.assertEqual(result["odds_before"], result["odds_after"])
        self.assertEqual(0, result["remaining_alias_duplicates"])
        self.assertEqual("ok", result["integrity"])
        store = Storage(self.db)
        try:
            match = dict(store.conn.execute(
                "SELECT * FROM oddset_matches WHERE id='pin:1'").fetchone())
            self.assertEqual("2", match["kambi_id"])
            self.assertEqual("Birmingham", match["home"])
            self.assertEqual("Wolves", match["away"])
            self.assertEqual(
                {"pinnacle", "svenskaspel"},
                {row[0] for row in store.conn.execute(
                    "SELECT DISTINCT source FROM oddset_odds WHERE match_id='pin:1'")})
            self.assertIsNone(store.conn.execute(
                "SELECT 1 FROM oddset_matches WHERE id='svs:2'").fetchone())
        finally:
            store.close()

        # Engångsskriptet är säkert att köra om.
        self.assertEqual(0, migration.migrate(self.db)["merged"])

    def test_unknown_references_abort_the_whole_transaction(self):
        self._seed(blocked=True)

        with self.assertRaisesRegex(RuntimeError, "oddset_absence_capture"):
            migration.migrate(self.db)

        store = Storage(self.db)
        try:
            self.assertEqual(2, store.conn.execute(
                "SELECT COUNT(*) FROM oddset_matches").fetchone()[0])
            self.assertEqual(6, store.conn.execute(
                "SELECT COUNT(*) FROM oddset_odds").fetchone()[0])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
