"""Vakten v1 — deterministisk driftvakt (`cli.py vakt`, launchd var 30:e min).

Bakgrund: Sofascore svarade 403 i varje källprov från 2026-09-25T10:43Z i sex
dygn utan att något syntes i appen, testsviten var röd ett dygn 2026-09-02
utan att någon såg det och en kupongkrasch låg kvar 24–27/9. Vakten läser de
artefakter som redan finns och skriver ETT läge som Idag visar. Larm visas i
UI:t, aldrig som ntfy/push (Samans beslut 2026-09-02).

Regler:
  * Ingen AI och inga anrop till datakällor. Allt är lokala filer,
    launchctl/ps/git och databasen öppnad SKRIVSKYDDAD (`mode=ro`).
  * Klockan, sökvägarna, kommandokörning och diskmätning injiceras (`Ctx`) så
    att varje kontroll kan testas utan launchctl, git eller ps på riktigt.
  * En kontroll som kraschar fäller aldrig de andra: den ger
    `vakt_check_failed` och dess senaste kända fynd och tillstånd bärs vidare.
  * `since` = när felet först sågs. Bärs mellan körningar på kind + key; en
    kontroll som vet starttiden ur sina data (källprovets första felkörning)
    anger den själv.
  * Tider jämförs som tider (`_at`), aldrig som strängar; `Z` = UTC.

Läget skrivs atomiskt till `<data>/vakt/vakt.json` och en rad per körning
läggs till i `<data>/vakt/vakt-logg.jsonl`. `pool_health._vakt_issues` läser
filen åt `/api/health`. Trösklar och läsanvisning: `docs/vakt.md`.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence
from zoneinfo import ZoneInfo

from .storage import DEFAULT_DB

VERSION = "vakt-v1"
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = DEFAULT_DB.parent
STATUS_DIR_ENV = "SPELKOMPISEN_VAKT_DIR"
STATUS_FILE = "vakt.json"
LOG_FILE = "vakt-logg.jsonl"
LOCAL_TZ = ZoneInfo("Europe/Stockholm")

# A. Källprovet (com.saman.spelkompisen.kalltest, var 6:e timme).
KALLTEST_LOG = "kalltest-macbook-192.168.50.100.jsonl"
KALLTEST_INTERVAL_H = 6
KALLTEST_STALE_H = 2 * KALLTEST_INTERVAL_H
KALLA_MIN_FAILED_RUNS = 2
DNS_MARKERS = ("temporary failure in name resolution", "could not resolve host",
               "name or service not known", "nodename nor servname provided",
               "network is unreachable")

# B. Jobben. (nyckel i tools/spelkompisen_tjanster.py, ska ha PID?)
JOBS: tuple[tuple[str, bool], ...] = (
    ("backend", True), ("frontend", True), ("snapshot", False), ("pool", False),
    ("backup", False), ("kalltest", False), ("vakt", False))
# Insamlingens liv bevisas BARA av append-only-tabeller (observationstids-
# regeln 1 och 7): `snapshots`/`sharp_snapshots` skrivs vid förändring och
# hade luckor på 150 resp. 187 min under normal drift 17/9–1/10, medan
# `pool_market_capture` (presence) och Pinnacles rader i
# `oddset_source_health_log` aldrig hade mer än 30 min. 90 min = tre missade
# basvarv. `oddset_health` larmar redan efter 45 min på meta-stämplarna; det
# här är vaktens oberoende bakstopp på själva artefakten.
INSAMLING_MAX_MIN = 90

# C. Backendloggarna (uvicorn under launchd, raderna saknar tidsstämpel).
BACKEND_OUT_LOG = "backend-server.out.log"
BACKEND_ERR_LOG = "backend-server.err.log"
FIRST_READ_MAX_BYTES = 5 * 1024 * 1024
BACKEND_5XX_TOTAL = 5
BACKEND_5XX_PER_ENDPOINT = 3
# Ett 5xx-skov syns annars bara i 30 min (till nästa körning). Fyndet ligger
# kvar ett dygn efter senaste observation, märkt `held`.
BACKEND_HOLD_H = 24
ACCESS_RE = re.compile(r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/[\d.]+" (?P<status>\d{3})')
EXCEPTION_RE = re.compile(r"^(?P<name>[A-Za-z_][\w.]*)(?::\s?(?P<msg>.*))?$")
CHAIN_MARKERS = ("The above exception was the direct cause",
                 "During handling of the above exception")

# D. Driftläge. En commit inom fem minuter efter omstarten räknas som körd
# (redigera → starta om → committa); `git log %ct` och ps har sekundupplösning.
CODE_GRACE_S = 300
FETCH_TIMEOUT_S = 30

# E. Tester en gång per lokalt dygn efter 03:00.
TEST_HOUR_LOCAL = 3
TEST_TIMEOUT_S = 15 * 60
TEST_FAIL_LINES = 12

# F. Disk.
DISK_WARN_GB = 10
DISK_ERROR_GB = 3

# G. Experiment (info). Info-fynd ligger kvar i sju dygn.
INFO_HOLD_H = 7 * 24

AREAS = ("jobb", "kallor", "backend", "drift", "tester", "server", "experiment")

Runner = Callable[..., tuple[int, str, str]]


# ── tider och småhjälp ────────────────────────────────────────────────────

def _at(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _minutes(delta: dt.timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _hours_text(delta: dt.timedelta) -> str:
    hours = delta.total_seconds() / 3600
    return f"{hours:.0f} h" if hours < 48 else f"{hours / 24:.1f} dygn".replace(".", ",")


def default_status_dir() -> Path:
    return Path(os.environ.get(STATUS_DIR_ENV) or DATA_DIR / "vakt")


def default_status_path() -> Path:
    return default_status_dir() / STATUS_FILE


def local_runner(args: Sequence[str], *, timeout: float = 30,
                 cwd: Optional[Path] = None, env: Optional[dict] = None
                 ) -> tuple[int, str, str]:
    """Kör ett kommando; vid timeout dödas hela processgruppen (kontroll.sh
    startar python/npm som barn — de får aldrig bli kvar)."""
    try:
        proc = subprocess.Popen([str(a) for a in args], cwd=cwd, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
    except OSError as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return 124, out or "", (err or "") + f"\ntimeout efter {int(timeout)} s"
    return proc.returncode, out or "", err or ""


def _tjanster():
    """tools/spelkompisen_tjanster.py — ENDA launchd-logiken (menyraden och
    tjanster.sh går genom samma modul). Ingen parallell implementation här."""
    tools = str(REPO_ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import spelkompisen_tjanster
    return spelkompisen_tjanster


@dataclass
class Ctx:
    now: dt.datetime
    data_dir: Path
    db_path: Path
    repo: Path
    status_dir: Path
    prev: dict
    run: Runner = local_runner
    fetch: bool = True
    tests: Optional[bool] = None          # None = schema, True = nu, False = aldrig
    disk_usage: Callable = shutil.disk_usage
    state: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    _launchd: Optional[dict] = None

    def launchd_states(self) -> dict:
        if self._launchd is None:
            tj = _tjanster()
            launchd = tj.Launchd(lambda args: self.run([tj.LAUNCHCTL, *args], timeout=25))
            states, error = launchd.state()
            if error:
                raise RuntimeError(f"launchctl: {error}")
            self._launchd = states
        return self._launchd

    def git(self, *args: str, timeout: float = 30) -> tuple[int, str, str]:
        # --no-optional-locks: vakten får inte skriva index/lås i driftkopian.
        return self.run(["git", "--no-optional-locks", "-C", str(self.repo), *args],
                        timeout=timeout)


def _finding(level: str, area: str, kind: str, key: str, message: str,
             **details) -> dict:
    assert level in ("error", "warning", "info") and area in AREAS
    return {"level": level, "area": area, "kind": kind, "key": str(key),
            "message": message, **details}


def _fid(finding: dict) -> str:
    return f"{finding.get('kind')}:{finding.get('key', '')}"


# ── A. källor ur källprovet ───────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue  # en avbruten skrivning får inte fälla kontrollen
            if isinstance(row, dict) and _at(row.get("at")):
                rows.append(row)
    return rows


def _infrastructure(row: dict) -> Optional[str]:
    """Samma klassning som kalltest_ip.py: eget nät/DNS nere säger inget om källan."""
    if row.get("infrastructure_error"):
        return str(row["infrastructure_error"])
    if row.get("outcome") == "infrastructure_error":
        return "infrastruktur"
    note = str(row.get("note", "")).lower()
    return "dns" if any(marker in note for marker in DNS_MARKERS) else None


def _outcome(row: dict) -> str:
    if _infrastructure(row):
        return "infrastructure_error"
    if row.get("outcome") in ("ok", "source_error"):
        return row["outcome"]
    return "ok" if row.get("ok") else "source_error"


def check_kallor(ctx: Ctx) -> list[dict]:
    path = ctx.data_dir / KALLTEST_LOG
    if not path.exists():
        return [_finding("warning", "kallor", "kalltest_stale", "saknas",
                         f"källprovets logg saknas ({path.name}) — ingen vet om "
                         "datakällorna svarar")]
    runs: dict[str, dict] = {}
    for row in _read_jsonl(path):
        run_id = str(row.get("run_id") or str(row["at"])[:16])
        run = runs.setdefault(run_id, {"at": _at(row["at"]), "rows": {}})
        run["at"] = min(run["at"], _at(row["at"]))
        run["rows"][str(row.get("source"))] = row
    ordered = sorted(runs.values(), key=lambda run: run["at"])
    findings: list[dict] = []
    ctx.summary["kallor"] = {"runs": len(ordered),
                             "latest_run": _iso(ordered[-1]["at"]) if ordered else None}
    if not ordered:
        return [_finding("warning", "kallor", "kalltest_stale", "tom",
                         "källprovets logg har inga läsbara körningar")]
    latest = ordered[-1]["at"]
    if ctx.now - latest > dt.timedelta(hours=KALLTEST_STALE_H):
        findings.append(_finding(
            "warning", "kallor", "kalltest_stale", "gammal",
            f"senaste källprov {_iso(latest)} ({_hours_text(ctx.now - latest)} sedan, "
            f"gräns {KALLTEST_STALE_H} h) — kontrollera jobbet kalltest",
            latest_run=_iso(latest)))

    # Eget nät nere: körningar där någon rad är ett infrastrukturfel.
    infra_series = []
    for run in reversed(ordered):
        if not any(_infrastructure(row) for row in run["rows"].values()):
            break
        infra_series.append(run)
    if infra_series:
        first = infra_series[-1]
        reason = next(_infrastructure(r) for r in infra_series[0]["rows"].values()
                      if _infrastructure(r))
        findings.append(_finding(
            "error" if len(infra_series) >= KALLA_MIN_FAILED_RUNS else "warning",
            "server", "natverk_nere", "kalltest",
            f"serverns eget nät/DNS fallerade i {len(infra_series)} källprov i rad "
            f"({reason}) — källorna kan inte bedömas förrän nätet är tillbaka",
            since=_iso(first["at"]), runs=len(infra_series)))

    sources = sorted({source for run in ordered for source in run["rows"]})
    failing = []
    for source in sources:
        series = []
        for run in reversed(ordered):
            row = run["rows"].get(source)
            if row is None:
                continue
            outcome = _outcome(row)
            if outcome == "infrastructure_error":
                continue  # ingen observation av källan — varken brott eller fel
            if outcome != "source_error":
                break
            series.append(row)
        if len(series) < KALLA_MIN_FAILED_RUNS:
            continue
        failing.append(source)
        since = _at(series[-1]["at"])
        note = str(series[0].get("note") or "inget felmeddelande")
        findings.append(_finding(
            "error", "kallor", "kalla_nere", source,
            f"{source} har fallerat i {len(series)} källprov i rad: {note[:240]}",
            since=_iso(since), runs=len(series), note=note[:500],
            last_run=series[0]["at"]))
    ctx.summary["kallor"]["failing"] = failing
    return findings


# ── B. jobb och insamlingens artefakter ──────────────────────────────────

def check_jobb(ctx: Ctx) -> list[dict]:
    tj = _tjanster()
    states = ctx.launchd_states()
    findings, seen = [], {}
    for key, keep_alive in JOBS:
        service = tj.BY_KEY.get(key)
        if service is None:
            findings.append(_finding("warning", "jobb", "jobb_okant", key,
                                     f"tjänsten {key} saknas i spelkompisen_tjanster.py"))
            continue
        state = states.get(service.label) or {}
        seen[key] = tj.state_text(state, service.scheduled)
        name = f"{service.name} ({service.label})"
        if not state.get("loaded"):
            disabled = bool(state.get("disabled"))
            findings.append(_finding(
                "warning" if disabled else "error", "jobb", "jobb_ej_laddat", key,
                f"{name} är inte laddad i launchd"
                + (" — avstängd med `stopp --permanent`" if disabled else
                   " — starta med tools/tjanster.sh start " + key),
                label=service.label, disabled=disabled))
        elif keep_alive and not state.get("running"):
            findings.append(_finding(
                "error", "jobb", "jobb_nere", key,
                f"{name} ska alltid köra men har ingen process "
                f"(senaste exit {state.get('last_exit')})",
                label=service.label, last_exit=state.get("last_exit")))
        elif (not keep_alive and not state.get("running")
              and state.get("last_exit") not in (None, 0)):
            code = state.get("last_exit")
            extra = (" — källprovet avslutar med 1 när en kritisk källa fallerar; "
                     "orsaken står under 'källa nere'" if key == "kalltest" and code == 1
                     else "")
            findings.append(_finding(
                "warning", "jobb", "jobb_exit", key,
                f"{name} avslutades senast med kod {code}{extra}",
                label=service.label, last_exit=code))
    ctx.summary["jobb"] = seen
    return findings


def _latest_time(conn, sql: str, params: tuple = ()) -> Optional[dt.datetime]:
    """Senaste tid bland de sist INSKRIVNA raderna, jämförd som tid. Databasen
    blandar `Z`, `+00:00` och mikrosekunder, så SQL:s MAX över text räcker inte."""
    try:
        rows = conn.execute(sql + " ORDER BY rowid DESC LIMIT 200", params).fetchall()
    except Exception:  # noqa: BLE001 — tabell utan rowid
        rows = conn.execute(sql + " ORDER BY 1 DESC LIMIT 200", params).fetchall()
    times = [t for t in (_at(row[0]) for row in rows) if t]
    return max(times) if times else None


def _ro_connect(path: Path):
    import sqlite3
    if not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def check_insamling(ctx: Ctx) -> list[dict]:
    conn = _ro_connect(ctx.db_path)
    try:
        open_draws = [t for t in (_at(row[0]) for row in conn.execute(
            "SELECT reg_close_time FROM draws WHERE state='Open'")) if t and t > ctx.now]
        pool = _latest_time(conn, "SELECT fetched_at FROM pool_market_capture")
        oddset = _latest_time(conn, "SELECT checked_at FROM oddset_source_health_log "
                                    "WHERE source='pinnacle' AND scope != 'live'")
    finally:
        conn.close()
    limit = dt.timedelta(minutes=INSAMLING_MAX_MIN)
    findings = []
    for key, latest, active, what in (
            ("pool", pool, bool(open_draws),
             "poolinsamlingen har inte skrivit någon presence-rad (pool_market_capture)"),
            ("oddset", oddset, True,
             "Oddset-varvet har inte kontrollerat Pinnacle (oddset_source_health_log)")):
        if not active:
            continue  # ingen öppen omgång = inget att samla, inget larm
        if latest is None or ctx.now - latest > limit:
            age = f"på {_minutes(ctx.now - latest)} min" if latest else "någonsin"
            findings.append(_finding(
                "error", "jobb", "insamling_star_still", key,
                f"{what} {age} (gräns {INSAMLING_MAX_MIN} min)",
                latest=latest and _iso(latest)))
    ctx.summary["insamling"] = {"pool_latest": pool and _iso(pool),
                                "oddset_latest": oddset and _iso(oddset),
                                "open_draws": len(open_draws)}
    return findings


# ── C. backendloggarna ────────────────────────────────────────────────────

def _read_new(path: Path, prev: Optional[dict]) -> tuple[str, dict, str]:
    """Bara det som tillkommit sedan förra körningen. Offset sparas i vakt.json;
    krympt/roterad fil (ny inode eller mindre än offset) läses om från 0."""
    stat = path.stat()
    size, inode = stat.st_size, stat.st_ino
    mode = "ny"
    if not prev:
        start, mode = max(0, size - FIRST_READ_MAX_BYTES), "första"
    elif prev.get("inode") != inode or size < int(prev.get("offset") or 0):
        start, mode = 0, "roterad"
    else:
        start = int(prev.get("offset") or 0)
    # Första läsningen mitt i filen: läs från byten FÖRE start och kapa allt
    # till och med första radslutet — då överlever en hel rad som börjar
    # exakt vid start, och en halv rad räknas aldrig.
    skip_partial = mode == "första" and start > 0
    base = start - 1 if skip_partial else start
    with path.open("rb") as handle:
        handle.seek(base)
        data = handle.read()
    if skip_partial:
        cut = data.find(b"\n")
        base, data = (base + cut + 1, data[cut + 1:]) if cut >= 0 else (base, b"")
    end = data.rfind(b"\n")
    if end < 0:  # ingen hel rad ännu — läs om nästa gång
        return "", {"offset": base, "inode": inode, "size": size}, mode
    chunk = data[:end + 1]
    return (chunk.decode("utf-8", errors="replace"),
            {"offset": base + len(chunk), "inode": inode, "size": size}, mode)


def _exceptions(text: str) -> list[str]:
    """Slutliga undantagsrader: en kedja (`The above exception…`) räknas en gång."""
    events: list[str] = []
    in_traceback = False
    for line in text.splitlines():
        if line.startswith("Traceback (most recent call last):"):
            in_traceback = True
            continue
        if line.startswith(CHAIN_MARKERS):
            if events:
                events.pop()  # orsaken; det slutliga undantaget kommer efter
            continue
        if not in_traceback:
            continue
        if not line.strip() or line[0] in " \t^~":
            continue
        in_traceback = False
        events.append(line.strip())
    return events


def _exception_kind(line: str) -> str:
    match = EXCEPTION_RE.match(line)
    name = (match.group("name") if match else line).lower()
    lowered = line.lower()
    if "timeout" in name:
        return "timeout"
    if (any(marker in lowered for marker in DNS_MARKERS) or name.endswith("connecterror")
            or name in ("connectionerror", "connectionrefusederror", "socket.gaierror")):
        return "network"
    return "bug"


def _window_text(mode: str) -> str:
    return {"första": "i loggens senaste del (vaktens första läsning)",
            "roterad": "sedan loggen roterades"}.get(mode, "sedan förra kontrollen")


def _hold(mode: str) -> dict:
    # Baslinjeläsningen (upp till 5 MB historik) hålls inte kvar ett dygn —
    # den beskriver gamla skov, inte vad som hänt sedan vakten började.
    return {} if mode == "första" else {"hold_h": BACKEND_HOLD_H}


def check_backend(ctx: Ctx) -> list[dict]:
    prev = (ctx.state.get("backend_log") or {})
    new_state = dict(prev)
    findings: list[dict] = []
    summary: dict = {}

    out_path = ctx.data_dir / BACKEND_OUT_LOG
    if out_path.exists():
        text, new_state["out"], mode = _read_new(out_path, prev.get("out"))
        by_endpoint: Counter = Counter()
        for match in ACCESS_RE.finditer(text):
            if 500 <= int(match.group("status")) <= 599:
                endpoint = f"{match.group('method')} {match.group('path').split('?', 1)[0]}"
                by_endpoint[endpoint] += 1
        total = sum(by_endpoint.values())
        summary.update({"out_mode": mode, "n_5xx": total,
                        "bytes_read_out": len(text.encode("utf-8"))})
        worst = by_endpoint.most_common(3)
        if total >= BACKEND_5XX_TOTAL or (worst and worst[0][1] >= BACKEND_5XX_PER_ENDPOINT):
            top = " · ".join(f"{endpoint} {n}" for endpoint, n in worst)
            findings.append(_finding(
                "warning", "backend", "backend_5xx", "access",
                f"{total} serverfel (5xx) i API:t {_window_text(mode)}: {top}",
                n=total, endpoints=dict(by_endpoint.most_common(10)),
                **_hold(mode)))
    else:
        summary["out_mode"] = "saknas"

    err_path = ctx.data_dir / BACKEND_ERR_LOG
    if err_path.exists():
        text, new_state["err"], mode = _read_new(err_path, prev.get("err"))
        events = _exceptions(text)
        kinds = Counter(_exception_kind(line) for line in events)
        summary.update({"err_mode": mode, "exceptions": dict(kinds)})
        bugs = [line for line in events if _exception_kind(line) == "bug"]
        network = [line for line in events if _exception_kind(line) == "network"]
        if bugs:
            findings.append(_finding(
                "warning", "backend", "backend_traceback", "err",
                f"{len(bugs)} undantag i backendloggen {_window_text(mode)}; "
                f"senast: {bugs[-1][:200]}",
                n=len(bugs), last=bugs[-1][:500], **_hold(mode)))
        if network:
            findings.append(_finding(
                "warning", "server", "natverk_nere", "backend",
                f"backend fick {len(network)} nät-/DNS-fel mot externa källor "
                f"{_window_text(mode)} (senast: {network[-1][:160]}) — servern har "
                "troligen tappat nätet", n=len(network), last=network[-1][:500],
                **_hold(mode)))
    else:
        summary["err_mode"] = "saknas"
    ctx.state["backend_log"] = new_state
    ctx.summary["backend"] = summary
    return findings


# ── D. driftläge ──────────────────────────────────────────────────────────

def _etime_seconds(text: str) -> int:
    """`ps -o etime=`: [[dd-]hh:]mm:ss. Förfluten tid i stället för lstart ger
    starttiden utan lokal tidszon/locale att tolka."""
    text = text.strip()
    days = 0
    if "-" in text:
        day_text, text = text.split("-", 1)
        days = int(day_text)
    parts = [int(part) for part in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    hours, minutes, seconds = parts[-3:]
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _last_commit(ctx: Ctx, *paths: str) -> Optional[tuple[dt.datetime, str]]:
    code, out, _ = ctx.git("log", "-1", "--format=%ct %h %s", "--", *paths)
    if code != 0 or not out.strip():
        return None
    stamp, _, rest = out.strip().partition(" ")
    return dt.datetime.fromtimestamp(int(stamp), dt.timezone.utc), rest


def check_drift(ctx: Ctx) -> list[dict]:
    findings: list[dict] = []
    summary: dict = {"repo": str(ctx.repo)}
    grace = dt.timedelta(seconds=CODE_GRACE_S)

    # (1) Backendprocessen mot senaste commit i backend/app. cli.py läses inte
    # av uvicorn (launchd-jobben startar den på nytt varje varv) och ingår inte.
    tj = _tjanster()
    backend = ctx.launchd_states().get(tj.BY_KEY["backend"].label) or {}
    commit = _last_commit(ctx, "backend/app")
    if backend.get("pid") and commit:
        code, out, _ = ctx.run(["ps", "-o", "etime=", "-p", str(backend["pid"])], timeout=10)
        if code == 0 and out.strip():
            started = ctx.now - dt.timedelta(seconds=_etime_seconds(out))
            summary["backend_started"] = _iso(started)
            if commit[0] > started + grace:
                findings.append(_finding(
                    "warning", "drift", "backend_kor_gammal_kod", "backend",
                    f"backend startades {_iso(started)} men backend/app ändrades "
                    f"{_iso(commit[0])} ({commit[1][:80]}) — starta om: "
                    "tools/tjanster.sh omstart backend",
                    started=_iso(started), commit_at=_iso(commit[0])))

    # (2) Byggd frontend mot senaste commit i frontend/src.
    index = ctx.repo / "frontend" / "dist" / "index.html"
    commit = _last_commit(ctx, "frontend/src")
    if commit:
        if not index.exists():
            findings.append(_finding("warning", "drift", "appen_ej_byggd", "frontend",
                                     "frontend/dist saknas — bygg med `cd frontend && npm run build`"))
        else:
            built = dt.datetime.fromtimestamp(index.stat().st_mtime, dt.timezone.utc)
            summary["frontend_built"] = _iso(built)
            if commit[0] > built + grace:
                findings.append(_finding(
                    "warning", "drift", "appen_ej_byggd", "frontend",
                    f"appen byggdes {_iso(built)} men frontend/src ändrades "
                    f"{_iso(commit[0])} ({commit[1][:80]}) — kör `cd frontend && npm run build`",
                    built=_iso(built), commit_at=_iso(commit[0])))

    # (3) origin/main mot driftkopians HEAD. Hämtfel larmar inte (nätet syns i A/C).
    if ctx.fetch:
        code, _, err = ctx.git("fetch", "--quiet", "origin", timeout=FETCH_TIMEOUT_S)
        summary["fetch"] = "ok" if code == 0 else f"misslyckades: {err.strip()[:160]}"
    else:
        summary["fetch"] = "avstängd"
    code, out, _ = ctx.git("rev-list", "--left-right", "--count", "HEAD...origin/main")
    if code == 0 and out.split():
        ahead, behind = (int(part) for part in out.split()[:2])
        summary.update({"ahead": ahead, "behind": behind})
        code, branch, _ = ctx.git("rev-parse", "--abbrev-ref", "HEAD")
        summary["branch"] = branch.strip() if code == 0 else None
        if behind:
            findings.append(_finding(
                "warning", "drift", "main_ej_utcheckad", "origin",
                f"origin/main har {behind} commit(s) som driftkopian inte har — "
                "dra ned och driftsätt (merge, bygg, omstart)", behind=behind))
        if ahead:
            findings.append(_finding(
                "warning", "drift", "opushade_commits", "origin",
                f"driftkopian har {ahead} commit(s) som inte finns på origin/main — "
                "pusha (backupen av koden är GitHub)", ahead=ahead))

    # (4) Ändrade SPÅRADE filer i driftkopian (nya, ospårade filer ignoreras).
    code, out, _ = ctx.git("status", "--porcelain", "--untracked-files=no")
    if code == 0:
        changed = [line[3:] for line in out.splitlines() if line.strip()]
        summary["changed_tracked"] = len(changed)
        if changed:
            shown = ", ".join(changed[:5]) + (f" +{len(changed) - 5}" if len(changed) > 5 else "")
            findings.append(_finding(
                "warning", "drift", "ocommittat_i_driftkopian", "status",
                f"{len(changed)} spårad(e) fil(er) ändrade men inte committade i "
                f"driftkopian: {shown}", files=changed[:20]))
    ctx.summary["drift"] = summary
    return findings


# ── E. testsviten nattligen ──────────────────────────────────────────────

def test_day_start(now: dt.datetime) -> dt.datetime:
    """Senaste 03:00 svensk tid ≤ now, som UTC."""
    local = now.astimezone(LOCAL_TZ)
    start = local.replace(hour=TEST_HOUR_LOCAL, minute=0, second=0, microsecond=0)
    if local < start:
        start = (local - dt.timedelta(days=1)).replace(
            hour=TEST_HOUR_LOCAL, minute=0, second=0, microsecond=0)
    return start.astimezone(dt.timezone.utc)


def _tests_due(ctx: Ctx) -> bool:
    if ctx.tests is not None:
        return ctx.tests
    last = _at((ctx.state.get("tests") or {}).get("started_at"))
    return last is None or last < test_day_start(ctx.now)


def run_test_suite(ctx: Ctx) -> dict:
    """tools/kontroll.sh i en temporär worktree av driftkopians HEAD — aldrig i
    driftkopian och aldrig mot produktionsdatabasen (kontroll.sh sätter
    SPELKOMPISEN_DB till en temporär fil). Worktreen tas alltid bort."""
    started = ctx.now
    t0 = time.monotonic()
    parent = Path(tempfile.mkdtemp(prefix="spk-vakt-test-"))
    worktree = parent / "wt"
    result: dict = {"started_at": _iso(started)}
    try:
        code, head, _ = ctx.git("rev-parse", "--short", "HEAD")
        result["head"] = head.strip() if code == 0 else None
        code, _, err = ctx.git("worktree", "add", "--detach", str(worktree), "HEAD",
                               timeout=120)
        if code != 0:
            raise RuntimeError(f"git worktree add: {err.strip()[:200]}")
        for link, target in (("backend/.venv", ctx.repo / "backend" / ".venv"),
                             ("frontend/node_modules", ctx.repo / "frontend" / "node_modules")):
            if target.exists():
                (worktree / link).symlink_to(target)
        env = {key: value for key, value in os.environ.items()
               if key not in ("SPELKOMPISEN_DB", STATUS_DIR_ENV)}
        runtime = Path.home() / ".local" / "spelkompisen-runtime" / "bin"
        env["PATH"] = f"{runtime}:{env.get('PATH', '/usr/bin:/bin')}"
        code, out, err = ctx.run(["/bin/bash", str(worktree / "tools" / "kontroll.sh")],
                                 timeout=TEST_TIMEOUT_S, cwd=worktree, env=env)
        lines = (out + "\n" + err).splitlines()
        marker = next((i for i, line in enumerate(lines) if line.strip() == "== kontroll =="),
                      None)
        summary = ([line for line in lines[marker + 1:] if line.strip()]
                   if marker is not None else [])
        fail_lines = [line for line in lines
                      if re.match(r"^(FAIL|ERROR):|^not ok|^✗|.*timeout efter", line.strip())]
        result.update({
            "ok": code == 0, "exit_code": code,
            "summary": summary[:10],
            "fail_lines": fail_lines[:TEST_FAIL_LINES],
            "timeout": code == 124,
        })
    except Exception as exc:  # noqa: BLE001 — ett trasigt testbygge är också rött
        result.update({"ok": False, "exit_code": None, "summary": [],
                       "fail_lines": [f"{type(exc).__name__}: {exc}"[:300]],
                       "timeout": False})
    finally:
        ctx.git("worktree", "remove", "--force", str(worktree), timeout=120)
        ctx.git("worktree", "prune", timeout=60)
        shutil.rmtree(parent, ignore_errors=True)
    result["duration_s"] = round(time.monotonic() - t0, 1)
    return result


def check_tester(ctx: Ctx) -> list[dict]:
    previous = ctx.state.get("tests") or {}
    if _tests_due(ctx):
        result = run_test_suite(ctx)
        # Röd serie: första röda körningen är `since` så länge sviten är röd.
        if not result.get("ok"):
            result["red_since"] = (previous.get("red_since") if previous.get("ok") is False
                                   else None) or result["started_at"]
        ctx.state["tests"] = result
        ran = True
    else:
        result, ran = previous, False
    ctx.summary["tester"] = {"ran_now": ran, "started_at": result.get("started_at"),
                             "green": result.get("ok"), "head": result.get("head"),
                             "duration_s": result.get("duration_s")}
    if result and result.get("ok") is False:
        first = "; ".join(result.get("fail_lines", [])[:3]) or "se vakt.json"
        verdict = "timeout efter 15 min" if result.get("timeout") else "röd"
        return [_finding(
            "error", "tester", "tester_roda", "kontroll",
            f"nattliga testkörningen ({result.get('head') or 'HEAD'}, "
            f"{result.get('started_at')}) var {verdict}: {first[:300]}",
            since=result.get("red_since") or result.get("started_at"),
            summary=result.get("summary", []), fail_lines=result.get("fail_lines", []))]
    return []


# ── F. server ────────────────────────────────────────────────────────────

def check_server(ctx: Ctx) -> list[dict]:
    usage = ctx.disk_usage(ctx.data_dir)
    free_gb = usage.free / 1024 ** 3
    db_size = ctx.db_path.stat().st_size if ctx.db_path.exists() else None
    ctx.summary["server"] = {"free_gb": round(free_gb, 1),
                             "total_gb": round(usage.total / 1024 ** 3, 1),
                             "db_bytes": db_size, "db_path": str(ctx.db_path)}
    if free_gb < DISK_WARN_GB:
        level = "error" if free_gb < DISK_ERROR_GB else "warning"
        return [_finding(level, "server", "disk_lag", "data",
                         f"{free_gb:.1f} GB ledigt på volymen med backend/data "
                         f"(varning under {DISK_WARN_GB} GB, fel under {DISK_ERROR_GB} GB)",
                         free_gb=round(free_gb, 2))]
    return []


# ── G. experiment (info, inga larm) ──────────────────────────────────────

@contextlib.contextmanager
def _main_storage_read_only(db_path: Path):
    """`gater._ph4_oot` → `main.turnover_prognos()` öppnar en EGEN Storage().
    Under katalogläsningen byts den mot en skrivskyddad anslutning till samma
    databas, så vakten aldrig öppnar produktionsdatabasen skrivbar."""
    from . import main as main_mod
    from .storage import Storage
    original = main_mod.Storage
    main_mod.Storage = lambda *args, **kwargs: Storage(db_path, read_only=True)
    try:
        yield
    finally:
        main_mod.Storage = original


def _catalog(ctx: Ctx) -> dict:
    from . import pool_tests
    from .storage import Storage
    store = Storage(ctx.db_path, read_only=True)
    try:
        with _main_storage_read_only(ctx.db_path):
            return pool_tests.catalog(store, now=ctx.now)
    finally:
        store.close()


def check_experiment(ctx: Ctx, catalog: Optional[Callable[[Ctx], dict]] = None) -> list[dict]:
    payload = (catalog or _catalog)(ctx)
    current = {}
    for test in payload.get("tests") or []:
        progress = test.get("progress") or None
        current[test["id"]] = {
            "title": test.get("title"), "status": test.get("status"),
            "n": progress and progress.get("n"), "krav": progress and progress.get("krav"),
            "cell": progress and progress.get("namn")}
    previous = ((ctx.state.get("experiments") or {}).get("tests") or {})
    findings = []
    for test_id, cur in current.items():
        old = previous.get(test_id)
        if old and old.get("status") != cur["status"]:
            findings.append(_finding(
                "info", "experiment", "test_status_andrad",
                f"{test_id}:{old.get('status')}->{cur['status']}",
                f"{cur['title']}: {old.get('status')} → {cur['status']}",
                hold_h=INFO_HOLD_H, test=test_id))
        # Bara ÖVERGÅNGEN räknas (förra körningen under kravet, nu på eller
        # över): poolopt står t.ex. på 62/40 efter sin avläsning vid 40 och ska
        # inte läsas av igen förrän vid 120 (Samans beslut 5aA). Första
        # körningen är baslinje och noterar inget.
        old_n = old and old.get("n")
        if (old and cur["status"] == "samlar" and cur["n"] is not None and cur["krav"]
                and old_n is not None and old_n < cur["krav"] <= cur["n"]):
            findings.append(_finding(
                "info", "experiment", "avlasningspunkt_nadd", test_id,
                f"{cur['title']}: underlaget {cur['n']}/{cur['krav']} når kravet "
                f"({cur['cell']}) medan testet fortfarande samlar — avläsning enligt "
                "testets dokument",
                hold_h=INFO_HOLD_H, test=test_id, n=cur["n"], krav=cur["krav"]))
    ctx.state["experiments"] = {"tests": current, "at": _iso(ctx.now)}
    ctx.summary["experiment"] = {test_id: f"{cur['status']}"
                                 + (f" {cur['n']}/{cur['krav']}" if cur["krav"] else "")
                                 for test_id, cur in current.items()}
    return findings


# ── körning ──────────────────────────────────────────────────────────────

CHECKS: tuple[tuple[str, str, Callable[[Ctx], list[dict]]], ...] = (
    ("kallor", "kallor", check_kallor),
    ("jobb", "jobb", check_jobb),
    ("insamling", "jobb", check_insamling),
    ("backend", "backend", check_backend),
    ("drift", "drift", check_drift),
    ("tester", "tester", check_tester),
    ("server", "server", check_server),
    ("experiment", "experiment", check_experiment),
)


def load_status(status_dir: Path) -> dict:
    try:
        payload = json.loads((status_dir / STATUS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def merge_findings(new: list[dict], previous: list[dict], now: dt.datetime,
                   failed_checks: set[str]) -> list[dict]:
    """Bär `since` på kind + key. Fynd från en kraschad kontroll och fynd med
    `hold_h` (info 7 dygn, backendskov 24 h) ligger kvar märkta."""
    prev_by_id = {_fid(f): f for f in previous if isinstance(f, dict)}
    out, seen = [], set()
    for finding in new:
        fid = _fid(finding)
        old = prev_by_id.get(fid) or {}
        finding["since"] = finding.get("since") or old.get("since") or _iso(now)
        finding["last_seen"] = _iso(now)
        out.append(finding)
        seen.add(fid)
    for fid, old in prev_by_id.items():
        if fid in seen:
            continue
        if old.get("check") in failed_checks:
            out.append({**old, "carried": True})
            continue
        last = _at(old.get("last_seen") or old.get("since"))
        hold = old.get("hold_h")
        if hold and last and now - last < dt.timedelta(hours=float(hold)):
            out.append({**old, "held": True})
    order = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda f: (order.get(f.get("level"), 3), f.get("area", ""),
                            f.get("kind", ""), f.get("key", "")))
    return out


def run(*, now: Optional[dt.datetime] = None, data_dir: Optional[Path] = None,
        db_path: Optional[Path] = None, repo: Optional[Path] = None,
        status_dir: Optional[Path] = None, runner: Runner = local_runner,
        fetch: bool = True, tests: Optional[bool] = None,
        disk_usage: Callable = shutil.disk_usage,
        checks=CHECKS) -> dict:
    """Kör alla kontroller och returnera nya läget (skriver inget — se write_status)."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    db_path = Path(db_path or (data_dir and Path(data_dir) / "stryktips.db") or DEFAULT_DB)
    data_dir = Path(data_dir or DATA_DIR)
    status_dir = Path(status_dir or default_status_dir())
    previous = load_status(status_dir)
    ctx = Ctx(now=now, data_dir=data_dir, db_path=db_path,
              repo=Path(repo or REPO_ROOT), status_dir=status_dir, prev=previous,
              run=runner, fetch=fetch, tests=tests, disk_usage=disk_usage,
              state=copy.deepcopy(previous.get("state") or {}))
    t_all = time.monotonic()
    findings: list[dict] = []
    failed: set[str] = set()
    check_summary: dict = {}
    for name, area, check in checks:
        t0 = time.monotonic()
        try:
            got = check(ctx) or []
            for finding in got:
                finding["check"] = name
            findings.extend(got)
            check_summary[name] = {**ctx.summary.get(name, {}), "ok": True}
        except Exception as exc:  # noqa: BLE001 — en trasig kontroll får inte fälla de andra
            failed.add(name)
            error = f"{type(exc).__name__}: {exc}"[:300]
            check_summary[name] = {"ok": False, "error": error}
            findings.append({**_finding(
                "warning", area, "vakt_check_failed", name,
                f"vaktens kontroll '{name}' kraschade ({type(exc).__name__}) — "
                "dess senaste kända fynd visas oförändrade", error=error),
                "check": "vakt"})
        check_summary[name]["ms"] = int((time.monotonic() - t0) * 1000)
    merged = merge_findings(findings, previous.get("findings") or [], now, failed)
    return {
        "version": VERSION,
        "checked_at": _iso(now),
        "duration_s": round(time.monotonic() - t_all, 2),
        "counts": dict(Counter(f["level"] for f in merged)),
        "findings": merged,
        "checks": check_summary,
        "paths": {"data_dir": str(data_dir), "db": str(ctx.db_path), "repo": str(ctx.repo)},
        "state": ctx.state,
    }


def write_status(status: dict, status_dir: Optional[Path] = None) -> Path:
    """vakt.json atomiskt (tmp + os.replace) och EN loggrad per körning."""
    status_dir = Path(status_dir or default_status_dir())
    status_dir.mkdir(parents=True, exist_ok=True)
    target = status_dir / STATUS_FILE
    tmp = status_dir / f".{STATUS_FILE}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)
    line = {"checked_at": status["checked_at"], "version": status["version"],
            "duration_s": status.get("duration_s"), "counts": status.get("counts", {}),
            "findings": [f"{f['level']}:{f['kind']}:{f.get('key', '')}"
                         for f in status.get("findings", [])],
            "failed_checks": sorted(name for name, c in status.get("checks", {}).items()
                                    if not c.get("ok"))}
    with (status_dir / LOG_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    return target


def format_status(status: dict, verbose: bool = True) -> str:
    counts = status.get("counts") or {}
    out = [f"VAKTEN {status.get('version')} · {status.get('checked_at')} · "
           f"{counts.get('error', 0)} fel · {counts.get('warning', 0)} varningar · "
           f"{counts.get('info', 0)} noteringar · {status.get('duration_s')} s"]
    mark = {"error": "✗", "warning": "!", "info": "·"}
    for finding in status.get("findings") or []:
        flag = " (kvar)" if finding.get("held") or finding.get("carried") else ""
        out.append(f"  {mark.get(finding['level'], '?')} {finding['kind']}"
                   f"[{finding.get('key', '')}]{flag}: {finding['message']} "
                   f"(sedan {finding.get('since')})")
    for name, check in (status.get("checks") or {}).items():
        if not verbose and check.get("ok"):
            continue  # launchd-loggen: bara kraschade kontroller
        state = "ok" if check.get("ok") else f"KRASCH {check.get('error')}"
        out.append(f"  kontroll {name:11} {state} · {check.get('ms')} ms")
    return "\n".join(out)
