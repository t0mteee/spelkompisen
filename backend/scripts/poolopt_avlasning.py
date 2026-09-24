"""Formell avläsning av pooloptimeraren v1 vid 40 parade omgångar.

Regeln låstes i docs/poolopt-v1-avlasning-2026-09-24.md (commit d123e6c)
innan skriptet kördes första gången: de 40 första parade omgångarna per cell
(arm × horisont), kronologiskt efter championens frysning, med optimerarens
egen metod (träff-Δ, ROI-Δ winsoriserad ±2,0, percentilbootstrap-KI90 med
2 000 dragningar). "Parad" är exakt `pool_system_ledger.research_gate`.

Read-only: databasen öppnas med mode=ro. Skriver bara den JSON som anges
med --out.

    .venv/bin/python -B scripts/poolopt_avlasning.py \
      --out ../docs/poolopt-v1-avlasning-2026-09-24.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pool_system_ledger import (CHAMPION_KEY, FREEZE_HORIZONS,  # noqa: E402
                                    POOLOPT_FORWARD_CONFIGS, _unit_of)
from app.storage import DEFAULT_DB  # noqa: E402
from scripts.optimera_topptips256 import (SEED, WINSOR_ROI_DIFF,  # noqa: E402
                                          _bootstrap_ci)

READING = "forward40"
N_DRAWS = 40
VERSION = "poolopt-v1-avlasning-40"


def _parse(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _mean(values: list[float]):
    return sum(values) / len(values) if values else None


def load_rows(conn: sqlite3.Connection) -> dict[tuple, dict]:
    keys = [c["key"] for c in POOLOPT_FORWARD_CONFIGS] + [CHAMPION_KEY]
    marks = ",".join("?" for _ in keys)
    out: dict[tuple, dict] = {}
    for (product, draw, horizon, key, frozen_at, timely, correct_max,
         payout_complete, payout_kr, cost_kr) in conn.execute(
            "SELECT product, draw_number, horizon, config_key, frozen_at, "
            "timely, correct_max, payout_complete, payout_kr, cost_kr "
            f"FROM pool_system_ledger WHERE config_key IN ({marks})", keys):
        if horizon not in FREEZE_HORIZONS:
            continue
        out[(product, int(draw), horizon, key)] = {
            "frozen_at": frozen_at, "timely": bool(timely),
            "open": correct_max is None,
            "complete": bool(payout_complete) if payout_complete is not None else False,
            "correct_max": correct_max,
            "payout_kr": float(payout_kr or 0.0), "cost_kr": float(cost_kr or 0.0),
        }
    return out


def n_events(conn: sqlite3.Connection) -> dict[tuple, int]:
    return {(p, int(d)): int(n) for p, d, n in conn.execute(
        "SELECT product, draw_number, n_events FROM pool_draw_settlement "
        "WHERE n_events IS NOT NULL")}


def reading(conn: sqlite3.Connection) -> dict:
    rows = load_rows(conn)
    events = n_events(conn)
    cells = []
    for config in POOLOPT_FORWARD_CONFIGS:
        arm = config["key"]
        for horizon in FREEZE_HORIZONS:
            paired = []
            for (product, draw, hz, key), arm_row in rows.items():
                if key != arm or hz != horizon:
                    continue
                champ = rows.get((product, draw, horizon, CHAMPION_KEY))
                if champ is None:
                    continue
                members = (arm_row, champ)
                if any(m["open"] for m in members):
                    continue
                if not all(m["timely"] for m in members):
                    continue
                if not all(m["complete"] for m in members):
                    continue
                paired.append((_parse(champ["frozen_at"]), product, draw,
                               arm_row, champ))
            paired.sort(key=lambda item: (item[0], item[1], item[2]))
            units = {_unit_of(p, "family") for _, p, _, _, _ in paired}
            chosen = paired[:N_DRAWS]
            hit_d, roi_d, arm_hits, champ_hits = [], [], 0, 0
            draws = []
            for frozen, product, draw, arm_row, champ in chosen:
                target = events.get((product, draw), 8)
                a_hit = int(arm_row["correct_max"] == target)
                c_hit = int(champ["correct_max"] == target)
                a_roi = arm_row["payout_kr"] / arm_row["cost_kr"] - 1 if arm_row["cost_kr"] else None
                c_roi = champ["payout_kr"] / champ["cost_kr"] - 1 if champ["cost_kr"] else None
                arm_hits += a_hit
                champ_hits += c_hit
                hit_d.append(float(a_hit - c_hit))
                if a_roi is not None and c_roi is not None:
                    roi_d.append(max(-WINSOR_ROI_DIFF,
                                     min(WINSOR_ROI_DIFF, a_roi - c_roi)))
                draws.append({"product": product, "draw_number": draw,
                              "frozen_at": frozen.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "arm_hit": a_hit, "champion_hit": c_hit,
                              "arm_roi": a_roi, "champion_roi": c_roi})
            hit_ci = _bootstrap_ci(hit_d, f"{READING}|{horizon}|{arm}|hit")
            roi_ci = _bootstrap_ci(roi_d, f"{READING}|{horizon}|{arm}|roi")
            enough = len(chosen) >= N_DRAWS
            passed = bool(enough and ((hit_ci and hit_ci[0] > 0)
                                      or (roi_ci and roi_ci[0] > 0)))
            cells.append({
                "arm": arm, "arm_label": config.get("label"),
                "horizon": horizon,
                "horizon_minutes": FREEZE_HORIZONS[horizon][0],
                "units": sorted(units),
                "paired_available": len(paired), "n": len(chosen),
                "enough": enough,
                "arm_hits": arm_hits, "champion_hits": champ_hits,
                "mean_hit_delta": _mean(hit_d), "hit_delta_ci90": hit_ci,
                "roi_n": len(roi_d),
                "mean_winsor_roi_delta": _mean(roi_d), "winsor_roi_delta_ci90": roi_ci,
                "gate_passed": passed,
                "first": draws[0] if draws else None,
                "last": draws[-1] if draws else None,
                "draws": draws,
            })
    return {"version": VERSION, "reading": READING, "n_draws": N_DRAWS,
            "seed_base": SEED, "winsor": WINSOR_ROI_DIFF,
            "champion_key": CHAMPION_KEY, "cells": cells}


def _fmt(value, digits=3):
    return "–" if value is None else f"{value:+.{digits}f}"


def _ci(pair):
    return "–" if not pair else f"[{pair[0]:+.3f}; {pair[1]:+.3f}]"


def markdown(report: dict) -> str:
    lines = ["| arm | horisont | n | träffar arm/champion | träff-Δ/omg | KI90 | "
             "ROI-Δ winsor | KI90 | grind |",
             "|---|---|---|---|---|---|---|---|---|"]
    for c in report["cells"]:
        lines.append(
            f"| {c['arm_label']} | {c['horizon_minutes']} min | {c['n']} | "
            f"{c['arm_hits']}/{c['champion_hits']} | {_fmt(c['mean_hit_delta'])} | "
            f"{_ci(c['hit_delta_ci90'])} | {_fmt(c['mean_winsor_roi_delta'])} | "
            f"{_ci(c['winsor_roi_delta_ci90'])} | "
            f"{'passerad' if c['gate_passed'] else 'ej passerad'} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", help="JSON-fil att skriva")
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        report = reading(conn)
    finally:
        conn.close()
    if args.out:
        pathlib.Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
    print(markdown(report))
    for c in report["cells"]:
        print(f"{c['arm_label']} {c['horizon']}: tillgängliga par {c['paired_available']}, "
              f"första {c['first'] and c['first']['frozen_at']}, "
              f"sista {c['last'] and c['last']['frozen_at']}, enheter {c['units']}")


if __name__ == "__main__":
    main()
