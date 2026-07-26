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


class RotationRiskTests(unittest.TestCase):
    """Samans beställning 2026-07-25: vikta vila OCH viktigare nästa match.

    Vilodatan fanns redan (rest_hours, matches_7/14/30d) men var enkelriktad —
    bara bakåt. Ett lag med Champions League-kval om tre dagar vilar spelare i
    ligan, och den informationen fanns inte ens insamlad: `_event_entry`
    släppte bara igenom `finished`.
    """

    TARGET = dt.datetime(2026, 8, 1, 16, 0, tzinfo=dt.timezone.utc)
    LIGA = 40          # Allsvenskan

    @staticmethod
    def _fixture(start, ut, slug="x", name="X"):
        return {"start_at": start, "unique_tournament_id": ut,
                "tournament_slug": slug, "tournament_name": name,
                "home_team_id": 1, "away_team_id": 2}

    def test_kommande_matcher_sparas_numera(self):
        raw = {
            "id": 5, "startTimestamp": 1785000000,
            "status": {"type": "notstarted"},
            "homeTeam": {"id": 1, "sport": {"slug": "football"}},
            "awayTeam": {"id": 2},
            "tournament": {"id": 9, "uniqueTournament": {"id": 7, "name": "UCL"}},
            "homeScore": {}, "awayScore": {},
        }
        entry = oddset_schedule._event_entry(raw, 1)
        self.assertIsNotNone(entry, "planerade matcher får inte kastas bort")
        self.assertEqual("scheduled", entry["status"])

    def test_tyngre_turnering_inom_fem_dygn_flaggas(self):
        upcoming = [self._fixture("2026-08-04T18:45:00Z", 7,
                                  "uefa-champions-league", "UCL")]
        out = oddset_schedule._forward_features(upcoming, 1, self.TARGET, self.LIGA)
        self.assertTrue(out["next_is_heavier"])
        self.assertEqual(5, out["next_weight"])
        self.assertAlmostEqual(74.75, out["hours_to_next"], places=1)

    def test_vanlig_ligamatch_efterat_ar_ingen_rotationsrisk(self):
        upcoming = [self._fixture("2026-08-04T18:45:00Z", self.LIGA,
                                  "allsvenskan", "Allsvenskan")]
        out = oddset_schedule._forward_features(upcoming, 1, self.TARGET, self.LIGA)
        self.assertFalse(out["next_is_heavier"])

    def test_tung_match_langt_bort_ar_ingen_rotationsrisk(self):
        upcoming = [self._fixture("2026-08-20T18:45:00Z", 7, "ucl", "UCL")]
        self.assertFalse(oddset_schedule._forward_features(
            upcoming, 1, self.TARGET, self.LIGA)["next_is_heavier"])

    def test_matcher_fore_target_raknas_aldrig_som_nasta(self):
        upcoming = [self._fixture("2026-07-30T18:45:00Z", 7, "ucl", "UCL"),
                    self._fixture("2026-08-05T18:45:00Z", self.LIGA, "a", "A")]
        out = oddset_schedule._forward_features(upcoming, 1, self.TARGET, self.LIGA)
        self.assertEqual("2026-08-05T18:45:00Z", out["next_match_at"])

    def test_okand_turnering_far_ligans_vikt_aldrig_hogre(self):
        """Vi antar aldrig att något är viktigare än ligan utan att veta det."""
        okand = self._fixture("2026-08-03T12:00:00Z", 99999, "mystery", "Mystery")
        self.assertEqual(oddset_schedule.LEAGUE_WEIGHT,
                         oddset_schedule.tournament_weight(okand, self.LIGA))

    def test_inhemsk_cup_hittas_via_slug(self):
        cup = self._fixture("2026-08-03T12:00:00Z", 80, "svenska-cupen",
                            "Svenska Cupen")
        self.assertEqual(oddset_schedule.CUP_WEIGHT,
                         oddset_schedule.tournament_weight(cup, self.LIGA))

    def test_traningsmatch_vager_lattast(self):
        vanlig = self._fixture("2026-08-03T12:00:00Z", 853, "club-friendly",
                               "Club Friendly Games")
        self.assertEqual(0, oddset_schedule.tournament_weight(vanlig, self.LIGA))

    def test_matchen_vi_analyserar_blir_aldrig_sin_egen_nasta(self):
        # Granskningsfix F5 (2026-07-26): Sofascores klocka kan ligga minuter
        # från Kambis för samma match — utan marginal blev matchen sin egen
        # "nästa match" med hours_to_next ≈ 0. Inget lag spelar två matcher
        # inom sex timmar.
        upcoming = [self._fixture("2026-08-01T16:03:00Z", self.LIGA, "a", "A"),
                    self._fixture("2026-08-05T18:45:00Z", 7, "ucl", "UCL")]
        out = oddset_schedule._forward_features(upcoming, 1, self.TARGET, self.LIGA)
        self.assertEqual("2026-08-05T18:45:00Z", out["next_match_at"])
        self.assertEqual(1, out["congested_after"])

    def test_policykontraktet_bar_forwardsemantiken(self):
        # F5b: schema 4 fingeravtrycker statusomfång och forwardvikter —
        # payloadändringar utan versionbump var granskningens fynd.
        policy = oddset_schedule.POLICY
        self.assertGreaterEqual(policy["schema"], 4)
        self.assertIn("notstarted", policy["event_status_scope"])
        self.assertIn("tournament_weight", policy["forward"])
        self.assertEqual(oddset_schedule.FORWARD_SELF_GUARD_H,
                         policy["forward"]["self_guard_h"])


class CaptureStatusScopeTests(unittest.TestCase):
    """F5c (2026-07-26): valideringen krävde `finished` medan insamlaren sedan
    2026-07-25 skickar även planerade/pågående — VARJE lagcapture med en
    kommande fixtur kraschade tyst och WP9c-insamlingen stod still i drift."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _capture(self, at: str, events: list[dict]) -> int:
        return self.store.oddset_save_sofa_team_event_capture({
            "team_id": 1, "captured_at": at, "page_count": 1,
            "policy_version": oddset_schedule.policy_version(),
            "raw_event_count": len(events), "payload_hash": f"h-{at}",
        }, events)

    def test_scheduled_och_inprogress_accepteras(self) -> None:
        scheduled = {**_event(41, "2026-08-01T16:00:00Z", 1, 9),
                     "status": "scheduled", "home_score": None,
                     "away_score": None}
        live = {**_event(42, "2026-07-26T16:00:00Z", 1, 8),
                "status": "inprogress"}
        self.assertEqual(2, self._capture("2026-07-20T08:00:00Z",
                                          [scheduled, live]))

    def test_okand_status_avvisas_fortfarande(self) -> None:
        with self.assertRaises(ValueError):
            self._capture("2026-07-20T08:00:00Z",
                          [{**_event(43, "2026-08-01T16:00:00Z", 1, 9),
                            "status": "postponed"}])

    def test_fixtures_as_of_laser_starttiden_som_den_var_kand_da(self) -> None:
        # F5a: eventet bokas om 2026-08-01 → 2026-08-03. En as-of-läsning
        # mellan observationerna ska se den GAMLA tiden — huvudradens upsert
        # skriver över start_at och får inte användas retroaktivt.
        first = {**_event(51, "2026-08-01T16:00:00Z", 1, 9),
                 "status": "scheduled", "home_score": None, "away_score": None}
        moved = {**first, "start_at": "2026-08-03T16:00:00Z"}
        self._capture("2026-07-20T08:00:00Z", [first])
        self._capture("2026-07-24T08:00:00Z", [moved])

        before = self.store.oddset_sofa_team_fixtures_as_of(
            1, "2026-07-22T00:00:00Z")
        after = self.store.oddset_sofa_team_fixtures_as_of(
            1, "2026-07-25T00:00:00Z")
        self.assertEqual(["2026-08-01T16:00:00Z"],
                         [f["start_at"] for f in before])
        self.assertEqual(["2026-08-03T16:00:00Z"],
                         [f["start_at"] for f in after])


if __name__ == "__main__":
    unittest.main()
