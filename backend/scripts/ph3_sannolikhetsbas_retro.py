"""Retroaktiv NOMINERINGSKONTROLL: Pinnacle- mot SvS-bas i EV-byggaren.

Fråga (förregistrerad i docs/ph3-sannolikhetsbas-v1-2026-09-02.md): väljer
`build_ev_system` andra rader när `_pq` tar Pinnacles devigade pris först
(`prob_base="sharp"`) i stället för SvS-oddsens (`"svs"`, dagens champion),
och blir träff/ROI annorlunda på Topptipset-familjens pit-v4-omgångar?

Underlag: ENBART `pool_pit_match_features` (pit-v4, observed_pit, horisont
h3) — samma frysta point-in-time-sannolikheter som PH4 dömdes på — plus
settlementlagrets facit. Ingen bakfyllning, inga dagens priser. Båda armarna
ser exakt samma omgångar, samma turnover_asof och samma jackpot_asof, så
skillnaden är radvalet och inget annat.

Detta är en NOMINERINGSKONTROLL, inte promotionsbevis: kohorten är retroaktiv
även om priserna är PIT (radvalet kördes aldrig live), och PH3:s
promotionsregel kräver BH-FDR över hela utmanarfamiljen på ≥ 40 parade
FRAMÅT frysta omgångar. Utmanaren `dr1-b256-medel-sharp` mäts därför även
framåt i PH3 från och med nästa Topptipsomgång.

Körning (read-only, gärna mot snapshoten):
  cd backend && PYTHONPATH=. .venv/bin/python -B scripts/ph3_sannolikhetsbas_retro.py \
      --db data/optimizer/snapshot-2026-09-02.db
Utdata: docs/ph3-sannolikhetsbas-retro-2026-09-02.json + sammanfattning.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.builder import build_ev_system                      # noqa: E402
from app.pool_system_ledger import counterfactual_payout     # noqa: E402

VERSION = "ph3-sannolikhetsbas-retro-v1"
SEED = 20260902
PRODUCTS = ("topptipset", "topptipsetstryk", "topptipsetextra")
PLAN = {"ratio": 0.70, "splits": {8: 1.00}}      # = main.PRIZE_PLANS Topptipset
HORIZON = "h3"
FEATURE_VERSION = "pit-v4"
BUDGET, STRATEGY, VALUE_WEIGHT = 256.0, "medel", 0.5   # = dr1-b256-medel
OUT = ROOT.parent / "docs" / "ph3-sannolikhetsbas-retro-2026-09-02.json"
SIGNS = ("1", "X", "2")


def _analysis(product: str, matches: list[sqlite3.Row], turnover: float):
    out = []
    for m in matches:
        svs = (m["p_svs_1"], m["p_svs_x"], m["p_svs_2"])
        sharp = (m["p_sharp_1"], m["p_sharp_x"], m["p_sharp_2"])
        svs_ok = bool(m["svs_eligible"]) and None not in svs
        sharp_ok = bool(m["sharp_eligible"]) and None not in sharp
        if not svs_ok and not sharp_ok:
            return None
        # fair_prob speglar analysis.py: SvS-odds först, Pinnacle som reserv.
        fair = svs if svs_ok else sharp
        outcomes = {}
        for i, s in enumerate(SIGNS):
            streck = (m["streck_1"], m["streck_x"], m["streck_2"])[i]
            outcomes[s] = SimpleNamespace(
                fair_prob=fair[i], sharp_prob=(sharp[i] if sharp_ok else None),
                streck=streck, tags=[], value=0, value_sharp=0)
        fav = max(SIGNS, key=lambda s: outcomes[s].fair_prob)
        out.append(SimpleNamespace(
            event_number=int(m["event_number"]), description=f"M{m['event_number']}",
            cancelled=False, outcomes=outcomes, favourite=fav,
            favourite_prob=outcomes[fav].fair_prob,
            spik_score=outcomes[fav].fair_prob * 100,
            open_score=(1 - outcomes[fav].fair_prob) * 100,
            best_value_sign=None, total_line=None))
    return SimpleNamespace(matches=out, turnover=turnover, product=product,
                           row_price=1.0)


def _settle(rows: list[list[str]], facit: list[str], tiers: dict) -> dict:
    dist: dict[int, int] = {}
    for signs in rows:
        c = sum(1 for s, r in zip(signs, facit) if s == r)
        dist[c] = dist.get(c, 0) + 1
    payout, published, complete, note = counterfactual_payout(dist, tiers)
    cost = float(len(rows))
    return {"hit": int(max(dist) == len(facit)) if dist else 0,
            "payout": payout, "complete": complete,
            "roi": ((payout - cost) / cost) if payout is not None else None}


def _ci(diffs: list[float], rng: random.Random, n_boot: int = 2000):
    if len(diffs) < 5:
        return None
    boots = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(len(diffs))] for _ in diffs]
        boots.append(statistics.mean(sample))
    boots.sort()
    return [round(boots[int(0.05 * n_boot)], 5), round(boots[int(0.95 * n_boot)], 5)]


def main() -> int:
    global HORIZON, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "stryktips.db"))
    # Förregistrerat h3. m20 lades till 2026-09-02 EFTER att h3-täckningen
    # visat sig vara 18/87 omgångar (Pinnacle listar de flesta Topptips-
    # matcherna först nära avspark: m20 56/88) men FÖRE något m20-resultat
    # sågs — redovisas som kompletterande, aldrig i stället för h3.
    ap.add_argument("--horizon", default=HORIZON, choices=("h24", "h3", "m20"))
    args = ap.parse_args()
    HORIZON = args.horizon
    if HORIZON != "h3":
        OUT = OUT.with_name(OUT.stem + f"-{HORIZON}" + OUT.suffix)
    conn = sqlite3.connect(f"file:{Path(args.db).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    draws = conn.execute(
        "SELECT f.product, f.draw_number, f.n_events, f.turnover_asof, "
        "f.jackpot_asof, s.net_sale FROM pool_pit_draw_features f "
        "JOIN pool_draw_settlement s ON s.product=f.product AND "
        "s.draw_number=f.draw_number AND s.draw_state='Finalized' "
        "WHERE f.horizon=? AND f.feature_version=? AND f.product IN (?,?,?) "
        "ORDER BY s.reg_close_time", (HORIZON, FEATURE_VERSION, *PRODUCTS)).fetchall()
    records, skipped = [], {"ofullstandiga_features": 0, "facit_saknas": 0,
                            "utdelning_ofullstandig": 0, "bygge_misslyckades": 0}
    for d in draws:
        product, dn = d["product"], int(d["draw_number"])
        matches = conn.execute(
            "SELECT * FROM pool_pit_match_features WHERE product=? AND "
            "draw_number=? AND horizon=? AND feature_version=? ORDER BY event_number",
            (product, dn, HORIZON, FEATURE_VERSION)).fetchall()
        if len(matches) != int(d["n_events"]):
            skipped["ofullstandiga_features"] += 1
            continue
        outcomes = dict(conn.execute(
            "SELECT event_number, outcome FROM pool_event_settlement WHERE "
            "product=? AND draw_number=?", (product, dn)).fetchall())
        facit = [outcomes.get(int(m["event_number"])) for m in matches]
        if any(o not in SIGNS for o in facit):
            skipped["facit_saknas"] += 1
            continue
        tiers = {int(r[0]): (r[1], r[2]) for r in conn.execute(
            "SELECT correct, winners, amount FROM pool_payout_tier WHERE "
            "product=? AND draw_number=? AND correct IS NOT NULL", (product, dn))}
        turnover = float(d["turnover_asof"] or 0.0) or float(d["net_sale"] or 0.0)
        analysis = _analysis(product, matches, turnover)
        if analysis is None:
            skipped["ofullstandiga_features"] += 1
            continue
        jackpot = max(0.0, float(d["jackpot_asof"] or 0.0))
        arms = {}
        for base in ("svs", "sharp"):
            try:
                system = build_ev_system(
                    analysis, STRATEGY, BUDGET, row_price=1.0,
                    value_weight=VALUE_WEIGHT, plan=PLAN, jackpot=jackpot,
                    prob_base=base)
            except Exception as exc:                      # noqa: BLE001
                skipped["bygge_misslyckades"] += 1
                arms = None
                print(f"  {product} {dn}: bygge misslyckades ({exc})")
                break
            arms[base] = {"rows": [list(r) for r in system.rows],
                          **_settle([list(r) for r in system.rows], facit, tiers)}
        if not arms:
            continue
        if not (arms["svs"]["complete"] and arms["sharp"]["complete"]):
            skipped["utdelning_ofullstandig"] += 1
            continue
        a, b = arms["svs"], arms["sharp"]
        shared = len({tuple(r) for r in a["rows"]} & {tuple(r) for r in b["rows"]})
        n_sharp = sum(1 for m in matches if m["sharp_eligible"])
        records.append({
            "product": product, "draw_number": dn, "n_sharp_eligible": n_sharp,
            "turnover_asof": turnover, "jackpot_asof": jackpot,
            "rows_shared": shared, "rows_total": len(a["rows"]),
            "svs": {"hit": a["hit"], "roi": a["roi"], "payout": a["payout"]},
            "sharp": {"hit": b["hit"], "roi": b["roi"], "payout": b["payout"]},
        })

    rng = random.Random(SEED)
    n = len(records)
    d_hit = [r["sharp"]["hit"] - r["svs"]["hit"] for r in records]
    d_roi = [r["sharp"]["roi"] - r["svs"]["roi"] for r in records]
    # Winsorisering på de NOLLSKILDA parade skillnaderna: när radvalen är
    # identiska i de flesta omgångar är 95:e percentilen av alla |Δ| noll och
    # skulle nolla varje verklig skillnad. Rå Δ och rå KI redovisas bredvid.
    nonzero = sorted(abs(x) for x in d_roi if x != 0.0)
    cap = nonzero[int(0.95 * (len(nonzero) - 1))] if nonzero else 0.0
    d_roi_w = [max(-cap, min(cap, x)) for x in d_roi]
    summary = {
        "version": VERSION, "seed": SEED, "db": str(Path(args.db).resolve()),
        "horizon": HORIZON, "feature_version": FEATURE_VERSION,
        "config": {"budget": BUDGET, "strategy": STRATEGY,
                   "value_weight": VALUE_WEIGHT, "champion": "dr1-b256-medel",
                   "challenger": "dr1-b256-medel-sharp"},
        "n_draws": n, "skipped": skipped,
        "draws_with_any_sharp": sum(1 for r in records if r["n_sharp_eligible"]),
        "draws_with_full_sharp": sum(1 for r in records if r["n_sharp_eligible"] == 8),
        "mean_rows_shared": (round(statistics.mean(
            r["rows_shared"] / r["rows_total"] for r in records), 4) if n else None),
        "draws_identical": sum(1 for r in records if r["rows_shared"] == r["rows_total"]),
        "hits": {"svs": sum(r["svs"]["hit"] for r in records),
                 "sharp": sum(r["sharp"]["hit"] for r in records)},
        "roi_mean": {"svs": round(statistics.mean(r["svs"]["roi"] for r in records), 4) if n else None,
                     "sharp": round(statistics.mean(r["sharp"]["roi"] for r in records), 4) if n else None},
        "paired": {
            "hit_diff_mean": round(statistics.mean(d_hit), 5) if n else None,
            "hit_diff_ci90": _ci(d_hit, rng),
            "roi_diff_mean_raw": round(statistics.mean(d_roi), 5) if n else None,
            "roi_diff_ci90_raw": _ci(d_roi, rng),
            "roi_diff_mean_winsor": round(statistics.mean(d_roi_w), 5) if n else None,
            "roi_diff_ci90_winsor": _ci(d_roi_w, rng),
            "n_draws_rows_differ": sum(1 for r in records
                                       if r["rows_shared"] < r["rows_total"]),
            "n_draws_roi_differ": sum(1 for x in d_roi if x != 0.0),
            "winsor_cap": round(cap, 4),
        },
        "records": records,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    s = summary
    print(f"{VERSION}: {n} omgångar (hoppade: {skipped})")
    print(f"  sharp-eligible i någon match: {s['draws_with_any_sharp']}, alla 8: "
          f"{s['draws_with_full_sharp']}; identiska radval: {s['draws_identical']}; "
          f"delade rader i snitt: {s['mean_rows_shared']}")
    print(f"  8 rätt: svs {s['hits']['svs']} / sharp {s['hits']['sharp']}  "
          f"(Δ {s['paired']['hit_diff_mean']}, KI90 {s['paired']['hit_diff_ci90']})")
    print(f"  ROI: svs {s['roi_mean']['svs']} / sharp {s['roi_mean']['sharp']}  "
          f"(Δ winsor {s['paired']['roi_diff_mean_winsor']}, KI90 "
          f"{s['paired']['roi_diff_ci90_winsor']}, rå Δ {s['paired']['roi_diff_mean_raw']} "
          f"KI90 {s['paired']['roi_diff_ci90_raw']}; ROI skiljer i "
          f"{s['paired']['n_draws_roi_differ']} omgångar)")
    print(f"  skrivet: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
