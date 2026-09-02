"""Ta bort pit-total-v1-rader som skrevs FÖRE seriens deklarerade fönster.

BAKGRUND (2026-09-02, samma kväll som serien driftsattes). Första
`build_recent` efter driftsättningen byggde alla passerade horisonter för de
senaste omgångarna — även horisonter vars as-of låg veckor före
`sharp_total_snapshots` ens fanns. De raderna hade `total_eligible=0` och
betydde "serien fanns inte" — inte "Pinnacle saknade total" — och hör enligt
kohortregeln till ingen kohort. `pool_dataset.TOTAL_FEATURE_START_AT` gatar
nu byggaren; den här migreringen tar bort det som redan skrevs före fönstret.
Inget annat rörs: pit-v4, captures och totalserien är orörda.

Kör:
    .venv/bin/python -B scripts/migrera_pit_total_fonster.py --dry-run
    .venv/bin/python -B scripts/migrera_pit_total_fonster.py --skarp
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pool_dataset import TOTAL_FEATURE_START_AT, TOTAL_FEATURE_VERSION  # noqa: E402
from app.storage import Storage, DEFAULT_DB                                  # noqa: E402


def _backup(db_path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.stem}-backup-pittotal-{stamp}.db")
    with sqlite3.connect(db_path) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skarp", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    skarp = args.skarp and not args.dry_run
    db_path = Path(args.db)
    store = Storage(db_path)
    q = ("FROM pool_pit_total_features WHERE feature_version=? AND asof<?")
    before = store.conn.execute(f"SELECT COUNT(*) {q}",
                                (TOTAL_FEATURE_VERSION, TOTAL_FEATURE_START_AT)).fetchone()[0]
    keep = store.conn.execute(
        "SELECT COUNT(*) FROM pool_pit_total_features WHERE feature_version=? AND asof>=?",
        (TOTAL_FEATURE_VERSION, TOTAL_FEATURE_START_AT)).fetchone()[0]
    print(f"rader före fönstret {TOTAL_FEATURE_START_AT}: {before}; inom fönstret: {keep}")
    if not before or not skarp:
        print("torrkörning — inget skrivet" if not skarp else "inget att ta bort")
        store.close()
        return 0
    store.close()
    print(f"backup: {_backup(db_path)}")
    store = Storage(db_path)
    with store.bulk():
        store.conn.execute(f"DELETE {q}", (TOTAL_FEATURE_VERSION, TOTAL_FEATURE_START_AT))
    after = store.conn.execute("SELECT COUNT(*) FROM pool_pit_total_features").fetchone()[0]
    print(f"borttaget: {before}; kvar: {after}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
