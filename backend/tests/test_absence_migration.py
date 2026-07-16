import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrera_franvarohistorik import migrate


class AbsenceMigrationTests(unittest.TestCase):
    def test_legacy_meta_is_backfilled_once_without_inventing_player_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.executescript("""
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE oddset_matches (
                    id TEXT PRIMARY KEY, start TEXT
                );
            """)
            conn.execute("INSERT INTO oddset_matches(id,start) VALUES(?,?)",
                         ("m1", "2026-07-17T02:30:00Z"))
            conn.execute("INSERT INTO meta(key,value) VALUES(?,?)", (
                "oddset_abs:m1", json.dumps({
                    "at": "2026-07-16T10:00:00Z", "confirmed": False,
                    "home": [{"name": "Legacy Player", "reason": "skada",
                              "apps": 4, "rating": 6.5}], "away": [],
                })))
            conn.commit()
            conn.close()

            first = migrate(db)
            second = migrate(db)

            self.assertEqual(1, first["inserted_captures"])
            self.assertEqual(1, first["inserted_players"])
            self.assertEqual(0, second["inserted_captures"])
            self.assertEqual("ok", second["integrity"])
            conn = sqlite3.connect(db)
            player = conn.execute(
                "SELECT player_id, position, name FROM oddset_absence_player").fetchone()
            conn.close()
            self.assertEqual((None, None, "Legacy Player"), player)


if __name__ == "__main__":
    unittest.main()
