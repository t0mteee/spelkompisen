"""Härleda 1X2 från asiatisk handikapp (spread) + over/under (total).

När Pinnacle ännu inte öppnat moneyline (1X2) men har spread/total kan vi ändå
uppskatta 1X2 — och, viktigast, fånga hur oddset *rör sig* när linjerna rör sig.

Metod (väletablerad):
  supremacy  = balanserad handikapplinje (där hemma/borta är 50/50) -> förväntad
               måldifferens hemma−borta
  total      = balanserad over/under-linje -> förväntat antal mål
  hemma_xg = (total + supremacy)/2,  borta_xg = (total − supremacy)/2
  Poisson (oberoende lag) -> P(1), P(X), P(2) -> decimalodds
Detta är en uppskattning, inte Pinnacles riktiga 1X2 — markeras som "derived".
"""
from __future__ import annotations

import math
from typing import Optional


def american_to_prob(a: Optional[float]) -> Optional[float]:
    if a is None:
        return None
    return (-a) / (-a + 100) if a < 0 else 100 / (a + 100)


def _cross_at_half(pairs: list[tuple[float, float]]) -> Optional[float]:
    """Linje (x) där sannolikheten (y) korsar 0.5, linjär interpolation."""
    pts = sorted(pairs)
    if not pts:
        return None
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if (y1 - 0.5) * (y2 - 0.5) <= 0 and y2 != y1:
            return x1 + (0.5 - y1) * (x2 - x1) / (y2 - y1)
    return min(pts, key=lambda p: abs(p[1] - 0.5))[0]  # närmast 0.5


def _supremacy(spread_prices: list[dict]) -> Optional[float]:
    """Förväntad måldifferens hemma−borta från spread-marknaderna."""
    pairs = []
    by_line: dict[float, dict] = {}
    for p in spread_prices:
        by_line.setdefault(abs(p["points"]), {})[p["designation"]] = p
    for _, hp in by_line.items():
        if "home" not in hp or "away" not in hp:
            continue
        ph = american_to_prob(hp["home"]["price"])
        pa = american_to_prob(hp["away"]["price"])
        if not ph or not pa:
            continue
        line = hp["home"]["points"]            # hemmalagets handikapp (+ = underdog)
        pairs.append((line, ph / (ph + pa)))   # P(hemma täcker), ökar med line
    if len(pairs) < 2:
        return None
    h_star = _cross_at_half(pairs)             # line där hemma är 50/50
    return None if h_star is None else -h_star  # supremacy = −balanserad linje


def _expected_total(total_prices: list[dict]) -> Optional[float]:
    pairs = []
    by_line: dict[float, dict] = {}
    for p in total_prices:
        by_line.setdefault(p["points"], {})[p["designation"]] = p
    for line, ou in by_line.items():
        if "over" not in ou or "under" not in ou:
            continue
        po = american_to_prob(ou["over"]["price"])
        pu = american_to_prob(ou["under"]["price"])
        if not po or not pu:
            continue
        pairs.append((line, po / (po + pu)))   # P(over), minskar med line
    if len(pairs) < 2:
        return None
    return _cross_at_half(pairs)


def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def goal_expectations(spread_prices: list[dict],
                      total_prices: list[dict]) -> Optional[tuple[float, float]]:
    """Förväntade mål (home_xg, away_xg) ur Pinnacles spread + total.
    Underlag för både derive_1x2 och Bombens resultatmodell (oberoende Poisson)."""
    sup = _supremacy(spread_prices)
    mu = _expected_total(total_prices)
    if sup is None or mu is None or mu <= 0:
        return None
    return max(0.03, (mu + sup) / 2), max(0.03, (mu - sup) / 2)


def derive_1x2(spread_prices: list[dict], total_prices: list[dict],
               max_goals: int = 12) -> Optional[dict]:
    """Returnerar {'1','X','2'} decimalodds eller None om underlag saknas."""
    xg = goal_expectations(spread_prices, total_prices)
    if xg is None:
        return None
    home_xg, away_xg = xg
    ph = pd = pa = 0.0
    home_pmf = [_poisson(i, home_xg) for i in range(max_goals + 1)]
    away_pmf = [_poisson(j, away_xg) for j in range(max_goals + 1)]
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = home_pmf[i] * away_pmf[j]
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
    tot = ph + pd + pa
    if tot <= 0:
        return None
    ph, pd, pa = ph / tot, pd / tot, pa / tot
    if min(ph, pd, pa) <= 0:
        return None
    return {"1": round(1 / ph, 2), "X": round(1 / pd, 2), "2": round(1 / pa, 2)}
