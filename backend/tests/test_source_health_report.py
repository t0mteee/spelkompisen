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
        """Det som återstår efter kontextregeln är ÖVERSÄTTNINGAR — namn utan
        gemensam teckenstruktur, som bara ett observerat alias kan lösa.
        `FC Copenhagen` ↔ `FC København` är exakt det fallet (2026-08-06),
        och så här upptäcktes det: i en hink där alla ANDRA matcher länkade.
        """
        self._fs("Paide (Est)", "SK Rapid (Aut)")       # länkar via kontext
        self._sofa("Paide Linnameeskond", "SK Rapid Wien")
        self._fs("FC Copenhagen (Den)", "Debrecen (Hun)")
        self._sofa("FC København", "Debrecen")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("Copenhagen", rapport)
        self.assertIn("København", rapport)
        self.assertNotIn("Paide", rapport, "länkade par är inte luckor")

    def test_linked_pair_is_not_reported(self):
        self._fs("FC Copenhagen (Den)", "Debrecen (Hun)")
        self._sofa("FC København", "Debrecen")
        rapport = format_link_gaps(self.store, hours=6)   # aliasen aktiva
        self.assertIn("inga", rapport)

    def test_context_linked_short_names_are_not_reported_as_gaps(self):
        """Detektorn måste köra SAMMA regler som länken. Kortnamnen nedan
        länkar sedan 2026-08-06; att lista dem vore brus som skickar Saman
        på aliasjakt efter par som redan fungerar."""
        self._fs("Paide (Est)", "SK Rapid (Aut)")
        self._sofa("Paide Linnameeskond", "SK Rapid Wien")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            self.assertIn("inga", format_link_gaps(self.store, hours=6))

    def test_different_matches_at_the_same_kickoff_are_not_reported(self):
        """Två skilda matcher med samma avspark får inte bli brus."""
        self._fs("Lyn", "Sogndal")
        self._sofa("Egersund", "Sandnes Ulf")
        rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("inga", rapport)

    def test_country_label_does_not_sink_similarity(self):
        """Flashscores landsetikett fick inte gömma ett identiskt namn.

        `Sparta Prague (Cze)` ↔ `Sparta Praha` mätt på rå `norm_team` gav 0,65
        mot tröskeln 0,72 och föll ur åtgärdslistan; strippat är det 0,80.
        Detektorn ska mäta på samma normalisering som länken.
        """
        self._fs("Sparta Prague (Cze)", "Kairat Almaty (Kaz)")
        self._sofa("Sparta Praha", "Kairat Almaty")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("Sparta Prague (Cze)", rapport)
        self.assertIn("likhet", rapport)

    def test_orphan_in_an_otherwise_linked_bucket_is_reported(self):
        """`Lyon` ↔ `Olympique Lyonnais` liknar inte varandra (0,36).

        Namnlikhet kan aldrig hitta det paret. Att båda providrarna har exakt
        en rad kvar utan motpart i en hink som ANNARS länkar är beviset.
        """
        self._fs("Levski Sofia", "Kairat Almaty")
        self._sofa("Levski Sofia", "Kairat Almaty")
        self._fs("Lyon", "Sparta Praha")
        self._sofa("Olympique Lyonnais", "Sparta Praha")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            rapport = format_link_gaps(self.store, hours=6)
        self.assertIn("ensam", rapport)
        self.assertIn("Olympique Lyonnais", rapport)
        self.assertNotIn("Kairat", rapport)

    def test_different_kickoff_is_never_paired(self):
        self._fs("Hodd", "Moss", start="2026-08-02T15:00:00Z")
        self._sofa("Hødd IL", "Moss FK", start="2026-08-02T19:00:00Z")
        with patch.object(live_radar, "LIVE_TEAM_ALIASES", {}):
            self.assertIn("inga", format_link_gaps(self.store, hours=6))


if __name__ == "__main__":
    unittest.main()
