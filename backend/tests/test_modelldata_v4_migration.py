import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import migrera_modelldata_v4


class ModelDataV4MigrationTests(unittest.TestCase):
    def _legacy_db(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.executescript("""
        CREATE TABLE oddset_results (
          league TEXT NOT NULL, date TEXT NOT NULL, home TEXT NOT NULL,
          away TEXT NOT NULL, home_raw TEXT, away_raw TEXT, hg INTEGER,
          ag INTEGER, xg_h REAL, xg_a REAL, cor_h REAL, cor_a REAL,
          source TEXT, PRIMARY KEY (league,date,home,away));
        CREATE TABLE oddset_absence_capture (
          match_id TEXT NOT NULL, captured_at TEXT NOT NULL,
          source_event_id TEXT, match_start TEXT, confirmed INTEGER NOT NULL,
          payload_hash TEXT NOT NULL, home_missing INTEGER NOT NULL,
          away_missing INTEGER NOT NULL, missing_count INTEGER NOT NULL,
          PRIMARY KEY (match_id,captured_at));
        CREATE TABLE oddset_absence_player (
          match_id TEXT NOT NULL, captured_at TEXT NOT NULL, side TEXT NOT NULL,
          player_key TEXT NOT NULL, player_id INTEGER, name TEXT NOT NULL,
          position TEXT, reason_code INTEGER, reason TEXT, description TEXT,
          expected_end TEXT, appearances INTEGER, rating REAL,
          PRIMARY KEY (match_id,captured_at,side,player_key));
        """)
        conn.executemany(
            "INSERT INTO oddset_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                ("allsvenskan", "2026-07-01", "a", "b", "A", "B", 1, 0,
                 1.2, 0.4, 5, 2, "fd"),
                ("allsvenskan", "2026-07-02", "c", "d", "C", "D", 2, 1,
                 1.8, 0.7, 6, 3, "sofa+fs"),
                ("premier_league", "2026-07-03", "e", "f", "E", "F", 0, 0,
                 None, None, 4, 4, "fd"),
            ])
        conn.executemany(
            "INSERT INTO oddset_absence_capture VALUES(?,?,?,?,?,?,?,?,?)", [
                ("m1", "2026-08-01T10:00:00Z", "123", None, 0, "a", 0, 1, 1),
                ("m1", "2026-08-01T11:00:00Z", "fs:ABC", None, 0, "b", 1, 0, 1),
            ])
        conn.executemany(
            "INSERT INTO oddset_absence_player VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", [
                ("m1", "2026-08-01T10:00:00Z", "away", "sofa:77", 77,
                 "Sofa", "F", None, "skada", None, None, 12, 6.8),
                ("m1", "2026-08-01T11:00:00Z", "home", "sofa:XYZ", "XYZ",
                 "Flash", None, None, "skada", None, None, None, None),
            ])
        conn.commit()
        conn.close()

    @staticmethod
    def _old_stats_table(conn: sqlite3.Connection) -> None:
        conn.executescript("""
        CREATE TABLE oddset_result_stats (
          league TEXT NOT NULL, date TEXT NOT NULL, home TEXT NOT NULL,
          away TEXT NOT NULL, provider TEXT NOT NULL, provider_event_id TEXT,
          observed_at TEXT, match_start_at TEXT, final_home_score INTEGER,
          final_away_score INTEGER, xg_h REAL, xg_a REAL, cor_h REAL,
          cor_a REAL, PRIMARY KEY (league,date,home,away,provider));
        """)

    def test_migration_separates_stats_and_namespaces_player_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            self._legacy_db(db)

            result = migrera_modelldata_v4.migrate(db)

            self.assertTrue(result["absence_rebuilt"])
            self.assertEqual(4, result["stats_rows"])
            self.assertEqual("ok", result["integrity"])
            self.assertEqual("ok", result["foreign_keys"])
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            sources = [tuple(row) for row in conn.execute(
                "SELECT date,source,xg_h,cor_h FROM oddset_results ORDER BY date")]
            providers = [tuple(row) for row in conn.execute(
                "SELECT date,provider,xg_h,cor_h FROM oddset_result_stats "
                "ORDER BY date")]
            players = [tuple(row) for row in conn.execute(
                "SELECT provider,player_id FROM oddset_absence_player "
                "ORDER BY provider")]
            player_type = {row[1]: row[2] for row in conn.execute(
                "PRAGMA table_info(oddset_absence_player)")}["player_id"]
            conn.close()
            self.assertEqual([
                ("2026-07-01", "fd", None, None),
                ("2026-07-02", "sofa", None, None),
                ("2026-07-03", "fd", None, None),
            ], sources)
            self.assertEqual([
                ("2026-07-01", "sofascore", 1.2, 5.0),
                ("2026-07-02", "flashscore", 1.8, None),
                ("2026-07-02", "legacy", None, 6.0),
                ("2026-07-03", "football_data", None, 4.0),
            ], providers)
            self.assertEqual([("flashscore", "fs:XYZ"),
                              ("sofascore", "sofa:77")], players)
            self.assertEqual("TEXT", player_type.upper())

    def test_failure_after_result_mutation_rolls_back_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            self._legacy_db(db)
            with patch.object(migrera_modelldata_v4, "_rebuild_absences",
                              side_effect=RuntimeError("injected")):
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    migrera_modelldata_v4.migrate(db)

            conn = sqlite3.connect(db)
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='oddset_result_stats'").fetchone()
            row = conn.execute(
                "SELECT source,xg_h,cor_h FROM oddset_results "
                "WHERE date='2026-07-02'").fetchone()
            columns = {r[1] for r in conn.execute(
                "PRAGMA table_info(oddset_absence_capture)")}
            conn.close()
            self.assertIsNone(table)
            self.assertEqual(("sofa+fs", 1.8, 6.0), row)
            self.assertNotIn("provider", columns)

    def test_migration_is_idempotent_and_backup_is_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            backup = Path(tmp) / "backup.db"
            self._legacy_db(db)
            self.assertTrue(migrera_modelldata_v4.backup_database(db, backup))
            self.assertFalse(migrera_modelldata_v4.backup_database(db, backup))
            migrera_modelldata_v4.migrate(db)

            second = migrera_modelldata_v4.migrate(db)

            self.assertFalse(second["absence_rebuilt"])
            self.assertEqual(4, second["stats_rows"])
            conn = sqlite3.connect(backup)
            self.assertEqual(3, conn.execute(
                "SELECT COUNT(*) FROM oddset_results").fetchone()[0])
            conn.close()

    def test_existing_provider_row_is_completed_without_losing_legacy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            self._legacy_db(db)
            conn = sqlite3.connect(db)
            self._old_stats_table(conn)
            conn.execute(
                "INSERT INTO oddset_result_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("allsvenskan", "2026-07-01", "a", "b", "sofascore",
                 "sofa:1", "2026-07-01T20:00:00Z",
                 "2026-07-01T18:00:00Z", 1, 0, 1.2, 0.4, None, None))
            conn.commit()
            conn.close()

            result = migrera_modelldata_v4.migrate(db)

            self.assertEqual(4, result["stats_rows"])
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM oddset_result_stats WHERE date='2026-07-01' "
                "AND provider='sofascore'").fetchone()
            columns = {entry[1] for entry in conn.execute(
                "PRAGMA table_info(oddset_result_stats)")}
            conn.close()
            self.assertEqual((1.2, 0.4, 5.0, 2.0),
                             (row["xg_h"], row["xg_a"], row["cor_h"],
                              row["cor_a"]))
            self.assertEqual("2026-07-01T20:00:00Z", row["xg_observed_at"])
            self.assertIsNone(row["corners_observed_at"])
            self.assertEqual("sofa:1", row["provider_event_id"])
            self.assertNotIn("observed_at", columns)

    def test_ambiguous_old_common_time_is_not_assigned_to_either_family(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            self._legacy_db(db)
            conn = sqlite3.connect(db)
            self._old_stats_table(conn)
            conn.execute(
                "INSERT INTO oddset_result_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("serie_a", "2026-06-01", "x", "y", "flashscore", "FS1",
                 "2026-06-01T22:00:00Z", "2026-06-01T18:00:00Z", 2, 1,
                 1.7, 0.8, 4, 6))
            conn.commit()
            conn.close()

            migrera_modelldata_v4.migrate(db)

            conn = sqlite3.connect(db)
            row = conn.execute(
                "SELECT xg_observed_at,corners_observed_at,xg_h,cor_h "
                "FROM oddset_result_stats WHERE provider='flashscore' "
                "AND league='serie_a'").fetchone()
            conn.close()
            self.assertEqual((None, None, 1.7, 4.0), row)

    def test_conflicting_existing_provider_value_aborts_and_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            self._legacy_db(db)
            conn = sqlite3.connect(db)
            self._old_stats_table(conn)
            conn.execute(
                "INSERT INTO oddset_result_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("allsvenskan", "2026-07-01", "a", "b", "sofascore",
                 "sofa:1", "2026-07-01T20:00:00Z", None, 1, 0,
                 9.9, 0.4, None, None))
            conn.commit()
            conn.close()

            with self.assertRaisesRegex(RuntimeError, "motstridig legacy-statistik"):
                migrera_modelldata_v4.migrate(db)

            conn = sqlite3.connect(db)
            result = conn.execute(
                "SELECT source,xg_h,cor_h FROM oddset_results "
                "WHERE date='2026-07-01'").fetchone()
            stats = conn.execute(
                "SELECT observed_at,xg_h,cor_h FROM oddset_result_stats "
                "WHERE date='2026-07-01'").fetchone()
            conn.close()
            self.assertEqual(("fd", 1.2, 5.0), result)
            self.assertEqual(("2026-07-01T20:00:00Z", 9.9, None), stats)

    def test_provider_inference_accepts_an_away_only_xg_value(self) -> None:
        self.assertEqual(
            "sofascore",
            migrera_modelldata_v4._provider("fd", 0.4),
        )


if __name__ == "__main__":
    unittest.main()
