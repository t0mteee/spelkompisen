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

import datetime as dt
import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config  # noqa: F401 — laddar .env (ODDS_API_KEY) vid import
from . import steam as steam_mod
from .analysis import analyze_draw, analysis_to_dict
from .builder import (build_math_system, build_reduced_system,
                      build_guarantee_system, build_svs_rsystem,
                      build_ev_system, build_color_system, SVS_R12, system_to_dict)
from .collector import collector
from . import sharp_service
from .pinnacle import Pinnacle
from .storage import Storage
from .svenskaspel import SvenskaSpel, draw_to_dict, GAME_GROUPS

app = FastAPI(title="SvS kompisen", version="0.1.0")
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
        # oddsrörelse (sharp först) + streck-rörelse + devigat steam-skift,
        # sammanvävt i en dict — samma helper som ntfy-notiserna använder
        merged = steam_mod.movement_with_steam(store, product, draw.draw_number)
    finally:
        store.close()
    return analyze_draw(draw, sharp, merged)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/draws")
def draws(product: str = "stryktipset"):
    """Lista tillgängliga omgångar för spelet/gruppen (för omgångsväljaren).
    Topptipset-gruppen aggregerar flera produkter; varje omgång bär sin egen
    'product' (slug) så efterföljande anrop använder rätt produkt."""
    if product == "bomben":
        with SvenskaSpel() as ss:
            raw = ss.bomben_draws()
        ds = [{"product": "bomben", "draw_number": d["drawNumber"],
               "state": d.get("drawState"), "reg_close_time": d.get("regCloseTime")}
              for d in raw]
        ds.sort(key=lambda d: d.get("reg_close_time") or "")
        return {"product": "bomben", "draws": ds,
                "open": [d for d in ds if d["state"] == "Open"]}
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


@app.get("/api/bomben")
def bomben(draw: int | None = None):
    """Bomben-analys: exakt-resultat-modell (Pinnacle-xg → Poisson) vs folkets
    resultatfördelning. Separat speltyp — inga 1X2-odds från Svenska Spel."""
    from . import bomben as bomben_mod
    with SvenskaSpel() as ss:
        draws = ss.bomben_draws()
    if not draws:
        raise HTTPException(404, "Inga Bomben-omgångar")
    d = next((x for x in draws if x["drawNumber"] == draw), None) if draw \
        else next((x for x in draws if x.get("drawState") == "Open"), draws[0])
    if not d:
        raise HTTPException(404, f"Bomben-omgång {draw} hittades inte")
    try:
        with Pinnacle() as p:
            idx = p.soccer_index(include_without_odds=True)
    except Exception:  # noqa: BLE001 — Pinnacle kan Cloudflare-blockas; folk-only då
        idx = None
    res = bomben_mod.analyze_bomben(d, idx)
    jp = 0.0
    with SvenskaSpel() as ss:
        try:
            jp = ss.get_jackpot("bomben", d["drawNumber"]) or 0.0
        except Exception:  # noqa: BLE001
            jp = 0.0
    res["jackpot"] = jp
    res["sharp_available"] = idx is not None
    return res


# Svenska Spels officiella vinstplaner: återbetalningsandel + andel per nivå.
# (Validerat mot faktiska utfall.) Topptipset: bara 8 rätt delar potten.
PRIZE_PLANS = {
    "stryktipset":     {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}},
    "europatipset":    {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}},
    "topptipset":      {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetstryk": {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetextra": {"ratio": 0.70, "splits": {8: 1.00}},
}


def _projected_turnover(product: str, current: float) -> float | None:
    """Förväntad SLUTomsättning = medianen av de senaste avgjorda omgångarnas
    slutomsättning (cachas 6 h i meta). Tidig låg omsättning ger annars
    glädje-EV: både potter och medvinnare skalar med omsättningen."""
    import json as _json

    store = Storage()
    try:
        key = f"finalturn_{product}"
        cached = store.meta_get(key)
        if cached:
            try:
                c = _json.loads(cached)
                age = (dt.datetime.now(dt.timezone.utc)
                       - dt.datetime.fromisoformat(c["ts"])).total_seconds()
                if age < 6 * 3600 and c.get("median"):
                    return max(current, float(c["median"]))
            except (ValueError, KeyError):
                pass
        vals: list[float] = []
        with SvenskaSpel() as ss:
            ds = ss.list_draws(product, start_hint=_seed_hint(product))
            nr = (min(d["draw_number"] for d in ds) - 1) if ds else None
            tried = 0
            while nr and len(vals) < 6 and tried < 15:
                res = ss.get_result(product, nr)
                tried += 1
                nr -= 1
                if res and res.get("turnover"):
                    vals.append(res["turnover"])
        if not vals:
            return None
        vals.sort()
        median = vals[len(vals) // 2]
        store.meta_set(key, _json.dumps(
            {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "median": median}))
        return max(current, median)
    finally:
        store.close()


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
    # spelvärde = total återbetalning inkl jackpot/rullpott; > ratio => extra bra omgång
    with SvenskaSpel() as ss:
        jackpot = ss.get_jackpot(product, d.draw_number) or d.jackpot or 0.0
    spelvarde = plan["ratio"] + (jackpot / turnover if turnover else 0.0)
    projected = _projected_turnover(product, turnover) or turnover
    spelvarde_proj = plan["ratio"] + (jackpot / projected if projected else 0.0)
    return {"available": turnover > 0, "draw_number": d.draw_number,
            "turnover": turnover, "row_price": row_price, "ratio": plan["ratio"],
            "jackpot": jackpot, "extra_info": d.extra_info,
            "spelvarde": round(spelvarde, 4),
            "projected_turnover": projected,
            "spelvarde_proj": round(spelvarde_proj, 4),
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
           sv_rsystem: str = "",
           ev: bool = False,
           color: bool = False,
           colors: str = "",
           bounds: str = "",
           value_weight: float = 0.5):
    """value_weight 0..1 = EV-/värdeskala: 0 = lågoddsare/favoriter (hög träffchans),
    högre = mer värde/skräll (lägre chans, högre EV). sv_rsystem ger SvS R-system.
    ev=true rankar konkreta rader efter popularitetsjusterad EV (poolspels-optimal)."""
    a = _analyze(product, draw)
    vw = max(0.0, min(1.0, value_weight))
    # EV-rankning/färgval räknar mot förväntad SLUTomsättning (tidig låg
    # omsättning gör annars +1:an i medvinnarformeln dominant = glädje-EV)
    if ev or color:
        proj = _projected_turnover(product, a.turnover or 0.0)
        if proj and proj > (a.turnover or 0.0):
            a.turnover = proj
    try:
        if sv_rsystem and sv_rsystem in SVS_R12:
            s = build_svs_rsystem(a, sv_rsystem, strategy, value_weight=vw)
        elif ev:
            s = build_ev_system(a, strategy, budget, row_price=a.row_price or 1.0,
                                value_weight=vw, plan=PRIZE_PLANS.get(product))
        elif color:
            # manuella overrides: colors="1:X:b,5:2:g" (b=blå, g=gul), bounds="0-2,0-1"
            co = None
            if colors:
                co = {}
                for part in colors.split(","):
                    bits = part.split(":")
                    if len(bits) == 3 and bits[1] in ("1", "X", "2") and bits[2] in ("b", "g"):
                        try:
                            co[(int(bits[0]), bits[1])] = "blå" if bits[2] == "b" else "gul"
                        except ValueError:
                            pass
            bo = None
            if bounds:
                try:
                    b, g = bounds.split(",")
                    blo, bhi = (int(x) for x in b.split("-"))
                    glo, ghi = (int(x) for x in g.split("-"))
                    bo = (blo, bhi, glo, ghi)
                except ValueError:
                    bo = None
            s = build_color_system(a, strategy, budget, row_price=a.row_price or 1.0,
                                   value_weight=vw, plan=PRIZE_PLANS.get(product),
                                   colors_override=co, bounds_override=bo)
        elif reduced and guarantee:
            s = build_guarantee_system(a, strategy, budget, guarantee=guarantee, value_weight=vw)
        elif reduced:
            s = build_reduced_system(a, strategy, budget, value_weight=vw)
        else:
            s = build_math_system(a, strategy, budget, value_weight=vw)
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


@app.get("/api/movement")
def movement(product: str = "stryktipset", draw: int | None = None):
    """Hela oddsserien (SvS + Pinnacle) per utfall för rörelse-tooltipen.
    Slår inte mot SvS-API:t när draw anges — läser bara våra snapshots."""
    dn = draw or _get_draw(product, None).draw_number
    store = Storage()
    try:
        ser = store.odds_series(product, dn)
    finally:
        store.close()
    events: dict[str, dict] = {}
    for (ev, sign), data in ser.items():
        events.setdefault(str(ev), {})[sign] = data
    return {"draw_number": dn, "events": events}


@app.get("/api/steam")
def steam(product: str = "stryktipset", draw: int | None = None):
    """Devigade sannolikhetsskift per tecken (6/24/72 h) — 'steam' = marknaden
    flyttar sig på riktigt, jämförbart mellan favoriter och skrällar."""
    dn = draw or _get_draw(product, None).draw_number
    store = Storage()
    try:
        rows = steam_mod.steam_table(store, product, dn)
    finally:
        store.close()
    return {"draw_number": dn, "rows": rows}


@app.get("/api/clv")
def clv_facit(product: str | None = None):
    """Signal-facit: flaggade värdetecken vs devigad Pinnacle-stängning (CLV)
    + träffprocent mot facit. Positiv snitt-CLV = signalerna är äkta."""
    from . import clv as clv_mod
    store = Storage()
    try:
        clv_mod.resolve(store)        # sätt stängningar som hunnit passera (lokalt, billigt)
        slugs = GAME_GROUPS.get(product, [product]) if product else [None]
        if len(slugs) == 1:
            return clv_mod.report(store, slugs[0])
        # gruppflik (topptipset) = slå ihop varianterna
        rows = []
        for s in slugs:
            rows.extend(store.clv_rows(s))
        rows.sort(key=lambda r: r["first_at"] or "", reverse=True)
        scored = [r for r in rows if r["closing_prob"] is not None and r["first_prob"]]
        for r in scored:
            r["clv_pp"] = round((r["closing_prob"] - r["first_prob"]) * 100, 2)
        beat = [r for r in scored if r["clv_pp"] > 0]
        judged = [r for r in rows if r["outcome"] is not None]
        return {"n_flagged": len(rows), "n_scored": len(scored),
                "beat_pct": round(len(beat) / len(scored), 3) if scored else None,
                "avg_clv_pp": round(sum(r["clv_pp"] for r in scored) / len(scored), 2) if scored else None,
                "n_judged": len(judged),
                "hit_pct": round(sum(r["outcome"] for r in judged) / len(judged), 3) if judged else None,
                "avg_streck": None, "rows": rows[:120]}
    finally:
        store.close()


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
