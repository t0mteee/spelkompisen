#!/usr/bin/env python3
"""Menyradsmonitor för Spelkompisen på den separata MacBook-servern."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spelkompisen_tjanster as tjanster  # noqa: E402


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
# Serverns saman är UID 501; över ssh måste domänen vara serverns, inte vår.
SERVER_UID = os.environ.get("SPELKOMPISEN_SERVER_UID", "501")

# Tjänstlistan ägs av spelkompisen_tjanster — en enda sanning för menyraden,
# CLI:t och drifthandboken.
SERVICE_LABELS = {
    service.key: service.label for service in tjanster.SERVICES
}


def _launchd() -> tjanster.Launchd:
    """Lokalt på servern, annars samma kommandon över ssh från huvuddatorn."""
    if LOCAL_MODE:
        return tjanster.Launchd()
    return tjanster.Launchd(
        tjanster.ssh_runner(SERVER_HOST, SERVER_USER, SSH_KEY),
        domain=f"gui/{SERVER_UID}",
        local=False,
    )


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
    states, error = _launchd().state()
    if error:
        return {}, error
    return {
        key: states.get(label, {
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


# Samma lägestext som CLI:t — menyraden och terminalen ska aldrig kunna säga
# olika saker om samma tjänst.
_service_text = tjanster.state_text


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
            self.services_item = self._build_services_menu()
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
                self.services_item,
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

        # ---- start/stopp ----

        def _build_services_menu(self) -> "rumps.MenuItem":
            """En post per tjänst med Starta om / Stoppa / Starta i undermeny.

            Byggs EN gång; `_apply` uppdaterar bara titlarna, annars flimrar
            menyn vid varje 30-sekunderskontroll.
            """
            root = rumps.MenuItem("Tjänster")
            self.service_items: dict[str, rumps.MenuItem] = {}
            project = None
            for service in tjanster.SERVICES:
                if project is not None and service.project != project:
                    root.add(rumps.separator)
                project = service.project

                item = rumps.MenuItem(service.key)
                for label, action in (
                    ("Starta om", "omstart"),
                    ("Stoppa", "stopp"),
                    ("Starta", "start"),
                    ("Stoppa permanent …", "permanent"),
                ):
                    item.add(rumps.MenuItem(
                        label, callback=self._service_action(action, service),
                    ))
                self.service_items[service.key] = item
                root.add(item)

            root.add(rumps.separator)
            root.add(rumps.MenuItem("Starta allt som ligger nere", callback=self.start_all))
            return root

        def _service_action(self, action: str, service) -> "callable":
            def run(_sender) -> None:
                self._run_action(action, service)
            return run

        def _run_action(self, action: str, service) -> None:
            permanent = action == "permanent"
            if action == "stopp" and service.warning:
                if not rumps.alert(
                    title=f"Stoppa {service.key}?",
                    message=f"{service.summary}\n\n{service.warning}",
                    ok="Stoppa", cancel="Avbryt",
                ):
                    return
            if permanent:
                if not rumps.alert(
                    title=f"Stoppa {service.key} permanent?",
                    message=(
                        f"{service.summary}\n\n"
                        f"{service.warning or ''}\n\n"
                        "Tjänsten startar INTE vid nästa inloggning eller omstart. "
                        "Den kommer tillbaka först när du startar den igen."
                    ).strip(),
                    ok="Stäng av", cancel="Avbryt",
                ):
                    return

            launchd = _launchd()
            if action == "start":
                result = launchd.start(service)
            elif action == "omstart":
                result = launchd.restart(service)
            else:
                result = launchd.stop(service, permanent=permanent)

            if not result.ok:
                rumps.alert(title=f"{service.key} — gick inte", message=result.message)
            self.refresh(None)

        def start_all(self, _sender) -> None:
            launchd = _launchd()
            states, error = launchd.state()
            if error:
                rumps.alert(title="Kunde inte läsa launchd", message=error)
                return
            nere = [
                service for service in tjanster.SERVICES
                if not states.get(service.label, {}).get("loaded")
            ]
            if not nere:
                rumps.alert(title="Allt är redan igång", message="Alla nio tjänster är laddade.")
                return
            problem = []
            for service in nere:
                result = launchd.start(service)
                if not result.ok:
                    problem.append(f"{service.key}: {result.message}")
            if problem:
                rumps.alert(title="Några startade inte", message="\n".join(problem))
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
            for service in tjanster.SERVICES:
                self.service_items[service.key].title = (
                    f"{service.key} · "
                    f"{_service_text(services.get(service.key), service.scheduled)}"
                )
            self.checked_item.title = f"Senast kontrollerad: {status['checked_at']}"

    SpelkompisenMonitor().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_once() if "--once" in sys.argv[1:] else _run_app())
