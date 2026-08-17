import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.storage import LIVE_RADAR_SCHEMA
from scripts import migrera_live_signal_quotes


class LiveSignalQuoteMigrationTests(unittest.TestCase):
    def test_migration_is_idempotent_and_preserves_signal_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            conn = sqlite3.connect(db)
            # Skapa grundtabellerna men simulera DB:n före den nya tabellen.
            old_schema = LIVE_RADAR_SCHEMA.split(
                "CREATE TABLE IF NOT EXISTS oddset_live_signal_quote", 1)[0]
            conn.executescript(old_schema)
            conn.execute(
                "INSERT INTO oddset_live_signal(match_key,provider,provider_event_id,"
                "captured_at,capture_version,signal_version,league,home,away,"
                "signal_level,signal_type,odds_status,recorded_at) "
                "VALUES('m','flashscore','e','2026-08-18T00:00:00Z','v','s',"
                "'l','h','a','watch','xg','not_offered','2026-08-18T00:00:00Z')")
            conn.commit()
            conn.close()

            first = migrera_live_signal_quotes.migrate(db)
            second = migrera_live_signal_quotes.migrate(db)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual("ok", second["integrity"])
            check = sqlite3.connect(db)
            self.assertEqual(1, check.execute(
                "SELECT COUNT(*) FROM oddset_live_signal").fetchone()[0])
            self.assertEqual(0, check.execute(
                "SELECT COUNT(*) FROM oddset_live_signal_quote").fetchone()[0])
            check.close()


if __name__ == "__main__":
    unittest.main()
