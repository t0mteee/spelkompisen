"""FastAPI-backend.

Endpoints
---------
GET /api/health
GET /api/draw?product=stryktipset            -> aktuell omgång (rå data)
GET /api/analysis?product=stryktipset        -> analyserad omgång (spik/värde/rörelse)
GET /api/spikar?product=stryktipset          -> matcher sorterade efter spik-score
POST /api/snapshot?product=stryktipset       -> hämta + spara snapshot, returnerar antal rader
GET /api/history?draw=...&event=...&sign=1   -> oddshistorik för ett utfall
"""
from __future__ import annotations

import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config  # noqa: F401 — laddar .env (ODDS_API_KEY) vid import
from .analysis import analyze_draw, analysis_to_dict
from .builder import (build_math_system, build_reduced_system,
                      build_guarantee_system, build_svs_rsystem,
                      SVS_R12, system_to_dict)
from .collector import collector
from . import sharp_service
from .storage import Storage
from .svenskaspel import SvenskaSpel, draw_to_dict, GAME_GROUPS

app = FastAPI(title="Stryktips-hjälpen", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


PRODUCTS_PUBLIC = ["topptipset", "stryktipset", "europatipset"]


def _seed_hint(product: str) -> int | None:
    store = Storage()
    try:
        v = store.meta_get(f"latest_{product}")
        return int(v) if v else None
    finally:
        store.close()


def _store_seed(product: str, draws) -> None:
    nums = [d.draw_number if hasattr(d, "draw_number") else d.get("draw_number")
            for d in draws]
    nums = [n for n in nums if n]
    if not nums:
        return
    store = Storage()
    try:
        prev = store.meta_get(f"latest_{product}")
        newmax = max(nums + ([int(prev)] if prev else []))
        store.meta_set(f"latest_{product}", str(newmax))
    finally:
        store.close()


def _get_draw(product: str, draw_number: int | None = None):
    with SvenskaSpel() as ss:
        if draw_number:
            draw = ss.get_draw(draw_number, product)
        else:
            draw = ss.get_current_draw(product, start_hint=_seed_hint(product))
    if draw is None:
        raise HTTPException(404, f"Ingen öppen omgång för {product}")
    _store_seed(product, [draw])
    return draw


def _analyze(product: str, draw_number: int | None = None):
    """Analysera vald omgång och väv in cachade sharp-odds + rörelse."""
    draw = _get_draw(product, draw_number)
    store = Storage()
    try:
        sharp = store.get_sharp(product, draw.draw_number)
        # rörelse-signalen baseras på Pinnacle (snabbare/sharpare); SS som fallback
        movement = store.sharp_movement(product, draw.draw_number)
        if not movement:
            movement = store.movement(product, draw.draw_number)
    finally:
        store.close()
    return analyze_draw(draw, sharp, movement)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/draws")
def draws(product: str = "stryktipset"):
    """Lista tillgängliga omgångar för spelet/gruppen (för omgångsväljaren).
    Topptipset-gruppen aggregerar flera produkter; varje omgång bär sin egen
    'product' (slug) så efterföljande anrop använder rätt produkt."""
    slugs = GAME_GROUPS.get(product, [product])
    all_draws = []
    with SvenskaSpel() as ss:
        for slug in slugs:
            ds = ss.list_draws(slug, start_hint=_seed_hint(slug))
            _store_seed(slug, ds)
            all_draws.extend(ds)
    all_draws.sort(key=lambda d: d.get("reg_close_time") or "")
    opens = [d for d in all_draws if d["state"] == "Open"]
    return {"product": product, "draws": all_draws, "open": opens}


@app.get("/api/draw")
def draw(product: str = "stryktipset", draw: int | None = None):
    return draw_to_dict(_get_draw(product, draw))


# Svenska Spels officiella vinstplaner: återbetalningsandel + andel per nivå.
# (Validerat mot faktiska utfall.) Topptipset: bara 8 rätt delar potten.
PRIZE_PLANS = {
    "stryktipset":     {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}},
    "europatipset":    {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}},
    "topptipset":      {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetstryk": {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetextra": {"ratio": 0.70, "splits": {8: 1.00}},
}


@app.get("/api/payouts")
def payouts(product: str = "stryktipset", draw: int | None = None):
    """Prispott per vinstnivå beräknad från AKTUELL omsättning och Svenska Spels
    officiella vinstplan. Antal vinnare (och därmed kr/vinnare) räknar frontend
    ut från nuvarande streck. EV blir då rätt — inte baserat på förra omgången."""
    plan = PRIZE_PLANS.get(product)
    if not plan:
        return {"available": False}
    d = _get_draw(product, draw)
    turnover = d.net_sale or 0.0
    row_price = d.row_price or 1.0
    tiers = [{"correct": c, "share": s, "pool": round(turnover * plan["ratio"] * s, 2)}
             for c, s in sorted(plan["splits"].items(), reverse=True)]
    return {"available": turnover > 0, "draw_number": d.draw_number,
            "turnover": turnover, "row_price": row_price, "ratio": plan["ratio"],
            "tiers": tiers}


@app.get("/api/analysis")
def analysis(product: str = "stryktipset", draw: int | None = None):
    return analysis_to_dict(_analyze(product, draw))


@app.get("/api/spikar")
def spikar(product: str = "stryktipset", draw: int | None = None):
    a = _analyze(product, draw)
    return {"draw_number": a.draw_number,
            "spikar": [asdict(m) for m in a.spikar]}


@app.get("/api/system")
def system(product: str = "stryktipset",
           draw: int | None = None,
           strategy: str = Query("medel", pattern="^(säker|medel|tuff)$"),
           budget: float = 100.0,
           reduced: bool = False,
           guarantee: int = 0,
           sv_rsystem: str = ""):
    """sv_rsystem=R 3-3-24 m.fl. ger Svenska Spels eget R-system (12-rätts garanti).
    Annars: reduced=true + guarantee=11/12 ger egen covering-reducering;
    reduced=true ensam ger värde-reducering; default = matematiskt."""
    a = _analyze(product, draw)
    try:
        if sv_rsystem and sv_rsystem in SVS_R12:
            s = build_svs_rsystem(a, sv_rsystem, strategy)
        elif reduced and guarantee:
            s = build_guarantee_system(a, strategy, budget, guarantee=guarantee)
        elif reduced:
            s = build_reduced_system(a, strategy, budget)
        else:
            s = build_math_system(a, strategy, budget)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return system_to_dict(s)


@app.get("/api/rsystems")
def rsystems():
    """Lista Svenska Spels 12-rättsgaranti-R-system."""
    return {"systems": [{"name": k, **v} for k, v in SVS_R12.items()]}


@app.post("/api/snapshot")
def snapshot(product: str = "stryktipset", draw: int | None = None):
    d = _get_draw(product, draw)
    store = Storage()
    try:
        rows = store.save_snapshot(d)
    finally:
        store.close()
    return {"draw_number": d.draw_number, "rows_saved": rows,
            "fetched_at": d.fetched_at}


@app.get("/api/history")
def history(draw: int, event: int, sign: str | None = None,
            product: str = "stryktipset"):
    """Oddshistorik för grafen. Pinnacle (sharp) i första hand — snabbare/sharpare
    rörelse — annars Svenska Spels egna snapshots."""
    store = Storage()
    try:
        sharp = store.sharp_history(product, draw, event)
        if sharp:
            return {"history": sharp, "source": "pinnacle"}
        return {"history": store.history(product, draw, event, sign), "source": "svenskaspel"}
    finally:
        store.close()


# ---- insamlare (start/stopp från UI) ----

# ---- bakgrundsinsamling via launchd (den som körs även när appen är stängd) ----

LAUNCHD_LABEL = "com.saman.svs.snapshot"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def _launchd_loaded() -> bool:
    try:
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        return LAUNCHD_LABEL in r.stdout
    except Exception:  # noqa: BLE001
        return False


@app.get("/api/collection/status")
def collection_status():
    store = Storage()
    try:
        last, count = store.last_snapshot(), store.snapshot_count()
    finally:
        store.close()
    return {"active": _launchd_loaded(), "installed": LAUNCHD_PLIST.exists(),
            "last_snapshot": last, "snapshot_count": count}


@app.post("/api/collection/start")
def collection_start():
    if LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)],
                       capture_output=True, text=True, timeout=10)
    return collection_status()


@app.post("/api/collection/stop")
def collection_stop():
    if LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)],
                       capture_output=True, text=True, timeout=10)
    return collection_status()


@app.get("/api/collector/status")
def collector_status():
    return collector.status()


@app.post("/api/collector/start")
def collector_start(interval: int = 1800, product: str = "stryktipset"):
    return collector.start(interval=interval, product=product)


@app.post("/api/collector/stop")
def collector_stop():
    return collector.stop()


# ---- sharp-odds (Pinnacle, gratis) ----

@app.get("/api/external-odds")
def external_odds(product: str = "stryktipset", draw: int | None = None):
    """Hämtar sharp-odds från Pinnacle (gratis, täcker även landskamper) och
    cachar dem så analysen kan väva in dem. Ger coverage-status per match."""
    draw = _get_draw(product, draw)
    pin_res = sharp_service.collect_pinnacle(product, draw=draw, cache=True)
    hits, status = pin_res["hits"], pin_res["status"]

    out = []
    for m in draw.matches:
        h = hits.get(m.event_number)
        ext_data = None
        st = status.get(m.event_number, "not_listed")
        if h:
            ext_data = {"source": h["source"], "matched": f'{h["home"]} - {h["away"]}',
                        "confidence": h["confidence"], "commence_time": h.get("start"),
                        "bookmaker": h["bookmaker"], "odds": h["odds"],
                        "swapped": h.get("swapped", False)}
        out.append({"event_number": m.event_number, "description": m.description,
                    "ss_has_odds": m.outcomes["1"].odds is not None,
                    "status": st, "external": ext_data})

    return {"enabled": True, "draw_number": draw.draw_number,
            "matched": sum(1 for o in out if o["external"]),
            "cached": len(hits), "matches": out}
