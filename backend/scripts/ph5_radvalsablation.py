"""PH5 — slår VÅRT radval baslinjerna? Ablation på final_only-backfillen.

Frågan PH3-ledgern inte kan svara på i tid: poolspel ger ~1 datapunkt per omgång
och toppvinster är sällsynta, så en ROI-signifikans dröjer i praktiken år.
Settlementlagret har däremot hundratals relevanta 13-matchsomgångar med
slutstreck, öppningsodds, facit OCH identifierbara vinstnivåer. Det räcker för
att jämföra RADVALSMETODER mot varandra långt innan forward-grinden fylls.

## Vad detta är och inte är

* **Relativ jämförelse, aldrig en spelbar ROI.** Alla armar ser exakt samma
  information (slutstreck + öppningsodds), så jämförelsen är rättvis — men
  slutstrecket var inte känt när raden hade byggts på riktigt. Absoluta tal är
  därför ett optimistiskt icke-PIT-estimat, inte en prognos eller bevisad övre
  gräns. PIT-frågan mäts av `pit-v3`, inte här.
* **Kohort `final_only`** — hålls utanför pit-v3-manifestet och får aldrig
  blandas in i det frysta forward-experimentet.
* Med `--fixed-payout-cohort` väljs bara omgångar där samtliga vinstnivåer är
  identifierbara FÖRE armarna byggs. Kohorten kan då inte ändras med budgeten.
* `byggarslump` dras ur exakt samma kandidatuniversum som produktionsbyggaren.
  Kandidattecknen kommer från `builder.ev_candidate_signs`, aldrig från en
  tredje kopia av EV-logiken.
* `traffsakrare` kör samma produktionsbyggare med `value_weight=0.0`. Det är
  exakt profilen som API/UI kallar "Träffsäkrare", inte en favoritradsproxy.

Körning:  .venv/bin/python -B scripts/ph5_radvalsablation.py [--product X]
              [--limit N] [--budget KR] [--db FIL] [--fixed-payout-cohort]
              [--skip-hamming] [--bootstrap-iters N] [--json FIL]
"""
from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import random
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import builder                                   # noqa: E402
from app.analysis import analyze_draw                     # noqa: E402
from app.pool_system_ledger import counterfactual_payout  # noqa: E402
from app.storage import DEFAULT_DB                        # noqa: E402
from app.svenskaspel import Draw, Match, Outcome          # noqa: E402

COHORT = "final_only-radval-v2"
FIXED_COHORT = "final_only-radval-v3-fixed-payout"
# v1 UNDERKÄNDES av sitt eget förregistrerade sanity-krav (2026-07-25): `slump`
# skulle ligga klart sämst men låg BÄST i fyra av fem produkter, som mest
# +45,5 % i Topptipset Stryk med KI [−69,7..+197,7]. Slumpen var inte bättre —
# den var tyngre i svansen. ROI per omgång är golvad vid −100 % och obegränsad
# uppåt, så ett enda lyckoträff-toppvinstutfall bär hela medelvärdet. Exakt den
# estimand-fällan som gav "+6,6 %" när sanningen var +2,65 %.
#
# v2 (specificerad FÖRE körning, motiverad av validitetsbrottet — inte av att
# resultatet inte passade):
#   1. PARAD jämförelse per omgång: omgångens tur/otur delas av alla armar, så
#      differensen `vår − baslinje` tar bort den helt.
#   2. Winsoriserad differens (±200 pp) — huvudsiffra och KI samma estimand.
#   3. Andel omgångar där vi slår baslinjen (rangstatistik, svansimmun).
#   4. Per-omgångs-ROI SPARAS i JSON, så framtida omräkning aldrig kräver ny
#      1,5-timmarskörning.
WINSOR_PP = 2.0        # ±200 procentenheter på den parade differensen
PRODUCTS = ("stryktipset", "europatipset", "topptipset",
            "topptipsetstryk", "topptipsetextra")
PRIMARY_BASELINES = ("folkrad", "favoritrad", "byggarslump")
SIGNS = ("1", "X", "2")
SEED = 20260725


def prize_plan(product: str) -> dict:
    from app.main import PRIZE_PLANS
    return PRIZE_PLANS[product]


def _tiers_identifiable(tiers: dict[int, tuple], plan: dict) -> bool:
    """Alla nivåpotter måste kunna räknas oavsett vilken arm som träffar dem."""
    for correct in plan["splits"]:
        winners, amount = tiers.get(int(correct), (None, None))
        if winners is None or winners <= 0 or amount is None:
            return False
    return True


def load(conn: sqlite3.Connection, product: str, plan: dict,
         require_identifiable_tiers: bool = False) -> list[dict]:
    """Kompletta omgångar med streck, odds, facit och vinstnivåer."""
    heads = {dn: (net, price, cancelled, close) for dn, net, price, cancelled, close
             in conn.execute(
                 "SELECT draw_number, net_sale, row_price, n_cancelled, "
                 "reg_close_time FROM pool_draw_settlement WHERE product=?",
                 (product,))}
    events: dict[int, list] = {}
    for row in conn.execute(
            "SELECT draw_number, event_number, description, outcome, cancelled, "
            "streck_one, streck_x, streck_two, start_odds_one, start_odds_x, "
            "start_odds_two FROM pool_event_settlement WHERE product=? "
            "ORDER BY draw_number, event_number", (product,)):
        events.setdefault(row[0], []).append(row[1:])
    tiers: dict[int, dict[int, tuple]] = {}
    for dn, correct, winners, amount in conn.execute(
            "SELECT draw_number, correct, winners, amount FROM pool_payout_tier "
            "WHERE product=? AND correct IS NOT NULL", (product,)):
        tiers.setdefault(dn, {})[int(correct)] = (winners, amount)

    out = []
    for dn, (net, price, cancelled, close) in sorted(heads.items()):
        evs = events.get(dn) or []
        if not evs or cancelled or any(e[3] for e in evs):
            continue                      # struket/lottat: facit ej jämförbart
        if require_identifiable_tiers and product in (
                "stryktipset", "europatipset") and len(evs) != 13:
            continue                      # v3-frågan gäller exakt 13 matcher
        if not net or net <= 0 or not price or price <= 0:
            continue
        if any(e[2] not in SIGNS for e in evs):
            continue
        if any(e[i] is None for e in evs for i in (4, 5, 6, 7, 8, 9)):
            continue                      # kräver både streck OCH odds
        draw_tiers = tiers.get(dn) or {}
        if not draw_tiers:
            continue
        if require_identifiable_tiers and not _tiers_identifiable(draw_tiers, plan):
            continue                     # fast kohort före något armutfall
        out.append({"draw": dn, "net_sale": float(net), "row_price": float(price),
                    "close": str(close or ""), "events": evs,
                    "tiers": draw_tiers})
    return out


def as_draw(product: str, row: dict) -> tuple[Draw, list[str]]:
    """Bygg ett Draw-objekt så den RIKTIGA byggaren kan köras på historiken."""
    draw = Draw(product=product, draw_number=row["draw"], state="Finalized",
                reg_close_time=row["close"], net_sale=row["net_sale"],
                row_price=row["row_price"], fetched_at=row["close"], jackpot=0.0)
    facit = []
    for (ev, desc, outcome, _cancelled, s1, sx, s2, o1, ox, o2) in row["events"]:
        streck = {"1": int(s1), "X": int(sx), "2": int(s2)}
        odds = {"1": float(o1), "X": float(ox), "2": float(o2)}
        draw.matches.append(Match(
            event_number=int(ev), description=desc or "?",
            home=(desc or "? - ?").split(" - ")[0],
            away=(desc or "? - ?").split(" - ")[-1],
            home_iso=None, away_iso=None, league="", match_start=row["close"],
            cancelled=False, kambi_id=None,
            outcomes={s: Outcome(sign=s, odds=odds[s], start_odds=odds[s],
                                 streck=streck[s], streck_ref=streck[s])
                      for s in SIGNS}))
        facit.append(outcome)
    return draw, facit


def _candidate_rows(draw: Draw, n_rows: int, rank) -> list[tuple]:
    """Topp-n rader ur samma kandidatmängd som byggaren använder (topp-2 tecken
    per match), rankade av armens egen funktion."""
    per_match = []
    for m in draw.matches:
        ranked = sorted(SIGNS, key=lambda s: -_p_market(m, s))
        per_match.append(ranked[:2])
    rows = [()]
    for signs in per_match:
        rows = [row + (s,) for row in rows for s in signs]
        if len(rows) > 40000:                     # samma andas cap som byggaren
            rows = sorted(rows, key=rank, reverse=True)[:20000]
    return sorted(rows, key=rank, reverse=True)[:n_rows]


def _p_market(m, sign: str) -> float:
    """Marknadens normerade sannolikhet — power-devig via analysis, inte egen
    matematik (samma devig som resten av projektet)."""
    from app.analysis import _fair_probs
    fair, _source = _fair_probs(m.outcomes)
    return float(fair.get(sign) or 0.0)


def _p_folk(m, sign: str) -> float:
    total = sum(m.outcomes[s].streck or 0 for s in SIGNS) or 1
    return max((m.outcomes[sign].streck or 0) / total, 0.001)


def arms(draw: Draw, n_rows: int, rng: random.Random,
         plan: dict, include_hamming: bool = True,
         include_baselines: bool = True) -> dict[str, object]:
    """Armar med samma budget; byggarslump delar vår kandidatmängd exakt."""
    ms = draw.matches

    def p_row(row, fn):
        out = 1.0
        for m, sign in zip(ms, row):
            out *= fn(m, sign)
        return out

    out: dict[str, object] = {}

    # 1. VÅR metod — den riktiga byggaren, exakt samma kod som appen kör.
    analysis = analyze_draw(draw)
    try:
        # PH5 v3 är ett publicerat historiskt experiment. Den nya
        # forwardregeln får en egen v4 och får inte skriva om denna kohort.
        candidate_signs, universe = builder.ev_candidate_signs(
            analysis, 0.5, draw_risk=False)
        system = builder.build_ev_system(
            analysis, strategy="medel", budget=n_rows * (draw.row_price or 1.0),
            row_price=draw.row_price or 1.0, value_weight=0.5, plan=plan,
            jackpot=0.0, draw_risk=False)
        out["varderader"] = [tuple(r) for r in (system.rows or [])][:n_rows]
        hit_system = builder.build_ev_system(
            analysis, strategy="medel", budget=n_rows * (draw.row_price or 1.0),
            row_price=draw.row_price or 1.0, value_weight=0.0, plan=plan,
            jackpot=0.0, draw_risk=False)
        out["traffsakrare"] = [
            tuple(r) for r in (hit_system.rows or [])][:n_rows]
        out["_builder_universe_n"] = universe
        if include_baselines:
            builder_pool = list(itertools.product(*(
                candidate_signs[m.event_number] for m in analysis.matches)))
            builder_rng = random.Random(
                f"{SEED}|{draw.product}|{draw.draw_number}|{n_rows}|byggarslump")
            out["byggarslump"] = builder_rng.sample(
                builder_pool, min(n_rows, len(builder_pool)))
    except Exception as exc:                      # noqa: BLE001
        out["varderader"] = []
        out["_error"] = f"{type(exc).__name__}: {exc}"[:120]   # type: ignore

    if not include_baselines:
        return out

    # 2. Folkets rader — mest streckade kombinationerna.
    out["folkrad"] = _candidate_rows(draw, n_rows, lambda r: p_row(r, _p_folk))
    # 3. Marknadens favoritrader — högst sannolikhet enligt odds.
    out["favoritrad"] = _candidate_rows(draw, n_rows, lambda r: p_row(r, _p_market))
    # 4. Slump bland samma kandidater — golvet.
    pool = _candidate_rows(draw, max(n_rows * 8, 200), lambda r: p_row(r, _p_market))
    out["slump"] = rng.sample(pool, min(n_rows, len(pool)))
    # 5. Hamming-spridning är historiskt förregistrerad men O(rader × pool).
    # Täthetssvepet kan välja bort den eftersom den inte ingår i v3-grinden.
    if include_hamming:
        out["hamming"] = _hamming_spread(pool, n_rows)
    return out


def _hamming_spread(pool: list[tuple], n_rows: int) -> list[tuple]:
    """Girig max-min-Hamming: starta i marknadens toppard, välj sedan raden
    längst från de valda; lika avstånd bryts av lägre poolindex (= högre
    marknadssannolikhet). Inkrementell min-avståndslista håller kostnaden
    på O(rader × pool)."""
    if not pool:
        return []
    target = min(n_rows, len(pool))
    chosen = [pool[0]]
    cands = list(pool[1:])
    mind = [sum(a != b for a, b in zip(c, pool[0])) for c in cands]
    while len(chosen) < target and cands:
        i = max(range(len(cands)), key=lambda j: (mind[j], -j))
        pick = cands.pop(i)
        mind.pop(i)
        chosen.append(pick)
        for j, cand in enumerate(cands):
            d = sum(a != b for a, b in zip(cand, pick))
            if d < mind[j]:
                mind[j] = d
    return chosen


def evaluate(rows: list[tuple], facit: list[str], tiers: dict,
             cost: float) -> dict:
    """Facit för en arm: rätt-fördelning → utspädd utdelning → ROI."""
    if not rows:
        return {"n_rows": 0, "payout": None, "roi": None, "complete": False,
                "best": None}
    dist: dict[int, int] = {}
    best = 0
    for row in rows:
        correct = sum(1 for got, want in zip(row, facit) if got == want)
        dist[correct] = dist.get(correct, 0) + 1
        best = max(best, correct)
    payout, published, complete, _note = counterfactual_payout(dist, tiers)
    roi = ((payout - cost) / cost) if (complete and cost > 0) else None
    return {"n_rows": len(rows), "payout": payout, "published": published,
            "roi": roi, "complete": complete, "best": best}


def block_ci(values: list[float], rng: random.Random,
             iters: int = 1000, alpha: float = 0.10) -> tuple:
    """Bootstrap-KI med OMGÅNGEN som block (samma regel som κ och CLV)."""
    if len(values) < 3:
        return None, None
    means = []
    for _ in range(iters):
        sample = [rng.choice(values) for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(len(means) * alpha / 2)]
    hi = means[min(len(means) - 1, int(len(means) * (1 - alpha / 2)))]
    return round(lo, 4), round(hi, 4)


def _code_version() -> str:
    """Commit som faktiskt kör skriptet; `unknown` utanför en git-kopia."""
    try:
        root = pathlib.Path(__file__).resolve().parents[2]
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", action="append", choices=PRODUCTS)
    ap.add_argument("--limit", type=int, default=0,
                    help="max antal omgångar per produkt (0 = alla)")
    ap.add_argument("--budget", type=float, default=100.0)
    ap.add_argument("--db", type=str, default=str(DEFAULT_DB),
                    help="SQLite-fil; öppnas alltid read-only")
    ap.add_argument("--fixed-payout-cohort", action="store_true",
                    help="kräv identifierbara potter på alla nivåer före armbygge")
    ap.add_argument("--skip-hamming", action="store_true",
                    help="utelämna den kvadratiska Hamming-armen")
    ap.add_argument("--profiles-only", action="store_true",
                    help="jämför bara Standard mot exakta Träffsäkrare-profilen")
    ap.add_argument("--bootstrap-iters", type=int, default=1000)
    ap.add_argument("--json", type=str, default="")
    args = ap.parse_args()

    if args.bootstrap_iters < 100:
        ap.error("--bootstrap-iters måste vara minst 100")
    db_path = pathlib.Path(args.db).expanduser().resolve()
    conn = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    report = {
        "cohort": FIXED_COHORT if args.fixed_payout_cohort else COHORT,
        "seed": SEED,
        "budget": args.budget,
        "code_version": _code_version(),
        "database": {"path": str(db_path), "size_bytes": db_path.stat().st_size},
        "fixed_payout_cohort": args.fixed_payout_cohort,
        "hamming_included": not args.skip_hamming,
        "profiles_only": args.profiles_only,
        "bootstrap_iters": args.bootstrap_iters,
        "primary_baselines": list(PRIMARY_BASELINES),
        "products": {},
    }
    for product in (args.product or PRODUCTS):
        plan = prize_plan(product)
        draws = load(conn, product, plan, args.fixed_payout_cohort)
        if args.limit:
            draws = draws[-args.limit:]            # senaste = mest relevanta
        rng = random.Random(SEED)
        per_arm: dict[str, list[float]] = {}
        per_draw: list[dict] = []
        hits: dict[str, int] = {}
        row_shortfalls: dict[str, int] = {}
        used = incomplete = failed = 0
        for row in draws:
            draw, facit = as_draw(product, row)
            n_rows = max(1, int(args.budget / (row["row_price"] or 1.0)))
            cost = n_rows * (row["row_price"] or 1.0)
            built = arms(draw, n_rows, rng, plan,
                         include_hamming=not args.skip_hamming,
                         include_baselines=not args.profiles_only)
            if not built.get("varderader"):
                failed += 1
                continue
            results = {name: evaluate(rows, facit, row["tiers"], cost)
                       for name, rows in built.items() if not name.startswith("_")}
            if not all(r["complete"] for r in results.values()):
                incomplete += 1
                continue
            expected_arms = (("varderader", "traffsakrare")
                             if args.profiles_only
                             else ("varderader", *PRIMARY_BASELINES))
            for name in expected_arms:
                if results.get(name, {}).get("n_rows") != n_rows:
                    row_shortfalls[name] = row_shortfalls.get(name, 0) + 1
            used += 1
            for name, res in results.items():
                per_arm.setdefault(name, []).append(res["roi"])
                if res["best"] >= max(row["tiers"]):
                    hits[name] = hits.get(name, 0) + 1
            per_draw.append({
                "draw": row["draw"],
                "builder_universe_n": built.get("_builder_universe_n"),
                "n_rows": {name: res["n_rows"] for name, res in results.items()},
                **{name: res["roi"] for name, res in results.items()},
            })
        summary = {}
        for name, rois in sorted(per_arm.items()):
            lo, hi = block_ci(
                rois, random.Random(SEED), iters=args.bootstrap_iters)
            summary[name] = {
                "n_draws": len(rois),
                # BEHÅLLS för spårbarhet men är INTE beslutsunderlag: ROI är
                # golvad vid −100 % och obegränsad uppåt, så en enda toppvinst
                # bär medelvärdet. Se `paired` nedan.
                "mean_roi_unpaired": round(sum(rois) / len(rois), 4) if rois else None,
                "ci90_unpaired": [lo, hi], "top_tier_hits": hits.get(name, 0)}

        # HUVUDANALYS: parad differens mot varje baslinje. Omgångens tur delas
        # av alla armar, så differensen isolerar radvalet.
        paired = {}
        ours = "varderader"
        for name in sorted(per_arm):
            if name == ours:
                continue
            diffs = [d[ours] - d[name] for d in per_draw
                     if d.get(ours) is not None and d.get(name) is not None]
            if not diffs:
                continue
            wins = sum(1 for x in diffs if x > 0)
            clipped = [max(-WINSOR_PP, min(WINSOR_PP, x)) for x in diffs]
            lo90, hi90 = block_ci(
                clipped, random.Random(SEED), iters=args.bootstrap_iters,
                alpha=0.10)
            lo95, hi95 = block_ci(
                clipped, random.Random(SEED), iters=args.bootstrap_iters,
                alpha=0.05)
            paired[name] = {
                "n": len(diffs),
                "mean_diff_w": round(sum(clipped) / len(clipped), 4),
                "median_diff": round(sorted(diffs)[len(diffs) // 2], 4),
                "ci90": [lo90, hi90],
                "ci95": [lo95, hi95],
                "passes_ci95": lo95 is not None and lo95 > 0,
                "win_share": round(wins / len(diffs), 4)}

        report["products"][product] = {
            "n_available": len(draws), "n_used": used,
            "n_incomplete_payout": incomplete, "n_build_failed": failed,
            "primary_row_shortfalls": row_shortfalls,
            "arms": summary, "paired_vs_baselines": paired,
            # rådata så omräkning aldrig kräver en ny 1,5-timmarskörning
            "per_draw_roi": per_draw}
        print(f"\n{product} — {used} utvärderade omgångar "
              f"({incomplete} ofullständig utdelning, {failed} byggfel)")
        print("   toppnivåträffar: " + ", ".join(
            f"{n} {s['top_tier_hits']}" for n, s in summary.items()))
        print(f"   PARAD differens {ours} − baslinje (winsoriserad ±200 pp):")
        for name, p in paired.items():
            ci = (f"[{p['ci95'][0]*100:+.1f}..{p['ci95'][1]*100:+.1f}]"
                  if p["ci95"][0] is not None else "KI –")
            print(f"     vs {name:12s} {p['mean_diff_w']*100:+7.1f} pp {ci:>20s}"
                  f" · median {p['median_diff']*100:+6.1f} pp"
                  f" · vinner {p['win_share']*100:.0f} % av omgångarna")
    conn.close()
    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nSkrev {args.json}")


if __name__ == "__main__":
    main()
