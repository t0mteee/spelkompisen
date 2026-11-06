"""Providerseparerat Ö/U-reservunderlag (Svenska Spel/Kambi).

Aldrig sharp, PIT eller CLV. Sedan pool-draw-risk-v2 (Samans beslut
2026-11-06, "X-skydd via Kambi") är Kambis lina BYGGINPUT på en enda plats:
X-skyddets total när Pinnacle-totalen saknas (`build_totals` +
`builder.apply_reserve_totals`). Inför en frysning hämtas omgångens linor
direkt (`refresh_for_build`) så att bygget har en färsk observation."""
from __future__ import annotations

import datetime as dt
import math
import time
from types import SimpleNamespace

import httpx

from . import kambi

# v2 sedan 2026-09-24: gemensam kö per basvarv (fynd C3) i stället för
# produktordning. v3 (2026-11-06, pool-draw-risk-v2): kön får 12 anrop per
# basvarv (ett anrop tar ~0,1 s, Age 0) och frysningen hämtar sina egna linor
# via `refresh_for_build`. Samma journal och tolkning; äldre rader ligger kvar.
VERSION = "pool-reserve-ou-v3"
SOURCE = "svenskaspel_kambi"
MAX_AGE_S = 1800
COOLDOWN_S = 900
MAX_CALLS = 12
BUDGET_S = 8
# Byggets färskhet: samma 90 min som pool-sharp-freshness-v1 ger Pinnacle.
BUILD_MAX_AGE_S = 5400
# Före en frysning: hämta om en lina som kontrollerats för mer än 5 min sedan.
BUILD_REFRESH_S = 300
BUILD_MAX_CALLS = 40      # per varv, alla produkter tillsammans
BUILD_BUDGET_S = 12
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
    Kön är visningens underlag; byggets linor hämtas av `refresh_for_build`
    och läses av `build_totals`. Aldrig PIT- eller CLV-input. Kön töms, så en
    andra körning dubbelräknar inget."""
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


def _rows_until(store, product, draw_number, now):
    """Omgångens rader kontrollerade senast `now`, senaste kontroll först —
    sorterat som TID (aldrig som text). En rad efter as-of finns inte."""
    oldest = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    rows = [row for row in store.conn.execute(
        "SELECT * FROM pool_reserve_quote WHERE product=? AND draw_number=?",
        (product, draw_number)).fetchall()
        if (_time(row["checked_at"]) or now) <= now]
    return sorted(rows, key=lambda row: _time(row["checked_at"]) or oldest,
                  reverse=True)


def build_totals(store, product, draw_number, at):
    """pool-draw-risk-v2: Kambis Ö/U-lina per match som BYGGET får använda.

    Senaste kontroll ≤ `at` per match (källfel och `stale` hoppas över, som i
    visningen); den måste vara `available`, observerad ≤ `at` och högst
    BUILD_MAX_AGE_S gammal vid `at`, och matchen får inte ha startat. Ren
    läsning med injicerad as-of: samma anrop ger samma svar i appen, PH3,
    spelai och i efterhandsgranskningen."""
    if not _has_table(store):
        return {}
    out, seen = {}, set()
    for row in _rows_until(store, product, draw_number, at):
        r = dict(row); ev = r["event_number"]
        if ev in seen or r["status"] in ("source_error", "stale"):
            continue
        seen.add(ev)
        observed, start = _time(r["observed_at"]), _time(r["match_start"])
        if (r["status"] == "available" and r["line"] is not None and observed
                and 0 <= (at-observed).total_seconds() <= BUILD_MAX_AGE_S
                and start and start > at):
            out[ev] = {"line": r["line"], "over_odds": r["over_odds"],
                       "under_odds": r["under_odds"], "observed_at": r["observed_at"],
                       "source": SOURCE}
    return out


def refresh_for_build(store, product, draw, sharp, varv=None, now=None):
    """Hämta Kambis Ö/U för omgångens matcher utan Pinnacle-total, inför en
    frysning (PH3 eller spelai). Anropas FÖRE frysningens klocka sätts, så
    att observationen ligger före as-of.

    Ett provider-id kontrollerat inom BUILD_REFRESH_S anropas inte igen; den
    observationen sparas för produkten om den saknas (samma regel som kön:
    aldrig med ny tid). Högst BUILD_MAX_CALLS anrop och BUILD_BUDGET_S per
    varv. Nät-/parsefel sparas som source_error, aldrig som frånvaro."""
    report = {"calls": 0, "saved": 0, "fresh": 0, "unserved": 0}
    if draw.state != "Open" or product == "bomben" or not _has_table(store):
        return report
    now = now or dt.datetime.now(dt.timezone.utc)
    varv = varv if varv is not None else SimpleNamespace()
    close = _time(getattr(draw, "reg_close_time", None))
    for m in draw.matches:
        total = (sharp.get(m.event_number) or {}).get("total") or {}
        if not m.kambi_id or m.cancelled or total.get("line") is not None:
            continue
        candidate = SimpleNamespace(product=product, draw_number=draw.draw_number,
                                    match=m, provider_id=str(m.kambi_id), close=close)
        if _closed(candidate, now):
            continue
        rows = [dict(row) for row in store.conn.execute(
            "SELECT * FROM pool_reserve_quote WHERE source=? AND provider_event_id=?",
            (SOURCE, candidate.provider_id))]
        oldest = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        last = max(rows, key=lambda row: _time(row["checked_at"]) or oldest, default=None)
        last_at = _time(last["checked_at"]) if last else None
        if last_at and 0 <= (now-last_at).total_seconds() < BUILD_REFRESH_S:
            report["fresh"] += 1
            if _shareable(last, m):
                report["saved"] += _save(store, candidate, last)
            continue
        if (getattr(varv, "build_calls", 0) >= BUILD_MAX_CALLS
                or time.monotonic() >= getattr(varv, "build_deadline", float("inf"))):
            report["unserved"] += 1
            continue
        if not hasattr(varv, "build_deadline"):
            varv.build_deadline = time.monotonic() + BUILD_BUDGET_S
        varv.build_calls = getattr(varv, "build_calls", 0) + 1
        try:
            quote = fetch_quote(m)
        except Exception:  # nät-/parsefel är inte frånvaro
            checked = dt.datetime.now(dt.timezone.utc).isoformat()
            quote = {"status": "source_error", "checked_at": checked, "observed_at": checked}
        last_observation = max((t for t in (_time(row["observed_at"]) for row in rows
                                            if row["status"] not in ("source_error", "stale"))
                                if t), default=None)
        if last_observation and _time(quote["observed_at"]) < last_observation:
            quote = {**quote, "status": "stale"}
        report["calls"] += 1
        report["saved"] += _save(store, candidate, quote)
    store.conn.commit()
    return report


def read_for_draw(store, product, draw_number, now=None):
    """Ren läsning. Ett källfel raderar inte senaste färska observationen."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if not store.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='pool_reserve_quote'").fetchone():
        return {}
    rows = _rows_until(store, product, draw_number, now)
    result, errors = {}, set()
    for row in rows:
        r = dict(row); ev = r["event_number"]
        if ev in result:
            continue
        if r["status"] in ("source_error", "stale"):
            errors.add(ev)
            continue
        observed, start = _time(r["observed_at"]), _time(r["match_start"])
        fresh = observed and 0 <= (now-observed).total_seconds() <= BUILD_MAX_AGE_S
        available = r["status"] == "available" and fresh and start and start > now
        # used_by_builder sätts av anroparen när X-skyddet faktiskt fick linan
        # (build_totals har längre färskhet än visningens MAX_AGE_S).
        result[ev] = {**r, "available": bool(available), "source_error": ev in errors,
                      "label": "SvS/Kambi", "used_by_builder": False}
    for ev in errors-result.keys():
        result[ev] = {"available":False,"status":"source_error","label":"SvS/Kambi",
                      "used_by_builder":False}
    return result
