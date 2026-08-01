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
            self.assertIn("clock_source", first["tables"]
                          ["oddset_live_signal"]["columns"])

    def test_pre_clock_source_schema_gets_the_columns_added(self):
        # En DB från den VERKLIGA 2026-07-31-DDL:n (utan proveniens-
        # kolumnerna men med alla constraints kvar — DROP COLUMN bevarar dem)
        # ska migreras additivt, inte falla på valideringen.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            migrera_live_signal_ledger.migrate(db)
            conn = sqlite3.connect(db)
            conn.execute(
                "ALTER TABLE oddset_live_signal DROP COLUMN clock_source")
            conn.execute(
                "ALTER TABLE oddset_live_signal DROP COLUMN clock_observed_at")
            conn.commit()
            conn.close()

            result = migrera_live_signal_ledger.migrate(db)

            self.assertIn("clock_source", result["tables"]
                          ["oddset_live_signal"]["columns"])
            self.assertIn("clock_observed_at", result["tables"]
                          ["oddset_live_signal"]["columns"])

    def test_deviant_existing_schema_fails_loudly_without_mutation(self):
        # CREATE TABLE IF NOT EXISTS är en tyst no-op på en avvikande tabell —
        # migrationen ska FELA FÖRE någon mutation, inte lämna DB:n
        # halvmigrerad med nya systertabeller och ALTER:ade kolumner.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE oddset_live_signal "
                         "(id INTEGER PRIMARY KEY, helt_fel_kolumn TEXT)")
            conn.commit()
            conn.close()

            with self.assertRaises(RuntimeError) as ctx:
                migrera_live_signal_ledger.migrate(db)
            self.assertIn("avviker", str(ctx.exception))
            conn = sqlite3.connect(db)
            tables = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(oddset_live_signal)")]
            conn.close()
            self.assertNotIn("oddset_live_capture", tables,
                             "fälld migration får inte ha skapat systertabeller")
            self.assertNotIn("clock_source", columns,
                             "fälld migration får inte ha ALTER:at tabellen")

    def test_missing_unique_guard_fails_loudly(self):
        # Rätt kolumnnamn men utan UNIQUE-vakten (t.ex. en CREATE TABLE AS-
        # kopia) — append-once vore tyst brutet; migrationen ska fälla.
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            migrera_live_signal_ledger.migrate(db)
            conn = sqlite3.connect(db)
            conn.executescript(
                "CREATE TABLE kopia AS SELECT * FROM oddset_live_signal "
                "WHERE 0;\n"
                "DROP TABLE oddset_live_signal;\n"
                "ALTER TABLE kopia RENAME TO oddset_live_signal;")
            conn.commit()
            conn.close()

            with self.assertRaises(RuntimeError) as ctx:
                migrera_live_signal_ledger.migrate(db)
            self.assertIn("UNIQUE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
