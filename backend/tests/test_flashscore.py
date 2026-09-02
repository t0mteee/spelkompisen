"""Flashscore som live-radarns primära statistikkälla (2026-08-01).

Fixturerna är avkortade men FORMATTROGNA utdrag ur skarpa svar hämtade
2026-08-01 (Chelsea–Tottenham, id SKg88Q3T) — samma pipe-format, samma
etiketter, samma fältnamn.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import flashscore, live_radar
from app.storage import Storage

NOW = dt.datetime(2026, 8, 1, 11, 5, tzinfo=dt.timezone.utc)
START_AT = (NOW - dt.timedelta(minutes=80)).strftime("%Y-%m-%dT%H:%M:%SZ")
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

    def test_halftime_freezes_the_clock_at_45_instead_of_dropping_it(self):
        """Paus är inte okänd tid — den inträffar per definition efter 45
        spelade minuter. Att censurera där dödade signalen: `radar_signal`
        returnerar `no_clock` utan minut, så en match med stort chansgap föll
        ur "starkt chansgap" i samma sekund domaren blåste av."""
        paus = {"stage": "38", "stage_started_ts": SECOND_HALF_START}
        self.assertEqual(45, flashscore.minute_at(paus, NOW))
        # Pausens längd får ALDRIG läggas på spelad tid.
        senare = NOW + dt.timedelta(minutes=14)
        self.assertEqual(45, flashscore.minute_at(paus, senare))
        # Även utan stadieklocka: paus betyder 45 spelade minuter.
        self.assertEqual(
            45, flashscore.minute_at(
                {"stage": "38", "stage_started_ts": None}, NOW))

    def test_stage_label_marks_only_a_standing_clock(self):
        """Etiketten visas i klockans STÄLLE, så den får bara finnas när
        klockan står stilla — annars hade kortet sagt "1:a halvlek" om en
        match där minuten är sannare. Tabellerna delar källa så de inte kan
        glida isär."""
        self.assertEqual({"38"}, set(flashscore.STAGE_LABEL))
        self.assertEqual(set(flashscore.STAGE_FROZEN_MINUTE),
                         set(flashscore.STAGE_LABEL))
        self.assertNotIn("12", flashscore.STAGE_LABEL)
        self.assertNotIn("13", flashscore.STAGE_LABEL)

    def test_stats_read_full_match_only_and_skip_non_numeric(self):
        stats = flashscore.parse_stats(STATS_FEED)
        self.assertEqual(1.76, stats["xg_home"])
        self.assertEqual(0.26, stats["xg_away"])
        self.assertEqual(2.51, stats["xgot_home"])
        self.assertEqual(11, stats["shots_home"])
        self.assertEqual(4, stats["shots_on_home"])
        self.assertEqual(4, stats["big_chances_home"])
        self.assertEqual(9, stats["shots_inside_home"])
        # Bollinnehav ÄR måttet och läses som andel (2026-08-06).
        self.assertEqual(42.0, stats["possession_home"])
        self.assertEqual(58.0, stats["possession_away"])
        # Passningar rapporteras som "85% (271/319)" — där är procenten en
        # härledd kvot, inte observationen. Den läses fortfarande inte.
        self.assertNotIn("passes_home", stats)
        self.assertIsNone(flashscore._share("85% (271/319)"))
        self.assertIsNone(flashscore._f("42%"))

    def test_half_section_never_overwrites_the_full_match_value(self):
        self.assertEqual(1.76, flashscore.parse_stats(STATS_FEED)["xg_home"])

    def test_empty_stats_feed_yields_nothing_not_zeroes(self):
        self.assertEqual({}, flashscore.parse_stats("SE÷Match¬~SF÷Top stats¬"))

    def test_toppligor_och_besta_har_explicit_live_mapping(self):
        expected = {
            "ENGLAND: Premier League": "premier_league",
            "ENGLAND: Championship": "championship",
            "ITALY: Serie A": "serie_a",
            "SPAIN: LaLiga": "la_liga",
            "GERMANY: Bundesliga": "bundesliga",
            "ICELAND: Besta deild karla": "bestadeild",
            "DENMARK: Superliga": "danish_superliga",
            "BELGIUM: Jupiler Pro League": "belgian_pro_league",
            "PORTUGAL: Liga Portugal": "primeira_liga",
            "BOLIVIA: Division Profesional": "bolivian_primera",
        }
        for provider_name, league in expected.items():
            self.assertEqual(league, flashscore.LEAGUE_NAMES[provider_name])


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

    def test_unstructured_empty_body_is_not_a_valid_empty_live_list(self):
        response = Mock()
        response.headers = {}
        response.text = ""
        response.raise_for_status = Mock()
        with patch.object(flashscore.httpx.Client, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "strukturhuvud"):
                flashscore.Flashscore().matches()

    def test_truncated_za_header_is_not_a_valid_empty_live_list(self):
        response = Mock()
        response.headers = {}
        response.text = "ZA÷SWEDEN: Allsvenskan¬ZEE÷def¬"
        response.raise_for_status = Mock()
        with patch.object(flashscore.httpx.Client, "get", return_value=response):
            with self.assertRaisesRegex(ValueError, "strukturhuvud"):
                flashscore.Flashscore().matches()

    def test_sa_header_without_matches_is_a_valid_empty_live_list(self):
        response = Mock()
        response.headers = {}
        response.text = "SA÷1¬"
        response.raise_for_status = Mock()
        with patch.object(flashscore.httpx.Client, "get", return_value=response):
            rows, _observed_at = flashscore.Flashscore().matches()
        self.assertEqual([], rows)


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

    def test_score_and_stats_outside_consistency_guard_are_not_saved(self):
        match = {
            "flashscore_id": "SKEW1", "league": "allsvenskan",
            "tournament": "SWEDEN: Allsvenskan", "home": "Hammarby",
            "away": "AIK", "start_ts": MATCH_START, "stage": "12",
            "stage_started_ts": MATCH_START, "home_score": 0,
            "away_score": 0,
        }

        class FakeFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): return [match], NOW
            def stats(self, _match_id):
                return flashscore.parse_stats(STATS_FEED), (
                    NOW + dt.timedelta(seconds=flashscore.MAX_SCORE_STATS_SKEW_S + 1))

        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore()):
            report = flashscore.collect(self.store, known_matches=[])
        # Statistiken är FÄRSK — bara dagsfeedens ställning är gammal. Utan
        # summary-feed (faket saknar den) slopas ställningen men raden och
        # minuten sparas; ingen gammal ställning lagras.
        self.assertEqual(1, report["saved"])
        self.assertTrue(any("klocka slopad" in e for e in report["partial_errors"]))
        capture = self.store.live_flashscore_captures()[0]
        # MINUTEN överlever: den härleds ur stadiets statiska starttid och
        # ruttnar inte med feedens cacheålder. Bara ställningen gör det.
        self.assertIsNotNone(capture["minute"])
        self.assertIsNone(capture["home_score"])
        self.assertIsNone(capture["away_score"])
        self.assertIsNotNone(capture["shots_home"], "statistiken ska finnas kvar")

    def _stale_feed_fake(self, summary_result=None, summary_raises=False,
                         summary_age_s=5):
        """Dagsfeed med gammal ställning + valfri summary-feed."""
        match = {
            "flashscore_id": "SUR1", "league": "allsvenskan",
            "tournament": "SWEDEN: Allsvenskan", "home": "Hammarby",
            "away": "AIK", "start_ts": MATCH_START, "stage": "12",
            "stage_started_ts": MATCH_START, "home_score": 0,
            "away_score": 0,
        }
        stats_at = NOW + dt.timedelta(
            seconds=flashscore.MAX_SCORE_STATS_SKEW_S + 100)

        class FakeFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): return [dict(match)], NOW
            def stats(self, _match_id):
                return flashscore.parse_stats(STATS_FEED), stats_at
            def summary(self, _match_id):
                if summary_raises:
                    raise RuntimeError("nere")
                return summary_result, stats_at - dt.timedelta(
                    seconds=summary_age_s)

        return FakeFlashscore()

    def test_stale_day_feed_score_is_rescued_from_summary(self):
        """Lyn 3–0 visades som 'resultat saknas' trots att Flashscore hade
        målen — dagsfeeden var CDN-fryst. `df_sur` är sekundfärsk och räddar
        ställningen; minuten behålls när stadiet är oförändrat."""
        fake = self._stale_feed_fake(
            summary_result={"home_score": 3, "away_score": 0, "stage": "12"})
        with patch.object(flashscore, "Flashscore", return_value=fake):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertEqual(1, report["saved"])
        capture = self.store.live_flashscore_captures()[0]
        self.assertEqual(3, capture["home_score"])
        self.assertEqual(0, capture["away_score"])
        self.assertIsNotNone(capture["minute"])

    def test_stage_change_in_summary_freezes_the_minute_at_halftime(self):
        """Halvtid: dagsfeeden tror fortfarande '1:a halvlek' och minuten
        tickade till 46–47' i UI:t. Summaryns stadium avslöjar bytet.

        Klockan får inte ticka vidare i fel stadium — men svaret är att FRYSA
        den vid pausens kända spelade tid, inte att kasta den. Att censurera
        gjorde `radar_signal` till `no_clock`, och matchen föll ur "starkt
        chansgap" just när gapet var mest intressant (2026-08-06).
        """
        fake = self._stale_feed_fake(
            summary_result={"home_score": 2, "away_score": 1, "stage": "38"})
        with patch.object(flashscore, "Flashscore", return_value=fake):
            flashscore.collect(self.store, known_matches=[])
        capture = self.store.live_flashscore_captures()[0]
        self.assertEqual(2, capture["home_score"])
        self.assertEqual(45, capture["minute"], "paus = 45 spelade minuter")
        self.assertEqual("Paus", capture["stage_label"])

    def test_unusable_summary_falls_back_to_score_drop(self):
        for fake in (self._stale_feed_fake(summary_raises=True),
                     self._stale_feed_fake(summary_result=None),
                     self._stale_feed_fake(
                         summary_result={"home_score": 1, "away_score": 0,
                                         "stage": "12"},
                         summary_age_s=flashscore.MAX_SCORE_STATS_SKEW_S + 200)):
            with patch.object(flashscore, "Flashscore", return_value=fake):
                report = flashscore.collect(self.store, known_matches=[])
            capture = self.store.live_flashscore_captures()[-1]
            self.assertIsNone(capture["home_score"])
            self.assertIsNotNone(capture["minute"])
            self.assertTrue(
                any("klocka slopad" in e or "summary" in e
                    for e in report["partial_errors"]))

    def test_stale_stats_are_discarded_entirely(self):
        """Motsatt riktning: när STATISTIKEN är för gammal finns inget att
        rädda — då hjälper ingen lånad klocka."""
        match = {
            "flashscore_id": "OLD1", "league": "allsvenskan",
            "tournament": "SWEDEN: Allsvenskan", "home": "Hammarby",
            "away": "AIK", "start_ts": MATCH_START, "stage": "12",
            "stage_started_ts": MATCH_START, "home_score": 0,
            "away_score": 0,
        }

        class FakeFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): return [match], NOW
            def stats(self, _match_id):
                return flashscore.parse_stats(STATS_FEED), (
                    NOW - dt.timedelta(
                        seconds=flashscore.MAX_STALE_STATS_SKEW_S + 1))

        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore()):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertEqual(0, report["saved"])
        self.assertEqual([], self.store.live_flashscore_captures())

    def test_guard_is_directional(self):
        """De två feedarna är CDN-cachade oberoende, så |skillnaden| blandade
        ihop cachejitter med verklig inkoherens. Bara riktningen där
        ställningen är GAMMAL kan fabricera 'hög xG men inget mål'."""
        # Farlig riktning: statistiken observerad efter ställningen.
        self.assertTrue(flashscore.skew_rejected(
            flashscore.MAX_SCORE_STATS_SKEW_S + 1))
        # Konservativ riktning: ställningen nyare än statistiken. Ett mål i den
        # nyare ställningen kan bara krympa gapet, aldrig skapa ett.
        self.assertFalse(flashscore.skew_rejected(-48))
        self.assertFalse(flashscore.skew_rejected(
            -flashscore.MAX_STALE_STATS_SKEW_S))
        # Men en riktigt gammal statrad släpps inte igenom heller.
        self.assertTrue(flashscore.skew_rejected(
            -flashscore.MAX_STALE_STATS_SKEW_S - 1))
        self.assertLess(flashscore.MAX_SCORE_STATS_SKEW_S,
                        flashscore.MAX_STALE_STATS_SKEW_S,
                        "den farliga riktningen måste ha den snävare gränsen")

    def test_conservative_skew_is_saved(self):
        """Nordic United 2026-08-02: skew −48 s kastades och FotMob tog kortet
        trots att Flashscore hade statistik."""
        match = {
            "flashscore_id": "SKEW2", "league": "allsvenskan",
            "tournament": "SWEDEN: Allsvenskan", "home": "Hammarby",
            "away": "AIK", "start_ts": MATCH_START, "stage": "12",
            "stage_started_ts": MATCH_START, "home_score": 0,
            "away_score": 0,
        }

        class FakeFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): return [match], NOW
            def stats(self, _match_id):
                return flashscore.parse_stats(STATS_FEED), (
                    NOW - dt.timedelta(seconds=48))

        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore()):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertEqual(1, report["saved"])
        self.assertEqual([], report["partial_errors"])

    def test_roster_refresh_updates_metadata_for_all_remaining_matches(self):
        def row(match_id, score):
            return {
                "flashscore_id": match_id, "league": "allsvenskan",
                "tournament": "SWEDEN: Allsvenskan", "home": f"Home {match_id}",
                "away": f"Away {match_id}", "start_ts": MATCH_START,
                "stage": "12", "stage_started_ts": MATCH_START,
                "home_score": score, "away_score": 0,
            }

        class FakeFlashscore:
            def __init__(self): self.match_calls = 0
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self):
                self.match_calls += 1
                if self.match_calls == 1:
                    return [row("A", 0), row("B", 0)], NOW
                return ([row("A", 0), row("B", 1)],
                        NOW + dt.timedelta(seconds=22))
            def stats(self, match_id):
                seconds = 21 if match_id == "A" else 23
                return (flashscore.parse_stats(STATS_FEED),
                        NOW + dt.timedelta(seconds=seconds))

        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore()):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertEqual(2, report["saved"])
        rows = {row["flashscore_id"]: row
                for row in self.store.live_flashscore_captures()}
        self.assertEqual(1, rows["B"]["home_score"],
                         "andra matchen måste använda den förnyade rostern")

    def test_valid_empty_list_marks_previous_flashscore_match_as_ended(self):
        match = {
            "flashscore_id": "END1", "league": "allsvenskan",
            "tournament": "SWEDEN: Allsvenskan", "home": "Hammarby",
            "away": "AIK", "start_ts": MATCH_START, "stage": "12",
            "stage_started_ts": MATCH_START, "home_score": 0,
            "away_score": 0,
        }

        class FakeFlashscore:
            def __init__(self, rows, observed):
                self.rows, self.observed = rows, observed
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): return self.rows, self.observed
            def stats(self, _match_id):
                return flashscore.parse_stats(STATS_FEED), self.observed

        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore(
                [match], NOW)):
            flashscore.collect(self.store, known_matches=[])
        with patch.object(flashscore, "Flashscore", return_value=FakeFlashscore(
                [], NOW + dt.timedelta(minutes=2))):
            flashscore.collect(self.store, known_matches=[])
        presence = json.loads(self.store.meta_get(flashscore.PRESENCE_KEY))
        self.assertEqual([], presence["active_ids"])
        self.assertIn("END1", presence["ended_at"])
        health = next(row for row in self.store.oddset_source_health()
                      if row["source"] == "flashscore" and
                      row["scope"] == "live")
        self.assertTrue(health["ok"])

    def test_failed_listing_records_red_health_without_ending_matches(self):
        from app.live_radar import record_presence
        record_presence(self.store, flashscore.PRESENCE_KEY, ["KEEP1"],
                        NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))

        class BrokenFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self): raise RuntimeError("feed unavailable")

        with patch.object(flashscore, "Flashscore",
                          return_value=BrokenFlashscore()):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertIn("RuntimeError", report["error"])
        presence = json.loads(self.store.meta_get(flashscore.PRESENCE_KEY))
        self.assertEqual(["KEEP1"], presence["active_ids"])
        health = next(row for row in self.store.oddset_source_health()
                      if row["source"] == "flashscore")
        self.assertFalse(health["ok"])

    def test_truncated_za_roster_is_red_without_ending_matches(self):
        live_radar.record_presence(
            self.store, flashscore.PRESENCE_KEY, ["KEEP1"],
            NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
        response = Mock()
        response.headers = {}
        response.text = "ZA÷SWEDEN: Allsvenskan¬ZEE÷def¬"
        response.raise_for_status = Mock()
        with patch.object(flashscore.httpx.Client, "get",
                          return_value=response), \
                patch.object(flashscore, "_now", return_value=NOW):
            report = flashscore.collect(self.store, known_matches=[])

        self.assertFalse(report["health_ok"])
        presence = json.loads(self.store.meta_get(flashscore.PRESENCE_KEY))
        self.assertEqual(["KEEP1"], presence["active_ids"])
        self.assertNotIn("KEEP1", presence["ended_at"])
        health = next(row for row in self.store.oddset_source_health()
                      if row["source"] == "flashscore")
        self.assertFalse(health["ok"])

    def test_partial_stats_failure_is_not_green_in_health_or_payload(self):
        def row(match_id, home):
            return {
                "flashscore_id": match_id, "league": "allsvenskan",
                "tournament": "SWEDEN: Allsvenskan", "home": home,
                "away": "Away", "start_ts": MATCH_START, "stage": "12",
                "stage_started_ts": MATCH_START, "home_score": 0,
                "away_score": 0,
            }

        class PartialFlashscore:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self):
                return [row("OK", "OK"), row("FAIL", "FAIL")], NOW
            def stats(self, match_id):
                if match_id == "FAIL":
                    raise RuntimeError("stats unavailable")
                return flashscore.parse_stats(STATS_FEED), NOW

        with patch.object(flashscore, "Flashscore",
                          return_value=PartialFlashscore()), \
                patch.object(flashscore, "_now", return_value=NOW):
            report = flashscore.collect(self.store, known_matches=[])
        self.assertEqual(1, report["saved"])
        self.assertEqual(1, report["stats_ok"])
        self.assertFalse(report["health_ok"])
        health = next(row for row in self.store.oddset_source_health()
                      if row["source"] == "flashscore")
        self.assertFalse(health["ok"])
        self.assertEqual(2, health["event_count"])
        self.assertIn("FAIL: RuntimeError", health["error"])
        payload_health = next(
            row for row in live_radar.payload(self.store, now=NOW)[
                "source_health"]
            if row["source"] == "flashscore")
        self.assertFalse(payload_health["ok"])
        self.assertIn("RuntimeError", payload_health["error"])


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
            "start_at": START_AT,
            "home": "Hammarby", "away": "AIK", "status": "2nd half",
            "minute": 60, "home_score": 0, "away_score": 0, **stats})

    def _fotmob(self, **stats):
        self.store.live_fotmob_save({
            "fotmob_id": 7001, "captured_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capture_version": __import__(
                "app.fotmob", fromlist=["x"]).CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "start_at": START_AT,
            "home": "Hammarby", "away": "AIK", "minute": 60,
            "home_score": 0, "away_score": 0, **stats})

    def _flash(self, match_id="FS1", **stats):
        self.store.live_flashscore_save({
            "flashscore_id": match_id,
            "captured_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "capture_version": flashscore.CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "start_at": START_AT,
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

    def test_partial_flashscore_never_hides_complete_fotmob_proxy(self):
        """Källvalet bedömer fälttäckning, inte hur dramatiska talen är."""
        self._sofa()
        self._fotmob(big_chances_home=0, big_chances_away=0,
                     shots_on_home=0, shots_on_away=0,
                     shots_inside_home=0, shots_inside_away=0)
        self._flash(big_chances_home=99)  # högt men ensidigt/partiellt
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
