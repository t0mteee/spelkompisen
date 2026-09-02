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
# Skrivs i `pool_draw_settlement.draw_state` för en INSTÄLLD omgång. SvS egen
# `drawState` säger "Finalized" även då, så flaggan måste komma från resultatet.
CANCELLED_STATE = "Cancelled"
NOT_FINALIZED = "not_finalized"
HTTP_404 = "http_404"
INCOMPLETE = "incomplete_result"
DIVERGENCE = "divergence"
ERROR = "error"


# OMPRÖVNINGSPOLICY (2026-08-08). Den fasta 6-timmarsbackoffen mättes upp som
# HELA fördröjningen: av 30 observerade not_finalized→ok-övergångar tog 100 %
# mer än 5,5 h och medianen var 6,21 h — alltså backoffen på pricken, inte
# SvS. Två fel samverkade. Ett försök gjordes ofta INNAN matcherna var
# färdigspelade (en spelad kupong är kandidat från den sekund den bokförs),
# och det försöket startade en klocka som blockerade just det försök som hade
# lyckats. Nu bär varje loggrad sin EGEN tidigaste omprövning, härledd ur
# draw-payloaden vi ändå har i handen.
RETRY_SOON_MIN = 15        # matcherna spelade — vi väntar bara på publicering
RETRY_MAX_H = 6.0          # tak, så en omgång som aldrig finaliseras får ro
MATCH_DURATION_MIN = 130   # avspark → slutsignal med marginal för tillägg


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value) -> Optional[dt.datetime]:
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.timezone.utc)


def jackpot_at_close(store: Storage, product: str, draw_number: int,
                     close_iso: Optional[str]) -> tuple[Optional[float],
                                                        Optional[str]]:
    """Senast VERIFIERADE jackpotobservation vid eller före spelstopp.

    Resultatpayloaden bär ingen jackpot och `/jackpots` listar bara öppna
    omgångar, så det enda ärliga värdet är vad vi själva observerade i
    `pool_draw_snapshot` innan stängning — och bara med proveniensen
    `verified_endpoint`. `draw.fund` är opålitligt och räknas aldrig.
    Returnerar (NULL, NULL) när ingen sådan observation finns; NULL betyder
    oobserverad, aldrig "ingen jackpot".
    """
    close = _parse_iso(close_iso)
    if close is None:
        return None, None
    cutoff = close.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = store.conn.execute(
        "SELECT jackpot, fetched_at FROM pool_draw_snapshot WHERE product=? "
        "AND draw_number=? AND jackpot_source='verified_endpoint' "
        "AND jackpot IS NOT NULL AND fetched_at<=? "
        "ORDER BY fetched_at DESC LIMIT 1",
        (product, draw_number, cutoff)).fetchone()
    if row is None:
        return None, None
    return float(row[0]), str(row[1])


def _retry_after(raw: Optional[dict], now: Optional[dt.datetime] = None) -> str:
    """Tidigaste meningsfulla omprövning av en omgång som inte var finaliserad.

    En omgång vars matcher fortfarande rullar KAN inte ha en utdelning; att
    fråga igen om tio minuter är rent slöseri. En omgång där alla matcher är
    spelade väntar bara på att SvS publicerar, och då är rätt kadens minuter.
    Skillnaden läses ur payloaden — inget extra anrop, ingen gissning.
    """
    from .pool_played import match_finished, match_postponed
    now = now or dt.datetime.now(dt.timezone.utc)
    soon = now + dt.timedelta(minutes=RETRY_SOON_MIN)
    latest_end = None
    for ev in ((raw or {}).get("drawEvents") or []):
        match = ev.get("match") or {}
        # En uppskjuten match blir aldrig "färdigspelad" och dess `matchStart`
        # kan flyttas veckor framåt. Att vänta på den skulle skjuta omprövningen
        # långt bortom den punkt där SvS stryker matchen och finaliserar
        # omgången — de övriga matcherna avgör när det sker.
        if match_finished(match) or ev.get("cancelled") or match_postponed(match):
            continue
        start = _parse_iso(match.get("matchStart"))
        if start is None:
            continue           # okänd avspark: låt `soon` gälla, aldrig längre
        end = start + dt.timedelta(minutes=MATCH_DURATION_MIN)
        latest_end = end if latest_end is None else max(latest_end, end)
    when = max(soon, latest_end) if latest_end else soon
    # `matchStart` bär normalt svensk offset (+01/+02). `strftime(...Z)`
    # ändrar bara TEXTEN, inte tidszonen: utan konverteringen nedan blev
    # 21:25+02 felaktigt 21:25Z i stället för 19:25Z och settlement väntade
    # exakt två extra timmar under sommartid (Europatipset 2597).
    return min(when, now + dt.timedelta(hours=RETRY_MAX_H)) \
        .astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
         detail: Optional[str] = None, retry_after: Optional[str] = None) -> None:
    store.conn.execute(
        "INSERT OR REPLACE INTO pool_backfill_log "
        "(product, draw_number, attempted_at, status, detail, retry_after) "
        "VALUES (?,?,?,?,?,?)",
        (product, draw_number, _now_iso(), status, detail, retry_after))
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
    soon = _retry_after(None)      # transportfel säger inget om omgången
    try:
        raw = svs.raw_draw(product, draw_number)
    except Exception as exc:  # noqa: BLE001 — transportfel är retrybart
        _log(store, product, draw_number, ERROR, f"draw: {exc}", soon)
        return ERROR
    if raw is None:
        # Omgången finns inte hos SvS — den fasta backoffen är rätt här.
        _log(store, product, draw_number, HTTP_404, "draw 404")
        return HTTP_404
    state = raw.get("drawState") or ""
    if state != "Finalized":
        from .pool_played import match_finished
        events = raw.get("drawEvents") or []
        left = sum(1 for ev in events
                   if not (match_finished(ev.get("match") or {})
                           or ev.get("cancelled")))
        _log(store, product, draw_number, NOT_FINALIZED,
             f"state={state}, {left}/{len(events)} matcher kvar",
             _retry_after(raw))
        return NOT_FINALIZED
    try:
        result = svs.raw_result(product, draw_number)
    except Exception as exc:  # noqa: BLE001
        _log(store, product, draw_number, ERROR, f"result: {exc}", soon)
        return ERROR
    if result is None or not _tiers_complete(result):
        # Omgången ÄR finaliserad; utdelningen håller på att publiceras just nu.
        _log(store, product, draw_number, INCOMPLETE,
             "result saknas" if result is None else "distribution ofullständig",
             soon)
        return INCOMPLETE

    version = source_version or _git_hash()
    events = raw.get("drawEvents") or []
    # INSTÄLLD OMGÅNG (uppmätt 2026-08-12 på Topptipset 4259 m.fl.): SvS sätter
    # `cancelled: true` på RESULTATET, lämnar varje event utan utfall och
    # publicerar en distribution med noll vinnare och 0,00 kr. Omgångens egen
    # `drawState` står kvar på "Finalized", så utan den här flaggan lagras en
    # inställd omgång som en vanlig avgjord omgång vars åtta utfall råkar
    # saknas — och systemledgern dömer den som "utfall saknas för minst en
    # match" i stället för "spelades aldrig". Uppmätt 56 av 8 324 omgångar.
    draw_cancelled = bool(result.get("cancelled"))
    state = CANCELLED_STATE if draw_cancelled else state
    outcome_by_event = {}
    cancelled_by_event = {}
    for ev in (result.get("events") or []):
        en = ev.get("eventNumber")
        if ev.get("outcome") in ("1", "X", "2"):
            outcome_by_event[en] = ev["outcome"]
        cancelled_by_event[en] = bool(ev.get("cancelled"))
    jackpot_close, jackpot_seen = jackpot_at_close(
        store, product, draw_number, raw.get("regCloseTime"))
    try:
        with store.bulk():
            n_cancelled = sum(1 for v in cancelled_by_event.values() if v)
            store.conn.execute(
                "INSERT INTO pool_draw_settlement (product, draw_number, "
                "draw_state, reg_close_time, net_sale, row_price, n_events, "
                "n_cancelled, product_name, source_version, payload_hash, "
                "fetched_at, jackpot_close, jackpot_close_observed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw_number, state, raw.get("regCloseTime"),
                 _f(result.get("currentNetSale")) or _f(raw.get("currentNetSale")),
                 _f(raw.get("rowPrice")), len(events), n_cancelled,
                 raw.get("productName"), version,
                 payload_hash(raw, result), _now_iso(),
                 jackpot_close, jackpot_seen))
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
    tyst — får aldrig fälla varvet.

    `retry_after_h` är numera bara FALLBACK för loggrader utan egen
    omprövningstid (historik och 404). Nya rader bär sin egen — se
    `_retry_after`.
    """
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(hours=min_close_age_h)) \
        .strftime("%Y-%m-%dT%H:%M:%S")
    retry_cutoff = (now - dt.timedelta(hours=retry_after_h)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    # Kandidater ur den lokala draws-tabellen (stängda för > min_close_age_h)
    # UNION omgångar vi faktiskt SPELAT på.
    #
    # Andra ledet behövs för att Topptipset saknar listnings-API: omgångarna
    # hittas genom nummerscanning, så `draws` fylls opportunistiskt och
    # slutade 2026-08-08 på 4248 medan Saman hade en spelad kupong på 4251.
    # Joinen mot draws hittade då ingenting att settla, och kupongen låg kvar
    # utan facit trots att utdelningen var publicerad (8 rätt, 658 vinnare).
    # En spelad kupong är det starkaste beviset som finns på att omgången
    # angår oss — den behöver ingen reg_close_time för att kvalificera, och
    # `settle_draw` avvisar ändå en omgång som inte är finaliserad.
    rows = store.conn.execute(
        "SELECT draw_number FROM ("
        "  SELECT d.draw_number AS draw_number FROM draws d "
        "  LEFT JOIN pool_draw_settlement s "
        "    ON s.product=d.product AND s.draw_number=d.draw_number "
        "  WHERE d.product=? AND s.draw_number IS NULL "
        "    AND d.reg_close_time IS NOT NULL AND d.reg_close_time < ? "
        "  UNION "
        "  SELECT c.draw_number FROM pool_played_coupon c "
        "  LEFT JOIN pool_draw_settlement s "
        "    ON s.product=c.product AND s.draw_number=c.draw_number "
        "  WHERE c.product=? AND s.draw_number IS NULL"
        ") ORDER BY draw_number DESC LIMIT 25",
        (product, cutoff, product)).fetchall()
    now_iso = _now_iso()
    report = {"tried": 0, "ok": 0, "skipped": 0}
    for (draw_number,) in rows:
        if report["tried"] >= max_draws:
            break
        last = store.conn.execute(
            "SELECT attempted_at, retry_after FROM pool_backfill_log "
            "WHERE product=? AND draw_number=? "
            "ORDER BY attempted_at DESC LIMIT 1",
            (product, draw_number)).fetchone()
        if last:
            attempted_at, retry_after = last[0], last[1]
            # Radens egen omprövningstid vinner alltid: den vet om matcherna
            # rullade eller om vi bara väntade på publicering.
            if retry_after:
                if retry_after > now_iso:
                    report["skipped"] += 1
                    continue
            elif attempted_at and attempted_at > retry_cutoff:
                report["skipped"] += 1
                continue
        report["tried"] += 1
        if settle_draw(store, svs, product, draw_number) == OK:
            report["ok"] += 1
    return report
