import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import migrera_live_radar


class LiveRadarMigrationTests(unittest.TestCase):
    def test_migration_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE legacy(id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO legacy VALUES(1)")
            conn.commit()
            conn.close()

            first = migrera_live_radar.migrate(db)
            second = migrera_live_radar.migrate(db)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual("ok", second["integrity"])
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(
                    1, conn.execute("SELECT COUNT(*) FROM legacy").fetchone()[0])
                # 26 datafält + `radar_version` (2026-08-05): koden som
                # producerade raden bärs av raden själv i stället för att
                # rekonstrueras ur en handskriven gränskonstant.
                self.assertEqual(
                    27, len(conn.execute(
                        "PRAGMA table_info(oddset_live_capture)").fetchall()))
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
