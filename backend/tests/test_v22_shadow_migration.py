import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrera_v22_shadow import migrate, remove_empty_precreated_table


class V22ShadowMigrationTests(unittest.TestCase):
    def test_schema_migration_is_additive_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE keep_me (value TEXT)")
            conn.execute("INSERT INTO keep_me VALUES ('safe')")
            conn.commit()
            conn.close()

            first = migrate(db)
            second = migrate(db)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(0, second["rows"])
            self.assertEqual("ok", second["integrity"])
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(
                    "safe", conn.execute(
                        "SELECT value FROM keep_me").fetchone()[0])
            finally:
                conn.close()

    def test_cleanup_only_removes_an_empty_precreated_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE oddset_v22_shadow_capture (value TEXT)")
            conn.commit()
            conn.close()

            self.assertTrue(remove_empty_precreated_table(db))
            conn = sqlite3.connect(db)
            try:
                self.assertIsNone(conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='oddset_v22_shadow_capture'").fetchone())
            finally:
                conn.close()

    def test_cleanup_refuses_a_table_with_shadow_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE oddset_v22_shadow_capture (value TEXT)")
            conn.execute(
                "INSERT INTO oddset_v22_shadow_capture VALUES ('keep')")
            conn.commit()
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "innehåller 1 rader"):
                remove_empty_precreated_table(db)

            conn = sqlite3.connect(db)
            try:
                self.assertEqual("keep", conn.execute(
                    "SELECT value FROM oddset_v22_shadow_capture").fetchone()[0])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
