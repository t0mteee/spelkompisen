"""Lokal, återupptagbar sökning efter Topptipset-portföljer vid 256 kr.

Forskningskontrakt: docs/pooloptimerare-v1-forregistrering.md.

Exempel, teknisk pilot (skriver bara lokal JSON):

    .venv/bin/python -B scripts/optimera_topptips256.py \
      --db /sokvag/till/fixerad-snapshot.db --pilot --configs 500 \
      --output data/optimizer/topptips256-v1-pilot.json

Återuppta samma körning med ``--resume``. Produktionsdatabasen öppnas alltid
``mode=ro``; skriptet känner inte till några API:er för att lägga spel.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import pathlib
import random
import sqlite3
import subprocess
import sys
import time
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import builder  # noqa: E402
from app.analysis import analyze_draw  # noqa: E402
from app.storage import DEFAULT_DB  # noqa: E402
from scripts import ph5_radvalsablation as ph5  # noqa: E402

VERSION = "poolopt-topptips256-v1"
SEED = 20260830
BUDGET = 256
MIN_CLOSE = "2024-01-01"
EXCLUDED_DRAWS = frozenset({("topptipset", 4289)})
PRODUCTS = ("topptipset", "topptipsetstryk", "topptipsetextra")
SIGNS = ("1", "X", "2")
SIGN_INDEX = {sign: index for index, sign in enumerate(SIGNS)}
ALL_ROWS = tuple(itertools.product(SIGNS, repeat=8))
ROW_INDEX = {row: index for index, row in enumerate(ALL_ROWS)}
X_COUNTS = tuple(row.count("X") for row in ALL_ROWS)
WINSOR_ROI_DIFF = 2.0
CHAMPION_ID = "champion-standard-v1"
CHECKPOINT_EVERY = 4
DEFAULT_OUTPUT_DIR = (pathlib.Path(__file__).resolve().parents[1] / "data"
                      / "optimizer")

_WORKER_CONFIGS: list[dict] = []


def _code_version() -> str:
    try:
        root = pathlib.Path(__file__).resolve().parents[2]
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _code_fingerprint() -> str:
    """Hasha den faktiska forskningskoden, även före nästa git-commit."""
    root = pathlib.Path(__file__).resolve().parents[1]
    paths = (
        pathlib.Path(__file__).resolve(),
        root / "app" / "builder.py",
        root / "app" / "analysis.py",
        root / "scripts" / "ph5_radvalsablation.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def champion_config() -> dict:
    return {
        "id": CHAMPION_ID,
        "value_weight": 0.5,
        "kappa_scale": 1.0,
        "x_slope": 0.0,
        "x_curve": 0.0,
        "x_quota": 0.0,
        "sign_cap": 1.0,
    }


def generate_configs(count: int, seed: int = SEED) -> list[dict]:
    """Skapa champion + deterministiska, unika sökkonfigurationer."""
    if count < 1:
        raise ValueError("antal konfigurationer måste vara minst 1")
    rng = random.Random(seed)
    out = [champion_config()]
    seen = {tuple(out[0][key] for key in (
        "value_weight", "kappa_scale", "x_slope", "x_curve",
        "x_quota", "sign_cap"))}
    quota_values = (0.0, 0.25, 0.5, 0.75, 1.0)
    cap_values = (0.65, 0.70, 0.80, 0.90, 1.0)
    while len(out) < count:
        values = (
            round(rng.uniform(0.0, 1.0), 3),
            round(math.exp(rng.uniform(math.log(0.75), math.log(1.40))), 3),
            round(rng.uniform(-0.25, 0.25), 3),
            round(rng.uniform(-0.08, 0.12), 3),
            rng.choice(quota_values),
            rng.choice(cap_values),
        )
        if values in seen:
            continue
        seen.add(values)
        payload = {
            "value_weight": values[0], "kappa_scale": values[1],
            "x_slope": values[2], "x_curve": values[3],
            "x_quota": values[4], "sign_cap": values[5],
        }
        out.append({"id": "cfg-" + _stable_hash(payload), **payload})
    return out


def _close_key(row: dict) -> tuple:
    return (str(row.get("close") or ""), str(row.get("product") or ""),
            int(row.get("draw") or 0))


def split_history(rows: list[dict], pilot: bool = False,
                  pilot_total: int = 60) -> dict[str, list[dict]]:
    """Global kronologisk 60/20/20-delning; pilot tar ett jämnt delurval."""
    ordered = sorted(rows, key=_close_key)
    if pilot and len(ordered) > pilot_total:
        ordered = even_sample(ordered, pilot_total)
    n = len(ordered)
    first = int(n * 0.60)
    second = int(n * 0.80)
    return {"development": ordered[:first],
            "validation": ordered[first:second],
            "test": ordered[second:]}


def even_sample(rows: list, count: int) -> list:
    if count <= 0 or count >= len(rows):
        return list(rows)
    if count == 1:
        return [rows[-1]]
    indices = [round(i * (len(rows) - 1) / (count - 1))
               for i in range(count)]
    return [rows[index] for index in dict.fromkeys(indices)]


def load_history(conn: sqlite3.Connection) -> list[dict]:
    rows = []
    for product in PRODUCTS:
        plan = ph5.prize_plan(product)
        for item in ph5.load(conn, product, plan):
            item = dict(item)
            item["product"] = product
            if len(item.get("events") or []) != 8:
                continue
            if str(item.get("close") or "")[:10] < MIN_CLOSE:
                continue
            if (product, int(item["draw"])) in EXCLUDED_DRAWS:
                continue
            rows.append(item)
    return sorted(rows, key=_close_key)


def dataset_fingerprint(rows: list[dict]) -> str:
    compact = []
    for item in rows:
        compact.append({
            "product": item["product"], "draw": item["draw"],
            "close": item.get("close"), "net_sale": item.get("net_sale"),
            "row_price": item.get("row_price"),
            "events": [list(event) for event in item.get("events") or []],
            "tiers": sorted((int(k), list(v))
                            for k, v in (item.get("tiers") or {}).items()),
        })
    return _stable_hash(compact)


def _prepare(item: dict) -> dict:
    draw, facit = ph5.as_draw(item["product"], item)
    analysis = analyze_draw(draw)
    if len(analysis.matches) != 8 or tuple(facit) not in ROW_INDEX:
        raise ValueError("omgången saknar exakt åtta giltiga utfall")
    field = float(item["net_sale"]) / float(item["row_price"])
    plan = ph5.prize_plan(item["product"])
    top = max(plan["splits"])
    pool = (float(item["net_sale"]) * float(plan["ratio"])
            * float(plan["splits"][top]))
    base_kappa = builder.kappa_for(item["product"], top)
    p_by_col = []
    q_by_col = []
    for match in analysis.matches:
        ps, qs = [], []
        for sign in SIGNS:
            outcome = match.outcomes[sign]
            p = outcome.fair_prob if outcome.fair_prob is not None else 1 / 3
            q = ((outcome.streck / 100.0) if outcome.streck else p)
            ps.append(max(float(p), 1e-12))
            qs.append(max(float(q), 0.001))
        p_by_col.append(tuple(ps)); q_by_col.append(tuple(qs))

    logp, q_values, p_values, reference_ev = [], [], [], []
    for row in ALL_ROWS:
        lp = 0.0
        q = 1.0
        for column, sign in enumerate(row):
            index = SIGN_INDEX[sign]
            lp += math.log(p_by_col[column][index])
            q *= q_by_col[column][index]
        probability = math.exp(lp)
        dividend = min(pool, pool / (field * q * base_kappa + 1.0))
        logp.append(lp); q_values.append(q); p_values.append(probability)
        reference_ev.append(probability * dividend)

    tier = (item.get("tiers") or {}).get(top, (None, None))
    winners, amount = tier
    return {
        "key": f"{item['product']}:{item['draw']}",
        "product": item["product"], "draw": int(item["draw"]),
        "close": item.get("close"), "field": field, "pool": pool,
        "base_kappa": base_kappa, "logp": logp, "q": q_values,
        "p": p_values, "reference_ev": reference_ev,
        "x_distribution": builder.x_count_distribution(analysis),
        "facit_index": ROW_INDEX[tuple(facit)],
        "winners": winners, "amount": amount,
        "cost": float(BUDGET), "target": BUDGET,
    }


def _x_kappa(prepared: dict, config: dict, x_count: int) -> float:
    centered = x_count - 2
    modifier = (float(config["kappa_scale"])
                * math.exp(float(config["x_slope"]) * centered
                           + float(config["x_curve"]) * centered * centered))
    modifier = max(0.50, min(2.00, modifier))
    return float(prepared["base_kappa"]) * modifier


def _ranked_indices(prepared: dict, config: dict) -> list[int]:
    exponent = 3.0 - 2.0 * float(config["value_weight"])
    field = float(prepared["field"])
    scores = [
        (exponent * prepared["logp"][index]
         - math.log1p(field * prepared["q"][index]
                      * _x_kappa(prepared, config, X_COUNTS[index])), index)
        for index in range(len(ALL_ROWS))
    ]
    scores.sort(reverse=True)
    return [index for _score, index in scores]


def select_rows(prepared: dict, config: dict) -> list[int]:
    """Välj exakt 256 rader med valfria X-minimikvoter och teckentak."""
    ranked = _ranked_indices(prepared, config)
    target = int(prepared["target"])
    quota_strength = float(config["x_quota"])
    needed = {
        count: int(target * quota_strength
                   * prepared["x_distribution"][count])
        for count in range(9)
    }
    cap = math.ceil(target * float(config["sign_cap"]))
    selected: list[int] = []
    chosen = set()
    exposures = [[0, 0, 0] for _ in range(8)]

    def allowed(index: int) -> bool:
        row = ALL_ROWS[index]
        return all(exposures[column][SIGN_INDEX[sign]] < cap
                   for column, sign in enumerate(row))

    def add(index: int) -> None:
        selected.append(index); chosen.add(index)
        for column, sign in enumerate(ALL_ROWS[index]):
            exposures[column][SIGN_INDEX[sign]] += 1

    # Fyll X-minimikvoterna med den bästa ännu tillåtna raden ur en underfylld
    # grupp. Global bästa-av-grupperna gör resultatet oberoende av bucketordning.
    per_bucket = {count: [index for index in ranked if X_COUNTS[index] == count]
                  for count in range(9)}
    rank_position = {index: position for position, index in enumerate(ranked)}
    pointers = {count: 0 for count in range(9)}
    while any(value > 0 for value in needed.values()):
        candidates = []
        for count, remaining in needed.items():
            if remaining <= 0:
                continue
            rows = per_bucket[count]
            pointer = pointers[count]
            while pointer < len(rows) and not allowed(rows[pointer]):
                pointer += 1
            pointers[count] = pointer
            if pointer < len(rows):
                index = rows[pointer]
                # `ranked` har redan totalordningen; lägre position är bättre.
                candidates.append((rank_position[index], count, index))
        if not candidates:
            return []
        _position, count, index = min(candidates)
        add(index); needed[count] -= 1; pointers[count] += 1

    for index in ranked:
        if index in chosen or not allowed(index):
            continue
        add(index)
        if len(selected) == target:
            return selected
    return []


def evaluate_selected(prepared: dict, selected: list[int]) -> dict:
    target = int(prepared["target"])
    if len(selected) != target or len(set(selected)) != target:
        return {"valid": False}
    hit = int(int(prepared["facit_index"]) in set(selected))
    winners, amount = prepared.get("winners"), prepared.get("amount")
    payout_identifiable = (winners is not None and amount is not None
                           and float(winners) > 0)
    # ROI-kohorten måste vara oberoende av kandidatens utfall. Om ingen
    # historisk vinnare fanns är den publicerade toppnivåpotten inte
    # identifierbar från winners×amount; då får varken träff eller miss ett
    # ROI-värde. Träffmåttet behåller däremot omgången.
    roi = -1.0 if payout_identifiable and not hit else None
    if hit and payout_identifiable:
        payout = float(winners) * float(amount) / (float(winners) + 1.0)
        roi = payout / float(prepared["cost"]) - 1.0
    counts = [[0, 0, 0] for _ in range(8)]
    for index in selected:
        for column, sign in enumerate(ALL_ROWS[index]):
            counts[column][SIGN_INDEX[sign]] += 1
    return {
        "valid": True,
        "hit": hit,
        "roi": roi,
        "expected_hit": sum(prepared["p"][index] for index in selected),
        "reference_ev": sum(prepared["reference_ev"][index]
                            for index in selected),
        "mean_x": sum(X_COUNTS[index] for index in selected) / target,
        "x4_share": sum(X_COUNTS[index] >= 4 for index in selected) / target,
        "max_exposure": max(value for column in counts for value in column) / target,
    }


def evaluate_draw(item: dict, configs: list[dict]) -> tuple[str, dict]:
    prepared = _prepare(item)
    results = {}
    for config in configs:
        results[config["id"]] = evaluate_selected(
            prepared, select_rows(prepared, config))
    return prepared["key"], results


def _worker_init(configs: list[dict]) -> None:
    global _WORKER_CONFIGS
    _WORKER_CONFIGS = configs


def _worker(item: dict) -> tuple[str, dict]:
    return evaluate_draw(item, _WORKER_CONFIGS)


def _empty_aggregate(configs: list[dict]) -> dict:
    return {config["id"]: {
        "n": 0, "invalid": 0, "hits": 0, "roi_sum": 0.0, "roi_n": 0,
        "expected_hit_sum": 0.0, "reference_ev_sum": 0.0,
        "mean_x_sum": 0.0, "x4_share_sum": 0.0,
        "max_exposure_sum": 0.0, "paired_roi_sum": 0.0,
        "paired_roi_n": 0, "hit_delta_sum": 0,
    } for config in configs}


def _merge_draw(aggregate: dict, results: dict) -> None:
    champion = results.get(CHAMPION_ID) or {"valid": False}
    if not champion.get("valid"):
        raise ValueError("champion kunde inte bygga exakt 256 rader")
    for config_id, result in results.items():
        target = aggregate[config_id]
        if not result.get("valid"):
            target["invalid"] += 1
            continue
        target["n"] += 1
        target["hits"] += int(result["hit"])
        target["expected_hit_sum"] += float(result["expected_hit"])
        target["reference_ev_sum"] += float(result["reference_ev"])
        target["mean_x_sum"] += float(result["mean_x"])
        target["x4_share_sum"] += float(result["x4_share"])
        target["max_exposure_sum"] += float(result["max_exposure"])
        target["hit_delta_sum"] += int(result["hit"]) - int(champion["hit"])
        if result["roi"] is not None:
            target["roi_sum"] += float(result["roi"]); target["roi_n"] += 1
        if result["roi"] is not None and champion["roi"] is not None:
            delta = float(result["roi"]) - float(champion["roi"])
            target["paired_roi_sum"] += max(-WINSOR_ROI_DIFF,
                                             min(WINSOR_ROI_DIFF, delta))
            target["paired_roi_n"] += 1


def summarize(aggregate: dict, configs_by_id: dict[str, dict]) -> list[dict]:
    champion = aggregate[CHAMPION_ID]
    champion_hit = champion["expected_hit_sum"] or 1e-12
    champion_ev = champion["reference_ev_sum"] or 1e-12
    out = []
    for config_id, values in aggregate.items():
        n = values["n"]
        hit_ratio = values["expected_hit_sum"] / champion_hit
        ev_ratio = values["reference_ev_sum"] / champion_ev
        paired = (values["paired_roi_sum"] / values["paired_roi_n"]
                  if values["paired_roi_n"] else 0.0)
        balanced = (paired
                    + 0.25 * max(-0.5, min(0.5, math.log(max(hit_ratio, 1e-9))))
                    + 0.10 * max(-0.5, min(0.5, math.log(max(ev_ratio, 1e-9)))))
        out.append({
            **configs_by_id[config_id],
            "n_draws": n, "invalid_draws": values["invalid"],
            "hits": values["hits"],
            "hit_rate": values["hits"] / n if n else None,
            "hit_delta": values["hit_delta_sum"],
            "mean_roi": (values["roi_sum"] / values["roi_n"]
                         if values["roi_n"] else None),
            "roi_draws": values["roi_n"],
            "paired_winsor_roi_delta": paired,
            "expected_hit": values["expected_hit_sum"] / n if n else None,
            "expected_hit_ratio": hit_ratio,
            "reference_ev": values["reference_ev_sum"] / n if n else None,
            "reference_ev_ratio": ev_ratio,
            "mean_x": values["mean_x_sum"] / n if n else None,
            "x4_share": values["x4_share_sum"] / n if n else None,
            "max_exposure": values["max_exposure_sum"] / n if n else None,
            "balanced_score": balanced,
            "passes_floor": bool(n and values["invalid"] == 0
                                 and hit_ratio >= 0.95 and ev_ratio >= 0.90),
        })
    return out


def select_survivors(summary: list[dict], keep: int) -> list[str]:
    """Rund-robin-union av fyra mål; champion följer alltid med."""
    keep = max(1, min(int(keep), len(summary)))
    valid = [row for row in summary if row["passes_floor"]]
    if not any(row["id"] == CHAMPION_ID for row in valid):
        valid.append(next(row for row in summary if row["id"] == CHAMPION_ID))
    rankings = [
        sorted(valid, key=lambda row: (row["balanced_score"], row["id"]), reverse=True),
        sorted(valid, key=lambda row: (row["hits"], row["expected_hit_ratio"], row["id"]), reverse=True),
        sorted(valid, key=lambda row: (row["expected_hit_ratio"], row["id"]), reverse=True),
        sorted(valid, key=lambda row: (row["reference_ev_ratio"], row["id"]), reverse=True),
        sorted(valid, key=lambda row: (row["paired_winsor_roi_delta"], row["id"]), reverse=True),
    ]
    chosen = [CHAMPION_ID]
    seen = set(chosen)
    position = 0
    while len(chosen) < keep and any(position < len(rows) for rows in rankings):
        for rows in rankings:
            if position >= len(rows):
                continue
            config_id = rows[position]["id"]
            if config_id not in seen:
                chosen.append(config_id); seen.add(config_id)
                if len(chosen) == keep:
                    break
        position += 1
    return chosen


def leaderboards(summary: list[dict], limit: int = 10) -> dict:
    valid = [row for row in summary if row["passes_floor"]]
    keys = {
        "balanced": "balanced_score",
        "historical_roi": "paired_winsor_roi_delta",
        "actual_hits": "hits",
        "expected_hit": "expected_hit_ratio",
        "reference_ev": "reference_ev_ratio",
        "x4_coverage": "x4_share",
    }
    return {name: sorted(valid, key=lambda row: (row[key], row["id"]),
                         reverse=True)[:limit]
            for name, key in keys.items()}


def _bootstrap_ci(values: list[float], seed: str,
                  iterations: int = 2000) -> Optional[list[float]]:
    if len(values) < 3:
        return None
    rng = random.Random(f"{SEED}|{seed}")
    means = []
    for _ in range(iterations):
        means.append(sum(rng.choice(values) for _value in values) / len(values))
    means.sort()
    return [means[int(iterations * 0.05)],
            means[min(iterations - 1, int(iterations * 0.95))]]


def final_audit(details: dict, config_ids: list[str]) -> dict:
    """Ojusterade KI:n på den låsta historiska slutauditen.

    Kandidaterna valdes på development+validation, aldrig på dessa detaljer.
    KI:t är ändå bara diagnostik: parameterfamiljen motiverades av tidigare
    historik och 10 000-sökningen kräver senare multipeltest/forwardgrind.
    """
    out = {}
    for config_id in config_ids:
        roi_deltas, hit_deltas = [], []
        for results in details.values():
            champion = results.get(CHAMPION_ID) or {}
            candidate = results.get(config_id) or {}
            if not champion.get("valid") or not candidate.get("valid"):
                continue
            hit_deltas.append(float(candidate["hit"] - champion["hit"]))
            if champion.get("roi") is not None and candidate.get("roi") is not None:
                delta = float(candidate["roi"]) - float(champion["roi"])
                roi_deltas.append(max(-WINSOR_ROI_DIFF,
                                      min(WINSOR_ROI_DIFF, delta)))
        out[config_id] = {
            "n_draws": len(hit_deltas), "paired_roi_n": len(roi_deltas),
            "mean_hit_delta": (sum(hit_deltas) / len(hit_deltas)
                               if hit_deltas else None),
            "hit_delta_ci90_unadjusted": _bootstrap_ci(
                hit_deltas, f"{config_id}|hit"),
            "mean_winsor_roi_delta": (sum(roi_deltas) / len(roi_deltas)
                                      if roi_deltas else None),
            "winsor_roi_delta_ci90_unadjusted": _bootstrap_ci(
                roi_deltas, f"{config_id}|roi"),
        }
    return out


def _atomic_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    temporary.replace(path)


def _draw_key(item: dict) -> str:
    return f"{item['product']}:{item['draw']}"


def run_stage(name: str, draws: list[dict], configs: list[dict], workers: int,
              report: dict, output: pathlib.Path,
              keep_details: bool = False) -> tuple[list[dict], dict]:
    config_ids = [config["id"] for config in configs]
    expected_keys = [_draw_key(item) for item in draws]
    partial = report.get("partial") or {}
    if (partial.get("name") == name
            and partial.get("config_ids") == config_ids
            and partial.get("draw_keys") == expected_keys):
        aggregate = partial["aggregate"]
        completed = set(partial.get("completed") or [])
        details = partial.get("details") or {}
        print(f"{name}: återupptar efter {len(completed)}/{len(draws)} omgångar")
    else:
        aggregate = _empty_aggregate(configs)
        completed = set()
        details = {}
    remaining = [item for item in draws if _draw_key(item) not in completed]
    started = time.monotonic()

    def save() -> None:
        report["partial"] = {
            "name": name, "config_ids": config_ids,
            "draw_keys": expected_keys, "completed": sorted(completed),
            "aggregate": aggregate,
        }
        if keep_details:
            report["partial"]["details"] = details
        report["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(output, report)

    if workers <= 1:
        iterator = (evaluate_draw(item, configs) for item in remaining)
        executor = None
    else:
        try:
            executor = concurrent.futures.ProcessPoolExecutor(
                max_workers=workers, initializer=_worker_init,
                initargs=(configs,))
            iterator = executor.map(_worker, remaining, chunksize=1)
        except (OSError, PermissionError) as exc:
            # Vissa sandlådor förbjuder process-semaforer. En lokal körning
            # ska då bli långsammare, aldrig obrukbar eller metodiskt annorlunda.
            print(f"{name}: multiprocessing saknas ({type(exc).__name__}); "
                  "fortsätter sekventiellt")
            executor = None
            iterator = (evaluate_draw(item, configs) for item in remaining)
    try:
        for position, (key, result) in enumerate(iterator, start=1):
            _merge_draw(aggregate, result); completed.add(key)
            if keep_details:
                details[key] = result
            if position % CHECKPOINT_EVERY == 0 or position == len(remaining):
                save()
                elapsed = time.monotonic() - started
                total_done = len(completed)
                print(f"{name}: {total_done}/{len(draws)} omgångar, "
                      f"{len(configs)} konfigurationer, {elapsed:.1f}s")
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
    configs_by_id = {config["id"]: config for config in configs}
    return summarize(aggregate, configs_by_id), details


def stage_plan(parts: dict[str, list[dict]], n_configs: int,
               pilot: bool) -> list[tuple[str, list[dict], Optional[int]]]:
    dev = parts["development"]
    if pilot:
        coarse_n, wide_n = min(8, len(dev)), min(24, len(dev))
        keep1 = min(n_configs, max(100, math.ceil(n_configs * 0.20)))
        keep2 = min(keep1, max(40, math.ceil(keep1 * 0.20)))
        keep3, keep4 = min(20, keep2), min(5, keep2)
    else:
        coarse_n, wide_n = min(12, len(dev)), min(64, len(dev))
        keep1 = min(n_configs, max(1000, math.ceil(n_configs * 0.20)))
        keep2 = min(keep1, max(200, math.ceil(keep1 * 0.20)))
        keep3, keep4 = min(40, keep2), min(8, keep2)
    return [
        ("development-coarse", even_sample(dev, coarse_n), keep1),
        ("development-wide", even_sample(dev, wide_n), keep2),
        ("development-full", dev, keep3),
        ("validation", parts["validation"], keep4),
        ("historical-test", parts["test"], None),
    ]


def _new_report(args, db_path: pathlib.Path, rows: list[dict],
                configs: list[dict], parts: dict) -> dict:
    spec = {
        "version": VERSION, "seed": SEED, "budget": BUDGET,
        "min_close": MIN_CLOSE, "excluded_draws": sorted(EXCLUDED_DRAWS),
        "products": list(PRODUCTS), "pilot": bool(args.pilot),
        "pilot_draws": int(args.pilot_draws) if args.pilot else None,
        "config_count": len(configs), "split": "global-chronological-60-20-20",
    }
    return {
        "status": "running", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "code_version": _code_version(), "code_fingerprint": _code_fingerprint(),
        "spec": spec,
        "spec_fingerprint": _stable_hash(spec),
        "dataset_fingerprint": dataset_fingerprint(rows),
        "parts_fingerprint": _stable_hash({
            key: [_draw_key(item) for item in value]
            for key, value in parts.items()
        }),
        "config_fingerprint": _stable_hash(configs),
        "database": {"path": str(db_path), "size_bytes": db_path.stat().st_size},
        "dataset": {"total": len(rows),
                    **{key: len(value) for key, value in parts.items()}},
        "configs": configs, "stages": {}, "partial": None,
        "warning": ("final_only med slutstreck; relativ screening, inte "
                    "spelbar ROI eller promotionsbevis"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB),
                        help="fixerad SQLite-snapshot; öppnas alltid read-only")
    parser.add_argument("--output", default="")
    parser.add_argument("--configs", type=int, default=500)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true",
                      help="teknisk 60-omgångspilot; resultat får inte tolkas")
    mode.add_argument("--full", action="store_true",
                      help="full historisk sökning enligt förregistreringen")
    parser.add_argument("--pilot-draws", type=int, default=60)
    parser.add_argument("--workers", type=int, default=0,
                        help="0 = alla utom en CPU, 1 = sekventiellt")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.configs < 1 or args.configs > 10_000:
        parser.error("--configs måste vara 1–10000")
    if args.pilot_draws < 20:
        parser.error("--pilot-draws måste vara minst 20")
    db_path = pathlib.Path(args.db).expanduser().resolve()
    if not db_path.is_file():
        parser.error(f"databasen saknas: {db_path}")
    default_name = ("topptips256-v1-pilot.json" if args.pilot
                    else "topptips256-v1-full.json")
    output = pathlib.Path(
        args.output or (DEFAULT_OUTPUT_DIR / default_name)).expanduser().resolve()
    if output.exists() and not args.resume:
        parser.error(f"resultatfilen finns redan; välj annan --output eller --resume: {output}")

    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        rows = load_history(conn)
    finally:
        conn.close()
    parts = split_history(rows, pilot=args.pilot, pilot_total=args.pilot_draws)
    if min(map(len, parts.values())) < 4:
        parser.error("för få kvalificerade omgångar för 60/20/20-delningen")
    configs = generate_configs(args.configs)
    fresh = _new_report(args, db_path, rows, configs, parts)
    if args.resume:
        report = json.loads(output.read_text(encoding="utf-8"))
        for key in ("code_fingerprint", "spec_fingerprint",
                    "dataset_fingerprint", "parts_fingerprint",
                    "config_fingerprint"):
            if report.get(key) != fresh.get(key):
                parser.error(f"--resume vägras: {key} har ändrats")
    else:
        report = fresh
        _atomic_json(output, report)

    workers = args.workers or max(1, (os.cpu_count() or 2) - 1)
    all_configs = {config["id"]: config for config in configs}
    active = configs
    print(f"{VERSION}: {len(rows)} kvalificerade omgångar, "
          f"{len(configs)} konfigurationer, {workers} worker(s)")
    for name, draws, keep in stage_plan(parts, len(configs), args.pilot):
        existing = (report.get("stages") or {}).get(name)
        if existing:
            active = [all_configs[config_id] for config_id in existing["kept_ids"]]
            print(f"{name}: redan klar, {len(active)} går vidare")
            continue
        keep_details = name in ("validation", "historical-test")
        summary, details = run_stage(
            name, draws, active, workers, report, output,
            keep_details=keep_details)
        kept = ([row["id"] for row in summary] if keep is None
                else select_survivors(summary, keep))
        report["stages"][name] = {
            "n_draws": len(draws), "n_configs": len(active),
            "kept_ids": kept, "leaderboards": leaderboards(summary),
            "champion": next(row for row in summary if row["id"] == CHAMPION_ID),
            "survivors": [row for row in summary if row["id"] in kept],
            "finalists": ([row for row in summary if row["id"] in kept]
                          if keep is None else []),
        }
        if keep_details:
            report["stages"][name]["per_draw"] = details
        if name == "historical-test":
            report["stages"][name]["audit"] = final_audit(details, kept)
        report["partial"] = None
        report["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _atomic_json(output, report)
        active = [all_configs[config_id] for config_id in kept]
        print(f"{name}: klar, {len(active)} går vidare")
    report["status"] = "complete"
    report["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["partial"] = None
    _atomic_json(output, report)
    print(f"Klar: {output}")


if __name__ == "__main__":
    main()
