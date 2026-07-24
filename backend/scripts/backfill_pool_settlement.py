"""PH1-backfill: fyll settlementlagret bakåt via SvS öppna API (final_only).

Går nedåt från senaste lokalt kända omgång per produkt tills en permanent
404-serie (GAP_STOP i rad) eller golvet från PH0-auditen. Idempotent och
resumable: settlade omgångar hoppas över utan API-anrop, misslyckade förblir
retrybara via pool_backfill_log. Throttlad (default 0,35 s → ingen 429 i
PH0). Avbrott är ofarligt — kör igen så fortsätter den.

Körning:
    cd backend && .venv/bin/python -B scripts/backfill_pool_settlement.py \
        [--product stryktipset] [--delay 0.35] [--max-requests 8000] \
        [--retry-404] [--floor 1]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import pool_settlement as ps          # noqa: E402
from app.storage import Storage                # noqa: E402
from app.svenskaspel import PRODUCTS, SvenskaSpel  # noqa: E402

# PH0-belagda golv (äldsta åtkomliga / äldsta sonderade träff) — sondera
# ändå GAP_STOP under golvet så att exakta gränser dokumenteras naturligt.
PH0_FLOORS = {"stryktipset": 4267, "europatipset": 1606, "topptipset": 3246,
              "topptipsetstryk": 363, "topptipsetextra": 865}
GAP_STOP = 25   # så många 404 i rad = permanent gräns, sluta


def backfill_product(store: Storage, svs: SvenskaSpel, product: str,
                     delay: float, budget: dict, retry_404: bool,
                     floor: int, version: str) -> dict:
    top = store.conn.execute(
        "SELECT MAX(draw_number) FROM draws WHERE product=?",
        (product,)).fetchone()[0]
    if not top:
        return {"product": product, "error": "ingen lokal omgång"}
    stats = {"product": product, "from": int(top), "ok": 0, "exists": 0,
             "http_404": 0, "not_finalized": 0, "incomplete_result": 0,
             "error": 0, "skipped_log": 0, "stopped_at": None}
    misses_in_a_row = 0
    n = int(top)
    while n >= max(1, floor) and budget["left"] > 0:
        if ps.is_settled(store, product, n):
            stats["exists"] += 1
            misses_in_a_row = 0
            n -= 1
            continue
        last = ps.latest_status(store, product, n)
        if last == ps.HTTP_404 and not retry_404:
            stats["skipped_log"] += 1
            misses_in_a_row += 1   # känd lucka räknas mot stoppserien
            if misses_in_a_row >= GAP_STOP and n < PH0_FLOORS.get(product, 0):
                stats["stopped_at"] = n
                break
            n -= 1
            continue
        time.sleep(delay)
        budget["left"] -= 2   # draw + result
        status = ps.settle_draw(store, svs, product, n, source_version=version)
        stats[status] = stats.get(status, 0) + 1
        if status == ps.HTTP_404:
            misses_in_a_row += 1
            # under PH0-golvet räcker gapserien för att kalla gränsen permanent
            if misses_in_a_row >= GAP_STOP and n < PH0_FLOORS.get(product, 0):
                stats["stopped_at"] = n
                break
        else:
            misses_in_a_row = 0
        done = stats["ok"] + stats["exists"]
        if done and done % 100 == 0:
            print(f"  {product}: {done} klara, vid #{n}, "
                  f"budget kvar {budget['left']}", flush=True)
        n -= 1
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", choices=list(PRODUCTS), default=None)
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--max-requests", type=int, default=8000)
    ap.add_argument("--retry-404", action="store_true")
    ap.add_argument("--floor", type=int, default=1)
    args = ap.parse_args()

    products = [args.product] if args.product else list(PRODUCTS)
    budget = {"left": args.max_requests}
    store = Storage()
    version = ps._git_hash()   # noqa: SLF001 — samma version hela körningen
    try:
        with SvenskaSpel() as svs:
            for product in products:
                print(f"backfill {product} …", flush=True)
                stats = backfill_product(
                    store, svs, product, args.delay, budget,
                    args.retry_404, args.floor, version)
                print(f"  -> {stats}", flush=True)
                if budget["left"] <= 0:
                    print("requestbudgeten slut — kör igen för att fortsätta.",
                          flush=True)
                    break
    finally:
        store.close()


if __name__ == "__main__":
    main()
