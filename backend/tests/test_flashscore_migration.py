"""Migrationen som ger Flashscore en egen tabell och gör signal-id:t textbaserat."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.storage import Storage
from scripts import migrera_flashscore


class FlashscoreMigrationTests(unittest.TestCase):
    def _legacy_db(self, path: Path) -> None:
        """En DB från 2026-08-01-läget: signal-id som INTEGER, ingen
        Flashscore-tabell — och EN bokförd signalrad som måste överleva."""
        store = Storage(path)
        store.live_signal_save({
            "match_key": "pin:1632638189", "match_id": "pin:1632638189",
            "provider": "sofascore", "provider_event_id": "15171622",
            "captured_at": "2026-08-01T01:02:15Z",
            "capture_version": "sofa-live-v2",
            "signal_version": "chance-gap-shadow-v2",
            "league": "mls", "home": "New York City FC", "away": "Toronto FC",
            "minute": 57, "home_score": 1, "away_score": 1,
            "signal_level": "watch", "signal_type": "xg",
            "ou_line": 3.5, "over_odds": 2.3, "under_odds": 1.52,
            "odds_source": "svenskaspel", "odds_status": "captured",
            "recorded_at": "2026-08-01T01:02:15Z",
        })
        store.close()
        # ...och skriv om kolumnen till INTEGER som den gamla versionen hade
        conn = sqlite3.connect(path)
        conn.executescript(
            "PRAGMA legacy_alter_table=ON;"
            "ALTER TABLE oddset_live_signal RENAME TO gammal;")
        ddl = migrera_flashscore._ddl("oddset_live_signal").replace(
            "provider_event_id   TEXT NOT NULL,   -- ogenomskinlig per provider:"
            "\n                                         -- Flashscores id är alfanumeriskt",
            "provider_event_id   INTEGER NOT NULL,")
        conn.execute(ddl)
        cols = ",".join(("id",) + Storage.LIVE_SIGNAL_COLUMNS)
        conn.execute(f"INSERT INTO oddset_live_signal({cols}) "
                     f"SELECT {cols} FROM gammal")
        conn.executescript("DROP TABLE gammal;"
                           "DROP TABLE IF EXISTS oddset_live_flashscore;")
        conn.commit()
        conn.close()

    def _real_0731_db(self, path: Path) -> None:
        """Verklig pre-fix-DDL: INTEGER-id och inga klockprovenienskolumner."""
        ddl = migrera_flashscore._ddl("oddset_live_signal").replace(
            "provider_event_id   TEXT NOT NULL,   -- ogenomskinlig per provider:"
            "\n                                         -- Flashscores id är alfanumeriskt",
            "provider_event_id   INTEGER NOT NULL,")
        ddl = "\n".join(
            line for line in ddl.splitlines()
            if "clock_source" not in line and "clock_observed_at" not in line)
        conn = sqlite3.connect(path)
        conn.execute(ddl)
        conn.execute(migrera_flashscore._ddl("oddset_live_signal_result"))
        conn.execute(
            "INSERT INTO oddset_live_signal("
            "match_key,provider,provider_event_id,captured_at,capture_version,"
            "signal_version,league,home,away,signal_level,signal_type,odds_status,"
            "recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("sofa:1", "sofascore", 123, "2026-07-31T20:00:00Z",
             "sofa-live-v2", "chance-gap-shadow-v2", "allsvenskan",
             "Hammarby", "AIK", "watch", "xg", "not_offered",
             "2026-07-31T20:00:01Z"))
        conn.commit()
        conn.close()

    def test_migration_preserves_the_existing_signal_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)

            result = migrera_flashscore.migrate(db)

            self.assertTrue(result["signal_rebuilt"])
            self.assertEqual(1, result["signal_rows"])
            self.assertEqual("ok", result["integrity"])
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            row = dict(conn.execute(
                "SELECT * FROM oddset_live_signal").fetchone())
            conn.close()
            self.assertEqual("New York City FC", row["home"])
            self.assertEqual("chance-gap-shadow-v2", row["signal_version"])
            self.assertEqual(2.3, row["over_odds"])

    def test_provider_event_id_becomes_text_and_accepts_flashscore_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)
            migrera_flashscore.migrate(db)

            store = Storage(db)
            store.live_signal_save({
                "match_key": "flashscore:SKg88Q3T", "provider": "flashscore",
                "provider_event_id": "SKg88Q3T",
                "captured_at": "2026-08-01T11:05:00Z",
                "capture_version": "flashscore-live-v1",
                "signal_version": "chance-gap-shadow-v3",
                "league": "friendlies", "home": "Chelsea", "away": "Tottenham",
                "signal_level": "watch", "signal_type": "xg",
                "odds_status": "no_svenskaspel_id",
                "recorded_at": "2026-08-01T11:05:00Z"})
            locked = store.live_signal_locked_key(
                "chance-gap-shadow-v3", [("flashscore", "SKg88Q3T")])
            store.close()
            self.assertEqual("flashscore:SKg88Q3T", locked)

    def test_unique_guard_and_index_survive_the_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)
            migrera_flashscore.migrate(db)

            conn = sqlite3.connect(db)
            uniques = [
                tuple(r[2] for r in conn.execute(f"PRAGMA index_info({i[1]})"))
                for i in conn.execute("PRAGMA index_list(oddset_live_signal)")
                if i[2]]
            indexes = {i[1] for i in conn.execute(
                "PRAGMA index_list(oddset_live_signal)")}
            conn.close()
            self.assertIn(("match_key", "signal_version", "signal_type",
                           "signal_level"), uniques)
            self.assertIn("idx_live_signal_recent", indexes)

    def test_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)
            migrera_flashscore.migrate(db)

            second = migrera_flashscore.migrate(db)

            self.assertFalse(second["signal_rebuilt"])
            self.assertFalse(second["flashscore_created"])
            self.assertEqual(1, second["signal_rows"])

    def test_real_0731_schema_without_clock_columns_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._real_0731_db(db)

            result = migrera_flashscore.migrate(db)

            self.assertTrue(result["signal_rebuilt"])
            conn = sqlite3.connect(db)
            columns = {row[1]: row[2] for row in conn.execute(
                "PRAGMA table_info(oddset_live_signal)")}
            row = conn.execute(
                "SELECT provider_event_id,clock_source,clock_observed_at "
                "FROM oddset_live_signal").fetchone()
            conn.close()
            self.assertEqual("TEXT", columns["provider_event_id"].upper())
            self.assertEqual(("123", None, None), row)

    def test_validation_failure_leaves_all_existing_schema_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE oddset_live_flashscore("
                         "flashscore_id TEXT PRIMARY KEY)")
            conn.commit()
            before = {row[1]: row[2] for row in conn.execute(
                "PRAGMA table_info(oddset_live_signal)")}
            conn.close()

            with self.assertRaises(RuntimeError):
                migrera_flashscore.migrate(db)

            conn = sqlite3.connect(db)
            after = {row[1]: row[2] for row in conn.execute(
                "PRAGMA table_info(oddset_live_signal)")}
            malformed = [row[1] for row in conn.execute(
                "PRAGMA table_info(oddset_live_flashscore)")]
            conn.close()
            self.assertEqual(before, after)
            self.assertEqual(["flashscore_id"], malformed)

    def test_failure_after_rebuild_rolls_back_the_whole_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "test.db"
            self._legacy_db(db)

            with patch.object(
                    migrera_flashscore, "_repair_result_fk",
                    side_effect=RuntimeError("simulerat fel efter ombyggnad")):
                with self.assertRaisesRegex(RuntimeError, "simulerat fel"):
                    migrera_flashscore.migrate(db)

            conn = sqlite3.connect(db)
            provider_type = next(
                row[2] for row in conn.execute(
                    "PRAGMA table_info(oddset_live_signal)")
                if row[1] == "provider_event_id")
            flashscore_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                ("oddset_live_flashscore",)).fetchone()
            rows = conn.execute(
                "SELECT COUNT(*) FROM oddset_live_signal").fetchone()[0]
            conn.close()
            self.assertEqual("INTEGER", provider_type.upper())
            self.assertIsNone(flashscore_exists)
            self.assertEqual(1, rows)


if __name__ == "__main__":
    unittest.main()
