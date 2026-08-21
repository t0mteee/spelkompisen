import datetime as dt
import copy
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


def _market(values: dict, last_seen_at: str) -> dict:
    return {
        **values, "line": None, "available": True, "fresh": True,
        "last_seen_at": last_seen_at,
    }


class V22ShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        # Alla fixturdatum ligger RELATIVT manifestets insamlingsstart —
        # change_policy kräver nytt manifest vid källversionsändring (hände
        # 2026-07-26), och absoluta datum hamnade då före `starts_at` och
        # föll som invalid_timing.
        starts = dt.datetime.fromisoformat(
            oddset_v22.load_manifest()["collection"]["starts_at"]
            .replace("Z", "+00:00"))
        self.now = (starts + dt.timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0)
        self.match = {
            "id": "m-v22", "league": "allsvenskan",
            "home": "home", "away": "away",
            "start": self._t(hours=24),
            "odds": {
                "pinnacle": {
                    "1x2": _market({"1": 2.0, "X": 3.5, "2": 4.0},
                                   self._t(hours=0)),
                },
                "svenskaspel": {
                    "1x2": _market({"1": 2.1, "X": 3.4, "2": 3.9},
                                   self._t(hours=0)),
                },
            },
            "model": {
                "p": {"1": 0.52, "X": 0.27, "2": 0.21},
                "anchored": False,
            },
        }
        self.store.oddset_upsert_match(self.match)
        base = (self.now - dt.timedelta(days=84)).date()
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
             "level": 1, "elo": 1510,
             "valid_from": (self.now - dt.timedelta(days=23)).date().isoformat(),
             "valid_to": (self.now + dt.timedelta(days=7)).date().isoformat()},
            {"club_key": "away", "club_raw": "Away", "country": "SWE",
             "level": 1, "elo": 1480,
             "valid_from": (self.now - dt.timedelta(days=23)).date().isoformat(),
             "valid_to": (self.now + dt.timedelta(days=7)).date().isoformat()},
        ], self._t(days=-14))
        for team_id, name, lat, lon in (
                (1, "home", 59.33, 18.07), (2, "away", 57.71, 11.97)):
            self.store.oddset_save_sofa_team(
                _team(team_id, name, lat, lon), self._t(days=-14),
                league="allsvenskan", season_id=1)
        self.store.oddset_save_sofa_team_event_capture({
            "team_id": 1, "captured_at": self._t(hours=-28),
            "policy_version": oddset_schedule.policy_version(), "page_count": 1,
            "raw_event_count": 2, "payload_hash": "home-events",
        }, [
            _event(11, self._t(days=-7), 1, 8),
            _event(12, self._t(days=-2), 9, 1, 999),
        ])
        self.store.oddset_save_sofa_team_event_capture({
            "team_id": 2, "captured_at": self._t(hours=-28),
            "policy_version": oddset_schedule.policy_version(), "page_count": 1,
            "raw_event_count": 1, "payload_hash": "away-events",
        }, [
            _event(13, self._t(days=-3), 2, 7),
        ])
        # T-kalibreringen ingår i `model_source_version` och därmed i det
        # frysta kontraktet. Den bor i DB-meta, inte i koden, så den måste
        # seedas här — annars jämför testet ett okalibrerat temp-store mot ett
        # manifest fryst mot produktionens kalibrering. Ändras någon av dessa
        # i drift SKA det här testet falla: en omkalibrering är en ändrad
        # datagenererande process och kräver ett nytt manifest.
        for league, temperature in (("allsvenskan", 1.0),
                                    ("premier_league", 0.8),
                                    ("serie_a", 0.7),
                                    ("la_liga", 0.9),
                                    ("bundesliga", 0.95)):
            self.store.meta_set(f"oddset_cal:{league}",
                                json.dumps({"t": temperature}))
        frozen = oddset_v22.load_manifest()["source_versions_at_freeze"]
        self.versions = {
            "sharp": {
                "signal_version": frozen["sharp_signal_version"],
                "base_version": frozen["sharp_base_version"],
            },
            "model": {
                "signal_version": "m-d82792f7",
                "base_version": "m-c00f8a09",
            },
        }

    def _t(self, **offset) -> str:
        return (self.now + dt.timedelta(**offset)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

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
            self._t(hours=-28),
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
        health = oddset_v22.health(self.store)
        self.assertEqual("error", health["status"])
        self.assertEqual(1, health["source_mismatch_rows"])
        self.assertEqual("captured_source_mismatch",
                         health["issues"][0]["kind"])

    def test_active_manifest_is_frozen_to_current_provider_policy(self) -> None:
        manifest = oddset_v22.load_manifest()
        frozen = manifest["source_versions_at_freeze"]
        self.assertEqual("v2.2-wp9c-multileague-v9", manifest["experiment"])
        versions = oddset_ledger.prediction_versions(self.store)
        self.assertEqual(frozen["sharp_signal_version"],
                         versions["sharp"]["signal_version"])
        self.assertEqual(frozen["sharp_base_version"],
                         versions["sharp"]["base_version"])
        self.assertEqual(frozen["model_signal_version"],
                         oddset_v22.model_source_version(self.store))
        self.assertEqual(frozen["feature_version"],
                         oddset_v22.feature_version(self.store))
        self.assertEqual("ok", oddset_v22.health(self.store)["status"])

    def test_health_larmar_innan_capture_nar_manifestet_inte_matchar(self) -> None:
        broken = copy.deepcopy(oddset_v22.load_manifest())
        broken["source_versions_at_freeze"]["sharp_signal_version"] = "s-fel"

        with patch.object(oddset_v22, "load_manifest", return_value=broken):
            health = oddset_v22.health(self.store)

        self.assertEqual("error", health["status"])
        self.assertEqual(0, health["rows"])
        self.assertEqual("source_contract_mismatch", health["issues"][0]["kind"])
        self.assertIn("sharp_signal_version", health["issues"][0]["message"])

    def test_health_varnar_nar_fem_rader_i_rad_saknar_eligible(self) -> None:
        rows = [{"eligible": 0, "issues_json": '["wp9c_issues"]'}
                for _ in range(oddset_v22.ZERO_ELIGIBLE_MIN_ROWS)]

        with patch.object(self.store, "oddset_v22_shadows", return_value=rows):
            health = oddset_v22.health(self.store)

        self.assertEqual("warning", health["status"])
        self.assertEqual("zero_eligible_rows", health["issues"][0]["kind"])

    def test_feeder_alias_change_bumps_feature_version(self) -> None:
        before = oddset_v22.feature_version(self.store)
        self.store.meta_set("oddset_alias:championship", json.dumps({
            "example feeder alias": "example feeder canonical",
        }))

        self.assertNotEqual(before, oddset_v22.feature_version(self.store))

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

    def test_v22_scope_league_now_also_gets_a_regular_model_capture(self) -> None:
        """Premier League är modelliga sedan 2026-08-07 (xG bakfyllt).

        Testet hette tidigare `..._research_league_gets_shadow_but_no_regular_
        model_capture` och låste motsatsen. Premissen är borta: ligan är inte
        längre research_only, och `RESEARCH_LEAGUE_KEYS` är tom. Det som SKA
        gälla nu är att V2.2-skuggan är oberoende av den ordinarie capturen —
        två spår, samma match, ingen delad tabell.
        """
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
                    "captured_at": self._t(hours=0),
                    "target_at": self._t(hours=0),
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

        self.assertEqual(2, result["captures"])
        self.assertEqual(["model", "sharp"], sorted(
            row["tier"] for row in self.store.oddset_prediction_captures()
            if row["match_id"] == "m-eu"))
        self.assertEqual("premier_league",
                         self.store.oddset_v22_shadows()[0]["league"])

    def test_model_capture_is_still_skipped_outside_model_leagues(self) -> None:
        """Mekanismen synlig ≠ modellerad finns kvar även utan research-ligor.

        En liga kan visas i UI:t och bära sharp-signaler utan att ha
        resultathistorik nog för en modell — cuperna och träningsmatcherna gör
        exakt det. Grinden är MODEL_LEAGUES-medlemskap, inget annat.
        """
        self.match["id"] = "m-cup"
        self.match["league"] = "champions_league"
        self.store.oddset_upsert_match(self.match)
        with patch.object(oddset_ledger, "prediction_versions",
                          return_value=self.versions):
            result = oddset_ledger.capture_predictions(
                self.store, [self.match], now=self.now)

        self.assertEqual(1, result["captures"])
        self.assertEqual(["sharp"], [
            row["tier"] for row in self.store.oddset_prediction_captures()
            if row["match_id"] == "m-cup"
        ])


if __name__ == "__main__":
    unittest.main()
