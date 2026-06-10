"""Push-notiser via ntfy.sh (gratis, ingen registrering).

Aktiveras genom att sätta NTFY_TOPIC i backend/.env (välj ett hemligt
topicnamn, t.ex. NTFY_TOPIC=saman-svs-x7k2) och prenumerera på samma topic
i ntfy-appen (iOS/Android) eller på https://ntfy.sh/<topic>. Utan topic är
notiserna avstängda och allt här är no-ops.

Notisen skickas när en match får 🔥-flaggan (markant SEN oddssänkning nära
avspark — vår starkaste köpsignal) och omgången stänger inom NOTIFY_WINDOW_H
timmar. En notis per (produkt, omgång, match), deduplicerat via meta-tabellen.
"""
from __future__ import annotations

import datetime as dt
import os

import httpx

from .analysis import analyze_draw
from .storage import Storage
from .svenskaspel import Draw

NOTIFY_WINDOW_H = 8.0   # notifiera bara när spelstopp är inom så här många timmar


def enabled() -> bool:
    return bool(os.getenv("NTFY_TOPIC"))


def push(title: str, message: str, tags: str = "fire") -> bool:
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return False
    try:
        httpx.post(f"https://ntfy.sh/{topic}", content=message.encode("utf-8"),
                   headers={"Title": title, "Priority": "high", "Tags": tags},
                   timeout=10)
        return True
    except Exception:  # noqa: BLE001 — notiser får aldrig fälla insamlingen
        return False


def check_movers(product: str, draw: Draw, store: Storage) -> int:
    """Pusha 🔥-rörelser för en omgång nära spelstopp. Returnerar antal skickade."""
    if not enabled() or not draw.reg_close_time:
        return 0
    try:
        close = dt.datetime.fromisoformat(draw.reg_close_time.replace("Z", "+00:00"))
        if close.tzinfo is None:
            close = close.replace(tzinfo=dt.timezone.utc)
        hrs = (close - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
    except (ValueError, TypeError):
        return 0
    if not (0 <= hrs <= NOTIFY_WINDOW_H):
        return 0

    # samma rörelse-sammanslagning som API:ts _analyze
    sharp = store.get_sharp(product, draw.draw_number)
    movement = store.sharp_movement(product, draw.draw_number) \
        or store.movement(product, draw.draw_number)
    streck_mv = store.streck_movement(product, draw.draw_number)
    merged: dict = {}
    for k in set(movement) | set(streck_mv):
        e = dict(movement.get(k, {}))
        sm = streck_mv.get(k)
        if sm:
            e["streck_first"], e["streck_last"] = sm["first"], sm["last"]
        merged[k] = e

    sent = 0
    for m in analyze_draw(draw, sharp, merged).matches:
        mv = m.mover
        if not mv or not mv.get("late"):
            continue
        key = f"notified_{product}_{draw.draw_number}_{m.event_number}"
        if store.meta_get(key):
            continue
        msg = (f"{m.description}\n{mv['label']}\n"
               f"Spelstopp om {hrs:.1f} h · {product} omg {draw.draw_number}")
        if push("Sen oddssänkning – het signal", msg):
            store.meta_set(key, dt.datetime.now(dt.timezone.utc).isoformat())
            sent += 1
    return sent
