"""PH1: immutable settlementlager för poolspelen (2026-07-24).

Append-once-facit per omgång: utfall per match, slutstreck, slutomsättning
och full utdelning per prisnivå, med payload-hash och källversion. Första
lyckade läsningen är kanon — avvikande omhämtningar loggas som `divergence`
i `pool_backfill_log` och skriver ALDRIG över. Kohorten (observed_pit/
final_only) lagras inte här utan stämplas i PH2-datasetet.

Semantiken i `snapshots`/`sharp_snapshots` rörs inte. Design och testfall:
`docs/ph1-settlement-schema-forslag-2026-07-24.md`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Optional

from .storage import Storage
from .svenskaspel import SvenskaSpel, _f, _i

# Statusar i pool_backfill_log (retrybara: http_404 via --retry-404,
# not_finalized/incomplete_result/error alltid).
OK = "ok"
EXISTS = "exists"
NOT_FINALIZED = "not_finalized"
HTTP_404 = "http_404"
INCOMPLETE = "incomplete_result"
DIVERGENCE = "divergence"
ERROR = "error"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent, capture_output=True,
            text=True, timeout=5).stdout.strip() or "okand"
    except Exception:  # noqa: BLE001
        return "okand"


def payload_hash(raw_draw: dict, raw_result: dict) -> str:
    blob = json.dumps(raw_draw, sort_keys=True, ensure_ascii=False) + \
        json.dumps(raw_result, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _log(store: Storage, product: str, draw_number: int, status: str,
         detail: Optional[str] = None) -> None:
    store.conn.execute(
        "INSERT OR REPLACE INTO pool_backfill_log "
        "(product, draw_number, attempted_at, status, detail) "
        "VALUES (?,?,?,?,?)",
        (product, draw_number, _now_iso(), status, detail))
    if not store._bulk:  # noqa: SLF001 — samma commitregel som övriga moduler
        store.conn.commit()


def is_settled(store: Storage, product: str, draw_number: int) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM pool_draw_settlement WHERE product=? AND draw_number=?",
        (product, draw_number)).fetchone() is not None


def _tiers_complete(result: dict) -> bool:
    tiers = result.get("distribution") or []
    return bool(tiers) and all(
        t.get("winners") is not None and t.get("amount") is not None
        for t in tiers)


def settle_draw(store: Storage, svs: SvenskaSpel, product: str,
                draw_number: int, source_version: Optional[str] = None) -> str:
    """Hämta + skriv settlement för EN omgång. Idempotent: redan settlad
    omgång returnerar 'exists' utan API-anrop. Allt-eller-inget per omgång."""
    if is_settled(store, product, draw_number):
        return EXISTS
    try:
        raw = svs.raw_draw(product, draw_number)
    except Exception as exc:  # noqa: BLE001 — transportfel är retrybart
        _log(store, product, draw_number, ERROR, f"draw: {exc}")
        return ERROR
    if raw is None:
        _log(store, product, draw_number, HTTP_404, "draw 404")
        return HTTP_404
    state = raw.get("drawState") or ""
    if state != "Finalized":
        _log(store, product, draw_number, NOT_FINALIZED, f"state={state}")
        return NOT_FINALIZED
    try:
        result = svs.raw_result(product, draw_number)
    except Exception as exc:  # noqa: BLE001
        _log(store, product, draw_number, ERROR, f"result: {exc}")
        return ERROR
    if result is None or not _tiers_complete(result):
        _log(store, product, draw_number, INCOMPLETE,
             "result saknas" if result is None else "distribution ofullständig")
        return INCOMPLETE

    version = source_version or _git_hash()
    events = raw.get("drawEvents") or []
    outcome_by_event = {}
    cancelled_by_event = {}
    for ev in (result.get("events") or []):
        en = ev.get("eventNumber")
        if ev.get("outcome") in ("1", "X", "2"):
            outcome_by_event[en] = ev["outcome"]
        cancelled_by_event[en] = bool(ev.get("cancelled"))
    try:
        with store.bulk():
            n_cancelled = sum(1 for v in cancelled_by_event.values() if v)
            store.conn.execute(
                "INSERT INTO pool_draw_settlement (product, draw_number, "
                "draw_state, reg_close_time, net_sale, row_price, n_events, "
                "n_cancelled, product_name, source_version, payload_hash, "
                "fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw_number, state, raw.get("regCloseTime"),
                 _f(result.get("currentNetSale")) or _f(raw.get("currentNetSale")),
                 _f(raw.get("rowPrice")), len(events), n_cancelled,
                 raw.get("productName"), version,
                 payload_hash(raw, result), _now_iso()))
            for ev in events:
                match = ev.get("match") or {}
                parts = {p.get("type"): p for p in match.get("participants", [])}
                start_odds = ev.get("startOdds") or {}
                folk = ev.get("svenskaFolket") or {}
                en = ev.get("eventNumber")
                store.conn.execute(
                    "INSERT INTO pool_event_settlement (product, draw_number, "
                    "event_number, description, home, away, match_start, "
                    "outcome, cancelled, streck_one, streck_x, streck_two, "
                    "start_odds_one, start_odds_x, start_odds_two) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (product, draw_number, en, ev.get("eventDescription"),
                     parts.get("home", {}).get("name"),
                     parts.get("away", {}).get("name"),
                     match.get("matchStart"), outcome_by_event.get(en),
                     int(cancelled_by_event.get(en) or bool(ev.get("cancelled"))),
                     _i(folk.get("one")), _i(folk.get("x")), _i(folk.get("two")),
                     _f(start_odds.get("one")), _f(start_odds.get("x")),
                     _f(start_odds.get("two"))))
            for tier in result.get("distribution") or []:
                name = str(tier.get("name", ""))
                try:
                    correct = int(name.split()[0])
                except (ValueError, IndexError):
                    correct = None
                store.conn.execute(
                    "INSERT INTO pool_payout_tier (product, draw_number, "
                    "tier_name, correct, winners, amount) VALUES (?,?,?,?,?,?)",
                    (product, draw_number, name, correct,
                     _i(tier.get("winners")), _f(tier.get("amount"))))
            _log(store, product, draw_number, OK,
                 f"{len(events)} events, "
                 f"{len(result.get('distribution') or [])} nivåer")
    except Exception as exc:  # noqa: BLE001 — rollback via bulk(); retrybart
        _log(store, product, draw_number, ERROR, f"write: {exc}")
        return ERROR
    return OK


def verify_draw(store: Storage, svs: SvenskaSpel, product: str,
                draw_number: int) -> str:
    """Kontrolläsning mot kanon: omhämta payload och jämför hash. Avvikelse
    loggas som divergence med båda hasharna — kanonraderna rörs aldrig."""
    row = store.conn.execute(
        "SELECT payload_hash FROM pool_draw_settlement "
        "WHERE product=? AND draw_number=?", (product, draw_number)).fetchone()
    if row is None:
        return "not_settled"
    raw = svs.raw_draw(product, draw_number)
    result = svs.raw_result(product, draw_number)
    if raw is None or result is None:
        _log(store, product, draw_number, DIVERGENCE,
             f"kontrolläsning gav 404 (kanon {row[0][:12]}…)")
        return DIVERGENCE
    fresh = payload_hash(raw, result)
    if fresh != row[0]:
        _log(store, product, draw_number, DIVERGENCE,
             f"kanon {row[0][:12]}… ≠ omläst {fresh[:12]}…")
        return DIVERGENCE
    return OK


def latest_status(store: Storage, product: str, draw_number: int) -> Optional[str]:
    row = store.conn.execute(
        "SELECT status FROM pool_backfill_log WHERE product=? AND draw_number=? "
        "ORDER BY attempted_at DESC LIMIT 1", (product, draw_number)).fetchone()
    return row[0] if row else None


def settle_recent(store: Storage, svs: SvenskaSpel, product: str,
                  max_draws: int = 5, min_close_age_h: float = 2.0,
                  retry_after_h: float = 6.0) -> dict:
    """Framåtriktad settlement i snapshot-varvet: settla nyss stängda omgångar
    (kända i lokala draws-tabellen) som saknar settlementrad. Budgeterad och
    tyst — får aldrig fälla varvet."""
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(hours=min_close_age_h)) \
        .strftime("%Y-%m-%dT%H:%M:%S")
    retry_cutoff = (now - dt.timedelta(hours=retry_after_h)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = store.conn.execute(
        "SELECT d.draw_number FROM draws d "
        "LEFT JOIN pool_draw_settlement s "
        "  ON s.product=d.product AND s.draw_number=d.draw_number "
        "WHERE d.product=? AND s.draw_number IS NULL "
        "  AND d.reg_close_time IS NOT NULL AND d.reg_close_time < ? "
        "ORDER BY d.draw_number DESC LIMIT 25", (product, cutoff)).fetchall()
    report = {"tried": 0, "ok": 0, "skipped": 0}
    for (draw_number,) in rows:
        if report["tried"] >= max_draws:
            break
        last = store.conn.execute(
            "SELECT MAX(attempted_at) FROM pool_backfill_log "
            "WHERE product=? AND draw_number=?",
            (product, draw_number)).fetchone()[0]
        if last and last > retry_cutoff:
            report["skipped"] += 1
            continue   # nyligen försökt (t.ex. ej finaliserad än) — vänta
        report["tried"] += 1
        if settle_draw(store, svs, product, draw_number) == OK:
            report["ok"] += 1
    return report
