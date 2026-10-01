"""Indatapaketet: poolvarvets färska underlag, fruset när en horisont är due.

Databasen sparar inte omgångens Draw-payload (`snapshots` är en
förändringsserie och `pool_draw_snapshot` bär bara omsättning/jackpot). PH3
bygger därför ur poolvarvets FÄRSKA Draw. Facitsidan gör samma sak: bredvid
`freeze_due` i `cli.py pool-tick` sparas ETT paket per (produkt, omgång,
horisont) i `spelai_input` — draw (tur-och-retur via to/from_payload), sharp
efter pool-sharp-freshness-v1, movement, värderingsomsättningen enligt
`_valuation_turnover` och jackpot. Billigt: inga byggen och inga subprocesser
i poolvarvet. `spelai-tick` bygger standarden och anropar agenten ur paketet.

Fönster (observationstiden = när draw hämtades, observationstidsregeln):
* `6h`  — [T−6h, T−5h30]: första tick där draw observerats inom fönstret.
          Basvarvet går var 30:e minut, därav 30 minuters tolerans.
* `30m` — [T−35m, T−30m]: inom 2 h före stopp tickar poolvarvet var 5:e
          minut, så fönstret träffas.
Utan paket i fönstret ⇒ `missat` (frysning.mark_missed). Missat bakfylls aldrig.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from typing import Optional

from ..svenskaspel import Draw, Match, Outcome
from . import nivaer, schema
from .tillstand import iso, utc

SCHEMA_VERSION = "spelai-indata-v1"
# horisont → (fönstrets start, fönstrets slut) i minuter före spelstopp
WINDOWS = {"6h": (360, 330), "30m": (35, 30)}
# Längsta tid från observation till frysning. 30m-regeln: paketet måste ha
# observerats i [T−35, T−30] OCH frysas inom 5 min efter observationen.
FREEZE_MAX_MIN = {"6h": 30, "30m": 5}
HORIZONS = tuple(WINDOWS)


def window(close: dt.datetime, horizon: str) -> tuple[dt.datetime, dt.datetime]:
    start_min, end_min = WINDOWS[horizon]
    return (close - dt.timedelta(minutes=start_min),
            close - dt.timedelta(minutes=end_min))


# ── tur och retur ────────────────────────────────────────────────────────

def draw_to_payload(draw: Draw) -> dict:
    return dataclasses.asdict(draw)


def draw_from_payload(data: dict) -> Draw:
    matches = []
    for m in data.get("matches") or []:
        outcomes = {sign: Outcome(**o) for sign, o in (m.get("outcomes") or {}).items()}
        fields = {k: v for k, v in m.items() if k != "outcomes"}
        matches.append(Match(**fields, outcomes=outcomes))
    fields = {k: v for k, v in data.items() if k != "matches"}
    return Draw(**fields, matches=matches)


def encode_sharp(sharp: Optional[dict]) -> dict:
    return {str(event): value for event, value in (sharp or {}).items()}


def decode_sharp(data: Optional[dict]) -> dict:
    return {int(event): value for event, value in (data or {}).items()}


def encode_movement(movement: Optional[dict]) -> list:
    return [[int(event), sign, value]
            for (event, sign), value in sorted((movement or {}).items())]


def decode_movement(data: Optional[list]) -> dict:
    return {(int(event), sign): value for event, sign, value in (data or [])}


def payload_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _latest_sharp_observation(store, product: str, draw_number: int,
                              at: dt.datetime) -> Optional[str]:
    """Senaste Pinnacle-OBSERVATION (presence/förändring) ≤ at, som tid."""
    best: Optional[dt.datetime] = None
    try:
        values = store.sharp_latest_observations(product, draw_number).values()
    except Exception:  # noqa: BLE001 — underlagstid är dokumentation, inte grind
        return None
    for raw in values:
        t = utc(raw)
        if t is not None and t <= at and (best is None or t > best):
            best = t
    return iso(best) if best else None


def build_payload(store, product: str, draw: Draw, horizon: str,
                  sharp: Optional[dict], movement: Optional[dict],
                  jackpot: Optional[float], jackpot_source: str,
                  sharp_stale: Optional[dict], now: dt.datetime) -> dict:
    from .. import pool_system_ledger
    close = utc(draw.reg_close_time)
    observed = utc(draw.fetched_at)
    live = float(draw.net_sale or 0.0)
    used, basis = pool_system_ledger._valuation_turnover(  # noqa: SLF001
        store, product, live, close_iso=close.isoformat())
    start, end = window(close, horizon)
    return {
        "schema": SCHEMA_VERSION,
        "product": product,
        "draw_number": int(draw.draw_number),
        "horizon": horizon,
        "observed_at": iso(observed),
        "captured_at": iso(now),
        "reg_close_time": iso(close),
        "window": {"start": iso(start), "end": iso(end)},
        "nivaer": list(nivaer.nivaer_for(product)),
        "n_matches": len(draw.matches),
        "events_order": [m.event_number for m in draw.matches],
        "draw": draw_to_payload(draw),
        "sharp": encode_sharp(sharp),
        "sharp_stale_events": sorted(int(e) for e in (sharp_stale or {})),
        "movement": encode_movement(movement),
        "turnover": {"live": live, "used": used, "basis": basis},
        "jackpot": {"value": jackpot, "source": jackpot_source},
        "underlag_tider": {
            # odds, streck och omsättning kommer ur SAMMA draw-läsning
            "svs": iso(observed),
            "omsattning": iso(observed),
            "sharp": _latest_sharp_observation(store, product, draw.draw_number, now),
        },
    }


def capture_due(store, product: str, draw: Draw, sharp: Optional[dict] = None,
                movement: Optional[dict] = None, jackpot: Optional[float] = None,
                jackpot_source: str = "missing",
                now: Optional[dt.datetime] = None,
                sharp_stale: Optional[dict] = None) -> dict:
    """Spara indatapaket för de horisonter vars fönster draw observerades i.

    Anropas i poolvarvet direkt efter PH3:s underlag. Får aldrig fälla
    varvet: saknas tabellerna (migreringen inte körd) händer ingenting."""
    report = {"captured": [], "skipped": None}
    if not nivaer.nivaer_for(product):
        report["skipped"] = "produkten ingår inte"
        return report
    if not schema.tables_exist(store.conn, ("spelai_input",)):
        report["skipped"] = "spelai-tabellerna saknas"
        return report
    now = now or dt.datetime.now(dt.timezone.utc)
    close = utc(draw.reg_close_time)
    observed = utc(draw.fetched_at)
    if close is None or observed is None or observed >= close:
        report["skipped"] = "ingen giltig stopp- eller observationstid"
        return report
    for horizon in HORIZONS:
        start, end = window(close, horizon)
        if not (start <= observed <= end):
            continue
        if store.conn.execute(
                "SELECT 1 FROM spelai_input WHERE product=? AND draw_number=? "
                "AND horizon=?", (product, draw.draw_number, horizon)).fetchone():
            continue
        payload = build_payload(store, product, draw, horizon, sharp, movement,
                                jackpot, jackpot_source, sharp_stale, now)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        cur = store.conn.execute(
            "INSERT OR IGNORE INTO spelai_input (product, draw_number, horizon, "
            "observed_at, captured_at, reg_close_time, schema_version, "
            "payload_json, payload_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (product, int(draw.draw_number), horizon, payload["observed_at"],
             payload["captured_at"], payload["reg_close_time"], SCHEMA_VERSION,
             text, payload_hash(text)))
        if not getattr(store, "_bulk", False):
            store.conn.commit()
        if cur.rowcount == 1:
            report["captured"].append(horizon)
    return report
