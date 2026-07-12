"""Etapp 5: walk-forward-backtest av målmodellen mot Pinnacles STÄNGNINGSODDS
(football-data.co.uk, PSC-kolumnerna) från 2024-07 och framåt.

Fyra frågor besvaras:
1. Kalibrering — logloss/Brier för modellen vs devigad stängningsmarknad,
   plus kalibreringstabell (predikterad sannolikhet vs verklig träff).
2. Informationsvärde — optimal blandvikt w i w·modell + (1−w)·marknad
   (w > 0 betyder att modellen tillför något marknaden inte redan vet).
3. Spelbarhet — ROI om man satsat 1 enhet på varje modell-edge ≥ tröskel,
   till stängningspris resp. bästa pris (Max-kolumnerna) — beslutsregeln.
4. rho — grid-sökning på klubb-rho (Dixon-Coles lågmålskorrektion).

Ärlighetsregel: modellen fittas ENDAST på matcher före respektive matchdag
(ingen läcka). Backtestens säsonger saknar xG (Sofascore täcker bara nuvarande)
— den validerar alltså mål-versionen; xG-viktningen är en bonus ovanpå.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
from typing import Optional

import httpx

from .analysis import _power_probs
from . import oddset_model
from .oddset import norm_team
from .oddset_data import FD_URLS

EVAL_FROM = "2024-07-01"
SIGNS = ("1", "X", "2")


def fetch_rows(league: str, min_season: int = 2023) -> list[dict]:
    r = httpx.get(FD_URLS[league], timeout=30, follow_redirects=True)
    r.raise_for_status()
    rows = []
    for row in csv.DictReader(io.StringIO(r.text.lstrip("﻿"))):
        try:
            if int((row.get("Season") or "0")[:4]) < min_season:
                continue
            d = dt.datetime.strptime(row["Date"], "%d/%m/%Y").strftime("%Y-%m-%d")
            rec = {"date": d, "home": norm_team(row["Home"]),
                   "away": norm_team(row["Away"]),
                   "hg": int(row["HG"]), "ag": int(row["AG"])}
        except (ValueError, KeyError):
            continue
        for src, cols in (("ps", ("PSCH", "PSCD", "PSCA")),
                          ("mx", ("MaxCH", "MaxCD", "MaxCA")),
                          ("av", ("AvgCH", "AvgCD", "AvgCA"))):
            try:
                rec[src] = [float(row[c]) for c in cols]
            except (ValueError, KeyError, TypeError):
                rec[src] = None
        rows.append(rec)
    rows.sort(key=lambda x: x["date"])
    return rows


def run_league(league: str, eval_from: str = EVAL_FROM,
               fit_iter: int = 40, use_store_xg: bool = False,
               pool_extra: tuple = ()) -> list[dict]:
    """Prediktioner (mu_h, mu_a, marknadsprobs, stängningsodds, facit) per match.
    use_store_xg: lägg på Sofascore-xG från databasen (efter xgbackfill) så
    fitten blir xG-viktad — mäter om xG lyfter modellen (backtest v2).
    pool_extra: extra ligor (t.ex. superettan) vars resultat poolas in i fitten
    med egen liga-nyckel — mäter cross-liga-fitten (backtest v3)."""
    rows = fetch_rows(league)
    if use_store_xg:
        from .storage import Storage
        from .oddset_data import merged_results
        store = Storage()
        try:
            xmap = {(r["date"], r["home"], r["away"]): (r.get("xg_h"), r.get("xg_a"))
                    for r in merged_results(store, league) if r.get("xg_h") is not None}
        finally:
            store.close()
        n_hit = 0
        for r in rows:
            xg = xmap.get((r["date"], r["home"], r["away"]))
            if xg:
                r["xg_h"], r["xg_a"] = xg
                n_hit += 1
        print(f"  ({league}: xG kopplad till {n_hit}/{len(rows)} matcher)")
    hist_src = rows
    if pool_extra:
        from .storage import Storage
        from .oddset_data import merged_results
        store = Storage()
        try:
            extra = []
            for plg in pool_extra:
                extra.extend(merged_results(store, plg))
        finally:
            store.close()
        hist_src = sorted(rows + extra, key=lambda r: r["date"])
        print(f"  ({league}: poolar in {len(extra)} matcher från {'+'.join(pool_extra)})")

    dates = sorted({r["date"] for r in rows if r["date"] >= eval_from})
    preds, hist_ptr, hist = [], 0, []
    for d in dates:
        while hist_ptr < len(hist_src) and hist_src[hist_ptr]["date"] < d:
            hist.append(hist_src[hist_ptr])
            hist_ptr += 1
        fit = oddset_model.fit_league(hist, now=dt.date.fromisoformat(d),
                                      iters=fit_iter)
        if not fit:
            continue
        for r in rows:
            if r["date"] != d or not r["ps"]:
                continue
            mus = oddset_model.predict(fit, r["home"], r["away"], league="")
            if not mus:
                continue
            mkt = _power_probs({s: 1 / o for s, o in zip(SIGNS, r["ps"])})
            res = "1" if r["hg"] > r["ag"] else "2" if r["hg"] < r["ag"] else "X"
            preds.append({"mu_h": mus[0], "mu_a": mus[1], "mkt": mkt, "res": res,
                          "ps": dict(zip(SIGNS, r["ps"])),
                          "mx": dict(zip(SIGNS, r["mx"])) if r["mx"] else None,
                          "hg": r["hg"], "ag": r["ag"]})
    return preds


def _model_probs(p: dict, rho: float) -> dict[str, float]:
    return oddset_model.matrix_1x2(
        oddset_model.dc_matrix(p["mu_h"], p["mu_a"], rho))


def _logloss(prob_rows: list[tuple[dict, str]]) -> float:
    return -sum(math.log(max(pr[r], 1e-9)) for pr, r in prob_rows) / len(prob_rows)


def report(preds: list[dict], rho: float = oddset_model.DC_RHO_CLUB) -> dict:
    n = len(preds)
    model = [(_model_probs(p, rho), p["res"]) for p in preds]
    market = [(p["mkt"], p["res"]) for p in preds]
    out = {"n": n, "logloss_model": round(_logloss(model), 4),
           "logloss_market": round(_logloss(market), 4)}
    out["brier_model"] = round(sum(
        sum((pr[s] - (1 if s == r else 0)) ** 2 for s in SIGNS)
        for pr, r in model) / n, 4)
    out["brier_market"] = round(sum(
        sum((pr[s] - (1 if s == r else 0)) ** 2 for s in SIGNS)
        for pr, r in market) / n, 4)

    # rho-grid (bästa 1X2-logloss)
    grid = {}
    for rh in [x / 100 for x in range(-25, 6, 3)]:
        rows = [(_model_probs(p, rh), p["res"]) for p in preds]
        grid[rh] = round(_logloss(rows), 4)
    out["rho_grid"] = grid
    out["rho_best"] = min(grid, key=grid.get)

    # blandvikt: w·modell + (1−w)·marknad
    blend = {}
    for wi in range(0, 11):
        w = wi / 10
        rows = [({s: w * mp[s] + (1 - w) * p["mkt"][s] for s in SIGNS}, p["res"])
                for (mp, _), p in zip(model, preds)]
        blend[w] = round(_logloss(rows), 4)
    out["blend"] = blend
    out["w_best"] = min(blend, key=blend.get)

    # kalibrering (deciler över alla tecken-sannolikheter)
    buckets = [[0, 0.0, 0] for _ in range(10)]
    for (pr, r) in model:
        for s in SIGNS:
            b = min(9, int(pr[s] * 10))
            buckets[b][0] += 1
            buckets[b][1] += pr[s]
            buckets[b][2] += 1 if s == r else 0
    out["calibration"] = [
        {"bucket": f"{b * 10}-{b * 10 + 10}%", "n": c,
         "pred": round(psum / c, 3), "hit": round(hits / c, 3)}
        for b, (c, psum, hits) in enumerate(buckets) if c >= 30]

    # beslutsregel-ROI: satsa 1 enhet på varje modell-edge ≥ tröskel
    out["roi"] = {}
    for th in (0.02, 0.05, 0.08, 0.12):
        for price_key, label in (("ps", "pinnacle_close"), ("mx", "max_close")):
            stake = ret = 0
            for (pr, r), p in zip(model, preds):
                prices = p.get(price_key)
                if not prices:
                    continue
                for s in SIGNS:
                    if pr[s] * p["ps"][s] - 1 >= th:   # edge alltid mot Pinnacle-pris
                        stake += 1
                        if s == r:
                            ret += prices[s]
            if stake:
                out["roi"][f"{label}@{th:.0%}"] = {
                    "n": stake, "roi": round((ret - stake) / stake, 4)}
    return out


def print_report(league: str, rep: dict) -> None:
    print(f"\n=== {league} (n={rep['n']}) ===")
    print(f"logloss  modell {rep['logloss_model']}  vs marknad {rep['logloss_market']}"
          f"  (lägre = bättre; marknaden är riktmärket)")
    print(f"brier    modell {rep['brier_model']}  vs marknad {rep['brier_market']}")
    print(f"rho-grid bäst {rep['rho_best']}: {rep['rho_grid']}")
    print(f"blandvikt w·modell+(1-w)·marknad — bäst w={rep['w_best']}: {rep['blend']}")
    print("kalibrering (pred vs verklig träff):")
    for b in rep["calibration"]:
        print(f"  {b['bucket']:>8} n={b['n']:5d} pred {b['pred']:.3f} verkligt {b['hit']:.3f}")
    print("beslutsregel-ROI (satsa på modell-edge mot Pinnacle-stängning):")
    for k, v in rep["roi"].items():
        print(f"  {k:>22}: n={v['n']:4d} ROI {v['roi']*100:+.1f}%")
