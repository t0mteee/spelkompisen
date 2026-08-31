import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import migrera_pool_totaler


class PoolTotalMigrationTests(unittest.TestCase):
    def test_migration_is_additive_backed_up_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "old.db"
            backup = root / "backup.db"
            conn = sqlite3.connect(db)
            conn.executescript("""
                CREATE TABLE sharp_odds (
                    product TEXT NOT NULL,
                    draw_number INTEGER NOT NULL,
                    event_number INTEGER NOT NULL,
                    bookmaker TEXT,
                    one REAL, x REAL, two REAL,
                    confidence REAL, matched TEXT, fetched_at TEXT,
                    PRIMARY KEY(product, draw_number, event_number)
                );
                INSERT INTO sharp_odds VALUES
                    ('europatipset',2603,8,'pinnacle',2.66,2.99,3.16,
                     0.99,'Deportivo - Valencia','2026-08-30T12:00:00Z');
            """)
            conn.commit()
            conn.close()

            first = migrera_pool_totaler.migrate(db, backup)
            second = migrera_pool_totaler.migrate(db, backup)

            self.assertTrue(first["backup_created"])
            self.assertFalse(second["backup_created"])
            self.assertEqual("ok", second["integrity_check"])
            self.assertEqual(0, second["historical_rows_backfilled"])
            self.assertEqual([], second["columns_added"])
            self.assertTrue(backup.is_file())
            conn = sqlite3.connect(db)
            try:
                columns = {row[1] for row in conn.execute(
                    "PRAGMA table_info(sharp_odds)")}
                self.assertTrue({
                    "total_line", "over_odds", "under_odds",
                }.issubset(columns))
                self.assertEqual(0, conn.execute(
                    "SELECT COUNT(*) FROM sharp_total_snapshots").fetchone()[0])
                self.assertEqual(1, conn.execute(
                    "SELECT COUNT(*) FROM sharp_odds").fetchone()[0])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
