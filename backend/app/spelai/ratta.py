"""Rättning: PH3:s kontrafaktiska facit för agentens förslag och standarden.

Samma väg som `pool_system_ledger.settle_pending`: officiellt utfall per
eventNumber ur `pool_event_settlement` (struken match = SvS fastställda
tecken), publicerade vinnare/belopp ur `pool_payout_tier` och egen utspädning
(`counterfactual_settle` → `counterfactual_payout`). 0 officiella vinnare på
en nivå = rullpott okänd ⇒ ofullständigt facit, ROI räknas aldrig som noll.
En inställd omgång är ingen observation. Append-once i `spelai_pool_result`.
"""
from __future__ import annotations

import datetime as dt
import json

from .. import pool_settlement
from .. import pool_system_ledger as ph3
from . import nivaer
from .tillstand import iso

SETTLEMENT_VERSION = f"spelai-v1/{ph3.SETTLEMENT_VERSION}"


def _rows_of(fmt: str, rows_text, msystem_json) -> list[str]:
    if fmt == "msystem":
        return nivaer.expandera(json.loads(msystem_json))
    return [line for line in (rows_text or "").splitlines() if line]


def settle(conn_or_store, *, now: dt.datetime) -> dict:
    """Rätta frysta förslag vars omgång har facit i settlementlagret."""
    store = conn_or_store
    conn = store.conn
    report = {"rattade": 0, "installda": 0, "olosliga": 0}
    rows = conn.execute(
        "SELECT p.id, p.product, p.draw_number, p.events_order, p.format, "
        "p.rows_text, p.msystem_json, p.cost_kr, s.draw_state "
        "FROM spelai_pool_proposal p JOIN pool_draw_settlement s "
        "ON s.product=p.product AND s.draw_number=p.draw_number "
        "WHERE p.status='fryst' AND NOT EXISTS ("
        "  SELECT 1 FROM spelai_pool_result r WHERE r.proposal_id=p.id)").fetchall()
    for (proposal_id, product, draw_number, events_order, fmt, rows_text,
         msystem_json, cost, draw_state) in rows:
        base = (proposal_id, iso(now), SETTLEMENT_VERSION)
        if draw_state == pool_settlement.CANCELLED_STATE:
            conn.execute(
                "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
                "settlement_version, cost_kr, note) VALUES (?,?,?,?,?)",
                (*base, cost, ph3.CANCELLED_NOTE))
            report["installda"] += 1
            continue
        events = [int(e) for e in (events_order or "").split(",") if e]
        facit = ph3.counterfactual_settle(
            store, product, draw_number, events,
            _rows_of(fmt, rows_text, msystem_json), cost)
        if facit is None:
            conn.execute(
                "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
                "settlement_version, cost_kr, note) VALUES (?,?,?,?,?)",
                (*base, cost, ph3.UNRESOLVABLE_NOTE))
            report["olosliga"] += 1
            continue
        conn.execute(
            "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
            "settlement_version, correct_max, correct_dist, payout_kr, "
            "published_payout_kr, payout_complete, cost_kr, roi, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (*base, facit["correct_max"], json.dumps(facit["dist"], sort_keys=True),
             facit["payout"], facit["published"], int(facit["complete"]), cost,
             facit["roi"], facit["note"]))
        report["rattade"] += 1
    if rows:
        conn.commit()
    return report
