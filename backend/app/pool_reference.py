"""Referenspriser för poolens 1X2 — ren PRESENTATION (pool-reference-v1).

Pinnacle spärrar Sverige sedan 2026-11-05 09:30Z, så poolen saknar sharp-
referens. Samans beslut 2026-11-06 (val "bara visning"): Smarkets och SBOBET
visas där Pinnacle-raden stod och räknas i underlagsvarningen. De går ALDRIG in
i analysens sannolikheter, bygget, PH3, PIT, X-skyddet, rörelser eller CLV —
att göra dem till poolens sharp vore en ny datagenererande process.

Kopplingen är EXAKT: poolmatchens Kambi-id (från Svenska Spels draw-payload) =
Oddset-matchens write-once `kambi_id`. Ingen namnmatchning. Priset måste vara
tillgängligt, bekräftat högst `oddset_value.PRICE_MAX_AGE_MIN` före as-of och
satt före as-of (WP2-prisregeln och observationstidsregeln).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

VERSION = "pool-reference-v1"
SOURCES = ("smarkets", "sbobet")       # prioritetsordning i visningen
LABELS = {"smarkets": "Smarkets", "sbobet": "SBOBET"}
SHORT = {"smarkets": "Sm", "sbobet": "SBO"}
SIGNS = ("1", "X", "2")


def _time(value: Optional[str]) -> Optional[dt.datetime]:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo else None


def _quote(market: Optional[dict], at: dt.datetime, max_age_min: int) -> Optional[dict]:
    if not market or not market.get("available"):
        return None
    if not all(isinstance(market.get(s), (int, float)) and market[s] > 1 for s in SIGNS):
        return None
    seen, changed = _time(market.get("last_seen_at")), _time(market.get("fetched_at"))
    if seen is None or changed is None or changed > at:
        return None          # priset sattes efter as-of: ingen observation då
    if seen < at - dt.timedelta(minutes=max_age_min):
        return None
    return {s: market[s] for s in SIGNS} | {"last_seen_at": market["last_seen_at"]}


def read_for_draw(store, draw, at: dt.datetime) -> dict[int, dict]:
    """{event_number: {källa: {"1","X","2","fair","last_seen_at","label","short"}}}.

    Bara färska, kompletta 1X2-priser. En match utan Kambi-id, utan Oddset-rad
    eller utan färskt pris saknas i svaret — aldrig en gissning."""
    from .oddset_value import PRICE_MAX_AGE_MIN, _devig
    by_kambi = {str(m.kambi_id): m.event_number
                for m in getattr(draw, "matches", []) if getattr(m, "kambi_id", None)}
    if not by_kambi:
        return {}
    marks = ",".join("?" * len(by_kambi))
    rows = store.conn.execute(
        f"SELECT id, kambi_id FROM oddset_matches WHERE kambi_id IN ({marks})",
        tuple(by_kambi)).fetchall()
    event_of = {r["id"]: by_kambi[str(r["kambi_id"])] for r in rows}
    if not event_of:
        return {}
    latest = store.oddset_latest(list(event_of))
    out: dict[int, dict] = {}
    for mid, event_number in event_of.items():
        for source in SOURCES:
            quote = _quote(((latest.get(mid) or {}).get(source) or {}).get("1x2"),
                           at, PRICE_MAX_AGE_MIN)
            if not quote:
                continue
            fair = _devig({s: quote[s] for s in SIGNS}, SIGNS)
            out.setdefault(event_number, {})[source] = {
                **quote, "fair": {s: round(p, 4) for s, p in (fair or {}).items()},
                "label": LABELS[source], "short": SHORT[source], "version": VERSION}
    return out
