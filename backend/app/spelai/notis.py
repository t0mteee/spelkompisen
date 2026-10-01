"""Notiser för facitsidan (designens avsnitt 9) via ntfy.

Ämnet läses ur `SPELAI_NTFY_TOPIC` i gitignorerade `backend/.env`. Saknas det
skickas ingenting — händelsen bokförs ändå i `spelai_event`. Detta återaktiverar
INTE Spelkompisens pausade odds-/signalnotiser (`NTFY_TOPIC`).

* En notis per spel och tidpunkt (6 h/30 min), samlad för alla nivåer.
* En notis per nytt beslut och per missat förslag.
* Tysta timmar 23–07 svensk tid — utom beslut med sista tid. En notis som
  hamnar i tysta timmar skjuts upp (kandidaterna härleds ur tabellerna), den
  försvinner inte; ett förslag vars spelstopp passerat skickas aldrig.
* Aldrig rader, insatser eller loggar — bara vad som hänt och en länk.
* Dedup per händelse-id: `spelai_event.dedup_key = notis:<id>`.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Callable, Optional

from ..svenskaspel import PRODUCTS
from . import tillstand
from .tillstand import LOCAL_TZ, iso, utc

TOPIC_ENV = "SPELAI_NTFY_TOPIC"
LINK_ENV = "SPELAI_NOTIS_LANK"
QUIET_FROM, QUIET_TO = 23, 7
LOOKBACK_H = 12
HORISONT_TEXT = {"6h": "förhandsversion 6 h", "30m": "officiellt förslag 30 min"}

Sender = Callable[[str, str, str, Optional[str]], bool]


def topic() -> Optional[str]:
    from .. import config  # noqa: F401 — laddar backend/.env om den finns
    return os.environ.get(TOPIC_ENV) or None


def tysta_timmar(now: dt.datetime) -> bool:
    hour = now.astimezone(LOCAL_TZ).hour
    return hour >= QUIET_FROM or hour < QUIET_TO


def ntfy_sender(topic_name: str, title: str, message: str,
                link: Optional[str]) -> bool:
    """ntfy:s JSON-publicering — UTF-8 i titeln utan headerkodning."""
    import httpx
    body = {"topic": topic_name, "title": title, "message": message,
            "tags": ["robot"]}
    if link:
        body["click"] = link
    try:
        response = httpx.post("https://ntfy.sh/", json=body, timeout=10)
        return response.status_code < 400
    except Exception:  # noqa: BLE001 — notiser får aldrig fälla tick
        return False


def _namn(product: str) -> str:
    return PRODUCTS.get(product, {}).get("name", product)


def kandidater(conn, *, now: dt.datetime) -> list[dict]:
    """Notiser som borde finnas, härledda ur tabellerna (dedup sker i skicka)."""
    since = now - dt.timedelta(hours=LOOKBACK_H)
    out: list[dict] = []
    groups: dict[tuple, dict] = {}
    for (product, draw_number, horizon, role, status, frozen_at,
         close_raw) in conn.execute(
            "SELECT product, draw_number, horizon, role, status, frozen_at, "
            "reg_close_time FROM spelai_pool_proposal ORDER BY id DESC LIMIT 2000"):
        frozen = utc(frozen_at)
        if frozen is None or frozen < since:
            continue
        g = groups.setdefault((product, draw_number, horizon), {
            "close": utc(close_raw), "statuses": {"agent": [], "standard": []}})
        g["statuses"][role].append(status)
    for (product, draw_number, horizon), g in groups.items():
        close = g["close"]
        stopp = close.astimezone(LOCAL_TZ).strftime("%H:%M") if close else "?"
        statuses = g["statuses"]
        alla = statuses["agent"] + statuses["standard"]
        namn = f"{_namn(product)} {draw_number}"
        if alla and all(s == "missat" for s in alla):
            out.append({"key": f"missat:{product}:{draw_number}:{horizon}",
                        "kind": "missat", "exempt": False, "close": close,
                        "title": "Poolförslag missat",
                        "message": f"{namn}: {HORISONT_TEXT[horizon]} frystes inte "
                                   f"i tid. Spelstopp {stopp}."})
            continue
        if all(s == "pausad" for s in alla):
            continue
        nivaer = len(statuses["standard"])
        ogiltiga = sum(1 for s in statuses["agent"] if s != "fryst")
        extra = (f" Agentens förslag saknas eller är ogiltigt på {ogiltiga} "
                 f"nivå{'er' if ogiltiga != 1 else ''} — standarden visas."
                 if ogiltiga else "")
        out.append({"key": f"pool:{product}:{draw_number}:{horizon}",
                    "kind": "pool", "exempt": False, "close": close,
                    "title": "Poolförslag klart",
                    "message": f"{namn}: {HORISONT_TEXT[horizon]} fryst för "
                               f"{nivaer} nivå{'er' if nivaer != 1 else ''}. "
                               f"Spelstopp {stopp}.{extra}"})
    for inbox_id, rubrik, sista, created in conn.execute(
            "SELECT id, rubrik, sista_tid, created_at FROM spelai_inbox "
            "WHERE typ='beslut' ORDER BY id DESC LIMIT 200"):
        created_at = utc(created)
        if created_at is None or created_at < since:
            continue
        sista_at = utc(sista)
        if sista_at is not None and sista_at < now:
            continue
        msg = "Ett nytt beslut väntar på ditt svar"
        if sista_at is not None:
            msg += f" senast {sista_at.astimezone(LOCAL_TZ).strftime('%d/%m %H:%M')}"
        out.append({"key": f"beslut:{inbox_id}", "kind": "beslut",
                    "exempt": sista_at is not None, "close": None,
                    "title": "Nytt beslut", "message": f"{msg}: {rubrik[:120]}"})
    return out


def skicka(conn, *, now: dt.datetime, sender: Optional[Sender] = None,
           topic_name: Optional[str] = None, link: Optional[str] = None) -> dict:
    """Skicka nya notiser. `sender` injiceras i testerna; i drift ntfy."""
    report = {"skickade": 0, "uppskjutna": 0, "utan_amne": 0, "fel": 0}
    link = link if link is not None else (os.environ.get(LINK_ENV) or None)
    quiet = tysta_timmar(now)
    for item in kandidater(conn, now=now):
        dedup = f"notis:{item['key']}"
        if tillstand.har_handelse(conn, dedup):
            continue
        if item["close"] is not None and item["close"] <= now:
            continue     # spelstoppet har passerat — notisen har inget värde
        if quiet and not item["exempt"]:
            report["uppskjutna"] += 1
            continue
        detail = {"kind": item["kind"], "title": item["title"]}
        if not topic_name:
            tillstand.logga(conn, "notis", item["key"],
                            {**detail, "skickad": False, "orsak": "ämne saknas"},
                            now=now, dedup_key=dedup)
            report["utan_amne"] += 1
            continue
        ok = (sender or ntfy_sender)(topic_name, item["title"], item["message"], link)
        if ok:
            tillstand.logga(conn, "notis", item["key"], {**detail, "skickad": True},
                            now=now, dedup_key=dedup)
            report["skickade"] += 1
        else:
            tillstand.logga(conn, "notis_fel", item["key"], detail, now=now)
            report["fel"] += 1
    return report
