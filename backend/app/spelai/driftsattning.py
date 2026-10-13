"""Driftsättning av agentens app via beslutssidan (2026-10-13).

Beslut koordinatorn-2026-10-13-driftsattning-via-beslut (Saman, val 0). Agenten
lägger en begäran (`typ: "driftsattning"`, format i docs/spelai-facit.md avsnitt
17) i utkorgen. Inkorgen gör den till ett beslut med FASTA alternativ (Godkänn /
Avvisa), så agenten kan varken formulera knapparna eller lägga till steg. När
Saman godkänt från Spelkompisens beslutssida kör spelai-ticken stegen här, en
begäran åt gången och aldrig två gånger (`driftsattning_start:<id>` i
spelai_event). Bara stegen i `STEG` finns:

* `bygg_app`    bygg agentens app ur en ren `git archive` av commiten, i
                sandboxprofilen `bygg.sb` (inget nät, skriver bara i
                byggkatalogen), byt `frontend/dist` och starta om spelai-app (5176)
* `omstart_api` starta om spelai-api (8003); kräver att arbetskopians spårade
                filer under backend/ är byte-identiska med commiten
* `push`        pusha `main` till GitHub via den betrodda spegeln (`spegel.py`)

Ordning: commitkontroll (agentens `main` == commiten, hämtad till spegeln; git
körs aldrig i agentrepot) → bygge → installation → omstart → hälsa (8003
`/api/agent/health` och 5176 `/`) → skärmbild 390×844 → push. Röd hälsa:
förra `dist` läggs tillbaka, tjänsterna startas om och hälsan prövas igen;
ingen push. API-koden kan inte återställas här (agentrepot rörs aldrig med
git), så en röd API-hälsa efter återställning rapporteras som röd.

Resultatet skrivs till `~/spel-ai-data/driftsattning/<id>/resultat.json` (och
skärmbilden bredvid), så att agenten kan läsa det, och som `driftsattning_klar`
i spelai_event. Inget i Spelkompisen eller dess databas berörs av stegen.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import spegel, tillstand
from .roller import AGENT_DATA, AGENT_REPO, HOME
from .tillstand import iso

STEG = ("bygg_app", "omstart_api", "push")
STEG_TEXT = {"bygg_app": "Bygg agentens app (5176) och starta om den",
             "omstart_api": "Starta om agentens API (8003)",
             "push": "Pusha main till GitHub"}
ALTERNATIV = ({"text": "Godkänn: kör stegen", "rekommenderas": False},
              {"text": "Avvisa", "rekommenderas": False})
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
DRIFT_DIR = AGENT_DATA / "driftsattning"
REPO_ROOT = Path(__file__).resolve().parents[3]
BYGG_PROFIL = Path(__file__).with_name("bygg.sb")
NODE = HOME / ".local" / "spelkompisen-runtime" / "bin" / "node"
SANDBOX = "/usr/bin/sandbox-exec"
HALSA = (("api", "http://127.0.0.1:8003/api/agent/health"),
         ("app", "http://127.0.0.1:5176/"))
HALSA_VANTA_S = 45
BYGG_TIMEOUT_S = 300
TJANST = {"app": "spelai-app", "api": "spelai-api"}


class Ogiltig(ValueError):
    pass


def validera(data: dict) -> dict:
    """Driftsättningens egna fält. Returnerar {'commit', 'steg'} (steg i STEG-ordning)."""
    commit = data.get("commit")
    if not isinstance(commit, str) or not COMMIT_RE.match(commit):
        raise Ogiltig("'commit' måste vara hela commit-hashen (40 tecken 0–9, a–f)")
    steg = data.get("steg")
    if not isinstance(steg, list) or not steg or not all(isinstance(s, str) for s in steg):
        raise Ogiltig(f"'steg' måste vara en icke-tom lista ur {', '.join(STEG)}")
    okanda = sorted(set(steg) - set(STEG))
    if okanda:
        raise Ogiltig(f"okända steg {', '.join(okanda)} (tillåtna: {', '.join(STEG)})")
    if len(set(steg)) != len(steg):
        raise Ogiltig("'steg' innehåller dubbletter")
    if "alternativ" in data:
        raise Ogiltig("en driftsättning har fasta alternativ; ange inte 'alternativ'")
    return {"commit": commit, "steg": [s for s in STEG if s in steg]}


def alternativ(payload: dict) -> list[dict]:
    """De fasta alternativen; begäran bärs av det första (inkorgens tabell är orörd)."""
    return [{**ALTERNATIV[0], "driftsattning": payload}, dict(ALTERNATIV[1])]


def payload_for(alternativ_list: list) -> Optional[dict]:
    first = alternativ_list[0] if alternativ_list else None
    found = first.get("driftsattning") if isinstance(first, dict) else None
    return found if isinstance(found, dict) else None


def _katalog(external_id: str, rot: Path) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", external_id)[:100]
    return Path(rot) / safe


def status(conn, inbox_id: int) -> Optional[dict]:
    """Senaste kända läge för en driftsättning: None, 'pagar' eller resultatet."""
    klar = conn.execute(
        "SELECT detail_json FROM spelai_event WHERE dedup_key=?",
        (f"driftsattning_klar:{inbox_id}",)).fetchone()
    if klar:
        return json.loads(klar[0])
    if tillstand.har_handelse(conn, f"driftsattning_start:{inbox_id}"):
        return {"status": "pagar"}
    return None


# ── körmiljön (injiceras i testerna) ─────────────────────────────────────

Runner = Callable[[list, dict, float, Optional[Path]], tuple]


def _local_runner(argv: list, env: dict, timeout: float,
                  cwd: Optional[Path] = None) -> tuple:
    try:
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL,
                              cwd=str(cwd) if cwd else None)
    except subprocess.TimeoutExpired:
        return 124, "", f"tidsgräns {timeout:.0f} s"
    except OSError as exc:
        return 127, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _http_status(url: str, timeout: float = 5.0) -> Optional[int]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status
    except Exception:  # noqa: BLE001 — ingen kontakt = röd
        return None


def _omstart(tjanst: str) -> tuple[bool, str]:
    import sys
    tools = str(REPO_ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import spelkompisen_tjanster as tj
    result = tj.Launchd().restart(tj.BY_KEY[tjanst])
    return result.ok, result.message


def _skarmbild(ut: Path) -> tuple[bool, str]:
    from . import skarmbilder
    env = {"PATH": "/usr/bin:/bin", "HOME": str(HOME), "LANG": "en_US.UTF-8",
           "SKARMBILD_ORIGIN": skarmbilder.APP_ORIGIN, "CHROME": str(skarmbilder.CHROME)}
    if os.environ.get("TMPDIR"):
        env["TMPDIR"] = os.environ["TMPDIR"]
    rc, _out, err = _local_runner(
        [str(skarmbilder.NODE), str(skarmbilder.SCRIPT), f"{skarmbilder.APP_ORIGIN}/#/",
         str(ut), str(skarmbilder.BREDD), str(skarmbilder.HOJD), "0"],
        env, skarmbilder.TIMEOUT_S)
    return rc == 0 and ut.exists(), " ".join(str(err).split())[-200:]


@dataclass
class Miljo:
    agent_repo: Path = AGENT_REPO
    rot: Path = DRIFT_DIR
    spegel_path: Path = spegel.SPEGEL
    git_runner: Callable = spegel._local_runner          # noqa: SLF001
    runner: Runner = _local_runner
    http_status: Callable[[str], Optional[int]] = _http_status
    omstart: Callable[[str], tuple[bool, str]] = _omstart
    skarmbild: Callable[[Path], tuple[bool, str]] = _skarmbild
    spegla: Optional[Callable] = None                    # None = spegel.spegla
    sov: Callable[[float], None] = time.sleep
    halsa_vanta_s: float = HALSA_VANTA_S
    logg: list = field(default_factory=list)


# ── stegen ───────────────────────────────────────────────────────────────

def _packa_upp(tar_path: Path, mal: Path) -> list[str]:
    """Packa upp ett git-arkiv; bara vanliga filer och kataloger, inga sökvägar ut."""
    mal.mkdir(parents=True, exist_ok=True)
    filer = []
    with tarfile.open(tar_path) as arkivet:
        medlemmar = [m for m in arkivet.getmembers() if m.isfile() or m.isdir()]
        arkivet.extractall(mal, members=medlemmar, filter="data")
        filer = [m.name for m in medlemmar if m.isfile()]
    return filer


def _jamfor_backend(env: Miljo, commit: str, katalog: Path) -> list[str]:
    """Spårade filer under backend/ som skiljer sig mellan commiten och arbetskopian."""
    tar_path = katalog / "backend.tar"
    fel = spegel.arkiv(commit, tar_path, "backend", spegel=env.spegel_path,
                       runner=env.git_runner)
    if fel:
        raise RuntimeError(fel)
    skillnader = []
    with tarfile.open(tar_path) as arkivet:
        for medlem in arkivet.getmembers():
            if not medlem.isfile():
                continue
            lokal = env.agent_repo / medlem.name
            data = arkivet.extractfile(medlem).read()
            if not lokal.is_file() or lokal.read_bytes() != data:
                skillnader.append(medlem.name)
    tar_path.unlink(missing_ok=True)
    return skillnader


def _bygg(env: Miljo, commit: str, katalog: Path) -> Path:
    bygg = katalog / "bygg"
    if bygg.exists():
        shutil.rmtree(bygg)
    tar_path = katalog / "frontend.tar"
    fel = spegel.arkiv(commit, tar_path, "frontend", spegel=env.spegel_path,
                       runner=env.git_runner)
    if fel:
        raise RuntimeError(fel)
    _packa_upp(tar_path, bygg)
    tar_path.unlink(missing_ok=True)
    frontend = bygg / "frontend"
    moduler = env.agent_repo / "frontend" / "node_modules"
    if not moduler.is_dir():
        raise RuntimeError(f"node_modules saknas: {moduler}")
    (frontend / "node_modules").symlink_to(moduler)
    argv = [SANDBOX, "-D", f"HOME={HOME}", "-D", f"BYGG={bygg}", "-f", str(BYGG_PROFIL),
            str(NODE), "node_modules/vite/bin/vite.js", "build"]
    env_vars = {"PATH": f"{NODE.parent}:/usr/bin:/bin", "HOME": str(HOME),
                "LANG": "en_US.UTF-8"}
    rc, out, err = env.runner(argv, env_vars, BYGG_TIMEOUT_S, frontend)
    (katalog / "bygg.log").write_text(f"{out}\n{err}", encoding="utf-8")
    dist = frontend / "dist"
    if rc != 0 or not (dist / "index.html").is_file():
        raise RuntimeError(f"bygget misslyckades (exit {rc}): "
                           f"{' '.join(str(err or out).split())[-300:]}")
    return dist


def _installera(env: Miljo, ny: Path, katalog: Path) -> bool:
    """Byt agentens dist. Sparar förra bygget; True om ett förra bygge fanns."""
    live = env.agent_repo / "frontend" / "dist"
    forra = katalog / "dist-forra"
    if forra.exists():
        shutil.rmtree(forra)
    hade = live.is_dir()
    if hade:
        shutil.copytree(live, forra, symlinks=False)
        shutil.rmtree(live)
    shutil.copytree(ny, live, symlinks=False)
    return hade


def _aterstall_dist(env: Miljo, katalog: Path) -> bool:
    live = env.agent_repo / "frontend" / "dist"
    forra = katalog / "dist-forra"
    if not forra.is_dir():
        return False
    if live.exists():
        shutil.rmtree(live)
    shutil.copytree(forra, live, symlinks=False)
    return True


def _halsa(env: Miljo) -> dict:
    """Vänta tills båda svarar 200 (högst halsa_vanta_s). {namn: status}."""
    deadline = time.monotonic() + env.halsa_vanta_s
    while True:
        svar = {namn: env.http_status(url) for namn, url in HALSA}
        if all(code == 200 for code in svar.values()) or time.monotonic() >= deadline:
            return svar
        env.sov(3)


def _gron(halsa: dict) -> bool:
    return all(code == 200 for code in halsa.values())


# ── körning ──────────────────────────────────────────────────────────────

def _godkanda(conn) -> list[dict]:
    from . import inkorg
    out = []
    for row in conn.execute(
            "SELECT id, external_id, alternativ_json FROM spelai_inbox "
            "WHERE typ='beslut' ORDER BY id").fetchall():
        payload = payload_for(json.loads(row[2]))
        if not payload:
            continue
        svar = inkorg._effektivt(conn, row[0])  # noqa: SLF001
        if not svar or svar["val"] != "0":
            continue
        if tillstand.har_handelse(conn, f"driftsattning_start:{row[0]}"):
            continue
        out.append({"inbox_id": row[0], "external_id": row[1], "svar": svar, **payload})
    return out


def kor(conn, *, now: Callable[[], dt.datetime], env: Optional[Miljo] = None) -> dict:
    """Kör den äldsta godkända driftsättningen som inte körts. Tomt = inget att göra."""
    env = env or Miljo()
    vantar = _godkanda(conn)
    if not vantar:
        return {}
    begaran = vantar[0]
    inbox_id, commit, steg = begaran["inbox_id"], begaran["commit"], begaran["steg"]
    if not tillstand.logga(conn, "driftsattning_start", str(inbox_id),
                           {"commit": commit, "steg": steg}, now=now(),
                           dedup_key=f"driftsattning_start:{inbox_id}"):
        return {}
    katalog = _katalog(begaran["external_id"], env.rot)
    katalog.mkdir(parents=True, exist_ok=True)
    resultat = {"id": begaran["external_id"], "inbox_id": inbox_id, "commit": commit,
                "steg": steg, "godkand": begaran["svar"]["tid"], "start": iso(now()),
                "logg": []}

    def logg(text: str) -> None:
        resultat["logg"].append(f"{iso(now())} {text}")

    try:
        resultat.update(_kor_steg(conn, env, begaran, katalog, logg, now))
    except Exception as exc:  # noqa: BLE001 — resultatet ska alltid skrivas
        resultat["status"] = resultat.get("status") or "avbruten"
        resultat["orsak"] = f"{type(exc).__name__}: {exc}"[:500]
        logg(f"avbruten: {resultat['orsak']}")
    resultat["slut"] = iso(now())
    (katalog / "resultat.json").write_text(
        json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")
    kort = {k: resultat.get(k) for k in ("status", "orsak", "halsa", "skarmbild", "push",
                                         "commit", "steg", "start", "slut")}
    kort["katalog"] = str(katalog)
    tillstand.logga(conn, "driftsattning_klar", str(inbox_id), kort, now=now(),
                    dedup_key=f"driftsattning_klar:{inbox_id}")
    return kort


def _kor_steg(conn, env: Miljo, begaran: dict, katalog: Path, logg, now) -> dict:
    commit, steg = begaran["commit"], begaran["steg"]
    main, fel = spegel.hamta_main(conn, now=now(), kalla=env.agent_repo,
                                  spegel=env.spegel_path, runner=env.git_runner)
    if fel or main != commit:
        orsak = fel or (f"agentens main är {main[:12]}, inte {commit[:12]}: "
                        "lägg en ny begäran med rätt commit")
        logg(f"commitkontroll: {orsak}")
        return {"status": "avbruten", "orsak": orsak}
    logg(f"commitkontroll: main = {commit[:12]}")
    if "omstart_api" in steg:
        skillnader = _jamfor_backend(env, commit, katalog)
        if skillnader:
            orsak = (f"arbetskopian skiljer sig från commiten i {len(skillnader)} fil(er) "
                     f"under backend/: {', '.join(skillnader[:5])}")
            logg(orsak)
            return {"status": "avbruten", "orsak": orsak}
        logg("backend/ i arbetskopian = commiten")
    hade_forra = False
    if "bygg_app" in steg:
        ny = _bygg(env, commit, katalog)
        logg("bygget klart i sandbox")
        hade_forra = _installera(env, ny, katalog)
        logg("dist installerad" + (" (förra bygget sparat)" if hade_forra else ""))
    for nyckel, tjanst in (("bygg_app", TJANST["app"]), ("omstart_api", TJANST["api"])):
        if nyckel in steg:
            ok, text = env.omstart(tjanst)
            logg(f"omstart {tjanst}: {text}")
            if not ok:
                raise RuntimeError(f"omstart {tjanst}: {text}")
    halsa = _halsa(env)
    logg(f"hälsa: {halsa}")
    ut = {"halsa": halsa}
    bild = katalog / "hem-390x844.png"
    ok, text = env.skarmbild(bild)
    ut["skarmbild"] = str(bild) if ok else None
    logg("skärmbild 390×844 tagen" if ok else f"skärmbild misslyckades: {text}")
    if not _gron(halsa):
        if "bygg_app" in steg and _aterstall_dist(env, katalog):
            logg("röd hälsa: förra bygget återställt")
        for nyckel, tjanst in (("bygg_app", TJANST["app"]), ("omstart_api", TJANST["api"])):
            if nyckel in steg:
                _ok, text = env.omstart(tjanst)
                logg(f"omstart {tjanst} efter återställning: {text}")
        efter = _halsa(env)
        logg(f"hälsa efter återställning: {efter}")
        ut["halsa_efter_aterstallning"] = efter
        ut["status"] = "aterstalld" if _gron(efter) else "rod"
        ut["orsak"] = ("hälsan var röd efter driftsättningen" +
                       ("" if _gron(efter) else "; röd även efter återställning "
                        "(API-koden återställs inte av facitsidan)"))
        ut["push"] = None
        return ut
    ut["status"] = "gron"
    if "push" in steg:
        spegla = env.spegla or spegel.spegla
        push = spegla(conn, now=now(), kalla=env.agent_repo, spegel=env.spegel_path,
                      runner=env.git_runner, intervall=dt.timedelta(0))
        ut["push"] = push.get("push") or ({"fel": push["fel"]} if push.get("fel")
                                          else {"redan_pushad": commit[:12]})
        logg(f"push: {ut['push']}")
        if push.get("fel"):
            ut["status"] = "gron_utan_push"
    return ut
