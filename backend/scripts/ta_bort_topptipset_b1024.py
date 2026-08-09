#!/usr/bin/env python3
"""Ta bort b1024-benchmarken ur Topptipset-familjens systemledger (2026-08-09).

BAKGRUND. Budgeten i PH3-matrisen är ANTAL RADER, och vad en budget betyder
beror på utfallsrummets storlek. Topptipset-spelen har 8 matcher, alltså
3^8 = 6 561 möjliga rader — 1 024 rader är 15,6 % av HELA rummet, och spelen
har bara EN vinstnivå att fördela på. Samma budget på ett 13-matchsspel är
1 024 / 1 594 323 = 0,06 %. Konfigurationen mätte alltså två olika saker under
samma namn. `pool_system_ledger.benchmarks_for()` fryser den inte längre för
`topptipset`/`topptipsetstryk`/`topptipsetextra`; det här skriptet städar de
rader som redan hann skrivas.

ÄRLIGHETSNOT. Uteslutningen beslutades efter att raderna var synliga. Den
vilar på utfallsrummets storlek, inte på deras ROI, men den är därmed inte en
ren förregistrering — se docs/db-atgarder.md.

Kör: .venv/bin/python -B scripts/ta_bort_topptipset_b1024.py [--apply]
Utan --apply är det en torrkörning som bara rapporterar.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pool_system_ledger import (  # noqa: E402
    EIGHT_MATCH_MAX_BUDGET, EIGHT_MATCH_PRODUCTS, benchmarks_for)
from app.storage import Storage  # noqa: E402

BACKUP = Path(__file__).resolve().parent.parent / "data" / "backups" / \
    "stryktips-2026-08-09-fore-b1024-borttagning.db"


def out_of_family(store: Storage) -> list[tuple]:
    """Rader vars config_key inte längre ingår i produktens benchmarkfamilj.

    Frågar matrisen i stället för att matcha på nyckelsträngen — nyckeln är
    en etikett, familjen är sanningen.
    """
    rows = store.conn.execute(
        "SELECT product, config_key, horizon, COUNT(*) n "
        "FROM pool_system_ledger WHERE product IN "
        f"({','.join('?' * len(EIGHT_MATCH_PRODUCTS))}) "
        "GROUP BY product, config_key, horizon ORDER BY product, config_key",
        tuple(sorted(EIGHT_MATCH_PRODUCTS))).fetchall()
    doomed = []
    for product, key, horizon, n in rows:
        if not any(b["key"] == key for b in benchmarks_for(product)):
            doomed.append((product, key, horizon, n))
    return doomed


def main() -> int:
    apply = "--apply" in sys.argv
    store = Storage()
    try:
        doomed = out_of_family(store)
        # Pensionerade generation 1-nycklar ligger också utanför familjen men
        # ska INTE röras — de är historik under sina egna namn.
        doomed = [d for d in doomed if d[1].startswith("b")]
        if not doomed:
            print("Inget att ta bort — familjen är redan ren.")
            return 0
        total = sum(d[3] for d in doomed)
        print(f"Topptipset-familjens tak: budget ≤ {EIGHT_MATCH_MAX_BUDGET:.0f} rader\n")
        for product, key, horizon, n in doomed:
            print(f"  {product:16} {key:14} {horizon:4} → {n} rader")
        print(f"\nTOTALT {total} rader i {len(doomed)} grupper.")
        if not apply:
            print("\nTORRKÖRNING — kör om med --apply för att radera.")
            return 0
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3.backup(), inte filkopiering: databasen kör WAL, så en rå
        # kopia av .db-filen kan sakna de senaste transaktionerna.
        with sqlite3.connect(BACKUP) as target:
            store.conn.backup(target)
        print(f"\nBackup: {BACKUP}")
        keys = sorted({d[1] for d in doomed})
        cur = store.conn.execute(
            "DELETE FROM pool_system_ledger WHERE product IN "
            f"({','.join('?' * len(EIGHT_MATCH_PRODUCTS))}) "
            f"AND config_key IN ({','.join('?' * len(keys))})",
            (*sorted(EIGHT_MATCH_PRODUCTS), *keys))
        store.conn.commit()
        print(f"Raderade {cur.rowcount} rader.")
        kvar = store.conn.execute(
            "SELECT COUNT(*) FROM pool_system_ledger WHERE product IN "
            f"({','.join('?' * len(EIGHT_MATCH_PRODUCTS))}) "
            f"AND config_key IN ({','.join('?' * len(keys))})",
            (*sorted(EIGHT_MATCH_PRODUCTS), *keys)).fetchone()[0]
        print(f"Efterkontroll: {kvar} kvar (ska vara 0).")
        integrity = store.conn.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"integrity_check: {integrity}")
        return 0 if kvar == 0 and integrity == "ok" else 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
