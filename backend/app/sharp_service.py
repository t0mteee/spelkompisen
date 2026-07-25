"""Delad logik för att hämta + cacha sharp-odds från Pinnacle (gratis).

Används av både /api/external-odds och bakgrundsinsamlaren. Rapporterar även
coverage-status per match så UI:t kan visa *varför* en match saknar sharp:
  matched       – 1X2 hämtat
  no_moneyline  – matchen finns på Pinnacle men 1X2 ej öppnad (bara spread/total)
  not_listed    – matchen finns inte i Pinnacles utbud (ännu)
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .pinnacle import Pinnacle, cache_adjusted_iso
from .storage import Storage
from .svenskaspel import SvenskaSpel, Draw

# DUBBELTRAFIKSPÄRR (2026-07-25). Sedan poolen fick ett eget 5-minutersjobb
# anropar TVÅ launchd-jobb Pinnacles globala bulk-endpoints under samma
# 25-minutersfönster, med samma gäst-nyckel från samma IP — förhöjd
# Cloudflare-403-risk. Objektet är dessutom CDN-cachat i 905 s, så de flesta
# extraanropen ger exakt samma data. Hoppa över hämtningen när någon väg redan
# hämtat inom detta fönster; DB:ns cachade priser används då som vanligt.
PINNACLE_MIN_INTERVAL_S = 600
_PINNACLE_LAST_FETCH_KEY = "pinnacle_last_bulk_fetch"


def _pinnacle_fetched_recently(store: Storage) -> bool:
    last = store.meta_get(_PINNACLE_LAST_FETCH_KEY)
    if not last:
        return False
    try:
        when = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return False
    age = (dt.datetime.now(dt.timezone.utc) - when).total_seconds()
    return 0 <= age < PINNACLE_MIN_INTERVAL_S


def collect_pinnacle(product: str = "stryktipset",
                     draw: Optional[Draw] = None,
                     cache: bool = True,
                     force: bool = False) -> Optional[dict]:
    """Hämta Pinnacle-odds för omgångens matcher. Returnerar hits + status.
    Cachar matchade odds i SQLite (gratis, kostar inga credits).

    force=True kringgår dubbeltrafikspärren. Används BARA när observationen
    inte kan göras om: poolens horisontfönster (T−24h/−3h/−20min) inträffar en
    gång per omgång och får aldrig bakfyllas. Spärren i övrigt är kvar —
    Oddset-varvets snabbpoll höll annars låset varmt så gott som konstant, och
    poolen förlorade sin sharp-observation i 52 % av alla ticks (2026-07-25).
    """
    if draw is None:
        with SvenskaSpel() as ss:
            draw = ss.get_current_draw(product)
    if draw is None:
        return None

    retrieved_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hits: dict[int, dict] = {}
    status: dict[int, str] = {}
    cache_age_s = 0

    _throttle_store = Storage()
    try:
        if not force and _pinnacle_fetched_recently(_throttle_store):
            return {"draw": draw, "hits": {}, "status": {},
                    "fetched_at": retrieved_at, "cache_age_s": 0,
                    "skipped": "pinnacle hämtad av annat varv inom "
                               f"{PINNACLE_MIN_INTERVAL_S // 60} min"}
    finally:
        _throttle_store.close()

    # Pinnacle Cloudflare-blockar periodvis vår (datacenter-/VPN-)IP → degradera
    # snyggt: krascha inte insamlingen, spåra hälsan i meta så UI:t kan visa det.
    # (Headers/TLS hjälper EJ — blocket är IP-baserat. the-odds-api är redan
    # svs primärkälla och täcker det Pinnacle gör, så ingen fallback behövs här.)
    try:
        with Pinnacle() as pin:
            index = pin.soccer_index(include_without_odds=True)
            # soccer_index hämtar marknader sist: last_age_s är alltså
            # prisendpointens HTTP Age, inte den separata matchup-listans.
            cache_age_s = int(getattr(pin, "last_age_s", 0) or 0)
            _ts = Storage()
            try:   # bokför hämtningen så andra varv kan hoppa över den
                _ts.meta_set(_PINNACLE_LAST_FETCH_KEY, retrieved_at)
            finally:
                _ts.close()
            for m in draw.matches:
                hit = pin.match(m.home, m.away, m.home_iso, m.away_iso,
                                index, m.match_start)
                if not hit:
                    status[m.event_number] = "not_listed"
                    continue
                o = hit.get("odds") or {}
                if o.get("1") is None and o.get("2") is None:
                    status[m.event_number] = "no_moneyline"
                else:
                    derived = hit.get("odds_source") == "derived"
                    status[m.event_number] = "derived" if derived else "matched"
                    hits[m.event_number] = {
                        **hit, "source": "pinnacle",
                        "bookmaker": "pinnacle (härledd)" if derived else "pinnacle"}
    except Exception as e:  # noqa: BLE001 — block/nätfel ska inte fälla SS-insamlingen
        _hs = Storage()
        try:
            _hs.meta_set("pinnacle_error", str(e).splitlines()[0][:160])
            _hs.meta_set("pinnacle_error_at", retrieved_at)
        finally:
            _hs.close()
        return {"draw": draw, "hits": {}, "status": {},
                "fetched_at": retrieved_at, "retrieved_at": retrieved_at,
                "cache_age_s": 0, "pinnacle_error": str(e)[:160]}

    observed_at = cache_adjusted_iso(retrieved_at, cache_age_s)
    store = Storage()
    try:
        store.meta_set("last_pinnacle_ok", retrieved_at)   # transporthälsan
        store.meta_set("pinnacle_error", "")
        if cache and hits:
            to_cache = [{"event_number": ev, "bookmaker": h["bookmaker"], "odds": h["odds"],
                         "confidence": h["confidence"],
                         "matched": f'{h["home"]} - {h["away"]}',
                         "fetched_at": observed_at}
                        for ev, h in hits.items()]
            store.save_sharp(product, draw.draw_number, to_cache)
            store.save_sharp_snapshot(
                product, draw.draw_number, hits, observed_at)
    finally:
        store.close()

    return {"draw": draw, "hits": hits, "status": status,
            "fetched_at": observed_at, "retrieved_at": retrieved_at,
            "cache_age_s": cache_age_s}
