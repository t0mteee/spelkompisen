"""Presentationsvarning för det underlag analysen/bygget faktiskt fick.

Inga nätanrop, modelländringar eller antaganden om varför priser saknas.
Ett befintligt pris är inte ett bevis på färsk presence.
"""
import math

VERSION = "pool-input-health-v1"
SIGNS = ("1", "X", "2")


def _price(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 1


def report(analysis):
    issues = []
    counts = {"missing_sharp": 0, "missing_svs": 0, "missing_all": 0, "missing_total": 0}
    for match in analysis.matches:
        svs = all(s in match.outcomes and _price(match.outcomes[s].odds) for s in SIGNS)
        sharp = all(s in match.outcomes and _price(match.outcomes[s].sharp_odds) for s in SIGNS)
        line = match.total_line
        total = (isinstance(line, (int, float)) and math.isfinite(line) and line > 0
                 and _price(match.total_over_odds) and _price(match.total_under_odds))
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
        if missing:
            issues.append({"event_number": match.event_number,
                           "description": match.description or f"Match {match.event_number}",
                           "missing": missing, "no_complete_1x2": not svs and not sharp,
                           "prob_source": match.prob_source})
    return {"version": VERSION, "product": analysis.product, "draw_number": analysis.draw_number,
            "analysis_fetched_at": analysis.fetched_at, "n_matches": len(analysis.matches),
            "level": "error" if counts["missing_all"] else "warning" if issues else "ok",
            **counts, "issues": issues}
