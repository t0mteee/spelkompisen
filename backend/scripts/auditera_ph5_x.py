"""Läsande audit av X-vikten i PH5:s frysta 5 000-raderskuponger.

Varje match räknas per metod och fryshorisont. Det här är alltså diagnostik av
radbyggarens beslut, inte antalet unika fotbollsmatcher. Skriptet skriver
aldrig databasen och får köras mot produktionsfilen.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pool_system_ledger import _bench  # noqa: E402
from app.storage import Storage            # noqa: E402


def audit(store: Storage) -> dict:
    groups: dict[tuple[str, str, str], dict] = collections.defaultdict(
        lambda: {"freezes": 0, "event_decisions": 0, "x_signs": 0,
                 "all_signs": 0, "x_omitted": 0, "x_outcomes": 0,
                 "x_outcomes_omitted": 0})
    misses = []
    rows = store.conn.execute(
        "SELECT product,draw_number,horizon,config_key,events_order,rows_text "
        "FROM pool_system_ledger WHERE config_key LIKE 'ph5-v3-b5000-%' "
        "ORDER BY product,draw_number,horizon,config_key").fetchall()
    for product, draw, horizon, config, events_text, rows_text in rows:
        method = _bench(config)["method"]
        key = (product, method, horizon)
        group = groups[key]
        group["freezes"] += 1
        events = [int(value) for value in (events_text or "").split(",") if value]
        system_rows = [value.split(",") for value in
                       (rows_text or "").splitlines() if value]
        outcomes = {int(event): outcome for event, outcome in store.conn.execute(
            "SELECT event_number,outcome FROM pool_event_settlement "
            "WHERE product=? AND draw_number=?", (product, draw))}
        for index, event in enumerate(events):
            x_count = sum(index < len(row) and row[index] == "X"
                          for row in system_rows)
            group["event_decisions"] += 1
            group["x_signs"] += x_count
            group["all_signs"] += len(system_rows)
            omitted = x_count == 0
            group["x_omitted"] += int(omitted)
            is_x = outcomes.get(event) == "X"
            group["x_outcomes"] += int(is_x)
            group["x_outcomes_omitted"] += int(is_x and omitted)
            if is_x and omitted:
                misses.append({"product": product, "draw": int(draw),
                               "horizon": horizon, "method": method,
                               "event": event})
    report = []
    for (product, method, horizon), values in sorted(groups.items()):
        report.append({
            "product": product, "method": method, "horizon": horizon,
            **values,
            "x_share": (values["x_signs"] / values["all_signs"]
                        if values["all_signs"] else None),
        })
    return {"groups": report, "x_outcomes_omitted": misses}


if __name__ == "__main__":
    store = Storage()
    try:
        print(json.dumps(audit(store), ensure_ascii=False, indent=2))
    finally:
        store.close()
