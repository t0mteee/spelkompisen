"""Engångsrensning 2026-07-25: ankarkällor som felaktigt loggats som böcker.

BAKGRUND. Smarkets kopplades in 2026-07-24 som ANDRA SHARP-ANKARE och lades
medvetet utanför `BOOKS` i oddset.py. Men `oddset_value.attach_value` byggde
sin bok-lista som "allt utom pinnacle" — `BOOKS` styr insamlingen, inte
värderingen. Därför blev börsens priser behandlade som en mjuk bok att hitta
värde hos, och 184 av 476 sharp-flaggor blev Smarkets-rader (126 i tunna
träningsmatcher, snitt-edge 13,2 % mot Svenska Spels 6,0 %).

Raderna mäter ankaroenighet och bid-ask-spread, inte felprissättning. De var
aldrig giltiga flaggor och ska inte ligga kvar och förorena CLV-facitet.
Spärren finns nu i `oddset_value.ANCHOR_SOURCES`; detta skript städar upp det
som redan hann loggas.

Idempotent: andra körningen raderar 0 rader.

Körning:
    cd backend && .venv/bin/python -B scripts/rensa_ankarflaggor.py [--kor]
Utan --kor görs en torrkörning som bara visar vad som skulle raderas.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "stryktips.db"
BACKUP = ROOT / "data" / "backups" / "stryktips-2026-07-25-fore-ankarrensning.db"


def backup_database(source: Path, target: Path) -> bool:
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source, timeout=10)
    dst = sqlite3.connect(target)
    try:
        src.execute("PRAGMA busy_timeout=10000")
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kor", action="store_true",
                    help="utför raderingen (annars torrkörning)")
    args = ap.parse_args()

    from app.oddset_value import ANCHOR_SOURCES  # noqa: E402
    anchors = sorted(ANCHOR_SOURCES)
    if not anchors:
        sys.exit("inga ankarkällor definierade — inget att rensa")

    conn = sqlite3.connect(DB, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        marks = ",".join("?" * len(anchors))
        total = conn.execute(
            "SELECT COUNT(*) FROM oddset_value_log").fetchone()[0]
        drabbade = conn.execute(
            f"SELECT COUNT(*) FROM oddset_value_log WHERE book IN ({marks})",
            anchors).fetchone()[0]
        stangda = conn.execute(
            f"SELECT COUNT(*) FROM oddset_value_log WHERE book IN ({marks}) "
            "AND closing_fair IS NOT NULL", anchors).fetchone()[0]
        print(f"ankarkällor: {', '.join(anchors)}")
        print(f"value_log totalt: {total}")
        print(f"  varav ankarflaggor: {drabbade} (varav {stangda} stängda)")
        for liga, n in conn.execute(
                f"SELECT league, COUNT(*) FROM oddset_value_log "
                f"WHERE book IN ({marks}) GROUP BY league ORDER BY COUNT(*) DESC",
                anchors):
            print(f"    {liga}: {n}")
        if not drabbade:
            print("inget att göra.")
            return
        if not args.kor:
            print("\nTORRKÖRNING — kör med --kor för att radera.")
            return

        fresh = backup_database(DB, BACKUP)
        print(f"\nbackup: {BACKUP.name} ({'skapad' if fresh else 'fanns redan'})")
        with conn:
            n = conn.execute(
                f"DELETE FROM oddset_value_log WHERE book IN ({marks})",
                anchors).rowcount
        kvar = conn.execute(
            "SELECT COUNT(*) FROM oddset_value_log").fetchone()[0]
        print(f"raderade {n} rader · kvar {kvar}")
        print("integrity_check:",
              conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
