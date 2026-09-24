"""Begränsad PIT-reserv före m20; livehits/cache orörda, ingen bakfyllning."""
from __future__ import annotations

import datetime as dt
import json
import math
import time
from types import SimpleNamespace

from . import pool_dataset
from .pinnacle import Pinnacle

COLLECTION_VERSION = "pool-capture-v2"
MAX_REQUESTS = 13
BUDGET_S = 12
TIMEOUT_S = 2
RETRY_AFTER_S = 240


def capture_missing(store, product, draw, result, varv, *, now=None, clock=time.monotonic):
    """Försök bara under de sista 10 minuterna FÖRE m20-as-of.

    Samma provider-id delas mellan produkter, högst 13 försök/12 s per varv
    (ett pågående anrop kan ta ytterligare TIMEOUT_S per nätverksfas).
    Ett redan giltigt event hoppas över. Källfel och för gamla priser ändrar
    ingenting; fullständig 1X2 OCH total krävs för att ingen äldre total ska
    få låna närvaro från det nya 1X2-priset. Bulk och styrke-shadow är orörda.
    """
    report = {"attempted": 0, "captured": 0, "rejected": 0, "errors": 0}
    injected_now = now
    now = now or dt.datetime.now(dt.timezone.utc)
    close = pool_dataset._parse(draw.reg_close_time)
    if close is None or not result or result.get("pinnacle_error") or result.get("skipped"):
        return report
    target = close - dt.timedelta(minutes=pool_dataset.HORIZONS["m20"])
    start = target - dt.timedelta(minutes=pool_dataset.TIMING_TOLERANCE_MIN["m20"])
    if not start <= now <= target:
        return report
    start_s, target_s = pool_dataset._iso(start), pool_dataset._iso(target)
    bulk_time = pool_dataset._parse(result.get("fetched_at"))
    if bulk_time is None:
        return report
    if varv.detail_deadline is None:
        varv.detail_deadline = clock() + BUDGET_S
    for match in draw.matches:
        hit = (result.get("hits") or {}).get(match.event_number) or {}
        mid = hit.get("id")
        if not mid or getattr(match, "cancelled", False):
            continue                    # aldrig en ny fuzzy-/ensidig ID-länk
        mid = str(mid)
        latest = store.conn.execute(
            "SELECT fetched_at,status,odds_complete FROM pool_market_capture "
            "WHERE product=? AND draw_number=? AND event_number=? AND source='sharp' "
            "AND fetched_at<=? ORDER BY fetched_at DESC LIMIT 1",
            (product, draw.draw_number, match.event_number, target_s)).fetchone()
        if latest and latest[0] >= start_s and latest[1] in ("matched", "derived") and latest[2]:
            continue
        if start <= bulk_time <= target and all((hit.get("odds") or {}).get(s) for s in ("1", "X", "2")):
            continue
        key = f"pool_detail_attempt:{mid}"
        quote = varv.detail_quotes.get(mid)
        if mid not in varv.detail_quotes:
            # Budgeten stoppar bara NYA nätanrop. `break` hoppade även över
            # senare matcher vars svar redan hämtats i samma varv av en annan
            # produkt (statusauditen 2026-09-24, fynd C9).
            if clock() >= varv.detail_deadline or len(varv.detail_quotes) >= MAX_REQUESTS:
                continue
            # Kontrollera väggklockan även efter tidigare nätanrop i samma loop.
            requested = injected_now or dt.datetime.now(dt.timezone.utc)
            if requested > target:
                break
            # now är injicerbar; quote.retrieved_at har alltid verklig per-anropstid.
            prior = store.meta_get(key)
            try:
                previous = pool_dataset._parse(json.loads(prior)["retrieved_at"]) if prior else None
            except (ValueError, KeyError, TypeError):
                previous = None
            if previous and (requested - previous).total_seconds() < RETRY_AFTER_S:
                continue
            varv.detail_quotes[mid] = None
            report["attempted"] += 1
            audit = {"version": COLLECTION_VERSION, "retrieved_at": pool_dataset._iso(requested)}
            try:
                with Pinnacle(timeout=TIMEOUT_S) as pin:
                    quote = pin.prematch_quote(mid)
                varv.detail_quotes[mid] = quote
                audit.update({k: quote[k] for k in ("retrieved_at", "fetched_at", "cache_age_s", "cache_age_valid")})
                audit["status"] = "observed"
            except Exception as exc:  # källfel får inte fabricera frånvaro
                report["errors"] += 1
                audit["status"] = "error"
                audit["error"] = type(exc).__name__
            store.meta_set(key, json.dumps(audit))
        if not quote:
            continue
        observed = pool_dataset._parse(quote.get("fetched_at"))
        retrieved = pool_dataset._parse(quote.get("retrieved_at"))
        odds, total = quote.get("odds") or {}, quote.get("total") or {}
        if (not observed or not retrieved or not quote.get("cache_age_valid") or
                observed > retrieved or retrieved > target or
                not start <= observed <= target or observed <= bulk_time or
                not all(odds.get(s, 0) > 1 for s in ("1", "X", "2")) or
                not all(total.get(k) is not None for k in ("line", "O", "U")) or
                not all(math.isfinite(float(v)) for v in [*odds.values(), *total.values()]) or
                total["O"] <= 1 or total["U"] <= 1):
            report["rejected"] += 1
            continue
        stamp = pool_dataset._iso(observed)
        newest = store.sharp_latest_observations(product, draw.draw_number).get(match.event_number)
        if newest and stamp < newest:
            report["rejected"] += 1
            continue
        if hit.get("swapped"):
            odds = {"1": odds["2"], "X": odds["X"], "2": odds["1"]}
        fresh = {"odds": odds, "total": total}
        partial = SimpleNamespace(draw_number=draw.draw_number, matches=[match])
        with store.bulk():
            store.save_sharp_snapshot(product, draw.draw_number, {match.event_number: fresh}, stamp)
            pool_dataset.record_sharp_capture(store, product, partial, {
                "hits": {match.event_number: fresh}, "status": {match.event_number: "matched"},
                "fetched_at": stamp})
        report["captured"] += 1
    return report
