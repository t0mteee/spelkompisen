"""Migration för Flashscore som live-radarns primära statistikkälla.

Körning:
    cd backend && .venv/bin/python -B scripts/migrera_flashscore.py

Två ändringar, båda additiva eller innehållsbevarande:

1. **Ny tabell `oddset_live_flashscore`** — egen capture-tabell, av samma skäl
   som FotMob har en: providrar blandas ALDRIG inom en serie.
2. **`oddset_live_signal.provider_event_id` INTEGER → TEXT.** Flashscores
   event-id är alfanumeriskt ('SKg88Q3T'). SQLite kan inte ändra kolumntyp med
   ALTER, så tabellen byggs om med samma kolumner, index och UNIQUE-vakt, och
   raderna kopieras oförändrade. Resultatlagret pekar på `id` och rörs inte.

Ingen bakfyllning: Flashscore-serien börjar samla framåt. Den befintliga
signalraden från `chance-gap-shadow-v2` behålls som historik — radarns
signalversion bumpas till v3 i samma leverans, så v2- och v3-kohorterna
blandas aldrig.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.storage import LIVE_RADAR_SCHEMA, Storage  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-01-fore-flashscore.db")
SIGNAL_COLUMNS = ("id",) + Storage.LIVE_SIGNAL_COLUMNS
LEGACY_ADDITIVE_SIGNAL_COLUMNS = frozenset(
    {"clock_source", "clock_observed_at"})


def backup_database(source: Path | str, target: Path | str) -> bool:
    target = Path(target)
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


def _columns(conn: sqlite3.Connection, table: str) -> dict:
    return {row[1]: row[2] for row in conn.execute(
        f"PRAGMA table_info({table})").fetchall()}


def _ddl(name: str) -> str:
    """Plocka EN CREATE-sats ur schemat — den nya tabellen ska vara identisk
    med `Storage`-schemat, aldrig en handskriven kopia som kan glida isär."""
    marker = f"CREATE TABLE IF NOT EXISTS {name} ("
    start = LIVE_RADAR_SCHEMA.index(marker)
    end = LIVE_RADAR_SCHEMA.index("\n);", start) + len("\n);")
    return LIVE_RADAR_SCHEMA[start:end]


def _execute_schema(conn: sqlite3.Connection) -> None:
    """Kör schemat satsvis utan ``executescript``-implicit commit.

    Python-SQLites ``executescript`` committar en pågående transaktion innan
    skriptet körs. Den här migrationen bygger om tabeller och måste därför
    hålla även CREATE-satserna i SAMMA transaktion som kopiering/validering.
    """
    statement = ""
    for line in LIVE_RADAR_SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                conn.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("ofullständig SQL-sats i LIVE_RADAR_SCHEMA")


def _has_unique_guard(conn: sqlite3.Connection) -> bool:
    expected = ("match_key", "signal_version", "signal_type", "signal_level")
    for index in conn.execute(
            "PRAGMA index_list(oddset_live_signal)").fetchall():
        if not index[2]:
            continue
        columns = tuple(row[2] for row in conn.execute(
            f"PRAGMA index_info({index[1]})").fetchall())
        if columns == expected:
            return True
    return False


def _validate_before(conn: sqlite3.Connection) -> None:
    """Tillåt bara den verkliga 07-31-varianten före någon mutation."""
    signal = _columns(conn, "oddset_live_signal")
    if signal:
        expected = set(SIGNAL_COLUMNS)
        actual = set(signal)
        missing = expected - actual
        extra = actual - expected
        if extra or not missing <= LEGACY_ADDITIVE_SIGNAL_COLUMNS:
            raise RuntimeError(
                "oddset_live_signal avviker före migration: saknar "
                f"{sorted(missing) or '–'} · extra {sorted(extra) or '–'}")
        provider_type = signal.get("provider_event_id", "").upper()
        if provider_type not in {"INTEGER", "TEXT"}:
            raise RuntimeError(
                f"oväntad provider_event_id-typ {provider_type!r}")
        if not _has_unique_guard(conn):
            raise RuntimeError("oddset_live_signal saknar UNIQUE-vakten")

    flashscore = _columns(conn, "oddset_live_flashscore")
    if flashscore and set(flashscore) != set(Storage.LIVE_FLASHSCORE_COLUMNS):
        raise RuntimeError(
            "oddset_live_flashscore avviker före migration: saknar "
            f"{sorted(set(Storage.LIVE_FLASHSCORE_COLUMNS) - set(flashscore)) or '–'} "
            f"· extra {sorted(set(flashscore) - set(Storage.LIVE_FLASHSCORE_COLUMNS)) or '–'}")


def _rebuild_signal_table(conn: sqlite3.Connection) -> bool:
    """Byt provider_event_id till TEXT utan att förlora en enda rad.

    Manuell transaktion, inte `executescript`: den senare committar implicit
    och skulle lämna DB:n halvombyggd om något felade mitt i. `legacy_alter_
    table` hindrar RENAME från att skriva om resultattabellens FK-referens.
    """
    columns = _columns(conn, "oddset_live_signal")
    if not columns or columns.get("provider_event_id", "").upper() == "TEXT":
        return False
    before = conn.execute(
        "SELECT COUNT(*) FROM oddset_live_signal").fetchone()[0]
    existing = set(columns)
    names = ",".join(SIGNAL_COLUMNS)
    select = ",".join(
        name if name in existing else f"NULL AS {name}"
        for name in SIGNAL_COLUMNS)
    conn.execute("DROP INDEX IF EXISTS idx_live_signal_recent")
    conn.execute("ALTER TABLE oddset_live_signal "
                 "RENAME TO oddset_live_signal_gammal")
    conn.execute(_ddl("oddset_live_signal"))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_live_signal_recent "
                 "ON oddset_live_signal "
                 "(captured_at DESC, signal_type, signal_level)")
    conn.execute(f"INSERT INTO oddset_live_signal({names}) "
                 f"SELECT {select} FROM oddset_live_signal_gammal")
    after = conn.execute(
        "SELECT COUNT(*) FROM oddset_live_signal").fetchone()[0]
    if after != before:
        raise RuntimeError(
            f"radantal ändrades vid ombyggnad: {before} → {after}")
    conn.execute("DROP TABLE oddset_live_signal_gammal")
    return True


def _repair_result_fk(conn: sqlite3.Connection) -> bool:
    """Reparera resultattabellens FK efter en RENAME utan legacy_alter_table.

    SQLite skriver som standard om FK-referenser i ANDRA tabeller när en
    tabell byter namn. Ett avbrutet ombyggnadsförsök 2026-08-01 lämnade därför
    `oddset_live_signal_result` pekande på `oddset_live_signal_gammal`, som
    sedan droppades — en hängande referens. Den är ofarlig så länge
    `foreign_keys` är av (vilket den är), men skulle fälla varje insert den
    dagen någon slår på kontrollen. Se docs/db-atgarder.md 2026-08-01.
    """
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        ("oddset_live_signal_result",)).fetchone()
    if not sql or "oddset_live_signal_gammal" not in (sql[0] or ""):
        return False
    cols = ",".join(Storage.LIVE_SIGNAL_RESULT_COLUMNS)
    before = conn.execute(
        "SELECT COUNT(*) FROM oddset_live_signal_result").fetchone()[0]
    conn.execute("ALTER TABLE oddset_live_signal_result "
                 "RENAME TO oddset_live_signal_result_trasig")
    conn.execute(_ddl("oddset_live_signal_result"))
    conn.execute(f"INSERT INTO oddset_live_signal_result({cols}) "
                 f"SELECT {cols} FROM oddset_live_signal_result_trasig")
    after = conn.execute(
        "SELECT COUNT(*) FROM oddset_live_signal_result").fetchone()[0]
    if after != before:
        raise RuntimeError(
            f"radantal ändrades vid FK-reparation: {before} → {after}")
    conn.execute("DROP TABLE oddset_live_signal_result_trasig")
    return True


def migrate(db: Path | str) -> dict:
    conn = sqlite3.connect(db, timeout=10)
    try:
        conn.execute("PRAGMA busy_timeout=10000")
        had_flashscore = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            ("oddset_live_flashscore",)).fetchone() is not None
        _validate_before(conn)
        conn.execute("PRAGMA legacy_alter_table=ON")
        conn.execute("BEGIN IMMEDIATE")
        _execute_schema(conn)
        rebuilt = _rebuild_signal_table(conn)
        repaired = _repair_result_fk(conn)

        columns = _columns(conn, "oddset_live_flashscore")
        expected = set(Storage.LIVE_FLASHSCORE_COLUMNS)
        if set(columns) != expected:
            raise RuntimeError(
                "oddset_live_flashscore avviker: saknar "
                f"{sorted(expected - set(columns)) or '–'} · extra "
                f"{sorted(set(columns) - expected) or '–'}")
        signal_type = _columns(conn, "oddset_live_signal").get(
            "provider_event_id", "").upper()
        if signal_type != "TEXT":
            raise RuntimeError(
                f"provider_event_id har fortfarande typen {signal_type!r}")
        result_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name=?",
            ("oddset_live_signal_result",)).fetchone()
        if result_sql and "oddset_live_signal_gammal" in (result_sql[0] or ""):
            raise RuntimeError("resultattabellens FK pekar fortfarande fel")
        if not _has_unique_guard(conn):
            raise RuntimeError("oddset_live_signal saknar UNIQUE-vakten efter migration")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check: {integrity}")
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"foreign_key_check: {fk_errors[:3]}")
        result = {
            "flashscore_created": not had_flashscore,
            "flashscore_columns": len(columns),
            "signal_rebuilt": rebuilt,
            "result_fk_repaired": repaired,
            "signal_rows": conn.execute(
                "SELECT COUNT(*) FROM oddset_live_signal").fetchone()[0],
            "integrity": integrity,
            "foreign_keys": "ok",
        }
        conn.execute("COMMIT")
        return result
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.close()


def main() -> None:
    backed_up = backup_database(DB, BACKUP)
    result = migrate(DB)
    print(f"backup {'skapad' if backed_up else 'fanns redan'}: {BACKUP.name}")
    print(f"oddset_live_flashscore: "
          f"{'skapad' if result['flashscore_created'] else 'fanns redan'} · "
          f"{result['flashscore_columns']} kolumner")
    print(f"oddset_live_signal: "
          f"{'ombyggd till TEXT' if result['signal_rebuilt'] else 'redan TEXT'}"
          f" · {result['signal_rows']} rader bevarade")
    print(f"oddset_live_signal_result: FK "
          f"{'reparerad' if result['result_fk_repaired'] else 'korrekt'}")
    print(f"integrity {result['integrity']}")


if __name__ == "__main__":
    main()
