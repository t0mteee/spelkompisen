import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrera_v2_features import migrate


class V2FeatureMigrationTests(unittest.TestCase):
    def test_schema_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            sqlite3.connect(db).close()

            first = migrate(db)
            second = migrate(db)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual(0, second["rows"])
            self.assertEqual(0, second["removed_development"])
            self.assertEqual("ok", second["integrity"])


if __name__ == "__main__":
    unittest.main()
