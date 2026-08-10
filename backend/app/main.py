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
import math
import statistics
import subprocess
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import config  # noqa: F401 — laddar .env (ODDS_API_KEY) vid import
from . import steam as steam_mod
from .analysis import analyze_draw, analysis_to_dict
from .builder import (build_math_system, build_reduced_system,
                      build_guarantee_system, build_svs_rsystem,
                      build_ev_system, build_color_system, SVS_R12,
                      kappa_for, system_to_dict)
from .collector import collector
from .pool_mc import materialize_system_rows, simulate_pool_portfolio
from . import sharp_service
from .pinnacle import Pinnacle
from .storage import Storage
from .svenskaspel import SvenskaSpel, draw_to_dict, GAME_GROUPS, PRODUCTS

app = FastAPI(title="Spelkompisen", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    allow_methods=["*"],
    allow_headers=["*"],
)


PRODUCTS_PUBLIC = ["topptipset", "stryktipset", "europatipset"]


# Scanhintet ägs av Storage sedan 2026-08-09 — insamlingsvarvet behöver exakt
# samma hint som API:t, och två kopior gled isär i fem dygn utan att någon
# märkte det. Se `Storage.seed_hint`.
def _seed_hint(product: str) -> int | None:
    store = Storage()
    try:
        return store.seed_hint(product)
    finally:
        store.close()


def _store_seed(product: str, draws) -> None:
    store = Storage()
    try:
        store.store_seed(product, draws)
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
    # HTTP-processen kan vara frisk samtidigt som en hel poolprodukt slutat
    # samlas. Returnera därför även den rent lokala änd-till-änd-kontrollen.
    from . import pool_health
    store = Storage()
    try:
        pools = pool_health.report(store)
        return {"status": "ok" if pools["status"] == "ok" else "degraded",
                "pools": pools}
    finally:
        store.close()


# Omgångslistningen live-scannar SvS-API:t (topptipsgruppen = nummerscanning
# × 3 slugs ≈ 40-55 requests). v3-dashboarden pollar var 2:e min — utan cache
# blev det 1 500+ upstream-requests/timme från en öppen flik, mer än hela
# launchd-insamlingen. Listan ändras på minutskala aldrig (nya omgångar dyker
# upp dagligen, stopptider är fasta) — 5 min TTL är säkert och artigt.
DRAWS_CACHE_TTL_S = 300


def _draws_cached(product: str):
    import json as _json
    store = Storage()
    try:
        raw = store.meta_get(f"draws_cache:{product}")
        if not raw:
            return None
        obj = _json.loads(raw)
        at = dt.datetime.fromisoformat(obj["at"])
        age = (dt.datetime.now(dt.timezone.utc) - at).total_seconds()
        return obj["payload"] if 0 <= age < DRAWS_CACHE_TTL_S else None
    except Exception:  # noqa: BLE001 — trasig cache = hämta live
        return None
    finally:
        store.close()


def _draws_cache_put(product: str, payload: dict) -> None:
    import json as _json
    store = Storage()
    try:
        store.meta_set(f"draws_cache:{product}", _json.dumps(
            {"at": dt.datetime.now(dt.timezone.utc).isoformat(),
             "payload": payload}))
    except Exception:  # noqa: BLE001 — cachefel får inte fälla svaret
        pass
    finally:
        store.close()


@app.get("/api/draws")
def draws(product: str = "stryktipset"):
    """Lista tillgängliga omgångar för spelet/gruppen (för omgångsväljaren).
    Topptipset-gruppen aggregerar flera produkter; varje omgång bär sin egen
    'product' (slug) så efterföljande anrop använder rätt produkt.
    Svaret cachas i DRAWS_CACHE_TTL_S sekunder — se kommentaren ovan."""
    cached = _draws_cached(product)
    if cached is not None:
        return cached
    if product == "bomben":
        with SvenskaSpel() as ss:
            raw = ss.bomben_draws()
        ds = [{"product": "bomben", "draw_number": d["drawNumber"],
               "state": d.get("drawState"), "reg_close_time": d.get("regCloseTime")}
              for d in raw]
        ds.sort(key=lambda d: d.get("reg_close_time") or "")
        payload = {"product": "bomben", "draws": ds,
                   "open": [d for d in ds if d["state"] == "Open"]}
        _draws_cache_put(product, payload)
        return payload
    slugs = GAME_GROUPS.get(product, [product])
    all_draws = []
    with SvenskaSpel() as ss:
        for slug in slugs:
            ds = ss.list_draws(slug, start_hint=_seed_hint(slug))
            _store_seed(slug, ds)
            all_draws.extend(ds)
    all_draws.sort(key=lambda d: d.get("reg_close_time") or "")
    opens = [d for d in all_draws if d["state"] == "Open"]
    payload = {"product": product, "draws": all_draws, "open": opens}
    _draws_cache_put(product, payload)
    return payload


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


@app.get("/api/bomben/system")
def bomben_system(draw: int, budget: float = 50.0, row_price: float = 1.0):
    """Radbyggare för Bomben: rangordnar konkreta resultat-rader efter EV."""
    from . import bomben as bomben_mod
    with SvenskaSpel() as ss:
        draws = ss.bomben_draws()
    d = next((x for x in draws if x["drawNumber"] == draw), None)
    if not d:
        raise HTTPException(404, f"Bomben-omgång {draw} hittades inte")
    try:
        with Pinnacle() as p:
            idx = p.soccer_index(include_without_odds=True)
    except Exception:  # noqa: BLE001
        idx = None
    res = bomben_mod.analyze_bomben(d, idx)
    sysm = bomben_mod.build_bomben_system(res, budget=budget, row_price=row_price)
    sysm["draw_number"] = draw
    return sysm


# Svenska Spels officiella vinstplaner: återbetalningsandel + andel per nivå.
# (Validerat mot faktiska utfall.) Topptipset: bara 8 rätt delar potten.
# Vinstplaner OMMÄTTA 2026-07-24 mot settlementlagret (PH1): median av
# faktisk utbetalning per nivå ÷ (omsättning × ratio), 150 omgångar/produkt.
# Stryktipset bekräftade den gamla planen exakt, men Europatipset visade sig
# ha en EGEN plan — 12 rätt får 0,22 (inte 0,15) och 13 rätt 0,39. Den gamla
# koden kopierade Stryktipsets plan och underskattade Europatipsets
# 12-rättspott med ~47 %. Splitsen summerar medvetet till < 1 (Stryk 0,92,
# Europa 0,98); resten går till jackpot-/rullpottsfonder och betalas alltså
# inte ut i den aktuella omgången — se _payout_ratio nedan.
PRIZE_PLANS = {
    "stryktipset":     {"ratio": 0.65, "splits": {13: 0.40, 12: 0.15, 11: 0.12, 10: 0.25}},
    "europatipset":    {"ratio": 0.65, "splits": {13: 0.39, 12: 0.22, 11: 0.12, 10: 0.25}},
    "topptipset":      {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetstryk": {"ratio": 0.70, "splits": {8: 1.00}},
    "topptipsetextra": {"ratio": 0.70, "splits": {8: 1.00}},
}


def _payout_ratio(plan: dict) -> float:
    """Andel av omsättningen som FAKTISKT betalas ut i omgången.

    `ratio` ensamt (0,65/0,70) är den gamla rubriksiffran, men eftersom
    splitsen inte summerar till 1 betalas bara ratio × Σsplits ut: Stryk
    59,8 %, Europa 63,7 %, Topptipset 70,0 % — verifierat mot 120 avgjorda
    omgångar per produkt. Break-even kräver därmed att radvalet slår fältet
    med 1/andel − 1 (Stryk +67 %, inte +54 %).
    """
    return plan["ratio"] * sum(plan["splits"].values())


def _finalturn_key(product: str, weekday: int | None) -> str:
    return (f"finalturn_{product}:"
            + (f"wd{weekday}" if weekday is not None else "any"))


def _close_weekday(close_iso: str | None) -> int | None:
    if not close_iso:
        return None
    try:
        return dt.datetime.fromisoformat(
            close_iso.replace("Z", "+00:00")).weekday()
    except (TypeError, ValueError):
        return None


def _projection_basis(product: str, close_iso: str | None) -> dict | None:
    """Prognosgrunden (veckodag, n, läge) för UI:t — läser cachen som
    _projected_turnover just skrev; None om ingen prognos gjorts."""
    import json as _json
    store = Storage()
    try:
        cached = store.meta_get(
            _finalturn_key(product, _close_weekday(close_iso)))
        return _json.loads(cached) if cached else None
    except (ValueError, TypeError):
        return None
    finally:
        store.close()


def _projected_turnover(product: str, current: float,
                        close_iso: str | None = None) -> float | None:
    """Förväntad SLUTomsättning ur det LOKALA settlementlagret (P4 2026-07-28):
    medianen av de senaste 8 avgjorda omgångarna med SAMMA spelstoppsveckodag.
    Europatipsets onsdagsomgångar omsätter en bråkdel av söndagens, och den
    gamla senaste-6-medianen blandade dagtyperna (den gjorde dessutom upp till
    15 resultat-anrop mot SvS per cache-miss — nu noll nätverk). Recency bär
    säsongseffekten (sommar ~12 M mot årsmedel ~24 M för Stryk) utan egen
    modell. Jackpotläget är MEDVETET utelämnat: settlementlagret saknar
    jackpotkolumn och snapshot-serien började 2026-07-24 — omprövas när den
    har volym. Tidig låg omsättning ger annars glädje-EV: både potter och
    medvinnare skalar med omsättningen."""
    import json as _json

    weekday = _close_weekday(close_iso)
    store = Storage()
    try:
        key = _finalturn_key(product, weekday)
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
        rows = [(r[0], float(r[1])) for r in store.conn.execute(
            "SELECT reg_close_time, net_sale FROM pool_draw_settlement "
            "WHERE product=? AND net_sale > 0 AND reg_close_time IS NOT NULL "
            "ORDER BY reg_close_time DESC LIMIT 60", (product,))]
        # METODVALET ÄR DATADRIVET PER PRODUKT (2026-07-28, upptäckt av
        # modellhälso-backtesten samma kväll som veckodagsmetoden byggdes):
        # för veckoprodukter (Stryk) vinner veckodagsmedianen, men för
        # dagliga produkter (Topptipset) är 8 samma-veckodagar = 8 veckors
        # säsongsdrift och den färska senaste-6 slår den stort (uppmätt
        # 173 % mot 43 % medianfel). Samma rullande backtest som
        # /api/pool/turnover-prognos väljer därför metod — bara på data
        # som fanns före respektive omgång.
        def _wd_vals(hist, wd, cap=8):
            picked = []
            for close_at, sale in hist:
                if _close_weekday(close_at) == wd:
                    picked.append(sale)
                if len(picked) >= cap:
                    break
            return picked

        errs_wd, errs_mix = [], []
        for i in range(min(20, max(0, len(rows) - 10))):
            t_close, actual = rows[i]
            hist = rows[i + 1:]
            for vals_i, errs in ((_wd_vals(hist, _close_weekday(t_close)),
                                  errs_wd),
                                 ([s for _, s in hist[:6]], errs_mix)):
                if len(vals_i) >= 3 and actual > 0:
                    errs.append(abs(sorted(vals_i)[len(vals_i) // 2] - actual)
                                / actual)
        def _median(xs):
            return sorted(xs)[len(xs) // 2] if xs else None
        wd_err, mix_err = _median(errs_wd), _median(errs_mix)
        vals = _wd_vals(rows, weekday) if weekday is not None else []
        # utan backtest-underlag gäller veckodagsprioren (dagtyperna skiljer);
        # bara ett UPPMÄTT övertag för blandade medianen väljer bort den
        use_weekday = (len(vals) >= 3
                       and (wd_err is None or mix_err is None
                            or wd_err <= mix_err))
        if use_weekday:
            mode = "weekday"
        else:
            mode, vals = "blandad", [sale for _, sale in rows[:6]]
        if not vals:
            return None
        ordered = sorted(vals)
        median = ordered[len(ordered) // 2]
        store.meta_set(key, _json.dumps(
            {"ts": dt.datetime.now(dt.timezone.utc).isoformat(),
             "median": median, "weekday": weekday, "n": len(vals),
             "mode": mode,
             "backtest_fel": {"veckodag": wd_err and round(wd_err, 4),
                              "blandad": mix_err and round(mix_err, 4)}}))
        return max(current, median)
    finally:
        store.close()


@app.get("/api/pool/history")
def pool_history(product: str = "stryktipset",
                 limit: int = Query(400, ge=1, le=1000),
                 draw: int | None = None):
    """PH1-settlementlagret (läser bara DB): avgjorda omgångar med utfall,
    slutstreck, slutomsättning och full utdelning per nivå. `final_only`-
    bakfyllda och framåtriktade omgångar — INGA rörelser härifrån (de finns
    bara i snapshot-kohorten). draw=<nr> ger full detalj inkl. matchfacit."""
    store = Storage()
    try:
        if draw is not None:
            head = store.conn.execute(
                "SELECT draw_number, draw_state, reg_close_time, net_sale, "
                "row_price, n_events, n_cancelled, product_name, fetched_at "
                "FROM pool_draw_settlement WHERE product=? AND draw_number=?",
                (product, draw)).fetchone()
            if not head:
                return {"available": False}
            events = store.conn.execute(
                "SELECT event_number, description, home, away, outcome, "
                "cancelled, streck_one, streck_x, streck_two "
                "FROM pool_event_settlement WHERE product=? AND draw_number=? "
                "ORDER BY event_number", (product, draw)).fetchall()
            tiers = store.conn.execute(
                "SELECT tier_name, correct, winners, amount FROM pool_payout_tier "
                "WHERE product=? AND draw_number=? ORDER BY correct DESC",
                (product, draw)).fetchall()
            return {"available": True, "draw": {
                "draw_number": head[0], "state": head[1], "close": head[2],
                "turnover": head[3], "row_price": head[4], "n_events": head[5],
                "n_cancelled": head[6], "product_name": head[7],
                "events": [{"event_number": e[0], "description": e[1],
                            "home": e[2], "away": e[3], "outcome": e[4],
                            "cancelled": bool(e[5]),
                            "streck": {"1": e[6], "X": e[7], "2": e[8]}}
                           for e in events],
                "tiers": [{"name": t[0], "correct": t[1], "winners": t[2],
                           "amount": t[3]} for t in tiers]}}
        total, first_close, last_close = store.conn.execute(
            "SELECT COUNT(*), MIN(reg_close_time), MAX(reg_close_time) "
            "FROM pool_draw_settlement WHERE product=?", (product,)).fetchone()
        mean_turnover = store.conn.execute(
            "SELECT AVG(net_sale) FROM pool_draw_settlement "
            "WHERE product=? AND net_sale>0", (product,)).fetchone()[0]
        top_rows = store.conn.execute(
            "SELECT p.winners, p.amount FROM pool_payout_tier p "
            "WHERE p.product=? AND p.correct=("
            " SELECT MAX(p2.correct) FROM pool_payout_tier p2 "
            " WHERE p2.product=p.product AND p2.draw_number=p.draw_number)",
            (product,)).fetchall()
        paid_top = sorted(
            float(r[1]) for r in top_rows
            if (r[0] or 0) > 0 and r[1] is not None and r[1] > 0)
        median_top = statistics.median(paid_top) if paid_top else None
        rollovers = sum(1 for r in top_rows if r[0] == 0)
        rows = store.conn.execute(
            "SELECT draw_number, reg_close_time, net_sale, row_price, "
            "n_cancelled FROM pool_draw_settlement WHERE product=? "
            "ORDER BY draw_number DESC LIMIT ?", (product, limit)).fetchall()
        draw_numbers = [r[0] for r in rows]
        tiers_by_draw: dict[int, list] = {}
        if draw_numbers:
            marks = ",".join("?" * len(draw_numbers))
            for t in store.conn.execute(
                    f"SELECT draw_number, tier_name, correct, winners, amount "
                    f"FROM pool_payout_tier WHERE product=? "
                    f"AND draw_number IN ({marks})",
                    (product, *draw_numbers)):
                tiers_by_draw.setdefault(t[0], []).append(
                    {"name": t[1], "correct": t[2], "winners": t[3],
                     "amount": t[4]})
        draws = []
        for r in rows:
            tiers = sorted(tiers_by_draw.get(r[0], []),
                           key=lambda t: -(t["correct"] or 0))
            top = tiers[0] if tiers else None
            draws.append({
                "draw_number": r[0], "close": r[1], "turnover": r[2],
                "row_price": r[3], "n_cancelled": r[4], "tiers": tiers,
                "top_winners": top and top["winners"],
                "top_amount": top and top["amount"]})
        return {"available": total > 0, "product": product, "total": total,
                "first_close": first_close, "last_close": last_close,
                "sample_size": len(draws),
                "stats": {
                    "scope": "all_settled",
                    "median_top_amount": median_top,
                    "rollovers": rollovers,
                    "rollover_rate": (rollovers / total if total else None),
                    "mean_turnover": mean_turnover,
                },
                "draws": draws}
    finally:
        store.close()


@app.get("/api/pool/systems")
def pool_systems():
    """PH3-systemledgern, rent läsande.

    Settlement sker i snapshotjobbet; ett GET-anrop får aldrig skriva DB.
    """
    from . import pool_system_ledger
    store = Storage()
    try:
        return pool_system_ledger.summary(store)
    finally:
        store.close()


@app.get("/api/pool/strength-shadow")
def pool_strength_shadow_report(product: str | None = None):
    """Pinnacle mot 90/10- och 80/20-styrkeblend; påverkar inga system."""
    from . import pool_strength_shadow
    if product is not None and product not in PRODUCTS:
        raise HTTPException(400, f"okänd poolprodukt: {product}")
    store = Storage()
    try:
        return pool_strength_shadow.report(store, product=product)
    finally:
        store.close()


@app.get("/api/pool/systems/detail")
def pool_system_detail(product: str, draw: int, horizon: str, config: str):
    """Ett fryst system mot facit, match för match — för mänsklig granskning.

    Visar vilka tecken systemet täckte, vad som gick in, och folkets streck
    både vid frysningen och vid spelstopp. Rent läsande; ingen ny insamling
    (raderna finns i ledgern, utfallet i settlementlagret, strecken i
    `snapshots`).
    """
    from . import pool_system_ledger
    store = Storage()
    try:
        return pool_system_ledger.system_detail(
            store, product, int(draw), horizon, config)
    finally:
        store.close()


@app.post("/api/pool/played")
async def pool_played_record(request: Request):
    """Bokför att användaren SJÄLV har lämnat in kupongen. Lägger inga spel."""
    from . import pool_played
    payload = await request.json()
    store = Storage()
    try:
        return {"coupon": pool_played.record(store, payload)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        store.close()


@app.delete("/api/pool/played/{coupon_id}")
def pool_played_forget(coupon_id: int):
    from . import pool_played
    store = Storage()
    try:
        if not pool_played.forget(store, coupon_id):
            raise HTTPException(
                status_code=409,
                detail="kupongen finns inte eller är redan settlad")
        return {"ok": True}
    finally:
        store.close()


@app.get("/api/pool/played")
def pool_played_list(live: bool = True):
    """Spelade kuponger med LIVESTATUS för öppna omgångar.

    Livestatusen läses ur SvS egen draw-payload (`match.result` +
    `statusId`), så reducerade system kan följas medan omgången pågår utan
    någon extra datakälla. Settlement sker i insamlingsjobbet — ett GET får
    aldrig skriva DB.
    """
    from . import pool_played
    store = Storage()
    try:
        coupons = pool_played.all_coupons(store)
        out = [dict(coupon) for coupon in coupons]
        if live:
            with SvenskaSpel() as ss:
                for item in out:
                    if item["settled_at"]:
                        continue
                    try:
                        raw = ss.get_draw_raw(item["product"],
                                              item["draw_number"])
                        states = [pool_played.event_state(e)
                                  for e in (raw.get("drawEvents") or [])]
                        # Pågående matcher måste prissättas live — SvS odds i
                        # payloaden är statiska prematch-odds hela omgången.
                        pool_played.attach_live_odds(store, states)
                        item["live"] = pool_played.live_status(item, states)
                    except Exception as exc:      # noqa: BLE001
                        item["live_error"] = f"{type(exc).__name__}"
        return {"coupons": out, "summary": pool_played.summary(store),
                "live_included": live}
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
        # Garantier (t.ex. ensamvinnargaranti) redovisas SEPARAT och räknas
        # medvetet inte in i spelvärdet — semantiken är overifierad.
        guarantees = ss.get_guarantees(product, d.draw_number)
    # Spelvärdet ska bygga på det som FAKTISKT betalas ut i omgången, inte på
    # bruttoandelen: Stryktipsets splits summerar till 0,92 så rubriken visade
    # 65 % när verklig utbetalning är 59,7 % (uppmätt, se _payout_ratio).
    payout_ratio = _payout_ratio(plan)
    spelvarde = payout_ratio + (jackpot / turnover if turnover else 0.0)
    projected = _projected_turnover(
        product, turnover, close_iso=d.reg_close_time) or turnover
    spelvarde_proj = payout_ratio + (jackpot / projected if projected else 0.0)
    basis = _projection_basis(product, d.reg_close_time)
    return {"available": turnover > 0, "draw_number": d.draw_number,
            "product": product,   # frontend behöver den för κ-korrektionen
            "turnover": turnover, "row_price": row_price,
            "ratio": plan["ratio"], "payout_ratio": round(payout_ratio, 4),
            # break-even: så mycket bättre än fältet måste radvalet vara
            "hurdle": round(1.0 / payout_ratio - 1.0, 4) if payout_ratio else None,
            "jackpot": jackpot, "guarantees": guarantees,
            "extra_info": d.extra_info,
            "spelvarde": round(spelvarde, 4),
            "projected_turnover": projected,
            "projection_basis": basis,
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
           jackpot: float | None = Query(None, ge=0),
           value_weight: float = 0.5):
    """value_weight 0..1 = EV-/värdeskala: 0 = lågoddsare/favoriter (hög träffchans),
    högre = mer värde/skräll (lägre chans, högre EV). sv_rsystem ger SvS R-system.
    ev=true rankar konkreta rader efter popularitetsjusterad EV (poolspels-optimal)."""
    a = _analyze(product, draw)
    vw = max(0.0, min(1.0, value_weight))
    plan = PRIZE_PLANS.get(product)
    jp = jackpot
    if (ev or color) and jp is None:
        try:
            with SvenskaSpel() as ss:
                jp = ss.get_jackpot(product, a.draw_number) or 0.0
        except Exception:  # jackpotfel ska inte blockera radbygget
            jp = 0.0
    jp = max(0.0, jp or 0.0)
    # Radvalet för EV/färg och WP6-portföljvärderingen räknar mot förväntad
    # SLUTomsättning. Tidig låg omsättning gör annars +1:an i medvinnarformeln
    # dominant och skapar glädje-EV. Övriga byggare använder inte omsättningen
    # för själva teckenvalet men får samma ärliga värderingshorisont efteråt.
    current_turnover = a.turnover or 0.0
    valuation_turnover = current_turnover
    turnover_basis = "live"
    if plan and valuation_turnover > 0:
        try:
            projected_turnover = (
                _projected_turnover(product, valuation_turnover,
                                    close_iso=a.reg_close_time)
                or valuation_turnover)
        except Exception:  # prognosfel ska inte blockera ett spelbart system
            projected_turnover = valuation_turnover
        if projected_turnover > valuation_turnover:
            valuation_turnover = projected_turnover
            turnover_basis = "projected"
    if (ev or color) and valuation_turnover > (a.turnover or 0.0):
        a.turnover = valuation_turnover
    try:
        if sv_rsystem and sv_rsystem in SVS_R12:
            s = build_svs_rsystem(a, sv_rsystem, strategy, value_weight=vw)
        elif ev:
            s = build_ev_system(a, strategy, budget, row_price=a.row_price or 1.0,
                                value_weight=vw, plan=plan, jackpot=jp)
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
                                   value_weight=vw, plan=plan,
                                   colors_override=co, bounds_override=bo, jackpot=jp)
        elif reduced and guarantee:
            s = build_guarantee_system(a, strategy, budget, guarantee=guarantee, value_weight=vw)
        elif reduced:
            s = build_reduced_system(a, strategy, budget, value_weight=vw)
        else:
            s = build_math_system(a, strategy, budget, value_weight=vw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if plan and valuation_turnover > 0:
        concrete_rows = materialize_system_rows(s)
        if concrete_rows is None:
            s.portfolio_mc = {
                "available": False,
                "reason": "Systemet är större än portföljsimuleringens 5 000-radersgräns.",
            }
        else:
            s.portfolio_mc = simulate_pool_portfolio(
                a, concrete_rows, plan, turnover=valuation_turnover,
                row_price=a.row_price or 1.0, jackpot=jp,
                turnover_basis=turnover_basis,
                # PH4-κ per nivå — samma tabell som radvalets EV, så
                # portföljvärderingen och byggaren berättar samma sanning
                kappa_by_tier={int(c): kappa_for(product, int(c))
                               for c in plan["splits"]},
            )
    return system_to_dict(s)


@app.get("/api/rsystems")
def rsystems():
    """Lista Svenska Spels 12-rättsgaranti-R-system."""
    return {"systems": [{"name": k, **v} for k, v in SVS_R12.items()]}


@app.get("/api/pool/turnover-prognos")
def turnover_prognos():
    """Modellhälsa (Labb, 2026-07-28): (a) rullande backtest av veckodags-
    prognosen mot gamla blandade senaste-6-medianen — medianabsolutfel över
    senaste ~20 avgjorda omgångarna per produkt, räknat enbart på data som
    fanns FÖRE respektive omgång; (b) PH4-gatens OOT-räknare (avgjorda
    omgångar efter 2026-07-24, krav ≥ 40 innan nya κ-varianter föreslås)."""
    import statistics
    store = Storage()
    try:
        out = {}
        for product in PRIZE_PLANS:
            rows = [(r[0], float(r[1])) for r in store.conn.execute(
                "SELECT reg_close_time, net_sale FROM pool_draw_settlement "
                "WHERE product=? AND net_sale > 0 AND reg_close_time IS NOT "
                "NULL ORDER BY reg_close_time DESC LIMIT 80", (product,))]
            errs_wd, errs_mix = [], []
            for i in range(min(20, max(0, len(rows) - 10))):
                target_close, actual = rows[i]
                hist = rows[i + 1:]
                wd = _close_weekday(target_close)
                same = [s for c, s in hist if _close_weekday(c) == wd][:8]
                mixed = [s for _, s in hist[:6]]
                for vals, errs in ((same, errs_wd), (mixed, errs_mix)):
                    if len(vals) >= 3 and actual > 0:
                        med = sorted(vals)[len(vals) // 2]
                        errs.append(abs(med - actual) / actual)
            oot = store.conn.execute(
                "SELECT COUNT(*) FROM pool_draw_settlement WHERE product=? "
                "AND reg_close_time > '2026-07-24T23:59:59Z'",
                (product,)).fetchone()[0]
            out[product] = {
                "n_backtest": len(errs_wd),
                "medianfel_veckodag": (round(statistics.median(errs_wd), 4)
                                       if errs_wd else None),
                "medianfel_blandad": (round(statistics.median(errs_mix), 4)
                                      if errs_mix else None),
                "ph4_oot": oot, "ph4_oot_krav": 40,
            }
        return out
    finally:
        store.close()


@app.get("/api/oddset/matches")
def oddset_matches(light: bool = False, compact: bool = False,
                   movement: bool = True,
                   limit: int | None = Query(default=None, ge=1, le=250)):
    """Oddset-fliken: matcher i tidsordning med senaste odds (Pinnacle + Svenska Spel)
    och rörelseserier. Läser bara DB — insamlingen sker via /api/oddset/refresh
    eller launchd-jobbet."""
    from . import oddset as oddset_mod
    store = Storage()
    try:
        return oddset_mod.matches_payload(
            store, light=light, compact_movement=compact,
            include_movement=movement, limit=limit,
            hide_sources=oddset_mod.UI_HIDDEN_SOURCES)
    finally:
        store.close()


@app.get("/api/oddset/movement")
def oddset_movement(match_id: str):
    """Råa rörelsepunkter för en öppnad matchdetalj, aldrig hela listan."""
    store = Storage()
    try:
        return {"match_id": match_id,
                "movement": store.oddset_movement([match_id]).get(match_id, {})}
    finally:
        store.close()


@app.get("/api/dashboard/oddset")
def dashboard_oddset():
    """Kompakt Oddset-underlag för Idag; fulla prisserier hör till Oddset-vyn."""
    from . import oddset as oddset_mod
    store = Storage()
    try:
        return oddset_mod.dashboard_payload(store)
    finally:
        store.close()


@app.get("/api/oddset/clv")
def oddset_clv():
    """Signal-facit för Oddset: loggade sharp-edges vs devigad Pinnacle-stängning."""
    import json as _json
    from . import oddset_value
    store = Storage()
    try:
        oddset_value.resolve_closings(store)
        # utfalls-facitet settlas opportunistiskt här precis som stängningarna
        oddset_value.resolve_outcomes(store)
        report = oddset_value.clv_report(store)
        # kalibreringsläsning (P6): senaste `oddsetcalibrate`-körningen per
        # liga (modelltemperatur mot football-data-backtesten). Display-only;
        # tom tills CLI-körningen gjorts.
        cal = {}
        for lg in ("allsvenskan", "eliteserien"):
            raw = store.meta_get(f"oddset_cal:{lg}")
            if raw:
                try:
                    cal[lg] = _json.loads(raw)
                except ValueError:
                    pass
        report["calibration"] = cal or None
        return report
    finally:
        store.close()


@app.get("/api/oddset/powerrank")
def oddset_powerrank(league: str = "allsvenskan", season: str | None = None):
    """Lagstyrka (att/def ur modellens EGEN fit) + xPts-avvikelse per lag.

    AMBER: en visning av modellens syn, aldrig ett beslutsunderlag. Uppmätt
    förutsäger modellen inte Pinnacles drift till stängning
    (r = −0,120, 90 % KI [−0,252, +0,034]), så ranken får inte ge stödchip
    eller påverka edge, urval eller notiser.
    """
    from . import oddset_data, oddset_model
    store = Storage()
    try:
        if league == "all":
            # Hela uppsättningen i ETT anrop — uppmätt 0,5 s för fem ligor,
            # så matchlistan slipper ett anrop per liga. Bara MODEL_LEAGUES:
            # utan resultatdata finns ingen styrka att skatta.
            out = {}
            for lg in sorted(oddset_data.MODEL_LEAGUES):
                pool = oddset_model.FIT_POOLS.get(lg, (lg,))
                rows, names = [], []
                for plg in pool:
                    rows.extend(oddset_model.cached_results(store, plg))
                    names.extend(store.oddset_team_names(plg))
                # Fitten ur den DELADE cachen — elva egna fits i ett anrop tog
                # 2,2 s och låg parallellt med matchhämtningen.
                out[lg] = oddset_model.powerrank(
                    rows, fit=oddset_model.cached_fit(store, pool),
                    league=lg, odds_names=names)
            return {"league": "all", "tier": "amber",
                    "version": oddset_model.POWERRANK_VERSION,
                    "by_league": out}
        pool = oddset_model.FIT_POOLS.get(league, (league,))
        rows: list[dict] = []
        names: list[str] = []
        for plg in pool:
            rows.extend(oddset_model.cached_results(store, plg))
            names.extend(store.oddset_team_names(plg))
        # Bara säsonger som HAR xG kan väljas: tabellen räknar uteslutande på
        # xG-täckta matcher, så en säsong utan xG skulle ge en tom vy och se
        # ut som ett fel i stället för som frånvaro av mätning.
        seasons = sorted({
            s for r in rows
            if r.get("league") == league
            and r.get("xg_h") is not None and r.get("xg_a") is not None
            and (s := oddset_model.season_of(r.get("date") or "", league))
        }, reverse=True)
        if season and season not in seasons:
            season = None
        rank = oddset_model.powerrank(rows, fit=oddset_model.cached_fit(store, pool),
                                      league=league, season=season,
                                      odds_names=names)
        return {
            "league": league,
            "version": oddset_model.POWERRANK_VERSION,
            "tier": "amber",
            "pool": list(pool),
            "n_results": len(rows),
            "seasons": seasons,
            "season": season,
            # UI:t förklarar formeln för Saman. Talen skickas med i stället
            # för att skrivas in i texten, så förklaringen inte kan glida
            # ifrån koden när en parameter ändras.
            "params": {
                "iters": oddset_model.FIT_ITER,
                "xg_weight": oddset_model.XG_WEIGHT,
                "half_life_d": round(oddset_model.DECAY_DAYS * math.log(2)),
                "ridge": 0.98,
            },
            "teams": rank,
            "disclaimer": (
                "Modellens egen styrkeskattning. Den förutsäger inte "
                "marknadens rörelse och påverkar inga tips, notiser eller "
                "CLV."),
        }
    finally:
        store.close()


@app.get("/api/oddset/predictions")
def oddset_predictions():
    """WP5-ledger: alla fasta horisontprediktioner och v3-status per grupp."""
    from . import oddset_ledger
    store = Storage()
    try:
        oddset_ledger.resolve_closings(store)
        return oddset_ledger.prediction_report(store)
    finally:
        store.close()


@app.get("/api/oddset/predictions/summary")
def oddset_predictions_summary():
    """Kompakt, read-only ledgerstatus för Idag-vyn."""
    from . import oddset_ledger
    store = Storage()
    try:
        return oddset_ledger.dashboard_summary(store)
    finally:
        store.close()


@app.get("/api/oddset/v2-shadow")
def oddset_v2_shadow():
    """Forskningsstatus för isolerad V2.2; inga tips eller notifieringar."""
    from . import oddset_v22
    store = Storage()
    try:
        return oddset_v22.audit(store)
    finally:
        store.close()


@app.get("/api/oddset/live-radar")
def oddset_live_radar():
    """Observerad chansradar för pågående matcher; shadow, aldrig speltips."""
    from . import live_radar
    store = Storage()
    try:
        return live_radar.payload(store)
    finally:
        store.close()


@app.get("/api/oddset/radar-facit")
def oddset_radar_facit():
    """Radar-facit (mode=shadow): rå-providerögonblick mot villkorad basrate
    plus framåtriktad signaljournal med UI:ts exakta signalbasis, live-Ö/U och
    slutresultat. Läser bara DB — settlement sker i live-tick-varvet, aldrig i
    ett GET-anrop."""
    from . import live_settlement
    store = Storage()
    try:
        return live_settlement.facit(store)
    finally:
        store.close()


@app.get("/api/oddset/match-flags")
def oddset_match_flags(match_id: str):
    """Rek-historiken för EN match: alla loggade värdeflaggor med utfall.
    Läser bara value_log — inga nya flaggor skapas av ett GET-anrop."""
    store = Storage()
    try:
        rows = [dict(r) for r in store.conn.execute(
            "SELECT market, sign, line, book, tier, first_at, first_odds, "
            "first_edge, best_edge, closing_fair, closing_odds, closing_note, "
            "anchor2_edge, model_version FROM oddset_value_log "
            "WHERE match_id=? ORDER BY first_at DESC", (match_id,))]
        for r in rows:
            # close-EV med samma definition som facitet: fair vid stängning ×
            # oddset vi kunde ta − 1. Saknas stängning redovisas det öppet.
            if r["closing_fair"] is not None and r["first_odds"]:
                r["close_ev"] = round(
                    r["closing_fair"] * r["first_odds"] - 1, 4)
            else:
                r["close_ev"] = None
        return {"match_id": match_id, "flags": rows}
    finally:
        store.close()


@app.get("/api/oddset/notices")
def oddset_notices():
    """Notis-historik: alla triggade värde-/steam-larm (skickade OCH torrkörda
    utan NTFY_TOPIC) ur meta-tabellens dedup-nycklar."""
    import json as _json
    store = Storage()
    try:
        rows = store.meta_like("oddset_ntfy_")
    finally:
        store.close()
    out = []
    for k, v in rows:
        try:
            d = _json.loads(v)
        except ValueError:   # gammalt format: bara tidsstämpel
            d = {"at": v, "title": k.split(":", 1)[-1], "msg": "", "sent": True}
        d["kind"] = "steam" if "steam" in k else "värde"
        out.append(d)
    out.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"notices": out[:50]}


@app.post("/api/oddset/refresh")
def oddset_refresh():
    """Hämta färska odds från Pinnacle + Kambi för alla Oddset-ligor (tar ~10-30 s)."""
    from . import oddset as oddset_mod
    store = Storage()
    try:
        return oddset_mod.collect(store)
    finally:
        store.close()


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

LAUNCHD_LABEL = "com.saman.spelkompisen.snapshot"
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
    """Installerar plisten från backend/scripts/ vid behov och laddar den.
    Returnerar status + ev. felmeddelande (tidigare no-op:ades tyst utan plist)."""
    error = None
    if not LAUNCHD_PLIST.exists():
        src = Path(__file__).resolve().parent.parent / "scripts" / f"{LAUNCHD_LABEL}.plist"
        if src.exists():
            try:
                LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
                LAUNCHD_PLIST.write_bytes(src.read_bytes())
            except OSError as e:
                error = f"kunde inte installera plist: {e}"
        else:
            error = f"plist-mallen saknas: {src}"
    if LAUNCHD_PLIST.exists():
        r = subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0 and r.stderr.strip():
            error = f"launchctl: {r.stderr.strip()}"
    st = collection_status()
    if error:
        st["error"] = error
    return st


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
    # Dubbeltrafikspärren ger tomma hits/status utan fel. Då vet vi ingenting om
    # Pinnacles utbud — defaulten "not_listed" hade påstått "ej listad hos
    # Pinnacle" om varje match trots att vi aldrig frågade (2026-07-25).
    unknown = "ej ompollad" if pin_res.get("skipped") else "not_listed"

    out = []
    for m in draw.matches:
        h = hits.get(m.event_number)
        ext_data = None
        st = status.get(m.event_number, unknown)
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
