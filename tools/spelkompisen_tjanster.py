#!/usr/bin/env python3
"""Start och stopp av serverns LaunchAgents — Spelkompisen, Chartervakt, Bonusvakt.

Delad modul: CLI:t längst ned och menyraden i `spelkompisen_menubar.py` går
BÅDA genom `Launchd` här. Skriv aldrig en parallell launchd-implementation.

`start.sh`/`stop.sh` duger inte på servern: de frigör bara portarna, och varje
långlivad tjänst har `KeepAlive = true`, så launchd startar om processen inom
sekunder. Riktigt stopp kräver `bootout` av rätt label i rätt domän.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


LAUNCHCTL = "/bin/launchctl"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    project: str
    summary: str
    scheduled: bool = False
    # Sätts när ett stopp kostar data eller drift. Observationstid går inte att
    # bakfylla, så texten ska säga vad som faktiskt går förlorat.
    warning: str | None = None

    @property
    def plist(self) -> Path:
        return PLIST_DIR / f"{self.label}.plist"


SERVICES: tuple[Service, ...] = (
    Service(
        "backend", "com.saman.spelkompisen.backend", "Spelkompisen",
        "API på 127.0.0.1:8002",
    ),
    Service(
        "frontend", "com.saman.spelkompisen.frontend", "Spelkompisen",
        "byggd frontend på 0.0.0.0:5175",
    ),
    Service(
        "snapshot", "com.saman.spelkompisen.snapshot", "Spelkompisen",
        "Oddset-insamling :00 och :30", scheduled=True,
        warning="Oddsets insamlingsvarv stannar. Priser som rör sig under "
                "stoppet går inte att hämta i efterhand.",
    ),
    Service(
        "pool", "com.saman.spelkompisen.pool", "Spelkompisen",
        "pool, settlement och liveradar var 5:e minut", scheduled=True,
        warning="Pool, settlement och liveradar stannar. Observationstid är en "
                "del av mätningen och får aldrig bakfyllas.",
    ),
    Service(
        "kalltest", "com.saman.spelkompisen.kalltest", "Spelkompisen",
        "append-only källprov var 20:e minut", scheduled=True,
        warning="Källprovet är append-only; luckan går inte att fylla i efterhand.",
    ),
    Service(
        "awake", "com.saman.spelkompisen.awake", "Spelkompisen",
        "caffeinate -s, sömnskydd",
        warning="Sömnskyddet släpps. Somnar datorn stannar ALLA tre projektens "
                "insamlare, inte bara den här tjänsten.",
    ),
    Service(
        "menubar", "com.saman.spelkompisen.menubar", "Spelkompisen",
        "statusmenyn SK↗ i menyraden",
    ),
    Service(
        "charter", "com.saman.chartervakt", "Chartervakt",
        "webb och scheduler på 3100",
        warning="Chartervakts scheduler stannar. Prisändringar som sker under "
                "stoppet syns aldrig i historiken.",
    ),
    Service(
        "bonus", "com.saman.bonusvakt", "Bonusvakt",
        "webb, /v1-API och scheduler på 3000",
        warning="Bonusvakts scheduler stannar. Bonusplatser som dyker upp och "
                "försvinner under stoppet larmar aldrig.",
    ),
)

BY_KEY = {service.key: service for service in SERVICES}
BY_LABEL = {service.label: service for service in SERVICES}

GROUPS: dict[str, tuple[str, ...]] = {
    "all": tuple(service.key for service in SERVICES),
    "spelkompisen": tuple(
        service.key for service in SERVICES if service.project == "Spelkompisen"
    ),
}


@dataclass(frozen=True)
class Result:
    ok: bool
    message: str


CommandResult = tuple[int, str, str]
Runner = Callable[[Sequence[str]], CommandResult]


def local_runner(args: Sequence[str]) -> CommandResult:
    try:
        done = subprocess.run(
            [LAUNCHCTL, *args], capture_output=True, text=True, timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return done.returncode, done.stdout, done.stderr


def ssh_runner(host: str, user: str, key: str) -> Runner:
    """launchctl på servern från huvuddatorn — samma kommandon, annan transport."""

    def run(args: Sequence[str]) -> CommandResult:
        remote = f"{LAUNCHCTL} " + " ".join(shlex.quote(arg) for arg in args)
        try:
            done = subprocess.run(
                [
                    "/usr/bin/ssh", "-i", key,
                    "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
                    f"{user}@{host}", remote,
                ],
                capture_output=True, text=True, timeout=40,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, "", str(exc)
        return done.returncode, done.stdout, done.stderr

    return run


class Launchd:
    """launchd-domänen som håller de nio com.saman-tjänsterna."""

    def __init__(
        self,
        runner: Runner = local_runner,
        *,
        domain: str | None = None,
        local: bool = True,
    ) -> None:
        self.run = runner
        # Servern kör allt som saman (UID 501); över ssh måste domänen vara
        # serverns, inte den anropande datorns.
        self.domain = domain or f"gui/{os.getuid()}"
        self.local = local

    # ---- läsning ----

    def disabled(self) -> set[str]:
        code, out, _ = self.run(["print-disabled", self.domain])
        if code != 0:
            return set()
        return {
            match.group(1)
            for match in re.finditer(r'"([^"]+)"\s*=>\s*(?:disabled|true)', out)
        }

    def state(self) -> tuple[dict[str, dict[str, object]], str | None]:
        """Läge per label ur ETT `launchctl list` plus disable-listan."""
        code, out, err = self.run(["list"])
        if code != 0:
            return {}, err.strip() or f"launchctl list slutade med {code}"

        found: dict[str, dict[str, object]] = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 3 or parts[2] not in BY_LABEL:
                continue
            pid_text, exit_text, label = parts
            found[label] = {
                "loaded": True,
                "running": pid_text != "-",
                "pid": int(pid_text) if pid_text.isdigit() else None,
                "last_exit": int(exit_text) if exit_text.lstrip("-").isdigit() else None,
            }

        disabled = self.disabled()
        states: dict[str, dict[str, object]] = {}
        for label in BY_LABEL:
            entry = found.get(label) or {
                "loaded": False, "running": False, "pid": None, "last_exit": None,
            }
            states[label] = {**entry, "disabled": label in disabled}
        return states, None

    # ---- skrivning ----

    def start(self, service: Service) -> Result:
        states, error = self.state()
        if error:
            return Result(False, error)
        state = states.get(service.label, {})

        # Idempotent, och enda vägen tillbaka efter ett `stopp --permanent`.
        self.run(["enable", f"{self.domain}/{service.label}"])

        if state.get("loaded"):
            if service.scheduled or state.get("running"):
                return Result(True, "redan aktiv")
            code, _, err = self.run(["kickstart", f"{self.domain}/{service.label}"])
            if code != 0:
                return Result(False, err.strip() or f"kickstart slutade med {code}")
            return Result(True, "startad (låg nere trots laddad plist)")

        if self.local and not service.plist.exists():
            return Result(False, f"plist saknas: {service.plist}")

        code, _, err = self.run(["bootstrap", self.domain, str(service.plist)])
        if code != 0:
            return Result(False, err.strip() or f"bootstrap slutade med {code}")
        return Result(True, "startad")

    def stop(self, service: Service, *, permanent: bool = False) -> Result:
        code, _, err = self.run(["bootout", f"{self.domain}/{service.label}"])
        text = err.strip()
        if code == 0:
            note = "stoppad"
        elif code == 3 or "No such process" in text:
            note = "var redan stoppad"
        else:
            return Result(False, text or f"bootout slutade med {code}")

        if not permanent:
            return Result(True, f"{note} (kommer tillbaka vid nästa inloggning)")

        code, _, err = self.run(["disable", f"{self.domain}/{service.label}"])
        if code != 0:
            return Result(
                False, f"{note}, men disable misslyckades: {err.strip() or code}",
            )
        return Result(True, f"{note} och avstängd tills `start` körs")

    def restart(self, service: Service) -> Result:
        states, error = self.state()
        if error:
            return Result(False, error)
        if not states.get(service.label, {}).get("loaded"):
            return self.start(service)
        code, _, err = self.run(["kickstart", "-k", f"{self.domain}/{service.label}"])
        if code != 0:
            return Result(False, err.strip() or f"kickstart slutade med {code}")
        return Result(True, "omstartad")


def state_text(state: dict[str, object] | None, scheduled: bool = False) -> str:
    """Ett läge i klartext. Delas med menyraden så båda säger samma sak."""
    state = state or {}
    if state.get("disabled") and not state.get("loaded"):
        return "avstängd (överlever omstart)"
    if not state.get("loaded"):
        return "stoppad"
    if state.get("running"):
        return "kör"
    exit_code = state.get("last_exit")
    if exit_code not in (None, 0):
        return f"stoppad efter fel ({exit_code})"
    return "aktiv · väntar på nästa körning" if scheduled else "aktiv"


# ---- CLI ----

USAGE = """Användning:
  tjanster.sh status  [tjänst ...]
  tjanster.sh start   <tjänst ...>
  tjanster.sh stopp   <tjänst ...> [--permanent]
  tjanster.sh omstart <tjänst ...>

Tjänster:
  backend frontend snapshot pool kalltest awake menubar charter bonus
Grupper:
  all            alla nio
  spelkompisen   Spelkompisens sju

Flaggor:
  --permanent  stoppet överlever omstart och inloggning (launchctl disable)
  --ja         hoppa över bekräftelsefrågan (krävs när stdin inte är en terminal)
"""


def _resolve(names: Iterable[str]) -> tuple[list[Service], str | None]:
    picked: list[Service] = []
    for name in names:
        keys = GROUPS.get(name, (name,))
        for key in keys:
            service = BY_KEY.get(key)
            if service is None:
                return [], f"okänd tjänst: {key}"
            if service not in picked:
                picked.append(service)
    return picked, None


def _print_status(launchd: Launchd, services: Sequence[Service]) -> int:
    states, error = launchd.state()
    if error:
        print(f"kunde inte läsa launchd: {error}", file=sys.stderr)
        return 1

    rows = [
        (
            service.key,
            service.project,
            state_text(states.get(service.label), service.scheduled),
            str(states.get(service.label, {}).get("pid") or "–"),
        )
        for service in services
    ]
    head = ("TJÄNST", "PROJEKT", "LÄGE", "PID")
    widths = [max(len(row[i]) for row in (head, *rows)) for i in range(3)]
    print("  ".join(head[i].ljust(widths[i]) for i in range(3)) + "  " + head[3])
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(3)) + "  " + row[3])

    unhealthy = [
        service.key for service in services
        if not states.get(service.label, {}).get("loaded")
    ]
    return 1 if unhealthy else 0


def _confirm(services: Sequence[Service], permanent: bool, assume_yes: bool) -> bool:
    warnings = [service for service in services if service.warning]
    if not warnings and not permanent:
        return True
    if assume_yes:
        return True

    print("Stoppet påverkar:")
    for service in warnings:
        print(f"  · {service.key}: {service.warning}")
    if permanent:
        print("  · --permanent: tjänsterna startar INTE vid nästa inloggning.")
    if not sys.stdin.isatty():
        sys.stdout.flush()
        print("Avbryter: kör med --ja för att bekräfta utan terminal.", file=sys.stderr)
        return False
    return input("Fortsätt? [j/N] ").strip().lower() in {"j", "ja", "y", "yes"}


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    permanent = "--permanent" in args
    assume_yes = "--ja" in args
    args = [arg for arg in args if arg not in {"--permanent", "--ja"}]

    if not args or args[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0

    action, names = args[0], args[1:]
    if action not in {"status", "start", "stopp", "omstart"}:
        print(f"okänt kommando: {action}\n\n{USAGE}", file=sys.stderr)
        return 2
    if permanent and action != "stopp":
        print("--permanent gäller bara `stopp`.", file=sys.stderr)
        return 2
    if action != "status" and not names:
        print(f"{action} kräver minst en tjänst.\n\n{USAGE}", file=sys.stderr)
        return 2

    services, error = _resolve(names or ["all"])
    if error:
        print(f"{error}\n\n{USAGE}", file=sys.stderr)
        return 2

    launchd = Launchd()
    if action == "status":
        return _print_status(launchd, services)

    if action == "stopp" and not _confirm(services, permanent, assume_yes):
        return 1

    failed = False
    for service in services:
        if action == "start":
            result = launchd.start(service)
        elif action == "stopp":
            result = launchd.stop(service, permanent=permanent)
        else:
            result = launchd.restart(service)
        print(f"{'✓' if result.ok else '✗'} {service.key}: {result.message}")
        failed = failed or not result.ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
