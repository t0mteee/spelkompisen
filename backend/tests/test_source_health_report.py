import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app.storage import Storage

from cli import format_source_health


class SourceHealthReportTests(unittest.TestCase):
    """Rapporten finns för EN fråga: kördes källan i varvet eller inte?"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime.now(dt.timezone.utc)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _at(self, minutes_ago: int) -> str:
        return (self.now - dt.timedelta(minutes=minutes_ago)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_a_source_that_skipped_the_dense_round_shows_a_hole(self) -> None:
        # Sofascore i båda förtätade varven, Flashscore bara i det första —
        # exakt mönstret från natten 2026-08-01/02.
        for m in (10, 8, 5, 3):
            self.store.oddset_record_source_health(
                "sofascore", "-", "live", self._at(m), True, 6)
        for m in (10, 5):
            self.store.oddset_record_source_health(
                "flashscore", "-", "live", self._at(m), True, 6)
        rapport = format_source_health(self.store, hours=6)
        self.assertIn("—", rapport)                       # hålet syns
        self.assertIn("flashscore    2 kontroller", rapport)
        self.assertIn("sofascore     4 kontroller", rapport)

    def test_source_never_checked_is_named_not_silently_absent(self) -> None:
        self.store.oddset_record_source_health(
            "sofascore", "-", "live", self._at(5), True, 6)
        rapport = format_source_health(self.store, hours=6)
        self.assertIn("fotmob      INGA kontroller", rapport)

    def test_failed_check_is_reported_with_its_error(self) -> None:
        self.store.oddset_record_source_health(
            "flashscore", "-", "live", self._at(5), False, 14,
            "3 matcher hoppade över (tidsbudget/matchtak)")
        rapport = format_source_health(self.store, hours=6)
        self.assertIn("1 med fel", rapport)
        self.assertIn("tidsbudget/matchtak", rapport)
        self.assertIn("✗", rapport)

    def test_checks_outside_the_window_are_not_counted(self) -> None:
        self.store.oddset_record_source_health(
            "flashscore", "-", "live", self._at(60 * 10), True, 6)
        rapport = format_source_health(self.store, hours=6)
        self.assertIn("inga kontroller registrerade", rapport)


if __name__ == "__main__":
    unittest.main()
