"""Bomben-analys: +EV på exakt-resultat-spelet.

Bomben skiljer sig från tipsspelen: man tippar EXAKT resultat (t.ex. 2–1) för
3 matcher, och Svenska Spel ger INGA odds — bara folkets streck. Vår vanliga
"odds vs streck"-signal saknar därför sin viktigaste ingrediens.

Lösning: en målmodell. Pinnacles spread+total ger förväntade mål (home_xg,
away_xg) per match → oberoende Poisson → sannolikhet för varje exakt resultat.
Folkets fördelning kommer från svenskaFolket (marginalfördelning hemmamål resp.
bortamål). Värde = P_modell(resultat) ÷ folk_andel(resultat); högt = underspelat.

Modellen är sharp-ankrad (Pinnacle), men fortfarande modell-härledd för exakt
resultat — märks `model_tier` och hålls (precis som metodregeln säger) utanför
CLV-facitet.
"""
from __future__ import annotations

import math
from typing import Optional

from .pinnacle import Pinnacle
from .svenskaspel import SvenskaSpel, _f

MAX_GOALS = 7          # rutnät 0..7 mål per lag (täcker i praktiken allt)
_POISSON_N = 12        # beräkna pmf längre för korrekt normalisering


def _poisson_pmf(mu: float, n: int = MAX_GOALS) -> list[float]:
    full = [math.exp(-mu) * mu ** k / math.factorial(k) for k in range(_POISSON_N + 1)]
    pmf = full[:n + 1]
    pmf[n] += sum(full[n + 1:])      # samla svansen i sista rutan
    return pmf


def _folk_marginals(events_folk: list[dict]) -> tuple[list[float], list[float]]:
    """svenskaFolket -> (hemmamål-fördelning, bortamål-fördelning), normaliserade.
    Varje post: {score:'k-k', home:'%', away:'%'} där index k = antal mål."""
    hd, ad = {}, {}
    for row in events_folk:
        first = str(row.get("score", "")).split("-")[0]
        if not first.isdigit():
            continue                       # hoppa "F-F" (Fler än 9 mål)
        k = int(first)
        hd[k] = _f(row.get("home")) or 0.0
        ad[k] = _f(row.get("away")) or 0.0
    n = (max(hd) if hd else 0) + 1
    home = [hd.get(k, 0.0) for k in range(n)]
    away = [ad.get(k, 0.0) for k in range(n)]
    hs, as_ = sum(home) or 1.0, sum(away) or 1.0
    return [h / hs for h in home], [a / as_ for a in away]


def _participants(event: dict) -> tuple[str, str, Optional[str], Optional[str]]:
    parts = {p.get("type"): p for p in event.get("match", {}).get("participants", [])}
    h, a = parts.get("home", {}), parts.get("away", {})
    return h.get("name", ""), a.get("name", ""), h.get("isoCode"), a.get("isoCode")


def analyze_bomben(draw: dict, pin_index: Optional[list[dict]] = None) -> dict:
    """Analysera en Bomben-omgång: per match folk- och modellfördelning över
    resultat + värde (modell ÷ folk). pin_index = Pinnacle.soccer_index()."""
    matcher = Pinnacle() if pin_index else None
    matches = []
    for ev in draw.get("events", []):
        home, away, hiso, aiso = _participants(ev)
        start = ev.get("match", {}).get("matchStart")
        fh, fa = _folk_marginals(ev.get("svenskaFolket") or [])

        hit = matcher.match(home, away, hiso, aiso, pin_index, match_start=start) \
            if matcher else None
        home_xg = hit.get("home_xg") if hit else None
        away_xg = hit.get("away_xg") if hit else None
        swapped = hit.get("swapped") if hit else False
        if swapped and home_xg is not None and away_xg is not None:
            home_xg, away_xg = away_xg, home_xg   # spegla till SvS hemma/borta

        mh = _poisson_pmf(home_xg) if home_xg else None
        ma = _poisson_pmf(away_xg) if away_xg else None

        # rutnät: per exakt resultat folk-andel, modell-P och värdekvot
        grid = []
        for h in range(MAX_GOALS + 1):
            for a in range(MAX_GOALS + 1):
                folk = fh[h] * fa[a] if h < len(fh) and a < len(fa) else 0.0
                pm = (mh[h] * ma[a]) if (mh and ma) else None
                ratio = (pm / folk) if (pm is not None and folk > 0) else None
                grid.append({"score": f"{h}-{a}", "h": h, "a": a,
                             "folk": round(folk, 4),
                             "model": round(pm, 4) if pm is not None else None,
                             "ratio": round(ratio, 2) if ratio is not None else None})

        scored = [g for g in grid if g["model"] is not None and g["folk"] > 0]
        top_value = sorted(scored, key=lambda g: g["ratio"], reverse=True)[:5]
        top_model = sorted([g for g in grid if g["model"] is not None],
                           key=lambda g: g["model"], reverse=True)[:5]
        top_folk = sorted(grid, key=lambda g: g["folk"], reverse=True)[:5]

        matches.append({
            "event_number": ev.get("eventNumber"),
            "description": ev.get("eventDescription"),
            "match_start": start, "home": home, "away": away,
            "home_xg": home_xg, "away_xg": away_xg,
            "has_model": mh is not None,
            "matched": f'{hit["home"]} - {hit["away"]}' if hit else None,
            "grid": grid, "top_value": top_value,
            "top_model": top_model, "top_folk": top_folk,
        })

    if matcher:
        matcher.close()
    return {
        "draw_number": draw.get("drawNumber"),
        "state": draw.get("drawState"),
        "reg_close_time": draw.get("regCloseTime"),
        "turnover": _f(draw.get("currentNetSales")),
        "match_count": draw.get("matchCount"),
        "matches": matches,
    }
