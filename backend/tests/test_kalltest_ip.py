import contextlib
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kalltest_ip.py"
SPEC = importlib.util.spec_from_file_location("kalltest_ip", SCRIPT)
kalltest = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(kalltest)


class KalltestReportTests(unittest.TestCase):
    def _write_log(self, path: Path, *, samples: int = 73,
                   missing: str | None = None, failed: str | None = None,
                   hours: int = 73) -> None:
        start = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
        rows = []
        for name, _check, _critical, _feeds in kalltest.CHECKS:
            if name == missing:
                continue
            for index in range(samples):
                when = start + dt.timedelta(hours=hours * index / (samples - 1))
                rows.append({
                    "at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "source": name,
                    "ok": name != failed,
                    "transport_ok": name != failed,
                    "coverage_ok": True if name == "flashscore" else None,
                    "ms": 10,
                    "note": "ok",
                })
        path.write_text("".join(json.dumps(row) + "\n" for row in rows),
                        encoding="utf-8")

    def _report(self, log: Path) -> tuple[int, str]:
        output = io.StringIO()
        with patch.object(kalltest, "LOG", log), contextlib.redirect_stdout(output):
            code = kalltest.report()
        return code, output.getvalue()

    def test_report_requires_every_source(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log, missing="pinnacle")
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("pinnacle", output)
        self.assertIn("saknas helt", output)

    def test_missing_support_source_does_not_block_critical_use(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log, missing="sofa_live")
            code, output = self._report(log)
        self.assertEqual(0, code)
        self.assertIn("användbar för alla kritiska funktioner", output)
        self.assertIn("sofa_live", output)

    def test_report_requires_real_72_hour_span(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log, hours=24)
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("✗ minst 72 h", output)
        self.assertIn("UNDERLAG OTILLRÄCKLIGT", output)
        self.assertNotIn("DISKVALIFICERAD", output)

    def test_report_requires_enough_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log, samples=4)
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("✗ minst 72 prov", output)
        self.assertIn("UNDERLAG OTILLRÄCKLIGT", output)

    def test_report_accepts_complete_three_day_series(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log)
            code, output = self._report(log)
        self.assertEqual(0, code)
        self.assertIn("separat statistiktäckning", output)

    def test_malformed_json_is_reported_without_crashing(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log)
            with log.open("a", encoding="utf-8") as stream:
                stream.write('{"at":"avbruten"\n')
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("1 loggrader är trasiga", output)
        self.assertIn("UNDERLAG OTILLRÄCKLIGT", output)

    def test_early_critical_failure_is_incomplete_not_disqualified(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log, samples=4, hours=3, failed="pinnacle")
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("UNDERLAG OTILLRÄCKLIGT", output)
        self.assertNotIn("DISKVALIFICERAD", output)

    def test_dns_errors_are_excluded_from_source_share(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log)
            when = "2026-08-04T02:00:00Z"
            with log.open("a", encoding="utf-8") as stream:
                for name, _check, _critical, _feeds in kalltest.CHECKS:
                    note = ("DNSError: Failed to perform, curl: (6) "
                            "Could not resolve host: api.example.test")
                    stream.write(json.dumps({
                        "at": when,
                        "source": name,
                        "ok": False,
                        "transport_ok": False,
                        "note": note,
                    }) + "\n")
            code, output = self._report(log)
        self.assertEqual(0, code)
        self.assertIn("exkluderade ur källornas OK-andelar", output)
        self.assertIn("100.0 % transport-OK av 73", output)

    def test_repeated_dns_outage_fails_infrastructure_not_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            self._write_log(log)
            with log.open("a", encoding="utf-8") as stream:
                for run_index in range(10):
                    when = f"2026-08-04T{10 + run_index:02d}:00:00Z"
                    for name, _check, _critical, _feeds in kalltest.CHECKS:
                        stream.write(json.dumps({
                            "run_id": f"dns-{run_index}",
                            "at": when,
                            "source": name,
                            "ok": False,
                            "transport_ok": False,
                            "note": ("ConnectError: [Errno -3] Temporary "
                                     "failure in name resolution"),
                        }) + "\n")
            code, output = self._report(log)
        self.assertEqual(1, code)
        self.assertIn("INFRASTRUKTUR UNDERKÄND", output)
        self.assertNotIn("DISKVALIFICERAD", output)


class KalltestProbeTests(unittest.TestCase):
    def test_flashscore_empty_statistics_is_coverage_gap_not_transport_error(self):
        daily = SimpleNamespace(
            status_code=200,
            headers={},
            text="~AA÷empty¬AB÷2~AA÷covered¬AB÷2",
        )
        empty = SimpleNamespace(status_code=200, headers={}, text="")
        covered = SimpleNamespace(status_code=200, headers={},
                                  text="SG÷Total shots¬SH÷8¬SI÷4")
        with patch.object(kalltest.httpx, "get",
                          side_effect=[daily, empty, covered]):
            transport_ok, note, coverage_ok = kalltest.check_flashscore()

        self.assertTrue(transport_ok)
        self.assertTrue(coverage_ok)
        self.assertIn("statistiktäckning 1/2", note)

    def test_sofascore_model_checks_every_real_endpoint_type(self):
        calls = []

        def fake_get(path):
            calls.append(path)
            keys = next(keys for _label, probe_path, keys
                        in kalltest.SOFA_MODEL_PROBES if probe_path == path)
            return SimpleNamespace(
                status_code=200,
                headers={},
                json=lambda: {key: [] for key in keys},
            )

        with patch.object(kalltest, "_sofa_get", side_effect=fake_get):
            ok, note = kalltest.check_sofascore_model()

        self.assertTrue(ok)
        self.assertEqual([path for _label, path, _keys
                          in kalltest.SOFA_MODEL_PROBES], calls)
        self.assertIn("8/8 modell-endpoints OK", note)

    def test_sofascore_live_is_kept_separate_from_model_probe(self):
        response = SimpleNamespace(
            status_code=403,
            headers={},
            json=lambda: {},
        )
        with patch.object(kalltest, "_sofa_get", return_value=response) as get:
            ok, note = kalltest.check_sofascore_live()
        self.assertFalse(ok)
        self.assertEqual("status 403", note)
        get.assert_called_once_with("/sport/football/events/live")

    def test_one_run_gets_one_run_id_and_explicit_outcomes(self):
        checks = (
            ("good", lambda: (True, "ok"), True, "good feed"),
            ("dns", lambda: (_ for _ in ()).throw(
                RuntimeError("Could not resolve host: example.test")),
             True, "dns feed"),
        )
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "log.jsonl"
            with patch.object(kalltest, "CHECKS", checks):
                code = kalltest.run_once(True, log)
            rows = [json.loads(line) for line in
                    log.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(1, code)
        self.assertEqual(1, len({row["run_id"] for row in rows}))
        self.assertEqual(["ok", "infrastructure_error"],
                         [row["outcome"] for row in rows])
        self.assertEqual("dns", rows[1]["infrastructure_error"])


if __name__ == "__main__":
    unittest.main()
