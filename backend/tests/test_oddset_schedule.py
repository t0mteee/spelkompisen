import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset_data, oddset_schedule
from app.storage import Storage


def _team(team_id: int, name: str, lat=None, lon=None, detail_at=None) -> dict:
    return {
        "team_id": team_id, "team_key": name.casefold(), "name": name,
        "country_code": "SWE", "sport": "football", "venue_id": team_id * 10,
        "venue_name": f"{name} Arena", "venue_city": name,
        "venue_lat": lat, "venue_lon": lon, "detail_fetched_at": detail_at,
    }


def _event(event_id: int, start_at: str, home: int, away: int,
           tournament_id: int = 40) -> dict:
    return {
        "event_id": event_id, "start_at": start_at, "status": "finished",
        "home_team_id": home, "away_team_id": away,
        "tournament_id": tournament_id,
        "unique_tournament_id": tournament_id,
        "tournament_name": "Allsvenskan" if tournament_id == 40 else "Cup",
        "tournament_slug": "allsvenskan" if tournament_id == 40 else "cup",
        "country_code": "SWE", "home_score": 1, "away_score": 0,
    }


class TeamEventStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_event_is_not_pit_visible_before_first_seen(self) -> None:
        event = _event(11, "2026-07-10T12:00:00Z", 1, 9)
        capture = {"team_id": 1, "captured_at": "2026-07-17T08:00:00Z",
                   "policy_version": oddset_schedule.policy_version(),
                   "page_count": 1, "raw_event_count": 1, "payload_hash": "h1"}

        self.assertEqual(1, self.store.oddset_save_sofa_team_event_capture(
            capture, [event]))
        self.assertEqual([], self.store.oddset_sofa_team_events_as_of(
            1, "2026-07-16T08:00:00Z"))
        self.assertEqual(1, len(self.store.oddset_sofa_team_events_as_of(
            1, "2026-07-18T08:00:00Z")))
        self.assertEqual(0, self.store.oddset_save_sofa_team_event_capture(
            capture, [event]))

    def test_invalid_team_event_rolls_back_capture(self) -> None:
        capture = {"team_id": 1, "captured_at": "2026-07-17T08:00:00Z",
                   "policy_version": oddset_schedule.policy_version(),
                   "page_count": 1, "raw_event_count": 1, "payload_hash": "bad"}

        with self.assertRaises(ValueError):
            self.store.oddset_save_sofa_team_event_capture(
                capture, [_event(12, "2026-07-10T12:00:00Z", 2, 3)])

        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_sofa_team_event_capture").fetchone()[0]
        self.assertEqual(0, count)


class ScheduleFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        observed = "2026-07-10T08:00:00Z"
        self.store.oddset_save_sofa_team(
            _team(1, "home", 59.33, 18.07, observed), observed,
            league="allsvenskan", season_id=1)
        self.store.oddset_save_sofa_team(
            _team(2, "away", 57.71, 11.97, observed), observed,
            league="allsvenskan", season_id=1)

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _capture(self, team_id: int, at: str, events: list[dict]) -> None:
        self.store.oddset_save_sofa_team_event_capture({
            "team_id": team_id, "captured_at": at, "page_count": 1,
            "policy_version": oddset_schedule.policy_version(),
            "raw_event_count": len(events), "payload_hash": f"h-{team_id}-{at}",
        }, events)

    def test_features_count_all_competitions_and_use_base_distance_proxy(self) -> None:
        self._capture(1, "2026-07-13T08:00:00Z", [
            _event(21, "2026-07-08T12:00:00Z", 1, 8),
            _event(22, "2026-07-12T12:00:00Z", 7, 1, tournament_id=999),
        ])
        self._capture(2, "2026-07-15T08:00:00Z", [
            _event(23, "2026-07-14T12:00:00Z", 2, 6),
        ])

        payload = oddset_schedule.features(
            self.store, "allsvenskan", "home", "away",
            "2026-07-17T12:00:00Z", "2026-07-16T12:00:00Z")

        self.assertEqual(120.0, payload["home"]["rest_hours"])
        self.assertEqual(72.0, payload["away"]["rest_hours"])
        self.assertEqual(1, payload["home"]["outside_primary_14d"])
        self.assertEqual(2, payload["home"]["matches_14d"])
        self.assertGreater(payload["travel_proxy"]["base_distance_km"], 390)
        self.assertEqual("club_base_to_club_base", payload["travel_proxy"]["mode"])
        self.assertFalse(payload["travel_proxy"]["neutral_venue_resolved"])
        self.assertEqual([], payload["issues"])

    def test_alias_resolution_is_explicit_and_never_fuzzy(self) -> None:
        observed = "2026-07-10T08:00:00Z"
        self.store.oddset_save_sofa_team(
            _team(3, "halmstads", None, None, observed), observed,
            league="allsvenskan", season_id=1)
        self.store.oddset_save_sofa_team(
            _team(4, "kfum oslo", None, None, observed), observed,
            league="eliteserien", season_id=1)
        self.store.oddset_save_sofa_team(
            _team(5, "hodd il", None, None, observed), observed,
            league="obosligaen", season_id=1)
        self.store.oddset_save_sofa_team(
            _team(6, "hamburger sv", None, None, observed), observed,
            league="bundesliga", season_id=1)

        self.assertEqual(3, oddset_schedule.resolve_team(
            self.store, "allsvenskan", "halmstad")["team_id"])
        self.assertEqual(4, oddset_schedule.resolve_team(
            self.store, "eliteserien", "KFUM")["team_id"])
        self.assertEqual(5, oddset_schedule.resolve_team(
            self.store, "obosligaen", "Hodd")["team_id"])
        self.assertEqual(6, oddset_schedule.resolve_team(
            self.store, "bundesliga", "Hamburg")["team_id"])
        self.assertIsNone(oddset_schedule.resolve_team(
            self.store, "allsvenskan", "halmstad city"))

    def test_rest_keeps_last_match_across_break_longer_than_35_days(self) -> None:
        self._capture(1, "2026-07-02T08:00:00Z", [
            _event(31, "2026-07-01T12:00:00Z", 1, 8),
        ])
        self._capture(2, "2026-07-02T08:00:00Z", [
            _event(32, "2026-07-01T12:00:00Z", 2, 9),
        ])

        payload = oddset_schedule.features(
            self.store, "allsvenskan", "home", "away",
            "2026-08-20T12:00:00Z", "2026-08-19T12:00:00Z")

        self.assertEqual(50 * 24, payload["home"]["rest_hours"])
        self.assertEqual(0, payload["home"]["matches_30d"])


class ScheduleCollectionTests(unittest.TestCase):
    def test_failed_team_is_retried_without_refetching_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime(2026, 7, 17, 8, tzinfo=dt.timezone.utc)
            at = "2026-07-17T08:00:00Z"
            try:
                for league in oddset_data.SOFA_UT:
                    store.meta_set(f"oddset_team_discovery_at:{league}", at)
                for team_id in (1, 2):
                    store.oddset_save_sofa_team(
                        _team(team_id, f"team {team_id}", 1.0, 1.0, at), at,
                        league="allsvenskan", season_id=1)
                calls = []

                def first(path: str):
                    calls.append(path)
                    if path == "/team/1/events/last/0":
                        return {"events": [], "hasNextPage": False}
                    raise RuntimeError("temporary")

                with mock.patch.object(oddset_data, "_now", return_value=now), \
                        mock.patch.object(oddset_schedule, "_paced_get", side_effect=first):
                    result = oddset_schedule.refresh(store)

                self.assertEqual(1, result["captures"])
                self.assertIsNotNone(store.oddset_sofa_team_latest_capture(1))
                self.assertIsNone(store.oddset_sofa_team_latest_capture(2))

                calls.clear()
                with mock.patch.object(oddset_data, "_now", return_value=now), \
                        mock.patch.object(oddset_schedule, "_paced_get",
                                          return_value={"events": [],
                                                        "hasNextPage": False}):
                    result = oddset_schedule.refresh(store)

                self.assertEqual(1, result["teams_due"])
                self.assertIsNotNone(store.oddset_sofa_team_latest_capture(2))
            finally:
                store.close()


class ScheduleParserTests(unittest.TestCase):
    def test_verified_venue_override_fills_provider_coordinate_gap(self) -> None:
        raw = {
            "id": 30, "name": "Brighton & Hove Albion",
            "sport": {"slug": "football"},
            "venue": {
                "id": 2443, "name": "American Express Stadium",
                "city": {"name": "Falmer"},
            },
        }

        parsed = oddset_schedule._team_entry(raw)

        self.assertAlmostEqual(50.8615471, parsed["venue_lat"])
        self.assertAlmostEqual(-0.0836931, parsed["venue_lon"])

    def test_parser_requires_finished_football_and_keeps_normal_time(self) -> None:
        raw = {
            "id": 55, "startTimestamp": 1_752_000_000,
            "status": {"type": "finished"},
            "homeTeam": {"id": 1, "name": "A",
                         "sport": {"slug": "football"}},
            "awayTeam": {"id": 2, "name": "B",
                         "sport": {"slug": "football"}},
            "homeScore": {"current": 6, "normaltime": 2},
            "awayScore": {"current": 5, "normaltime": 2},
            "tournament": {"id": 9, "name": "Cup",
                           "uniqueTournament": {"id": 99, "name": "Cup"}},
        }

        parsed = oddset_schedule._event_entry(raw, 1)

        self.assertEqual(2, parsed["home_score"])
        self.assertEqual(2, parsed["away_score"])
        raw["homeTeam"]["sport"]["slug"] = "handball"
        self.assertIsNone(oddset_schedule._event_entry(raw, 1))


if __name__ == "__main__":
    unittest.main()
