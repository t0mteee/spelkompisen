"""PH4 del B — ablationer på PIT-datasetet (observed_pit, läsande).

Fråga: förbättrar strecknivå/streckrörelse/sharprörelse matchsannolikheterna
utöver den devigade marknaden? Varianter (per match, softmax över 1/X/2):

  b   rå marknad: devigad sharp (annars SvS) som den är — referens
  b*  temperatur: beta0·ln(p_marknad) — bara omkalibrering av marknaden
  c   b* + strecknivå
  d   c + streckrörelse (first→as-of i andels-pp, PIT-ren ur snapshots)
  e   b* + sharprörelse (move_sharp_pp ur PIT-datasetet)
  f   allt

Walk-forward i omgångsordning per produkt (expanderande fönster, minst
MIN_TRAIN omgångar innan första utvärderingen — ALDRIG slumpad split).
Mått: logloss per match; Δ mot (b) med 90 % blockbootstrap per omgång.
Horisont h3 (bäst täckt). Endast omgångar med komplett facit.

FÖRREGISTRERAD GATE (får inte ändras i efterhand): en variant får föreslås
för runtime först när den, per produkt, har ≥40 utvärderade omgångar EFTER
2026-07-24 (out-of-time) med hela 90 %-KI:t för Δlogloss < 0 mot (b) OCH
inte försämrar någon annan produkt signifikant. Denna körning är
hypotesgenererande — ingen runtime-ändring.

Körning: cd backend && .venv/bin/python -B scripts/ph4_ablationer.py
Utdata:  docs/ph4-ablationer-2026-07-24.json + sammanfattning på stdout.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import pool_dataset  # noqa: E402 — _series för PIT-ren streckrörelse
from app.storage import Storage  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
OUT = ROOT.parent / "docs" / "ph4-ablationer-2026-07-24.json"
PRODUCTS = ("topptipset", "europatipset", "topptipsetextra",
            "stryktipset", "topptipsetstryk")
HORIZON = "h3"
MIN_TRAIN = 15
SIGNS = ("1", "X", "2")
SEED = 20260724
VARIANTS = {
    "b": [],                       # rå marknad (inga parametrar)
    "b*": ["lnp"],
    "c": ["lnp", "streck"],
    "d": ["lnp", "streck", "streckmove"],
    "e": ["lnp", "sharpmove"],
    "f": ["lnp", "streck", "streckmove", "sharpmove"],
}


def softmax(zs: list[float]) -> list[float]:
    mx = max(zs)
    es = [math.exp(z - mx) for z in zs]
    tot = sum(es)
    return [e / tot for e in es]


def fit_logit(rows: list[dict], feats: list[str],
              iters: int = 400, lr: float = 0.5) -> list[float]:
    """Konditionell logit via gradientnedstigning (litet, konvext, rent
    Python). rows[i]["x"][sign] = featurevektor; ["y"] = facittecknets index."""
    beta = [1.0 if f == "lnp" else 0.0 for f in feats]
    n = len(rows)
    for it in range(iters):
        grad = [0.0] * len(beta)
        for row in rows:
            zs = [sum(b * x for b, x in zip(beta, row["x"][s])) for s in SIGNS]
            ps = softmax(zs)
            for j in range(len(beta)):
                for si, s in enumerate(SIGNS):
                    indicator = 1.0 if si == row["y"] else 0.0
                    grad[j] += (indicator - ps[si]) * row["x"][s][j]
        step = lr / n / (1 + it / 100)
        beta = [b + step * g for b, g in zip(beta, grad)]
    return beta


def logloss(rows: list[dict], feats: list[str],
            beta: list[float] | None) -> list[float]:
    """Logloss per match. beta=None ⇒ rå marknad (variant b)."""
    out = []
    for row in rows:
        if beta is None:
            ps = [row["p_market"][s] for s in SIGNS]
        else:
            zs = [sum(b * x for b, x in zip(beta, row["x"][s])) for s in SIGNS]
            ps = softmax(zs)
        out.append(-math.log(max(ps[row["y"]], 1e-12)))
    return out


def load_rows(store: Storage, product: str) -> list[tuple[str, list[dict]]]:
    """[(asof, matchrader)] i omgångsordning. Features PIT-rena vid as-of."""
    conn = store.conn
    draws = conn.execute(
        "SELECT f.draw_number, f.asof FROM pool_pit_draw_features f "
        "JOIN pool_draw_settlement s ON s.product=f.product "
        "AND s.draw_number=f.draw_number "
        "WHERE f.product=? AND f.horizon=? AND f.feature_version=? "
        "ORDER BY f.asof", (product, HORIZON, pool_dataset.FEATURE_VERSION)
    ).fetchall()
    out = []
    for draw_number, asof in draws:
        outcomes = dict(conn.execute(
            "SELECT event_number, outcome FROM pool_event_settlement "
            "WHERE product=? AND draw_number=?", (product, draw_number)))
        feats = conn.execute(
            "SELECT event_number, p_svs_1, p_svs_x, p_svs_2, p_sharp_1, "
            "p_sharp_x, p_sharp_2, streck_1, streck_x, streck_2, "
            "move_sharp_pp_1, move_sharp_pp_x, move_sharp_pp_2 "
            "FROM pool_pit_match_features WHERE product=? AND draw_number=? "
            "AND horizon=? AND feature_version=?",
            (product, draw_number, HORIZON, pool_dataset.FEATURE_VERSION)
        ).fetchall()
        # streckrörelse (first→as-of) PIT-rent ur snapshots-serien
        svs_series = pool_dataset._series(  # noqa: SLF001 — samma paket
            store, "snapshots", product, draw_number, asof)
        rows = []
        for (event, p1, px, p2, q1, qx, q2, s1, sx, s2,
             m1, mx, m2) in feats:
            outcome = outcomes.get(event)
            if outcome not in SIGNS:
                continue
            market = {"1": q1, "X": qx, "2": q2} if None not in (q1, qx, q2) \
                else {"1": p1, "X": px, "2": p2}
            if None in market.values():
                continue
            streck = {"1": s1, "X": sx, "2": s2}
            if None in streck.values():
                continue
            tot = sum(streck.values()) or 1
            share = {s: streck[s] / tot for s in SIGNS}
            smove = {}
            ser = svs_series.get(event, {})
            for s in SIGNS:
                seq = [p for p in (ser.get(s) or []) if p[2] is not None]
                smove[s] = (seq[-1][2] - seq[0][2]) / 100.0 if len(seq) >= 2 else 0.0
            sharpmove = {"1": m1, "X": mx, "2": m2}
            x = {}
            for s in SIGNS:
                x[s] = {
                    "lnp": math.log(max(market[s], 1e-9)),
                    "streck": share[s],
                    "streckmove": smove[s],
                    "sharpmove": (sharpmove[s] or 0.0) / 100.0,
                }
            rows.append({"event": event, "y": SIGNS.index(outcome),
                         "p_market": market, "raw_x": x})
        if rows:
            out.append((asof, rows))
    return out


def main() -> None:
    rng = random.Random(SEED)
    store = Storage(DB)
    report: dict = {"horizon": HORIZON, "min_train": MIN_TRAIN, "seed": SEED,
                    "gate": "≥40 out-of-time-omgångar efter 2026-07-24 med "
                            "hela KI90(Δlogloss)<0 mot b, per produkt",
                    "products": {}}
    try:
        for product in PRODUCTS:
            data = load_rows(store, product)
            if len(data) <= MIN_TRAIN:
                report["products"][product] = {
                    "n_draws": len(data),
                    "note": f"för få omgångar (≤{MIN_TRAIN}) för walk-forward"}
                print(f"{product}: {len(data)} omgångar — hoppar (för få)")
                continue
            results: dict[str, list[list[float]]] = {v: [] for v in VARIANTS}
            for k in range(MIN_TRAIN, len(data)):
                train = [r for _, rows in data[:k] for r in rows]
                test = data[k][1]
                for variant, feats in VARIANTS.items():
                    for row in train + test:
                        row["x"] = {s: [row["raw_x"][s][f] for f in feats]
                                    for s in SIGNS}
                    beta = fit_logit(train, feats) if feats else None
                    results[variant].append(logloss(test, feats, beta))
            n_eval = len(results["b"])
            n_matches = sum(len(r) for r in results["b"])
            summary = {}
            base_mean = sum(sum(r) for r in results["b"]) / n_matches
            for variant in VARIANTS:
                mean = sum(sum(r) for r in results[variant]) / n_matches
                deltas = [(sum(rv) - sum(rb)) / len(rb)
                          for rv, rb in zip(results[variant], results["b"])]
                boots = []
                for _ in range(1000):
                    sample = [deltas[rng.randrange(len(deltas))]
                              for _ in range(len(deltas))]
                    boots.append(sum(sample) / len(sample))
                boots.sort()
                summary[variant] = {
                    "logloss": round(mean, 4),
                    "delta_vs_b": round(mean - base_mean, 4),
                    "delta_ci90": [round(boots[int(len(boots) * 0.05)], 4),
                                   round(boots[int(len(boots) * 0.95)], 4)],
                }
            report["products"][product] = {
                "n_draws": len(data), "n_eval_draws": n_eval,
                "n_matches": n_matches, "variants": summary}
            print(f"\n=== {product}: {n_eval} utvärderade omgångar "
                  f"({n_matches} matcher) ===")
            for variant, s in summary.items():
                print(f"  {variant:3s} logloss {s['logloss']} "
                      f"Δb {s['delta_vs_b']:+.4f} "
                      f"KI90 [{s['delta_ci90'][0]:+.4f}..{s['delta_ci90'][1]:+.4f}]")
    finally:
        store.close()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nSkrev {OUT}")


if __name__ == "__main__":
    main()
