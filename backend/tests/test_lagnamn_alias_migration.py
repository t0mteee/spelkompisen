import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "migrera_lagnamn_alias", ROOT / "scripts" / "migrera_lagnamn_alias.py")
MIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIG)

SCHEMA = """
CREATE TABLE oddset_results (
    league TEXT NOT NULL, date TEXT NOT NULL,
    home TEXT NOT NULL, away TEXT NOT NULL,
    home_raw TEXT, away_raw TEXT,
    hg INTEGER, ag INTEGER, xg_h REAL, xg_a REAL,
    cor_h REAL, cor_a REAL, source TEXT,
    PRIMARY KEY (league, date, home, away)
);
"""


class LagnamnAliasMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.conn = sqlite3.connect(self.db)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        MIG.NAME_TABLES = (("oddset_results", ("home", "away")),)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _add(self, home, away, hg, ag, source, xg_h=None) -> None:
        self.conn.execute(
            "INSERT INTO oddset_results(league,date,home,away,hg,ag,source,xg_h) "
            "VALUES('allsvenskan','2026-05-25',?,?,?,?,?,?)",
            (home, away, hg, ag, source, xg_h))
        self.conn.commit()

    def _rows(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM oddset_results ORDER BY home, away").fetchall()

    def test_duplicate_pair_merges_and_football_data_wins(self) -> None:
        self._add("norrkoping", "malmo", 1, 5, "fd")
        self._add("ifk norrkoping", "malmo", 1, 5, "sofa")
        with self.conn:
            MIG.migrate(self.conn)
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertEqual("ifk norrkoping", rows[0]["home"])
        self.assertEqual("fd", rows[0]["source"], "fd är resultatfacit i v4")
        self.assertEqual((1, 5), (rows[0]["hg"], rows[0]["ag"]))

    def test_lone_row_is_only_renamed(self) -> None:
        self._add("halmstads", "sirius", 0, 3, "sofa")
        with self.conn:
            MIG.migrate(self.conn)
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertEqual("halmstad", rows[0]["home"])
        self.assertEqual("sofa", rows[0]["source"])

    def test_unrelated_clubs_are_never_merged(self) -> None:
        """Öster ≠ Östersund. Aliaslistan är per bevisat par."""
        self._add("oster", "sirius", 1, 0, "fd")
        self._add("ostersunds", "sirius", 2, 2, "fd")
        with self.conn:
            MIG.migrate(self.conn)
        self.assertEqual(2, len(self._rows()))

    def test_migration_is_idempotent(self) -> None:
        self._add("norrkoping", "malmo", 1, 5, "fd")
        self._add("ifk norrkoping", "malmo", 1, 5, "sofa")
        with self.conn:
            MIG.migrate(self.conn)
        first = [dict(r) for r in self._rows()]
        with self.conn:
            second = MIG.migrate(self.conn)
        self.assertEqual(first, [dict(r) for r in self._rows()])
        self.assertEqual(0, second["merged"]["oddset_results"])
        self.assertEqual(0, second["renamed"]["oddset_results"])

    def test_richer_row_wins_when_source_is_equal(self) -> None:
        self._add("goteborg", "hacken", 2, 1, "sofa")
        self._add("ifk goteborg", "hacken", 2, 1, "sofa", xg_h=1.7)
        with self.conn:
            MIG.migrate(self.conn)
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(1.7, rows[0]["xg_h"])


if __name__ == "__main__":
    unittest.main()
