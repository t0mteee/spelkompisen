"""Providerseparerat Ö/U-reservunderlag. Aldrig sharp eller bygginput."""
from __future__ import annotations

import datetime as dt
import math
import time

import httpx

from . import kambi

VERSION = "pool-reserve-ou-v1"
SOURCE = "svenskaspel_kambi"
MAX_AGE_S = 1800
COOLDOWN_S = 900
MAX_CALLS = 3
SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_reserve_quote (
 product TEXT NOT NULL, draw_number INTEGER NOT NULL, event_number INTEGER NOT NULL,
 source TEXT NOT NULL, provider_event_id TEXT NOT NULL, checked_at TEXT NOT NULL,
 observed_at TEXT NOT NULL, status TEXT NOT NULL, line REAL, over_odds REAL,
 under_odds REAL, match_start TEXT, home TEXT, away TEXT, version TEXT NOT NULL,
 PRIMARY KEY(product,draw_number,event_number,source,checked_at)
);
CREATE INDEX IF NOT EXISTS idx_pool_reserve_event
 ON pool_reserve_quote(source,provider_event_id,checked_at);
"""


def _time(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(dt.timezone.utc) if result.tzinfo else None
    except (AttributeError, ValueError, TypeError):
        return None


def _number(value, minimum):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value > minimum)


def parse_quote(data, event_id, match_start, now):
    """SvS anger Kambi-id: exakt id + avspark är identitet, ingen fuzzy.

    Kambis hem/bortanamn sparas för audit; inget nytt namnalias skapas.
    Bara ordinarie fulltid, båda öppna utfall på SAMMA lina och prematch.
    """
    events = [e for e in data.get("events", []) if str(e.get("id")) == str(event_id)]
    if len(events) != 1:
        return {"status": "identity_unverified"}
    e = events[0]
    start, expected = _time(e.get("start")), _time(match_start)
    if (start is None or expected is None or abs((start-expected).total_seconds()) > 900
            or e.get("sport") != "FOOTBALL" or e.get("state") != "NOT_STARTED"
            or start <= now or expected <= now):
        return {"status": "identity_unverified"}
    identity = {"home": e.get("homeName"), "away": e.get("awayName"),
                "match_start": e.get("start")}
    offers = []
    for bo in data.get("betOffers", []):
        criterion = bo.get("criterion") or {}
        if (str(bo.get("eventId")) != str(event_id)
                or criterion.get("label") != "Asian totalt"
                or criterion.get("occurrenceType") != "GOALS"
                or criterion.get("lifetime") != "FULL_TIME"):
            continue
        sides = {}
        for outcome in bo.get("outcomes", []):
            sign = {"OT_OVER": "O", "OT_UNDER": "U"}.get(outcome.get("type"))
            if (sign and outcome.get("status") == "OPEN"
                    and _number(outcome.get("odds"), 1000)
                    and _number(outcome.get("line"), 0)):
                sides.setdefault(outcome["line"], {})[sign] = outcome["odds"] / 1000
        for line, prices in sides.items():
            if set(prices) == {"O", "U"}:
                offers.append(("MAIN_LINE" not in (bo.get("tags") or []),
                               abs(prices["O"]-2)+abs(prices["U"]-2), line, prices))
    if not offers:
        return {"status": "no_market", **identity}
    _, _, line, prices = min(offers, key=lambda p: p[:3])
    return {"status": "available", "line": line/1000,
            "over_odds": prices["O"], "under_odds": prices["U"], **identity}


def fetch_quote(match):
    response = httpx.get(f"{kambi.BASE}/betoffer/event/{match.kambi_id}.json",
                         params=kambi.PARAMS, headers=kambi.HEADERS, timeout=2)
    checked = dt.datetime.now(dt.timezone.utc)
    if response.status_code == 404:
        return {"status": "not_listed", "checked_at": checked.isoformat(),
                "observed_at": checked.isoformat()}
    response.raise_for_status()
    try:
        age = max(0, int(response.headers.get("age", 0)))
    except (TypeError, ValueError):
        return {"status": "source_error", "checked_at": checked.isoformat(),
                "observed_at": checked.isoformat()}
    quote = parse_quote(response.json(), match.kambi_id, match.match_start, checked)
    if age > MAX_AGE_S:
        quote = {"status": "stale"}
    return {**quote, "checked_at": checked.isoformat(),
            "observed_at": (checked-dt.timedelta(seconds=age)).isoformat()}


def collect(store, product, draw, varv):
    """Högst tre anrop per gemensamt basvarv, 15 min cooldown per provider-id."""
    if draw.state != "Open" or product == "bomben":
        return 0
    if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='pool_reserve_quote'").fetchone():
        return 0  # explicit backup/migrering krävs innan insamlingen aktiveras
    now = dt.datetime.now(dt.timezone.utc)
    sharp = store.get_sharp(product, draw.draw_number)
    count = 0
    def save(m, quote):
        values = [product,draw.draw_number,m.event_number,SOURCE,str(m.kambi_id),
                  *[quote.get(k) for k in ("checked_at","observed_at","status","line",
                      "over_odds","under_odds","match_start","home","away")],VERSION]
        return store.conn.execute("INSERT OR IGNORE INTO pool_reserve_quote VALUES ("+
                                  ",".join("?" for _ in values)+")",values).rowcount
    # Basvarven kan ligga längre isär än cooldown. Utan åldersordning
    # förbrukar samma tre första matcher budgeten för alltid.
    checked = {row['provider_event_id']: row['checked_at'] for row in
               store.conn.execute("SELECT provider_event_id, MAX(checked_at) AS checked_at "
                   "FROM pool_reserve_quote WHERE source=? GROUP BY provider_event_id", (SOURCE,))}
    oldest = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    for m in sorted(draw.matches, key=lambda m: (
            _time(checked.get(str(m.kambi_id))) or oldest, m.event_number)):
        total = (sharp.get(m.event_number) or {}).get("total") or {}
        if (not m.kambi_id or m.cancelled or not _time(m.match_start)
                or _time(m.match_start) <= now or total.get("line") is not None):
            continue
        last = store.conn.execute("SELECT * FROM pool_reserve_quote WHERE source=? "
            "AND provider_event_id=? ORDER BY checked_at DESC LIMIT 1", (SOURCE,str(m.kambi_id))).fetchone()
        if last and _time(last['checked_at']) and (now-_time(last['checked_at'])).total_seconds() < COOLDOWN_S:
            # Samma providerobservation får betjäna flera poolprodukter,
            # men ALDRIG få en ny observations- eller hämtningstid.
            quote = dict(last)
            if (quote['status'] != 'available' or (_time(quote['match_start']) and
                    abs((_time(quote['match_start'])-_time(m.match_start)).total_seconds()) <= 900)):
                count += save(m, quote)
            continue
        if (getattr(varv, "reserve_calls", 0) >= MAX_CALLS
                or time.monotonic() >= getattr(varv, "reserve_deadline", float('inf'))):
            continue
        if not hasattr(varv, "reserve_calls"):
            varv.reserve_calls, varv.reserve_deadline = 0, time.monotonic()+8
        varv.reserve_calls += 1
        try:
            quote = fetch_quote(m)
        except Exception:  # nät-/parsefel är inte frånvaro
            checked = dt.datetime.now(dt.timezone.utc).isoformat()
            quote = {"status": "source_error", "checked_at": checked, "observed_at": checked}
        last_observation = store.conn.execute("SELECT MAX(observed_at) FROM pool_reserve_quote "
            "WHERE source=? AND provider_event_id=? AND status NOT IN ('source_error','stale')",
            (SOURCE,str(m.kambi_id))).fetchone()[0]
        if last_observation and _time(quote['observed_at']) < _time(last_observation):
            quote = {**quote, "status": "stale"}
        count += save(m, quote)
    store.conn.commit()
    return count


def read_for_draw(store, product, draw_number, now=None):
    """Ren läsning. Ett källfel raderar inte senaste färska observationen."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='pool_reserve_quote'").fetchone():
        return {}
    rows = store.conn.execute("SELECT * FROM pool_reserve_quote WHERE product=? AND draw_number=? "
                              "ORDER BY checked_at DESC",(product,draw_number)).fetchall()
    result, errors = {}, set()
    for row in rows:
        r = dict(row); ev = r["event_number"]
        if ev in result:
            continue
        if r["status"] in ("source_error", "stale"):
            errors.add(ev)
            continue
        observed, start = _time(r["observed_at"]), _time(r["match_start"])
        fresh = observed and 0 <= (now-observed).total_seconds() <= MAX_AGE_S
        available = r["status"] == "available" and fresh and start and start > now
        result[ev] = {**r, "available": bool(available), "source_error": ev in errors,
                      "label": "SvS/Kambi · reserv", "used_by_builder": False}
    for ev in errors-result.keys():
        result[ev] = {"available":False,"status":"source_error","label":"SvS/Kambi · reserv",
                      "used_by_builder":False}
    return result
