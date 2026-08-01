"""Migrationen som ger Flashscore en egen tabell och gör signal-id:t textbaserat."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
