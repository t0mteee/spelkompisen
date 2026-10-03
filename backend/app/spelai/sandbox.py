"""Kör agentens poolbyggare i en macOS-sandbox och läs ENBART stdout (JSON).

Kontrakt (docs/spelai-facit.md):

    <agent_python> -B -m agent.forslag --indata <fil.json> --nivaer 256,512,...

med arbetskatalog `~/spel-ai-kompisen/backend`, inuti
`sandbox-exec -f app/spelai/agent.sb` (inget nätverk, skrivning bara i
`~/spel-ai-data`, temp och `stryktips.db-shm`; `~/.ssh`, `~/svs`, `~/vm` och
`.env`-filer spärrade även för läsning).

FAIL CLOSED: saknas sandbox-exec, profilen, agentkatalogen eller agentens
python körs INGEN agentkod — svaret blir `saknas`.

SQLite i WAL-läge: en `mode=ro`-läsare i sandboxen kan inte skapa `-wal`/
`-shm`. Provat 2026-10-01 på servern: läsningen lyckas när en annan process
håller databasen öppen (då finns båda filerna) och misslyckas annars. Den som
anropar `run` håller därför sin egen anslutning öppen under körningen
(`spelai-tick` gör det alltid).
"""
from __future__ import annotations

import dataclasses
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

HOME = Path.home()
AGENT_DIR_DEFAULT = HOME / "spel-ai-kompisen" / "backend"
AGENT_DATA_DEFAULT = HOME / "spel-ai-data"
SANDBOX_EXEC_DEFAULT = "/usr/bin/sandbox-exec"
PROFILE = Path(__file__).with_name("agent.sb")
TIMEOUT_S = 180
STDERR_MAX = 2000
STDOUT_MAX = 50 * 1024 * 1024
NICE = "/usr/bin/nice"


@dataclasses.dataclass
class AgentSvar:
    status: str                 # "ok" | "fel" | "saknas"
    data: Optional[dict] = None
    reason: Optional[str] = None
    stderr: Optional[str] = None


@dataclasses.dataclass
class AgentConfig:
    db_path: Path
    agent_dir: Path = AGENT_DIR_DEFAULT
    python: Optional[Path] = None          # default: <agent_dir>/.venv/bin/python
    data_dir: Path = AGENT_DATA_DEFAULT
    sandbox_exec: str = SANDBOX_EXEC_DEFAULT
    profile: Path = PROFILE
    home: Path = HOME

    @classmethod
    def from_env(cls, db_path: Path) -> "AgentConfig":
        env = os.environ
        agent_dir = Path(env.get("SPELAI_AGENT_DIR") or AGENT_DIR_DEFAULT)
        python = env.get("SPELAI_AGENT_PYTHON")
        return cls(db_path=Path(db_path), agent_dir=agent_dir,
                   python=Path(python) if python else None,
                   data_dir=Path(env.get("SPELAI_DATA_DIR") or AGENT_DATA_DEFAULT))

    @property
    def agent_python(self) -> Path:
        return self.python or (self.agent_dir / ".venv" / "bin" / "python")


def _tail(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    return text[-STDERR_MAX:] if len(text) > STDERR_MAX else text


def tillganglig(cfg: AgentConfig) -> tuple[bool, Optional[str]]:
    """Får agentkod köras alls? Allt som saknas ⇒ fail closed."""
    if not (os.path.isfile(cfg.sandbox_exec) and os.access(cfg.sandbox_exec, os.X_OK)):
        return False, f"sandbox saknas ({cfg.sandbox_exec}) — ingen agentkod körs"
    if not Path(cfg.profile).is_file():
        return False, f"sandboxprofilen saknas ({cfg.profile})"
    if not Path(cfg.agent_dir).is_dir():
        return False, f"agentkatalogen saknas ({cfg.agent_dir})"
    if not (Path(cfg.agent_python).is_file() and os.access(cfg.agent_python, os.X_OK)):
        return False, f"agentens python saknas ({cfg.agent_python})"
    if not Path(cfg.data_dir).is_dir():
        return False, f"agentens datakatalog saknas ({cfg.data_dir})"
    return True, None


MODULER = ("agent.forslag", "agent.live")


def command(cfg: AgentConfig, indata: Path, nivaer: Optional[list[int]],
            modul: str = "agent.forslag") -> list[str]:
    """`agent.forslag` (poolen, med --nivaer) eller `agent.live` (fas E)."""
    if modul not in MODULER:
        raise ValueError(f"okänd agentmodul: {modul}")
    cmd = [cfg.sandbox_exec,
           "-D", f"HOME={cfg.home}",
           "-D", f"AGENT_DATA={Path(cfg.data_dir).resolve()}",
           "-D", f"DB_SHM={Path(cfg.db_path).resolve()}-shm",
           "-f", str(cfg.profile),
           str(cfg.agent_python), "-B", "-m", modul,
           "--indata", str(indata)]
    if nivaer is not None:
        cmd += ["--nivaer", ",".join(str(int(n)) for n in nivaer)]
    if os.path.exists(NICE):   # beslut 8: låg prioritet
        cmd = [NICE, "-n", "10", *cmd]
    return cmd


def run(cfg: AgentConfig, payload: dict, nivaer: Optional[list[int]],
        timeout: float = TIMEOUT_S, modul: str = "agent.forslag") -> AgentSvar:
    """Kör agenten EN gång för alla nivåer. Läser bara stdout."""
    ok, reason = tillganglig(cfg)
    if not ok:
        return AgentSvar("saknas", reason=reason)
    with tempfile.TemporaryDirectory(prefix="spelai-indata-") as tmp:
        path = Path(tmp) / "indata.json"
        path.write_text(json.dumps(payload, ensure_ascii=False))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(cfg.home), "LANG": "en_US.UTF-8",
               "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": tmp,
               "SPELAI_DB": str(Path(cfg.db_path).resolve()),
               # `agent` får ligga i backend/ eller i repots rot.
               "PYTHONPATH": os.pathsep.join(
                   (str(cfg.agent_dir), str(Path(cfg.agent_dir).parent)))}
        try:
            proc = subprocess.Popen(
                command(cfg, path, nivaer, modul), cwd=str(cfg.agent_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as exc:
            return AgentSvar("saknas", reason=f"kunde inte starta agenten: {exc}")
        try:
            out, err = proc.communicate(timeout=max(1.0, timeout))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            out, err = proc.communicate()
            return AgentSvar("fel", reason=f"timeout efter {int(timeout)} s",
                             stderr=_tail(err.decode("utf-8", "replace")))
    stderr = _tail(err.decode("utf-8", "replace"))
    if proc.returncode != 0:
        return AgentSvar("fel", reason=f"agenten avslutade med kod {proc.returncode}",
                         stderr=stderr)
    if len(out) > STDOUT_MAX:
        return AgentSvar("fel", reason="stdout för stort", stderr=stderr)
    try:
        data = json.loads(out.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return AgentSvar("fel", reason=f"ogiltig JSON på stdout: {exc}", stderr=stderr)
    if not isinstance(data, dict):
        return AgentSvar("fel", reason="svaret är inte ett JSON-objekt", stderr=stderr)
    return AgentSvar("ok", data=data, stderr=stderr)


Runner = Callable[[dict, list[int], float], AgentSvar]


def runner_for(cfg: AgentConfig) -> Runner:
    return lambda payload, nivaer, timeout: run(cfg, payload, nivaer, timeout)


def live_runner_for(cfg: AgentConfig) -> Callable[[dict, float], AgentSvar]:
    """`agent.live` (fas E): samma sandbox, en match per anrop, inga nivåer."""
    return lambda payload, timeout: run(cfg, payload, None, timeout, modul="agent.live")
