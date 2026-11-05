"""Big 9 (ATG) i appen: omgångslista, matchvy och systembyggaren.

Beslut 2026-11-04-big9-i-byggaren (val 0): Big 9 syns under Poolspel med
omgångarna, matcherna med ATG:s odds och folkets streck för de sex cellerna
(1X2 × Över/Under 2,5) och byggaren med strategi och budget. Raderna lämnas
som text eller kupongbild — ATG:s radfilsformat är inte verifierat, så Saman
lägger in raderna själv på atg.se/sport/big9. Inga spel läggs härifrån.

Allt läses ur ATG-insamlingens append-only-tabeller (`app/atg.py`); modulen
hämtar aldrig själv. Underlaget är facitsidans paket
(`spelai.big9.build_payload` utan horisont) och byggaren är
`big9_builder.build_rows` via `spelai.big9.round_from_payload` — samma väg som
standarden, aldrig en parallell byggare. Strategi medel med 256 kr (och
512 kr från SP96 554) är standardens inställning; säker är värdevikt 0,2 som PH3:s `dr1-*-saker`.

Beslut 2026-11-04-big9-fullt-system (val 0): ATG tar bara fulla system
("Spela enskilda utfall"), så byggaren är `big9_builder.build_full_system`
och svaret bär cellmängden per match (`cells`) — kupongen att markera hos
ATG. Raderna är hela korsprodukten. BIG9 med Wild Card byggs inte.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from . import atg, big9_builder
from .spelai import big9 as spelai_big9, nivaer

ATG_URL = "https://www.atg.se/sport/big9"
STRATEGY_VALUE_WEIGHT = {"säker": 0.2, "medel": 0.5}
BUDGETS = (16, 32, 64, 128, 256, 512, 1024)
DEFAULT_BUDGET = 256
DEFAULT_STRATEGY = "medel"
RECENT_CLOSED = 6
CELL_KEYS = {"1O": ("home", "over"), "1U": ("home", "under"),
             "XO": ("tie", "over"), "XU": ("tie", "under"),
             "2O": ("away", "over"), "2U": ("away", "under")}


class Stangd(ValueError):
    """Omgången går inte längre att spela (spelstopp passerat eller ej öppen)."""


def _iso(t: Optional[dt.datetime]) -> Optional[str]:
    return atg.iso(t) if t else None


def is_open(status: str, close: Optional[dt.datetime], now: dt.datetime) -> bool:
    return status == atg.OPEN and close is not None and close > now


def rounds(conn, *, now: dt.datetime) -> dict:
    """Öppna omgångar (närmast spelstopp först) och de senaste stängda."""
    if not atg.tables_exist(conn):
        return {"available": False, "open": [], "recent": [], "atg_url": ATG_URL,
                "note": "atg-tabellerna saknas — kör scripts/migrera_atg.py"}
    open_, closed = [], []
    for r in atg.latest_rounds(conn):
        record = r["record"]
        pool = record.get("pool") or {}
        item = {"product": r["product"], "name": atg.namn(r["product"]),
                "serial": r["serial"], "title": record.get("name"),
                "status": r["status"], "close": _iso(r["start"]),
                "observed_at": _iso(r["observed_at"]),
                "turnover_kr": float(pool.get("turnover") or 0) / 100.0,
                "jackpot_kr": float(pool.get("jackpotAmount") or 0) / 100.0,
                "measured": r["product"] in atg.MEASURED,
                "open": is_open(r["status"], r["start"], now)}
        (open_ if item["open"] else closed).append(item)
    open_.sort(key=lambda i: (i["close"] or "", i["product"]))
    closed.sort(key=lambda i: (i["close"] or ""), reverse=True)
    return {"available": True, "open": open_, "recent": closed[:RECENT_CLOSED],
            "atg_url": ATG_URL, "budgets": list(BUDGETS),
            "strategies": list(STRATEGY_VALUE_WEIGHT),
            "default": {"budget": DEFAULT_BUDGET, "strategy": DEFAULT_STRATEGY}}


def _outcome(raw: dict) -> Optional[str]:
    if raw.get("canceledAt") or raw.get("status") == "CANCELED":
        return "*"
    if raw.get("status") != "DECIDED":
        return None
    result = raw.get("result") or {}
    sign = big9_builder.WINNER_SIGN.get(result.get("winner"))
    goal = big9_builder.GOALS_SIGN.get(result.get("goals"))
    return sign + goal if sign and goal else None


def _streck_pct(streck) -> Optional[dict]:
    if not isinstance(streck, dict):
        return None
    out = {}
    for cell, (winner, goals) in CELL_KEYS.items():
        value = (streck.get(winner) or {}).get(goals)
        if not isinstance(value, (int, float)):
            return None
        out[cell] = float(value)
    return out


def _match_view(m: dict, raw: dict, limit: float) -> dict:
    p = big9_builder.cell_probabilities(m.get("odds"), limit)
    q = big9_builder.folk_distribution(m.get("streck"))
    cells = []
    for cell in big9_builder.CELLS:
        prob = p.get(cell) if p else None
        folk = q.get(cell) if q else None
        cells.append({"cell": cell,
                      "p": round(prob, 5) if prob is not None else None,
                      "q": round(folk, 5) if folk is not None else None,
                      "value": (round(prob / folk, 3)
                                if prob is not None and folk else None)})
    return {"event_number": m["event_number"], "home": m.get("home"),
            "away": m.get("away"), "league": m.get("league"), "start": m.get("start"),
            "status": m.get("status"), "cancelled": m.get("cancelled"),
            "odds": m.get("odds"), "odds_updated": m.get("odds_updated"),
            "streck": _streck_pct(m.get("streck")),
            "p_source": "odds" if p else ("streck" if q else None),
            "cells": cells, "outcome": _outcome(raw)}


def round_view(conn, product: str, serial: int, *, now: dt.datetime) -> Optional[dict]:
    if product not in atg.PRODUCTS or not atg.tables_exist(conn):
        return None
    obs = atg.latest_observation(conn, product, serial)
    if obs is None:
        return None
    payload = spelai_big9.build_payload(conn, product, obs, None, now)
    omgang = payload["omgang"]
    limit = float(omgang.get("ou_grans") or 2.5)
    raw = {int(m.get("number")): m for m in obs["record"].get("matches") or []}
    cfg = atg.PRODUCTS[product]
    return {
        "product": product, "name": cfg["name"], "serial": int(serial),
        "title": omgang.get("namn"), "status": obs["status"],
        "open": is_open(obs["status"], obs["start"], now),
        "close": payload["reg_close_time"], "observed_at": payload["observed_at"],
        "measured": product in atg.MEASURED, "atg_url": ATG_URL,
        "wildcard": cfg["wildcard"], "row_price": cfg["row_price"],
        "ou_limit": limit,
        "splits": {str(k): v for k, v in cfg["splits"].items()},
        "payout_ratio": omgang["aterbetalning"],
        "pool": omgang["pool"], "turnover": payload["turnover"],
        "jackpot": payload["jackpot"],
        "matches": [_match_view(m, raw.get(m["event_number"], {}), limit)
                    for m in omgang["matches"]],
    }


def build_system(conn, product: str, serial: int, *, budget: int, strategy: str,
                 now: dt.datetime) -> dict:
    """Bygg ett fullt system för en öppen omgång. Kastar LookupError (okänd omgång),
    Stangd (inte spelbar) eller ValueError (ogiltigt val/underlag)."""
    if product not in atg.PRODUCTS:
        raise LookupError(f"okänd produkt {product!r}")
    if int(budget) not in BUDGETS:
        raise ValueError(f"budgeten {budget} kr finns inte "
                         f"(tillåtna: {', '.join(map(str, BUDGETS))})")
    if strategy not in STRATEGY_VALUE_WEIGHT:
        raise ValueError(f"okänd strategi {strategy!r}")
    if atg.PRODUCTS[product]["wildcard"]:
        raise ValueError(f"{atg.namn(product)} har Wild Card — byggaren gör bara "
                         "fulla system för Big 9 utan Wild Card")
    if not atg.tables_exist(conn):
        raise LookupError("atg-tabellerna saknas")
    obs = atg.latest_observation(conn, product, serial)
    if obs is None:
        raise LookupError(f"omgång {serial} finns inte")
    if not is_open(obs["status"], obs["start"], now):
        raise Stangd(f"omgång {serial} är inte öppen ({obs['status']})")
    payload = spelai_big9.build_payload(conn, product, obs, None, now)
    rnd = spelai_big9.round_from_payload(payload)
    value_weight = STRATEGY_VALUE_WEIGHT[strategy]
    system = big9_builder.build_full_system(rnd, float(budget),
                                            value_weight=value_weight)
    coverage = [{c: 0 for c in big9_builder.CELLS} for _ in rnd.matches]
    for text in system.rows:
        for i, token in enumerate(text.split()):
            coverage[i][token] += 1
    matches = payload["omgang"]["matches"]
    standard_key = spelai_big9.standard_key(product, budget, serial)
    return {
        "product": product, "serial": int(serial), "budget": int(budget),
        "strategy": strategy, "value_weight": value_weight,
        "version": big9_builder.SYSTEM_VERSION,
        "cells": system.cells,
        "form": "·".join(str(len(c)) for c in system.cells),
        "rows": system.rows, "n_rows": system.n_rows, "cost": system.cost,
        "ev_total": round(system.ev_total, 2), "note": system.note,
        "row_price": rnd.row_price, "turnover_used": rnd.turnover,
        "events_order": [m["event_number"] for m in matches],
        "matches": [{"event_number": m["event_number"], "home": m.get("home"),
                     "away": m.get("away")} for m in matches],
        "coverage": coverage, "observed_at": payload["observed_at"],
        "close": payload["reg_close_time"], "atg_url": ATG_URL,
        # bara när omgångens standard är ett fullt system är appens bygge standarden
        "standard_key": (standard_key if strategy == DEFAULT_STRATEGY
                         and product in atg.MEASURED
                         and nivaer.fullt_system(product, serial) else None),
    }
