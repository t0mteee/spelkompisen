import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrera_elohistorik import migrate


class EloMigrationTests(unittest.TestCase):
    def test_legacy_meta_becomes_one_idempotent_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)", [
                ("oddset_elo", json.dumps({"hammarby": 1508, "brann": 1528})),
                ("oddset_elo_at", "2026-07-16T09:00:00Z"),
            ])
            conn.commit()
            conn.close()

            first = migrate(db)
            second = migrate(db)

            self.assertEqual(1, first["inserted_capture"])
            self.assertEqual(2, first["inserted_ratings"])
            self.assertEqual(0, second["inserted_capture"])
            self.assertEqual(2, second["ratings"])
            self.assertEqual("ok", second["integrity"])
            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT country, club_raw FROM oddset_elo_rating "
                "WHERE club_key='hammarby'").fetchone()
            conn.close()
            self.assertEqual((None, "hammarby"), row)

    def test_meta_moving_after_daily_capture_does_not_create_new_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.executemany("INSERT INTO meta(key,value) VALUES(?,?)", [
                ("oddset_elo", json.dumps({"hammarby": 1508})),
                ("oddset_elo_at", "2026-07-16T09:00:00Z"),
            ])
            conn.commit()
            conn.close()
            migrate(db)

            conn = sqlite3.connect(db)
            conn.execute(
                "INSERT INTO oddset_elo_capture VALUES(?,?,?,?,?)",
                ("2026-07-16T10:00:00.500000Z", "2026-07-16", "daily", "h", 1))
            conn.execute(
                "INSERT INTO oddset_elo_rating VALUES(?,?,?,?,?,?,?,?)",
                ("2026-07-16T10:00:00.500000Z", "hammarby", "Hammarby",
                 "SWE", 1, 1508.0, "2026-07-13", "2026-07-19"))
            conn.execute(
                "INSERT INTO oddset_elo_capture VALUES(?,?,?,?,?)",
                ("2026-07-16T10:00:00Z", "2026-07-16", "legacy", "old-bug", 1))
            conn.execute(
                "INSERT INTO oddset_elo_rating VALUES(?,?,?,?,?,?,?,?)",
                ("2026-07-16T10:00:00Z", "hammarby", "hammarby",
                 None, None, 1508.0, "2026-07-16", "2026-07-16"))
            conn.execute("UPDATE meta SET value=? WHERE key='oddset_elo_at'",
                         ("2026-07-16T10:00:00Z",))
            conn.commit()
            conn.close()

            result = migrate(db)

            self.assertEqual(0, result["inserted_capture"])
            self.assertEqual(2, result["captures"])
            self.assertEqual(1, result["removed_duplicate_legacy"])


if __name__ == "__main__":
    unittest.main()
