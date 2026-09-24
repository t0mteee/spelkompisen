"""pool-sharp-freshness-v1: när ett cachat Pinnacle-pris får användas i poolen.

`sharp_odds` är en LATEST-STATE-tabell (observationstidsregeln 7): den skrivs
bara när poolmatcharen träffar och rensas aldrig när länken tappas. Auditen
2026-09-24 fann att analysen, byggaren, PH3-frysningen, CLV-loggen, notiserna
och Ö/U-reserven läste priset via `Storage.get_sharp` utan ålderskontroll:
Europatipset 2610 match 10 visade ett pris från 08:17Z fast matcharen sagt
`ambiguous` sedan 08:47Z, Stryktipset 4971 frystes 19/9 med priser från 15/9
på 10 av 13 matcher och vid PH3-frysningarna sedan 10/9 var senaste
sharp-capture inte `matched` för ungefär 18 % av matcherna.

REGELN: ett pris för en match är användbart vid tiden t om och endast om
  (a) sharp_odds.fetched_at ≥ t − SHARP_MAX_AGE_MIN, och
  (b) ingen rad i `pool_market_capture` (source='sharp') för matchen med
      sharp_odds.fetched_at < fetched_at ≤ t har en status utanför
      LINK_STATUSES — länken har då observerats tappad EFTER priset.
Utan capture-rader gäller bara åldersregeln. Tider jämförs som tider
(databasen blandar `Z`, `+00:00` och `+02:00`), aldrig lexikografiskt.
Klockan injiceras alltid (regel 9): funktionerna har ingen standardklocka.

Regeln LÄSER bara. `sharp_odds`, `sharp_snapshots` och captures lämnas orörda
— inget raderas, inget bakfylls och ingen ny nättrafik tillkommer.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Iterable, Optional

VERSION = "pool-sharp-freshness-v1"

# Driftsättningen (första pooltick 14:12Z). Frysningar FÖRE denna tid läste
# det cachade priset utan ålderskontroll; efter den tog regeln bort det.
# Samma gräns som tillägget 2026-09-24 i docs/ph3-sannolikhetsbas-v1-2026-09-02.md.
IN_EFFECT_FROM = "2026-09-24T14:11:09Z"

# 90 min. Uppmätt 2026-09-24: ett LÄNKAT pris är i median 7–9 min gammalt vid
# PH3-frysningen. Basvarvet går var 30:e min, dubbeltrafikspärren kan skjuta
# en hämtning upp till 10 min och Pinnacles CDN-ålder (max-age 905 s) gör ett
# nyss hämtat pris upp till 15 min gammalt: strax före nästa lyckade basvarv
# kan ett friskt pris alltså vara ~55 min. 90 min tål ett missat basvarv men
# inte två — då har ingen lyckad läsning bekräftat priset på över en timme.
SHARP_MAX_AGE_MIN = 90

# Statusvärden som FAKTISKT finns i pool_market_capture (source='sharp',
# prod 2026-09-24): matched, not_listed, ambiguous (sedan 15/9), no_moneyline
# och derived (senast 4/9). `derived` = matchen hittad men 1X2 härledd ur
# spread/total; samma observation skriver sharp_odds, så den kan aldrig
# ligga EFTER priset. Allt annat betyder att länken inte bar ett 1X2-pris.
LINK_STATUSES = frozenset({"matched", "derived"})

# Orsaksetiketter (svenska) för länkstatus och åldersregeln.
REASON_LABELS = {
    "not_listed": "ej listad/namn",
    "ambiguous": "tvetydig",
    "no_moneyline": "ingen 1X2",
    "too_old": "för gammal",
    "never_observed": "aldrig observerad",
}

try:  # Sveriges klocka i förklaringstexterna; UTC om tz-databasen saknas.
    from zoneinfo import ZoneInfo
    _LOCAL = ZoneInfo("Europe/Stockholm")
except Exception:  # noqa: BLE001 — förklaringen får aldrig fälla analysen
    _LOCAL = None


def _parse(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _clock(now: dt.datetime) -> dt.datetime:
    """Den injicerade klockan i UTC. En naiv tid tolkas som UTC."""
    if not isinstance(now, dt.datetime):
        raise TypeError("pool_sharp_freshness kräver en injicerad klocka (datetime)")
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(dt.timezone.utc)


def as_of(reg_close_time: Optional[str], now: dt.datetime) -> dt.datetime:
    """Tiden en analys bedöms vid: nu, men aldrig efter spelstopp.

    En stängd omgång visas som den såg ut vid spelstoppet i stället för att
    varje pris ska kallas 'för gammalt' i efterhand. Öppna omgångar (alla
    insamlings- och frysvägar) får exakt `now`.
    """
    t = _clock(now)
    close = _parse(reg_close_time)
    return min(t, close) if close is not None else t


def _captures(store, product: str, draw_number: int,
              t: dt.datetime) -> dict[int, list[tuple]]:
    """{event: [(tid, status, rå_tid), …]} i tidsordning, bara captures ≤ t."""
    out: dict[int, list[tuple]] = {}
    for event, fetched_at, status in store.conn.execute(
            "SELECT event_number, fetched_at, status FROM pool_market_capture "
            "WHERE product=? AND draw_number=? AND source='sharp'",
            (product, draw_number)):
        at = _parse(fetched_at)
        if at is None or at > t:
            continue
        out.setdefault(int(event), []).append((at, str(status), fetched_at))
    for seq in out.values():
        seq.sort(key=lambda item: item[0])
    return out


def _split(raw: dict, captures: dict, t: dt.datetime) -> tuple[dict, dict]:
    oldest = t - dt.timedelta(minutes=SHARP_MAX_AGE_MIN)
    fresh: dict[int, dict] = {}
    stale: dict[int, dict] = {}
    for event, price in raw.items():
        seen = _parse(price.get("fetched_at"))
        seq = captures.get(int(event), ())
        lost = None
        if seen is not None:
            lost = next((capture for capture in seq
                         if capture[0] > seen and capture[1] not in LINK_STATUSES),
                        None)
        if lost is None and seen is not None and seen >= oldest:
            fresh[event] = price
            continue
        latest = seq[-1] if seq else None
        entry = {"reason": "link_lost" if lost else "too_old",
                 "last_seen": price.get("fetched_at"),
                 "status": latest[1] if latest else None,
                 "status_at": latest[2] if latest else None}
        if lost:
            # Första observationen som sa att länken inte längre bar priset.
            entry["lost_status"], entry["lost_at"] = lost[1], lost[2]
        stale[event] = entry
    return fresh, stale


def fresh_sharp(store, product: str, draw_number: int,
                now: dt.datetime) -> tuple[dict[int, dict], dict[int, dict]]:
    """Dela `store.get_sharp` i (fresh, stale) enligt regeln vid tiden `now`.

    `fresh` har exakt samma form som `get_sharp`. `stale[event]` förklarar
    varför priset togs bort: {"reason": "link_lost" | "too_old",
    "last_seen": sharp_odds.fetched_at, "status": senaste capture-status,
    "status_at": dess tid} och för link_lost även "lost_status"/"lost_at" =
    den första capturen efter priset som inte bar länken.
    """
    t = _clock(now)
    raw = store.get_sharp(product, draw_number)
    if not raw:
        return {}, {}
    return _split(raw, _captures(store, product, draw_number, t), t)


def coverage(store, product: str, draw_number: int, now: dt.datetime,
             events: Iterable[int]) -> dict:
    """Hur många av `events` som har färsk sharp och varför resten saknar den.

    Orsaksnyckeln är länkstatusen som tappade priset (`ambiguous`,
    `not_listed`, `no_moneyline`), `too_old`, senaste status för en match som
    aldrig fått ett pris, eller `never_observed` utan någon capture alls.
    """
    t = _clock(now)
    wanted = [int(event) for event in events]
    raw = store.get_sharp(product, draw_number)
    captures = _captures(store, product, draw_number, t)
    fresh, stale = _split(raw, captures, t)
    reasons: Counter = Counter()
    for event in wanted:
        if event in fresh:
            continue
        entry = stale.get(event)
        if entry is not None:
            key = (entry.get("lost_status") if entry["reason"] == "link_lost"
                   else "too_old")
        else:
            seq = captures.get(event)
            key = seq[-1][1] if seq else "never_observed"
        reasons[key or "never_observed"] += 1
    return {"version": VERSION, "n": len(wanted),
            "fresh": sum(event in fresh for event in wanted),
            "reasons": dict(reasons)}


def reason_label(key: Optional[str]) -> str:
    return REASON_LABELS.get(key or "", key or "okänd")


def local_time(value, now: Optional[dt.datetime] = None) -> str:
    """'10:47' samma svenska dygn som `now`, annars '15/9 10:17'."""
    at = _parse(value) if not isinstance(value, dt.datetime) else _clock(value)
    if at is None:
        return "okänd tid"
    local = at.astimezone(_LOCAL) if _LOCAL else at
    suffix = "" if _LOCAL else " UTC"
    same_day = (now is not None and
                (_clock(now).astimezone(_LOCAL) if _LOCAL else _clock(now)).date()
                == local.date())
    if same_day:
        return f"{local:%H:%M}{suffix}"
    return f"{local.day}/{local.month} {local:%H:%M}{suffix}"


def explain(entry: dict, now: dt.datetime) -> str:
    """En mening för UI:t, t.ex. 'Pinnacle-länken tappad (tvetydig) sedan 10:47'."""
    if entry.get("reason") == "link_lost":
        return (f"Pinnacle-länken tappad ({reason_label(entry.get('lost_status'))}) "
                f"sedan {local_time(entry.get('lost_at'), now)}")
    return (f"Pinnacle-priset äldre än {SHARP_MAX_AGE_MIN} min "
            f"(senast {local_time(entry.get('last_seen'), now)})")
