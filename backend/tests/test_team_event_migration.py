import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrera_team_events import TABLES, backup_database, migrate


class TeamEventMigrationTests(unittest.TestCase):
    def test_backup_and_schema_migration_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            backup = Path(tmp) / "backup.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE marker(value TEXT)")
            conn.execute("INSERT INTO marker VALUES('before')")
            conn.commit()
            conn.close()

            self.assertTrue(backup_database(db, backup))
            self.assertFalse(backup_database(db, backup))
            first = migrate(db)
            second = migrate(db)

            self.assertEqual(set(TABLES), set(first["created"]))
            self.assertEqual([], second["created"])
            self.assertEqual([], second["added_columns"])
            self.assertEqual("ok", second["integrity"])
            saved = sqlite3.connect(backup).execute(
                "SELECT value FROM marker").fetchone()[0]
            self.assertEqual("before", saved)


if __name__ == "__main__":
    unittest.main()
