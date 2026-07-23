import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import oddset_ledger, oddset_schedule, oddset_v22
from app.storage import Storage


UTC = dt.timezone.utc


def _team(team_id: int, name: str, lat: float, lon: float) -> dict:
    return {
        "team_id": team_id, "team_key": name.casefold(), "name": name,
        "country_code": "SWE", "sport": "football", "venue_id": team_id * 10,
        "venue_name": f"{name} Arena", "venue_city": name,
        "venue_lat": lat, "venue_lon": lon,
        "detail_fetched_at": "2026-07-10T08:00:00Z",
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


def _market(values: dict) -> dict:
    return {
        **values, "line": None, "available": True, "fresh": True,
        "last_seen_at": "2026-07-24T12:00:00Z",
    }


class V22ShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime(2026, 7, 24, 12, tzinfo=UTC)
        self.match = {
            "id": "m-v22", "league": "allsvenskan",
            "home": "home", "away": "away",
            "start": "2026-07-25T12:00:00Z",
            "odds": {
                "pinnacle": {
                    "1x2": _market({"1": 2.0, "X": 3.5, "2": 4.0}),
                },
                "svenskaspel": {
                    "1x2": _market({"1": 2.1, "X": 3.4, "2": 3.9}),
                },
            },
            "model": {
                "p": {"1": 0.52, "X": 0.27, "2": 0.21},
                "anchored": False,
            },
        }
        self.store.oddset_upsert_match(self.match)
        base = dt.date(2026, 5, 1)
        for index in range(45):
            self.store.oddset_save_result({
                "league": "allsvenskan",
                "date": (base + dt.timedelta(days=index)).isoformat(),
                "home": "home", "away": "away",
                "hg": index % 3, "ag": (index + 1) % 3,
                "xg_h": 1.1 + index % 4 / 10,
                "xg_a": 0.9 + index % 3 / 10,
                "source": "fd",
            })
        self.store.oddset_save_elo_history([
            {"club_key": "home", "club_raw": "Home", "country": "SWE",
             "level": 1, "elo": 1510, "valid_from": "2026-07-01",
             "valid_to": "2026-07-31"},
            {"club_key": "away", "club_raw": "Away", "country": "SWE",
             "level": 1, "elo": 1480, "valid_from": "2026-07-01",
             "valid_to": "2026-07-31"},
        ], "2026-07-10T08:00:00Z")
        for team_id, name, lat, lon in (
                (1, "home", 59.33, 18.07), (2, "away", 57.71, 11.97)):
            self.store.oddset_save_sofa_team(
                _team(team_id, name, lat, lon), "2026-07-10T08:00:00Z",
                league="allsvenskan", season_id=1)
        self.store.oddset_save_sofa_team_event_capture({
            "team_id": 1, "captured_at": "2026-07-23T08:00:00Z",
            "policy_version": oddset_schedule.policy_version(), "page_count": 1,
            "raw_event_count": 2, "payload_hash": "home-events",
        }, [
            _event(11, "2026-07-17T12:00:00Z", 1, 8),
            _event(12, "2026-07-22T12:00:00Z", 9, 1, 999),
        ])
        self.store.oddset_save_sofa_team_event_capture({
            "team_id": 2, "captured_at": "2026-07-23T08:00:00Z",
            "policy_version": oddset_schedule.policy_version(), "page_count": 1,
            "raw_event_count": 1, "payload_hash": "away-events",
        }, [
            _event(13, "2026-07-21T12:00:00Z", 2, 7),
        ])
        self.versions = {
            "sharp": {
                "signal_version": "s-a4e45b6c",
                "base_version": "s-776ca0e0",
            },
            "model": {
                "signal_version": "m-d82792f7",
                "base_version": "m-c00f8a09",
            },
        }

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_complete_capture_is_exact_non_actionable_identity_control(self) -> None:
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions):
            result = oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        self.assertEqual({"captures": 2, "rows": 6, "empty": 0}, result)
        feature_row = self.store.oddset_v2_features(
            oddset_v22.feature_version(self.store))[0]
        payload = json.loads(feature_row["payload_json"])
        shadow = self.store.oddset_v22_shadows()[0]
        report = oddset_v22.audit(self.store)

        self.assertEqual(72.0, payload["features"]["rest_home_hours"])
        self.assertEqual(96.0, payload["features"]["rest_away_hours"])
        self.assertEqual(-24.0, payload["features"]["rest_diff_hours"])
        self.assertEqual(1, payload["features"]["outside_primary_home_14d"])
        self.assertGreater(payload["features"]["away_base_travel_km"], 390)
        self.assertEqual(2, payload["wp9c_source"]["home"]["event_count"])
        self.assertEqual(
            "2026-07-23T08:00:00Z",
            payload["wp9c_source"]["home"]["max_first_seen_at"])
        self.assertLessEqual(
            payload["wp9c_source"]["home"]["max_first_seen_at"],
            payload["as_of"])
        self.assertEqual("collecting_identity_control", shadow["state"])
        self.assertEqual("training_gate_not_met", shadow["fallback_reason"])
        self.assertEqual(1, shadow["eligible"])
        self.assertAlmostEqual(shadow["sharp_p1"], shadow["v22_p1"])
        self.assertAlmostEqual(shadow["sharp_px"], shadow["v22_px"])
        self.assertAlmostEqual(shadow["sharp_p2"], shadow["v22_p2"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["notifications"])
        self.assertEqual(0.0, report["identity_max_abs"])

    def test_missing_schedule_is_kept_as_incomplete_identity_control(self) -> None:
        self.store.conn.execute("DELETE FROM oddset_sofa_team_scope")
        self.store.conn.commit()
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions):
            oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        shadow = self.store.oddset_v22_shadows()[0]
        issues = json.loads(shadow["issues_json"])

        self.assertEqual(0, shadow["eligible"])
        self.assertEqual("incomplete_identity_control", shadow["state"])
        self.assertEqual("incomplete_features", shadow["fallback_reason"])
        self.assertIn("wp9c_identity_incomplete", issues)
        self.assertIn("wp9c_issues", issues)
        self.assertEqual(shadow["sharp_p1"], shadow["v22_p1"])

    def test_changed_source_version_cannot_mix_into_frozen_experiment(self) -> None:
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions), \
                patch.object(oddset_v22, "model_source_version",
                             return_value="m22-changed"):
            oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        shadow = self.store.oddset_v22_shadows()[0]
        issues = json.loads(shadow["issues_json"])

        self.assertEqual(0, shadow["eligible"])
        self.assertEqual("source_version_changed", shadow["fallback_reason"])
        self.assertIn("model_source_version_changed", issues)

    def test_feature_failure_rolls_back_sharp_ledger_and_can_retry(self) -> None:
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions), \
                patch.object(oddset_v22.FeatureBuilder, "capture",
                             side_effect=RuntimeError("feature failure")):
            with self.assertRaisesRegex(RuntimeError, "feature failure"):
                oddset_ledger.capture_predictions(
                    self.store, [self.match], now=self.now)

        captures = self.store.oddset_prediction_captures()
        self.assertEqual([], captures)
        self.assertEqual([], self.store.oddset_v22_shadows())

        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions):
            result = oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        self.assertEqual(2, result["captures"])
        self.assertEqual(6, result["rows"])
        self.assertEqual(1, len(self.store.oddset_v22_shadows()))

    def test_research_league_gets_shadow_but_no_regular_model_capture(self) -> None:
        self.match["id"] = "m-eu"
        self.match["league"] = "premier_league"
        self.store.oddset_upsert_match(self.match)
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions), \
                patch.object(oddset_v22.FeatureBuilder, "payload") as payload:
            base = oddset_v22.FeatureBuilder(self.store).base.payload(
                self.match, {
                    "match_id": self.match["id"], "horizon": "h24",
                    "signal_version": self.versions["sharp"]["signal_version"],
                    "match_start": self.match["start"],
                    "captured_at": "2026-07-24T12:00:00Z",
                    "target_at": "2026-07-24T12:00:00Z",
                }, "live")
            base.update({
                "schema": 2, "experiment": oddset_v22.load_manifest()["experiment"],
                "standalone_model_1x2": self.match["model"]["p"],
                "identity": {"all_fit_links_verified": False,
                             "all_elo_links_verified": False,
                             "wp9c_verified": False},
                "wp9c": {"issues": ["test_missing"]},
                "wp9c_source": {},
            })
            base["features"].update({
                name: None for name in (
                    oddset_v22.REQUIRED_MODEL_FEATURES +
                    oddset_v22.REQUIRED_SCHEDULE_FEATURES)
            })
            payload.return_value = base
            result = oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        self.assertEqual(1, result["captures"])
        self.assertEqual(["sharp"], [
            row["tier"] for row in self.store.oddset_prediction_captures()
            if row["match_id"] == "m-eu"
        ])
        self.assertEqual("premier_league",
                         self.store.oddset_v22_shadows()[0]["league"])


if __name__ == "__main__":
    unittest.main()
