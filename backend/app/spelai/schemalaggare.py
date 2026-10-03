"""Schemaläggaren (`cli.py spelai-tick`, launchd `com.saman.spelai.schema`).

Varje tick: läs in utkorgen, frys de indatapaket som poolvarvet sparat
(respekterar paus), markera missade fönster, rätta mot facit, skicka
notiser, lägga och rätta livekassans fiktiva spel (`livekassa`, fas E) och
lämna rapporterna i agentens chatt i Claude-appen (`chattbud`,
sist eftersom budet tar upp mot en halv minut). Varje steg isoleras — ett
fel i ett steg bokförs som `tick_fel` och stoppar inte de andra.
Rollkörningar (fas F) startas inte här ännu.

Klockan injiceras (`clock`), liksom agentkörningen (`runner`), utkorgen,
notissändaren och chattbudet (`chatt_runner`, None = av), så att testerna
aldrig kör agentkod, skickar notiser eller meddelanden eller läser väggklockan.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Callable, Optional

from . import chattbud, frysning, inkorg, livekassa, notis, ratta, schema, tillstand

STEG = ("inkorg", "frysning", "missat", "rattning", "notiser", "livespel",
        "liverattning", "chatt")


def tick(store, *, runner, clock: Callable[[], dt.datetime],
         utkorg: Path = inkorg.UTKORG_DEFAULT, sender=None,
         topic_name: Optional[str] = None, code_version: str = "dev",
         chatt_runner=None, live_runner=None) -> dict:
    conn = store.conn
    if not schema.tables_exist(conn):
        return {"fel": "spelai-tabellerna saknas — kör scripts/migrera_spelai.py"}
    report: dict = {"pausad": tillstand.pausad(conn)}
    steps = (
        ("inkorg", lambda: inkorg.las_in(conn, utkorg, now=clock())),
        ("frysning", lambda: frysning.process_inputs(
            conn, runner, clock=clock, code_version=code_version)),
        ("missat", lambda: frysning.mark_missed(
            conn, now=clock(), code_version=code_version)),
        ("rattning", lambda: ratta.settle(store, now=clock())),
        ("notiser", lambda: notis.skicka(conn, now=clock(), sender=sender,
                                         topic_name=topic_name)),
        # Fas E: livekassan. `live_runner` None = av (testerna kör aldrig agentkod
        # och anropar aldrig Kambi eller Flashscore).
        ("livespel", lambda: livekassa.varv(store, runner=live_runner, clock=clock)),
        ("liverattning", lambda: livekassa.ratta(store, now=clock())
         if live_runner is not None else {}),
        ("chatt", lambda: chattbud.skicka(conn, now=clock(), runner=chatt_runner)),
    )
    for name, step in steps:
        try:
            report[name] = step()
        except Exception as exc:  # noqa: BLE001 — ett steg får inte fälla resten
            try:
                conn.rollback()
                tillstand.logga(conn, "tick_fel", name,
                                {"fel": f"{type(exc).__name__}: {exc}"[:500]},
                                now=clock())
            except Exception:  # noqa: BLE001
                pass
            report[name] = {"fel": f"{type(exc).__name__}: {exc}"}
    return report
