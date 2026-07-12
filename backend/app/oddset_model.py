"""Egen målmodell för Oddset-delen (Etapp 3): Dixon-Coles per liga.

Styrkor (anfall/försvar per lag + hemmafördel per liga) fittas iterativt på
resultat sedan 2024 med exponentiell tidsavklingning. Där Sofascore-xG finns
används xG-viktad "effektiv målproduktion" (0.65·xG + 0.35·mål) — xG är mindre
brusig än utfallet. Totalnivån ANKRAS mot devigad sharp ÖU-linje när Pinnacle
finns (vm-lärdomen: linjen ≈ median, okalibrerad μ blir systematiskt fel).

METODREGEL (vm, tre gånger bevisad): modell-edges utan sharp-ankare är
systematiskt uppblåsta → allt härifrån är AMBER-tier: bakom toggle i UI,
ALDRIG in i CLV-facitet. Grön blir modellen först om backtesten (Etapp 5) håller.

Träningsmatcher modelleras INTE (rotationsrisk — där är steam/nyheter verktyget).
"""
from __future__ import annotations

import datetime as dt
import math
from difflib import SequenceMatcher
from typing import Optional

from . import oddset_data
from .analysis import _power_probs
from .storage import Storage

DC_RHO_CLUB = -0.01     # REFITTAD i Etapp 5-backtesten (2026-07-12): grid-minimum
                        # −0.01/+0.02 i BÅDA ligorna — klubblitteraturens −0.13
                        # överkorrigerar här precis som för landslag (vm: −0.04)
MAX_GOALS = 12
XG_WEIGHT = 0.65        # effektiva mål = 0.65·xG + 0.35·mål (när xG finns)
DECAY_DAYS = 240.0      # vikt = exp(-ålder/240 d) — ~1 säsong halveringstid
FIT_ITER = 80
MODEL_EDGE_SHOW = 0.05  # amber-pill först vid ≥5 % (högre ribba än sharp — okalibrerad)
MIN_MATCHES = 8         # lag med färre viktade matcher får ingen prediktion


def _pois(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dc_matrix(mu_h: float, mu_a: float, rho: float = DC_RHO_CLUB) -> list[list[float]]:
    hp = [_pois(i, mu_h) for i in range(MAX_GOALS + 1)]
    ap = [_pois(j, mu_a) for j in range(MAX_GOALS + 1)]
    m = [[hp[i] * ap[j] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
    tau = {(0, 0): 1 - mu_h * mu_a * rho, (0, 1): 1 + mu_h * rho,
           (1, 0): 1 + mu_a * rho, (1, 1): 1 - rho}
    for (i, j), t in tau.items():
        m[i][j] *= max(t, 0.0)
    s = sum(sum(row) for row in m) or 1.0
    return [[c / s for c in row] for row in m]


def matrix_1x2(m: list[list[float]]) -> dict[str, float]:
    p1 = sum(m[i][j] for i in range(len(m)) for j in range(len(m)) if i > j)
    p2 = sum(m[i][j] for i in range(len(m)) for j in range(len(m)) if i < j)
    return {"1": p1, "X": max(0.0, 1 - p1 - p2), "2": p2}


def total_over(m: list[list[float]], line: float) -> float:
    return sum(m[i][j] for i in range(len(m)) for j in range(len(m)) if i + j > line)


# --- styrkefit -------------------------------------------------------------------

def fit_league(results: list[dict], now: Optional[dt.date] = None,
               iters: int = FIT_ITER) -> Optional[dict]:
    """Iterativ Poisson-fit: λ_hemma = base·hf·att_h·def_a, λ_borta = base·att_a·def_h.
    Returnerar {'teams': {namn: {'att','def','n'}}, 'home_adv', 'base'}."""
    now = now or dt.date.today()
    rows = []
    for r in results:
        try:
            age = (now - dt.date.fromisoformat(r["date"])).days
        except ValueError:
            continue
        if age < 0:
            continue
        w = math.exp(-age / DECAY_DAYS)
        eh = (XG_WEIGHT * r["xg_h"] + (1 - XG_WEIGHT) * r["hg"]
              if r.get("xg_h") is not None else float(r["hg"]))
        ea = (XG_WEIGHT * r["xg_a"] + (1 - XG_WEIGHT) * r["ag"]
              if r.get("xg_a") is not None else float(r["ag"]))
        rows.append((r["home"], r["away"], eh, ea, w))
    if len(rows) < 40:
        return None

    teams = sorted({t for h, a, *_ in rows for t in (h, a)})
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    wsum = sum(w for *_, w in rows)
    base = sum((eh + ea) * w for _, _, eh, ea, w in rows) / (2 * wsum)
    home_adv = 1.25
    for _ in range(iters):
        exp_h = {t: 1e-9 for t in teams}
        exp_a = {t: 1e-9 for t in teams}
        obs_h = {t: 1e-9 for t in teams}
        obs_a = {t: 1e-9 for t in teams}
        exp_dh = {t: 1e-9 for t in teams}   # förväntat insläppt hemma/borta
        exp_da = {t: 1e-9 for t in teams}
        obs_dh = {t: 1e-9 for t in teams}
        obs_da = {t: 1e-9 for t in teams}
        tot_home_exp = tot_home_obs = 1e-9
        for h, a, eh, ea, w in rows:
            lh = base * home_adv * att[h] * dfn[a]
            la = base * att[a] * dfn[h]
            exp_h[h] += w * lh; obs_h[h] += w * eh
            exp_a[a] += w * la; obs_a[a] += w * ea
            exp_dh[a] += w * lh; obs_dh[a] += w * eh   # bortalagets försvar möter lh
            exp_da[h] += w * la; obs_da[h] += w * ea
            tot_home_exp += w * lh; tot_home_obs += w * eh
        for t in teams:
            att[t] *= ((obs_h[t] + obs_a[t]) / (exp_h[t] + exp_a[t])) ** 0.5
            dfn[t] *= ((obs_dh[t] + obs_da[t]) / (exp_dh[t] + exp_da[t])) ** 0.5
        m_att = sum(att.values()) / len(teams)
        m_dfn = sum(dfn.values()) / len(teams)
        for t in teams:
            att[t] /= m_att
            dfn[t] /= m_dfn
        base *= m_att * m_dfn
        home_adv *= (tot_home_obs / tot_home_exp) ** 0.5

    nw = {t: 0.0 for t in teams}
    for h, a, _, _, w in rows:
        nw[h] += w; nw[a] += w
    return {"teams": {t: {"att": round(att[t], 3), "def": round(dfn[t], 3),
                          "n": round(nw[t], 1)} for t in teams},
            "home_adv": round(home_adv, 3), "base": round(base, 3)}


def _find_team(fit: dict, norm_name: str) -> Optional[str]:
    if norm_name in fit["teams"]:
        return norm_name
    best, best_s = None, 0.6
    for t in fit["teams"]:
        if norm_name in t or t in norm_name:
            return t
        s = SequenceMatcher(None, norm_name, t).ratio()
        if s > best_s:
            best, best_s = t, s
    return best


def predict(fit: dict, home_norm: str, away_norm: str) -> Optional[tuple[float, float]]:
    h, a = _find_team(fit, home_norm), _find_team(fit, away_norm)
    if not h or not a:
        return None
    th, ta = fit["teams"][h], fit["teams"][a]
    if th["n"] < MIN_MATCHES or ta["n"] < MIN_MATCHES:
        return None
    mu_h = fit["base"] * fit["home_adv"] * th["att"] * ta["def"]
    mu_a = fit["base"] * ta["att"] * th["def"]
    return mu_h, mu_a


def _anchor_total(mu_h: float, mu_a: float, line: float,
                  p_over: float) -> tuple[float, float]:
    """Skala (mu_h, mu_a) med gemensam faktor s så att P(Över linjen) = sharp-prob.
    Bevarar modellens styrkeförhållande; totalnivån tas från marknaden."""
    lo, hi = 0.3, 3.0
    for _ in range(40):
        s = (lo + hi) / 2
        if total_over(dc_matrix(s * mu_h, s * mu_a), line) < p_over:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return s * mu_h, s * mu_a


# --- payload-koppling ---------------------------------------------------------------

def attach_model(store: Storage, matches: list[dict]) -> None:
    """Sätter m['model'] (amber-tier) på liga-matcher: sannolikheter, fair odds,
    μ, ankar-status, modell-edge vs SvS samt ClubElo. Träningsmatcher hoppas över."""
    from .oddset import norm_team
    fits: dict[str, Optional[dict]] = {}
    elo = oddset_data.get_elo(store)
    now_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in matches:
        lg = m.get("league")
        if lg not in oddset_data.FD_URLS:      # bara ligor med resultatdata
            continue
        if (m.get("start") or "9") <= now_iso:
            continue   # startad match — modell-edges mot live-odds är meningslösa
        if lg not in fits:
            fits[lg] = fit_league(oddset_data.merged_results(store, lg))
        fit = fits[lg]
        if not fit:
            continue
        hn, an = norm_team(m["home"]), norm_team(m["away"])
        mus = predict(fit, hn, an)
        eh, ea = elo.get(hn) or elo.get(_find_team({"teams": elo}, hn) or ""), \
            elo.get(an) or elo.get(_find_team({"teams": elo}, an) or "")
        if eh or ea:
            m["elo"] = {"h": eh, "a": ea}
        if not mus:
            continue
        mu_h, mu_a = mus
        anchored = False
        pin_ou = ((m.get("odds") or {}).get("pinnacle") or {}).get("ou")
        if pin_ou and pin_ou.get("O") and pin_ou.get("U"):
            inv = {"O": 1 / pin_ou["O"], "U": 1 / pin_ou["U"]}
            p_over = _power_probs(inv)["O"]
            mu_h, mu_a = _anchor_total(mu_h, mu_a, pin_ou["line"], p_over)
            anchored = True
        probs = matrix_1x2(dc_matrix(mu_h, mu_a))
        svs = ((m.get("odds") or {}).get("svenskaspel") or {}).get("1x2") or {}
        edges = {}
        for sign in ("1", "X", "2"):
            o = svs.get(sign)
            if o:
                edges[sign] = round(probs[sign] * o - 1.0, 4)
        m["model"] = {
            "p": {s: round(p, 4) for s, p in probs.items()},
            "fair": {s: round(1 / p, 2) if p > 0.001 else None
                     for s, p in probs.items()},
            "mu": [round(mu_h, 2), round(mu_a, 2)],
            "anchored": anchored, "edges": edges}
