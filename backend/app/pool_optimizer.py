"""Pooloptimerarens radval (poolopt-topptips256-v1) som återanvändbar kärna.

Kärnan flyttades hit 2026-09-02 från `scripts/optimera_topptips256.py` så att
PH3:s framåtfrysning (`pool_system_ledger.POOLOPT_FORWARD_CONFIGS`) kan
bygga EXAKT samma rader live som den historiska sökningen byggde. Skriptet
importerar härifrån; numeriken är oförändrad (regressionstest: championens
konfiguration reproducerar `build_ev_system` rad för rad).

Modellen: samma frysta referens som Standard — `fair_prob` (SvS-odds först,
Pinnacle som reserv) och streck — men radrankningen får fem frihetsgrader:
värdevikt, global κ-skala, X-kurva/-lutning på κ per antal X i raden,
X-minimikvot per X-antal och ett teckentak per kolumn. Ingen jackpot:
sökningen kördes utan, och forwardarmen speglar sökningen.
"""
from __future__ import annotations

import itertools
import math
from typing import Optional

from . import builder
from .analysis import DrawAnalysis

SIGNS = ("1", "X", "2")
SIGN_INDEX = {sign: index for index, sign in enumerate(SIGNS)}
ALL_ROWS = tuple(itertools.product(SIGNS, repeat=8))
ROW_INDEX = {row: index for index, row in enumerate(ALL_ROWS)}
X_COUNTS = tuple(row.count("X") for row in ALL_ROWS)
BUDGET = 256

CHAMPION_ID = "champion-standard-v1"


def champion_config() -> dict:
    return {"id": CHAMPION_ID, "value_weight": 0.5, "kappa_scale": 1.0,
            "x_slope": 0.0, "x_curve": 0.0, "x_quota": 0.0, "sign_cap": 1.0}


def prepare_analysis(product: str, analysis: DrawAnalysis, net_sale: float,
                     row_price: float, plan: dict,
                     budget: int = BUDGET) -> dict:
    """Förbered en 8-matchsanalys för `select_rows` — samma tal som skriptet."""
    if len(analysis.matches) != 8:
        raise ValueError("optimeraren kräver exakt åtta matcher")
    field = float(net_sale) / float(row_price)
    top = max(plan["splits"])
    pool = float(net_sale) * float(plan["ratio"]) * float(plan["splits"][top])
    base_kappa = builder.kappa_for(product, top)
    p_by_col, q_by_col = [], []
    for match in analysis.matches:
        ps, qs = [], []
        for sign in SIGNS:
            outcome = match.outcomes[sign]
            p = outcome.fair_prob if outcome.fair_prob is not None else 1 / 3
            q = ((outcome.streck / 100.0) if outcome.streck else p)
            ps.append(max(float(p), 1e-12))
            qs.append(max(float(q), 0.001))
        p_by_col.append(tuple(ps))
        q_by_col.append(tuple(qs))

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
        logp.append(lp)
        q_values.append(q)
        p_values.append(probability)
        reference_ev.append(probability * dividend)
    return {
        "product": product, "field": field, "pool": pool,
        "base_kappa": base_kappa, "logp": logp, "q": q_values,
        "p": p_values, "reference_ev": reference_ev,
        "x_distribution": builder.x_count_distribution(analysis),
        "cost": float(budget), "target": int(budget),
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
    """Välj exakt `target` rader med valfria X-minimikvoter och teckentak."""
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
        selected.append(index)
        chosen.add(index)
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
        add(index)
        needed[count] -= 1
        pointers[count] += 1

    for index in ranked:
        if index in chosen or not allowed(index):
            continue
        add(index)
        if len(selected) == target:
            return selected
    return []


def rows_for(product: str, analysis: DrawAnalysis, config: dict,
             net_sale: float, row_price: float, plan: dict,
             budget: int = BUDGET) -> list[list[str]]:
    """Konkreta rader (i matchordning) för en konfiguration; [] om omöjligt."""
    prepared = prepare_analysis(product, analysis, net_sale, row_price, plan,
                                budget=budget)
    selected = select_rows(prepared, config)
    return [list(ALL_ROWS[index]) for index in selected]
