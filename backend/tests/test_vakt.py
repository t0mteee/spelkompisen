"""Driftvakten (app/vakt.py): varje kontroll med fixturer och injicerad klocka.

Inga riktiga launchctl-, git- eller ps-anrop: kommandokörningen är en fake.
Fallet som motiverade vakten — Sofascore 403 i varje källprov sedan
2026-09-25T10:43Z utan att något syntes — är låst ordagrant i KallorTests.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock

from app import pool_health, vakt
from app.storage import Storage

UTC = dt.timezone.utc
LAUNCHCTL = "/bin/launchctl"
Usage = namedtuple("Usage", "total used free")
GB = 1024 ** 3


def t(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def kalltest_row(run_id: str, at: str, source: str, ok: bool, note: str,
                 infra: str | None = None) -> dict:
    return {"schema_version": 2, "run_id": run_id, "at": at, "source": source,
            "ok": ok, "transport_ok": ok, "coverage_ok": None,
            "outcome": "infrastructure_error" if infra else ("ok" if ok else "source_error"),
            "infrastructure_error": infra, "ms": 40, "note": note}


SOFA_MODEL_403 = ("0/8 modell-endpoints OK · säsonger status 403; avslutade matcher "
                  "status 403")


def sofascore_runs() -> list[dict]:
    """Källprovets riktiga rader runt 2026-09-25: grönt 04:43, 403 från 10:43."""
    rows = []
    for run_at, sofa_ok in (("2026-09-24T22:43:03Z", True), ("2026-09-25T04:43:15Z", True),
                            ("2026-09-25T10:43:17Z", False), ("2026-09-25T16:43:19Z", False),
                            ("2026-09-25T22:43:21Z", False)):
        run_id = f"{run_at}-abcd1234"
        row_at = run_at[:-3] + f"{int(run_at[-3:-1]) + 1:02d}Z"
        rows.append(kalltest_row(run_id, run_at, "svenskaspel", True, "'draws' ok (1)"))
        rows.append(kalltest_row(run_id, run_at, "pinnacle", True, "lista, 4867 objekt"))
        rows.append(kalltest_row(run_id, row_at, "sofa_model", sofa_ok,
                                 "8/8 modell-endpoints OK" if sofa_ok else SOFA_MODEL_403))
        rows.append(kalltest_row(run_id, row_at, "sofa_live", sofa_ok,
                                 "'events' ok (3)" if sofa_ok else "status 403"))
    return rows


class FakeRunner:
    """Svarar på launchctl/ps/git utan att köra något."""

    def __init__(self, *, launchctl_list: str = "", disabled: str = "",
                 git: dict | None = None, ps: str | None = None,
                 kontroll: tuple[int, str, str] = (0, "== kontroll ==\nALLT GRÖNT\n", "")):
        self.launchctl_list = launchctl_list
        self.disabled = disabled
        self.git = git or {}
        self.ps = ps
        self.kontroll = kontroll
        self.calls: list[list[str]] = []

    def __call__(self, args, *, timeout=30, cwd=None, env=None):
        args = [str(a) for a in args]
        self.calls.append(args)
        if args[0] == LAUNCHCTL:
            if args[1] == "list":
                return 0, self.launchctl_list, ""
            if args[1] == "print-disabled":
                return 0, f"disabled services = {{\n{self.disabled}}}", ""
            return 0, "", ""
        if args[0] == "ps":
            return (0, self.ps, "") if self.ps is not None else (1, "", "no such process")
        if args[0] == "git":
            sub = tuple(args[4:])
            for prefix, response in self.git.items():
                if sub[:len(prefix)] == prefix:
                    return response
            return 0, "", ""
        if args[0] == "/bin/bash" and args[1].endswith("kontroll.sh"):
            return self.kontroll
        return 127, "", "okänt kommando i testet"

    def git_calls(self, *prefix: str) -> list[list[str]]:
        return [call for call in self.calls
                if call[0] == "git" and tuple(call[4:4 + len(prefix)]) == prefix]


def launchctl_rows(**rows: tuple[str, str]) -> str:
    """launchctl list: PID \\t senaste exit \\t label."""
    lines = ["PID\tStatus\tLabel"]
    for key, (pid, status) in rows.items():
        lines.append(f"{pid}\t{status}\tcom.saman.spelkompisen.{key}")
    return "\n".join(lines) + "\n"


HEALTHY = dict(backend=("123", "-15"), frontend=("124", "0"), snapshot=("-", "0"),
               pool=("-", "0"), backup=("-", "0"), kalltest=("-", "0"), vakt=("125", "0"))


class Base(unittest.TestCase):
    NOW = t("2026-09-26T00:00:00Z")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        self.status_dir = self.data / "vakt"
        self.repo = self.root / "repo"
        self.repo.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, now=None, runner=None, prev=None, **kwargs) -> vakt.Ctx:
        prev = prev or {}
        return vakt.Ctx(now=now or self.NOW, data_dir=self.data,
                        db_path=self.data / "stryktips.db", repo=self.repo,
                        status_dir=self.status_dir, prev=prev,
                        run=runner or FakeRunner(), state=json.loads(json.dumps(
                            prev.get("state") or {})), **kwargs)

    def run_vakt(self, checks, now=None, runner=None, **kwargs) -> dict:
        status = vakt.run(now=now or self.NOW, data_dir=self.data, repo=self.repo,
                          status_dir=self.status_dir, runner=runner or FakeRunner(),
                          checks=checks, **kwargs)
        vakt.write_status(status, self.status_dir)
        return status

    @staticmethod
    def by_kind(findings: list[dict], kind: str) -> list[dict]:
        return [f for f in findings if f["kind"] == kind]


class KallorTests(Base):
    def write(self, rows):
        with (self.data / vakt.KALLTEST_LOG).open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.write("{trasig rad\n")  # en avbruten skrivning får inte fälla kontrollen

    def test_sofascore_403_sedan_2026_09_25_ger_kalla_nere_per_kalla(self):
        self.write(sofascore_runs())
        findings = vakt.check_kallor(self.ctx())
        down = {f["key"]: f for f in self.by_kind(findings, "kalla_nere")}
        self.assertEqual({"sofa_model", "sofa_live"}, set(down))
        for finding in down.values():
            self.assertEqual("error", finding["level"])
            self.assertEqual("kallor", finding["area"])
            self.assertEqual("2026-09-25T10:43:18Z", finding["since"])
            self.assertEqual(3, finding["runs"])
        self.assertIn("status 403", down["sofa_live"]["message"])
        self.assertIn("säsonger status 403", down["sofa_model"]["message"])
        self.assertEqual([], self.by_kind(findings, "kalltest_stale"))

    def test_ett_enstaka_fel_ar_inget_larm(self):
        rows = [r for r in sofascore_runs() if not r["run_id"].startswith(
            ("2026-09-25T16", "2026-09-25T22"))]
        self.write(rows)
        self.assertEqual([], self.by_kind(vakt.check_kallor(self.ctx()), "kalla_nere"))

    def test_eget_natfel_ar_natverk_nere_och_bryter_inte_kallserien(self):
        rows = sofascore_runs()
        for run_at in ("2026-09-26T04:43:00Z", "2026-09-26T10:43:00Z"):
            run_id = f"{run_at}-dns00000"
            for source in ("svenskaspel", "pinnacle", "sofa_model", "sofa_live"):
                rows.append(kalltest_row(
                    run_id, run_at, source, False,
                    "ConnectError: [Errno 8] nodename nor servname provided, or not known",
                    infra="dns"))
        self.write(rows)
        findings = vakt.check_kallor(self.ctx(now=t("2026-09-26T11:00:00Z")))
        network = self.by_kind(findings, "natverk_nere")
        self.assertEqual(1, len(network))
        self.assertEqual("error", network[0]["level"])  # två körningar i rad
        self.assertEqual("2026-09-26T04:43:00Z", network[0]["since"])
        # DNS-raderna är ingen observation av källan: Sofascores serie står kvar
        # och svenskaspel/pinnacle blir inte "nere" av vårt eget nät.
        self.assertEqual({"sofa_model", "sofa_live"},
                         {f["key"] for f in self.by_kind(findings, "kalla_nere")})

    def test_gammal_eller_saknad_logg_ar_kalltest_stale(self):
        self.assertEqual(["kalltest_stale"],
                         [f["kind"] for f in vakt.check_kallor(self.ctx())])
        self.write(sofascore_runs())
        late = vakt.check_kallor(self.ctx(now=t("2026-09-26T11:00:00Z")))
        self.assertEqual(1, len(self.by_kind(late, "kalltest_stale")))
        self.assertIn("gräns 12 h", self.by_kind(late, "kalltest_stale")[0]["message"])


class SinceAndCrashTests(Base):
    def test_since_bars_over_och_last_seen_flyttas(self):
        low = lambda _path: Usage(100 * GB, 92 * GB, 8 * GB)  # noqa: E731
        first = self.run_vakt((("server", "server", vakt.check_server),), disk_usage=low)
        later = self.run_vakt((("server", "server", vakt.check_server),),
                              now=self.NOW + dt.timedelta(minutes=30), disk_usage=low)
        f1, f2 = first["findings"][0], later["findings"][0]
        self.assertEqual(("disk_lag", "warning"), (f2["kind"], f2["level"]))
        self.assertEqual(f1["since"], f2["since"])
        self.assertEqual("2026-09-26T00:30:00Z", f2["last_seen"])
        tiny = self.run_vakt((("server", "server", vakt.check_server),),
                             disk_usage=lambda _p: Usage(100 * GB, 98 * GB, 2 * GB))
        self.assertEqual("error", tiny["findings"][0]["level"])
        healthy = self.run_vakt((("server", "server", vakt.check_server),),
                                disk_usage=lambda _p: Usage(100 * GB, 10 * GB, 90 * GB))
        self.assertEqual([], healthy["findings"])

    def test_kraschad_kontroll_faller_inte_de_andra_och_behaller_senaste_fynd(self):
        low = lambda _path: Usage(100 * GB, 92 * GB, 8 * GB)  # noqa: E731
        self.run_vakt((("server", "server", vakt.check_server),), disk_usage=low)

        def boom(_ctx):
            raise KeyError("trasig")

        calls = []

        def other(ctx):
            calls.append(ctx.now)
            return [vakt._finding("warning", "drift", "opushade_commits", "origin", "x")]

        status = self.run_vakt((("server", "server", boom), ("drift", "drift", other)),
                               now=self.NOW + dt.timedelta(minutes=30))
        self.assertEqual(1, len(calls))
        failed = self.by_kind(status["findings"], "vakt_check_failed")
        self.assertEqual(["server"], [f["key"] for f in failed])
        self.assertIn("KeyError", failed[0]["message"])
        self.assertFalse(status["checks"]["server"]["ok"])
        self.assertTrue(status["checks"]["drift"]["ok"])
        carried = self.by_kind(status["findings"], "disk_lag")
        self.assertEqual(1, len(carried))
        self.assertTrue(carried[0]["carried"])
        self.assertEqual(1, len(self.by_kind(status["findings"], "opushade_commits")))
        log = (self.status_dir / vakt.LOG_FILE).read_text().splitlines()
        self.assertEqual(2, len(log))  # EN rad per körning
        self.assertEqual(["server"], json.loads(log[-1])["failed_checks"])


class BackendLogTests(Base):
    CHECKS = (("backend", "backend", vakt.check_backend),)

    def access(self, path: str, status: int) -> str:
        reason = "Internal Server Error" if status >= 500 else "OK"
        return f'INFO:     127.0.0.1:5{status} - "GET {path} HTTP/1.1" {status} {reason}\n'

    def append(self, name: str, text: str):
        with (self.data / name).open("a", encoding="utf-8") as handle:
            handle.write(text)

    def test_offset_laser_bara_nytt_over_tva_korningar_och_rotation(self):
        self.append(vakt.BACKEND_OUT_LOG, self.access("/api/draws?product=x&_t=1", 500) * 2
                    + self.access("/api/health", 200) * 3)
        first = self.run_vakt(self.CHECKS)
        self.assertEqual([], first["findings"])  # 2 < 5 totalt, 2 < 3 per endpoint
        size = (self.data / vakt.BACKEND_OUT_LOG).stat().st_size
        self.assertEqual(size, first["state"]["backend_log"]["out"]["offset"])

        self.append(vakt.BACKEND_OUT_LOG,
                    self.access("/api/draws?product=y&_t=2", 500) * 3
                    + self.access("/api/payouts?draw=1", 502))
        second = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(minutes=30))
        found = self.by_kind(second["findings"], "backend_5xx")
        self.assertEqual(1, len(found))
        # Bara de NYA raderna: 4, inte 6 — och querysträngen är borta.
        self.assertEqual(4, found[0]["n"])
        self.assertEqual({"GET /api/draws": 3, "GET /api/payouts": 1}, found[0]["endpoints"])
        self.assertIn("sedan förra kontrollen", found[0]["message"])
        self.assertEqual("2026-09-26T00:30:00Z", found[0]["since"])

        third = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(hours=1))
        held = self.by_kind(third["findings"], "backend_5xx")
        self.assertTrue(held[0]["held"])
        self.assertEqual("2026-09-26T00:30:00Z", held[0]["since"])
        gone = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(hours=26))
        self.assertEqual([], self.by_kind(gone["findings"], "backend_5xx"))

        # Roterad (krympt) fil läses från början.
        (self.data / vakt.BACKEND_OUT_LOG).write_text(
            self.access("/api/system", 500) * 5, encoding="utf-8")
        rotated = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(hours=27))
        found = self.by_kind(rotated["findings"], "backend_5xx")
        self.assertEqual(5, found[0]["n"])
        self.assertIn("roterades", found[0]["message"])

    def test_forsta_lasningen_tar_bara_slutet_och_halls_inte_kvar(self):
        self.append(vakt.BACKEND_OUT_LOG, self.access("/api/gammal", 500) * 50
                    + self.access("/api/ny", 500) * 6)
        # 6 nya rader à 76 byte + 14 byte av en gammal rad som ska kapas bort.
        with mock.patch.object(vakt, "FIRST_READ_MAX_BYTES", 6 * 76 + 14):
            status = self.run_vakt(self.CHECKS)
        found = self.by_kind(status["findings"], "backend_5xx")[0]
        self.assertNotIn("GET /api/gammal", found["endpoints"])
        self.assertEqual({"GET /api/ny": 6}, found["endpoints"])
        self.assertIn("första läsning", found["message"])
        self.assertNotIn("hold_h", found)
        later = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(minutes=30))
        self.assertEqual([], later["findings"])

    def test_traceback_kedja_raknas_en_gang_och_natfel_blir_natverk_nere(self):
        chain = (
            "INFO:     Started server process [1]\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1, in f\n'
            "    raise X\n"
            "httpcore.ConnectError: [Errno 8] nodename nor servname provided, or not known\n"
            "\n"
            "The above exception was the direct cause of the following exception:\n"
            "\n"
            "Traceback (most recent call last):\n"
            '  File "y.py", line 2, in g\n'
            "    ~~~~^^\n"
            "httpx.ConnectError: [Errno 8] nodename nor servname provided, or not known\n")
        bug = ("ERROR:    Exception in ASGI application\n"
               "Traceback (most recent call last):\n"
               '  File "app/main.py", line 9, in h\n'
               "NameError: name 'pool_system_ledger' is not defined\n")
        self.append(vakt.BACKEND_ERR_LOG, chain)
        first = self.run_vakt(self.CHECKS)
        network = self.by_kind(first["findings"], "natverk_nere")
        self.assertEqual(1, network[0]["n"])  # kedjan är EN händelse
        self.assertEqual([], self.by_kind(first["findings"], "backend_traceback"))
        self.append(vakt.BACKEND_ERR_LOG, bug)
        second = self.run_vakt(self.CHECKS, now=self.NOW + dt.timedelta(minutes=30))
        tracebacks = self.by_kind(second["findings"], "backend_traceback")
        self.assertEqual(1, tracebacks[0]["n"])
        self.assertIn("NameError", tracebacks[0]["message"])
        self.assertEqual(24, tracebacks[0]["hold_h"])


class JobbTests(Base):
    def test_ej_laddat_nere_och_exit(self):
        rows = dict(HEALTHY, backend=("-", "-15"), kalltest=("-", "1"))
        rows.pop("vakt")
        runner = FakeRunner(launchctl_list=launchctl_rows(**rows),
                            disabled='\t"com.saman.spelkompisen.backup" => enabled\n')
        findings = {f["kind"] + ":" + f["key"]: f for f in vakt.check_jobb(self.ctx(runner=runner))}
        self.assertEqual({"jobb_nere:backend", "jobb_exit:kalltest", "jobb_ej_laddat:vakt"},
                         set(findings))
        self.assertEqual("error", findings["jobb_nere:backend"]["level"])
        self.assertEqual("error", findings["jobb_ej_laddat:vakt"]["level"])
        self.assertEqual("warning", findings["jobb_exit:kalltest"]["level"])
        self.assertIn("källa nere", findings["jobb_exit:kalltest"]["message"])

    def test_avstangd_tjanst_ar_varning_och_friskt_lage_ar_tyst(self):
        rows = dict(HEALTHY)
        rows.pop("backup")
        runner = FakeRunner(launchctl_list=launchctl_rows(**rows),
                            disabled='\t"com.saman.spelkompisen.backup" => disabled\n')
        findings = vakt.check_jobb(self.ctx(runner=runner))
        self.assertEqual([("jobb_ej_laddat", "backup", "warning")],
                         [(f["kind"], f["key"], f["level"]) for f in findings])
        runner = FakeRunner(launchctl_list=launchctl_rows(**HEALTHY))
        self.assertEqual([], vakt.check_jobb(self.ctx(runner=runner)))


class InsamlingTests(Base):
    def db(self, capture_at: str, health_at: str, close: str = "2026-09-27T12:00:00Z"):
        store = Storage(self.data / "stryktips.db")
        try:
            store.conn.execute("INSERT OR REPLACE INTO draws VALUES ('stryktipset', 1, 'Open', ?)",
                               (close,))
            store.conn.execute(
                "INSERT INTO pool_market_capture VALUES ('stryktipset', 1, 'sharp', 1, ?, "
                "'matched', 1, 0)", (capture_at,))
            for scope, at in (("1x2", health_at), ("live", "2026-09-25T23:59:00Z")):
                store.conn.execute(
                    "INSERT OR IGNORE INTO oddset_source_health_log "
                    "VALUES ('pinnacle', 'x', ?, ?, 1, 3, NULL)",
                    (scope, at))
            store.conn.commit()
        finally:
            store.close()

    def test_append_only_tabeller_bevisar_liv(self):
        # +02:00 och mikrosekunder: tider jämförs som tider, aldrig som text.
        self.db("2026-09-26T01:30:00.123456+02:00", "2026-09-25T23:40:00Z")
        self.assertEqual([], vakt.check_insamling(self.ctx()))
        self.db("2026-09-25T21:00:00Z", "2026-09-25T22:00:00Z")  # äldre rader till
        self.assertEqual([], vakt.check_insamling(self.ctx()))

    def test_tyst_insamling_ger_insamling_star_still(self):
        self.db("2026-09-25T22:00:00Z", "2026-09-25T22:10:00Z")
        findings = vakt.check_insamling(self.ctx())
        self.assertEqual({"pool", "oddset"}, {f["key"] for f in findings})
        self.assertTrue(all(f["level"] == "error" for f in findings))
        self.assertIn("120 min", next(f for f in findings if f["key"] == "pool")["message"])

    def test_utan_oppen_omgang_larmar_inte_poolen(self):
        self.db("2026-09-25T22:00:00Z", "2026-09-25T23:50:00Z", close="2026-09-25T12:00:00Z")
        self.assertEqual([], vakt.check_insamling(self.ctx()))

    def test_databasen_oppnas_skrivskyddad(self):
        self.db("2026-09-25T23:30:00Z", "2026-09-25T23:40:00Z")
        store = Storage(self.data / "stryktips.db", read_only=True)
        try:
            self.assertEqual(1, store.conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0])
            with self.assertRaises(sqlite3.OperationalError):
                store.conn.execute("DELETE FROM draws")
        finally:
            store.close()
        with self.assertRaises(sqlite3.OperationalError):
            Storage(self.root / "finns-inte" / "x.db", read_only=True)
        self.assertFalse((self.root / "finns-inte").exists())


class DriftTests(Base):
    def runner(self, extra: dict | None = None) -> FakeRunner:
        base = {
            ("log", "-1", "--format=%ct %h %s", "--", "backend/app"):
                (0, f"{int(t('2026-09-25T23:00:00Z').timestamp())} abc1234 Rätta krasch\n", ""),
            ("log", "-1", "--format=%ct %h %s", "--", "frontend/src"):
                (0, f"{int(t('2026-09-25T20:00:00Z').timestamp())} def5678 Ny vy\n", ""),
            ("fetch",): (128, "", "fatal: unable to access"),
            ("rev-list",): (0, "0\t2\n", ""),
            ("rev-parse",): (0, "main\n", ""),
            ("status",): (0, " M backend/app/main.py\n", ""),
        }
        base.update(extra or {})
        return FakeRunner(launchctl_list=launchctl_rows(**HEALTHY), git=base,
                          ps="   1-02:00:00\n")  # startad 2026-09-24T22:00Z

    def test_gammal_kod_obyggd_app_efter_github_och_ocommittat(self):
        dist = self.repo / "frontend" / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<html>")
        built = t("2026-09-25T19:00:00Z").timestamp()
        os.utime(dist / "index.html", (built, built))
        ctx = self.ctx(runner=self.runner())
        findings = {f["kind"]: f for f in vakt.check_drift(ctx)}
        self.assertEqual({"backend_kor_gammal_kod", "appen_ej_byggd", "main_ej_utcheckad",
                          "ocommittat_i_driftkopian"}, set(findings))
        self.assertIn("2026-09-24T22:00:00Z", findings["backend_kor_gammal_kod"]["message"])
        self.assertIn("2 commit", findings["main_ej_utcheckad"]["message"])
        self.assertIn("backend/app/main.py", findings["ocommittat_i_driftkopian"]["message"])
        self.assertTrue(ctx.summary["drift"]["fetch"].startswith("misslyckades"))
        status_call = ctx.run.git_calls("status")[0]
        self.assertIn("--no-optional-locks", status_call)
        self.assertIn("--untracked-files=no", status_call)

    def test_omstart_strax_fore_commit_och_ingen_fetch(self):
        # Startad 23:00:01Z, commit 23:00:00Z: inom marginalen, inget larm.
        runner = self.runner({("rev-list",): (0, "1\t0\n", ""), ("status",): (0, "", "")})
        runner.ps = "59:59"  # startad 2026-09-25T23:00:01Z
        ctx = self.ctx(runner=runner, fetch=False)
        findings = {f["kind"] for f in vakt.check_drift(ctx)}
        self.assertEqual({"opushade_commits", "appen_ej_byggd"}, findings)
        self.assertEqual([], runner.git_calls("fetch"))
        self.assertEqual("avstängd", ctx.summary["drift"]["fetch"])

    def test_etime(self):
        self.assertEqual(59, vakt._etime_seconds("00:59"))
        self.assertEqual(3600 + 61, vakt._etime_seconds("01:01:01"))
        self.assertEqual(86400 + 14 * 3600 + 24 * 60 + 22, vakt._etime_seconds(" 01-14:24:22\n"))


class TesterTests(Base):
    def test_dygnsgrans_ar_03_svensk_tid(self):
        # 02:30 svensk sommartid hör till föregående testdygn, 03:30 till dagens.
        self.assertEqual(t("2026-09-30T01:00:00Z"), vakt.test_day_start(t("2026-10-01T00:30:00Z")))
        self.assertEqual(t("2026-10-01T01:00:00Z"), vakt.test_day_start(t("2026-10-01T01:30:00Z")))
        self.assertEqual(t("2026-12-01T02:00:00Z"), vakt.test_day_start(t("2026-12-01T02:30:00Z")))

    def test_rod_svit_ger_tester_roda_och_worktreen_tas_alltid_bort(self):
        red = (1, "→ backendtester\nFAIL: test_x (tests.test_a.T)\n\n== kontroll ==\n"
                  "✗ backendtester\n✓ frontendlint\nSTOPP — rätta innan push\n", "")
        runner = FakeRunner(kontroll=red, git={("rev-parse",): (0, "72f9ebf\n", "")})
        now = t("2026-10-01T01:30:00Z")
        status = self.run_vakt((("tester", "tester", vakt.check_tester),), now=now,
                               runner=runner)
        finding = self.by_kind(status["findings"], "tester_roda")[0]
        self.assertEqual("error", finding["level"])
        self.assertIn("FAIL: test_x", finding["message"])
        self.assertEqual("2026-10-01T01:30:00Z", finding["since"])
        self.assertIn("✗ backendtester", status["state"]["tests"]["summary"])
        self.assertEqual(1, len(runner.git_calls("worktree", "add")))
        self.assertEqual(1, len(runner.git_calls("worktree", "remove")))
        kontroll = [c for c in runner.calls if c[0] == "/bin/bash"]
        self.assertEqual(1, len(kontroll))
        self.assertNotEqual(str(self.repo / "tools" / "kontroll.sh"), kontroll[0][1])

        # Samma testdygn: inte igen. Fyndet och dess since står kvar.
        again = self.run_vakt((("tester", "tester", vakt.check_tester),),
                              now=now + dt.timedelta(hours=5), runner=runner)
        self.assertEqual(1, len([c for c in runner.calls if c[0] == "/bin/bash"]))
        self.assertEqual("2026-10-01T01:30:00Z",
                         self.by_kind(again["findings"], "tester_roda")[0]["since"])
        # Nästa natt, fortfarande röd: serien behåller sin första röda körning.
        night = self.run_vakt((("tester", "tester", vakt.check_tester),),
                              now=now + dt.timedelta(days=1), runner=runner)
        self.assertEqual("2026-10-01T01:30:00Z",
                         self.by_kind(night["findings"], "tester_roda")[0]["since"])
        # Grön natt: fyndet försvinner.
        runner.kontroll = (0, "== kontroll ==\n✓ backendtester\nALLT GRÖNT\n", "")
        green = self.run_vakt((("tester", "tester", vakt.check_tester),),
                              now=now + dt.timedelta(days=2), runner=runner)
        self.assertEqual([], green["findings"])
        self.assertTrue(green["checks"]["tester"]["green"])

    def test_misslyckad_worktree_ar_rod_och_stadas(self):
        runner = FakeRunner(git={("worktree", "add"): (128, "", "fatal: låst")})
        status = self.run_vakt((("tester", "tester", vakt.check_tester),),
                               now=t("2026-10-01T01:30:00Z"), runner=runner, tests=True)
        finding = self.by_kind(status["findings"], "tester_roda")[0]
        self.assertIn("git worktree add", finding["message"])
        self.assertEqual(1, len(runner.git_calls("worktree", "remove")))
        self.assertEqual([], [c for c in runner.calls if c[0] == "/bin/bash"])

    def test_fore_0300_och_utan_tester_kors_inget(self):
        runner = FakeRunner()
        self.run_vakt((("tester", "tester", vakt.check_tester),),
                      now=t("2026-10-01T01:30:00Z"), runner=runner, tests=False)
        self.assertEqual([], runner.calls)


class ExperimentTests(Base):
    def catalog(self, status: str, n: int, krav: int = 40):
        def load(_ctx):
            return {"tests": [{"id": "total", "title": "Ö/U-totalen", "status": status,
                               "progress": {"n": n, "krav": krav, "namn": "total · m20"}},
                              {"id": "poolopt", "title": "Optimerare 256", "status": "samlar",
                               "progress": {"n": 62, "krav": 40, "namn": "balans"}}]}
        return load

    def check(self, status, n, now):
        return lambda ctx: vakt.check_experiment(ctx, catalog=self.catalog(status, n))

    def test_statusbyte_och_avlasningspunkt_ar_info_i_sju_dygn(self):
        first = self.run_vakt((("experiment", "experiment", self.check("samlar", 39, None)),))
        self.assertEqual([], first["findings"])  # baslinje; poolopt 62/40 noteras inte
        crossed = self.run_vakt((("experiment", "experiment", self.check("samlar", 40, None)),),
                                now=self.NOW + dt.timedelta(minutes=30))
        self.assertEqual([("info", "avlasningspunkt_nadd", "total")],
                         [(f["level"], f["kind"], f["key"]) for f in crossed["findings"]])
        changed = self.run_vakt(
            (("experiment", "experiment", self.check("underlag klart", 41, None)),),
            now=self.NOW + dt.timedelta(hours=1))
        kinds = {f["kind"]: f for f in changed["findings"]}
        self.assertEqual({"avlasningspunkt_nadd", "test_status_andrad"}, set(kinds))
        self.assertTrue(kinds["avlasningspunkt_nadd"]["held"])
        self.assertIn("samlar → underlag klart", kinds["test_status_andrad"]["message"])
        week = self.run_vakt(
            (("experiment", "experiment", self.check("underlag klart", 41, None)),),
            now=self.NOW + dt.timedelta(days=7, hours=2))
        self.assertEqual([], week["findings"])

    def test_katalogen_lases_skrivskyddat_och_main_aterstalls(self):
        from app import main as main_mod
        Storage(self.data / "stryktips.db").close()
        original = main_mod.Storage
        with vakt._main_storage_read_only(self.data / "stryktips.db"):
            store = main_mod.Storage()
            try:
                self.assertTrue(store.read_only)
            finally:
                store.close()
        self.assertIs(original, main_mod.Storage)


class PoolHealthVaktTests(Base):
    def health(self, status=None, now=None):
        path = self.status_dir / vakt.STATUS_FILE
        if status is not None:
            self.status_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(status), encoding="utf-8")
        store = Storage(self.data / "t.db")
        try:
            return pool_health.report(store, now=now or self.NOW, products=(),
                                      vakt_status_path=path)
        finally:
            store.close()

    def status(self, checked_at: str) -> dict:
        return {"version": "vakt-v1", "checked_at": checked_at, "findings": [
            {"level": "error", "area": "kallor", "kind": "kalla_nere", "key": "sofa_model",
             "message": "sofa_model har fallerat i 3 källprov i rad: status 403",
             "since": "2026-09-25T10:43:18Z"},
            {"level": "warning", "area": "backend", "kind": "backend_5xx", "key": "access",
             "message": "6 serverfel", "since": "2026-09-25T23:30:00Z", "held": True},
            {"level": "info", "area": "experiment", "kind": "test_status_andrad",
             "key": "total:samlar->underlag klart", "message": "Ö/U-totalen: samlar → underlag klart",
             "since": "2026-09-25T23:00:00Z"}]}

    def test_fel_och_varningar_blir_server_issues_men_info_blir_notes(self):
        payload = self.health(self.status("2026-09-25T23:45:00Z"))
        issues = {i["kind"]: i for i in payload["issues"]}
        self.assertEqual({"kalla_nere", "backend_5xx"}, set(issues))
        self.assertEqual("server", issues["kalla_nere"]["product"])
        self.assertEqual("error", issues["kalla_nere"]["level"])
        self.assertEqual("2026-09-25T10:43:18Z", issues["kalla_nere"]["since"])
        self.assertTrue(issues["backend_5xx"]["held"])
        self.assertEqual("error", payload["status"])
        self.assertNotIn("test_status_andrad", issues)
        self.assertEqual(["test_status_andrad"], [n["kind"] for n in payload["vakt"]["notes"]])
        self.assertEqual("2026-09-25T23:45:00Z", payload["vakt"]["checked_at"])

    def test_gammal_saknad_och_trasig_status_varnar(self):
        missing = self.health()
        self.assertEqual(["vakt_missing"], [i["kind"] for i in missing["issues"]])
        self.assertIsNone(missing["vakt"])
        stale = self.health(self.status("2026-09-25T22:00:00Z"))
        kinds = [i["kind"] for i in stale["issues"]]
        self.assertIn("vakt_stale", kinds)
        self.assertIn("kalla_nere", kinds)  # senaste kända fynd visas ändå
        (self.status_dir / vakt.STATUS_FILE).write_text("{trasig")
        self.assertEqual(["vakt_unreadable"], [i["kind"] for i in self.health()["issues"]])

    def test_utan_sokvag_ingen_vakt(self):
        store = Storage(self.data / "t.db")
        try:
            payload = pool_health.report(store, now=self.NOW, products=())
        finally:
            store.close()
        self.assertNotIn("vakt", payload)
        self.assertEqual([], payload["issues"])

    def test_samma_sokvag_som_vakten_skriver(self):
        self.assertEqual(vakt.default_status_path(), pool_health.VAKT_STATUS_PATH)
        with mock.patch.dict(os.environ, {vakt.STATUS_DIR_ENV: str(self.status_dir)}):
            self.assertEqual(self.status_dir / "vakt.json", vakt.default_status_path())


class WriteStatusTests(Base):
    def test_atomisk_skrivning_och_en_loggrad_per_korning(self):
        status = self.run_vakt(())
        self.assertEqual("vakt-v1", status["version"])
        on_disk = json.loads((self.status_dir / vakt.STATUS_FILE).read_text())
        self.assertEqual(status["checked_at"], on_disk["checked_at"])
        self.assertEqual([], [p.name for p in self.status_dir.iterdir()
                              if p.name.endswith(".tmp")])
        self.run_vakt((), now=self.NOW + dt.timedelta(minutes=30))
        self.assertEqual(2, len((self.status_dir / vakt.LOG_FILE).read_text().splitlines()))


class TjansterTests(unittest.TestCase):
    def test_vakten_ar_registrerad_som_schemalagd_servertjanst(self):
        tools = Path(__file__).resolve().parents[2] / "tools"
        sys.path.insert(0, str(tools))
        import spelkompisen_tjanster as tjanster
        service = tjanster.BY_KEY["vakt"]
        self.assertEqual("com.saman.spelkompisen.vakt", service.label)
        self.assertEqual("Server & övervakning", service.project)
        self.assertTrue(service.scheduled)
        plist = (Path(__file__).resolve().parents[1] / "scripts"
                 / "com.saman.spelkompisen.vakt.plist").read_text()
        self.assertIn("<integer>1800</integer>", plist)
        self.assertIn("<string>vakt</string>", plist)
        for key, _keep_alive in vakt.JOBS:
            self.assertIn(key, tjanster.BY_KEY)


if __name__ == "__main__":
    unittest.main()
