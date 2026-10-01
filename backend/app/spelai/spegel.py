"""Spegling av agentens repo till GitHub (fas F).

Agenten kan inte pusha själv (sandboxen spärrar `~/.ssh` och nyckelringen),
så facitsidan speglar: högst var 10:e minut hämtas `main` FRÅN
`~/spel-ai-kompisen` till en betrodd bar spegel `~/spel-ai-spegel.git`, och
om `main` ändrats sedan senaste lyckade push pushas den FRÅN spegeln till
`git@github.com:t0mteee/spel-ai-kompisen.git`.

* git körs aldrig med agentrepot som arbetskatalog — bara `--git-dir=<spegel>`
  och agentrepot som källa för `fetch` — och alltid med
  `core.hooksPath=/dev/null`, så inga krokar körs (agentens eller andras).
* Miljön är ren (inga hemligheter ur `.env`), terminalfrågor är avstängda och
  ssh kör i BatchMode.
* Push är bara fast-forward. Har agenten skrivit om `main` avvisar GitHub
  pushen; det loggas som `spegel_fel` en gång per huvud och spegeln står still
  tills någon bestämt vad som gäller.
* Senast pushade huvud bärs i spegeln som `refs/spegel/pushad`, så en push som
  misslyckats görs om nästa gång.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from . import tillstand
from .roller import AGENT_REPO, HOME

SPEGEL = HOME / "spel-ai-spegel.git"
REMOTE = "git@github.com:t0mteee/spel-ai-kompisen.git"
INTERVALL = dt.timedelta(minutes=10)
PUSHAD_REF = "refs/spegel/pushad"
TIMEOUT_S = 120

Runner = Callable[[list, dict, float], tuple]


def _local_runner(argv: list, env: dict, timeout: float) -> tuple:
    try:
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL,
                              cwd=str(HOME))
    except subprocess.TimeoutExpired:
        return 124, "", f"tidsgräns {timeout:.0f} s"
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _miljo() -> dict:
    env = {"HOME": str(HOME), "PATH": "/usr/bin:/bin", "LANG": "en_US.UTF-8",
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=20"}
    for key in ("SSH_AUTH_SOCK", "TMPDIR"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _git(runner: Runner, spegel: Path, *args: str) -> tuple:
    argv = ["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
            f"--git-dir={spegel}", *args]
    return runner(argv, _miljo(), TIMEOUT_S)


def _rev(runner: Runner, spegel: Path, ref: str) -> Optional[str]:
    rc, out, _err = _git(runner, spegel, "rev-parse", "--verify", "-q", ref)
    return out.strip() if rc == 0 and out.strip() else None


def _senast_hamtad(spegel: Path) -> Optional[dt.datetime]:
    fetch_head = spegel / "FETCH_HEAD"
    if not fetch_head.exists():
        return None
    return dt.datetime.fromtimestamp(fetch_head.stat().st_mtime, dt.timezone.utc)


def spegla(conn, *, now: dt.datetime, kalla: Path = AGENT_REPO,
           spegel: Path = SPEGEL, remote: str = REMOTE,
           runner: Runner = _local_runner, intervall: dt.timedelta = INTERVALL) -> dict:
    """Ett speglingsvarv. Returnerar vad som hände (tomt = inget att göra)."""
    senast = _senast_hamtad(spegel)
    if senast is not None and now - senast < intervall:
        return {}
    if not (kalla / ".git").exists():
        return {"fel": f"källan saknas: {kalla}"}
    report: dict = {}
    if not (spegel / "HEAD").exists():
        rc, _out, err = runner(["/usr/bin/git", "-c", "core.hooksPath=/dev/null",
                                "init", "--bare", "-q", str(spegel)], _miljo(), TIMEOUT_S)
        if rc != 0:
            return {"fel": f"git init: {err.strip()[-300:]}"}
        tillstand.logga(conn, "spegel_skapad", str(spegel), None, now=now)
        report["skapad"] = True
    rc, _out, err = _git(runner, spegel, "fetch", "--quiet", "--no-tags",
                         str(kalla), "+refs/heads/main:refs/heads/main")
    if rc != 0:
        return {**report, "fel": f"fetch: {err.strip()[-300:]}"}
    main = _rev(runner, spegel, "refs/heads/main")
    pushad = _rev(runner, spegel, PUSHAD_REF)
    if not main or main == pushad:
        return report
    rc, _out, err = _git(runner, spegel, "push", "--quiet", "--porcelain", remote,
                         "refs/heads/main:refs/heads/main")
    if rc != 0:
        orsak = " ".join(err.split())[-300:]
        tillstand.logga(conn, "spegel_fel", main[:12], {"orsak": orsak, "main": main},
                        now=now, dedup_key=f"spegel_fel:{main}")
        return {**report, "fel": f"push: {orsak}"}
    _git(runner, spegel, "update-ref", PUSHAD_REF, main)
    tillstand.logga(conn, "spegel_push", main[:12],
                    {"fran": pushad, "till": main, "remote": remote}, now=now)
    return {**report, "push": {"fran": pushad and pushad[:12], "till": main[:12]}}
