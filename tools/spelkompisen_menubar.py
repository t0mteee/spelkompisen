#!/usr/bin/env python3
"""Serverkontroll för Spelkompisen, Chartervakt och Bonusvakt."""

from __future__ import annotations

import json
import fcntl
import os
import sys
import time
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
AUTO_QUIT_MINUTES = max(0, int(os.environ.get(
    "SERVERKONTROLL_AUTO_QUIT_MINUTES", "0",
)))
TOOLS_DIR = Path(__file__).resolve().parent
ICON_PATH = TOOLS_DIR / "icons" / (
    "server-localTemplate.svg" if LOCAL_MODE else "server-remoteTemplate.svg"
)

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
        return tjanster.service_is_healthy(
            tjanster.BY_KEY[name], services.get(name),
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
    from AppKit import (  # laddas bara när GUI:t faktiskt startas
        NSMutableAttributedString,
        NSColor,
        NSForegroundColorAttributeName,
    )

    lock_path = Path("/tmp") / (
        f"serverkontroll-{os.getuid()}-{'local' if LOCAL_MODE else 'remote'}.lock"
    )
    lock = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0

    def heading(title: str) -> "rumps.MenuItem":
        item = rumps.MenuItem(title.upper())
        item.set_callback(None)
        item._menuitem.setEnabled_(False)
        return item

    def colored_title(
        item: "rumps.MenuItem", title: str, colored_text: str, tone: str,
    ) -> None:
        """Färga bara lägesordet; resten följer macOS-temat."""
        item.title = title
        start = title.find(colored_text)
        if start < 0:
            return
        colors = {
            "green": NSColor.systemGreenColor(),
            "red": NSColor.systemRedColor(),
            "orange": NSColor.systemOrangeColor(),
        }
        attributed = NSMutableAttributedString.alloc().initWithString_(title)
        attributed.addAttribute_value_range_(
            NSForegroundColorAttributeName,
            colors.get(tone, NSColor.secondaryLabelColor()),
            (start, len(colored_text)),
        )
        item._menuitem.setAttributedTitle_(attributed)

    class Serverkontroll(rumps.App):
        def __init__(self) -> None:
            super().__init__(
                "Serverkontroll", title="…",
                icon=str(ICON_PATH) if ICON_PATH.exists() else None,
                template=True, quit_button=None,
            )
            if not ICON_PATH.exists():
                self.title = "▤↗ …" if not LOCAL_MODE else "▤ …"
            self.server_item = rumps.MenuItem("Webb & API: kontrollerar …")
            self.data_item = rumps.MenuItem("Datastatus: kontrollerar …")
            self.snapshot_item = rumps.MenuItem("Oddset-insamling: kontrollerar …")
            self.pool_item = rumps.MenuItem("Pool + live: kontrollerar …")
            self.awake_item = rumps.MenuItem("Sömnskydd: kontrollerar …")
            self.kalltest_item = rumps.MenuItem("Källprov: kontrollerar …")
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
                heading("Spelkompisen"),
                self.server_item,
                self.data_item,
                self.snapshot_item,
                self.pool_item,
                None,
                heading("Chartervakt"),
                self.charter_item,
                None,
                heading("Bonusvakt"),
                self.bonus_item,
                None,
                heading("Server & övervakning"),
                self.awake_item,
                self.kalltest_item,
                None,
                self.services_item,
                None,
                rumps.MenuItem("Öppna Spelkompisen", callback=self.open_app),
                rumps.MenuItem("Öppna Chartervakt", callback=self.open_charter),
                rumps.MenuItem("Öppna Bonusvakt", callback=self.open_bonus),
                rumps.MenuItem("Uppdatera nu", callback=self.refresh),
                self.checked_item,
                *([rumps.MenuItem(
                    f"Stängs efter {AUTO_QUIT_MINUTES} min utan aktivitet",
                    callback=None,
                )] if AUTO_QUIT_MINUTES else []),
                None,
                rumps.MenuItem("Avsluta serverkontroll", callback=rumps.quit_application),
            ]
            self._refreshing = False
            self._last_interaction = time.monotonic()
            self.timer = rumps.Timer(self.refresh, 30)
            self.timer.start()
            self.idle_timer = None
            if AUTO_QUIT_MINUTES:
                self.idle_timer = rumps.Timer(self._auto_quit, 30)
                self.idle_timer.start()
            self.refresh(None)

        def _touch(self) -> None:
            self._last_interaction = time.monotonic()

        def _auto_quit(self, _sender) -> None:
            if time.monotonic() - self._last_interaction >= AUTO_QUIT_MINUTES * 60:
                rumps.quit_application()

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
                if service.project != project:
                    if project is not None:
                        root.add(rumps.separator)
                    root.add(heading(service.project))
                project = service.project

                item = rumps.MenuItem(service.name)
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
            self._touch()
            permanent = action == "permanent"
            if action == "stopp" and service.warning:
                if not rumps.alert(
                    title=f"Stoppa {service.name}?",
                    message=f"{service.summary}\n\n{service.warning}",
                    ok="Stoppa", cancel="Avbryt",
                ):
                    return
            if permanent:
                if not rumps.alert(
                    title=f"Stoppa {service.name} permanent?",
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
                rumps.alert(title=f"{service.name} — gick inte", message=result.message)
            self.refresh(None)

        def start_all(self, _sender) -> None:
            self._touch()
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
                rumps.alert(
                    title="Allt är redan igång",
                    message=f"Alla {len(tjanster.SERVICES)} tjänster är laddade.",
                )
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
            self._touch()
            webbrowser.open(SERVER_URL)

        def open_charter(self, _sender) -> None:
            self._touch()
            webbrowser.open(CHARTER_URL)

        def open_bonus(self, _sender) -> None:
            self._touch()
            webbrowser.open(BONUS_URL)

        def refresh(self, _sender) -> None:
            if _sender is not self.timer:
                self._touch()
            if self._refreshing:
                return
            self._refreshing = True
            self.title = "…" if ICON_PATH.exists() else (
                "▤↗ …" if not LOCAL_MODE else "▤ …"
            )
            status = collect_status()
            self._apply(status)

        def _apply(self, status: dict[str, object]) -> None:
            self._refreshing = False
            services = status.get("services") or {}
            marker = "✓" if status.get("healthy") else "!"
            self.title = marker if ICON_PATH.exists() else (
                f"▤↗ {marker}" if not LOCAL_MODE else f"▤ {marker}"
            )
            if status.get("frontend_ok") and status.get("api_ok"):
                state, tone = "kör", "green"
                title = f"Webb & API: {state} · {SERVER_HOST}"
            elif status.get("frontend_ok"):
                state, tone = "delvis fel", "red"
                title = f"Webb & API: {state} · backend svarar inte"
            else:
                state, tone = "stoppad", "red"
                title = f"Webb & API: {state}"
            colored_title(self.server_item, title, state, tone)
            data_status = status.get("data_status")
            data_text = (
                "grön" if data_status == "ok"
                else "kräver tillsyn" if data_status else "inget svar"
            )
            colored_title(
                self.data_item, f"Datastatus: {data_text}", data_text,
                "green" if data_status == "ok" else "red",
            )
            for item, key, label in (
                (self.snapshot_item, "snapshot", "Oddset-insamling"),
                (self.pool_item, "pool", "Pool & live"),
                (self.awake_item, "awake", "Sömnskydd"),
                (self.kalltest_item, "kalltest", "Källprov"),
            ):
                definition = tjanster.BY_KEY[key]
                state = _service_text(services.get(key), definition.scheduled)
                colored_title(
                    item, f"{label}: {state}", state,
                    tjanster.state_tone(services.get(key), definition.scheduled),
                )
            charter_process = _service_text(services.get("charter"))
            charter_state = "kör" if status.get("charter_ok") else "stoppad"
            colored_title(
                self.charter_item,
                f"Chartervakt: {charter_state} · {charter_process}",
                charter_state, "green" if status.get("charter_ok") else "red",
            )
            bonus_process = _service_text(services.get("bonus"))
            notifier = status.get("bonus_notifier") or "ingen push"
            bonus_state = "kör" if status.get("bonus_ok") else "stoppad"
            bonus_title = (
                f"Bonusvakt: {bonus_state} · {bonus_process} · {notifier}"
                if status.get("bonus_ok") else
                f"Bonusvakt: {bonus_state} · {bonus_process}"
            )
            colored_title(
                self.bonus_item, bonus_title, bonus_state,
                "green" if status.get("bonus_ok") else "red",
            )
            for service in tjanster.SERVICES:
                state = _service_text(services.get(service.key), service.scheduled)
                colored_title(
                    self.service_items[service.key],
                    f"{service.name} · {state}", state,
                    tjanster.state_tone(
                        services.get(service.key), service.scheduled,
                    ),
                )
            self.checked_item.title = f"Senast kontrollerad: {status['checked_at']}"

    Serverkontroll().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_once() if "--once" in sys.argv[1:] else _run_app())
