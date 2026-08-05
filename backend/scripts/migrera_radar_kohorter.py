"""Omklassificera radarkohorter efter den observerade koden, inte gränsen.

Körning i produktion (backup tas av skriptet före första mutation):
    cd backend && .venv/bin/python -B scripts/migrera_radar_kohorter.py

BAKGRUND. `RADAR_*_STARTED_AT` är handskrivna konstanter utan orsakssamband
med när koden faktiskt började köra: insamlingsjobben startar en ny process
varje tick ur arbetskopian, så en versionsbump gäller i samma sekund filen
sparas. Journalen stämplade write-time-versionen (verkligheten) medan
settlementet läste konstanten (avsikten), och de gled isär åt båda hållen:

  * v5-gränsen sattes 16 h EFTER att koden bytte  → 2 168 v5-producerade
    ögonblick låg under v4, alltså 57 % av hela v4-kohorten.
  * v3-gränsen sattes 3,5 h FÖRE att koden bytte  → 447 v2-producerade
    ögonblick låg under v3.
  * 7 journalrader stämplades i en annan kohort än settlementet gav samma
    ögonblick.

REGELN (live_radar.cohort_for): en rad hör till vN bara om vN-KODEN
producerade den OCH den observerades i vN:s DEKLARERADE fönster. Annars är den
`transitional` och ingår i INGEN kohort. Rader flyttas ALDRIG till föregående
kohort — det vore precis den kontaminering versionering finns för att
förhindra.

Gränserna rörs inte. Det som ändras är att koden slutar vara oense med dem.

BEVISHORISONT. Journalens första rad är 2026-08-01T01:02:15Z. Ögonblick före
den (17 272 v2-märkta, inklusive en v1→v2-växling) går inte att validera och
behåller sin deklarerade etikett — en påhittad transitional-etikett vore inte
ärligare. Det är en känd, dokumenterad begränsning.

Historiska captures får INTE `radar_version` bakfylld: kolumnen ska betyda
"observerat vid skrivning". NULL = härledd ur journalens växlingar, och den
skillnaden ska synas i efterhand.

Idempotent och atomär: en andra körning skriver noll rader.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import live_radar  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
BACKUP_DIR = ROOT / "data" / "backups"
DEFAULT_BACKUP = "stryktips-2026-08-05-fore-radarkohorter.db"


def backup_database(source: Path | str, target: Path | str) -> bool:
    target = Path(target)
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(source, timeout=10)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.execute("PRAGMA busy_timeout=10000")
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    return True


def _capture_versions(conn: sqlite3.Connection) -> dict[tuple, str]:
    """(provider, event_id, captured_at) → radens egen `radar_version`."""
    recorded: dict[tuple, str] = {}
    for provider, table, id_column in (
            ("sofascore", "oddset_live_capture", "event_id"),
            ("fotmob", "oddset_live_fotmob", "fotmob_id"),
            ("flashscore", "oddset_live_flashscore", "flashscore_id")):
        for row in conn.execute(
                f"SELECT {id_column} id, captured_at, radar_version "
                f"FROM {table} WHERE radar_version IS NOT NULL"):
            recorded[(provider, str(row["id"]), row["captured_at"])] = \
                row["radar_version"]
    return recorded


def migrate(conn: sqlite3.Connection) -> dict:
    report: dict = {"moments": {}, "signals": {}, "collisions": []}
    recorded = _capture_versions(conn)

    moments = conn.execute(
        "SELECT rowid, provider, event_id, captured_at, signal_version "
        "FROM oddset_live_moment_settlement").fetchall()
    changes: dict[str, int] = {}
    for row in moments:
        produced = recorded.get(
            (row["provider"], str(row["event_id"]), row["captured_at"]))
        cohort = live_radar.cohort_for(row["captured_at"],
                                       produced_by=produced)
        if cohort == row["signal_version"]:
            continue
        conn.execute(
            "UPDATE oddset_live_moment_settlement SET signal_version=? "
            "WHERE rowid=?", (cohort, row["rowid"]))
        key = f"{row['signal_version']} → {cohort}"
        changes[key] = changes.get(key, 0) + 1
    report["moments"] = changes

    # Journalens naturliga nyckel är (match_key, signal_version, typ, nivå).
    # En omstämpling får inte skapa två rader med samma nyckel; kontrolleras
    # FÖRE skrivning så en krock avbryter i stället för att tyst dubblera.
    signals = conn.execute(
        "SELECT id, match_key, captured_at, signal_version, signal_type, "
        "signal_level, provider, provider_event_id, home, away "
        "FROM oddset_live_signal").fetchall()
    planned: dict[tuple, int] = {}
    updates: list[tuple[str, int]] = []
    for row in signals:
        produced = recorded.get(
            (row["provider"], str(row["provider_event_id"]),
             row["captured_at"]))
        cohort = live_radar.cohort_for(row["captured_at"],
                                       produced_by=produced)
        key = (row["match_key"], cohort, row["signal_type"],
               row["signal_level"])
        if key in planned:
            report["collisions"].append(
                f"{row['home']}–{row['away']} {row['signal_type']}/"
                f"{row['signal_level']} → {cohort}")
        planned[key] = row["id"]
        if cohort != row["signal_version"]:
            updates.append((cohort, row["id"]))
    if report["collisions"]:
        return report
    changes = {}
    for cohort, signal_id in updates:
        before = next(r["signal_version"] for r in signals
                      if r["id"] == signal_id)
        conn.execute(
            "UPDATE oddset_live_signal SET signal_version=? WHERE id=?",
            (cohort, signal_id))
        key = f"{before} → {cohort}"
        changes[key] = changes.get(key, 0) + 1
    report["signals"] = changes
    return report


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    name = DEFAULT_BACKUP
    if "--backup" in argv:
        name = argv[argv.index("--backup") + 1]
    backup = BACKUP_DIR / name
    if not DB.exists():
        print(f"saknar databas: {DB}")
        return 1
    fresh = backup_database(DB, backup)
    print(f"backup: {backup.name} ({'skapad' if fresh else 'fanns redan'})")
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            report = migrate(conn)
        if report["collisions"]:
            print("  AVBRYTER: omstämplingen skulle krocka på journalens "
                  "naturliga nyckel:")
            for line in report["collisions"]:
                print(f"    {line}")
            return 1
        print("  ögonblick (oddset_live_moment_settlement):")
        for key, count in sorted(report["moments"].items()) or []:
            print(f"    {key:46} {count}")
        if not report["moments"]:
            print("    inga ändringar")
        print("  journalrader (oddset_live_signal):")
        for key, count in sorted(report["signals"].items()) or []:
            print(f"    {key:46} {count}")
        if not report["signals"]:
            print("    inga ändringar")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        print(f"  integrity_check={integrity} · foreign-key-fel={fk}")
        return 0 if integrity == "ok" and fk == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
