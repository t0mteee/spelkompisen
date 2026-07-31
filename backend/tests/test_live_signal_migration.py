import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts import migrera_live_signal_ledger


class LiveSignalMigrationTests(unittest.TestCase):
    def test_migration_is_idempotent_and_creates_both_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            sqlite3.connect(db).close()

            first = migrera_live_signal_ledger.migrate(db)
            second = migrera_live_signal_ledger.migrate(db)

            self.assertEqual("ok", first["integrity"])
            self.assertTrue(all(info["created"]
                                for info in first["tables"].values()))
            self.assertFalse(any(info["created"]
                                 for info in second["tables"].values()))
            self.assertIn("signal_level", first["tables"]
                          ["oddset_live_signal"]["columns"])
            self.assertIn("over_profit", first["tables"]
                          ["oddset_live_signal_result"]["columns"])


if __name__ == "__main__":
    unittest.main()
