"""Presentationsvarning för det underlag analysen/bygget faktiskt fick.

Inga nätanrop, modelländringar eller antaganden om varför priser saknas.
Ett befintligt pris är inte ett bevis på färsk presence. Cachade Pinnacle-
priser har däremot redan passerat pool-sharp-freshness-v1 i analysen: ett
borttaget pris räknas som saknat och matchens `sharp_stale` säger varför.
"""
import math

from .pool_sharp_freshness import VERSION as FRESHNESS_VERSION

VERSION = "pool-input-health-v1"
SIGNS = ("1", "X", "2")


def _price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 1


def _level(counts: dict, issues: list) -> str:
    """error = 1X2 saknas helt; info = Pinnacle saknas men varje sådan match har
    en referens (pool-reference-v1) och SvS 1X2 är komplett — Ö/U-hålet är
    då känt (ingen källa har totalen sedan Pinnacle stängde) och larmar inte
    som varning; annars warning när något saknas."""
    if counts["missing_all"]:
        return "error"
    if not issues:
        return "ok"
    covered = (counts["missing_svs"] == 0 and counts["missing_sharp"] > 0
               and counts["reference_1x2"] == counts["missing_sharp"])
    return "info" if covered else "warning"


def report(analysis):
    issues = []
    counts = {"missing_sharp": 0, "missing_svs": 0, "missing_all": 0, "missing_total": 0,
              "stale_sharp": 0, "reference_1x2": 0}
    for match in analysis.matches:
        svs = all(s in match.outcomes and _price(match.outcomes[s].odds) for s in SIGNS)
        sharp = all(s in match.outcomes and _price(match.outcomes[s].sharp_odds) for s in SIGNS)
        line = match.total_line
        total = (isinstance(line, (int, float)) and math.isfinite(line) and line > 0
                 and _price(match.total_over_odds) and _price(match.total_under_odds))
        stale = getattr(match, "sharp_stale", None)
        if stale:
            counts["stale_sharp"] += 1
        missing = []
        for key, missing_value, label in (
                ("missing_svs", not svs, "SvS 1X2"),
                ("missing_sharp", not sharp, "Pinnacle 1X2"),
                ("missing_total", not total, "Pinnacle Ö/U")):
            if missing_value:
                counts[key] += 1
                missing.append(label)
        if not svs and not sharp:
            counts["missing_all"] += 1
        reference = getattr(match, "reference_1x2", None) or None
        if not sharp and reference:
            counts["reference_1x2"] += 1
        if missing:
            issues.append({"event_number": match.event_number,
                           "description": match.description or f"Match {match.event_number}",
                           "missing": missing, "no_complete_1x2": not svs and not sharp,
                           "prob_source": match.prob_source,
                           "reserve_total": getattr(match, "reserve_total", None),
                           # Varför Pinnacle saknas när ett cachat pris fanns men
                           # inte fick användas; None = inget pris i cachen alls.
                           "reason": (stale.get("text") if stale else None),
                           # pool-reference-v1: källorna som visas i Pinnacles ställe
                           "reference": sorted(reference) if reference else [],
                           "sharp_stale": stale})
    return {"version": VERSION, "freshness_version": FRESHNESS_VERSION,
            "product": analysis.product, "draw_number": analysis.draw_number,
            "analysis_fetched_at": analysis.fetched_at, "n_matches": len(analysis.matches),
            "level": _level(counts, issues),
            **counts, "issues": issues}
