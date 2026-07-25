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


def collect_pinnacle(product: str = "stryktipset",
                     draw: Optional[Draw] = None,
                     cache: bool = True) -> Optional[dict]:
    """Hämta Pinnacle-odds för omgångens matcher. Returnerar hits + status.
    Cachar matchade odds i SQLite (gratis, kostar inga credits)."""
    if draw is None:
        with SvenskaSpel() as ss:
            draw = ss.get_current_draw(product)
    if draw is None:
        return None

    retrieved_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hits: dict[int, dict] = {}
    status: dict[int, str] = {}
    cache_age_s = 0

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
