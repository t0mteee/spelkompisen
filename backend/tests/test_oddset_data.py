import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset_data
from app.storage import Storage


def _event(event_id: int = 123) -> dict:
    return {
        "id": event_id,
        "status": {"type": "finished"},
        "startTimestamp": 1_720_000_000,
        "homeTeam": {"name": "Montreal"},
        "awayTeam": {"name": "Atlanta United"},
        "homeScore": {"current": 6, "normaltime": 2},
        "awayScore": {"current": 7, "normaltime": 2},
    }


class FootballDataParserTests(unittest.TestCase):
    def test_classic_european_file_is_normalized_with_corners(self) -> None:
        text = (
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HC,AC\n"
            "E0,18/05/2025,Arsenal,Newcastle,1,0,8,3\n"
        )

        rows = oddset_data._fd_result_rows(text, "premier_league")

        self.assertEqual(1, len(rows))
        self.assertEqual("2025-05-18", rows[0]["date"])
        self.assertEqual(("arsenal", "newcastle"),
                         (rows[0]["home"], rows[0]["away"]))
        self.assertEqual((1, 0), (rows[0]["hg"], rows[0]["ag"]))
        self.assertEqual((8.0, 3.0), (rows[0]["cor_h"], rows[0]["cor_a"]))

    def test_current_country_file_keeps_existing_semantics(self) -> None:
        text = (
            "Season,Date,Home,Away,HG,AG\n"
            "2026,01/04/2026,Hammarby,Malmo FF,2,1\n"
        )

        rows = oddset_data._fd_result_rows(text, "allsvenskan")

        self.assertEqual(1, len(rows))
        self.assertEqual("malmo", rows[0]["away"])

    def test_wrong_division_in_the_file_is_rejected(self) -> None:
        """football-data serverade skotsk Championship på La Ligas URL.

        `mmz4281/2627/SP1.csv` gav 2026-08-07 Ayr–Arbroath med `Div=SC1`, och
        fem sådana matcher hamnade i oddset_results som la_liga. Filen
        avslöjar sig själv — vi ska lita på innehållet, inte på URL:en.
        """
        text = (
            "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
            "SC1,01/08/2026,Ayr,Arbroath,2,0\n"
            "SP1,15/08/2026,Girona,Vallecano,1,3\n"
        )

        rows = oddset_data._fd_result_rows(text, "la_liga", div="SP1")

        self.assertEqual(1, len(rows))
        self.assertEqual("girona", rows[0]["home"])

    def test_country_files_without_div_are_untouched_by_the_guard(self) -> None:
        # Landsfilerna har Country/League i stället för Div och är enligiga.
        text = (
            "Season,Date,Home,Away,HG,AG\n"
            "2026,01/04/2026,Hammarby,Malmo FF,2,1\n"
        )

        rows = oddset_data._fd_result_rows(text, "allsvenskan", div="SWE")

        self.assertEqual(1, len(rows))

    def test_zero_xg_is_treated_as_a_missing_measurement(self) -> None:
        """En nolla ser ut som ett mätvärde — samma fel som fällde livekällan.

        Effektiva mål är 0,65·xG + 0,35·mål, så en falsk nolla gör en
        2–2-match till 0,7–0,7 i modellen.
        """
        # Båda exakt noll i en spelad match: saknad mätning.
        self.assertFalse(oddset_data._xg_is_measured(
            {"hg": 2, "ag": 2, "xg_h": 0.0, "xg_a": 0.0}))
        # Även i en 0–0: paret bär ingen information.
        self.assertFalse(oddset_data._xg_is_measured(
            {"hg": 0, "ag": 0, "xg_h": 0.0, "xg_a": 0.0}))
        # Ett lag som GJORDE MÅL kan inte ha xG 0,00 — varje mål är ett avslut.
        self.assertFalse(oddset_data._xg_is_measured(
            {"hg": 1, "ag": 0, "xg_h": 0.0, "xg_a": 1.39}))

    def test_scoreless_side_with_zero_xg_is_kept(self) -> None:
        # Osannolikt men möjligt. Att radera på osannolikhet i stället för
        # omöjlighet vore att tycka till om datat.
        self.assertTrue(oddset_data._xg_is_measured(
            {"hg": 3, "ag": 0, "xg_h": 1.32, "xg_a": 0.0}))
        self.assertTrue(oddset_data._xg_is_measured(
            {"hg": 1, "ag": 2, "xg_h": 0.9, "xg_a": 1.8}))

    def test_season_urls_roll_forward_without_guessing_future_years(self) -> None:
        urls = oddset_data._fd_season_urls(
            "E0", oddset_data.dt.date(2026, 7, 23))

        self.assertTrue(urls[-1].endswith("/2627/E0.csv"))
        self.assertTrue(urls[0].endswith("/2425/E0.csv"))


class SofaIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_transient_statistics_error_is_retried(self) -> None:
        event = _event()
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=RuntimeError("temporary")):
            completed = oddset_data._ingest_event(self.store, "mls", event)

        self.assertFalse(completed)
        self.assertIsNone(self.store.meta_get("oddset_sofa_seen:123"))
        retry = json.loads(self.store.meta_get("oddset_sofa_retry:123"))
        self.assertEqual(1, retry["attempts"])
        self.assertEqual(1, len(self.store.oddset_results("mls")))

        statistics = {"statistics": [{"groups": [{"statisticsItems": [
            {"name": "Expected goals", "home": "1.4", "away": "0.9"},
            {"name": "Corner kicks", "home": "6", "away": "3"},
        ]}]}]}
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get", return_value=statistics):
            completed = oddset_data._ingest_event(self.store, "mls", event)

        self.assertTrue(completed)
        self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:123"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:123"))
        row = self.store.oddset_results("mls")[0]
        self.assertEqual(2, row["hg"])
        self.assertEqual(2, row["ag"])
        self.assertAlmostEqual(1.4, row["xg_h"])
        self.assertAlmostEqual(0.9, row["xg_a"])

    def test_successful_but_xg_empty_response_is_retried(self) -> None:
        """Djurgården–Västerås 2026-08-03 markerades `seen` när Sofa gav
        ett lyckat men ännu xG-tomt svar. När 3,71–1,32 publicerades senare
        frågade v4 aldrig igen. `seen` får bara stoppa ett komplett xG-par."""
        event = _event(456)
        empty = {"statistics": [{"groups": [{"statisticsItems": [
            {"name": "Corner kicks", "home": "5", "away": "1"},
        ]}]}]}
        complete = {"statistics": [{"groups": [{"statisticsItems": [
            {"name": "Expected goals", "home": "3.71", "away": "1.32"},
            {"name": "Corner kicks", "home": "5", "away": "1"},
        ]}]}]}
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=[empty, complete]) as source:
            self.assertTrue(oddset_data._ingest_event(
                self.store, "allsvenskan", event))
            self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:456"))
            retry = json.loads(self.store.meta_get("oddset_sofa_retry:456"))
            self.assertEqual("missing_xg_in_successful_response", retry["error"])
            self.assertTrue(oddset_data._ingest_event(
                self.store, "allsvenskan", event))

        self.assertEqual(2, source.call_count)
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual((3.71, 1.32), (row["xg_h"], row["xg_a"]))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:456"))

        with mock.patch.object(oddset_data, "_sofa_get") as source:
            self.assertFalse(oddset_data._ingest_event(
                self.store, "allsvenskan", event))
            source.assert_not_called()

    def test_normaltime_excludes_penalty_shootout(self) -> None:
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get", return_value={}):
            self.assertTrue(oddset_data._ingest_event(self.store, "mls", _event(456)))

        row = self.store.oddset_results("mls")[0]
        self.assertEqual((2, 2), (row["hg"], row["ag"]))

    def test_missing_statistics_404_is_retried_but_410_is_terminal(self) -> None:
        class MissingStatistics(RuntimeError):
            response = type("Response", (), {"status_code": 404})()

        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=MissingStatistics("missing")):
            completed = oddset_data._ingest_event(self.store, "mls", _event(789))

        self.assertTrue(completed)
        self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:789"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_stats_terminal:789"))
        retry = json.loads(self.store.meta_get("oddset_sofa_retry:789"))
        self.assertEqual(404, retry["status"])

        class GoneStatistics(RuntimeError):
            response = type("Response", (), {"status_code": 410})()

        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=GoneStatistics("gone")):
            self.assertTrue(oddset_data._ingest_event(
                self.store, "mls", _event(789)))
        self.assertEqual("410", self.store.meta_get(
            "oddset_sofa_stats_terminal:789"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:789"))
        with mock.patch.object(oddset_data, "_sofa_get") as source:
            self.assertFalse(oddset_data._ingest_event(
                self.store, "mls", _event(789)))
            source.assert_not_called()

    def test_refresh_checks_older_page_when_newest_is_already_known(self) -> None:
        """En fullständigt känd sida 0 bevisar inte att sida 1 saknar luckor."""
        pages = {
            "/unique-tournament/242/season/99/events/last/0": {
                "events": [_event(1)]},
            "/unique-tournament/242/season/99/events/last/1": {
                "events": [_event(2)]},
            "/unique-tournament/242/season/99/events/last/2": {"events": []},
        }
        with mock.patch.object(oddset_data, "SOFA_UT", {"mls": 242}), \
                mock.patch.object(oddset_data, "SOFA_MAX_PAGES", 3), \
                mock.patch.object(oddset_data, "_sofa_season", return_value=99), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=lambda path: pages[path]) as source, \
                mock.patch.object(oddset_data, "_ingest_event",
                                  side_effect=[False, True]) as ingest:
            result = oddset_data.refresh_xg(self.store, force=True)

        self.assertEqual(1, result["mls"])
        self.assertEqual(2, ingest.call_count)
        self.assertEqual(3, source.call_count)


class SofaSeasonCacheTests(unittest.TestCase):
    def test_legacy_cache_without_tournament_id_is_refetched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            fixed = oddset_data.dt.datetime(
                2026, 7, 17, 8, tzinfo=oddset_data.dt.timezone.utc)
            try:
                store.meta_set("oddset_sofa_season:obosligaen",
                               "97377|2026-07-17T07:00:00+00:00")
                with mock.patch.object(oddset_data, "_now", return_value=fixed), \
                        mock.patch.object(oddset_data, "_sofa_get", return_value={
                            "seasons": [{"id": 87867, "name": "1st Division 2026"}]
                        }) as source:
                    season = oddset_data._sofa_season(store, "obosligaen")

                self.assertEqual(87867, season)
                source.assert_called_once_with("/unique-tournament/22/seasons")
                self.assertTrue(store.meta_get(
                    "oddset_sofa_season:obosligaen").startswith("22|87867|"))
            finally:
                store.close()


class AbsenceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_absence_entry_keeps_provider_identity_and_maps_suspensions(self) -> None:
        raw = {
            "player": {"id": 794516, "name": "Yohei Takaoka", "position": "G"},
            "reason": 13, "description": "red_card_suspension",
            "expectedEndDate": "2026-07-17T03:30:00+00:00",
        }

        entry = oddset_data._absence_entry(raw)

        self.assertEqual(794516, entry["player_id"])
        self.assertEqual("G", entry["position"])
        self.assertEqual(13, entry["reason_code"])
        self.assertEqual("avstängd", entry["reason"])
        self.assertEqual("red_card_suspension", entry["description"])
        self.assertEqual("annat", oddset_data._absence_entry(
            {"player": {"name": "Other"}, "reason": 0,
             "description": "other"})["reason"])

    def test_sofa_absence_link_requires_start_and_unique_candidate(self) -> None:
        from app.oddset import _team_sim

        match = {"home": "Inter", "away": "Milan",
                 "start": "2026-07-17T02:30:00Z"}
        exact = {
            "id": 1, "startTimestamp": 1784255400,
            "homeTeam": {"name": "Inter"}, "awayTeam": {"name": "Milan"},
        }
        wrong_time = {
            "id": 2, "startTimestamp": 1784262600,
            "homeTeam": {"name": "Inter"}, "awayTeam": {"name": "Milan"},
        }
        similar_squad = {
            "id": 3, "startTimestamp": 1784255400,
            "homeTeam": {"name": "Inter U23"},
            "awayTeam": {"name": "Milan U23"},
        }
        self.assertEqual(1, oddset_data._sofa_absence_event(
            [wrong_time, exact], match, _team_sim)["id"])
        # Den historiska fuzzy-regeln ger 1,0 även för dessa U23-namn.
        # Unikhetskravet ska därför stänga länken, inte välja första.
        self.assertIsNone(oddset_data._sofa_absence_event(
            [similar_squad, exact], match, _team_sim))
        self.assertIsNone(oddset_data._sofa_absence_event(
            [exact, {**exact, "id": 4}], match, _team_sim))
        self.assertIsNone(oddset_data._sofa_absence_event(
            [{key: value for key, value in exact.items()
              if key != "startTimestamp"}], match, _team_sim))

    def test_refresh_writes_structured_capture_and_latest_payload(self) -> None:
        self.store.oddset_upsert_match({
            "id": "m1", "league": "mls", "home": "Chicago Fire",
            "away": "Vancouver Whitecaps", "start": "2026-07-17T02:30:00Z",
        })
        event_list = {"events": [{
            "id": 15171583, "startTimestamp": 1784255400,
            "homeTeam": {"name": "Chicago Fire"},
            "awayTeam": {"name": "Vancouver Whitecaps"},
        }]}
        lineup = {"confirmed": False, "home": {"missingPlayers": []}, "away": {
            "missingPlayers": [{
                "player": {"id": 794516, "name": "Yohei Takaoka", "position": "G"},
                "reason": 13, "description": "red_card_suspension",
            }]}}
        statistics = {"statistics": {"appearances": 13, "rating": 6.91}}

        def source(path: str):
            if "/events/next/" in path:
                return event_list
            if path == "/event/15171583/lineups":
                return lineup
            if path.startswith("/player/794516/"):
                return statistics
            raise AssertionError(path)

        fixed_now = oddset_data.dt.datetime(
            2026, 7, 16, 10, 0, tzinfo=oddset_data.dt.timezone.utc)
        with mock.patch.object(oddset_data, "_now", return_value=fixed_now), \
                mock.patch.object(oddset_data, "_sofa_season", return_value=86668), \
                mock.patch.object(oddset_data, "_sofa_get", side_effect=source), \
                mock.patch.object(oddset_data.time, "sleep"):
            result = oddset_data.refresh_absences(self.store, force=True)

        self.assertEqual({"checked": 1, "found": 1,
                          "unavailable": 0}, result)
        latest = oddset_data.get_absences(self.store, ["m1"])["m1"]
        self.assertEqual("sofa:794516", latest["away"][0]["player_id"])
        self.assertEqual("G", latest["away"][0]["position"])
        self.assertEqual("sofascore", latest["provider"])
        self.assertEqual(1, len(self.store.oddset_absence_history("m1")))

    def test_only_verified_404_is_recorded_as_unavailable(self) -> None:
        self.store.oddset_upsert_match({
            "id": "m1", "league": "mls", "home": "Chicago Fire",
            "away": "Vancouver Whitecaps", "start": "2026-07-17T02:30:00Z",
        })
        event_list = {"events": [{
            "id": 15171583, "startTimestamp": 1784255400,
            "homeTeam": {"name": "Chicago Fire"},
            "awayTeam": {"name": "Vancouver Whitecaps"},
        }]}
        fixed_now = oddset_data.dt.datetime(
            2026, 7, 16, 10, 0, tzinfo=oddset_data.dt.timezone.utc)

        def network_source(path: str):
            if "/events/next/" in path:
                return event_list
            raise RuntimeError("network")

        with mock.patch.object(oddset_data, "_now", return_value=fixed_now), \
                mock.patch.object(oddset_data, "_sofa_season", return_value=86668), \
                mock.patch.object(oddset_data, "_sofa_get", side_effect=network_source), \
                mock.patch.object(oddset_data.time, "sleep"):
            network = oddset_data.refresh_absences(self.store, force=True)
        self.assertEqual(0, network["unavailable"])
        self.assertEqual([], self.store.oddset_absence_history("m1"))

        class MissingLineups(RuntimeError):
            response = type("Response", (), {"status_code": 404})()

        def missing_source(path: str):
            if "/events/next/" in path:
                return event_list
            raise MissingLineups("not published")

        with mock.patch.object(oddset_data, "_now", return_value=fixed_now), \
                mock.patch.object(oddset_data, "_sofa_season", return_value=86668), \
                mock.patch.object(oddset_data, "_sofa_get", side_effect=missing_source), \
                mock.patch.object(oddset_data.time, "sleep"):
            missing = oddset_data.refresh_absences(self.store, force=True)
        self.assertEqual(1, missing["unavailable"])
        self.assertEqual("unavailable",
                         self.store.oddset_absence_history("m1")[0]["status"])


class ClubEloTests(unittest.TestCase):
    CSV = """Rank,Club,Country,Level,Elo,From,To
1,Hammarby,SWE,1,1507.6638,2026-07-13,2026-07-19
2,Brann,NOR,1,1528.4,2026-07-13,2026-07-19
3,Ajax,NED,1,1700,2026-07-13,2026-07-19
4,Bad,SWE,1,not-a-number,2026-07-13,2026-07-19
5,Arsenal,ENG,1,1850.0,2026-07-13,2026-07-19
"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_parser_keeps_provider_intervals_and_filters_countries(self) -> None:
        rows = oddset_data.parse_elo_csv(self.CSV)

        self.assertEqual(3, len(rows))
        self.assertEqual("hammarby", rows[0]["club_key"])
        self.assertAlmostEqual(1507.6638, rows[0]["elo"])
        self.assertEqual("2026-07-19", rows[0]["valid_to"])

    def test_capture_becomes_current_and_history_is_explicit_as_of(self) -> None:
        count = oddset_data.save_elo_capture(
            self.store, "2026-07-16", self.CSV,
            captured_at="2026-07-16T10:00:00Z")

        self.assertEqual(3, count)
        self.assertEqual({"hammarby": 1508, "brann": 1528, "arsenal": 1850},
                         oddset_data.get_elo(self.store))
        self.assertEqual(3, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_elo_history").fetchone()[0])
        self.assertEqual({"hammarby": 1508, "brann": 1528, "arsenal": 1850},
                         oddset_data.get_elo(self.store, "2026-07-16T18:00:00Z"))


class ResultIdentityAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _save_pair(self, date: str) -> None:
        base = {"league": "test", "date": date, "away": "malmo",
                "hg": 2, "ag": 1}
        self.store.oddset_save_result(
            {**base, "home": "djurgardens", "source": "fd"})
        self.store.oddset_save_result({
            **base, "home": "djurgarden", "source": "sofa",
            "xg_h": 1.6, "xg_a": 0.8,
        })

    def test_every_fuzzy_link_is_audited_with_affected_match_count(self) -> None:
        self._save_pair("2026-04-01")
        self._save_pair("2026-04-08")
        audit = {}

        rows = oddset_data.merged_results(self.store, "test", audit=audit)

        self.assertEqual(2, len(rows))
        self.assertEqual(2, audit["fuzzy_links"][0]["matches"])
        self.assertEqual("djurgarden", audit["fuzzy_links"][0]["source_name"])
        self.assertEqual("djurgardens", audit["fuzzy_links"][0]["target_name"])
        self.assertFalse(audit["fuzzy_links"][0]["verified"])

    def test_verified_alias_removes_link_from_fuzzy_audit(self) -> None:
        self._save_pair("2026-04-01")
        self.store.meta_set("oddset_alias:test", json.dumps(
            {"djurgarden": "djurgardens"}))
        audit = {}

        rows = oddset_data.merged_results(self.store, "test", audit=audit)

        self.assertEqual(1, len(rows))
        self.assertEqual([], audit["fuzzy_links"])

    def test_review_band_is_suggested_but_never_auto_merged(self) -> None:
        base = {"league": "test", "date": "2026-11-23", "away": "kongsvinger",
                "hg": 1, "ag": 2}
        self.store.oddset_save_result(
            {**base, "home": "haugesund", "source": "fd"})
        self.store.oddset_save_result(
            {**base, "home": "egersund", "source": "sofa"})
        audit = {}

        rows = oddset_data.merged_results(self.store, "test", audit=audit)

        self.assertEqual(2, len(rows))
        self.assertEqual([], audit["fuzzy_links"])
        suggestion = next(u for u in audit["unmatched"] if u["name"] == "egersund")
        self.assertEqual("haugesund", suggestion["suggestion"])
        self.assertEqual(1, suggestion["matches"])
        self.assertGreaterEqual(suggestion["sim"], 0.55)
        self.assertLess(suggestion["sim"], oddset_data.FUZZY_AUTO_MIN)

    def test_known_false_link_is_audited_as_verified_rejection(self) -> None:
        base = {"league": "eliteserien", "date": "2026-11-23",
                "away": "kongsvinger", "hg": 1, "ag": 2}
        self.store.oddset_save_result(
            {**base, "home": "haugesund", "source": "fd"})
        self.store.oddset_save_result(
            {**base, "home": "egersund", "source": "sofa"})
        audit = {}

        rows = oddset_data.merged_results(
            self.store, "eliteserien", audit=audit)

        self.assertEqual(2, len(rows))
        self.assertNotIn("unmatched", audit)
        self.assertEqual("rejected", audit["rejected_links"][0]["decision"])
        self.assertTrue(audit["rejected_links"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
