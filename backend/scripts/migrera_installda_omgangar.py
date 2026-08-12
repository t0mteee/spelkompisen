"""Märk INSTÄLLDA omgångar i settlementlagret.

BAKGRUND (2026-08-12). SvS sätter `cancelled: true` på omgångens RESULTAT men
lämnar `drawState` på "Finalized". Settlementet läste bara drawState, så en
inställd omgång lagrades som en vanlig avgjord omgång vars samtliga utfall
råkade saknas. Systemledgern dömde den då "utfall saknas för minst en match" —
alltså ett misslyckat rättningsförsök i stället för "spelades aldrig".

Uppmätt: 56 av 8 324 settlade omgångar, samtliga Topptipset, spridda från
2024-05-08 till 2026-08-10. Kandidaterna hittas lokalt (alla utfall NULL, inga
strukna) och VERIFIERAS mot SvS resultat-API innan något skrivs — en omgång
märks bara om källan själv säger `cancelled: true`.

Kör:
    .venv/bin/python -B scripts/migrera_installda_omgangar.py --dry-run
    .venv/bin/python -B scripts/migrera_installda_omgangar.py --skarp
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pool_settlement import CANCELLED_STATE          # noqa: E402
from app.storage import Storage, DEFAULT_DB              # noqa: E402
from app.svenskaspel import SvenskaSpel                  # noqa: E402


KANDIDATER = """
SELECT s.product, s.draw_number, s.draw_state, s.reg_close_time,
       COUNT(e.event_number) AS n,
       SUM(CASE WHEN e.outcome IS NULL THEN 1 ELSE 0 END) AS utan,
       SUM(COALESCE(e.cancelled, 0)) AS strukna
  FROM pool_draw_settlement s
  JOIN pool_event_settlement e
    ON e.product = s.product AND e.draw_number = s.draw_number
 GROUP BY s.product, s.draw_number
HAVING n > 0 AND utan = n AND strukna = 0
 ORDER BY s.reg_close_time
"""


def _backup(db_path: Path) -> Path:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.stem}-backup-installda-{stamp}.db")
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
    rader = list(store.conn.execute(KANDIDATER))
    print(f"lokala kandidater (alla utfall saknas, inga strukna): {len(rader)}")
    if not rader:
        store.close()
        return 0

    bekraftade, avvisade = [], []
    with SvenskaSpel() as svs:
        for product, draw, state, close, n, utan, _strukna in rader:
            try:
                res = (svs._get(f"/draw/1/{product}/draws/{draw}/result") or {}).get("result")
            except Exception as exc:  # noqa: BLE001 — nätfel ska inte skriva något
                print(f"  ? {product} {draw}: källfel {exc} — lämnas orörd")
                continue
            if res is None:
                print(f"  ? {product} {draw}: inget resultat — lämnas orörd")
                continue
            if res.get("cancelled"):
                bekraftade.append((product, draw, state, close, n))
                print(f"  ✓ {product} {draw} ({str(close)[:10]}): INSTÄLLD, {utan}/{n} utan utfall")
            else:
                avvisade.append((product, draw))
                print(f"  ✗ {product} {draw}: källan säger INTE inställd — lämnas orörd")

    print(f"\nbekräftade av källan: {len(bekraftade)} · avvisade: {len(avvisade)}")
    redan = [r for r in bekraftade if r[2] == CANCELLED_STATE]
    att_skriva = [r for r in bekraftade if r[2] != CANCELLED_STATE]
    print(f"redan märkta: {len(redan)} · att märka: {len(att_skriva)}")

    if not skarp:
        print("\nTORRKÖRNING — inget skrivet. Kör med --skarp för att genomföra.")
        store.close()
        return 0

    säkerhetskopia = _backup(db_path)
    print(f"\nbackup: {säkerhetskopia}")
    for product, draw, _state, _close, _n in att_skriva:
        store.conn.execute(
            "UPDATE pool_draw_settlement SET draw_state=? "
            "WHERE product=? AND draw_number=?", (CANCELLED_STATE, product, draw))
    store.conn.commit()
    print(f"skrev draw_state='{CANCELLED_STATE}' på {len(att_skriva)} omgångar")

    # Ledgerrader som redan settlats med fel ORSAK. De är inte "oläsbara" —
    # omgången spelades aldrig. Noteringen rättas; settled_at rörs inte,
    # eftersom raden faktiskt är avslutad.
    ledger = store.conn.execute(
        "UPDATE pool_system_ledger SET settle_note=? "
        "WHERE settle_note=? AND (product, draw_number) IN "
        "(SELECT product, draw_number FROM pool_draw_settlement WHERE draw_state=?)",
        ("omgången inställd — ingen insats, inget facit",
         "utfall saknas för minst en match", CANCELLED_STATE)).rowcount
    store.conn.commit()
    print(f"rättade orsak på {ledger} ledgerrader")

    kvar = list(store.conn.execute(KANDIDATER))
    omärkta = [r for r in kvar if r[2] != CANCELLED_STATE]
    print(f"kvar utan märkning efter körning: {len(omärkta)}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
