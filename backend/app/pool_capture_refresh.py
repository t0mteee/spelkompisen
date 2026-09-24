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
ACCEPTED = "godtagen"
SOURCE_ERROR = "kallfel"
# Avslagsorsakerna i EXAKT den ordning villkoret alltid prövats. Den första
# som slår till är orsaken; vilka svar som godtas är oförändrat (fynd D3).
REJECT_REASONS = (
    "pristid_saknas",            # fetched_at saknas/oläslig
    "hamtningstid_saknas",       # retrieved_at saknas/oläslig
    "age_ogiltig",               # HTTP Age saknades eller var oläslig
    "pristid_efter_hamtning",    # negativ ålder: pristid > hämtningstid
    "hamtad_efter_as_of",
    "observerad_fore_fonstret",
    "observerad_efter_as_of",    # följer redan av de två föregående; kvar 1:1
    "ej_nyare_an_bulk",
    "ofullstandig_1x2",
    "ofullstandig_total",
    "ej_finit",
    "total_odds_ogiltiga",       # O eller U <= 1
    "aldre_an_senaste_observation",
)


def reject_reason(quote, start, target, bulk_time):
    """Första orsaken att avvisa ett detaljsvar, eller None.

    Samma villkor, i samma ordning och med samma kortslutning som den tidigare
    enda `or`-kedjan — också ett undantag (t.ex. None som odds) uppstår på
    samma ställe. `observerad_efter_as_of` kan inte slå till: pristid <=
    hämtningstid <= as-of är redan prövat; den finns för att varje del av det
    gamla fönstervillkoret ska ha ett namn. Kontrollen mot senaste
    observationen kräver databasen och görs i `capture_missing`."""
    observed = pool_dataset._parse(quote.get("fetched_at"))
    retrieved = pool_dataset._parse(quote.get("retrieved_at"))
    odds, total = quote.get("odds") or {}, quote.get("total") or {}
    if not observed:
        return "pristid_saknas"
    if not retrieved:
        return "hamtningstid_saknas"
    if not quote.get("cache_age_valid"):
        return "age_ogiltig"
    if observed > retrieved:
        return "pristid_efter_hamtning"
    if retrieved > target:
        return "hamtad_efter_as_of"
    if not start <= observed:
        return "observerad_fore_fonstret"
    if not observed <= target:
        return "observerad_efter_as_of"
    if observed <= bulk_time:
        return "ej_nyare_an_bulk"
    if not all(odds.get(s, 0) > 1 for s in ("1", "X", "2")):
        return "ofullstandig_1x2"
    if not all(total.get(k) is not None for k in ("line", "O", "U")):
        return "ofullstandig_total"
    if not all(math.isfinite(float(v)) for v in [*odds.values(), *total.values()]):
        return "ej_finit"
    if total["O"] <= 1 or total["U"] <= 1:
        return "total_odds_ogiltiga"
    return None


def log_lines(report):
    """En rad per prövat svar för den append-only poolloggen."""
    for e in report.get("log", ()):
        age = e.get("cache_age_s")
        yield (f"m20-reserv id {e['matchup_id']} match {e['event']}: {e['reason']}"
               + (f" ({e['error']}, begärd {e.get('requested_at')})" if e.get("error") else "")
               + f" · pristid {e.get('fetched_at') or '–'}"
               + f" · hämtad {e.get('retrieved_at') or '–'}"
               + f" · Age {'–' if age is None else age} s"
               + ("" if e.get("new_request") else " · svar hämtat tidigare i varvet"))


def capture_missing(store, product, draw, result, varv, *, now=None, clock=time.monotonic):
    """Försök bara under de sista 10 minuterna FÖRE m20-as-of.

    Samma provider-id delas mellan produkter, högst 13 försök/12 s per varv
    (ett pågående anrop kan ta ytterligare TIMEOUT_S per nätverksfas).
    Ett redan giltigt event hoppas över. Källfel och för gamla priser ändrar
    ingenting; fullständig 1X2 OCH total krävs för att ingen äldre total ska
    få låna närvaro från det nya 1X2-priset. Bulk och styrke-shadow är orörda.
    """
    report = {"attempted": 0, "captured": 0, "rejected": 0, "errors": 0,
              "reasons": {}, "log": []}
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
        new_request = False
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
            new_request = True
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
                report["log"].append({
                    "matchup_id": mid, "event": match.event_number, "reason": SOURCE_ERROR,
                    "error": audit["error"], "requested_at": audit["retrieved_at"],
                    "fetched_at": None, "retrieved_at": None, "cache_age_s": None,
                    "new_request": True})
            store.meta_set(key, json.dumps(audit))
        if not quote:
            continue
        reason = reject_reason(quote, start, target, bulk_time)
        if reason is None:
            observed = pool_dataset._parse(quote.get("fetched_at"))
            odds, total = quote.get("odds") or {}, quote.get("total") or {}
            stamp = pool_dataset._iso(observed)
            newest = store.sharp_latest_observations(product, draw.draw_number).get(match.event_number)
            # Oförändrad strängjämförelse (D3 får inte ändra vilka svar som
            # godtas); stamp är alltid sekundformat med Z.
            if newest and stamp < newest:
                reason = "aldre_an_senaste_observation"
        report["log"].append({
            "matchup_id": mid, "event": match.event_number, "reason": reason or ACCEPTED,
            "fetched_at": quote.get("fetched_at"), "retrieved_at": quote.get("retrieved_at"),
            "cache_age_s": quote.get("cache_age_s"), "new_request": new_request})
        if reason:
            report["rejected"] += 1
            report["reasons"][reason] = report["reasons"].get(reason, 0) + 1
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
