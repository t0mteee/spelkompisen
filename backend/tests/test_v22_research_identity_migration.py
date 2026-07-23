import tempfile
import unittest
from pathlib import Path

from app.storage import Storage
from scripts.migrera_v22_research_identitet import migrate


class ResearchIdentityMigrationTests(unittest.TestCase):
    def test_placeholder_duplicate_moves_kambi_history_to_pinnacle_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            store = Storage(db)
            try:
                store.oddset_upsert_match({
                    "id": "pin:1", "league": "serie_a",
                    "home": "Internazionale", "away": "Monza",
                    "start": "2026-08-22T16:30:00Z", "pinnacle_id": "1",
                })
                store.oddset_upsert_match({
                    "id": "svs:2", "league": "serie_a",
                    "home": "Inter", "away": "Monza",
                    "start": "2026-08-22T13:00:00Z", "kambi_id": "2",
                })
                store.oddset_save_odds(
                    "svs:2", "svenskaspel",
                    {"1": 1.8, "X": 3.8, "2": 4.5},
                    "2026-07-23T20:00:00Z")
            finally:
                store.close()

            first = migrate(db)
            second = migrate(db)
            store = Storage(db)
            try:
                matches = [row for row in store.oddset_matches()
                           if row["league"] == "serie_a"]
                odds = store.oddset_latest(["pin:1"])
            finally:
                store.close()

        self.assertEqual(1, first["merged"])
        self.assertEqual(0, second["merged"])
        self.assertEqual(1, len(matches))
        self.assertEqual("2", matches[0]["kambi_id"])
        self.assertEqual("2026-08-22T16:30:00Z", matches[0]["start"])
        self.assertAlmostEqual(
            1.8, odds["pin:1"]["svenskaspel"]["1x2"]["1"])


if __name__ == "__main__":
    unittest.main()
