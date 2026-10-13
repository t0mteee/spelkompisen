"""Driftsättning av agentens app via beslutssidan (app/spelai/driftsattning.py).

Agentrepot och spegeln är riktiga temporära git-repon (git körs bara mot
spegeln, som i drift). Bygget, omstarterna, hälsan, skärmbilden och pushen är
fejkade: testerna kör aldrig sandbox-exec, launchctl, Chrome eller GitHub.
"""
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app.spelai import driftsattning, inkorg, schemalaggare  # noqa: E402

SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/27.0 Mobile/15E148 Safari/604.1")
NU = START + dt.timedelta(days=12)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = ny_store(self.tmp)
        self.conn = self.store.conn
        self.repo = root / "spel-ai-kompisen"
        (self.repo / "frontend" / "src").mkdir(parents=True)
        (self.repo / "frontend" / "node_modules").mkdir()
        (self.repo / "backend" / "agent_api").mkdir(parents=True)
        (self.repo / "frontend" / "src" / "main.js").write_text("v1")
        (self.repo / "backend" / "agent_api" / "main.py").write_text("v1")
        (self.repo / ".gitignore").write_text("node_modules\ndist\n")
        (self.repo / "frontend" / "dist").mkdir()
        (self.repo / "frontend" / "dist" / "index.html").write_text("FÖRRA")
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "-c", "user.email=a@b", "-c", "user.name=a", "add", ".")
        git(self.repo, "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "-m", "v1")
        self.commit = git(self.repo, "rev-parse", "HEAD")
        self.utkorg = root / "utkorg"
        self.utkorg.mkdir()
        self.halsa = {"api": 200, "app": 200}
        self.omstarter, self.byggen, self.pushar = [], [], []
        self.env = driftsattning.Miljo(
            agent_repo=self.repo, rot=root / "driftsattning",
            spegel_path=root / "spegel.git", runner=self.fejk_bygg,
            http_status=lambda url: self.halsa["api" if "8003" in url else "app"],
            omstart=self.fejk_omstart, skarmbild=self.fejk_bild, spegla=self.fejk_spegla,
            sov=lambda s: None, halsa_vanta_s=0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    # fejkade steg
    def fejk_bygg(self, argv, env, timeout, cwd):
        self.byggen.append((argv, Path(cwd)))
        self.assertEqual("/usr/bin/sandbox-exec", argv[0])
        self.assertIn(str(driftsattning.BYGG_PROFIL), argv)
        src = (Path(cwd) / "src" / "main.js").read_text()
        (Path(cwd) / "dist").mkdir()
        (Path(cwd) / "dist" / "index.html").write_text(f"BYGGD {src}")
        return 0, "built", ""

    def fejk_omstart(self, tjanst):
        self.omstarter.append(tjanst)
        return True, "omstartad"

    def fejk_bild(self, ut):
        ut.write_bytes(b"png")
        return True, ""

    def fejk_spegla(self, conn, **kwargs):
        self.pushar.append(kwargs)
        return {"push": {"till": self.commit[:12]}}

    # hjälp
    def begaran(self, **extra):
        data = {"id": "koordinatorn-2026-10-14-drift-1", "typ": "driftsattning",
                "kalla": "Koordinatorn", "rubrik": "Ny Live-flik",
                "varfor": "Live-fliken visar kassan per dag.", "commit": self.commit,
                "steg": ["push", "bygg_app", "omstart_api"], **extra}
        (self.utkorg / f"{data['id']}.json").write_text(json.dumps(data), encoding="utf-8")
        return inkorg.las_in(self.conn, self.utkorg, now=NU)

    def inbox_id(self):
        return self.conn.execute("SELECT id FROM spelai_inbox").fetchone()[0]

    def svara(self, val="0", user_agent=SAFARI):
        inkorg.svara(self.conn, self.inbox_id(), val, None, user_agent=user_agent,
                     forwarded_for=None, client_host="127.0.0.1", now=NU)

    def kor(self):
        return driftsattning.kor(self.conn, now=lambda: NU, env=self.env)


class FormatTests(Base):
    def test_begaran_blir_beslut_med_fasta_alternativ(self):
        self.assertEqual(1, self.begaran()["inlasta"])
        post = inkorg.lista(self.conn, now=NU)[0]
        self.assertEqual("beslut", post["typ"])
        self.assertEqual(["Godkänn: kör stegen", "Avvisa"],
                         [alt["text"] for alt in post["alternativ"]])
        self.assertEqual(self.commit, post["driftsattning"]["commit"])
        # Stegen i fast ordning, oavsett agentens ordning.
        self.assertEqual(["bygg_app", "omstart_api", "push"], post["driftsattning"]["steg"])
        self.assertIsNone(post["driftsattning"]["resultat"])

    def test_ogiltiga_begaranden_avvisas(self):
        fall = ({"commit": self.commit[:12]}, {"commit": "Z" * 40}, {"steg": []},
                {"steg": ["rm -rf /"]}, {"steg": ["push", "push"]},
                {"alternativ": [{"text": "Godkänn"}]})
        for i, extra in enumerate(fall):
            rep = self.begaran(id=f"x-{i}", **extra)
            self.assertEqual(1, rep["avvisade"], extra)
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM spelai_inbox").fetchone()[0])


class KorningTests(Base):
    def test_godkand_driftsattning_kors_en_gang(self):
        self.begaran()
        self.assertEqual({}, self.kor())                 # inget svar än
        self.svara()
        kort = self.kor()
        self.assertEqual("gron", kort["status"], kort)
        live = (self.repo / "frontend" / "dist" / "index.html").read_text()
        self.assertEqual("BYGGD v1", live)
        self.assertEqual(["spelai-app", "spelai-api"], self.omstarter)
        self.assertEqual(1, len(self.pushar))
        self.assertEqual(dt.timedelta(0), self.pushar[0]["intervall"])
        katalog = Path(kort["katalog"])
        resultat = json.loads((katalog / "resultat.json").read_text())
        self.assertEqual(("gron", self.commit), (resultat["status"], resultat["commit"]))
        self.assertTrue((katalog / "hem-390x844.png").exists())
        self.assertEqual("FÖRRA", (katalog / "dist-forra" / "index.html").read_text())
        self.assertEqual({}, self.kor())                  # aldrig två gånger
        post = inkorg.lista(self.conn, now=NU)[0]
        self.assertEqual("gron", post["driftsattning"]["resultat"]["status"])

    def test_avvisad_eller_misstankt_svar_kor_inget(self):
        self.begaran()
        self.svara("1")
        self.assertEqual({}, self.kor())
        self.tearDown(); self.setUp()
        self.begaran()
        self.svara("0", user_agent="curl/8.7.1")
        self.assertEqual({}, self.kor())
        self.assertEqual([], self.byggen)

    def test_fel_commit_avbryter_fore_bygget(self):
        self.begaran(commit="a" * 40)
        self.svara()
        kort = self.kor()
        self.assertEqual("avbruten", kort["status"])
        self.assertIn("inte aaaaaaaaaaaa", kort["orsak"])
        self.assertEqual(([], [], []), (self.byggen, self.omstarter, self.pushar))
        self.assertEqual("FÖRRA", (self.repo / "frontend" / "dist" / "index.html").read_text())

    def test_ocommittad_backend_avbryter_omstarten(self):
        (self.repo / "backend" / "agent_api" / "main.py").write_text("ocommittat")
        self.begaran()
        self.svara()
        kort = self.kor()
        self.assertEqual("avbruten", kort["status"])
        self.assertIn("backend/agent_api/main.py", kort["orsak"])
        self.assertEqual([], self.omstarter)

    def test_bygget_anvander_commiten_inte_arbetskopian(self):
        (self.repo / "frontend" / "src" / "main.js").write_text("ocommittat")
        self.begaran(steg=["bygg_app"])
        self.svara()
        self.assertEqual("gron", self.kor()["status"])
        self.assertEqual("BYGGD v1", (self.repo / "frontend" / "dist" / "index.html").read_text())
        self.assertEqual([], self.pushar)

    def test_rod_halsa_aterstaller_forra_bygget_och_pushar_inte(self):
        self.halsa["app"] = None
        self.begaran()
        self.svara()
        kort = self.kor()
        self.assertEqual("rod", kort["status"])          # appen svarar inte ens efteråt
        self.assertEqual("FÖRRA", (self.repo / "frontend" / "dist" / "index.html").read_text())
        self.assertEqual(["spelai-app", "spelai-api", "spelai-app", "spelai-api"], self.omstarter)
        self.assertEqual([], self.pushar)

    def test_misslyckat_bygge_rors_inte_dist(self):
        self.env.runner = lambda argv, env, timeout, cwd: (1, "", "vite: syntaxfel")
        self.begaran()
        self.svara()
        kort = self.kor()
        self.assertEqual("avbruten", kort["status"])
        self.assertIn("vite: syntaxfel", kort["orsak"])
        self.assertEqual("FÖRRA", (self.repo / "frontend" / "dist" / "index.html").read_text())
        self.assertEqual([], self.omstarter)

    def test_ticken_kor_bara_med_miljo(self):
        self.begaran()
        self.svara()
        rep = schemalaggare.tick(self.store, runner=None, clock=lambda: NU, utkorg=self.utkorg)
        self.assertEqual({}, rep["driftsattning"])
        rep = schemalaggare.tick(self.store, runner=None, clock=lambda: NU, utkorg=self.utkorg,
                                 drift_miljo=self.env)
        self.assertEqual("gron", rep["driftsattning"]["status"])


if __name__ == "__main__":
    unittest.main()
