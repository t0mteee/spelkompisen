#!/usr/bin/env python3
"""Menyradsmonitor för Spelkompisen på den separata MacBook-servern."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime


SERVER_URL = os.environ.get("SPELKOMPISEN_SERVER_URL", "http://192.168.50.100:5175")
CHARTER_URL = os.environ.get("CHARTERVAKT_SERVER_URL", "http://192.168.50.100:3100")
BONUS_URL = os.environ.get("BONUSVAKT_SERVER_URL", "http://192.168.50.100:3000")
SERVER_HOST = os.environ.get("SPELKOMPISEN_SERVER_HOST", "192.168.50.100")
SERVER_USER = os.environ.get("SPELKOMPISEN_SERVER_USER", "saman")
LOCAL_MODE = os.environ.get("SPELKOMPISEN_MONITOR_LOCAL") == "1"
SSH_KEY = os.path.expanduser(os.environ.get(
    "SPELKOMPISEN_SERVER_SSH_KEY",
    "~/.ssh/spelkompisen_server_ed25519",
))

SERVICE_LABELS = {
    "backend": "com.saman.spelkompisen.backend",
    "frontend": "com.saman.spelkompisen.frontend",
    "snapshot": "com.saman.spelkompisen.snapshot",
    "pool": "com.saman.spelkompisen.pool",
    "kalltest": "com.saman.spelkompisen.kalltest",
    "awake": "com.saman.spelkompisen.awake",
    "charter": "com.saman.chartervakt",
    "bonus": "com.saman.bonusvakt",
}


def _fetch(
    path: str,
    *,
    base_url: str = SERVER_URL,
    timeout: float = 4.0,
) -> tuple[bool, object | None, str | None]:
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={"User-Agent": "Spelkompisen-menyrad/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if path == "/":
            return True, None, None
        return True, json.loads(raw), None
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return False, None, str(exc)


def _remote_services() -> tuple[dict[str, dict[str, object]], str | None]:
    command = (["/bin/launchctl", "list"] if LOCAL_MODE else [
        "/usr/bin/ssh", "-i", SSH_KEY,
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
        f"{SERVER_USER}@{SERVER_HOST}", "launchctl list",
    ])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=7)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, str(exc)
    if result.returncode != 0:
        transport = "launchctl" if LOCAL_MODE else "ssh"
        return {}, (result.stderr.strip() or f"{transport} slutade med {result.returncode}")

    by_label: dict[str, dict[str, object]] = {}
    wanted = set(SERVICE_LABELS.values())
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[2] not in wanted:
            continue
        pid_text, exit_text, label = parts
        by_label[label] = {
            "loaded": True,
            "running": pid_text != "-",
            "pid": int(pid_text) if pid_text.isdigit() else None,
            "last_exit": int(exit_text) if exit_text.lstrip("-").isdigit() else None,
        }
    return {
        key: by_label.get(label, {
            "loaded": False,
            "running": False,
            "pid": None,
            "last_exit": None,
        })
        for key, label in SERVICE_LABELS.items()
    }, None


def collect_status() -> dict[str, object]:
    frontend_ok, _, frontend_error = _fetch("/")
    api_ok, health, api_error = _fetch("/api/health")
    charter_ok, _, charter_error = _fetch("/", base_url=CHARTER_URL)
    bonus_ok, bonus_health, bonus_error = _fetch("/v1/health", base_url=BONUS_URL)
    services, ssh_error = _remote_services()
    def service_ok(name: str) -> bool:
        service = services.get(name, {})
        return bool(service.get("loaded")) and (
            bool(service.get("running"))
            or service.get("last_exit") in (None, 0)
        )
    required_services_ok = all(
        service_ok(name)
        for name in ("backend", "frontend", "snapshot", "pool", "awake")
    )
    data_status = health.get("status") if isinstance(health, dict) else None
    charter_service_ok = service_ok("charter")
    healthy = (
        frontend_ok
        and api_ok
        and required_services_ok
        and data_status == "ok"
        and charter_ok
        and charter_service_ok
        and bonus_ok
        and service_ok("bonus")
    )
    return {
        "healthy": healthy,
        "frontend_ok": frontend_ok,
        "frontend_error": frontend_error,
        "api_ok": api_ok,
        "api_error": api_error,
        "data_status": data_status,
        "charter_ok": charter_ok,
        "charter_error": charter_error,
        "bonus_ok": bonus_ok,
        "bonus_error": bonus_error,
        "bonus_notifier": (
            (bonus_health.get("notifier") or {}).get("kind")
            if isinstance(bonus_health, dict) else None
        ),
        "services": services,
        "ssh_error": ssh_error,
        "checked_at": datetime.now().astimezone().strftime("%H:%M:%S"),
    }


def _service_text(service: dict[str, object] | None, scheduled: bool = False) -> str:
    service = service or {}
    if not service.get("loaded"):
        return "saknas"
    if service.get("running"):
        return "kör nu"
    exit_code = service.get("last_exit")
    if exit_code not in (None, 0):
        return f"stoppad efter fel ({exit_code})"
    return "aktiv · väntar på nästa körning" if scheduled else "aktiv"


def _run_once() -> int:
    status = collect_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0 if status["healthy"] else 1


def _run_app() -> int:
    import rumps

    class SpelkompisenMonitor(rumps.App):
        def __init__(self) -> None:
            super().__init__("SK↗ …", quit_button=None)
            self.server_item = rumps.MenuItem("Server: kontrollerar …")
            self.data_item = rumps.MenuItem("Datastatus: kontrollerar …")
            self.snapshot_item = rumps.MenuItem("Oddset-insamling: kontrollerar …")
            self.pool_item = rumps.MenuItem("Pool + live: kontrollerar …")
            self.awake_item = rumps.MenuItem("Sömnskydd: kontrollerar …")
            self.kalltest_item = rumps.MenuItem("Källtest: kontrollerar …")
            self.charter_item = rumps.MenuItem("Chartervakt: kontrollerar …")
            self.bonus_item = rumps.MenuItem("Bonusvakt: kontrollerar …")
            self.checked_item = rumps.MenuItem("Senast kontrollerad: –")
            for item in (
                self.server_item, self.data_item, self.snapshot_item,
                self.pool_item, self.awake_item, self.kalltest_item,
                self.charter_item,
                self.bonus_item,
                self.checked_item,
            ):
                item.set_callback(None)
            self.menu = [
                self.server_item,
                self.data_item,
                None,
                self.snapshot_item,
                self.pool_item,
                self.awake_item,
                self.kalltest_item,
                None,
                self.charter_item,
                self.bonus_item,
                None,
                rumps.MenuItem("Öppna Spelkompisen", callback=self.open_app),
                rumps.MenuItem("Öppna Chartervakt", callback=self.open_charter),
                rumps.MenuItem("Öppna Bonusvakt", callback=self.open_bonus),
                rumps.MenuItem("Uppdatera nu", callback=self.refresh),
                self.checked_item,
                None,
                rumps.MenuItem("Avsluta monitor", callback=rumps.quit_application),
            ]
            self._refreshing = False
            self.timer = rumps.Timer(self.refresh, 30)
            self.timer.start()
            self.refresh(None)

        def open_app(self, _sender) -> None:
            webbrowser.open(SERVER_URL)

        def open_charter(self, _sender) -> None:
            webbrowser.open(CHARTER_URL)

        def open_bonus(self, _sender) -> None:
            webbrowser.open(BONUS_URL)

        def refresh(self, _sender) -> None:
            if self._refreshing:
                return
            self._refreshing = True
            self.title = "SK↗ …"
            status = collect_status()
            self._apply(status)

        def _apply(self, status: dict[str, object]) -> None:
            self._refreshing = False
            services = status.get("services") or {}
            self.title = "SK↗ ✓" if status.get("healthy") else "SK↗ !"
            if status.get("frontend_ok") and status.get("api_ok"):
                self.server_item.title = f"Server: online · {SERVER_HOST}"
            elif status.get("frontend_ok"):
                self.server_item.title = "Server: frontend online · backend svarar inte"
            else:
                self.server_item.title = "Server: offline"
            data_status = status.get("data_status")
            self.data_item.title = (
                "Datastatus: grön" if data_status == "ok"
                else "Datastatus: kräver tillsyn" if data_status
                else "Datastatus: inget svar"
            )
            self.snapshot_item.title = (
                "Oddset-insamling: " + _service_text(services.get("snapshot"), True)
            )
            self.pool_item.title = (
                "Pool + live: " + _service_text(services.get("pool"), True)
            )
            self.awake_item.title = "Sömnskydd: " + _service_text(services.get("awake"))
            self.kalltest_item.title = (
                "Källtest: " + _service_text(services.get("kalltest"), True)
            )
            charter_process = _service_text(services.get("charter"))
            self.charter_item.title = (
                f"Chartervakt: online · {charter_process}"
                if status.get("charter_ok")
                else f"Chartervakt: offline · {charter_process}"
            )
            bonus_process = _service_text(services.get("bonus"))
            notifier = status.get("bonus_notifier") or "ingen push"
            self.bonus_item.title = (
                f"Bonusvakt: online · {bonus_process} · {notifier}"
                if status.get("bonus_ok")
                else f"Bonusvakt: offline · {bonus_process}"
            )
            self.checked_item.title = f"Senast kontrollerad: {status['checked_at']}"

    SpelkompisenMonitor().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_once() if "--once" in sys.argv[1:] else _run_app())
