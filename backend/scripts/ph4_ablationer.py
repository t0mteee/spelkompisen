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

FÖRREGISTRERAD GATE läses ur docs/pool-ph4-forward-manifest-v2.json. Utvecklings-
omgångar får användas som expanderande träningshistorik men får ALDRIG räknas
i forward-volym, effekt eller KI. Kandidat-, feature- och timingversion är
frysta i manifestet.

Körning: cd backend && .venv/bin/python -B scripts/ph4_ablationer.py
Utdata:  docs/ph4-forward-status.json + sammanfattning på stdout. Den ursprungliga
hypotesgenererande rapporten ph4-ablationer-2026-07-24.json skrivs aldrig över.
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
MANIFEST_PATH = ROOT.parent / "docs" / "pool-ph4-forward-manifest-v2.json"
OUT = ROOT.parent / "docs" / "ph4-forward-status.json"
PRODUCTS = ("topptipset", "europatipset", "topptipsetextra",
            "stryktipset", "topptipsetstryk")
SIGNS = ("1", "X", "2")


def load_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest["feature_version"] != pool_dataset.FEATURE_VERSION:
        raise RuntimeError(
            f"manifest feature_version={manifest['feature_version']} men "
            f"runtime={pool_dataset.FEATURE_VERSION}")
    if manifest["feature_start_at"] != pool_dataset.FEATURE_START_AT:
        raise RuntimeError(
            f"manifest feature_start_at={manifest['feature_start_at']} men "
            f"runtime={pool_dataset.FEATURE_START_AT}")
    if manifest["eligibility"]["timing_policy"] != pool_dataset.TIMING_POLICY:
        raise RuntimeError(
            "manifestets timing_policy matchar inte runtime: "
            f"{manifest['eligibility']['timing_policy']} != "
            f"{pool_dataset.TIMING_POLICY}")
    return manifest


def softmax(zs: list[float]) -> list[float]:
    mx = max(zs)
    es = [math.exp(z - mx) for z in zs]
    tot = sum(es)
    return [e / tot for e in es]


def fit_logit(rows: list[dict], feats: list[str], *,
              iters: int = 800, lr: float = 0.25,
              ridge_l2: float = 1e-4,
              tolerance: float = 1e-8) -> tuple[list[float], bool, int]:
    """Konditionell logit via gradientnedstigning (litet, konvext, rent
    Python). rows[i]["x"][sign] = featurevektor; ["y"] = facittecknets index."""
    beta = [0.0 for _ in feats]
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
        for j in range(len(beta)):
            grad[j] -= ridge_l2 * beta[j] * n
        scaled_grad = [g / n for g in grad]
        if max((abs(g) for g in scaled_grad), default=0.0) < tolerance:
            return beta, True, it + 1
        step = lr / (1 + it / 200)
        beta = [b + step * g for b, g in zip(beta, scaled_grad)]
    return beta, False, iters


def attach_training_scaled_features(train: list[dict], test: list[dict],
                                    feats: list[str]) -> None:
    """Standardisera med ENBART träningsfoldens värden; aldrig testläckage."""
    means, scales = [], []
    for feat in feats:
        values = [row["raw_x"][s][feat] for row in train for s in SIGNS]
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / max(1, len(values))
        means.append(mean)
        scales.append(math.sqrt(var) or 1.0)
    for row in train + test:
        row["x"] = {
            s: [(row["raw_x"][s][feat] - means[j]) / scales[j]
                for j, feat in enumerate(feats)]
            for s in SIGNS
        }


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


def load_rows(store: Storage, product: str, *,
              horizon: str, feature_version: str) -> list[tuple[str, list[dict]]]:
    """[(asof, matchrader)] i omgångsordning. Features PIT-rena vid as-of."""
    conn = store.conn
    draws = conn.execute(
        "SELECT f.draw_number, f.asof FROM pool_pit_draw_features f "
        "JOIN pool_draw_settlement s ON s.product=f.product "
        "AND s.draw_number=f.draw_number "
        "WHERE f.product=? AND f.horizon=? AND f.feature_version=? "
        "ORDER BY f.asof", (product, horizon, feature_version)
    ).fetchall()
    out = []
    for draw_number, asof in draws:
        outcomes = dict(conn.execute(
            "SELECT event_number, outcome FROM pool_event_settlement "
            "WHERE product=? AND draw_number=?", (product, draw_number)))
        feats = conn.execute(
            "SELECT event_number, p_svs_1, p_svs_x, p_svs_2, p_sharp_1, "
            "p_sharp_x, p_sharp_2, streck_1, streck_x, streck_2, "
            "move_sharp_pp_1, move_sharp_pp_x, move_sharp_pp_2, "
            "svs_eligible, sharp_eligible "
            "FROM pool_pit_match_features WHERE product=? AND draw_number=? "
            "AND horizon=? AND feature_version=?",
            (product, draw_number, horizon, feature_version)
        ).fetchall()
        # streckrörelse (first→as-of) PIT-rent ur snapshots-serien
        svs_series = pool_dataset._series(  # noqa: SLF001 — samma paket
            store, "snapshots", product, draw_number, asof)
        rows = []
        for (event, p1, px, p2, q1, qx, q2, s1, sx, s2,
             m1, mx, m2, svs_eligible, sharp_eligible) in feats:
            outcome = outcomes.get(event)
            if outcome not in SIGNS:
                continue
            market = ({"1": q1, "X": qx, "2": q2}
                      if sharp_eligible and None not in (q1, qx, q2)
                      else {"1": p1, "X": px, "2": p2})
            if None in market.values():
                continue
            streck = {"1": s1, "X": sx, "2": s2}
            if not svs_eligible or None in streck.values():
                continue
            tot = sum(streck.values()) or 1
            share = {s: streck[s] / tot for s in SIGNS}
            smove = {}
            ser = svs_series.get(event, {})
            for s in SIGNS:
                seq = [p for p in (ser.get(s) or []) if p[2] is not None]
                smove[s] = ((seq[-1][2] - seq[0][2]) / 100.0
                            if seq else None)
            sharpmove = {"1": m1, "X": mx, "2": m2}
            x = {}
            for s in SIGNS:
                x[s] = {
                    "lnp": math.log(max(market[s], 1e-9)),
                    "streck": share[s],
                    "streckmove": smove[s],
                    "sharpmove": (sharpmove[s] / 100.0
                                  if sharp_eligible and
                                  sharpmove[s] is not None else None),
                }
            rows.append({"event": event, "y": SIGNS.index(outcome),
                         "p_market": market, "raw_x": x})
        if rows:
            out.append((asof, rows))
    return out


def _eligible(rows: list[dict], feats: list[str]) -> list[dict]:
    return [row for row in rows if all(
        row["raw_x"][s].get(feat) is not None
        for feat in feats for s in SIGNS)]


def evaluation_indexes(data: list[tuple[str, list[dict]]], min_train: int,
                       evaluation_start: str) -> tuple[list[int], list[int]]:
    """Returnera development/forward-index; fryspunkten styr ENDAST scoring."""
    dev, forward = [], []
    for k in range(min_train, len(data)):
        (forward if data[k][0] >= evaluation_start else dev).append(k)
    return dev, forward


def evaluate_phase(data: list[tuple[str, list[dict]]], indexes: list[int],
                   variants: dict[str, list[str]], training: dict) -> dict:
    results: dict[str, list[dict]] = {v: [] for v in variants}
    for k in indexes:
        raw_train = [r for _, rows in data[:k] for r in rows]
        raw_test = data[k][1]
        for variant, feats in variants.items():
            train = _eligible(raw_train, feats)
            test = _eligible(raw_test, feats)
            if not test or (feats and not train):
                continue
            if feats:
                attach_training_scaled_features(train, test, feats)
                beta, converged, iterations = fit_logit(
                    train, feats,
                    iters=int(training["max_iterations"]),
                    ridge_l2=float(training["ridge_l2"]),
                    tolerance=float(training["gradient_tolerance"]))
            else:
                beta, converged, iterations = None, True, 0
            results[variant].append({
                "candidate": logloss(test, feats, beta),
                "baseline": logloss(test, [], None),
                "converged": converged,
                "iterations": iterations,
            })
    return results


def summarize(records: list[dict], *, bootstrap_n: int,
              rng: random.Random) -> dict:
    if not records:
        return {"n_eval_draws": 0, "n_matches": 0, "status": "no_forward_data"}
    n_matches = sum(len(r["candidate"]) for r in records)
    candidate = sum(sum(r["candidate"]) for r in records) / n_matches
    baseline = sum(sum(r["baseline"]) for r in records) / n_matches
    deltas = [
        (sum(r["candidate"]) - sum(r["baseline"])) / len(r["baseline"])
        for r in records
    ]
    boots = []
    for _ in range(bootstrap_n):
        sample = [deltas[rng.randrange(len(deltas))]
                  for _ in range(len(deltas))]
        boots.append(sum(sample) / len(sample))
    boots.sort()
    return {
        "n_eval_draws": len(records),
        "n_matches": n_matches,
        "logloss": round(candidate, 5),
        "baseline_logloss": round(baseline, 5),
        "delta_vs_b": round(candidate - baseline, 5),
        "delta_ci90": [
            round(boots[int(len(boots) * 0.05)], 5),
            round(boots[int(len(boots) * 0.95)], 5),
        ],
        "converged_folds": sum(1 for r in records if r["converged"]),
        "total_folds": len(records),
    }


def main() -> None:
    manifest = load_manifest()
    variants = {k: list(v) for k, v in manifest["features"].items()}
    min_train = int(manifest["training"]["minimum_prior_draws"])
    bootstrap_n = int(manifest["uncertainty"]["bootstrap_samples"])
    seed = int(manifest["uncertainty"]["seed"])
    report: dict = {
        "experiment_id": manifest["experiment_id"],
        "manifest_frozen_at": manifest["frozen_at"],
        "evaluation_start": manifest["evaluation_start"],
        "feature_version": manifest["feature_version"],
        "horizon": manifest["horizon"],
        "minimum_prior_draws": min_train,
        "runtime_effect": "none",
        "products": {},
    }
    store = Storage(DB)
    try:
        for pi, product in enumerate(PRODUCTS):
            data = load_rows(
                store, product, horizon=manifest["horizon"],
                feature_version=manifest["feature_version"])
            dev_idx, forward_idx = evaluation_indexes(
                data, min_train, manifest["evaluation_start"])
            dev_records = evaluate_phase(
                data, dev_idx, variants, manifest["training"])
            forward_records = evaluate_phase(
                data, forward_idx, variants, manifest["training"])
            product_report = {
                "n_pit_draws": len(data),
                "n_before_forward_start": sum(
                    1 for asof, _ in data
                    if asof < manifest["evaluation_start"]),
                "development": {},
                "forward": {},
            }
            for vi, variant in enumerate(variants):
                product_report["development"][variant] = summarize(
                    dev_records[variant], bootstrap_n=bootstrap_n,
                    rng=random.Random(seed + pi * 100 + vi))
                product_report["forward"][variant] = summarize(
                    forward_records[variant], bootstrap_n=bootstrap_n,
                    rng=random.Random(seed + 10_000 + pi * 100 + vi))
            report["products"][product] = product_report
            candidate = product_report["forward"][manifest["primary_candidate"]]
            print(f"{product}: {len(data)} {manifest['feature_version']}, "
                  f"{candidate['n_eval_draws']} forward-evaluerade för "
                  f"{manifest['primary_candidate']}")
    finally:
        store.close()

    minimum = int(
        manifest["promotion_gate"]["minimum_forward_draws_per_product"])
    candidate_key = manifest["primary_candidate"]
    checks = {}
    for product, product_report in report["products"].items():
        result = product_report["forward"][candidate_key]
        enough = result["n_eval_draws"] >= minimum
        ci = result.get("delta_ci90")
        better = bool(ci and ci[1] < 0)
        not_worse = bool(ci and ci[0] <= 0)
        checks[product] = {
            "enough_forward_draws": enough,
            "ci_entirely_better": better,
            "not_significantly_worse": not_worse,
        }
    primary = manifest["primary_product"]
    report["promotion_gate"] = {
        "candidate": candidate_key,
        "minimum_forward_draws_per_product": minimum,
        "checks": checks,
        "passes": (
            checks.get(primary, {}).get("enough_forward_draws", False) and
            checks.get(primary, {}).get("ci_entirely_better", False) and
            all(c["enough_forward_draws"] and c["not_significantly_worse"]
                for p, c in checks.items() if p != primary)
        ),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"Promotion: {'JA' if report['promotion_gate']['passes'] else 'NEJ'}")
    print(f"Skrev {OUT}")


if __name__ == "__main__":
    main()
