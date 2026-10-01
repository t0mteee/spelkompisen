"""Sandboxen: fail closed, kontraktet, och (på macOS) riktiga gränser."""
import json
import os
import sys
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path

from app.spelai import sandbox

HAS_SANDBOX = os.path.isfile(sandbox.SANDBOX_EXEC_DEFAULT)


def _agent(root: Path, body: str) -> Path:
    pkg = root / "agent"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "forslag.py").write_text(textwrap.dedent(body))
    return root


class FailClosedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.marker = self.root / "agentkod-kordes.txt"
        self.agent_dir = _agent(self.root / "agentrepo", f"""
            open({str(self.marker)!r}, "w").write("kördes")
            print("{{}}")
        """)

    def tearDown(self):
        self.tmp.cleanup()

    def _cfg(self, **kw):
        base = dict(db_path=self.root / "x.db", agent_dir=self.agent_dir,
                    python=Path(sys.executable), data_dir=self.root)
        base.update(kw)
        return sandbox.AgentConfig(**base)

    def test_saknad_sandbox_kor_ingen_agentkod(self):
        svar = sandbox.run(self._cfg(sandbox_exec=str(self.root / "finns-inte")),
                           {"x": 1}, [256], 5)
        self.assertEqual("saknas", svar.status)
        self.assertIn("sandbox saknas", svar.reason)
        self.assertFalse(self.marker.exists())

    def test_saknad_agentkatalog_profil_eller_python(self):
        for kw, text in ((dict(agent_dir=self.root / "nej"), "agentkatalogen"),
                         (dict(profile=self.root / "nej.sb"), "profilen"),
                         (dict(python=self.root / "nej-python"), "python")):
            svar = sandbox.run(self._cfg(**kw), {}, [256], 5)
            self.assertEqual("saknas", svar.status, kw)
            self.assertIn(text, svar.reason)
        self.assertFalse(self.marker.exists())

    def test_kommandot_foljer_kontraktet(self):
        cmd = sandbox.command(self._cfg(), Path("/tmp/indata.json"), [256, 512])
        self.assertIn("-f", cmd)
        tail = cmd[cmd.index(str(Path(sys.executable))):]
        self.assertEqual([str(Path(sys.executable)), "-B", "-m", "agent.forslag",
                          "--indata", "/tmp/indata.json", "--nivaer", "256,512"], tail)


@unittest.skipUnless(HAS_SANDBOX, "sandbox-exec finns bara på macOS")
class RiktigSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, body, timeout=60):
        agent_dir = _agent(self.root / f"repo-{uuid.uuid4().hex[:6]}", body)
        cfg = sandbox.AgentConfig(db_path=self.root / "x.db", agent_dir=agent_dir,
                                  python=Path(sys.executable), data_dir=self.data)
        return sandbox.run(cfg, {"product": "topptipset", "n_matches": 8}, [256], timeout)

    def test_giltigt_svar_lases_fran_stdout(self):
        svar = self._run("""
            import argparse, json, sys
            ap = argparse.ArgumentParser(); ap.add_argument("--indata"); ap.add_argument("--nivaer")
            a = ap.parse_args()
            p = json.load(open(a.indata))
            print("logg till stderr", file=sys.stderr)
            print(json.dumps({"version": "t", "forslag": {"256": {"format": "rows",
                  "rows": ["1" * p["n_matches"]]}}, "nivaer": a.nivaer}))
        """)
        self.assertEqual("ok", svar.status, svar.reason)
        self.assertEqual("256", svar.data["nivaer"])
        self.assertIn("logg till stderr", svar.stderr)

    def test_exitkod_timeout_och_ogiltig_json(self):
        self.assertEqual("fel", self._run("raise SystemExit(3)").status)
        svar = self._run("import time; time.sleep(30)", timeout=2)
        self.assertEqual(("fel", "timeout efter 2 s"), (svar.status, svar.reason))
        svar = self._run("print('inte json')")
        self.assertIn("ogiltig JSON", svar.reason)

    def test_natverk_och_skrivning_utanfor_datakatalogen_nekas(self):
        forbjuden = Path.home() / f".spelai-sandboxprov-{uuid.uuid4().hex[:8]}"
        svar = self._run(f"""
            import json, socket
            res = {{}}
            try:
                open({str(forbjuden)!r}, "w").write("x"); res["hem"] = "tillaten"
            except OSError: res["hem"] = "nekad"
            try:
                open({str(self.data / 'ok.txt')!r}, "w").write("x"); res["data"] = "tillaten"
            except OSError: res["data"] = "nekad"
            try:
                socket.create_connection(("127.0.0.1", 8002), timeout=2); res["natet"] = "tillatet"
            except OSError: res["natet"] = "nekat"
            print(json.dumps(res))
        """)
        try:
            self.assertEqual({"hem": "nekad", "data": "tillaten", "natet": "nekat"}, svar.data)
            self.assertFalse(forbjuden.exists())
        finally:
            if forbjuden.exists():
                forbjuden.unlink()


if __name__ == "__main__":
    unittest.main()
