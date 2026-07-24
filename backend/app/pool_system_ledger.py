"""PH3: systemledger — frys byggarens konkreta förslag före spelstopp och
settla mot riktigt facit + riktig utdelning (pool_draw_settlement).

Benchmarkmatrisen är FÖRREGISTRERAD: ändra aldrig en befintlig config_key i
efterhand — lägg till nya nycklar om något nytt ska mätas. Dagens byggare är
champion; ingen policyändring promoveras på det material som valde den
(förregistrerad gate + out-of-time-fönster, se överlämningen 2026-07-24).

Frysning sker i snapshotvarvet med varvets PIT-färska draw-objekt (inga
extra API-anrop utom jackpot). Sena frysningar sparas men flaggas
`timely=0` — poolvarvets kadens är 30 min (5 min i tätläget), därav
horisonttoleranserna nedan. Bomben ingår inte (egen kolumnbyggare, ingen
1X2-EV-motor).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Optional

from .analysis import DrawAnalysis, analyze_draw
from .builder import build_ev_system
from .storage import Storage
from .svenskaspel import Draw

# (minuter före spelstopp, timely-tolerans i minuter)
FREEZE_HORIZONS = {"h3": (180, 30), "m20": (20, 10)}

# Förregistrerad matris 2026-07-24 (överlämningen: 50 kr primär + få
# sekundära lägen). Värderader (EV × träffchans) — samma motor som UI:t.
BENCHMARKS = (
    {"key": "ev50-medel-vw50", "budget": 50.0, "strategy": "medel",
     "value_weight": 0.5, "primary": True},
    {"key": "ev50-tuff-vw80", "budget": 50.0, "strategy": "tuff",
     "value_weight": 0.8, "primary": False},
    {"key": "ev256-medel-vw50", "budget": 256.0, "strategy": "medel",
     "value_weight": 0.5, "primary": False},
)


def _parse(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _frozen(store: Storage, product: str, draw_number: int,
            horizon: str, key: str) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM pool_system_ledger WHERE product=? AND draw_number=? "
        "AND horizon=? AND config_key=?",
        (product, draw_number, horizon, key)).fetchone() is not None


def freeze_due(store: Storage, product: str, draw: Draw,
               sharp: Optional[dict] = None, movement: Optional[dict] = None,
               jackpot: Optional[float] = None,
               now: Optional[dt.datetime] = None,
               code_version: str = "dev") -> dict:
    """Frys benchmarksystem för en öppen omgång vars horisontfönster öppnats.
    draw = varvets färska Draw-objekt (point-in-time)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    close = _parse(draw.reg_close_time)
    report = {"frozen": 0}
    if close is None or close <= now:
        return report
    due = [(hz, mins, tol) for hz, (mins, tol) in FREEZE_HORIZONS.items()
           if now >= close - dt.timedelta(minutes=mins)]
    if not due:
        return report
    plan = _prize_plan(product)
    analysis: Optional[DrawAnalysis] = None
    for horizon, minutes, tol in due:
        for bench in BENCHMARKS:
            if _frozen(store, product, draw.draw_number, horizon, bench["key"]):
                continue
            if analysis is None:
                analysis = analyze_draw(draw, sharp or {}, movement or {})
                turnover_used, basis = _valuation_turnover(
                    store, product, analysis.turnover or 0.0)
                if turnover_used > (analysis.turnover or 0.0):
                    analysis.turnover = turnover_used
                jp = max(0.0, jackpot or 0.0)
            system = build_ev_system(
                analysis, bench["strategy"], bench["budget"],
                row_price=analysis.row_price or 1.0,
                value_weight=bench["value_weight"], plan=plan, jackpot=jp)
            if not system.rows:
                continue   # gick inte att bygga — nästa varv försöker igen
            events_order = ",".join(
                str(match.event_number) for match in analysis.matches)
            rows_text = "\n".join(",".join(row) for row in system.rows)
            covered = sum(
                1 for match in analysis.matches
                if any(match.outcomes[s].fair_prob is not None
                       for s in ("1", "X", "2")))
            cutoff = close - dt.timedelta(minutes=minutes)
            lag = round((now - cutoff).total_seconds() / 60, 1)
            store.conn.execute(
                "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
                "config_key, frozen_at, lag_min, timely, code_version, budget, "
                "strategy, value_weight, row_price, n_rows, cost_kr, "
                "events_order, rows_text, rows_hash, n_events_covered, "
                "turnover_used, turnover_basis, jackpot_used, build_note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw.draw_number, horizon, bench["key"], _iso(now),
                 lag, int(lag <= tol), code_version, bench["budget"],
                 bench["strategy"], bench["value_weight"],
                 analysis.row_price or 1.0, system.num_rows, system.cost,
                 events_order, rows_text,
                 hashlib.sha256(rows_text.encode()).hexdigest()[:16],
                 covered, turnover_used, basis, jp, system.note))
            if not store._bulk:  # noqa: SLF001
                store.conn.commit()
            report["frozen"] += 1
    return report


def _valuation_turnover(store: Storage, product: str,
                        current: float) -> tuple[float, str]:
    """Samma värderingshorisont som /api/system: prognostiserad slutomsättning
    om den är högre än live-omsättningen (annars glädje-EV tidigt i veckan)."""
    try:
        from .main import _projected_turnover
        projected = _projected_turnover(product, current) or current
    except Exception:  # noqa: BLE001 — prognosfel får inte stoppa frysningen
        projected = current
    if projected > current:
        return projected, "projected"
    return current, "live"


def _prize_plan(product: str) -> Optional[dict]:
    try:
        from .main import PRIZE_PLANS
        return PRIZE_PLANS.get(product)
    except Exception:  # noqa: BLE001
        return None


def settle_pending(store: Storage, now: Optional[dt.datetime] = None) -> dict:
    """Settla frysta system där omgångens facit finns i settlementlagret."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = store.conn.execute(
        "SELECT l.product, l.draw_number, l.horizon, l.config_key, "
        "l.events_order, l.rows_text, l.cost_kr "
        "FROM pool_system_ledger l JOIN pool_draw_settlement s "
        "ON s.product=l.product AND s.draw_number=l.draw_number "
        "WHERE l.settled_at IS NULL").fetchall()
    report = {"settled": 0, "unresolvable": 0}
    for product, draw_number, horizon, key, events_order, rows_text, cost in rows:
        outcomes = dict(store.conn.execute(
            "SELECT event_number, outcome FROM pool_event_settlement "
            "WHERE product=? AND draw_number=?", (product, draw_number)))
        tiers = dict(store.conn.execute(
            "SELECT correct, amount FROM pool_payout_tier "
            "WHERE product=? AND draw_number=? AND correct IS NOT NULL",
            (product, draw_number)))
        events = [int(e) for e in events_order.split(",")]
        note = None
        if any(outcomes.get(e) not in ("1", "X", "2") for e in events):
            # utfall saknas för någon match (extremfall) — märk, försök inte
            note = "utfall saknas för minst en match"
            store.conn.execute(
                "UPDATE pool_system_ledger SET settled_at=?, settle_note=? "
                "WHERE product=? AND draw_number=? AND horizon=? AND config_key=?",
                (_iso(now), note, product, draw_number, horizon, key))
            report["unresolvable"] += 1
            continue
        facit = [outcomes[e] for e in events]
        dist: dict[int, int] = {}
        payout = 0.0
        for line in rows_text.split("\n"):
            signs = line.split(",")
            correct = sum(1 for sign, res in zip(signs, facit) if sign == res)
            dist[correct] = dist.get(correct, 0) + 1
            payout += tiers.get(correct, 0.0) or 0.0
        correct_max = max(dist) if dist else 0
        roi = round(payout / cost - 1.0, 4) if cost else None
        store.conn.execute(
            "UPDATE pool_system_ledger SET settled_at=?, correct_max=?, "
            "correct_dist=?, payout_kr=?, roi=?, settle_note=? "
            "WHERE product=? AND draw_number=? AND horizon=? AND config_key=?",
            (_iso(now), correct_max,
             json.dumps(dist, sort_keys=True), round(payout, 2), roi,
             "utdelning enligt faktiska nivåer; egen vinst späder inte (approx)",
             product, draw_number, horizon, key))
        report["settled"] += 1
    if rows and not store._bulk:  # noqa: SLF001
        store.conn.commit()
    return report


def summary(store: Storage) -> dict:
    """Champion-baseline-läget: per config × horisont över settlade system."""
    out = []
    for row in store.conn.execute(
            "SELECT config_key, horizon, COUNT(*) n, "
            "SUM(CASE WHEN settled_at IS NOT NULL AND correct_max IS NOT NULL "
            "THEN 1 ELSE 0 END) n_settled, "
            "SUM(CASE WHEN timely=1 THEN 1 ELSE 0 END) n_timely, "
            "SUM(CASE WHEN settled_at IS NOT NULL THEN cost_kr ELSE 0 END) cost, "
            "SUM(COALESCE(payout_kr, 0)) payout, MAX(correct_max) best "
            "FROM pool_system_ledger GROUP BY config_key, horizon "
            "ORDER BY config_key, horizon"):
        key, horizon, n, n_settled, n_timely, cost, payout, best = row
        out.append({
            "config_key": key, "horizon": horizon, "n_frozen": n,
            "n_settled": n_settled, "n_timely": n_timely,
            "cost_kr": round(cost or 0, 2), "payout_kr": round(payout or 0, 2),
            "roi": round((payout or 0) / cost - 1, 4) if cost else None,
            "best_correct": best,
            "primary": any(b["key"] == key and b["primary"] for b in BENCHMARKS),
        })
    recent = [{
        "product": r[0], "draw_number": r[1], "horizon": r[2],
        "config_key": r[3], "frozen_at": r[4], "timely": bool(r[5]),
        "n_rows": r[6], "cost_kr": r[7], "correct_max": r[8],
        "payout_kr": r[9], "roi": r[10],
    } for r in store.conn.execute(
        "SELECT product, draw_number, horizon, config_key, frozen_at, timely, "
        "n_rows, cost_kr, correct_max, payout_kr, roi FROM pool_system_ledger "
        "ORDER BY frozen_at DESC LIMIT 40")]
    return {"benchmarks": [dict(b) for b in BENCHMARKS],
            "horizons": {k: {"minutes": v[0], "tolerance_min": v[1]}
                         for k, v in FREEZE_HORIZONS.items()},
            "groups": out, "recent": recent}
