"""Nattlig databasbackup: onlinekopia, kontroll, rotation och publicering."""
from __future__ import annotations

import datetime as dt
import gzip
import json
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import backup_db

NOW = dt.datetime(2026, 9, 24, 2, 15, tzinfo=dt.timezone.utc)


def _make_db(path: pathlib.Path, rows: int = 500) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE pool_played (id INTEGER PRIMARY KEY, note TEXT)")
    conn.executemany("INSERT INTO pool_played (note) VALUES (?)",
                     [(f"kupong {i} " + "x" * 200,) for i in range(rows)])
    conn.commit()
    conn.close()


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.tmp.name)
        self.src = self.base / "stryktips.db"
        _make_db(self.src)
        self.root = self.base / "backups"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lokal_kopia_ar_kontrollerad_och_aterstallbar(self):
        status = backup_db.run(self.src, self.root, backup_db.DEFAULT_REMOTE,
                               keep=14, push=False, now=NOW)
        self.assertTrue(status["ok"])
        self.assertFalse(status["pushed"])
        self.assertIsNone(status["error"])
        copies = list((self.root / "daily").glob("stryktips-*.db.gz"))
        self.assertEqual(1, len(copies))
        snap = status["snapshot"]
        self.assertEqual("ok", snap["quick_check"])
        self.assertEqual(backup_db.sha256_of(copies[0]), snap["gz_sha256"])
        self.assertEqual({"pool_played": 500}, snap["table_counts"])
        restored = self.base / "restored.db"
        with gzip.open(copies[0], "rb") as src, open(restored, "wb") as dst:
            dst.write(src.read())
        conn = sqlite3.connect(restored)
        self.assertEqual("delete", conn.execute("PRAGMA journal_mode").fetchone()[0])
        self.assertEqual(500, conn.execute("SELECT COUNT(*) FROM pool_played").fetchone()[0])
        conn.close()
        saved = json.loads((self.root / "status.json").read_text())
        self.assertEqual("2026-09-24T02:15:00Z", saved["last_ok_at"])

    def test_misslyckad_kontroll_sparar_ingen_kopia(self):
        with mock.patch.object(backup_db, "quick_check", return_value="skadad sida"):
            status = backup_db.run(self.src, self.root, backup_db.DEFAULT_REMOTE,
                                   keep=14, push=False, now=NOW)
        self.assertFalse(status["ok"])
        self.assertIn("quick_check", status["error"])
        self.assertEqual([], list((self.root / "daily").glob("stryktips-*")))

    def test_rotation_behaller_de_senaste(self):
        daily = self.root / "daily"
        daily.mkdir(parents=True)
        for day in range(1, 6):
            (daily / f"stryktips-202609{day:02d}T021500Z.db.gz").write_bytes(b"x")
        removed = backup_db.rotate(daily, keep=2)
        self.assertEqual(3, len(removed))
        left = sorted(p.name for p in daily.glob("*.db.gz"))
        self.assertEqual(["stryktips-20260904T021500Z.db.gz",
                          "stryktips-20260905T021500Z.db.gz"], left)

    def test_delar_satts_ihop_till_originalet(self):
        blob = self.base / "blob.gz"
        blob.write_bytes(bytes(range(256)) * 1000)
        out = self.base / "parts"
        out.mkdir()
        parts = backup_db.split_file(blob, out, part_bytes=70_000)
        self.assertEqual(4, len(parts))
        joined = b"".join((out / p["name"]).read_bytes() for p in parts)
        self.assertEqual(blob.read_bytes(), joined)

    def test_publicering_skriver_om_repot_till_en_commit(self):
        bare = self.base / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        remote = str(bare)
        with mock.patch.object(backup_db, "ALLOWED_REMOTES", frozenset({remote})):
            first = backup_db.run(self.src, self.root, remote, keep=14,
                                  push=True, now=NOW)
            second = backup_db.run(self.src, self.root, remote, keep=14, push=True,
                                   now=NOW + dt.timedelta(days=1))
        self.assertTrue(first["pushed"], first.get("error"))
        self.assertTrue(second["pushed"], second.get("error"))
        self.assertEqual("1", _git(bare, "rev-list", "--count", "main"))
        manifest = json.loads(_git(bare, "show", "main:MANIFEST.json"))
        self.assertEqual("2026-09-25T02:15:00Z", manifest["created_at"])
        self.assertTrue(manifest["parts"])
        self.assertIn("PRIVAT", _git(bare, "show", "main:README.md"))

    def test_spärren_stoppar_fel_repo(self):
        status = backup_db.run(self.src, self.root,
                               "git@github.com:t0mteee/spelkompisen.git",
                               keep=14, push=True, now=NOW)
        self.assertTrue(status["ok"])
        self.assertFalse(status["pushed"])
        self.assertIn("otillåtet", status["error"])


if __name__ == "__main__":
    unittest.main()
