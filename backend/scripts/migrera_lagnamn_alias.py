"""Slå ihop klubbar som lagrats under två stavningar.

Körning i produktion (backup tas av skriptet före första mutation):
    cd backend && .venv/bin/python -B scripts/migrera_lagnamn_alias.py

Bakgrund: `oddset_results` lagrar normaliserade namn (oddset.norm_team).
football-data och Sofascore stavar samma klubb olika — `norrkoping` mot
`ifk norrkoping`, `halmstads` mot `halmstad` — och eftersom stavningen ingår i
primärnyckeln lade varje sådan match in TVÅ rader. Historiken var alltså inte
halverad utan DUBBLERAD, vilket dubbelviktar klubbarna i modellanpassningen.

De tolv paren i `TEAM_ALIASES` är bevisade: samma liga, samma datum, samma
motståndare och identiskt resultat i båda raderna. Migrationen skriver om
namnen med aliaset och slår ihop de rader som därmed krockar.

Sammanslagningsregeln följer v4-kontraktet: en football-data-rad vinner som
resultatfacit. Vid lika källa vinner raden med flest ifyllda fält. Ingen rad
uppfinner data — vid krock behålls en hel rad, aldrig ett hopplock av fält.

Idempotent och atomär: en andra körning skriver noll rader.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.oddset import TEAM_ALIASES  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
BACKUP = (ROOT / "data" / "backups" /
          "stryktips-2026-08-02-fore-lagnamn-alias.db")

# Tabeller med normaliserade lagnamn i primärnyckeln.
NAME_TABLES = (("oddset_results", ("home", "away")),
               ("oddset_result_stats", ("home", "away")),
               ("oddset_elo_rating", ("club_key",)))


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


def _pk(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            if row[5]]


def _completeness(row: sqlite3.Row) -> int:
    return sum(1 for value in tuple(row) if value is not None)


def _rank(row: sqlite3.Row, columns: list[str]) -> tuple[int, int]:
    """Lägre är bättre. football-data först, därefter mest ifyllda fält."""
    source = row["source"] if "source" in columns else None
    return (0 if source == "fd" else 1, -_completeness(row))


def migrate(conn: sqlite3.Connection) -> dict:
    report: dict = {"renamed": {}, "merged": {}, "kept": {}}
    for table, name_columns in NAME_TABLES:
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if not columns:
            continue
        pk = _pk(conn, table)
        rows = conn.execute(f"SELECT rowid, * FROM {table}").fetchall()
        groups: dict[tuple, list[sqlite3.Row]] = {}
        renamed = 0
        for row in rows:
            mapped = {}
            for column in name_columns:
                value = row[column]
                mapped[column] = TEAM_ALIASES.get(value, value)
                if mapped[column] != value:
                    renamed += 1
            key = tuple(mapped.get(column, row[column]) for column in pk)
            groups.setdefault(key, []).append(row)

        merged = 0
        for key, members in groups.items():
            if len(members) > 1:
                members.sort(key=lambda item: _rank(item, columns))
                for loser in members[1:]:
                    conn.execute(f"DELETE FROM {table} WHERE rowid = ?",
                                 (loser["rowid"],))
                    merged += 1
            winner = members[0]
            updates = {column: TEAM_ALIASES.get(winner[column], winner[column])
                       for column in name_columns}
            if any(updates[column] != winner[column] for column in name_columns):
                assignments = ", ".join(f"{column} = ?" for column in updates)
                conn.execute(f"UPDATE {table} SET {assignments} WHERE rowid = ?",
                             (*updates.values(), winner["rowid"]))
        report["renamed"][table] = renamed
        report["merged"][table] = merged
        report["kept"][table] = len(groups)
    return report


def main() -> int:
    if not DB.exists():
        print(f"saknar databas: {DB}")
        return 1
    fresh = backup_database(DB, BACKUP)
    print(f"backup: {BACKUP.name} ({'skapad' if fresh else 'fanns redan'})")
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        before = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table, _ in NAME_TABLES}
        with conn:
            report = migrate(conn)
        after = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                 for table, _ in NAME_TABLES}
        for table, _ in NAME_TABLES:
            print(f"  {table:22} {before[table]:6} → {after[table]:6} rader · "
                  f"{report['renamed'].get(table, 0)} namn omskrivna · "
                  f"{report['merged'].get(table, 0)} hopslagna")
            if before[table] - after[table] != report["merged"].get(table, 0):
                print("  AVBRYTER: radförlusten matchar inte antalet hopslagna")
                return 1
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        print(f"  integrity_check={integrity} · foreign-key-fel={fk}")
        return 0 if integrity == "ok" and fk == 0 else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
