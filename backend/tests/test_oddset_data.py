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

    def test_normaltime_excludes_penalty_shootout(self) -> None:
        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get", return_value={}):
            self.assertTrue(oddset_data._ingest_event(self.store, "mls", _event(456)))

        row = self.store.oddset_results("mls")[0]
        self.assertEqual((2, 2), (row["hg"], row["ag"]))

    def test_permanent_missing_statistics_does_not_retry_forever(self) -> None:
        class MissingStatistics(RuntimeError):
            response = type("Response", (), {"status_code": 404})()

        with mock.patch.object(oddset_data.time, "sleep"), \
                mock.patch.object(oddset_data, "_sofa_get",
                                  side_effect=MissingStatistics("missing")):
            completed = oddset_data._ingest_event(self.store, "mls", _event(789))

        self.assertTrue(completed)
        self.assertIsNotNone(self.store.meta_get("oddset_sofa_seen:789"))
        self.assertIsNone(self.store.meta_get("oddset_sofa_retry:789"))


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

    def test_refresh_writes_structured_capture_and_latest_payload(self) -> None:
        self.store.oddset_upsert_match({
            "id": "m1", "league": "mls", "home": "Chicago Fire",
            "away": "Vancouver Whitecaps", "start": "2026-07-17T02:30:00Z",
        })
        event_list = {"events": [{
            "id": 15171583, "homeTeam": {"name": "Chicago Fire"},
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

        self.assertEqual({"checked": 1, "found": 1}, result)
        latest = oddset_data.get_absences(self.store, ["m1"])["m1"]
        self.assertEqual(794516, latest["away"][0]["player_id"])
        self.assertEqual("G", latest["away"][0]["position"])
        self.assertEqual(1, len(self.store.oddset_absence_history("m1")))


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
