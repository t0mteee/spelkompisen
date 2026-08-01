import contextlib
import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
