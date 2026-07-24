import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import migrera_pool_capture_v2 as migration


class PoolCaptureMigrationTests(unittest.TestCase):
    def test_migration_is_additive_backed_up_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "old.db"
            backup = root / "backup.db"
            conn = sqlite3.connect(db)
            conn.executescript("""
                CREATE TABLE pool_draw_snapshot (
                    product TEXT, draw_number INTEGER, fetched_at TEXT,
                    net_sale REAL, jackpot REAL
                );
                CREATE TABLE pool_pit_draw_features (
                    product TEXT, draw_number INTEGER
                );
                CREATE TABLE pool_pit_match_features (
                    product TEXT, draw_number INTEGER
                );
                CREATE TABLE pool_system_ledger (
                    product TEXT, draw_number INTEGER
                );
                INSERT INTO pool_draw_snapshot
                    VALUES ('stryktipset', 1, '2026-01-01T00:00:00Z', 10, NULL);
            """)
            conn.commit()
            conn.close()

            with patch.object(migration, "DB", db), \
                    patch.object(migration, "BACKUP", backup), \
                    contextlib.redirect_stdout(io.StringIO()):
                # tysta migrationsutskriften — den drunknar testsvitens slutrad
                migration.main()
                migration.main()

            conn = sqlite3.connect(db)
            try:
                self.assertEqual(
                    1, conn.execute(
                        "SELECT COUNT(*) FROM pool_draw_snapshot").fetchone()[0])
                self.assertEqual(
                    "legacy_unverified",
                    conn.execute(
                        "SELECT jackpot_source FROM pool_draw_snapshot").fetchone()[0])
                self.assertEqual(
                    1, conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                        "AND name='pool_market_capture'").fetchone()[0])
                columns = {
                    r[1] for r in conn.execute(
                        "PRAGMA table_info(pool_system_ledger)")
                }
                self.assertTrue({
                    "jackpot_source", "published_payout_kr",
                    "payout_complete", "settlement_version",
                }.issubset(columns))
            finally:
                conn.close()
            self.assertTrue(backup.exists())


if __name__ == "__main__":
    unittest.main()
