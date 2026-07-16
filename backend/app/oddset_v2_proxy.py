"""Historisk, icke-promoverbar utvecklingsproxy för modell v2-B.

Football-data-filerna för SWE/NOR har i praktiken Pinnacle-closing men saknar
opening. Closing används därför som ett extra svårt marknads-upper-bound för att
hitta kodfel och kontrollera om ridge-idén överhuvudtaget är rimlig. Raderna kan
aldrig uppfylla V2:s fasta horisont- eller outer-testkrav.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from typing import Optional

from .analysis import _power_probs
from . import oddset_backtest, oddset_data, oddset_model, oddset_v2
from .oddset_v2_model import SIGNS
from .storage import Storage


PROXY_POLICY = {
    "schema": 1,
    "market": "football-data Pinnacle closing (PSCH/PSCD/PSCA)",
    "timing": "after all target horizons; upper-bound stress test only",
    "history_cutoff": "strictly earlier match date",
    "temperature": "current in-sample league temperature",
    "sharp_total_anchor": False,
    "features": "same semantic v2.1 fields, retrospectively reconstructed",
}


def _temperature(store: Storage, league: str) -> float:
    try:
        return float(json.loads(store.meta_get(f"oddset_cal:{league}") or "{}").get("t")
                     or 1.0)
    except (TypeError, ValueError):
        return 1.0


def _overlay_xg(store: Storage, league: str, rows: list[dict]) -> int:
    xg = {(row["date"], row["home"], row["away"]):
          (row.get("xg_h"), row.get("xg_a"))
          for row in oddset_data.merged_results(store, league)
          if row.get("xg_h") is not None and row.get("xg_a") is not None}
    hits = 0
    for row in rows:
        values = xg.get((row["date"], row["home"], row["away"]))
        if values:
            row["xg_h"], row["xg_a"] = values
            hits += 1
    return hits


def _last_date(rows: list[dict], team: Optional[str]) -> Optional[str]:
    if not team:
        return None
    dates = [row["date"] for row in rows if team in (row["home"], row["away"])]
    return max(dates) if dates else None


def _age(day: str, source: Optional[str]) -> Optional[int]:
    return ((dt.date.fromisoformat(day) - dt.date.fromisoformat(source)).days
            if source else None)


def _verified_elo(store: Storage, league: str, day: str,
                  home: str, away: str) -> tuple[Optional[float], Optional[float], dict]:
    details = store.oddset_elo_details_as_of(day)
    aliases = {**oddset_data._alias_map(store, league),
               **oddset_v2._elo_alias_map(store)}
    home_link = oddset_v2._link(home, details, aliases)
    away_link = oddset_v2._link(away, details, aliases)
    home_row = details.get(home_link["key"] or "") if home_link["verified"] else None
    away_row = details.get(away_link["key"] or "") if away_link["verified"] else None
    return ((float(home_row["elo"]) if home_row else None),
            (float(away_row["elo"]) if away_row else None),
            {"home": home_link, "away": away_link})


def _fit_features(fit: dict, history: list[dict], league: str, day: str,
                  home: str, away: str, elo_home: Optional[float],
                  elo_away: Optional[float]) -> tuple[dict, dict]:
    home_key = oddset_model._find_team(fit, home)
    away_key = oddset_model._find_team(fit, away)
    home_fit = fit["teams"].get(home_key or "")
    away_fit = fit["teams"].get(away_key or "")
    attack = defence = None
    if (home_fit and away_fit and home_fit.get("att", 0) > 0 and
            away_fit.get("att", 0) > 0 and home_fit.get("def", 0) > 0 and
            away_fit.get("def", 0) > 0):
        attack = math.log(home_fit["att"] / away_fit["att"])
        defence = math.log(away_fit["def"] / home_fit["def"])
    home_adv = oddset_model._lg_param(fit["home_adv"], league)
    home_last, away_last = _last_date(history, home_key), _last_date(history, away_key)
    features = {
        "attack_log_ratio": attack, "defence_log_ratio": defence,
        "home_adv_log": math.log(home_adv) if home_adv else None,
        "effective_n_home": home_fit.get("n") if home_fit else None,
        "effective_n_away": away_fit.get("n") if away_fit else None,
        "data_age_home_days": _age(day, home_last),
        "data_age_away_days": _age(day, away_last),
        "elo_home": elo_home, "elo_away": elo_away,
        "elo_diff": ((elo_home - elo_away)
                     if elo_home is not None and elo_away is not None else None),
    }
    identity = {
        "fit_home": home_key, "fit_away": away_key,
        "fit_exact": home_key == home and away_key == away,
    }
    return features, identity


def _residual(model: dict, sharp: dict) -> dict:
    raw = {sign: math.log(model[sign]) - math.log(sharp[sign]) for sign in SIGNS}
    center = sum(raw.values()) / len(raw)
    return {sign: raw[sign] - center for sign in SIGNS}


def build_historical_proxy(store: Storage, min_season: int = 2022,
                           eval_from: str = "2023-01-01",
                           price_timing: str = "close") -> dict:
    if price_timing not in ("open", "close"):
        raise ValueError("price_timing måste vara open eller close")
    dataset_kind = ("historical_opening_proxy" if price_timing == "open" else
                    "historical_closing_upper_bound")
    output, coverage = [], {}
    for league in oddset_v2.LEAGUES:
        rows = oddset_backtest.fetch_rows(league, min_season)
        for row in rows:
            row["league"] = league
        xg_hits = _overlay_xg(store, league, rows)
        history_source = list(rows)
        for pool_league in oddset_model.FIT_POOLS.get(league, (league,)):
            if pool_league != league:
                history_source.extend(oddset_data.merged_results(store, pool_league))
        history_source.sort(key=lambda row: (row["date"], row["home"], row["away"]))
        eval_rows = [row for row in rows if row["date"] >= eval_from]
        dates = sorted({row["date"] for row in eval_rows})
        pointer, history = 0, []
        temperature = _temperature(store, league)
        before = len(output)
        missing_price = missing_model = identity_review = 0
        for day in dates:
            while (pointer < len(history_source) and
                   history_source[pointer]["date"] < day):
                history.append(history_source[pointer])
                pointer += 1
            fit = oddset_model.fit_league(
                history, now=dt.date.fromisoformat(day), iters=oddset_model.FIT_ITER)
            if not fit:
                continue
            elo_for_prior = oddset_data.get_elo(store, as_of=day)
            for row in (item for item in eval_rows if item["date"] == day):
                prices = row.get(f"ps_{price_timing}")
                if not prices:
                    missing_price += 1
                    continue
                sharp = _power_probs({sign: 1 / price
                                      for sign, price in zip(SIGNS, prices)})
                elo_home, elo_away, elo_identity = _verified_elo(
                    store, league, day, row["home"], row["away"])
                features, fit_identity = _fit_features(
                    fit, history, league, day, row["home"], row["away"],
                    elo_home, elo_away)
                if not fit_identity["fit_exact"]:
                    identity_review += 1
                oddset_model._ensure_priors(fit, elo_for_prior,
                                             (row["home"], row["away"]))
                mus = oddset_model.predict(fit, row["home"], row["away"], league=league)
                if not mus:
                    missing_model += 1
                    continue
                matrix = oddset_model.temper(
                    oddset_model.dc_matrix(mus[0], mus[1]), temperature)
                model = oddset_model.matrix_1x2(matrix)
                outcome = ("1" if row["hg"] > row["ag"] else
                           "2" if row["hg"] < row["ag"] else "X")
                output.append({
                    "match_id": f"proxy:{league}:{day}:{row['home']}:{row['away']}",
                    "league": league, "season": int(day[:4]),
                    "home": row["home"], "away": row["away"],
                    "match_start": f"{day}T12:00:00Z",
                    "horizon": f"proxy_{price_timing}",
                    "split": "development_proxy", "dataset_kind": dataset_kind,
                    "sharp": sharp, "model": model,
                    "book_odds": dict(zip(SIGNS, prices)),
                    "model_market_log_residual": _residual(model, sharp),
                    "features": features, "outcome": outcome,
                    "research_ready": True, "promotion_ready": False,
                    "feature_capture_mode": "retrospective_proxy",
                    "feature_identity": {"fit": fit_identity, "elo": elo_identity},
                    "feature_source": {"cutoff_day": day,
                                       "history_rows": len(history),
                                       "history_xg_rows": sum(
                                           item.get("xg_h") is not None for item in history),
                                       "temperature": temperature},
                    "issues": (["pinnacle_opening_timestamp_unknown"]
                               if price_timing == "open" else
                               ["pinnacle_closing_is_after_target_horizons"]) + [
                               "retrospective_feature_reconstruction",
                               "sharp_total_anchor_unavailable",
                               "temperature_in_sample"],
                })
        coverage[league] = {
            "source_rows": len(rows), "eval_rows": len(eval_rows),
            "price_timing": price_timing, "price_rows": len(output) - before,
            "missing_price": missing_price, "missing_model": missing_model,
            "xg_overlay_rows": xg_hits, "fit_identity_review": identity_review,
        }
    output.sort(key=lambda row: (row["match_start"], row["match_id"]))
    return {"policy": PROXY_POLICY, "rows": output, "coverage": coverage}
