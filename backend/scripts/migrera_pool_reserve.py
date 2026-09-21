"""Additiv reservoddsjournal med onlinebackup, ingen bakfyllning."""
import argparse
import datetime as dt
import sqlite3
from contextlib import closing
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pool_reserve import SCHEMA


def migrate(db, backup):
    if not db.is_file() or backup.exists():
        raise ValueError("DB måste finnas och backupnamnet måste vara nytt")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db, timeout=30)) as source:
        with closing(sqlite3.connect(backup)) as target:
            source.backup(target)
        source.executescript(SCHEMA)
        check = source.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise RuntimeError(check)
    return {"backup":str(backup),"integrity_check":check,"backfilled":0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",type=Path,default=Path("data/stryktips.db"))
    parser.add_argument("--backup",type=Path,default=Path("data/backups") /
                        f"fore-pool-reserv-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.db")
    args = parser.parse_args()
    print(migrate(args.db,args.backup))
