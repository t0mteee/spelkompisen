"""Fyll `jackpot_close` för redan settlade omgångar ur snapshot-serien.

BAKGRUND (2026-09-02). `pool_draw_settlement` fick kolumnerna `jackpot_close`
och `jackpot_close_observed_at`: senast VERIFIERADE jackpotobservation i
`pool_draw_snapshot` vid eller före `regCloseTime`. Settlementet skriver dem
framåt; den här migreringen fyller dem för omgångar som settlades INNAN
kolumnerna fanns — men bara ur våra egna observationer (proveniens
`verified_endpoint`), aldrig ur `draw.fund` eller dagens jackpotlista.

Det är RESULTATSTATISTIK-bakfyllning i CLAUDE.md:s mening: observationen
gjordes vid rätt tid och ligger redan i DB; migreringen kopierar den till
settlementraden. En omgång utan verifierad observation före stängning förblir
NULL (oobserverad), aldrig 0.

Uppmätt före körning: 9 settlade omgångar (Stryktipset 3, Europatipset 6)
har en verifierad observation före stängning; snapshot-serien börjar
2026-07-24.

Kör:
    .venv/bin/python -B scripts/migrera_jackpot_close.py --dry-run
    .venv/bin/python -B scripts/migrera_jackpot_close.py --skarp
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pool_settlement import jackpot_at_close      # noqa: E402
from app.storage import Storage, DEFAULT_DB           # noqa: E402


KANDIDATER = """
SELECT product, draw_number, reg_close_time
  FROM pool_draw_settlement
 WHERE jackpot_close IS NULL AND reg_close_time IS NOT NULL
 ORDER BY reg_close_time
"""


def _backup(db_path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.stem}-backup-jackpot-{stamp}.db")
    # Onlinebackup ger en atomär SQLite-snapshot även när produktionsjobben
    # skriver samtidigt. En vanlig filkopiering kan få DB/WAL ur synk.
    with sqlite3.connect(db_path) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skarp", action="store_true", help="skriv (annars torrkörning)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    skarp = args.skarp and not args.dry_run

    db_path = Path(args.db)
    store = Storage(db_path)
    kandidater = list(store.conn.execute(KANDIDATER))
    traffar = []
    for product, draw_number, close in kandidater:
        jackpot, seen = jackpot_at_close(store, product, draw_number, close)
        if jackpot is not None:
            traffar.append((product, draw_number, close, jackpot, seen))
    print(f"settlade omgångar utan jackpot_close: {len(kandidater)}")
    print(f"med verifierad observation före stängning: {len(traffar)}")
    for product, draw_number, close, jackpot, seen in traffar:
        print(f"  {product} {draw_number} stängde {close}: "
              f"{jackpot:,.0f} kr observerad {seen}")
    if not traffar or not skarp:
        print("torrkörning — inget skrivet" if not skarp else "inget att skriva")
        store.close()
        return 0

    store.close()
    backup = _backup(db_path)
    print(f"backup: {backup}")
    store = Storage(db_path)
    with store.bulk():
        for product, draw_number, _close, jackpot, seen in traffar:
            store.conn.execute(
                "UPDATE pool_draw_settlement SET jackpot_close=?, "
                "jackpot_close_observed_at=? WHERE product=? AND draw_number=? "
                "AND jackpot_close IS NULL",
                (jackpot, seen, product, draw_number))
    kvar = store.conn.execute(
        "SELECT COUNT(*) FROM pool_draw_settlement WHERE jackpot_close IS NOT NULL"
    ).fetchone()[0]
    print(f"skrivet: {len(traffar)}; rader med jackpot_close nu: {kvar}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
