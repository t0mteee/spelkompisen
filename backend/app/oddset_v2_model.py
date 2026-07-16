"""Modell v2-B: marknadsankrad multinomial ridge och nested walk-forward.

Marknaden är en offset, inte en vanlig feature. Med alla koefficienter noll är
prediktionen därför exakt Pinnacles devigade 1X2. Modulen tränar inget vid
import och påverkar aldrig live-modellen; den används enbart av backtestet tills
V2-C uttryckligen aktiveras.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from typing import Optional


SIGNS = ("1", "X", "2")
REFERENCE_SIGN = "X"
CONTINUOUS_FEATURES = (
    "standalone_logit_1x",
    "standalone_logit_2x",
    "attack_log_ratio",
    "defence_log_ratio",
    "home_adv_log",
    "effective_history_log",
    "data_age_log",
    "elo_diff",
)
LAMBDA_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
FOLD_POLICY = {
    "outer_min_train_matches": 240,
    "outer_test_matches": 60,
    "inner_min_train_matches": 120,
    "inner_validation_matches": 40,
    "inner_folds": 3,
    "same_utc_date_is_one_block": True,
}
MODEL_POLICY = {
    "schema": 1,
    "family": "multinomial-ridge-market-offset-reference-X",
    "features": CONTINUOUS_FEATURES,
    "missing": "training-mean-neutral-standardized-plus-indicator",
    "league": "eliteserien-indicator-ridge-shrunk-to-common",
    "regularization": LAMBDA_GRID,
    "folds": FOLD_POLICY,
    "judgment": {
        "minimum_outer_matches": 300,
        "minimum_outer_per_league": 100,
        "delta_logloss_ci90_lower": ">0",
        "league_delta_logloss_min": -0.005,
        "brier_delta_max": 0.002,
        "new_abs_calibration_bias_max": 0.03,
        "incomplete_feature_delta_logloss": ">0",
    },
    "descriptive_bet_policy": {"edge_min": 0.02, "q_min": 0.015},
}
BOOTSTRAP_ITERS = 2000


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def policy_version() -> str:
    digest = hashlib.sha256(_canonical(MODEL_POLICY).encode()).hexdigest()[:8]
    return f"v2b-{digest}"


def _finite(value) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _market_residual(row: dict) -> Optional[dict[str, float]]:
    residual = row.get("model_market_log_residual")
    if residual and all(_finite(residual.get(sign)) is not None for sign in SIGNS):
        return {sign: float(residual[sign]) for sign in SIGNS}
    model, sharp = row.get("model"), row.get("sharp")
    if not model or not sharp:
        return None
    if any(_finite((model or {}).get(sign)) is None or
           _finite((sharp or {}).get(sign)) is None or
           model[sign] <= 0 or sharp[sign] <= 0 for sign in SIGNS):
        return None
    raw = {sign: math.log(model[sign]) - math.log(sharp[sign]) for sign in SIGNS}
    center = sum(raw.values()) / len(raw)
    return {sign: raw[sign] - center for sign in SIGNS}


def raw_features(row: dict) -> dict[str, Optional[float]]:
    """De förregistrerade v2.1-features, utan imputation eller standardisering."""
    features = row.get("features") or {}
    residual = _market_residual(row)
    n_home = _finite(features.get("effective_n_home"))
    n_away = _finite(features.get("effective_n_away"))
    ages = [_finite(features.get("data_age_home_days")),
            _finite(features.get("data_age_away_days"))]
    age_values = [value for value in ages if value is not None and value >= 0]
    effective = (math.log1p(min(n_home, n_away))
                 if n_home is not None and n_away is not None and
                 n_home >= 0 and n_away >= 0 else None)
    return {
        "standalone_logit_1x": ((residual["1"] - residual["X"])
                                 if residual else None),
        "standalone_logit_2x": ((residual["2"] - residual["X"])
                                 if residual else None),
        "attack_log_ratio": _finite(features.get("attack_log_ratio")),
        "defence_log_ratio": _finite(features.get("defence_log_ratio")),
        "home_adv_log": _finite(features.get("home_adv_log")),
        "effective_history_log": effective,
        "data_age_log": math.log1p(max(age_values)) if age_values else None,
        "elo_diff": _finite(features.get("elo_diff")),
    }


def fit_preprocessor(rows: list[dict]) -> dict:
    """Fitta mean/scale enbart på träningsfönstret."""
    raw = [raw_features(row) for row in rows]
    stats = {}
    for name in CONTINUOUS_FEATURES:
        values = [item[name] for item in raw if item[name] is not None]
        mean = sum(values) / len(values) if values else 0.0
        variance = (sum((value - mean) ** 2 for value in values) / len(values)
                    if values else 0.0)
        scale = math.sqrt(variance)
        stats[name] = {"mean": mean, "scale": scale if scale > 1e-9 else 1.0,
                       "observed": len(values), "missing": len(rows) - len(values)}
    names = (["intercept"] + list(CONTINUOUS_FEATURES) +
             [f"{name}__missing" for name in CONTINUOUS_FEATURES] +
             ["league_eliteserien"])
    return {"schema": 1, "continuous": stats, "feature_names": names,
            "n_fit_rows": len(rows)}


def transform(row: dict, preprocessor: dict) -> list[float]:
    raw = raw_features(row)
    values = [1.0]
    for name in CONTINUOUS_FEATURES:
        stat, value = preprocessor["continuous"][name], raw[name]
        values.append(0.0 if value is None else (value - stat["mean"]) / stat["scale"])
    values.extend(1.0 if raw[name] is None else 0.0 for name in CONTINUOUS_FEATURES)
    values.append(1.0 if row.get("league") == "eliteserien" else 0.0)
    return values


def _probabilities(sharp: dict, beta_1: list[float], beta_2: list[float],
                   x: list[float]) -> dict[str, float]:
    if any(_finite(sharp.get(sign)) is None or sharp[sign] <= 0 for sign in SIGNS):
        raise ValueError("sharp-sannolikheter måste vara positiva 1/X/2")
    base_1 = math.log(sharp["1"] / sharp["X"])
    base_2 = math.log(sharp["2"] / sharp["X"])
    eta_1 = base_1 + sum(beta * value for beta, value in zip(beta_1, x))
    eta_2 = base_2 + sum(beta * value for beta, value in zip(beta_2, x))
    pivot = max(0.0, eta_1, eta_2)
    exp_x = math.exp(-pivot)
    exp_1 = math.exp(eta_1 - pivot)
    exp_2 = math.exp(eta_2 - pivot)
    total = exp_1 + exp_x + exp_2
    return {"1": exp_1 / total, "X": exp_x / total, "2": exp_2 / total}


def identity_predict(sharp: dict) -> dict[str, float]:
    return _probabilities(sharp, [], [], [])


def predict(model: dict, row: dict) -> dict[str, float]:
    return _probabilities(row["sharp"], model["beta_1"], model["beta_2"],
                          transform(row, model["preprocessor"]))


def _penalty_mask(size: int) -> list[float]:
    # Global 1/X/2-intercepten får vara opåverkad; alla features och
    # ligaindikatorn krymps. Numerisk jitter läggs separat även på intercept.
    return [0.0] + [1.0] * (size - 1)


def _objective(rows: list[dict], xs: list[list[float]], beta: list[float],
               penalty: float) -> float:
    size = len(xs[0])
    beta_1, beta_2 = beta[:size], beta[size:]
    loss = 0.0
    for row, x in zip(rows, xs):
        probabilities = _probabilities(row["sharp"], beta_1, beta_2, x)
        loss -= math.log(max(probabilities[row["outcome"]], 1e-15))
    masks = _penalty_mask(size) * 2
    ridge = 0.5 * penalty * sum(mask * value * value
                               for mask, value in zip(masks, beta))
    return loss / len(rows) + ridge


def _linear_solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gauss-Jordan med pivotering; Hessianen är liten (36×36 i v2.1)."""
    n = len(vector)
    augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singulär ridge-Hessian")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if abs(factor) < 1e-18:
                continue
            augmented[row] = [value - factor * pivot_value
                              for value, pivot_value in
                              zip(augmented[row], augmented[column])]
    return [augmented[index][-1] for index in range(n)]


def fit(rows: list[dict], penalty: float, max_iter: int = 35,
        tolerance: float = 1e-8) -> dict:
    """Fitta ridge med Newtonsteg och backtracking; helt deterministiskt."""
    if penalty < 0:
        raise ValueError("ridge-styrkan får inte vara negativ")
    train = [row for row in rows if row.get("outcome") in SIGNS and row.get("sharp")]
    if len(train) < 3:
        raise ValueError("minst tre märkta träningsmatcher krävs")
    preprocessor = fit_preprocessor(train)
    xs = [transform(row, preprocessor) for row in train]
    size, total_size = len(xs[0]), 2 * len(xs[0])
    beta = [0.0] * total_size
    masks = _penalty_mask(size) * 2
    converged = False
    objective = _objective(train, xs, beta, penalty)
    iterations = 0
    for iteration in range(max_iter):
        gradient = [0.0] * total_size
        hessian = [[0.0] * total_size for _ in range(total_size)]
        for row, x in zip(train, xs):
            probabilities = _probabilities(
                row["sharp"], beta[:size], beta[size:], x)
            p1, p2 = probabilities["1"], probabilities["2"]
            y1, y2 = float(row["outcome"] == "1"), float(row["outcome"] == "2")
            for j, xj in enumerate(x):
                gradient[j] += (p1 - y1) * xj
                gradient[size + j] += (p2 - y2) * xj
                for k, xk in enumerate(x):
                    xx = xj * xk
                    hessian[j][k] += p1 * (1 - p1) * xx
                    hessian[size + j][size + k] += p2 * (1 - p2) * xx
                    cross = -p1 * p2 * xx
                    hessian[j][size + k] += cross
                    hessian[size + j][k] += cross
        n = len(train)
        for j in range(total_size):
            gradient[j] = gradient[j] / n + penalty * masks[j] * beta[j]
            for k in range(total_size):
                hessian[j][k] /= n
            hessian[j][j] += penalty * masks[j] + 1e-8
        step = _linear_solve(hessian, gradient)
        max_step = max(abs(value) for value in step)
        if max_step < tolerance:
            converged = True
            iterations = iteration
            break
        factor = 1.0
        accepted = False
        while factor >= 1 / 1024:
            candidate = [value - factor * delta for value, delta in zip(beta, step)]
            candidate_objective = _objective(train, xs, candidate, penalty)
            if candidate_objective < objective - 1e-12:
                beta, objective, accepted = candidate, candidate_objective, True
                break
            factor /= 2
        iterations = iteration + 1
        if not accepted:
            converged = max_step < 1e-5
            break
    model = {
        "policy_version": policy_version(), "penalty": penalty,
        "preprocessor": preprocessor, "beta_1": beta[:size], "beta_2": beta[size:],
        "objective": objective, "iterations": iterations, "converged": converged,
        "n_train": len(train),
    }
    model["model_hash"] = hashlib.sha256(_canonical(model).encode()).hexdigest()[:12]
    return model


def _date_blocks(rows: list[dict]) -> list[list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row["match_start"][:10]].append(row)
    return [sorted(groups[day], key=lambda row: row["match_id"])
            for day in sorted(groups)]


def _folds(rows: list[dict], min_train: int, test_size: int) -> list[dict]:
    """Expanderande walk-forward; samma UTC-matchdag delas aldrig."""
    blocks = _date_blocks(rows)
    folds, train_end = [], 0
    train_count = 0
    while train_end < len(blocks) and train_count < min_train:
        train_count += len(blocks[train_end])
        train_end += 1
    while train_end < len(blocks):
        test_end, count = train_end, 0
        while test_end < len(blocks) and count < test_size:
            count += len(blocks[test_end])
            test_end += 1
        train = [row for block in blocks[:train_end] for row in block]
        test = [row for block in blocks[train_end:test_end] for row in block]
        if test:
            folds.append({"train": train, "test": test})
        train_end = test_end
    return folds


def _logloss(probabilities: dict, outcome: str) -> float:
    return -math.log(max(probabilities[outcome], 1e-15))


def select_penalty(rows: list[dict], lambdas: tuple[float, ...] = LAMBDA_GRID,
                   policy: dict = FOLD_POLICY) -> dict:
    inner = _folds(rows, policy["inner_min_train_matches"],
                   policy["inner_validation_matches"])
    inner = inner[-policy["inner_folds"]:]
    if not inner:
        raise ValueError("för få träningsmatcher för inre walk-forward")
    totals = {value: [0.0, 0] for value in lambdas}
    fold_rows = []
    for index, fold in enumerate(inner):
        scores = {}
        for value in lambdas:
            model = fit(fold["train"], value)
            loss = sum(_logloss(predict(model, row), row["outcome"])
                       for row in fold["test"])
            totals[value][0] += loss
            totals[value][1] += len(fold["test"])
            scores[value] = loss / len(fold["test"])
        fold_rows.append({
            "fold": index, "n_train": len(fold["train"]),
            "n_validation": len(fold["test"]),
            "train_end": max(row["match_start"] for row in fold["train"]),
            "validation_start": min(row["match_start"] for row in fold["test"]),
            "scores": scores,
        })
    means = {value: total / count for value, (total, count) in totals.items()}
    selected = min(lambdas, key=lambda value: (means[value], -value))
    return {"selected": selected, "scores": means, "folds": fold_rows}


def nested_walk_forward(rows: list[dict], horizon: Optional[str] = None,
                        lambdas: tuple[float, ...] = LAMBDA_GRID,
                        policy: dict = FOLD_POLICY) -> dict:
    eligible = [row for row in rows if row.get("outcome") in SIGNS and
                row.get("sharp") and (horizon is None or row.get("horizon") == horizon)]
    ordered = sorted(eligible, key=lambda row: (row["match_start"], row["match_id"]))
    ids = [row["match_id"] for row in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("walk-forward kräver en rad per unik match och horisont")
    outer = _folds(ordered, policy["outer_min_train_matches"],
                   policy["outer_test_matches"])
    predictions, fold_report = [], []
    for index, fold in enumerate(outer):
        selection = select_penalty(fold["train"], lambdas, policy)
        model = fit(fold["train"], selection["selected"])
        train_ids = {row["match_id"] for row in fold["train"]}
        test_ids = {row["match_id"] for row in fold["test"]}
        if train_ids & test_ids:
            raise AssertionError("match finns i både train och test")
        for row in fold["test"]:
            raw = raw_features(row)
            predictions.append({
                "match_id": row["match_id"], "match_start": row["match_start"],
                "league": row["league"], "horizon": row.get("horizon"),
                "outcome": row["outcome"], "sharp": row["sharp"],
                "v2": predict(model, row), "fold": index,
                "book_odds": row.get("book_odds"),
                "penalty": selection["selected"],
                "complete_features": all(value is not None for value in raw.values()),
                "issues": row.get("issues") or [],
            })
        fold_report.append({
            "fold": index, "n_train": len(fold["train"]),
            "n_test": len(fold["test"]),
            "train_start": min(row["match_start"] for row in fold["train"]),
            "train_end": max(row["match_start"] for row in fold["train"]),
            "test_start": min(row["match_start"] for row in fold["test"]),
            "test_end": max(row["match_start"] for row in fold["test"]),
            "selected_penalty": selection["selected"],
            "inner_scores": selection["scores"], "inner_folds": selection["folds"],
            "model_hash": model["model_hash"], "converged": model["converged"],
        })
    return {"policy_version": policy_version(), "horizon": horizon,
            "n_eligible": len(ordered), "n_predictions": len(predictions),
            "predictions": predictions, "folds": fold_report,
            "penalty_counts": dict(Counter(row["penalty"] for row in predictions))}


def _bootstrap_delta(predictions: list[dict], iters: int = BOOTSTRAP_ITERS) \
        -> Optional[list[float]]:
    blocks = defaultdict(list)
    for row in predictions:
        blocks[row["match_id"]].append(
            _logloss(row["sharp"], row["outcome"]) -
            _logloss(row["v2"], row["outcome"]))
    if len(blocks) < 5:
        return None
    groups = list(blocks.values())
    seed_value = "|".join(sorted(blocks))
    seed = int(hashlib.sha256(seed_value.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        sample = [rng.choice(groups) for _ in groups]
        flat = [value for group in sample for value in group]
        means.append(sum(flat) / len(flat))
    means.sort()
    return [means[int(iters * 0.05)],
            means[min(iters - 1, int(iters * 0.95))]]


def _metric_block(predictions: list[dict]) -> dict:
    if not predictions:
        return {"n": 0, "n_matches": 0, "delta_logloss": None,
                "delta_logloss_ci90": None, "brier_sharp": None,
                "brier_v2": None, "brier_delta": None,
                "accuracy_sharp": None, "accuracy_v2": None,
                "bets": 0, "bet_hit": None, "bet_roi": None}
    deltas, brier_sharp, brier_v2 = [], [], []
    for row in predictions:
        outcome = row["outcome"]
        deltas.append(_logloss(row["sharp"], outcome) -
                      _logloss(row["v2"], outcome))
        brier_sharp.append(sum((row["sharp"][sign] - float(sign == outcome)) ** 2
                               for sign in SIGNS))
        brier_v2.append(sum((row["v2"][sign] - float(sign == outcome)) ** 2
                            for sign in SIGNS))
    bets = []
    for row in predictions:
        prices = row.get("book_odds") or {}
        for sign in SIGNS:
            odds = _finite(prices.get(sign))
            if odds is None or odds <= 1:
                continue
            edge = row["v2"][sign] * odds - 1
            quality = edge / max(odds - 1, 0.01)
            if edge >= 0.02 and quality >= 0.015:
                won = row["outcome"] == sign
                bets.append((won, odds - 1 if won else -1.0))
    return {
        "n": len(predictions), "n_matches": len({row["match_id"] for row in predictions}),
        "delta_logloss": sum(deltas) / len(deltas),
        "delta_logloss_ci90": _bootstrap_delta(predictions),
        "brier_sharp": sum(brier_sharp) / len(brier_sharp),
        "brier_v2": sum(brier_v2) / len(brier_v2),
        "brier_delta": (sum(brier_v2) - sum(brier_sharp)) / len(predictions),
        "accuracy_sharp": sum(max(row["sharp"], key=row["sharp"].get) == row["outcome"]
                              for row in predictions) / len(predictions),
        "accuracy_v2": sum(max(row["v2"], key=row["v2"].get) == row["outcome"]
                           for row in predictions) / len(predictions),
        "bets": len(bets),
        "bet_hit": (sum(won for won, _ in bets) / len(bets) if bets else None),
        "bet_roi": (sum(pnl for _, pnl in bets) / len(bets) if bets else None),
    }


def evaluation_report(walk: dict, dataset_kind: str) -> dict:
    predictions = walk["predictions"]
    total = _metric_block(predictions)
    by_league = {league: _metric_block(
        [row for row in predictions if row["league"] == league])
        for league in sorted({row["league"] for row in predictions})}
    calibration = {}
    for sign in SIGNS:
        if not predictions:
            calibration[sign] = {"actual": None, "sharp": None, "v2": None,
                                 "sharp_bias": None, "v2_bias": None,
                                 "new_abs_bias": None}
            continue
        actual = sum(row["outcome"] == sign for row in predictions) / len(predictions)
        sharp = sum(row["sharp"][sign] for row in predictions) / len(predictions)
        v2 = sum(row["v2"][sign] for row in predictions) / len(predictions)
        calibration[sign] = {
            "actual": actual, "sharp": sharp, "v2": v2,
            "sharp_bias": sharp - actual, "v2_bias": v2 - actual,
            "new_abs_bias": abs(v2 - actual) - abs(sharp - actual),
        }
    incomplete = [row for row in predictions if not row["complete_features"]]
    complete = [row for row in predictions if row["complete_features"]]
    reasons = []
    if any(not fold.get("converged") for fold in walk["folds"]):
        reasons.append("ridge_fit_not_converged")
    if dataset_kind != "live_outer":
        reasons.append("dataset_is_not_frozen_live_outer_test")
    if total["n_matches"] < 300:
        reasons.append("fewer_than_300_outer_matches")
    for league in ("allsvenskan", "eliteserien"):
        if by_league.get(league, {}).get("n_matches", 0) < 100:
            reasons.append(f"fewer_than_100_{league}_matches")
    ci = total["delta_logloss_ci90"]
    if not ci or ci[0] <= 0:
        reasons.append("delta_logloss_ci_not_positive")
    if any(block["delta_logloss"] is not None and block["delta_logloss"] < -0.005
           for block in by_league.values()):
        reasons.append("league_logloss_guardrail_failed")
    if total["brier_delta"] is None or total["brier_delta"] > 0.002:
        reasons.append("brier_guardrail_failed")
    if any(item["new_abs_bias"] is not None and item["new_abs_bias"] > 0.03
           for item in calibration.values()):
        reasons.append("calibration_guardrail_failed")
    incomplete_block = _metric_block(incomplete)
    if (incomplete_block["n"] and
            (incomplete_block["delta_logloss"] is None or
             incomplete_block["delta_logloss"] <= 0)):
        reasons.append("incomplete_feature_guardrail_failed")
    return {
        "policy_version": walk["policy_version"], "dataset_kind": dataset_kind,
        "horizon": walk.get("horizon"),
        "n_eligible": walk["n_eligible"], "n_predictions": len(predictions),
        "folds": walk["folds"], "penalty_counts": walk["penalty_counts"],
        "total": total, "by_league": by_league, "calibration": calibration,
        "complete_features": _metric_block(complete),
        "incomplete_features": incomplete_block,
        "decision": {"pass": not reasons, "reasons": reasons},
    }


def format_report(report: dict) -> str:
    total = report["total"]
    ci = total["delta_logloss_ci90"]
    ci_text = f"[{ci[0]:+.5f}..{ci[1]:+.5f}]" if ci else "saknas"
    lines = [
        f"V2-B {report['policy_version']} · {report['dataset_kind']} · "
        f"{report.get('horizon') or 'alla'}",
        f"eligible {report['n_eligible']} · OOT-developmentprediktioner "
        f"{report['n_predictions']} · folds {len(report['folds'])}",
        f"Δlogloss sharp−v2 {total['delta_logloss']} · 90% KI {ci_text} · "
        f"ΔBrier {total['brier_delta']}",
        f"träff sharp/v2 {total['accuracy_sharp']} / {total['accuracy_v2']} · "
        f"värdespel n={total['bets']} ROI={total['bet_roi']}",
    ]
    for league, block in report["by_league"].items():
        lines.append(f"{league:12} n={block['n_matches']:4} · "
                     f"Δlogloss {block['delta_logloss']:+.5f} · "
                     f"ΔBrier {block['brier_delta']:+.5f}")
    complete, incomplete = report["complete_features"], report["incomplete_features"]
    lines.append(f"features kompletta n={complete['n']} ΔLL={complete['delta_logloss']} · "
                 f"ofullständiga n={incomplete['n']} ΔLL={incomplete['delta_logloss']}")
    lines.append(f"ridge λ per prediktion: {report['penalty_counts']}")
    lines.append("kalibreringsbias v2 (ny absolut bias mot sharp): " + ", ".join(
        f"{sign} {item['v2_bias']:+.3f} ({item['new_abs_bias']:+.3f})"
        for sign, item in report["calibration"].items()
        if item["v2_bias"] is not None))
    status = "PASS" if report["decision"]["pass"] else "STOPP"
    lines.append(f"dom {status}: {', '.join(report['decision']['reasons']) or 'alla krav'}")
    return "\n".join(lines)
