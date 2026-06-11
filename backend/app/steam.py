"""Steam = devigade sannolikhetsskift över tidsfönster (6/24/72 h).

Rå oddsrörelse blandar ihop marginalbrus med riktig rörelse och är inte
jämförbar mellan favoriter och skrällar (1.50→1.45 är stort, 21→19 är brus).
Devigad sannolikhet i procentenheter löser båda: power-devig av Pinnacles
1X2 vid två tidpunkter, skiftet är direkt jämförbart. (Mönster från VM-kollen.)

🔥-flaggan och ntfy-notisen använder 24h-skiftet (eller äldsta mätningen om
serien är kortare) i stället för rå odds-diff.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .analysis import _power_probs
from .storage import Storage

SIGNS = ("1", "X", "2")
WINDOWS_H = (6.0, 24.0, 72.0)


def _parse(ts: str) -> Optional[dt.datetime]:
    try:
        d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def _series_per_event(rows: list[dict]) -> dict[int, list[tuple[dt.datetime, str, float]]]:
    out: dict[int, list] = {}
    for r in rows:
        t = _parse(r["fetched_at"])
        if t:
            out.setdefault(r["event_number"], []).append((t, r["sign"], r["odds"]))
    return out


def _probs_at(series: list[tuple], t: dt.datetime) -> Optional[dict[str, float]]:
    """Devigade sannolikheter vid tidpunkt t = sista odds per tecken ≤ t.
    Kräver att alla tre tecknen har data senast t."""
    last: dict[str, float] = {}
    for ts, sign, odds in series:        # serien är tidsordnad
        if ts > t:
            break
        last[sign] = odds
    if not all(s in last for s in SIGNS):
        return None
    return _power_probs({s: 1.0 / o for s, o in last.items()})


def steam_table(store: Storage, product: str, draw_number: int) -> list[dict]:
    """Per (match, tecken): devigad sannolikhet nu + skift i procentenheter
    mot 6/24/72 h sedan. Sorterad efter största |skift| (färskaste fönstret)."""
    rows = store.sharp_history_all(product, draw_number)
    if not rows:
        return []
    per_event = _series_per_event(rows)
    now = max(t for ser in per_event.values() for t, _, _ in ser)
    out: list[dict] = []
    for ev, ser in per_event.items():
        p_now = _probs_at(ser, now)
        if not p_now:
            continue
        first_t = ser[0][0]
        shifts: dict[str, dict[str, Optional[float]]] = {s: {} for s in SIGNS}
        for w in WINDOWS_H:
            t_then = now - dt.timedelta(hours=w)
            p_then = _probs_at(ser, t_then) if t_then >= first_t else None
            for s in SIGNS:
                shifts[s][f"{w:g}"] = round((p_now[s] - p_then[s]) * 100, 1) if p_then else None
        for s in SIGNS:
            sh = shifts[s]
            primary = next((sh[k] for k in ("6", "24", "72") if sh[k] is not None), None)
            out.append({"event_number": ev, "sign": s,
                        "p_now": round(p_now[s], 4), "pp": sh, "primary": primary})
    out.sort(key=lambda r: abs(r["primary"] or 0), reverse=True)
    return out


def movement_with_steam(store: Storage, product: str, draw_number: int) -> dict:
    """Rörelse-dict till analyze_draw: oddsrörelse (sharp först, SvS-fallback)
    + folkets streck-rörelse + devigat steam-skift (24h-fönstret, annars hela
    serien). Delas av API:t och notiserna så 🔥-logiken är identisk."""
    movement = store.sharp_movement(product, draw_number) \
        or store.movement(product, draw_number)
    streck_mv = store.streck_movement(product, draw_number)

    steam_pp: dict[tuple[int, str], float] = {}
    rows = store.sharp_history_all(product, draw_number)
    if rows:
        per_event = _series_per_event(rows)
        now = max(t for ser in per_event.values() for t, _, _ in ser)
        for ev, ser in per_event.items():
            p_now = _probs_at(ser, now)
            if not p_now:
                continue
            t24 = now - dt.timedelta(hours=24)
            p_then = _probs_at(ser, t24) if t24 >= ser[0][0] else _probs_at(ser, ser[0][0])
            if not p_then:
                continue
            for s in SIGNS:
                steam_pp[(ev, s)] = round((p_now[s] - p_then[s]) * 100, 1)

    merged: dict = {}
    for k in set(movement) | set(streck_mv) | set(steam_pp):
        e = dict(movement.get(k, {}))
        sm = streck_mv.get(k)
        if sm:
            e["streck_first"], e["streck_last"] = sm["first"], sm["last"]
        if k in steam_pp:
            e["steam_pp"] = steam_pp[k]
        merged[k] = e
    return merged
