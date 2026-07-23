"""Modell v2-A: frysta point-in-time-features och dataset-audit.

VILANDE: V2-B stoppades av den förregistrerade domen 2026-07-17. Spåret får
återupptas endast med en ny hypotes och ett nytt fryst outer-manifest.

Ingen modell tränas här. Modulen gör tre saker som måste vara sanna först:

* fryser featurevärden samtidigt med ledgerns modellcapture;
* bygger en rad per match och fast horisont utan att filtrera bort saknad data;
* bevisar att identitetsmodellen (delta=0) är exakt samma marknad.

Historiskt rekonstruerade features märks uttryckligen och får aldrig räknas som
promotion-data. De finns bara för att kunna testa pipeline och coverage nu.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from . import oddset_data, oddset_model
from .oddset import norm_team
from .storage import Storage


SIGNS = ("1", "X", "2")
LEAGUES = ("allsvenskan", "eliteserien")
COLLECTION_START = "2026-07-16T13:30:00Z"
PAIR_MAX_MINUTES = 5
ELO_TEAM_ALIAS = {
    # Verifierade provider-translittereringar: norm_team tappar diakritiken,
    # ClubElo skriver i stället ae/oe. Hålls separat från resultatidentiteten.
    "bodo glimt": "bodoe glimt",
    "goteborg": "goeteborg",
    "mjallby": "mjaellby",
    "vasteras": "vaesteras",
    # Verifierade Kambi/Svenska Spel → ClubElo-identiteter för V2.2-EU.
    "coventry city": "coventry", "manchester united": "man united",
    "ipswich town": "ipswich", "nottingham": "forest",
    "manchester city": "man city", "newcastle united": "newcastle",
    "internazionale": "inter",
    "racing santander": "santander", "dep la coruna": "depor",
    "deportivo la coruna": "depor",
    "espanyol": "espanyol", "celta vigo": "celta",
    "real sociedad": "sociedad",
    "athletic bilbao": "bilbao", "atletico madrid": "atletico",
    "real betis": "betis", "rayo vallecano": "rayo vallecano",
    "bayern munchen": "bayern", "borussia mgladbach": "gladbach",
    "bayer leverkusen": "leverkusen", "borussia dortmund": "dortmund",
    "1 koln": "koeln", "tsg hoffenheim": "hoffenheim",
    "1 union berlin": "union berlin",
    "eintracht frankfurt": "frankfurt", "mainz 05": "mainz",
    "paderborn 07": "paderborn", "werder bremen": "werder",
    "schalke 04": "schalke", "hamburger sv": "hamburg",
}
FEATURE_POLICY = {
    "schema": 5,
    "scope": {"leagues": LEAGUES, "market": "1x2"},
    "result_cutoff": "strictly-before-utc-capture-date",
    "result_merge": oddset_data.MODEL_DATA_VERSION,
    "fit": {
        "xg_weight": oddset_model.XG_WEIGHT,
        "decay_days": oddset_model.DECAY_DAYS,
        "iterations": oddset_model.FIT_ITER,
        "minimum_effective_matches": oddset_model.MIN_MATCHES,
    },
    "elo": "provider-validity-interval-as-of-capture-date",
    "team_link": "exact-or-verified-alias; fuzzy-is-review-only",
    "formulas": {
        "attack": "log(home_att/away_att)",
        "defence": "log(away_def/home_def)",
        "home_advantage": "log(home_adv)",
        "model_market": "center(log(model)-log(sharp))",
    },
    "missing": "explicit-no-row-filtering",
}
MANIFEST_PATH = Path(__file__).resolve().parents[2] / "docs" / "model-v2-outer-manifest.json"


def _parse_iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def feature_version(store: Storage) -> str:
    """Semantisk featureversion; aliasbeslut ingår eftersom de ändrar länkar."""
    alias_leagues = sorted({league for scoped in LEAGUES
                            for league in oddset_model.FIT_POOLS.get(scoped, (scoped,))})
    aliases = {league: oddset_data._alias_map(store, league)
               for league in alias_leagues}
    digest = _hash({"policy": FEATURE_POLICY, "runtime_aliases": aliases,
                    "elo_aliases": _elo_alias_map(store)})[:8]
    return f"f-{digest}"


def _elo_alias_map(store: Storage) -> dict[str, str]:
    aliases = dict(ELO_TEAM_ALIAS)
    try:
        aliases.update(json.loads(store.meta_get("oddset_elo_alias") or "{}"))
    except (TypeError, ValueError):
        pass
    return aliases


def _link(name: str, keys, alias: Optional[dict[str, str]] = None) -> dict:
    """Länka öppet: endast exakt/verifierat alias är godkänt för V2-B."""
    raw = norm_team(name)
    canonical = raw
    seen = set()
    while canonical in (alias or {}) and canonical not in seen:
        seen.add(canonical)
        canonical = alias[canonical]
    method = "alias" if canonical != raw else "exact"
    keys = tuple(keys)
    if canonical in keys:
        return {"raw": raw, "key": canonical, "method": method,
                "score": 1.0, "verified": True}
    substring = sorted(k for k in keys if canonical in k or k in canonical)
    if len(substring) == 1:
        return {"raw": raw, "key": substring[0], "method": "substring",
                "score": round(SequenceMatcher(None, canonical, substring[0]).ratio(), 3),
                "verified": False}
    best = max(((k, SequenceMatcher(None, canonical, k).ratio()) for k in keys),
               key=lambda item: item[1], default=(None, 0.0))
    if best[0] and best[1] >= oddset_data.FUZZY_SUGGEST_MIN:
        return {"raw": raw, "key": best[0], "method": "fuzzy",
                "score": round(best[1], 3), "verified": False}
    return {"raw": raw, "key": None, "method": "missing",
            "score": round(best[1], 3), "verified": False}


def _input_rows(store: Storage, league: str, cutoff_day: str,
                pool: Optional[tuple[str, ...]] = None) -> list[dict]:
    rows = []
    for pool_league in (pool or oddset_model.FIT_POOLS.get(
            league, (league,))):
        rows.extend(oddset_data.merged_results(store, pool_league))
    # Resultattabellen saknar klockslag. Samma UTC-dag utesluts därför hellre
    # än att en tidigare/later match på dagen felklassas som känd.
    return sorted((row for row in rows if row.get("date", "9") < cutoff_day),
                  key=lambda row: (row["date"], row["home"], row["away"],
                                   row.get("source") or ""))


def _input_fingerprint(rows: list[dict]) -> str:
    fields = ("league", "date", "home", "away", "hg", "ag", "xg_h", "xg_a")
    return _hash([{key: row.get(key) for key in fields} for row in rows])


def _last_team_date(rows: list[dict], key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    values = [row["date"] for row in rows if key in (row["home"], row["away"])]
    return max(values) if values else None


def _age_days(as_of_day: str, source_day: Optional[str]) -> Optional[int]:
    if not source_day:
        return None
    return (dt.date.fromisoformat(as_of_day) - dt.date.fromisoformat(source_day)).days


class FeatureBuilder:
    """Återanvänder fitten för flera matcher i samma liga/cutoff under ett varv."""

    def __init__(self, store: Storage,
                 fit_pools: Optional[dict[str, tuple[str, ...]]] = None):
        self.store = store
        self.fit_pools = fit_pools or oddset_model.FIT_POOLS
        self._cache: dict[tuple, tuple[list[dict], Optional[dict]]] = {}

    def payload(self, match: dict, capture: dict, capture_mode: str) -> dict:
        as_of = _parse_iso(capture["captured_at"])
        start = _parse_iso(capture["match_start"])
        cutoff_day = min(as_of.date(), start.date()).isoformat()
        league = match.get("league")
        cache_key = (league, cutoff_day)
        if cache_key not in self._cache:
            pool = self.fit_pools.get(league, (league,))
            rows = _input_rows(self.store, league, cutoff_day, pool)
            fit = oddset_model.fit_league(rows, now=dt.date.fromisoformat(cutoff_day))
            self._cache[cache_key] = rows, fit
        rows, fit = self._cache[cache_key]

        alias = {}
        for pool_league in self.fit_pools.get(league, (league,)):
            alias.update(oddset_data._alias_map(self.store, pool_league))
        fit_keys = (fit or {}).get("teams", {}).keys()
        home_link = _link(match.get("home") or "", fit_keys, alias)
        away_link = _link(match.get("away") or "", fit_keys, alias)
        home_fit = (fit or {}).get("teams", {}).get(home_link["key"])
        away_fit = (fit or {}).get("teams", {}).get(away_link["key"])

        elo_details = self.store.oddset_elo_details_as_of(cutoff_day)
        elo_alias = {**alias, **_elo_alias_map(self.store)}
        home_elo_link = _link(match.get("home") or "", elo_details, elo_alias)
        away_elo_link = _link(match.get("away") or "", elo_details, elo_alias)
        # En fuzzy Elo-kandidat redovisas för review men blir aldrig ett värde.
        # Saknad Elo är en legitim missing-feature, fel lag är det inte.
        home_elo = (elo_details.get(home_elo_link["key"] or "")
                    if home_elo_link["verified"] else None)
        away_elo = (elo_details.get(away_elo_link["key"] or "")
                    if away_elo_link["verified"] else None)

        home_last = _last_team_date(rows, home_link["key"])
        away_last = _last_team_date(rows, away_link["key"])
        attack_diff = defence_diff = None
        if (home_fit and away_fit and home_fit.get("att", 0) > 0 and
                away_fit.get("att", 0) > 0 and home_fit.get("def", 0) > 0 and
                away_fit.get("def", 0) > 0):
            attack_diff = math.log(home_fit["att"] / away_fit["att"])
            # Högre värde betyder att bortalagets försvar släpper till mer än
            # hemmalagets, alltså en riktad fördel för hemmalaget.
            defence_diff = math.log(away_fit["def"] / home_fit["def"])
        home_adv = None
        if fit and fit.get("home_adv"):
            home_adv = oddset_model._lg_param(fit["home_adv"], league)

        source = {
            "cutoff_day": cutoff_day,
            "strict_day_cutoff": True,
            "input_rows": len(rows),
            "input_xg_rows": sum(row.get("xg_h") is not None and
                                 row.get("xg_a") is not None for row in rows),
            "input_max_date": max((row["date"] for row in rows), default=None),
            "input_hash": _input_fingerprint(rows),
            "elo_as_of_day": cutoff_day,
            "elo_home": ({key: home_elo.get(key) for key in
                          ("club_key", "valid_from", "valid_to", "first_fetched_at")}
                         if home_elo else None),
            "elo_away": ({key: away_elo.get(key) for key in
                          ("club_key", "valid_from", "valid_to", "first_fetched_at")}
                         if away_elo else None),
        }
        features = {
            "attack_log_ratio": attack_diff,
            "defence_log_ratio": defence_diff,
            "home_adv_log": math.log(home_adv) if home_adv else None,
            "effective_n_home": home_fit.get("n") if home_fit else None,
            "effective_n_away": away_fit.get("n") if away_fit else None,
            "data_age_home_days": _age_days(cutoff_day, home_last),
            "data_age_away_days": _age_days(cutoff_day, away_last),
            "elo_home": home_elo.get("elo") if home_elo else None,
            "elo_away": away_elo.get("elo") if away_elo else None,
            "elo_diff": ((home_elo["elo"] - away_elo["elo"])
                         if home_elo and away_elo else None),
        }
        missing = {key: value is None for key, value in features.items()}
        identity = {
            "fit_home": home_link, "fit_away": away_link,
            "elo_home": home_elo_link, "elo_away": away_elo_link,
            "all_fit_links_verified": bool(home_link["verified"] and
                                           away_link["verified"]),
            "all_elo_links_verified": bool(home_elo_link["verified"] and
                                           away_elo_link["verified"]),
            "fit_links_review_free": all(
                link["method"] not in ("substring", "fuzzy")
                for link in (home_link, away_link)),
            "elo_links_review_free": all(
                link["method"] not in ("substring", "fuzzy")
                for link in (home_elo_link, away_elo_link)),
        }
        return {
            "schema": FEATURE_POLICY["schema"],
            "capture_mode": capture_mode,
            "match_id": capture["match_id"], "horizon": capture["horizon"],
            "league": league, "home": match.get("home"), "away": match.get("away"),
            "match_start": capture["match_start"], "as_of": capture["captured_at"],
            "target_at": capture["target_at"],
            "model_signal_version": capture["signal_version"],
            "source": source, "features": features, "missing": missing,
            "identity": identity,
        }

    def capture(self, match: dict, capture: dict, capture_mode: str = "live") -> bool:
        version = feature_version(self.store)
        payload = self.payload(match, capture, capture_mode)
        payload["feature_version"] = version
        payload_json = _canonical_json(payload)
        now = _iso(dt.datetime.now(dt.timezone.utc))
        return self.store.oddset_save_v2_features({
            "match_id": capture["match_id"], "horizon": capture["horizon"],
            "model_signal_version": capture["signal_version"],
            "feature_version": version, "captured_at": capture["captured_at"],
            "match_start": capture["match_start"], "capture_mode": capture_mode,
            "payload_hash": hashlib.sha256(payload_json.encode()).hexdigest(),
            "payload_json": payload_json, "created_at": now,
        })


def backfill_features(store: Storage) -> dict:
    """Rekonstruera äldre ledgercaptures, tydligt spärrade från promotion."""
    matches = {row["id"]: row for row in store.oddset_matches()}
    builder = FeatureBuilder(store)
    added = skipped = 0
    for capture in store.oddset_prediction_captures():
        match = matches.get(capture["match_id"])
        if capture["tier"] != "model" or not match or match["league"] not in LEAGUES:
            skipped += 1
            continue
        added += int(builder.capture(match, capture, "reconstructed"))
    return {"feature_version": feature_version(store), "added": added,
            "skipped": skipped, "total": len(store.oddset_v2_features())}


def _earliest_captures(store: Storage) -> dict[tuple, dict]:
    matches = {row["id"]: row for row in store.oddset_matches()}
    selected = {}
    for capture in store.oddset_prediction_captures():
        match = matches.get(capture["match_id"])
        if not match or match.get("league") not in LEAGUES:
            continue
        key = (capture["match_id"], capture["horizon"], capture["tier"])
        rank = (capture["captured_at"], capture["signal_version"])
        if key not in selected or rank < selected[key][0]:
            selected[key] = (rank, capture)
    return {key: value[1] for key, value in selected.items()}


def _probabilities(rows: list[dict], capture: Optional[dict], tier: str) -> Optional[dict]:
    if not capture:
        return None
    picked = {}
    for row in rows:
        if (row["match_id"] != capture["match_id"] or
                row["horizon"] != capture["horizon"] or
                row["tier"] != tier or
                row["signal_version"] != capture["signal_version"] or
                row["market"] != "1x2" or row["sign"] not in SIGNS):
            continue
        if tier == "sharp" and (row["fair_source"] != "pinnacle" or
                                not row["fair_available"] or not row["fair_fresh"]):
            continue
        picked[row["sign"]] = float(row["fair_prob"])
    if set(picked) != set(SIGNS) or any(picked[sign] <= 0 for sign in SIGNS):
        return None
    total = sum(picked.values())
    return {sign: picked[sign] / total for sign in SIGNS} if total > 0 else None


def _book_odds(rows: list[dict], capture: Optional[dict]) -> Optional[dict]:
    if not capture:
        return None
    picked = {}
    for row in rows:
        if (row["match_id"] == capture["match_id"] and
                row["horizon"] == capture["horizon"] and row["tier"] == "sharp" and
                row["signal_version"] == capture["signal_version"] and
                row["market"] == "1x2" and row["sign"] in SIGNS and
                row.get("book_odds") and row["book_odds"] > 1 and
                row.get("book_available") and row.get("book_fresh")):
            picked[row["sign"]] = float(row["book_odds"])
    return picked if set(picked) == set(SIGNS) else None


def _softmax_log(probabilities: dict) -> dict:
    values = {sign: math.exp(math.log(probabilities[sign])) for sign in SIGNS}
    total = sum(values.values())
    return {sign: values[sign] / total for sign in SIGNS}


def _model_market_residual(model: Optional[dict], sharp: Optional[dict]) -> Optional[dict]:
    """Centrerad log-sannolikhetsskillnad; invariant mot softmaxens konstant."""
    if not model or not sharp:
        return None
    raw = {sign: math.log(model[sign]) - math.log(sharp[sign]) for sign in SIGNS}
    center = sum(raw.values()) / len(raw)
    return {sign: raw[sign] - center for sign in SIGNS}


def _result_index(store: Storage) -> dict[str, list[dict]]:
    return {league: oddset_data.merged_results(store, league) for league in LEAGUES}


def _outcome(store: Storage, match: dict,
             results: dict[str, list[dict]]) -> tuple[Optional[str], Optional[str]]:
    day = _parse_iso(match["start"]).date()
    amap = oddset_data._alias_map(store, match["league"])
    home = amap.get(norm_team(match["home"]), norm_team(match["home"]))
    away = amap.get(norm_team(match["away"]), norm_team(match["away"]))
    candidates = []
    for row in results.get(match["league"], []):
        if row["home"] != home or row["away"] != away:
            continue
        gap = abs((dt.date.fromisoformat(row["date"]) - day).days)
        if gap <= 1 and row.get("hg") is not None and row.get("ag") is not None:
            candidates.append((gap, row["date"], row))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if not candidates or (len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]):
        return None, None
    row = candidates[0][2]
    sign = "1" if row["hg"] > row["ag"] else "2" if row["hg"] < row["ag"] else "X"
    return sign, f"{row['date']}|{row['home']}|{row['away']}"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_dataset(store: Storage, version: Optional[str] = None) -> dict:
    """Bygg alla scope-rader. Saknad data blir issues/fält, aldrig radfilter."""
    from .oddset_ledger import HORIZON_MAX_DELAY
    version = version or feature_version(store)
    matches = {row["id"]: row for row in store.oddset_matches()}
    captures = _earliest_captures(store)
    prediction_rows = store.oddset_prediction_rows()
    feature_rows = {}
    for row in store.oddset_v2_features(version):
        key = (row["match_id"], row["horizon"], row["model_signal_version"])
        feature_rows[key] = {**row, "payload": json.loads(row["payload_json"])}
    results = _result_index(store)
    manifest = load_manifest()
    outer_start = manifest["outer_test"]["start_at"]

    keys = sorted({(match_id, horizon) for match_id, horizon, _ in captures})
    dataset = []
    for match_id, horizon in keys:
        match = matches[match_id]
        sharp_capture = captures.get((match_id, horizon, "sharp"))
        model_capture = captures.get((match_id, horizon, "model"))
        sharp = _probabilities(prediction_rows, sharp_capture, "sharp")
        model = _probabilities(prediction_rows, model_capture, "model")
        book_odds = _book_odds(prediction_rows, sharp_capture)
        feature = (feature_rows.get((match_id, horizon,
                                    model_capture["signal_version"]))
                   if model_capture else None)
        issues = []
        if not sharp_capture:
            issues.append("sharp_capture_missing")
        if not model_capture:
            issues.append("model_capture_missing")
        if sharp_capture and sharp_capture["row_count"] == 0:
            issues.append("sharp_empty_capture")
        if model_capture and model_capture["row_count"] == 0:
            issues.append("model_empty_capture")
        if not sharp:
            issues.append("direct_fresh_sharp_1x2_missing")
        if not model:
            issues.append("model_1x2_missing")
        if not feature:
            issues.append("feature_capture_missing")

        start = _parse_iso(match["start"])
        timing_ok = True
        for tier, capture in (("sharp", sharp_capture), ("model", model_capture)):
            if not capture:
                timing_ok = False
                continue
            if _parse_iso(capture["captured_at"]) >= start:
                issues.append(f"{tier}_post_kickoff")
                timing_ok = False
            max_delay = HORIZON_MAX_DELAY[horizon]
            if capture["delay_minutes"] > max_delay:
                issues.append(f"{tier}_late_capture")
                timing_ok = False
        pair_gap = None
        if sharp_capture and model_capture:
            pair_gap = abs((_parse_iso(sharp_capture["captured_at"]) -
                            _parse_iso(model_capture["captured_at"])).total_seconds()) / 60
            if pair_gap > PAIR_MAX_MINUTES:
                issues.append("capture_pair_too_far_apart")
                timing_ok = False

        identity = _softmax_log(sharp) if sharp else None
        market_residual = _model_market_residual(model, sharp)
        identity_max_abs = (max(abs(identity[s] - sharp[s]) for s in SIGNS)
                            if identity else None)
        if identity_max_abs is not None and identity_max_abs >= 1e-10:
            issues.append("market_identity_failed")
        outcome, result_key = _outcome(store, match, results)
        payload = feature["payload"] if feature else {}
        links_ok = bool(payload.get("identity", {}).get("fit_links_review_free"))
        if feature and not links_ok:
            issues.append("feature_identity_review")
        source = payload.get("source", {})
        leakage_ok = not (source.get("input_max_date") and
                          source["input_max_date"] >= source.get("cutoff_day", ""))
        if not leakage_ok:
            issues.append("result_feature_leakage")
        reconstructed = bool(feature and feature["capture_mode"] != "live")
        if reconstructed:
            issues.append("features_reconstructed")

        research_ready = bool(sharp and model and feature and timing_ok and
                              leakage_ok and identity_max_abs is not None and
                              identity_max_abs < 1e-10 and links_ok)
        promotion_ready = bool(research_ready and not reconstructed)
        split = "outer_test" if match["start"] >= outer_start else "development"
        dataset.append({
            "match_id": match_id, "league": match["league"],
            "season": int(match["start"][:4]), "home": match["home"],
            "away": match["away"], "match_start": match["start"],
            "horizon": horizon, "split": split,
            "sharp_captured_at": sharp_capture["captured_at"] if sharp_capture else None,
            "model_captured_at": model_capture["captured_at"] if model_capture else None,
            "capture_pair_gap_minutes": pair_gap,
            "sharp_version": sharp_capture["signal_version"] if sharp_capture else None,
            "model_version": model_capture["signal_version"] if model_capture else None,
            "feature_version": version, "feature_capture_mode": (
                feature["capture_mode"] if feature else None),
            "sharp": sharp, "model": model, "book_odds": book_odds,
            "model_market_log_residual": market_residual,
            "features": payload.get("features"), "feature_missing": payload.get("missing"),
            "feature_source": source or None, "feature_identity": payload.get("identity"),
            "outcome": outcome, "result_key": result_key,
            "identity": identity, "identity_max_abs": identity_max_abs,
            "research_ready": research_ready, "promotion_ready": promotion_ready,
            "evaluation_ready": bool(promotion_ready and outcome),
            "issues": sorted(set(issues)),
        })
    digest = _hash(dataset)
    return {"schema": 2, "feature_version": version, "manifest": manifest,
            "rows": dataset, "dataset_hash": digest}


def _coverage(dataset: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in dataset:
        groups[(row["league"], row["season"], row["horizon"])].append(row)
    output = []
    for (league, season, horizon), rows in sorted(groups.items()):
        n = len(rows)
        count = lambda predicate: sum(bool(predicate(row)) for row in rows)
        output.append({
            "league": league, "season": season, "horizon": horizon, "rows": n,
            "sharp": count(lambda row: row["sharp"]),
            "model": count(lambda row: row["model"]),
            "features": count(lambda row: row["features"]),
            "fit_complete": count(lambda row: row["features"] and
                                  row["features"].get("attack_log_ratio") is not None and
                                  row["features"].get("defence_log_ratio") is not None),
            "elo_complete": count(lambda row: row["features"] and
                                  row["features"].get("elo_diff") is not None),
            "live_features": count(lambda row: row["feature_capture_mode"] == "live"),
            "outcomes": count(lambda row: row["outcome"]),
            "research_ready": count(lambda row: row["research_ready"]),
            "promotion_ready": count(lambda row: row["promotion_ready"]),
        })
    return output


def _feature_coverage(dataset: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for row in dataset:
        groups[(row["league"], row["season"], row["horizon"])].append(row)
    output = []
    for (league, season, horizon), rows in sorted(groups.items()):
        names = sorted({name for row in rows for name in (row.get("features") or {})})
        for name in names:
            present = sum((row.get("features") or {}).get(name) is not None for row in rows)
            output.append({"league": league, "season": season, "horizon": horizon,
                           "feature": name, "present": present, "rows": len(rows),
                           "coverage": round(present / len(rows), 4)})
        for name, getter in (
                ("sharp_market", lambda row: row.get("sharp")),
                ("standalone_model", lambda row: row.get("model")),
                ("model_market_log_residual",
                 lambda row: row.get("model_market_log_residual"))):
            present = sum(getter(row) is not None for row in rows)
            output.append({"league": league, "season": season, "horizon": horizon,
                           "feature": name, "present": present, "rows": len(rows),
                           "coverage": round(present / len(rows), 4)})
    return output


def _opportunities(store: Storage, now: dt.datetime) -> list[dict]:
    from .oddset_ledger import HORIZONS, HORIZON_MAX_DELAY
    captures = defaultdict(list)
    for row in store.oddset_prediction_captures():
        captures[(row["match_id"], row["horizon"], row["tier"])].append(row)
    start_at = _parse_iso(COLLECTION_START)
    groups = defaultdict(lambda: {"opportunities": 0, "sharp": 0, "model": 0,
                                 "sharp_timely": 0, "model_timely": 0})
    for match in store.oddset_matches():
        if match.get("league") not in LEAGUES or not match.get("start"):
            continue
        start = _parse_iso(match["start"])
        for horizon, minutes in HORIZONS:
            target = start - dt.timedelta(minutes=minutes)
            settled = target + dt.timedelta(minutes=HORIZON_MAX_DELAY[horizon])
            if target < start_at or settled > now:
                continue
            group = groups[(match["league"], start.year, horizon)]
            group["opportunities"] += 1
            for tier in ("sharp", "model"):
                found = captures.get((match["id"], horizon, tier), [])
                group[tier] += int(bool(found))
                group[f"{tier}_timely"] += int(any(
                    row["delay_minutes"] <= HORIZON_MAX_DELAY[horizon]
                    and _parse_iso(row["captured_at"]) < start for row in found))
    return [{"league": key[0], "season": key[1], "horizon": key[2], **value}
            for key, value in sorted(groups.items())]


def audit(store: Storage, now: Optional[dt.datetime] = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    built = build_dataset(store)
    rows = built["rows"]
    identity_values = [row["identity_max_abs"] for row in rows
                       if row["identity_max_abs"] is not None]
    leak_rows = [row["match_id"] + ":" + row["horizon"] for row in rows
                 if "result_feature_leakage" in row["issues"] or
                 any(issue.endswith("post_kickoff") for issue in row["issues"])]
    resolved = [row for row in rows if row["outcome"] and row["sharp"]]
    logloss_delta = []
    for row in resolved:
        sign = row["outcome"]
        sharp_loss = -math.log(row["sharp"][sign])
        identity_loss = -math.log(row["identity"][sign])
        logloss_delta.append(identity_loss - sharp_loss)
    outer_matches = {row["match_id"] for row in rows
                     if row["split"] == "outer_test" and row["evaluation_ready"]}
    outer_by_league = {league: len({row["match_id"] for row in rows
                                    if row["league"] == league and
                                    row["split"] == "outer_test" and
                                    row["evaluation_ready"]})
                       for league in LEAGUES}
    split_by_match = defaultdict(set)
    for row in rows:
        split_by_match[row["match_id"]].add(row["split"])
    split_overlap = sorted(match_id for match_id, splits in split_by_match.items()
                           if len(splits) > 1)
    return {
        "feature_version": built["feature_version"],
        "dataset_hash": built["dataset_hash"], "rows": len(rows),
        "unique_matches": len({row["match_id"] for row in rows}),
        "coverage": _coverage(rows), "feature_coverage": _feature_coverage(rows),
        "opportunities": _opportunities(store, now),
        "checks": {
            "post_kickoff_or_feature_leak_rows": leak_rows,
            "identity_rows": len(identity_values),
            "identity_max_abs": max(identity_values, default=None),
            "identity_logloss_max_abs": max((abs(v) for v in logloss_delta), default=None),
            "duplicate_match_horizon_rows": len(rows) - len({
                (row["match_id"], row["horizon"]) for row in rows}),
            "train_test_overlap_matches": split_overlap,
        },
        "readiness": {
            "research_ready_rows": sum(row["research_ready"] for row in rows),
            "promotion_ready_rows": sum(row["promotion_ready"] for row in rows),
            "evaluation_ready_rows": sum(row["evaluation_ready"] for row in rows),
            "outer_test_unique_matches": len(outer_matches),
            "outer_test_by_league": outer_by_league,
            "outer_threshold_total": built["manifest"]["outer_test"]["minimum_matches"],
            "outer_threshold_per_league": built["manifest"]["outer_test"][
                "minimum_matches_per_league"],
        },
    }


def format_audit(report: dict) -> str:
    lines = [
        f"V2-A {report['feature_version']} · dataset {report['dataset_hash'][:12]}",
        f"rader {report['rows']} · matcher {report['unique_matches']} · "
        f"research-ready {report['readiness']['research_ready_rows']} · "
        f"promotion-ready {report['readiness']['promotion_ready_rows']}",
    ]
    for row in report["coverage"]:
        lines.append(
            f"{row['league']:12} {row['season']} {row['horizon']:3} n={row['rows']:3} · "
            f"sharp {row['sharp']:3} · model {row['model']:3} · fit {row['fit_complete']:3} · "
            f"Elo {row['elo_complete']:3} · live {row['live_features']:3} · "
            f"facit {row['outcomes']:3}")
    checks = report["checks"]
    lines.append(
        f"identitet max |Δp|={checks['identity_max_abs']} · "
        f"max |Δlogloss|={checks['identity_logloss_max_abs']} · "
        f"läckrader={len(checks['post_kickoff_or_feature_leak_rows'])} · "
        f"dubbletter={checks['duplicate_match_horizon_rows']}")
    return "\n".join(lines)
