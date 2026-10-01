"""Skärmbilder åt rollen Användaren (fas F).

Agentens Bash når inte 127.0.0.1 (gränsprovet 2026-10-01), så facitsidan tar
bilderna av agentens app (5176) före en `veckogenomgang` och lägger dem i
`~/spel-ai-data/skarmbilder/<YYYY-MM-DD>/`: varje flik i äkta 390×844 och som
helsida.

Skriptet är facitsidans BETRODDA kopia `tools/spelai/skarmbild.mjs` (granskad
mot agentens original): bara ursprunget nedan, död proxy för allt annat,
DevTools över pipe. Miljön är ren — inga hemligheter ur Spelkompisens `.env`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .roller import AGENT_DATA, HOME

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "tools" / "spelai" / "skarmbild.mjs"
NODE = HOME / ".local" / "spelkompisen-runtime" / "bin" / "node"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
APP_ORIGIN = "http://127.0.0.1:5176"
FLIKAR = (("hem", "#/"), ("pool", "#/pool"), ("beslut", "#/beslut"),
          ("live", "#/live"), ("agent", "#/agent"))
FORMAT = (("390x844", "0"), ("hel", "1"))
BREDD, HOJD = 390, 844
TIMEOUT_S = 90

Runner = Callable[[list, dict, float], tuple]


def _local_runner(argv: list, env: dict, timeout: float) -> tuple:
    try:
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return 124, "", f"tidsgräns {timeout:.0f} s"
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def ta(dag: str, *, ut_rot: Optional[Path] = None, runner: Runner = _local_runner,
       node: Path = NODE, script: Path = SCRIPT, chrome: Path = CHROME,
       origin: str = APP_ORIGIN) -> dict:
    """Ta alla flikar i båda formaten. Returnerar {katalog, filer, fel}."""
    if not (len(dag) == 10 and dag[4] == "-" and dag[7] == "-"
            and dag.replace("-", "").isdigit()):
        raise ValueError(f"ogiltigt datum: {dag}")
    katalog = Path(ut_rot or AGENT_DATA / "skarmbilder") / dag
    katalog.mkdir(parents=True, exist_ok=True)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(HOME), "LANG": "en_US.UTF-8",
           "SKARMBILD_ORIGIN": origin, "CHROME": str(chrome)}
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    filer, fel = [], []
    for namn, fragment in FLIKAR:
        for suffix, hel in FORMAT:
            fil = katalog / f"{namn}-{suffix}.png"
            argv = [str(node), str(script), f"{origin}/{fragment}", str(fil),
                    str(BREDD), str(HOJD), hel]
            rc, _out, err = runner(argv, env, TIMEOUT_S)
            if rc == 0 and fil.exists():
                filer.append(fil.name)
            else:
                fel.append(f"{fil.name}: exit {rc} {' '.join(str(err).split())[-200:]}")
    return {"katalog": str(katalog), "filer": filer, "fel": fel}
