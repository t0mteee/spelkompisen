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
import hashlib
import io
import math
import random
from typing import Optional

import httpx

from .analysis import _power_probs
from . import oddset_model
from .oddset import norm_team
from .oddset_data import FD_URLS

EVAL_FROM = "2024-07-01"
SIGNS = ("1", "X", "2")
Q_EDGE_MIN = 0.02
Q_THRESHOLDS = (0.0075, 0.01, 0.015, 0.02, 0.03)
Q_POLICY = 0.015
ROI_BOOTSTRAP_ITERS = 2000


def _odds_from_sets(row: dict, column_sets: tuple[tuple[str, tuple[str, ...]], ...]
                    ) -> tuple[Optional[list[float]], Optional[str]]:
    """Första kompletta oddsuppsättningen, normalt closing före opening."""
    for label, columns in column_sets:
        try:
            odds = [float(row[column]) for column in columns]
        except (ValueError, KeyError, TypeError):
            continue
        if all(odd > 1.0 for odd in odds):
            return odds, label
    return None, None


def _fetch_texts(league: str) -> list[tuple[str, Optional[str]]]:
    """(CSV-text, förväntad divisionskod) för en ligas football-data-filer.

    Landsfilerna (`FD_URLS`) är en fil per liga; höst/vår-ligorna publiceras
    som en fil per säsong (`FD_SEASON_CODES`). Backtestet kunde bara läsa de
    förra, vilket i praktiken gjorde Europaligorna okalibrerbara — inte för att
    stängningsodds saknades (PSCH/MaxCH/AvgCH finns i båda formaten) utan för
    att hämtningen inte kände formatet.
    """
    from .oddset_data import FD_SEASON_CODES, _fd_season_urls
    if league in FD_URLS:
        r = httpx.get(FD_URLS[league], timeout=30, follow_redirects=True)
        r.raise_for_status()
        return [(r.text, None)]
    code = FD_SEASON_CODES.get(league)
    if not code:
        raise KeyError(league)
    out = []
    for url in _fd_season_urls(code):
        r = httpx.get(url, timeout=30, follow_redirects=True)
        if r.status_code == 404:
            continue          # säsongsfil ej publicerad ännu — väntat
        r.raise_for_status()
        out.append((r.text, code))
    return out


def fetch_rows(league: str, min_season: int = 2023) -> list[dict]:
    rows = []
    for text, div in _fetch_texts(league):
        rows.extend(_rows_from_text(text, min_season, div))
    rows.sort(key=lambda x: x["date"])
    return rows


def _rows_from_text(text: str, min_season: int,
                    div: Optional[str] = None) -> list[dict]:
    rows = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        # Samma divisionsvakt som insamlingen: football-data serverade skotsk
        # Championship på La Ligas säsongs-URL 2026-08-07.
        if div and (row.get("Div") or "").strip() not in ("", div):
            continue
        try:
            season = row.get("Season")
            date = dt.datetime.strptime(
                row["Date"], "%d/%m/%Y" if len(row["Date"]) == 10
                else "%d/%m/%y")
            if season is not None:
                if int((season or "0")[:4]) < min_season:
                    continue
            elif date.year < min_season:
                # Säsongsfilerna saknar Season-kolumn; datumet duger, och
                # EVAL_FROM styr ändå vad som utvärderas.
                continue
            d = date.strftime("%Y-%m-%d")
            home = row.get("Home") or row.get("HomeTeam")
            away = row.get("Away") or row.get("AwayTeam")
            hg = row.get("HG") if row.get("HG") not in (None, "") else row.get("FTHG")
            ag = row.get("AG") if row.get("AG") not in (None, "") else row.get("FTAG")
            rec = {"date": d, "home": norm_team(home), "away": norm_team(away),
                   "hg": int(hg), "ag": int(ag)}
        except (ValueError, KeyError, TypeError):
            continue
        sources = {
            "ps": (("close", ("PSCH", "PSCD", "PSCA")),
                   ("open", ("PSH", "PSD", "PSA"))),
            "mx": (("close", ("MaxCH", "MaxCD", "MaxCA")),
                   ("open", ("MaxH", "MaxD", "MaxA"))),
            "av": (("close", ("AvgCH", "AvgCD", "AvgCA")),
                   ("open", ("AvgH", "AvgD", "AvgA"))),
            "b365": (("close", ("B365CH", "B365CD", "B365CA")),
                     ("open", ("B365H", "B365D", "B365A"))),
        }
        for src, column_sets in sources.items():
            # Behåll båda tidpunkterna separat för V2-B:s uttryckligt märkta
            # utvecklingsproxy. Det befintliga backtestet fortsätter välja
            # closing först och ändrar därmed inte sitt facit.
            rec[f"{src}_close"], _ = _odds_from_sets(row, (column_sets[0],))
            rec[f"{src}_open"], _ = _odds_from_sets(row, (column_sets[1],))
            rec[src], rec[f"{src}_timing"] = _odds_from_sets(row, column_sets)
        rows.append(rec)
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
            preds.append({"match_id": f"{r['date']}|{r['home']}|{r['away']}",
                          "date": r["date"], "home": r["home"], "away": r["away"],
                          "mu_h": mus[0], "mu_a": mus[1], "mkt": mkt, "res": res,
                          "ps": dict(zip(SIGNS, r["ps"])),
                          "ps_timing": r.get("ps_timing"),
                          "mx": dict(zip(SIGNS, r["mx"])) if r["mx"] else None,
                          "mx_timing": r.get("mx_timing"),
                          "b365": (dict(zip(SIGNS, r["b365"]))
                                   if r.get("b365") else None),
                          "b365_timing": r.get("b365_timing"),
                          "hg": r["hg"], "ag": r["ag"]})
    return preds


def _model_probs(p: dict, rho: float,
                 temperature: float = 1.0) -> dict[str, float]:
    matrix = oddset_model.dc_matrix(p["mu_h"], p["mu_a"], rho)
    if abs(temperature - 1.0) > 1e-9:
        matrix = oddset_model.temper(matrix, temperature)
    return oddset_model.matrix_1x2(matrix)


def _logloss(prob_rows: list[tuple[dict, str]]) -> float:
    return -sum(math.log(max(pr[r], 1e-9)) for pr, r in prob_rows) / len(prob_rows)


def _quality(edge: float, odds: float) -> float:
    """Kelly-andelen q: samma edge kräver mer på höga odds."""
    return edge / max(odds - 1.0, 0.01)


def _roi_ci(blocks: dict[str, tuple[int, float]], key: str,
            iters: int = ROI_BOOTSTRAP_ITERS) -> Optional[list[float]]:
    """90 %-KI för ROI med matchen som block; deterministiskt seedad."""
    values = list(blocks.values())
    if len(values) < 5 or iters <= 0:
        return None
    seed = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    draws = []
    for _ in range(iters):
        sample = [rng.choice(values) for _ in values]
        stake = sum(item[0] for item in sample)
        if stake:
            draws.append(sum(item[1] for item in sample) / stake)
    draws.sort()
    return [round(draws[int(len(draws) * 0.05)], 4),
            round(draws[min(len(draws) - 1, int(len(draws) * 0.95))], 4)]


def _bet_stats(bets: list[dict], key: str) -> dict:
    blocks: dict[str, list[float]] = {}
    for bet in bets:
        block = blocks.setdefault(bet["match_id"], [0, 0.0])
        block[0] += 1
        block[1] += bet["pnl"]
    n = len(bets)
    pnl = sum(bet["pnl"] for bet in bets)
    return {
        "n": n, "n_matches": len(blocks),
        "hit": round(sum(bet["won"] for bet in bets) / n, 4) if n else None,
        "roi": round(pnl / n, 4) if n else None,
        "roi_ci": _roi_ci(
            {match_id: (int(values[0]), values[1])
             for match_id, values in blocks.items()}, key) if n else None,
        "avg_edge": round(sum(bet["edge"] for bet in bets) / n, 4) if n else None,
        "avg_q": round(sum(bet["q"] for bet in bets) / n, 4) if n else None,
        "avg_odds": round(sum(bet["odds"] for bet in bets) / n, 2) if n else None,
    }


def quality_report(preds: list[dict], price_key: str = "b365",
                   thresholds: tuple[float, ...] = Q_THRESHOLDS) -> dict:
    """Backtest v4: förregistrerad q-regel, känslighetsgrid och krysskalibrering.

    Pinnacle-close devigas till fair; B365 är den mjuka boken och vinst/förlust
    räknas till dess odds. Edge måste alltid vara minst 2 % precis som liveloggen.
    Tröskelgridden är känslighetsanalys — runtimepolicyn 1,5 % väljs inte om på
    samma data som den utvärderas på.
    """
    bets = []
    draw_rows = []
    timing = {"close": 0, "open": 0}
    for index, pred in enumerate(preds):
        # q-facitet definieras mot sharp closing. Modellen får jämföras mot en
        # äldre prisproxy, men en Pinnacle-opening får aldrig bli facit av misstag.
        if pred.get("ps_timing", "close") != "close":
            continue
        soft = pred.get(price_key)
        if not soft or not all(soft.get(sign) for sign in SIGNS):
            continue
        timing_key = pred.get(f"{price_key}_timing") or "open"
        timing[timing_key] = timing.get(timing_key, 0) + 1
        soft_fair = _power_probs({sign: 1 / soft[sign] for sign in SIGNS})
        draw_rows.append({"actual": int(pred["res"] == "X"),
                          "sharp": pred["mkt"]["X"], "soft": soft_fair["X"]})
        match_id = pred.get("match_id") or str(index)
        for sign in SIGNS:
            edge = pred["mkt"][sign] * soft[sign] - 1.0
            q = _quality(edge, soft[sign])
            won = sign == pred["res"]
            bets.append({
                "match_id": match_id, "sign": sign, "edge": edge, "q": q,
                "odds": soft[sign], "won": won,
                "pnl": soft[sign] - 1.0 if won else -1.0,
            })

    eligible = [bet for bet in bets if bet["edge"] >= Q_EDGE_MIN]
    grid = {}
    for threshold in thresholds:
        selected = [bet for bet in eligible if bet["q"] >= threshold]
        grid[f"{threshold:.4f}"] = _bet_stats(
            selected, f"q:{threshold:.4f}")
    policy = [bet for bet in eligible if bet["q"] >= Q_POLICY]
    by_sign = {sign: _bet_stats(
        [bet for bet in policy if bet["sign"] == sign], f"q-policy:{sign}")
        for sign in SIGNS}
    n_draw = len(draw_rows)
    draw = {
        "n": n_draw,
        "actual": (round(sum(row["actual"] for row in draw_rows) / n_draw, 4)
                   if n_draw else None),
        "sharp": (round(sum(row["sharp"] for row in draw_rows) / n_draw, 4)
                  if n_draw else None),
        "soft": (round(sum(row["soft"] for row in draw_rows) / n_draw, 4)
                 if n_draw else None),
    }
    return {"price_key": price_key, "n_predictions": len(preds),
            "n_priced": n_draw,
            "coverage": round(n_draw / len(preds), 4) if preds else 0.0,
            "edge_min": Q_EDGE_MIN, "policy_q": Q_POLICY,
            "soft_timing": timing, "grid": grid,
            "policy_by_sign": by_sign, "draw": draw}


def report(preds: list[dict], rho: float = oddset_model.DC_RHO_CLUB,
           temperature: float = 1.0) -> dict:
    n = len(preds)
    model = [(_model_probs(p, rho, temperature), p["res"]) for p in preds]
    market = [(p["mkt"], p["res"]) for p in preds]
    out = {"n": n, "temperature": temperature,
           "logloss_model": round(_logloss(model), 4),
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
        rows = [(_model_probs(p, rh, temperature), p["res"]) for p in preds]
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
    out["quality_v4"] = {
        "b365": quality_report(preds, "b365"),
        # Max closing är ett optimistiskt tak: det liknar livevalet av bästa bok
        # men omfattar fler böcker än appen och får aldrig ensam ändra policyn.
        "max": quality_report(preds, "mx"),
    }
    return out


def fit_temperature(preds: list[dict],
                    rho: float = oddset_model.DC_RHO_CLUB) -> tuple[float, float, float]:
    """Grid-sök temperatur T som minimerar 1X2-logloss på walk-forward-
    prediktionerna. Returnerar (T, logloss_vid_T, logloss_vid_1.0)."""
    base_ll = None
    best = (1.0, 1e9)
    for ti in range(70, 185, 5):
        t = ti / 100
        rows = []
        for p in preds:
            mx = oddset_model.temper(
                oddset_model.dc_matrix(p["mu_h"], p["mu_a"], rho), t)
            rows.append((oddset_model.matrix_1x2(mx), p["res"]))
        ll = _logloss(rows)
        if abs(t - 1.0) < 1e-6:
            base_ll = ll
        if ll < best[1]:
            best = (t, ll)
    return best[0], best[1], base_ll


def print_report(league: str, rep: dict) -> None:
    print(f"\n=== {league} (n={rep['n']}) ===")
    print(f"temperatur T={rep['temperature']:.2f} (samma som live för ligan)")
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
    print("backtest v4 — sharp-fair, edge ≥2 % och q-grid:")
    for source, source_label in (("b365", "B365 (spelbar proxy)"),
                                 ("max", "Max closing (optimistiskt tak)")):
        qrep = rep["quality_v4"][source]
        timing = qrep["soft_timing"]
        print(f"  {source_label}: {qrep['n_priced']}/{qrep['n_predictions']} matcher "
              f"({qrep['coverage']:.1%}) · {timing.get('close', 0)} closing · "
              f"{timing.get('open', 0)} opening")
        for threshold, stats in qrep["grid"].items():
            if not stats["n"]:
                continue
            ci = (f" · 90% KI [{stats['roi_ci'][0]*100:+.1f}.."
                  f"{stats['roi_ci'][1]*100:+.1f}]" if stats["roi_ci"] else "")
            marker = (" ← policy" if abs(float(threshold) - qrep["policy_q"]) < 1e-9
                      else "")
            print(f"    q≥{float(threshold)*100:4.2f}%: n={stats['n']:4d} · "
                  f"ROI {stats['roi']*100:+.1f}%{ci} · odds "
                  f"{stats['avg_odds']:.2f}{marker}")
        draw = qrep["draw"]
        if draw["n"]:
            print(f"    X-frekvens: utfall {draw['actual']*100:.1f}% · "
                  f"Pinnacle {draw['sharp']*100:.1f}% · proxy {draw['soft']*100:.1f}% "
                  f"(n={draw['n']})")
            xstats = qrep["policy_by_sign"]["X"]
            if xstats["n"]:
                print(f"    q-policy på X: n={xstats['n']} · ROI "
                      f"{xstats['roi']*100:+.1f}%")
