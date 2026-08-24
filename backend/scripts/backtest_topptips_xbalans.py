"""Historisk screening av Topptipsets X-/radformskandidater.

Kohorten använder slutstreck och öppningsodds och är därför INTE point-in-time.
Alla armar ser samma information, så den parade jämförelsen kan sålla en ny
radvalsmetod men aldrig ensam promovera den till skarpt förslag.

Körning:
  .venv/bin/python -B scripts/backtest_topptips_xbalans.py --db FIL --json FIL
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sqlite3
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import builder  # noqa: E402
from app.analysis import analyze_draw  # noqa: E402
from app.main import PRIZE_PLANS  # noqa: E402
from app.storage import DEFAULT_DB  # noqa: E402
from scripts import ph5_radvalsablation as ph5  # noqa: E402

VERSION = builder.TOPPTIPS_ROW_SHAPE_VERSION
PRODUCTS = ("topptipset", "topptipsetstryk", "topptipsetextra")
EVALUATION_FROM_DATE = "2024-01-01"
EVALUATION_BEFORE_DATE = "2026-08-24"
HOLDOUT_SHARE = 0.30
WINSOR_ROI_DIFF = 2.0
SEED = 20260824
ARMS = ("current", "row_shape", "x_balanced", "low_ev")
X_BUCKETS = tuple(range(5))
MIN_EXPECTED_WINNERS = 100.0
KAPPA_MULTIPLIER_RANGE = (0.5, 1.5)


def _probability(match, sign: str) -> float:
    outcome = match.outcomes[sign]
    probability = (outcome.sharp_prob if outcome.sharp_prob is not None
                   else outcome.fair_prob)
    return max(0.0, min(1.0, probability or (1.0 / 3.0)))


def _portfolio_diagnostics(analysis, rows: list[tuple], facit: list[str]) -> dict:
    hit_probability = 0.0
    x_counts = []
    for row in rows:
        probability = 1.0
        for match, sign in zip(analysis.matches, row):
            probability *= _probability(match, sign)
        hit_probability += probability
        x_counts.append(row.count("X"))
    expected_x = sum(_probability(match, "X") for match in analysis.matches)
    actual_x = facit.count("X")
    return {
        "hit_probability": hit_probability,
        "expected_x": expected_x,
        "mean_x": statistics.fmean(x_counts),
        "max_x": max(x_counts),
        "actual_x": actual_x,
        "x_count_impossible": actual_x > max(x_counts),
    }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _comparison(rows: list[dict], candidate: str,
                bootstrap_iters: int) -> dict:
    roi_pairs = [
        (row[candidate]["roi"], row["current"]["roi"])
        for row in rows
        if row[candidate]["roi"] is not None
        and row["current"]["roi"] is not None
    ]
    roi_diffs = [left - right for left, right in roi_pairs]
    clipped_roi = [max(-WINSOR_ROI_DIFF, min(WINSOR_ROI_DIFF, value))
                   for value in roi_diffs]
    hit_diffs = [float(row[candidate]["hit"])
                 - float(row["current"]["hit"]) for row in rows]
    probability_diffs = [
        row[candidate]["hit_probability"]
        - row["current"]["hit_probability"] for row in rows]
    seed_offset = sum(ord(char) for char in candidate)
    roi_ci = ph5.block_ci(
        clipped_roi, random.Random(SEED + seed_offset),
        iters=bootstrap_iters, alpha=0.10)
    hit_ci = ph5.block_ci(
        hit_diffs, random.Random(SEED + seed_offset + 1),
        iters=bootstrap_iters, alpha=0.10)
    return {
        "paired_roi_n": len(roi_pairs),
        "mean_roi_diff_w": _mean(clipped_roi),
        "roi_diff_ci90": list(roi_ci),
        "mean_top_hit_diff": _mean(hit_diffs),
        "top_hit_diff_ci90": list(hit_ci),
        "candidate_only_hits": sum(
            row[candidate]["hit"] and not row["current"]["hit"]
            for row in rows),
        "current_only_hits": sum(
            row["current"]["hit"] and not row[candidate]["hit"]
            for row in rows),
        "mean_market_hit_probability_diff": _mean(probability_diffs),
    }


def _summarize(rows: list[dict], bootstrap_iters: int) -> dict:
    arms = {}
    for arm in ARMS:
        selected = [row[arm] for row in rows]
        rois = [item["roi"] for item in selected if item["roi"] is not None]
        arms[arm] = {
            "n": len(selected),
            "top_hits": sum(item["hit"] for item in selected),
            "top_hit_share": _mean([float(item["hit"]) for item in selected]),
            "roi_complete_n": len(rois),
            "mean_roi_unpaired": _mean(rois),
            "mean_market_hit_probability": _mean(
                [item["hit_probability"] for item in selected]),
            "mean_system_x": _mean([item["mean_x"] for item in selected]),
            "mean_market_expected_x": _mean(
                [item["expected_x"] for item in selected]),
            "mean_abs_x_gap": _mean(
                [abs(item["mean_x"] - item["expected_x"])
                 for item in selected]),
            "x_count_impossible": sum(
                item["x_count_impossible"] for item in selected),
        }

    return {
        "n": len(rows),
        "arms": arms,
        "row_shape_vs_current": _comparison(
            rows, "row_shape", bootstrap_iters),
        "x_balanced_vs_current": _comparison(
            rows, "x_balanced", bootstrap_iters),
        "low_ev_vs_current": _comparison(rows, "low_ev", bootstrap_iters),
    }


def _evaluate_arm(system, analysis, facit, tiers, cost) -> dict:
    rows = [tuple(row) for row in system.rows or []]
    result = ph5.evaluate(rows, facit, tiers, cost)
    diagnostics = _portfolio_diagnostics(analysis, rows, facit)
    return {
        "roi": result["roi"],
        "payout": result["payout"],
        "best": result["best"],
        "hit": result["best"] == 8,
        **diagnostics,
    }


def _run_draw(product: str, historic: dict, budget: float,
              kappa_multiplier_by_x: dict[int, float]) -> dict:
    draw, facit = ph5.as_draw(product, historic)
    analysis = analyze_draw(draw)
    price = draw.row_price or 1.0
    cost = max(1, int(budget / price)) * price
    plan = PRIZE_PLANS[product]
    kwargs = {
        "analysis": analysis,
        "strategy": "medel",
        "budget": budget,
        "row_price": price,
        "plan": plan,
        "jackpot": 0.0,
    }
    current = builder.build_ev_system(value_weight=0.5, **kwargs)
    x_balanced = builder.build_topptips_x_balanced_system(
        value_weight=0.5, **kwargs)
    kappa_by_x = {
        bucket: builder.kappa_for(product, 8) * multiplier
        for bucket, multiplier in kappa_multiplier_by_x.items()
    }
    row_shape = builder.build_topptips_row_shape_system(
        kappa_by_x=kappa_by_x, value_weight=0.5, **kwargs)
    low_ev = builder.build_ev_system(value_weight=0.0, **kwargs)
    return {
        "product": product,
        "draw": historic["draw"],
        "close": historic["close"],
        "n_rows": int(cost / price),
        "actual_x": facit.count("X"),
        "current": _evaluate_arm(
            current, analysis, facit, historic["tiers"], cost),
        "row_shape": _evaluate_arm(
            row_shape, analysis, facit, historic["tiers"], cost),
        "x_balanced": _evaluate_arm(
            x_balanced, analysis, facit, historic["tiers"], cost),
        "low_ev": _evaluate_arm(
            low_ev, analysis, facit, historic["tiers"], cost),
    }


def _fit_row_shape_kappa(
        development: list[tuple[str, dict]]) -> tuple[dict[int, float], dict]:
    """Skatta familjegemensam radform relativt produktens bas-kappa.

    Endast utvecklingsperioden används. Kvoten `faktiska vinnare / nuvarande
    modellprognos` appliceras sedan på produktens befintliga 2024+-kappa.
    4-bucketen betyder fyra eller fler X. Tunn exponering faller stängt till
    den befintliga modellen; säkerhetsklampen är låst före utvärderingen.
    """
    totals = {bucket: {"actual": 0.0, "expected_base": 0.0, "draws": 0}
              for bucket in X_BUCKETS}
    for product, historic in development:
        winners, _amount = historic["tiers"].get(8, (None, None))
        if winners is None:
            continue
        q_row = 1.0
        x_count = 0
        for (_event, _description, outcome, _cancelled,
             s1, sx, s2, _o1, _ox, _o2) in historic["events"]:
            total = float(s1 + sx + s2) or 1.0
            q_row *= {"1": s1, "X": sx, "2": s2}[outcome] / total
            x_count += int(outcome == "X")
        bucket = min(x_count, 4)
        field = historic["net_sale"] / historic["row_price"]
        expected = field * q_row * builder.kappa_for(product, 8)
        totals[bucket]["actual"] += float(winners)
        totals[bucket]["expected_base"] += expected
        totals[bucket]["draws"] += 1

    multipliers = {}
    lo, hi = KAPPA_MULTIPLIER_RANGE
    for bucket in X_BUCKETS:
        item = totals[bucket]
        expected = item["expected_base"]
        raw = item["actual"] / expected if expected > 0 else 1.0
        multiplier = max(lo, min(hi, raw)) if expected >= MIN_EXPECTED_WINNERS else 1.0
        multipliers[bucket] = multiplier
        item["raw_multiplier"] = raw
        item["used_multiplier"] = multiplier
    absolute_by_product = {
        product: {
            bucket: builder.kappa_for(product, 8) * multipliers[bucket]
            for bucket in X_BUCKETS}
        for product in PRODUCTS
    }
    return multipliers, {
        "buckets": totals,
        "multipliers": multipliers,
        "absolute_kappa_by_product": absolute_by_product,
        "min_expected_winners": MIN_EXPECTED_WINNERS,
        "multiplier_range": list(KAPPA_MULTIPLIER_RANGE),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--budget", type=float, default=384.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--bootstrap-iters", type=int, default=2000)
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    if args.bootstrap_iters < 100:
        parser.error("--bootstrap-iters måste vara minst 100")

    db_path = pathlib.Path(args.db).expanduser().resolve()
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    report = {
        "version": VERSION,
        "diagnostic_version": builder.TOPPTIPS_X_BALANCED_VERSION,
        "evaluation_from_date": EVALUATION_FROM_DATE,
        "evaluation_before_date": EVALUATION_BEFORE_DATE,
        "budget": args.budget,
        "holdout_share": HOLDOUT_SHARE,
        "bootstrap_iters": args.bootstrap_iters,
        "database": {"path": str(db_path), "size_bytes": db_path.stat().st_size},
        "limitations": [
            "final_only: slutstreck och öppningsodds, inte point-in-time",
            "relativ historisk screening; ingen automatisk promotion",
            "jackpot sätts till 0 eftersom historisk jackpot saknas i kohorten",
        ],
        "products": {},
    }
    cohorts = {}
    development_training: list[tuple[str, dict]] = []
    for product in PRODUCTS:
        historic = ph5.load(
            conn, product, PRIZE_PLANS[product],
            require_identifiable_tiers=False)
        historic = [row for row in historic
                    if EVALUATION_FROM_DATE <= str(row["close"])[:10]
                    < EVALUATION_BEFORE_DATE and 8 in row["tiers"]]
        if args.limit:
            historic = historic[-args.limit:]
        split = max(1, int(len(historic) * (1.0 - HOLDOUT_SHARE)))
        cohorts[product] = (historic, split)
        development_training.extend(
            (product, row) for row in historic[:split])

    kappa_multipliers, fit_report = _fit_row_shape_kappa(development_training)
    report["row_shape_fit"] = fit_report
    print("Radformskappa:", ", ".join(
        f"{bucket if bucket < 4 else '4+'}X={value:.4f}"
        for bucket, value in kappa_multipliers.items()), flush=True)

    family_development = []
    family_holdout = []
    for product in PRODUCTS:
        historic, split = cohorts[product]
        per_draw = []
        for index, row in enumerate(historic, 1):
            per_draw.append(_run_draw(
                product, row, args.budget, kappa_multipliers))
            if index % 100 == 0:
                print(f"{product}: {index}/{len(historic)}", flush=True)
        development = per_draw[:split]
        holdout = per_draw[split:]
        family_development.extend(development)
        family_holdout.extend(holdout)
        report["products"][product] = {
            "n_available": len(per_draw),
            "split_index": split,
            "development": _summarize(development, args.bootstrap_iters),
            "holdout": _summarize(holdout, args.bootstrap_iters),
            "full": _summarize(per_draw, args.bootstrap_iters),
            "per_draw": per_draw,
        }
        print(f"{product}: klar ({len(per_draw)} omgångar)", flush=True)

    report["family"] = {
        "development": _summarize(family_development, args.bootstrap_iters),
        "holdout": _summarize(family_holdout, args.bootstrap_iters),
        "full": _summarize(
            family_development + family_holdout, args.bootstrap_iters),
    }
    conn.close()
    if args.json:
        output = pathlib.Path(args.json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"JSON: {output}")
    family = report["family"]["holdout"]
    print(json.dumps({
        "row_shape_fit": fit_report,
        "holdout": family,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
