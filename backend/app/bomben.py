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
RATIO = 0.65           # antagen återbetalningsandel (Oddset-pool); skalar bara EV-nivån
BUILD_CAND = 6         # kandidatresultat per match i radbyggaren (6^3 = 216 rader)


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
    fund = draw.get("fund") or {}
    rullpott = (_f(fund.get("rolloverIn")) or 0.0) + (_f(fund.get("extraMoney")) or 0.0)
    return {
        "draw_number": draw.get("drawNumber"),
        "state": draw.get("drawState"),
        "reg_close_time": draw.get("regCloseTime"),
        "turnover": _f(draw.get("currentNetSales")),
        "rullpott": rullpott,
        "match_count": draw.get("matchCount"),
        "matches": matches,
    }


def build_bomben_system(analysis: dict, budget: float = 50.0,
                        row_price: float = 1.0) -> dict:
    """Bygg ett KOLUMN-baserat Bomben-system: per match väljs hemmamål- och
    bortamål-kolumner (det kupongen faktiskt markerar). Radantalet = produkten
    av kolumnerna = exakt vad du fyller i OCH betalar OCH får i filen — inga
    förvirrande reduceringar. Kolumnerna väljs girigt EV-viktat: lägg till den
    mål-kolumn som ökar systemets förväntade utdelning mest per ny rad.
    EV = Σ_rader P_modell(rad) × pott/(fält × folk(rad)+1); pott = oms×andel + rullpott."""
    matches = analysis.get("matches") or []
    if not matches:
        return {"rows": [], "note": "Ingen data."}
    turnover = analysis.get("turnover") or 0.0
    pott = turnover * RATIO + (analysis.get("rullpott") or 0.0)
    field = (turnover / row_price) if (turnover and row_price) else 0.0
    target = max(1, int(budget / row_price))

    # marginalfördelningar per match (mål-kolumner): modell (folk som fallback) + folk
    per = []
    for m in matches:
        hp, ap, hf, af = {}, {}, {}, {}
        for g in m["grid"]:
            mod = g["model"] if g["model"] is not None else (g["folk"] or 0.0)
            hp[g["h"]] = hp.get(g["h"], 0.0) + mod
            ap[g["a"]] = ap.get(g["a"], 0.0) + mod
            hf[g["h"]] = hf.get(g["h"], 0.0) + (g["folk"] or 0.0)
            af[g["a"]] = af.get(g["a"], 0.0) + (g["folk"] or 0.0)
        home_order = sorted([k for k in hp if hp[k] > 0.003], key=lambda k: hp[k], reverse=True) or [0]
        away_order = sorted([k for k in ap if ap[k] > 0.003], key=lambda k: ap[k], reverse=True) or [0]
        per.append({"ev": m["event_number"], "desc": m["description"],
                    "hp": hp, "ap": ap, "hf": hf, "af": af,
                    "home_order": home_order, "away_order": away_order,
                    # börja med varje matchs mest sannolika hemma- och bortamål
                    "H": home_order[:1], "A": away_order[:1]})

    def system_ev() -> tuple[float, float, float, int]:
        """Enumerera produktraderna -> (EV-utdelning, P(alla rätt), Σfolk, antal rader)."""
        ev = pall = 0.0
        combos = [(1.0, 1.0)]   # (P_modell, folk) ackumulerat
        for p in per:
            nxt = []
            for h in p["H"]:
                for a in p["A"]:
                    pm = p["hp"].get(h, 0.0) * p["ap"].get(a, 0.0)
                    pf = p["hf"].get(h, 0.0) * p["af"].get(a, 0.0)
                    for cpm, cpf in combos:
                        nxt.append((cpm * pm, cpf * pf))
            combos = nxt
        for pm, pf in combos:
            div = min(pott, pott / (field * pf + 1.0)) if (pott and field) else 0.0
            ev += pm * div
            pall += pm
        return ev, pall, 0.0, len(combos)

    def rows_count() -> int:
        r = 1
        for p in per:
            r *= len(p["H"]) * len(p["A"])
        return r

    # girigt: lägg till den kolumn (hemma/borta i någon match) som ger mest
    # EV-ökning per ny rad, så länge radantalet ryms i budget
    cur_ev = system_ev()[0]
    while True:
        best, best_eff = None, 0.0
        base_rows = rows_count()
        for p in per:
            for axis, order, sel in (("H", p["home_order"], p["H"]), ("A", p["away_order"], p["A"])):
                nxt = next((g for g in order if g not in sel), None)
                if nxt is None:
                    continue
                new_rows = base_rows // (len(sel)) * (len(sel) + 1)
                if new_rows > target:
                    continue
                sel.append(nxt)
                ev2 = system_ev()[0]
                sel.pop()
                eff = (ev2 - cur_ev) / (new_rows - base_rows) if new_rows > base_rows else 0.0
                if eff > best_eff:
                    best, best_eff = (p, axis, nxt, ev2), eff
        if best is None:
            break
        p, axis, g, ev2 = best
        p[axis].append(g)
        p[axis].sort()
        cur_ev = ev2

    # bygg de konkreta produktraderna (för fil/kopia/tabell) + EV per rad
    detail = []
    combos = [[]]
    for p in per:
        combos = [c + [f"{h}-{a}"] for c in combos for h in p["H"] for a in p["A"]]
    for r in combos:
        pm = pf = 1.0
        for p, s in zip(per, r):
            h, a = (int(x) for x in s.split("-"))
            pm *= p["hp"].get(h, 0.0) * p["ap"].get(a, 0.0)
            pf *= p["hf"].get(h, 0.0) * p["af"].get(a, 0.0)
        div = min(pott, pott / (field * pf + 1.0)) if (pott and field) else 0.0
        detail.append({"scores": r, "p": pm, "folk": pf, "ev": pm * div, "dividend": div})
    detail.sort(key=lambda x: x["ev"], reverse=True)

    num_rows = len(detail)
    cost = num_rows * row_price
    ev_sum = sum(c["ev"] for c in detail)
    used = [{"event_number": p["ev"], "description": p["desc"],
             "home_goals": sorted(p["H"]), "away_goals": sorted(p["A"]),
             "scores": sorted({f"{h}-{a}" for h in p["H"] for a in p["A"]})}
            for p in per]
    return {
        "rows": [c["scores"] for c in detail],
        "detail": detail, "used": used,
        "num_rows": num_rows, "cost": round(cost, 2),
        "manual_rows": num_rows,   # kolumn-system: manuell = fil = exakt detta
        "ev_payout": round(ev_sum, 0), "ev": round(ev_sum - cost, 0),
        "pott": round(pott, 0),
        "p_all": round(sum(c["p"] for c in detail), 5),
        "note": f"{num_rows} rader (kolumnval, EV-optimerat) vid "
                f"{turnover:,.0f} kr oms + {analysis.get('rullpott') or 0:,.0f} kr rullpott."
                .replace(",", " "),
    }
