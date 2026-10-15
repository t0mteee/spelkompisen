"""Livesidan för poolspelen (2026-10-15): alla pågående omgångar på en gång.

Samans önskemål 2026-10-15: liverättningen och omsättningen segade ner Idag,
det gick inte att se vad som krävs för alla rätt, och inget uppdaterades av
sig självt. Livebilden räknas därför i BAKGRUNDEN (`LiveHub`, var 20:e s när
något pågår) och sidorna läser bara det färdiga svaret (`GET /api/pool/live`).

* Omgångar: alla poolomgångar (utom Bomben) vars spelstopp passerat de senaste
  `FONSTER_BAKAT` och som ännu inte settlats, samt omgångar med en ospelad
  kupong som stänger inom `FONSTER_FRAMAT`. Även omgångar utan egen kupong
  visas, med rätt rad hittills och folkets andel med alla rätt.
* Samma källkedja och samma regler som Mina kuponger: `pool_played.event_state`
  och `live_status` (LIVEBILD, aldrig facit), `payout_forecast` (vår prognos).
  Ingenting här skriver databasen.
* "Krävs för alla rätt" är `live_status`s heja-matris mot toppnivån: per
  öppen match de tecken som håller minst en rad vid liv till alla rätt.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Callable, Optional

from . import pool_played
from .svenskaspel import PRODUCTS
from .storage import Storage

logger = logging.getLogger(__name__)

PRODUKTER = ("stryktipset", "europatipset", "topptipset", "topptipsetstryk",
             "topptipsetextra")
FONSTER_BAKAT = dt.timedelta(hours=12)
FONSTER_FRAMAT = dt.timedelta(minutes=30)
INTERVALL_S = 20.0           # när något pågår
VILA_S = 120.0               # när inget pågår: bara upptäck att något börjat
LEVANDE_RADER_MAX = 12

StatesFn = Callable[[Storage, list], tuple[dict, dict]]
ForecastFn = Callable[[Storage, str, int, list, float], Optional[dict]]


def _utc(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── urval ────────────────────────────────────────────────────────────────

def aktiva_omgangar(store: Storage, now: dt.datetime) -> list[tuple[str, int, str]]:
    """(produkt, omgång, spelstopp) som ska följas live, äldsta stopp först."""
    out: dict[tuple[str, int], str] = {}
    settled = {(p, int(n)) for p, n in store.conn.execute(
        "SELECT product, draw_number FROM pool_draw_settlement")}
    for product, number, close in store.conn.execute(
            "SELECT product, draw_number, reg_close_time FROM draws"):
        at = _utc(close)
        if (product in PRODUKTER and at is not None
                and now - FONSTER_BAKAT <= at <= now
                and (product, int(number)) not in settled):
            out[(product, int(number))] = close
    for coupon in pool_played.open_coupons(store):
        at = _utc(coupon.get("draw_close"))
        key = (coupon["product"], int(coupon["draw_number"]))
        if (coupon["product"] in PRODUKTER and at is not None
                and at <= now + FONSTER_FRAMAT and key not in settled):
            out[key] = coupon.get("draw_close")
    return sorted(((p, n, c) for (p, n), c in out.items()),
                  key=lambda item: (_utc(item[2]), item[0], item[1]))


# ── en omgång ────────────────────────────────────────────────────────────

def _match(state: dict, now: dt.datetime) -> dict:
    decided = pool_played._decided(state)  # noqa: SLF001
    minute = None
    if state.get("in_progress"):
        played = pool_played._minutes_played(state, now)  # noqa: SLF001
        minute = int(played) if played is not None else None
    probs = state.get("probs") if state.get("in_progress") else None
    return {
        "event": state.get("event_number"),
        "home": state.get("home"), "away": state.get("away"),
        "description": state.get("description"),
        "start": state.get("start"),
        "score": state.get("score"), "sign": state.get("sign"),
        "final": decided,
        "in_progress": bool(state.get("in_progress")),
        "extra_time": bool(state.get("extra_time")),
        "sign_provisional": bool(state.get("sign_provisional")),
        "postponed": bool(state.get("postponed")),
        "cancelled": bool(state.get("cancelled")),
        "status_text": state.get("status_text"),
        "minute": minute,
        "folk": state.get("folk"),
        "live_probs": probs if state.get("probs_basis") == "live" else None,
    }


def _folk_alla_ratt(states: list[dict]) -> Optional[float]:
    """Andel av folkets rader (ur strecken) som har alla rätt hittills, givet
    ställningen nu i startade matcher. None innan någon match startat."""
    share, n = 1.0, 0
    for state in states:
        sign = state.get("sign")
        if state.get("cancelled") or sign not in pool_played.SIGNS:
            continue
        if not (state.get("final") or state.get("score")):
            continue
        folk = state.get("folk") or {}
        if folk.get(sign) is None:
            return None
        share *= max(0.0, float(folk[sign])) / 100.0
        n += 1
    return round(share, 6) if n else None


def _krav(live: dict) -> list[dict]:
    """Per öppen match: tecknen som håller minst en rad vid liv till alla rätt."""
    out = []
    for cheer in live.get("cheer") or []:
        signs = cheer.get("signs") or {}
        top = {sign: int((signs.get(sign) or {}).get("top") or 0)
               for sign in pool_played.SIGNS}
        out.append({"col": cheer.get("col"), "description": cheer.get("description"),
                    "signs": [sign for sign in pool_played.SIGNS if top[sign] > 0],
                    "rows": top, "best": cheer.get("best")})
    return out


def kompakt_kupong(coupon: dict, live: dict) -> dict:
    """Det livesidan visar om en kupong: summering, nivåer, krav, levande rader."""
    keep = ("n_events", "n_decided", "all_decided", "best_secure", "current_known",
            "current_best", "current_best_rows", "max_possible", "out_of_contention",
            "alive_per_level", "alive_min_per_level", "alive_max_per_level",
            "alive_unproven", "chance_per_level", "chance_min_per_level",
            "chance_max_per_level", "chance_note", "chance_unpriced", "chance_basis",
            "alive_rows_total")
    out = {key: live[key] for key in keep if key in live}
    levels = sorted((live.get("alive_per_level") or {}), reverse=True)
    top = levels[0] if levels else None
    krav = _krav(live)
    out.update({
        "id": coupon["id"], "label": coupon.get("label"),
        "build_kind": coupon.get("build_kind"), "n_rows": coupon.get("n_rows"),
        "cost_kr": coupon.get("cost_kr"), "played_at": coupon.get("played_at"),
        "top_level": top,
        "top_alive": (live.get("alive_per_level") or {}).get(top) if top else None,
        "krav": krav,
        # Kupongens tecken per kolumn, i omgångens eventordning.
        "row_signs": {str(m.get("event")): m.get("row_signs") or {}
                      for m in live.get("matches") or []},
        "alive_rows": (live.get("alive_rows") or [])[:LEVANDE_RADER_MAX],
    })
    return out


def bygg(store: Storage, now: dt.datetime, *, states_fn: StatesFn,
         forecast_fn: ForecastFn,
         row_price_fn: Callable[[str, int], Optional[float]] = lambda p, n: None) -> dict:
    """Hela livesidans svar. `coupon_live` (fulla livebilder per kupong-id) är
    internt och strippas i API:t; Mina kuponger återanvänder den."""
    omgangar = aktiva_omgangar(store, now)
    keys = [(p, n) for p, n, _close in omgangar]
    states_by_draw, errors_by_draw = states_fn(store, keys) if keys else ({}, {})
    coupons_by_draw: dict[tuple[str, int], list[dict]] = {}
    for coupon in pool_played.open_coupons(store):
        coupons_by_draw.setdefault(
            (coupon["product"], int(coupon["draw_number"])), []).append(coupon)
    draws, coupon_live, aktiv = [], {}, False
    for product, number, close in omgangar:
        key = (product, number)
        entry = {"product": product, "name": PRODUCTS.get(product, {}).get("name", product),
                 "draw_number": number, "close": close, "matches": [], "coupons": []}
        if key in errors_by_draw or key not in states_by_draw:
            entry["error"] = type(errors_by_draw.get(key) or LookupError()).__name__
            draws.append(entry)
            continue
        states = states_by_draw[key]
        matches = [_match(state, now) for state in states]
        entry["matches"] = matches
        entry["n_decided"] = sum(1 for m in matches if m["final"])
        entry["n_live"] = sum(1 for m in matches if m["in_progress"])
        entry["started"] = any(m["score"] for m in matches)
        entry["finished"] = bool(matches) and all(m["final"] for m in matches)
        aktiv = aktiv or bool(entry["n_live"]) or (entry["started"] and not entry["finished"])
        entry["folk_alla_ratt"] = _folk_alla_ratt(states)
        own = coupons_by_draw.get(key, [])
        row_price = (row_price_fn(product, number)
                     or (float(own[0].get("row_price") or 1.0) if own else 1.0))
        try:
            entry["forecast"] = forecast_fn(store, product, number, states, row_price)
        except Exception:  # noqa: BLE001 — prognosen får aldrig fälla livebilden
            logger.warning("Prognosen misslyckades för %s %s", product, number,
                           exc_info=True)
            entry["forecast"] = None
        for coupon in own:
            try:
                live = pool_played.live_status(coupon, states, include_chance=True)
            except Exception:  # noqa: BLE001
                logger.warning("Livestatus misslyckades för kupong %s", coupon["id"],
                               exc_info=True)
                entry["coupons"].append({"id": coupon["id"], "error": True})
                continue
            if entry.get("forecast") is not None:
                live["forecast"] = entry["forecast"]
            coupon_live[coupon["id"]] = live
            entry["coupons"].append(kompakt_kupong(coupon, live))
        draws.append(entry)
    return {"as_of": _iso(now), "active": aktiv, "interval_s": INTERVALL_S,
            "draws": draws, "coupon_live": coupon_live}


# ── bakgrunden ───────────────────────────────────────────────────────────

class LiveHub:
    """Räknar livebilden i bakgrunden och delar den mellan alla läsare.

    `snapshot()` svarar direkt ur senaste bygget. Finns inget, eller är det
    äldre än `max_age_s` (tråden har stannat), byggs det i anropet — men bara
    av en tråd i taget (single-flight)."""

    def __init__(self, build: Callable[[], dict], *, interval_s: float = INTERVALL_S,
                 idle_s: float = VILA_S, clock: Callable[[], float] = time.monotonic):
        self._build = build
        self.interval_s, self.idle_s, self._clock = interval_s, idle_s, clock
        self._lock = threading.Lock()
        self._payload: Optional[dict] = None
        self._built_at: Optional[float] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def refresh(self) -> Optional[dict]:
        with self._lock:
            try:
                payload = self._build()
            except Exception:  # noqa: BLE001 — en trasig byggnad behåller förra bilden
                logger.warning("Livebilden kunde inte byggas", exc_info=True)
                return self._payload
            self._payload, self._built_at = payload, self._clock()
            return payload

    def age_s(self) -> Optional[float]:
        return None if self._built_at is None else self._clock() - self._built_at

    def snapshot(self, max_age_s: float = 90.0) -> Optional[dict]:
        age = self.age_s()
        if age is None or age > max_age_s:
            if self._lock.locked():      # någon bygger redan: vänta på den
                with self._lock:
                    pass
                if self.age_s() is not None and self.age_s() <= max_age_s:
                    return self._payload
            return self.refresh()
        return self._payload

    def _loop(self) -> None:
        while not self._stop.is_set():
            payload = self.refresh()
            self._stop.wait(self.interval_s if payload and payload.get("active")
                            else self.idle_s)

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="pool-live-hub",
                                            daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
