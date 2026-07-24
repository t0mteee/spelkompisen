"""PH2-helsvep: bygg PIT-features för ALLA lokalt observerade omgångar.

Läser snapshots/sharp_snapshots och fryser features per omgång/horisont
(observed_pit-kohorten). Idempotent per (nyckel, FEATURE_VERSION) — kan
köras om när som helst; redan byggda horisonter hoppas över. Löpande
underhåll sköts av snapshotvarvet (pool_dataset.build_recent).

Körning:
    cd backend && .venv/bin/python -B scripts/bygg_pit_dataset.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import pool_dataset  # noqa: E402
from app.storage import Storage  # noqa: E402


def main() -> None:
    store = Storage()
    try:
        draws = store.conn.execute(
            "SELECT DISTINCT s.product, s.draw_number, d.reg_close_time "
            "FROM snapshots s JOIN draws d "
            "ON d.product=s.product AND d.draw_number=s.draw_number "
            "WHERE d.reg_close_time IS NOT NULL "
            "ORDER BY s.product, s.draw_number").fetchall()
        total = {"built": 0, "skipped": 0}
        for product, draw_number, close in draws:
            rep = pool_dataset.build_draw(store, product, int(draw_number), close)
            total["built"] += rep["built"]
            total["skipped"] += rep["skipped"]
        print(f"{len(draws)} observerade omgångar -> {total['built']} nya "
              f"horisontrader, {total['skipped']} skippade (framtida/byggda/tomma)")
        for row in store.conn.execute(
                "SELECT product, horizon, COUNT(*), AVG(n_covered_sharp), "
                "AVG(n_covered_streck) FROM pool_pit_draw_features "
                "GROUP BY product, horizon ORDER BY product, horizon"):
            print(f"  {row[0]} {row[1]}: {row[2]} omgångar · "
                  f"sharp-täckning {row[3]:.1f} · streck {row[4]:.1f}")
    finally:
        store.close()


if __name__ == "__main__":
    main()
