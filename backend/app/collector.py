"""Bakgrundsinsamlare som kan startas/stoppas från webb-UI:t.

Kör i en daemon-tråd och tar ett snapshot med jämna mellanrum (sparar bara
vid förändring tack vare storage-dedup). Ett enklare alternativ till launchd
när man vill kunna slå på/av insamlingen med en knapp.

Obs: lever bara så länge backend-processen kör. För insamling dygnet runt även
när datorn/servern startas om, använd launchd-jobbet i scripts/ istället.
"""
from __future__ import annotations

import datetime as dt
import threading
from typing import Optional

from . import sharp_service
from .storage import Storage
from .svenskaspel import SvenskaSpel

MIN_INTERVAL = 60  # sekunder — skydd mot att spamma API:t


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Collector:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.running = False
        self.interval = 1800
        self.product = "stryktipset"
        self.last_run: Optional[str] = None
        self.last_result: Optional[str] = None
        self.runs = 0
        self.saved_total = 0
        self.started_at: Optional[str] = None

    def status(self) -> dict:
        return {
            "running": self.running,
            "interval": self.interval,
            "product": self.product,
            "runs": self.runs,
            "saved_total": self.saved_total,
            "last_run": self.last_run,
            "last_result": self.last_result,
            "started_at": self.started_at,
        }

    def start(self, interval: Optional[int] = None,
              product: Optional[str] = None) -> dict:
        with self._lock:
            if self.running:
                return self.status()
            if interval:
                self.interval = max(MIN_INTERVAL, int(interval))
            if product:
                self.product = product
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self.running = True
            self.started_at = _now()
            self._thread.start()
        return self.status()

    def stop(self) -> dict:
        with self._lock:
            self._stop.set()
            self.running = False
        return self.status()

    def _loop(self) -> None:
        self._tick()                                  # kör direkt vid start
        while not self._stop.wait(self.interval):     # sedan var interval:te sek
            self._tick()

    def _tick(self) -> None:
        try:
            with SvenskaSpel() as ss:
                draw = ss.get_current_draw(self.product)
            if not draw:
                self.last_result = "ingen öppen omgång"
            else:
                store = Storage()
                try:
                    rows = store.save_snapshot_if_changed(draw)
                finally:
                    store.close()
                self.saved_total += rows
                # uppdatera även sharp (Pinnacle, gratis) så 1X2 plockas upp
                # automatiskt så fort de öppnas inför avspark
                sharp_n = 0
                try:
                    res = sharp_service.collect_pinnacle(self.product, draw=draw, cache=True)
                    sharp_n = len(res["hits"]) if res else 0
                except Exception:  # noqa: BLE001 — sharp får aldrig stoppa SS-insamlingen
                    sharp_n = -1
                self.last_result = (f"sparade {rows} ändrade rader, "
                                    f"sharp {sharp_n} matcher (omgång {draw.draw_number})")
            self.runs += 1
            self.last_run = _now()
        except Exception as e:  # noqa: BLE001 — vill aldrig krascha tråden
            self.last_result = f"fel: {e}"
            self.last_run = _now()


# modulglobal singleton
collector = Collector()
