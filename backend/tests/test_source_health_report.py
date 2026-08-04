import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app.storage import Storage

from unittest.mock import patch

from app import live_radar

from cli import format_link_gaps, format_source_health


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


class LinkGapReportTests(unittest.TestCase):
    """Fem namnfall på ett dygn hittades genom att Saman såg dubbletter i
    UI:t. Detektorn ska hitta dem först — och bara dem."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _fs(self, home, away, start="2026-08-02T15:00:00Z"):
        self.store.live_flashscore_save({
            "flashscore_id": f"fs{home}", "captured_at": self.at,
            "capture_version": "v", "league": "eliteserien",
            "tournament": "Eliteserien", "home": home, "away": away,
            "start_at": start, "minute": 30, "home_score": 0, "away_score": 0,
            "shots_home": 5, "shots_away": 4})

    def _sofa(self, home, away, start="2026-08-02T15:00:00Z"):
        self.store.oddset_save_live_capture({
            "event_id": abs(hash(home)) % 10**6, "captured_at": self.at,
            "capture_version": "v", "league": "eliteserien",
            "tournament": "Eliteserien", "home": home, "away": away,
            "start_at": start, "status": "2nd half", "minute": 30,
            "home_score": 0, "away_score": 0})

    def test_similar_unlinked_pair_is_reported(self):
        self._fs("Hodd", "Moss")
        self._sofa("Hødd IL", "Moss FK")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("Hodd", rapport)
        self.assertIn("Hødd IL", rapport)

    def test_linked_pair_is_not_reported(self):
        self._fs("Hodd", "Moss")
        self._sofa("Hødd IL", "Moss FK")
        rapport = format_link_gaps(self.store, hours=6)   # aliasen aktiva
        self.assertIn("inga", rapport)

    def test_different_matches_at_the_same_kickoff_are_not_reported(self):
        """Två skilda matcher med samma avspark får inte bli brus."""
        self._fs("Lyn", "Sogndal")
        self._sofa("Egersund", "Sandnes Ulf")
        rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("inga", rapport)

    def test_different_kickoff_is_never_paired(self):
        self._fs("Hodd", "Moss", start="2026-08-02T15:00:00Z")
        self._sofa("Hødd IL", "Moss FK", start="2026-08-02T19:00:00Z")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            self.assertIn("inga", format_link_gaps(self.store, hours=6))


if __name__ == "__main__":
    unittest.main()
