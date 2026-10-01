"""Fas F runt rollerna: GitHub-spegeln (mot LOKALA repon), skärmbilderna och
registreringen i tjänstelistan och vakten. Aldrig GitHub, Chrome eller claude."""
import datetime as dt
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from spelai_fixtur import START, ny_store  # noqa: E402
from app import vakt  # noqa: E402
from app.spelai import skarmbilder, spegel  # noqa: E402
import spelkompisen_tjanster as tjanster  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def git(*args, cwd=None):
    env = {"HOME": os.environ.get("HOME", "/tmp"), "PATH": "/usr/bin:/bin",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1"}
    out = subprocess.run(["/usr/bin/git", *args], cwd=cwd, env=env, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


class SpegelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn
        self.kalla = self.root / "spel-ai-kompisen"
        self.kalla.mkdir()
        git("init", "-q", "-b", "main", cwd=self.kalla)
        self.commit("första")
        self.github = self.root / "github.git"
        git("init", "-q", "--bare", str(self.github))
        self.spegel = self.root / "spel-ai-spegel.git"

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def commit(self, text):
        (self.kalla / "fil.txt").write_text(text, encoding="utf-8")
        git("add", "fil.txt", cwd=self.kalla)
        git("commit", "-q", "-m", text, cwd=self.kalla)
        return git("rev-parse", "HEAD", cwd=self.kalla)

    def spegla(self, now):
        return spegel.spegla(self.conn, now=now, kalla=self.kalla, spegel=self.spegel,
                             remote=str(self.github))

    def remote_main(self):
        return git(f"--git-dir={self.github}", "rev-parse", "refs/heads/main")

    def backdate(self, minutes):
        fetch_head = self.spegel / "FETCH_HEAD"
        stamp = fetch_head.stat().st_mtime - minutes * 60
        os.utime(fetch_head, (stamp, stamp))

    def test_skapar_spegeln_pushar_och_respekterar_intervallet(self):
        head = git("rev-parse", "HEAD", cwd=self.kalla)
        now = dt.datetime.now(UTC)
        rapport = self.spegla(now)
        self.assertTrue(rapport.get("skapad"))
        self.assertEqual(head[:12], rapport["push"]["till"])
        self.assertEqual(head, self.remote_main())
        self.assertTrue((self.spegel / "HEAD").exists())
        # inom 10 min: ingenting, inte ens fetch
        ny = self.commit("andra")
        self.assertEqual({}, self.spegla(now))
        self.assertEqual(head, self.remote_main())
        # efter intervallet: den nya committen speglas
        self.backdate(11)
        self.assertEqual(ny[:12], self.spegla(now)["push"]["till"])
        self.assertEqual(ny, self.remote_main())
        # oförändrad main: hämtas men pushas inte
        self.backdate(11)
        self.assertEqual({}, self.spegla(now))
        kinds = [r[0] for r in self.conn.execute(
            "SELECT kind FROM spelai_event WHERE kind LIKE 'spegel%' ORDER BY id")]
        self.assertEqual(["spegel_skapad", "spegel_push", "spegel_push"], kinds)

    def test_krokar_kors_aldrig(self):
        self.spegla(dt.datetime.now(UTC))
        self.commit("andra")          # testets egen commit, före krokarna
        marker = self.root / "krok-kordes"
        for hooks in (self.spegel / "hooks", self.kalla / ".git" / "hooks"):
            for name in ("pre-push", "reference-transaction", "post-update"):
                hook = hooks / name
                hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
                hook.chmod(0o755)
        self.backdate(11)
        self.assertIn("push", self.spegla(dt.datetime.now(UTC)))
        self.assertFalse(marker.exists())

    def test_omskriven_historik_pushas_inte_och_loggas_en_gang(self):
        now = dt.datetime.now(UTC)
        self.spegla(now)
        self.commit("andra")
        self.backdate(11)
        self.spegla(now)
        pushad = self.remote_main()
        git("reset", "-q", "--hard", "HEAD~1", cwd=self.kalla)
        self.commit("omskriven")
        for _ in range(2):
            self.backdate(11)
            self.assertIn("push:", self.spegla(now).get("fel", ""))
        self.assertEqual(pushad, self.remote_main())          # aldrig force
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_event WHERE kind='spegel_fel'").fetchone()[0])

    def test_kor_aldrig_git_i_agentrepot(self):
        calls = []

        def runner(argv, env, timeout):
            calls.append(argv)
            return subprocess.run(argv, env=env, capture_output=True, text=True,
                                  cwd=str(self.root)).returncode, "", ""
        spegel.spegla(self.conn, now=NOW, kalla=self.kalla, spegel=self.spegel,
                      remote=str(self.github), runner=runner)
        self.assertTrue(calls)
        for argv in calls:
            self.assertEqual("/usr/bin/git", argv[0])
            self.assertIn("core.hooksPath=/dev/null", argv)
            self.assertFalse(any(a.startswith(("-C", "--work-tree")) for a in argv))
            self.assertFalse(any(a == f"--git-dir={self.kalla}" for a in argv))

    def test_saknad_kalla_ar_ett_fel_utan_spegel(self):
        rapport = spegel.spegla(self.conn, now=NOW, kalla=self.root / "finns-inte",
                                spegel=self.spegel, remote=str(self.github))
        self.assertIn("källan saknas", rapport["fel"])
        self.assertFalse(self.spegel.exists())


class SkarmbildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_alla_flikar_i_bada_formaten_med_ren_miljo(self):
        calls = []

        def runner(argv, env, timeout):
            calls.append((argv, env))
            if "#/live" in argv[2]:
                return 1, "", "Chrome svarade inte"
            Path(argv[3]).write_bytes(b"\x89PNG")
            return 0, "{}", ""
        os.environ["SPELAI_NTFY_TOPIC"] = "hemligt"
        try:
            rapport = skarmbilder.ta("2026-10-04", ut_rot=self.root, runner=runner)
        finally:
            del os.environ["SPELAI_NTFY_TOPIC"]
        self.assertEqual(10, len(calls))
        urls = [argv[2] for argv, _env in calls]
        self.assertEqual({"http://127.0.0.1:5176/#/", "http://127.0.0.1:5176/#/pool",
                          "http://127.0.0.1:5176/#/beslut", "http://127.0.0.1:5176/#/live",
                          "http://127.0.0.1:5176/#/agent"}, set(urls))
        for argv, env in calls:
            self.assertEqual(str(skarmbilder.SCRIPT), argv[1])
            self.assertEqual(["390", "844"], argv[4:6])
            self.assertTrue(Path(argv[3]).parent == self.root / "2026-10-04")
            self.assertEqual("http://127.0.0.1:5176", env["SKARMBILD_ORIGIN"])
            self.assertNotIn("SPELAI_NTFY_TOPIC", env)
            self.assertEqual("/usr/bin:/bin", env["PATH"])
        self.assertEqual(8, len(rapport["filer"]))
        self.assertIn("hem-390x844.png", rapport["filer"])
        self.assertIn("agent-hel.png", rapport["filer"])
        self.assertEqual(2, len(rapport["fel"]))
        with self.assertRaises(ValueError):
            skarmbilder.ta("../../x", ut_rot=self.root, runner=runner)

    def test_betrodda_skriptet_ar_last(self):
        """Granskningens krav på kopian (docs/spelai-facit.md "Rollkörningar")."""
        text = skarmbilder.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--remote-debugging-pipe", text)
        self.assertNotIn("--remote-debugging-port", text)
        self.assertIn("--proxy-server=http://127.0.0.1:9", text)
        # senare regler går före: `<-loopback>` först, annars nekas ursprunget
        self.assertIn("--proxy-bypass-list=<-loopback>;${ORIGIN.host}", text)
        self.assertIn("target.origin !== ORIGIN.origin", text)
        for forbjudet in ("fetch(", "WebSocket", "http.request", "https", "net.connect"):
            self.assertNotIn(forbjudet, text.split("import process")[1])
        self.assertEqual(1, text.count("writeFile("))


class RegistreringTests(unittest.TestCase):
    def test_tjanst_plist_och_vakt(self):
        service = tjanster.BY_KEY["spelai-roller"]
        self.assertEqual("com.saman.spelai.roller", service.label)
        self.assertEqual("spel-ai-kompisen", service.project)
        self.assertTrue(service.scheduled)
        self.assertIn("spelai-roller", tjanster.GROUPS["spelai"])
        self.assertIn(("spelai-roller", False), vakt.JOBS)
        plist = plistlib.loads((ROOT / "backend" / "scripts"
                                / "com.saman.spelai.roller.plist").read_bytes())
        self.assertEqual("com.saman.spelai.roller", plist["Label"])
        self.assertEqual(300, plist["StartInterval"])
        self.assertEqual(10, plist["Nice"])
        self.assertEqual(["cli.py", "spelai-roller"], plist["ProgramArguments"][-2:])
        self.assertTrue(plist["StandardOutPath"].endswith("backend/data/spelai-roller.out.log"))
        self.assertTrue(plist["StandardErrorPath"].endswith("backend/data/spelai-roller.err.log"))


if __name__ == "__main__":
    unittest.main()
