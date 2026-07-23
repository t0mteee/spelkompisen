"""V2.2: fryst Allsvenskan-capture med WP9c och isolerad shadowkontroll.

Det här är inte en tränad modell. Fram till den förregistrerade träningsgaten
är uppfylld lagras ``p_v22 == p_sharp`` exakt. På så sätt kan datakontrakt,
horisonter och coverage köras live utan att påverka appens sannolikheter,
signaler, notiser eller CLV-facit.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Optional

from . import oddset_data, oddset_schedule, oddset_v2
from .storage import Storage


SIGNS = ("1", "X", "2")
SCOPE_LEAGUES = ("allsvenskan",)
MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "docs" /
    "model-v2.2-forward-manifest.json"
)
REQUIRED_BASE_FEATURES = (
    "attack_log_ratio", "defence_log_ratio", "home_adv_log",
    "effective_n_home", "effective_n_away", "data_age_home_days",
    "data_age_away_days", "elo_home", "elo_away", "elo_diff",
)
REQUIRED_SCHEDULE_FEATURES = (
    "rest_home_hours", "rest_away_hours", "rest_diff_hours",
    "matches_home_7d", "matches_away_7d", "matches_home_14d",
    "matches_away_14d", "matches_home_30d", "matches_away_30d",
    "outside_primary_home_14d", "outside_primary_away_14d",
    "last_was_away_home", "last_was_away_away", "away_base_travel_km",
)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def shadow_version() -> str:
    return f"v22-{_hash(load_manifest())[:8]}"


def feature_version(store: Storage) -> str:
    policy = {
        "schema": 1,
        "experiment": load_manifest()["experiment"],
        "base_feature_version": oddset_v2.feature_version(store),
        "wp9c_policy_version": oddset_schedule.policy_version(),
        "wp9c_source_fingerprint": (
            "event-id-start-tournament-first-seen-hash-per-team-as-of"),
        "required_base": REQUIRED_BASE_FEATURES,
        "required_schedule": REQUIRED_SCHEDULE_FEATURES,
    }
    return f"f22-{_hash(policy)[:8]}"


def _schedule_features(payload: dict) -> dict:
    home, away = payload.get("home") or {}, payload.get("away") or {}
    travel = payload.get("travel_proxy") or {}
    rest_home, rest_away = home.get("rest_hours"), away.get("rest_hours")
    return {
        "rest_home_hours": rest_home,
        "rest_away_hours": rest_away,
        "rest_diff_hours": (
            round(rest_home - rest_away, 1)
            if rest_home is not None and rest_away is not None else None
        ),
        "matches_home_7d": home.get("matches_7d"),
        "matches_away_7d": away.get("matches_7d"),
        "matches_home_14d": home.get("matches_14d"),
        "matches_away_14d": away.get("matches_14d"),
        "matches_home_30d": home.get("matches_30d"),
        "matches_away_30d": away.get("matches_30d"),
        "outside_primary_home_14d": home.get("outside_primary_14d"),
        "outside_primary_away_14d": away.get("outside_primary_14d"),
        "last_was_away_home": home.get("last_was_away"),
        "last_was_away_away": away.get("last_was_away"),
        "away_base_travel_km": travel.get("away_km"),
    }


def _schedule_source(store: Storage, schedule: dict, as_of: str) -> dict:
    """Frys beviset bakom aggregaten utan att duplicera hela eventhistoriken."""
    source = {
        "as_of": as_of,
        "policy_version": schedule["policy_version"],
    }
    for side in ("home", "away"):
        team_id = schedule["identity"].get(f"{side}_team_id")
        events = (store.oddset_sofa_team_events_as_of(team_id, as_of)
                  if team_id is not None else [])
        fingerprint_rows = [{
            "event_id": event["event_id"], "start_at": event["start_at"],
            "home_team_id": event["home_team_id"],
            "away_team_id": event["away_team_id"],
            "unique_tournament_id": event.get("unique_tournament_id"),
            "first_seen_at": event["first_seen_at"],
        } for event in events]
        source[side] = {
            "team_id": team_id, "event_count": len(events),
            "input_hash": _hash(fingerprint_rows),
            "max_event_start": max(
                (event["start_at"] for event in events), default=None),
            "max_first_seen_at": max(
                (event["first_seen_at"] for event in events), default=None),
        }
    return source


def _probabilities(rows: list[dict], tier: str) -> Optional[dict[str, float]]:
    picked = {}
    for row in rows:
        if (row.get("market") != "1x2" or row.get("sign") not in SIGNS or
                row.get("fair_source") != ("pinnacle" if tier == "sharp" else "model")):
            continue
        if tier == "sharp" and not (
                row.get("fair_available") and row.get("fair_fresh")):
            continue
        value = row.get("fair_prob")
        if value is not None and math.isfinite(float(value)) and float(value) > 0:
            picked[row["sign"]] = float(value)
    if set(picked) != set(SIGNS):
        return None
    total = sum(picked.values())
    return ({sign: picked[sign] / total for sign in SIGNS}
            if total > 0 else None)


class FeatureBuilder:
    """Kompletterar den frysta V2-A-payloaden med point-in-time-WP9c."""

    def __init__(self, store: Storage):
        self.store = store
        self.base = oddset_v2.FeatureBuilder(store)

    def payload(self, match: dict, capture: dict) -> dict:
        payload = self.base.payload(match, capture, "live")
        schedule = oddset_schedule.features(
            self.store, match["league"], match["home"], match["away"],
            capture["match_start"], capture["captured_at"])
        payload.update({
            "schema": 1,
            "experiment": load_manifest()["experiment"],
            "base_schema": oddset_v2.FEATURE_POLICY["schema"],
            "wp9c": schedule,
            "wp9c_source": _schedule_source(
                self.store, schedule, capture["captured_at"]),
        })
        payload["features"].update(_schedule_features(schedule))
        payload["missing"] = {
            key: value is None for key, value in payload["features"].items()
        }
        payload["identity"]["wp9c_home_team_id"] = (
            schedule["identity"]["home_team_id"])
        payload["identity"]["wp9c_away_team_id"] = (
            schedule["identity"]["away_team_id"])
        payload["identity"]["wp9c_verified"] = bool(
            schedule["identity"]["home_team_id"] is not None and
            schedule["identity"]["away_team_id"] is not None)
        return payload

    def capture(self, match: dict, capture: dict,
                sharp_signal_version: str) -> dict:
        version = feature_version(self.store)
        payload = self.payload(match, capture)
        payload["feature_version"] = version
        payload_json = _canonical(payload)
        now = _iso(dt.datetime.now(dt.timezone.utc))
        feature_added = self.store.oddset_save_v2_features({
            "match_id": capture["match_id"], "horizon": capture["horizon"],
            "model_signal_version": capture["signal_version"],
            "feature_version": version, "captured_at": capture["captured_at"],
            "match_start": capture["match_start"], "capture_mode": "live",
            "payload_hash": hashlib.sha256(payload_json.encode()).hexdigest(),
            "payload_json": payload_json, "created_at": now,
        })
        shadow_added = capture_shadow(
            self.store, capture, payload, version, sharp_signal_version, now)
        return {
            "feature_added": feature_added, "shadow_added": shadow_added,
            "feature_version": version, "shadow_version": shadow_version(),
        }


def _eligibility(capture: dict, payload: dict, sharp: Optional[dict],
                 model: Optional[dict], sharp_signal_version: str,
                 pair_gap_minutes: Optional[float]) -> tuple[bool, list[str]]:
    from .oddset_ledger import HORIZON_MAX_DELAY

    reasons = []
    if capture.get("league") not in SCOPE_LEAGUES:
        reasons.append("league_out_of_scope")
    if capture["captured_at"] < load_manifest()["collection"]["starts_at"]:
        reasons.append("before_collection_start")
    frozen_versions = load_manifest()["source_versions_at_freeze"]
    if sharp_signal_version != frozen_versions["sharp_signal_version"]:
        reasons.append("sharp_source_version_changed")
    if capture["signal_version"] != frozen_versions["model_signal_version"]:
        reasons.append("model_source_version_changed")
    if capture.get("delay_minutes", float("inf")) > HORIZON_MAX_DELAY[capture["horizon"]]:
        reasons.append("late_capture")
    if capture["captured_at"] >= capture["match_start"]:
        reasons.append("post_kickoff")
    if sharp is None:
        reasons.append("direct_fresh_sharp_1x2_missing")
    if model is None:
        reasons.append("paired_model_1x2_missing")
    if pair_gap_minutes is None or pair_gap_minutes > load_manifest()[
            "eligibility"]["paired_capture_max_minutes"]:
        reasons.append("capture_pair_too_far_apart")
    identity = payload.get("identity") or {}
    if not (identity.get("all_fit_links_verified") and
            identity.get("all_elo_links_verified")):
        reasons.append("base_identity_incomplete")
    if not identity.get("wp9c_verified"):
        reasons.append("wp9c_identity_incomplete")
    if (payload.get("wp9c") or {}).get("issues"):
        reasons.append("wp9c_issues")
    for side in ("home", "away"):
        first_seen = ((payload.get("wp9c_source") or {}).get(side) or {}).get(
            "max_first_seen_at")
        if first_seen and first_seen > capture["captured_at"]:
            reasons.append("wp9c_source_after_as_of")
    for name in REQUIRED_BASE_FEATURES + REQUIRED_SCHEDULE_FEATURES:
        if (payload.get("features") or {}).get(name) is None:
            reasons.append(f"feature_missing:{name}")
    return not reasons, sorted(set(reasons))


def capture_shadow(store: Storage, capture: dict, payload: dict,
                   feature_version_value: str, sharp_signal_version: str,
                   created_at: Optional[str] = None) -> bool:
    """Spara en isolerad kontrollrad. Ingen modell- eller signalväg läser den."""
    sharp_rows = store.oddset_prediction_market_rows(
        capture["match_id"], capture["horizon"], "sharp",
        sharp_signal_version, "1x2")
    model_rows = store.oddset_prediction_market_rows(
        capture["match_id"], capture["horizon"], "model",
        capture["signal_version"], "1x2")
    sharp = _probabilities(sharp_rows, "sharp")
    model = _probabilities(model_rows, "model")
    sharp_capture = store.oddset_prediction_capture(
        capture["match_id"], capture["horizon"], "sharp",
        sharp_signal_version)
    pair_gap = None
    if sharp_capture:
        pair_gap = abs((
            dt.datetime.fromisoformat(
                sharp_capture["captured_at"].replace("Z", "+00:00")) -
            dt.datetime.fromisoformat(
                capture["captured_at"].replace("Z", "+00:00"))
        ).total_seconds()) / 60
    eligible, reasons = _eligibility(
        capture, payload, sharp, model, sharp_signal_version, pair_gap)
    if sharp is None:
        state = "sharp_missing"
        fallback = "direct_fresh_sharp_1x2_missing"
    elif not eligible:
        state = "incomplete_identity_control"
        if any(reason.endswith("source_version_changed") for reason in reasons):
            fallback = "source_version_changed"
        elif any(reason in ("late_capture", "post_kickoff",
                            "capture_pair_too_far_apart",
                            "before_collection_start") for reason in reasons):
            fallback = "invalid_timing"
        else:
            fallback = "incomplete_features"
    else:
        state = "collecting_identity_control"
        fallback = "training_gate_not_met"
    values = sharp or {}
    return store.oddset_save_v22_shadow({
        "match_id": capture["match_id"], "horizon": capture["horizon"],
        "shadow_version": shadow_version(),
        "feature_version": feature_version_value,
        "sharp_signal_version": sharp_signal_version,
        "model_signal_version": capture["signal_version"],
        "league": capture.get("league"), "match_start": capture["match_start"],
        "target_at": capture["target_at"], "captured_at": capture["captured_at"],
        "offset_minutes": capture["offset_minutes"],
        "delay_minutes": capture["delay_minutes"], "state": state,
        "eligible": int(eligible), "fallback_reason": fallback,
        "issues_json": _canonical(reasons),
        "sharp_p1": values.get("1"), "sharp_px": values.get("X"),
        "sharp_p2": values.get("2"), "v22_p1": values.get("1"),
        "v22_px": values.get("X"), "v22_p2": values.get("2"),
        "feature_payload_hash": _hash(payload),
        "created_at": created_at or _iso(dt.datetime.now(dt.timezone.utc)),
    })


def audit(store: Storage) -> dict:
    rows = store.oddset_v22_shadows(shadow_version())
    matches_by_id = {row["id"]: row for row in store.oddset_matches()}
    results = {
        "allsvenskan": oddset_data.merged_results(store, "allsvenskan")
    }
    settled = set()
    for match_id in {row["match_id"] for row in rows}:
        match = matches_by_id.get(match_id)
        if match and oddset_v2._outcome(store, match, results)[0]:
            settled.add(match_id)
    unique = {row["match_id"] for row in rows}
    eligible = [row for row in rows if row["eligible"]]
    by_horizon = {}
    for horizon in load_manifest()["scope"]["horizons"]:
        subset = [row for row in rows if row["horizon"] == horizon]
        eligible_subset = [row for row in subset if row["eligible"]]
        matches = {row["match_id"] for row in eligible_subset}
        settled_matches = matches & settled
        dates = sorted(
            row["match_start"][:10] for row in eligible_subset
            if row["match_id"] in settled_matches)
        span = ((dt.date.fromisoformat(dates[-1]) -
                 dt.date.fromisoformat(dates[0])).days + 1 if dates else 0)
        by_horizon[horizon] = {
            "rows": len(subset), "eligible_rows": len(eligible_subset),
            "eligible_unique_matches": len(matches), "span_days": span,
            "settled_eligible_unique_matches": len(settled_matches),
            "training_min_matches": load_manifest()["training_gate"][
                "minimum_unique_settled_matches_per_horizon"],
            "training_min_span_days": load_manifest()["training_gate"][
                "minimum_span_days_per_horizon"],
        }
    identity_error = max((
        max(abs(row[f"sharp_p{suffix}"] - row[f"v22_p{suffix}"])
            for suffix in ("1", "x", "2"))
        for row in rows if row["sharp_p1"] is not None
    ), default=0.0)
    states = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    return {
        "experiment": load_manifest()["experiment"],
        "shadow_version": shadow_version(),
        "feature_version": feature_version(store),
        "phase": "identity_control_until_training_gate",
        "actionable": False, "notifications": False,
        "rows": len(rows), "unique_matches": len(unique),
        "eligible_rows": len(eligible), "states": states,
        "identity_max_abs": identity_error, "horizons": by_horizon,
    }


def format_audit(report: dict) -> str:
    lines = [
        f"V2.2 {report['shadow_version']} · {report['phase']} · "
        f"{report['rows']} rader/{report['unique_matches']} matcher",
        f"actionable nej · notiser nej · identity max |Δp| "
        f"{report['identity_max_abs']:.3g}",
    ]
    for horizon, row in report["horizons"].items():
        lines.append(
            f"{horizon:>3}: eligible {row['eligible_unique_matches']}/"
            f"{row['training_min_matches']} fångade, avgjorda "
            f"{row['settled_eligible_unique_matches']}/"
            f"{row['training_min_matches']} · span "
            f"{row['span_days']}/{row['training_min_span_days']} d · "
            f"alla rader {row['rows']}")
    if report["states"]:
        lines.append("status: " + ", ".join(
            f"{key}={value}" for key, value in sorted(report["states"].items())))
    return "\n".join(lines)
