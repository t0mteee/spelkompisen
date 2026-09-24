"""Nattlig databasbackup för Spelkompisen (Samans beslut 2026-09-24).

Stegen, i ordning:

1. Onlinekopia med SQLites backup-API till ``<rot>/daily/``. En aktiv
   SQLite-fil kopieras ALDRIG med filkopiering: WAL-sidor som ännu inte
   checkpointats skulle saknas, och kopian kan bli trasig utan att det syns.
2. ``PRAGMA quick_check`` på kopian. En kopia som inte svarar "ok" sparas
   inte och publiceras aldrig.
3. gzip och sha256. De ``--keep`` senaste dagskopiorna sparas lokalt; de
   skyddar mot en felaktig migrering, inte mot diskfel.
4. Den senaste kopian publiceras till det PRIVATA repot
   ``t0mteee/spelkompisen-backup``, delad i delar under GitHubs varningsgräns
   på 50 MB (hård gräns 100 MB per fil). Repot ersätts varje natt med EN
   commit på en föräldralös gren (force-push), så det växer inte. Detta
   skyddar mot diskfel och stöld. Publicera ALDRIG till spelkompisen-repot:
   det är publikt, och databasen innehåller spelade kuponger och insatser.
5. ``status.json`` bär senaste utfall (även vid fel) och ``last_ok_at``
   bevaras från förra lyckade körningen.

Kör manuellt:

    .venv/bin/python -B scripts/backup_db.py            # full körning
    .venv/bin/python -B scripts/backup_db.py --no-push  # bara lokalt

Återställning: se README.md i backup-repot eller docs/backup.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.storage import DEFAULT_DB  # noqa: E402

VERSION = "db-backup-v1"
DEFAULT_ROOT = pathlib.Path.home() / "Backups" / "spelkompisen"
DEFAULT_REMOTE = "git@github.com:t0mteee/spelkompisen-backup.git"
# Endast detta repo får ta emot databasen. Spärren fångar ett felskrivet
# --remote innan något lämnar servern.
ALLOWED_REMOTES = frozenset({DEFAULT_REMOTE})
PART_BYTES = 45 * 1024 * 1024
KEEP_DAILY = 14
GZ_LEVEL = 6
PREFIX = "stryktips-"
SUFFIX = ".db.gz"


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(src: pathlib.Path, dest: pathlib.Path) -> None:
    """Konsistent onlinekopia i ETT steg.

    Stegvis backup startar om varje gång en annan anslutning skriver, och
    insamlingen skriver var femte minut. I WAL-läge blockerar en läsare inte
    skrivare, så ett enda steg är både säkert och snabbt.
    """
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
        # Kopian ska vara en fristående fil, inte en WAL-databas som kräver
        # -wal/-shm bredvid sig.
        target.execute("PRAGMA journal_mode=DELETE")
    finally:
        target.close()
        source.close()


def quick_check(path: pathlib.Path) -> str:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = [row[0] for row in conn.execute("PRAGMA quick_check")]
    finally:
        conn.close()
    return "ok" if rows == ["ok"] else "; ".join(str(r) for r in rows[:5])


def table_counts(path: pathlib.Path, tables: tuple[str, ...]) -> dict[str, int]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        present = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables if t in present}
    finally:
        conn.close()


def compress(path: pathlib.Path) -> pathlib.Path:
    out = path.with_name(path.name + ".gz")
    with open(path, "rb") as src, gzip.open(out, "wb", compresslevel=GZ_LEVEL) as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    path.unlink()
    return out


def split_file(path: pathlib.Path, dest_dir: pathlib.Path,
               part_bytes: int = PART_BYTES) -> list[dict]:
    parts = []
    with open(path, "rb") as handle:
        index = 0
        while True:
            chunk = handle.read(part_bytes)
            if not chunk:
                break
            name = f"{path.name}.part-{index:03d}"
            (dest_dir / name).write_bytes(chunk)
            parts.append({"name": name, "bytes": len(chunk),
                          "sha256": hashlib.sha256(chunk).hexdigest()})
            index += 1
    return parts


def rotate(daily_dir: pathlib.Path, keep: int) -> list[str]:
    """Behåll de `keep` senaste dagskopiorna; namnet bär UTC-stämpeln."""
    copies = sorted(p for p in daily_dir.glob(f"{PREFIX}*{SUFFIX}"))
    removed = []
    for old in copies[:-keep] if keep > 0 else copies:
        old.unlink()
        removed.append(old.name)
    return removed


def _git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                            text=True, timeout=900)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{(result.stderr or result.stdout).strip()[:300]}")
    return result.stdout.strip()


README = """# Spelkompisen — databasbackup (PRIVAT)

Det här repot tar emot en nattlig kopia av Spelkompisens SQLite-databas.
Det innehåller spelade kuponger och insatser och ska alltid vara privat.
Repot skrivs om varje natt: bara den senaste kopian finns kvar här. Äldre
kopior ligger 14 dagar bakåt på servern (`~/Backups/spelkompisen/daily`).

## Återställa

```sh
cat stryktips-*.db.gz.part-* > stryktips.db.gz
shasum -a 256 stryktips.db.gz        # jämför med gz_sha256 i MANIFEST.json
gunzip stryktips.db.gz
sqlite3 stryktips.db "PRAGMA integrity_check"
```

Lägg aldrig tillbaka en kopia i produktion utan att först stoppa
insamlingen och ta en backup av den nuvarande databasen. Se docs/backup.md i
spelkompisen-repot.
"""


def publish(gz_path: pathlib.Path, repo: pathlib.Path, remote: str,
            manifest: dict, identity: tuple[str, str]) -> None:
    """Ersätt backup-repots innehåll med en commit och force-pusha den."""
    if remote not in ALLOWED_REMOTES:
        raise RuntimeError(f"otillåtet backup-repo: {remote}")
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
        _git(repo, "remote", "add", "origin", remote)
    if _git(repo, "remote", "get-url", "origin") != remote:
        raise RuntimeError("backup-repots origin stämmer inte med spärren")
    _git(repo, "config", "user.name", identity[0])
    _git(repo, "config", "user.email", identity[1])
    for child in repo.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    parts = split_file(gz_path, repo)
    manifest = {**manifest, "parts": parts}
    (repo / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (repo / "README.md").write_text(README, encoding="utf-8")
    branch = "snapshot-" + manifest["created_stamp"]
    _git(repo, "checkout", "-q", "--orphan", branch)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"Databaskopia {manifest['created_at']}")
    branches = _git(repo, "branch", "--format=%(refname:short)").split()
    if "main" in branches:
        _git(repo, "branch", "-D", "main")
    _git(repo, "branch", "-m", "main")
    _git(repo, "push", "-q", "-f", "origin", "main")
    # Släpp gamla kopior lokalt också, annars växer .git med 150 MB per natt.
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "-q", "--prune=now")


def _project_commit() -> Optional[str]:
    try:
        return _git(ROOT.parent, "rev-parse", "--short", "HEAD")
    except (RuntimeError, OSError):
        return None


def _read_status(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(src: pathlib.Path, root: pathlib.Path, remote: str, keep: int,
        push: bool, now: dt.datetime,
        identity: tuple[str, str] = ("Saman", "saman@MacBook-Pro-SERVER.local")) -> dict:
    daily = root / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    status_path = root / "status.json"
    previous = _read_status(status_path)
    status = {"version": VERSION, "last_attempt_at": _iso(now), "ok": False,
              "error": None, "pushed": False,
              "last_ok_at": previous.get("last_ok_at"),
              "last_pushed_at": previous.get("last_pushed_at")}
    raw = daily / f"{PREFIX}{_stamp(now)}.db"
    try:
        snapshot(src, raw)
        check = quick_check(raw)
        if check != "ok":
            raw.unlink(missing_ok=True)
            raise RuntimeError(f"quick_check: {check}")
        counts = table_counts(raw, ("pool_draw_settlement", "pool_market_capture",
                                    "pool_system_ledger", "pool_played",
                                    "oddset_odds", "sharp_snapshots"))
        db_bytes = raw.stat().st_size
        gz_path = compress(raw)
        manifest = {
            "version": VERSION, "created_at": _iso(now),
            "created_stamp": _stamp(now), "source": str(src),
            "project_commit": _project_commit(), "db_bytes": db_bytes,
            "gz_name": gz_path.name, "gz_bytes": gz_path.stat().st_size,
            "gz_sha256": sha256_of(gz_path), "quick_check": check,
            "table_counts": counts,
        }
        (daily / (gz_path.name + ".json")).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        status.update({"ok": True, "last_ok_at": _iso(now), "snapshot": manifest})
        status["rotated_out"] = rotate(daily, keep)
        for stale in daily.glob(f"{PREFIX}*{SUFFIX}.json"):
            if not (daily / stale.name[:-len(".json")]).exists():
                stale.unlink()
        if push:
            publish(gz_path, root / "github", remote, manifest, identity)
            status.update({"pushed": True, "last_pushed_at": _iso(now)})
    except Exception as exc:  # noqa: BLE001 — status ska alltid skrivas
        # `ok` avser den lokala kopian och `pushed` publiceringen. Ett nätfel
        # vid push lämnar alltså ok=True, pushed=False och felet synligt.
        status["error"] = f"{type(exc).__name__}: {exc}"[:400]
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", default=str(DEFAULT_DB))
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--keep", type=int, default=KEEP_DAILY)
    parser.add_argument("--no-push", action="store_true")
    args = parser.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    status = run(pathlib.Path(args.src), pathlib.Path(args.root), args.remote,
                 args.keep, not args.no_push, now)
    snap = status.get("snapshot") or {}
    print(f"[{status['last_attempt_at']}] {VERSION}: "
          f"{'ok' if status['ok'] else 'FEL'}"
          f"{' · publicerad' if status['pushed'] else ''}"
          f" · {snap.get('gz_bytes', 0) / 1e6:.1f} MB"
          f"{' · ' + status['error'] if status.get('error') else ''}")
    return 0 if status["ok"] and (status["pushed"] or args.no_push) else 1


if __name__ == "__main__":
    raise SystemExit(main())
