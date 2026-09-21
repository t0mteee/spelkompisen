#!/usr/bin/env python3
"""Offline-screening på sparade frystidspriser. Skriver ALDRIG till databasen.

Ingen framtida information ges till väljaren. Historiska omgångar är redan
sedda och resultaten är därför diagnostik, inte ett opartiskt forwardtest.
"""
import argparse
from collections import Counter
import hashlib
import json
from math import prod
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import builder, pool_portfolio as portfolio, pool_system_ledger as ledger
from app.analysis import analyze_draw
from app.svenskaspel import Draw, Match, Outcome
from scripts.ph5_radvalsablation import prize_plan


def prepared_analysis(detail, row_price):
    matches, sharp = [], {}
    for e in detail["events"]:
        prices, shares = e["odds_at_freeze"], e["streck_at_freeze"]
        if any(prices.get(s) is None or prices[s] <= 1 or shares.get(s) is None
               for s in portfolio.SIGNS):
            raise ValueError(f"ofullständig frystidsinput i match {e['event_number']}")
        matches.append(Match(e["event_number"], e.get("description") or "",
            e.get("home") or "", e.get("away") or "", None, None, "", None,
            False, None, {s: Outcome(s, prices[s], None, shares[s], None)
                         for s in portfolio.SIGNS}))
        sharp[e["event_number"]] = {"odds": e["sharp_odds_at_freeze"],
                                    "total": e["total_at_freeze"]}
    draw = Draw(detail["product"], detail["draw_number"], "Open", None,
                detail["turnover_used"], row_price, detail["frozen_at"], matches=matches)
    return analyze_draw(draw, sharp=sharp)


def report(conn, product, draw, horizon, config, budget=None):
    detail = ledger.system_detail(SimpleNamespace(conn=conn), product, draw, horizon, config)
    if not detail.get("available") or not detail["timely"]:
        raise ValueError("kräver en tidsriktigt sparad referenskupong")
    row_price, jackpot = conn.execute(
        "SELECT row_price,jackpot_used FROM pool_system_ledger WHERE product=? "
        "AND draw_number=? AND horizon=? AND config_key=?", (product, draw, horizon, config)).fetchone()
    analysis = prepared_analysis(detail, row_price)
    budget = budget or detail["cost_kr"]
    if budget <= 0 or budget > 20000:
        raise ValueError("testbudget måste vara 1–20000 kr")
    plan = prize_plan(product)
    ranked, baseline, chosen, audit, probabilities = portfolio.prepare(
        analysis, budget, row_price, detail["value_weight"], plan, jackpot or 0)
    tiers = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT correct,winners,amount FROM pool_payout_tier WHERE product=? AND draw_number=?",
        (product, draw))}
    # Gemensam ROI-kohort; saknad pott får inte bli noll för ena armen.
    complete_payouts = all(level in tiers and tiers[level][0] is not None
        and tiers[level][0] > 0 and tiers[level][1] is not None for level in plan["splits"])
    outcomes = [e["outcome"] for e in detail["events"]]

    def evaluate(name, selected):
        rows = [r[2] for r in selected]
        distribution = Counter(sum(a == b for a, b in zip(r, outcomes)) for r in rows)
        payout = ledger.counterfactual_payout(distribution, tiers)[0] if complete_payouts and detail["facit_complete"] else None
        return {"arm": name, "rows": len(rows), "cost": len(rows) * row_price,
                "best": max(distribution) if detail["facit_complete"] else None,
                "payout": payout, "roi": payout / (len(rows)*row_price)-1 if payout is not None else None,
                "coverage_independent_sample": portfolio.evaluate_coverage(rows, probabilities),
                "exact_top_chance": sum(prod(probabilities[c][portfolio.SIGNS.index(s)]
                                              for c, s in enumerate(row)) for row in rows),
                "max_sign_share": max(sum(r[c] == s for r in rows) / len(rows)
                                      for c in range(len(outcomes)) for s in portfolio.SIGNS),
                "rows_hash": hashlib.sha256("\n".join("".join(r) for r in sorted(rows)).encode()).hexdigest()}

    return {"version": portfolio.VERSION, "status": "screening — inte promotion",
            "product": product, "draw": draw, "horizon": horizon, "source_config": config,
            "frozen_at": detail["frozen_at"], "budget": budget, "audit": audit,
            "snapshot_note": "senast sparade priser före frysning; inte bevis på färsk PIT-presence",
            "same_rows_as_saved": set(r[2] for r in baseline) == set(tuple(r["signs"]) for r in detail["rows"]),
            "inputs_hash": hashlib.sha256(json.dumps({"probabilities": probabilities,
                "events": [{k: e[k] for k in ("event_number", "odds_at_freeze", "streck_at_freeze",
                                              "sharp_odds_at_freeze", "total_at_freeze")}
                           for e in detail["events"]]}, sort_keys=True).encode()).hexdigest(),
            "results": [evaluate("oförändrad byggare, samma budget", baseline),
                        evaluate(portfolio.VERSION, chosen)]}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="data/stryktips.db")
    p.add_argument("--product", required=True)
    p.add_argument("--draw", type=int, required=True)
    p.add_argument("--horizon", default="m20", choices=("h3", "m20"))
    p.add_argument("--config", required=True)
    p.add_argument("--budget", type=int)
    args = p.parse_args()
    with sqlite3.connect(Path(args.db).resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        print(json.dumps(report(conn, args.product, args.draw, args.horizon, args.config, args.budget),
                         ensure_ascii=False, indent=2))
