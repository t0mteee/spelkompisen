"""Rätta ett livespel på ett slutresultat som Saman verifierat.

BAKGRUND (beslut driften-2026-11-26-livespel-257-orattat, val 2). Spel 257
(Atlético Madrid–Viking Stavanger, Champions League 2026-11-25) låg orättat:
insamlingen fick aldrig matchens resultat, så `livekassa.ratta` hade inget att
rätta mot. Saman verifierade slutresultatet (2–0) och valde att spelet rättas
på det. Skriptet rättar via `livekassa.ratta_manuellt` (samma Asian-regler och
nästa pris som `ratta`); `oddset_results` rörs inte.

Kör:
    .venv/bin/python -B scripts/ratta_livespel_manuellt.py --spel 257 --resultat 2-0 \
        --beslut driften-2026-11-26-livespel-257-orattat            # torrkörning
    ... --skarp                                                      # skriv
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.spelai import livekassa                          # noqa: E402
from app.storage import Storage, DEFAULT_DB              # noqa: E402


def _backup(db_path: Path, stamp: str) -> Path:
    dest_dir = db_path.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"{db_path.stem}-{stamp}-fore-manuell-liverattning.db"
    # Onlinebackup: atomär även när produktionsjobben skriver samtidigt.
    with sqlite3.connect(db_path) as source, sqlite3.connect(dest) as target:
        source.backup(target)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spel", type=int, required=True)
    ap.add_argument("--resultat", required=True, help="hemma-borta, t.ex. 2-0")
    ap.add_argument("--beslut", required=True)
    ap.add_argument("--skarp", action="store_true", help="skriv (annars torrkörning)")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    args = ap.parse_args()
    m = re.fullmatch(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", args.resultat)
    if not m:
        print(f"ogiltigt resultat: {args.resultat!r}")
        return 2
    hg, ag = int(m.group(1)), int(m.group(2))
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    db_path = Path(args.db)

    if not args.skarp:
        store = Storage(db_path, read_only=True)
        try:
            spel = livekassa._spel(store.conn, "WHERE b.id=?", (args.spel,))  # noqa: SLF001
            if not spel:
                print(f"spel {args.spel} finns inte")
                return 1
            bet = spel[0]
            match = livekassa._match_for_ref(store.conn, bet["match_ref"])  # noqa: SLF001
            oppna = livekassa._spel(store.conn, "WHERE b.match_ref=? AND r.bet_id IS NULL",  # noqa: SLF001
                                    (bet["match_ref"],))
        finally:
            store.close()
        print(f"match: {match and match['home']}–{match and match['away']} "
              f"({match and match['start']}), resultat {hg}–{ag}")
        print(f"spel {args.spel}: rättat={bet['outcome']}")
        for b in oppna:
            utfall, netto = livekassa.ou_utfall(hg + ag, float(b["line"]), b["sign"],
                                                float(b["odds"]), float(b["stake_kr"]))
            print(f"  spel {b['id']}: {b['market']} {b['sign']} {b['line']} @ {b['odds']}, "
                  f"{b['stake_kr']} kr → {utfall} {netto:+.2f} kr")
        print("\nTORRKÖRNING — inget skrivet. Kör med --skarp för att genomföra.")
        return 0

    stamp = now.strftime("%Y-%m-%dT%H%M%SZ")
    print(f"backup: {_backup(db_path, stamp)}")
    store = Storage(db_path)
    try:
        rapport = livekassa.ratta_manuellt(store, args.spel, hg, ag,
                                           beslut=args.beslut, now=now)
        print(f"rättat {now.isoformat()}: {rapport}")
        print("integrity_check:", store.conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
