"""Flashscore som live-radarns primära statistikkälla (2026-08-01).

Fixturerna är avkortade men FORMATTROGNA utdrag ur skarpa svar hämtade
2026-08-01 (Chelsea–Tottenham, id SKg88Q3T) — samma pipe-format, samma
etiketter, samma fältnamn.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import flashscore, live_radar
from app.storage import Storage

NOW = dt.datetime(2026, 8, 1, 11, 5, tzinfo=dt.timezone.utc)
# Stadiets starttid: 2:a halvlek startade 42 min före NOW ⇒ minut 45+42 = 87.
SECOND_HALF_START = int((NOW - dt.timedelta(minutes=42)).timestamp())
MATCH_START = int((NOW - dt.timedelta(minutes=80)).timestamp())

DAY_FEED = (
    "SA÷1¬~ZA÷WORLD: Club Friendly¬ZEE÷abc¬"
    f"~AA÷SKg88Q3T¬AB÷2¬AC÷13¬AD÷{MATCH_START}¬AE÷Chelsea (Eng)¬"
    f"AF÷Tottenham (Eng)¬AG÷1¬AH÷1¬AO÷{SECOND_HALF_START}¬"
    "~ZA÷SWEDEN: Allsvenskan¬ZEE÷def¬"
    f"~AA÷ALLSV111¬AB÷2¬AC÷12¬AD÷{MATCH_START}¬AE÷Hammarby¬AF÷AIK¬"
    f"AG÷0¬AH÷0¬AO÷{int((NOW - dt.timedelta(minutes=30)).timestamp())}¬"
    "~ZA÷CHINA: Jia League¬ZEE÷ghi¬"          # okänd liga → aldrig med
    f"~AA÷OKAND99¬AB÷2¬AC÷12¬AD÷{MATCH_START}¬AE÷Dalian¬AF÷Shaanxi¬"
    "~ZA÷SWEDEN: Superettan¬ZEE÷jkl¬"
    f"~AA÷EJLIVE1¬AB÷1¬AC÷1¬AD÷{MATCH_START}¬AE÷Örgryte¬AF÷Utsikten¬"
)

STATS_FEED = (
    "SE÷Match¬~SF÷Top stats¬"
    "~SD÷432¬SG÷Expected goals (xG)¬SH÷1.76¬SI÷0.26¬"
    "~SD÷12¬SG÷Ball possession¬SH÷42%¬SI÷58%¬"
    "~SD÷34¬SG÷Total shots¬SH÷11¬SI÷4¬"
    "~SD÷13¬SG÷Shots on target¬SH÷4¬SI÷3¬"
    "~SD÷459¬SG÷Big chances¬SH÷4¬SI÷1¬"
    "~SD÷342¬SG÷Passes¬SH÷85% (271/319)¬SI÷87% (399/457)¬"
    "~SF÷Shots¬"
    "~SD÷499¬SG÷xG on target (xGOT)¬SH÷2.51¬SI÷0.79¬"
    "~SD÷461¬SG÷Shots inside the box¬SH÷9¬SI÷1¬"
    "~SE÷1st Half¬~SF÷Top stats¬"          # halvleksavsnitt läses ALDRIG
    "~SD÷432¬SG÷Expected goals (xG)¬SH÷0.90¬SI÷0.10¬"
)


class ParseTests(unittest.TestCase):
    def test_day_feed_keeps_only_live_matches_in_our_leagues(self):
        rows = flashscore.parse_day_feed(DAY_FEED)
        self.assertEqual(["SKg88Q3T", "ALLSV111"],
                         [r["flashscore_id"] for r in rows])
        self.assertEqual(["friendlies", "allsvenskan"],
                         [r["league"] for r in rows])

    def test_unknown_league_never_inherits_the_previous_key(self):
        rows = flashscore.parse_day_feed(DAY_FEED)
        self.assertNotIn("OKAND99", [r["flashscore_id"] for r in rows])

    def test_match_fields_are_read_verbatim(self):
        row = flashscore.parse_day_feed(DAY_FEED)[0]
        self.assertEqual("Chelsea (Eng)", row["home"])
        self.assertEqual("Tottenham (Eng)", row["away"])
        self.assertEqual(1, row["home_score"])
        self.assertEqual(1, row["away_score"])

    def test_minute_is_derived_from_the_stage_clock(self):
        rows = flashscore.parse_day_feed(DAY_FEED)
        self.assertEqual(87, flashscore.minute_at(rows[0], NOW))   # 45 + 42
        self.assertEqual(30, flashscore.minute_at(rows[1], NOW))   # 1:a halvlek

    def test_unknown_stage_censors_the_clock_instead_of_guessing(self):
        halftime = {"stage": "14", "stage_started_ts": SECOND_HALF_START}
        self.assertIsNone(flashscore.minute_at(halftime, NOW))
        no_clock = {"stage": "13", "stage_started_ts": None}
        self.assertIsNone(flashscore.minute_at(no_clock, NOW))

    def test_stats_read_full_match_only_and_skip_non_numeric(self):
        stats = flashscore.parse_stats(STATS_FEED)
        self.assertEqual(1.76, stats["xg_home"])
        self.assertEqual(0.26, stats["xg_away"])
        self.assertEqual(2.51, stats["xgot_home"])
        self.assertEqual(11, stats["shots_home"])
        self.assertEqual(4, stats["shots_on_home"])
        self.assertEqual(4, stats["big_chances_home"])
        self.assertEqual(9, stats["shots_inside_home"])
        # procent och "85% (271/319)" är inga rena mått
        self.assertNotIn("possession_home", stats)

    def test_half_section_never_overwrites_the_full_match_value(self):
        self.assertEqual(1.76, flashscore.parse_stats(STATS_FEED)["xg_home"])

    def test_empty_stats_feed_yields_nothing_not_zeroes(self):
        self.assertEqual({}, flashscore.parse_stats("SE÷Match¬~SF÷Top stats¬"))


class TransportTests(unittest.TestCase):
    def test_unparsable_body_is_a_transport_error_not_a_format_change(self):
        response = Mock()
        response.headers = {"content-encoding": "br"}
        response.text = "\x1f\x8b binärt skräp utan avgränsare"
        with patch.object(flashscore.httpx.Client, "get",
                          return_value=response):
            with self.assertRaises(ValueError) as ctx:
                flashscore.Flashscore().matches()
        self.assertIn("brotli", str(ctx.exception))

    def test_observation_time_subtracts_http_age(self):
        response = Mock()
        response.headers = {"age": "120"}
        response.text = DAY_FEED
        with patch.object(flashscore.httpx.Client, "get",
                          return_value=response), \
                patch.object(flashscore, "_now", return_value=NOW):
            _rows, observed_at = flashscore.Flashscore().matches()
        self.assertEqual(NOW - dt.timedelta(seconds=120), observed_at)


class CollectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        # Träningsmatchen måste finnas i Oddset för att släppas igenom
        self.store.oddset_upsert_match({
            "id": "pin:1", "league": "friendlies",
            "home": "Chelsea", "away": "Tottenham",
            "start": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pinnacle_id": "1", "kambi_id": "2"})

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _run(self, stats_text=STATS_FEED):
        def fake_get(_self, path):
            response = Mock()
            response.headers = {}
            response.text = (DAY_FEED if path.startswith(f"{flashscore.BASE}/f_")
                             else stats_text)
            response.raise_for_status = Mock()
            return response
        with patch.object(flashscore.httpx.Client, "get", fake_get), \
                patch.object(flashscore, "_now", return_value=NOW):
            return flashscore.collect(self.store)

    def test_saves_captures_with_own_clock_and_score(self):
        report = self._run()
        self.assertEqual(2, report["saved"])
        rows = self.store.live_flashscore_captures()
        chelsea = next(r for r in rows if r["flashscore_id"] == "SKg88Q3T")
        self.assertEqual(1.76, chelsea["xg_home"])
        self.assertEqual(87, chelsea["minute"])
        self.assertEqual(1, chelsea["home_score"])
        self.assertEqual(flashscore.CAPTURE_VERSION, chelsea["capture_version"])

    def test_no_stats_means_no_row_never_zeroes(self):
        report = self._run(stats_text="SE÷Match¬")
        self.assertEqual(0, report["saved"])
        self.assertEqual([], self.store.live_flashscore_captures())

    def test_rerun_is_idempotent_for_the_same_observation(self):
        self._run()
        self._run()
        self.assertEqual(2, len(self.store.live_flashscore_captures()))


class SourceSelectionTests(unittest.TestCase):
    """Flashscore är primär — men DATAKVALITET rankas före källordning."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _sofa(self, **stats):
        self.store.oddset_save_live_capture({
            "event_id": 5001, "captured_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capture_version": live_radar.CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "home": "Hammarby", "away": "AIK", "status": "2nd half",
            "minute": 60, "home_score": 0, "away_score": 0, **stats})

    def _fotmob(self, **stats):
        self.store.live_fotmob_save({
            "fotmob_id": 7001, "captured_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capture_version": __import__(
                "app.fotmob", fromlist=["x"]).CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "home": "Hammarby", "away": "AIK", "minute": 60,
            "home_score": 0, "away_score": 0, **stats})

    def _flash(self, match_id="FS1", **stats):
        self.store.live_flashscore_save({
            "flashscore_id": match_id,
            "captured_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capture_version": flashscore.CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "home": "Hammarby", "away": "AIK", "minute": 60,
            "home_score": 0, "away_score": 0, **stats})

    def test_flashscore_wins_on_equal_quality(self):
        self._sofa(xg_home=1.0, xg_away=0.5)
        self._fotmob(xg_home=1.1, xg_away=0.5)
        self._flash(xg_home=1.2, xg_away=0.5)
        match = live_radar.payload(self.store, now=NOW)["matches"][0]
        self.assertEqual("flashscore", match["signal"]["stats_source"])

    def test_better_fotmob_data_is_never_downgraded(self):
        # FotMob har xG, Flashscore bara skott → FotMob måste bära signalen
        self._sofa()
        self._fotmob(xg_home=1.4, xg_away=0.3)
        self._flash(shots_on_home=6, shots_on_away=1, shots_inside_home=9,
                    shots_inside_away=1)
        match = live_radar.payload(self.store, now=NOW)["matches"][0]
        self.assertEqual("fotmob", match["signal"]["stats_source"])

    def test_flashscore_only_match_gets_its_own_card(self):
        self._flash(match_id="SOLO1", xg_home=2.0, xg_away=0.2)
        payload = live_radar.payload(self.store, now=NOW)
        self.assertEqual(1, len(payload["matches"]))
        match = payload["matches"][0]
        self.assertEqual("flashscore:SOLO1", match["event_id"])
        self.assertEqual("flashscore", match["signal"]["stats_source"])

    def test_linked_flashscore_never_creates_a_duplicate_card(self):
        self._sofa(xg_home=1.0, xg_away=0.5)
        self._flash(xg_home=1.2, xg_away=0.5)
        self.assertEqual(1, len(live_radar.payload(
            self.store, now=NOW)["matches"]))

    def test_coverage_reports_the_bearing_source(self):
        self._flash(xg_home=2.0, xg_away=0.2)
        coverage = live_radar.payload(self.store, now=NOW)["coverage"]
        self.assertEqual(1, coverage["flashscore_xg"])
        self.assertIn("flashscore 1", coverage["by_source"])


if __name__ == "__main__":
    unittest.main()
