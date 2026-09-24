"""Providerseparerat Ö/U-reservunderlag. Aldrig sharp eller bygginput."""
from __future__ import annotations

import datetime as dt
import math
import time
from types import SimpleNamespace

import httpx

from . import kambi

VERSION = "pool-reserve-ou-v1"
SOURCE = "svenskaspel_kambi"
MAX_AGE_S = 1800
COOLDOWN_S = 900
MAX_CALLS = 3
BUDGET_S = 8
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


def _has_table(store):
    # Explicit backup/migrering krävs innan insamlingen aktiveras.
    return bool(store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                   "AND name='pool_reserve_quote'").fetchone())


def _queue(varv):
    queue = getattr(varv, "reserve_queue", None)
    if queue is None:
        queue = varv.reserve_queue = []
    return queue


def _last_checks(store, provider_ids):
    """Senaste kontroll per provider-id, jämförd som TID — aldrig som sträng."""
    ids = sorted(set(provider_ids))
    latest = {}
    if not ids:
        return latest
    for pid, checked in store.conn.execute(
            "SELECT provider_event_id, checked_at FROM pool_reserve_quote WHERE source=? "
            f"AND provider_event_id IN ({','.join('?' for _ in ids)})", (SOURCE, *ids)):
        t = _time(checked)
        if t and (pid not in latest or t > latest[pid]):
            latest[pid] = t
    return latest


def _closed(candidate, now):
    """Stängd omgång eller startad match: ingen kandidat, inget anrop."""
    start = _time(candidate.match.match_start)
    return (start is None or start <= now
            or (candidate.close is not None and candidate.close <= now))


def _shareable(quote, match):
    """Samma providerobservation får betjäna flera poolprodukter, men en
    tillgänglig quote bara när Kambis avspark stämmer med kandidatens."""
    start, expected = _time(quote.get("match_start")), _time(match.match_start)
    return (quote.get("status") != "available"
            or bool(start and expected and abs((start-expected).total_seconds()) <= 900))


def _save(store, candidate, quote):
    values = [candidate.product, candidate.draw_number, candidate.match.event_number,
              SOURCE, candidate.provider_id,
              *[quote.get(k) for k in ("checked_at","observed_at","status","line",
                  "over_odds","under_odds","match_start","home","away")], VERSION]
    return store.conn.execute("INSERT OR IGNORE INTO pool_reserve_quote VALUES ("+
                              ",".join("?" for _ in values)+")", values).rowcount


def register(store, product, draw, varv, now=None):
    """Registrera omgångens kandidater i varvets gemensamma kö. INGA nätanrop.

    Anropen görs av `run_queue` efter produktloopen (statusauditen
    2026-09-24, fynd C3): när varje produkt anropade direkt tog
    stryktipset/europatipset hela varvets budget och senare
    Topptipset-omgångar stängde utan en enda kontroll.

    En match räknas som att sakna Pinnacle-total när dess cachade sharp inte
    passerar pool-sharp-freshness-v1 — ett gammalt eller länktappat pris får
    inte hålla reserven borta. `now` injiceras av tester. Returnerar antalet
    nya kandidater."""
    if draw.state != "Open" or product == "bomben" or not _has_table(store):
        return 0
    from .pool_sharp_freshness import fresh_sharp
    now = now or dt.datetime.now(dt.timezone.utc)
    close = _time(getattr(draw, "reg_close_time", None))
    queue = _queue(varv)
    queued = {(c.product, c.draw_number, c.match.event_number) for c in queue}
    sharp, _stale = fresh_sharp(store, product, draw.draw_number, now)
    wanted = []
    for m in draw.matches:
        total = (sharp.get(m.event_number) or {}).get("total") or {}
        if (not m.kambi_id or m.cancelled or total.get("line") is not None
                or (product, draw.draw_number, m.event_number) in queued):
            continue
        candidate = SimpleNamespace(product=product, draw_number=draw.draw_number,
                                    match=m, provider_id=str(m.kambi_id), close=close)
        if not _closed(candidate, now):
            wanted.append(candidate)
    checks = _last_checks(store, [c.provider_id for c in wanted])
    for candidate in wanted:
        candidate.last_check = checks.get(candidate.provider_id)
        queue.append(candidate)
    return len(wanted)


def run_queue(store, varv, now=None, clock=time.monotonic):
    """Gör varvets reservanrop EFTER produktloopen, gemensamt för alla produkter.

    Högst MAX_CALLS anrop per basvarv (och BUDGET_S från första anropet) i
    ordningen: aldrig kontrollerad först, därefter äldst kontroll, därefter
    närmast spelstopp. Ett provider-id som delas av flera produkter kostar ETT
    anrop och svaret sparas för alla. 15 min cooldown per provider-id: inom
    den görs inget nytt anrop, men samma providerobservation får betjäna
    flera poolprodukter — ALDRIG med ny observations- eller hämtningstid.
    checked_at/observed_at sätts av `fetch_quote` efter varje anrop.
    Reserven är presentation (`used_by_builder=False`): aldrig bygg-, PIT-
    eller CLV-input. Kön töms, så en andra körning dubbelräknar inget."""
    queue = list(getattr(varv, "reserve_queue", None) or [])
    varv.reserve_queue = []
    report = {"candidates": len(queue), "calls": 0, "saved": 0, "cooldown": 0,
              "unserved": 0, "called": []}
    if not queue or not _has_table(store):
        return report
    now = now or dt.datetime.now(dt.timezone.utc)
    groups = {}
    for candidate in queue:
        if not _closed(candidate, now):
            groups.setdefault(candidate.provider_id, []).append(candidate)
    oldest = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    latest = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    due = []
    for pid, members in groups.items():
        members.sort(key=lambda c: c.close or latest)    # närmast spelstopp först
        rows = [dict(row) for row in store.conn.execute(
            "SELECT * FROM pool_reserve_quote WHERE source=? AND provider_event_id=?",
            (SOURCE, pid))]
        last = max(rows, key=lambda row: _time(row["checked_at"]) or oldest, default=None)
        last_at = _time(last["checked_at"]) if last else None
        if last_at and (now-last_at).total_seconds() < COOLDOWN_S:
            report["cooldown"] += 1
            report["saved"] += sum(_save(store, c, last) for c in members
                                   if _shareable(last, c.match))
            continue
        checked = min((c.last_check for c in members if c.last_check), default=None)
        due.append(((checked is not None, checked or oldest, members[0].close or latest),
                    members, rows))
    due.sort(key=lambda item: item[0])
    for key, members, rows in due:
        if (getattr(varv, "reserve_calls", 0) >= MAX_CALLS
                or clock() >= getattr(varv, "reserve_deadline", float("inf"))):
            report["unserved"] += 1
            continue
        if not hasattr(varv, "reserve_deadline"):
            varv.reserve_deadline = clock() + BUDGET_S
        varv.reserve_calls = getattr(varv, "reserve_calls", 0) + 1
        head = members[0]
        try:
            quote = fetch_quote(head.match)
        except Exception:  # nät-/parsefel är inte frånvaro
            checked = dt.datetime.now(dt.timezone.utc).isoformat()
            quote = {"status": "source_error", "checked_at": checked, "observed_at": checked}
        last_observation = max((t for t in (_time(row["observed_at"]) for row in rows
                                            if row["status"] not in ("source_error", "stale"))
                                if t), default=None)
        if last_observation and _time(quote["observed_at"]) < last_observation:
            quote = {**quote, "status": "stale"}
        report["calls"] += 1
        report["saved"] += _save(store, head, quote)
        report["saved"] += sum(_save(store, c, quote) for c in members[1:]
                               if _shareable(quote, c.match))
        report["called"].append({"product": head.product, "draw_number": head.draw_number,
                                 "event_number": head.match.event_number,
                                 "provider_id": head.provider_id, "shared": len(members)-1,
                                 "never_checked": not key[0], "status": quote.get("status")})
    store.conn.commit()
    return report


def summary_line(report):
    """En rad till den append-only poolloggen: vilka id:n kön valde och varför."""
    called = ", ".join(
        f"{c['product']} {c['draw_number']} #{c['event_number']} (id {c['provider_id']}, "
        f"{'aldrig kontrollerad' if c['never_checked'] else 'äldst kontroll'}, {c['status']}"
        + (f", delad med {c['shared']}" if c['shared'] else "") + ")"
        for c in report["called"])
    return (f"Ö/U-reserv: {report['calls']} anrop av {report['candidates']} kandidater "
            f"({report['cooldown']} id i cooldown, {report['unserved']} id utan budget, "
            f"{report['saved']} rader sparade)" + (f": {called}" if called else "."))


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
