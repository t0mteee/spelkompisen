"""Regressionstester för serverns gemensamma launchd-kontroll."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
import spelkompisen_tjanster as tjanster  # noqa: E402


class FakeRunner:
    def __init__(self, list_output: str = "") -> None:
        self.list_output = list_output
        self.calls: list[list[str]] = []

    def __call__(self, args):
        command = list(args)
        self.calls.append(command)
        if command == ["list"]:
            return 0, self.list_output, ""
        if command[:1] == ["print-disabled"]:
            return 0, 'disabled services = { }', ""
        return 0, "", ""


class ServiceCatalogTests(unittest.TestCase):
    def test_projects_are_visible_and_server_helpers_are_not_spelkompisen(self):
        projects = {service.key: service.project for service in tjanster.SERVICES}
        self.assertEqual("Spelkompisen", projects["backend"])
        self.assertEqual("Chartervakt", projects["charter"])
        self.assertEqual("Bonusvakt", projects["bonus"])
        for key in ("awake", "kalltest", "menubar"):
            self.assertEqual("Server & övervakning", projects[key])

        self.assertEqual(
            ("backend", "frontend", "snapshot", "pool"),
            tjanster.GROUPS["spelkompisen"],
        )
        self.assertEqual(("awake", "kalltest", "menubar"),
                         tjanster.GROUPS["server"])

    def test_names_are_human_readable(self):
        self.assertEqual("Oddset-insamling", tjanster.BY_KEY["snapshot"].name)
        self.assertEqual("Pool & live", tjanster.BY_KEY["pool"].name)
        self.assertEqual("Källprov (IP och datakällor)",
                         tjanster.BY_KEY["kalltest"].name)

    def test_state_text_tone_and_health_distinguish_scheduled_services(self):
        waiting = {"loaded": True, "running": False, "last_exit": 0}
        stopped = {"loaded": False, "running": False, "last_exit": None}
        failed = {"loaded": True, "running": False, "last_exit": 1}

        self.assertIn("väntar", tjanster.state_text(waiting, scheduled=True))
        self.assertEqual("green", tjanster.state_tone(waiting, scheduled=True))
        self.assertTrue(tjanster.service_is_healthy(
            tjanster.BY_KEY["snapshot"], waiting,
        ))
        self.assertFalse(tjanster.service_is_healthy(
            tjanster.BY_KEY["backend"], waiting,
        ))
        self.assertEqual("red", tjanster.state_tone(stopped))
        self.assertEqual("red", tjanster.state_tone(failed))


class LaunchdTests(unittest.TestCase):
    def test_state_parses_running_waiting_and_disabled(self):
        runner = FakeRunner(
            "123\t0\tcom.saman.spelkompisen.backend\n"
            "-\t0\tcom.saman.spelkompisen.snapshot\n"
        )

        def with_disabled(args):
            if list(args)[:1] == ["print-disabled"]:
                return 0, ('disabled services = {\n'
                           '  "com.saman.bonusvakt" => true\n}'), ""
            return runner(args)

        states, error = tjanster.Launchd(
            with_disabled, domain="gui/501", local=False,
        ).state()
        self.assertIsNone(error)
        self.assertTrue(states["com.saman.spelkompisen.backend"]["running"])
        self.assertFalse(states["com.saman.spelkompisen.snapshot"]["running"])
        self.assertTrue(states["com.saman.bonusvakt"]["disabled"])

    def test_start_enables_then_bootstraps_an_unloaded_service(self):
        runner = FakeRunner()
        launchd = tjanster.Launchd(runner, domain="gui/501", local=False)
        result = launchd.start(tjanster.BY_KEY["charter"])
        self.assertTrue(result.ok)
        self.assertIn(["enable", "gui/501/com.saman.chartervakt"], runner.calls)
        self.assertIn([
            "bootstrap", "gui/501",
            str(tjanster.BY_KEY["charter"].plist),
        ], runner.calls)

    def test_permanent_stop_boots_out_and_disables(self):
        runner = FakeRunner()
        launchd = tjanster.Launchd(runner, domain="gui/501", local=False)
        result = launchd.stop(tjanster.BY_KEY["bonus"], permanent=True)
        self.assertTrue(result.ok)
        self.assertEqual([
            ["bootout", "gui/501/com.saman.bonusvakt"],
            ["disable", "gui/501/com.saman.bonusvakt"],
        ], runner.calls)

    def test_restart_uses_targeted_kickstart(self):
        runner = FakeRunner("42\t0\tcom.saman.spelkompisen.backend\n")
        launchd = tjanster.Launchd(runner, domain="gui/501", local=False)
        result = launchd.restart(tjanster.BY_KEY["backend"])
        self.assertTrue(result.ok)
        self.assertEqual(
            ["kickstart", "-k", "gui/501/com.saman.spelkompisen.backend"],
            runner.calls[-1],
        )


if __name__ == "__main__":
    unittest.main()
