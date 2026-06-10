"""CLV-facit: mäter om våra signaler SLÅR stängningslinjen.

Vi flaggar värdetecken (grön kvot ≥ 1.08) och sharp-edges (≥ 2 %), men utan
facit vet vi inte om signalerna är äkta. Closing Line Value = devigad
Pinnacle-sannolikhet vid avspark minus dito när vi flaggade. Positiv
snitt-CLV över många flaggor = vi hittar värde innan marknaden; negativ =
vi lurar oss själva. (Mönster portat från VM-kollen.)

Metodregel: endast marknadspriser (Pinnacle devigad via power, annars SvS-odds)
får logga flaggor — inga modellhärledda sannolikheter i facitet.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .analysis import analyze_draw, _power_probs
from .storage import Storage
from .svenskaspel import Draw, SvenskaSpel

FLAG_RATIO = 1.08      # grön värde-kvot
FLAG_EDGE = 0.02       # sharp tror ≥ 2 procentenheter mer än SvS-oddsen
RESULT_RETRY_H = 6     # försök hämta facit högst var 6:e timme per omgång


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def log_flags(product: str, draw: Draw, store: Storage) -> int:
    """Körs av snapshot-pollen: logga tecken med grön värde-kvot eller sharp-edge.
    first/best per selektion — CLV utvärderas från FÖRSTA flaggan."""
    sharp = store.get_sharp(product, draw.draw_number)
    a = analyze_draw(draw, sharp, {})
    at = _now().isoformat()
    n = 0
    for m in a.matches:
        if m.cancelled or not m.match_start:
            continue
        start = _parse(m.match_start)
        if start and start <= _now():
            continue                      # flagga aldrig efter avspark
        for s, o in m.outcomes.items():
            ratio = (o.fair_prob / (o.streck / 100.0)) \
                if (o.fair_prob and o.streck) else None
            types = []
            if ratio and ratio >= FLAG_RATIO:
                types.append("värde")
            if o.edge_vs_ss is not None and o.edge_vs_ss >= FLAG_EDGE:
                types.append("sharp")
            if not types:
                continue
            prob = o.sharp_prob if o.sharp_prob is not None else o.fair_prob
            if prob is None:
                continue
            store.log_value_flag({
                "product": product, "draw_number": draw.draw_number,
                "event_number": m.event_number, "sign": s,
                "description": m.description, "match_start": m.match_start,
                "flag_type": "+".join(types), "odds": o.odds, "prob": prob,
                "prob_src": "pinnacle" if o.sharp_prob is not None else "svenskaspel",
                "streck": o.streck, "ratio": ratio,
            }, at)
            n += 1
    return n


def resolve(store: Storage, ss: Optional[SvenskaSpel] = None) -> dict:
    """Sätt stängningslinje (lokala sharp-snapshots, inga API-anrop) för startade
    matcher, och facit (kräver API) för avgjorda omgångar."""
    now = _now()
    closed = 0
    for f in store.unresolved_closings():
        start = _parse(f["match_start"])
        if not start or start > now:
            continue
        hist = store.sharp_history(f["product"], f["draw_number"], f["event_number"])
        last: dict[str, float] = {}
        for r in hist:
            t = _parse(r["fetched_at"])
            if t and t <= start and r["odds"]:
                last[r["sign"]] = r["odds"]   # sista före avspark vinner
        if all(s in last for s in ("1", "X", "2")):
            probs = _power_probs({s: 1.0 / o for s, o in last.items()})
            store.set_closing(f["product"], f["draw_number"], f["event_number"],
                              f["sign"], prob=round(probs[f["sign"]], 4),
                              odds=last[f["sign"]])
            closed += 1
        elif (now - start).total_seconds() > 3600:
            store.set_closing(f["product"], f["draw_number"], f["event_number"],
                              f["sign"], note="stängningsodds saknas")

    outcomes = 0
    if ss is not None:
        for product, dn in store.draws_missing_outcome():
            key = f"clv_res_try_{product}_{dn}"
            tried = _parse(store.meta_get(key))
            if tried and (now - tried).total_seconds() < RESULT_RETRY_H * 3600:
                continue
            store.meta_set(key, now.isoformat())
            try:
                res = ss.get_result(product, dn)
            except Exception:  # noqa: BLE001 — SvS 500:ar ibland, försök igen senare
                continue
            if res and res.get("outcomes"):
                outcomes += store.set_outcomes(product, dn, res["outcomes"])
    return {"closings": closed, "outcomes": outcomes}


def report(store: Storage, product: Optional[str] = None) -> dict:
    """Sammanställning + radlista för UI:t."""
    rows = store.clv_rows(product)
    scored = [r for r in rows if r["closing_prob"] is not None and r["first_prob"]]
    for r in scored:
        r["clv_pp"] = round((r["closing_prob"] - r["first_prob"]) * 100, 2)
    beat = [r for r in scored if r["clv_pp"] > 0]
    judged = [r for r in rows if r["outcome"] is not None]
    hits = [r for r in judged if r["outcome"]]
    return {
        "n_flagged": len(rows),
        "n_scored": len(scored),
        "beat_pct": round(len(beat) / len(scored), 3) if scored else None,
        "avg_clv_pp": round(sum(r["clv_pp"] for r in scored) / len(scored), 2) if scored else None,
        "n_judged": len(judged),
        "hit_pct": round(len(hits) / len(judged), 3) if judged else None,
        "avg_streck": round(sum(r["first_streck"] or 0 for r in judged) / len(judged), 1) if judged else None,
        "rows": rows[:120],
    }
