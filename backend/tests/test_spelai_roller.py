"""Rollkörningar (fas F): due-ordning, gränser, paus, kvot, tolkning, en rad per körning.

Klockan och köraren injiceras — `claude` körs aldrig. Den riktiga köraren
provas bara mot ett falskt `claude`-skript i en temporär katalog.
"""
import contextlib
import datetime as dt
import fcntl
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, iso, ny_store  # noqa: E402
from app.spelai import roller, tillstand  # noqa: E402

UTC = dt.timezone.utc
# Söndag 2026-10-04 12:00 svensk tid (CEST = UTC+2).
SONDAG_12 = dt.datetime(2026, 10, 4, 10, 0, tzinfo=UTC)
TORSDAG = dt.datetime(2026, 10, 1, 4, 59, tzinfo=UTC)     # 06:59 svensk tid


def svar_json(result="Klart.\nSAMMANFATTNING: Allt grönt, inga larm.", **extra):
    data = {"type": "result", "subtype": "success", "is_error": False,
            "num_turns": 7, "result": result, "total_cost_usd": 0.42,
            "session_id": "s-1", "usage": {"input_tokens": 10, "output_tokens": 20}}
    data.update(extra)
    return {"returncode": 0, "stdout": json.dumps(data), "stderr": "", "timed_out": False}


class Klocka:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def fram(self, **kw):
        self.t += dt.timedelta(**kw)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn
        self.vakt = self.root / "vakt.json"
        self.agent_data = self.root / "spel-ai-data"
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def runner(self, svar=None):
        def kor(post):
            self.calls.append(post)
            return svar if svar is not None else svar_json()
        return kor

    def due(self, now):
        return roller.due(self.conn, now, vakt_path=self.vakt, agent_data=self.agent_data)

    def uppgifter(self, now):
        return [p["uppgift"] for p in self.due(now)]

    def forslag(self, *, frozen, agent_hash="h-std", product="stryktipset",
                number=4973, horizon="30m", levels=(256, 512), agent_status="fryst"):
        close = frozen + dt.timedelta(minutes=30)
        for level in levels:
            for role, status, rows_hash in (("standard", "fryst", f"h-std-{level}"),
                                            ("agent", agent_status,
                                             f"{agent_hash}-{level}" if level == levels[-1]
                                             else f"h-std-{level}")):
                self.conn.execute(
                    "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                    "horizon, role, status, rows_hash, reg_close_time, frozen_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (product, number, level, horizon, role, status, rows_hash,
                     iso(close), iso(frozen)))
        self.conn.commit()

    def vaktfel(self, *findings):
        self.vakt.write_text(json.dumps({"findings": list(findings)}), encoding="utf-8")

    def korning(self, task, started, role="driften", status="klar"):
        self.conn.execute(
            "INSERT INTO spelai_run (role, task, started_at, ended_at, status, model, "
            "recorded_at) VALUES (?,?,?,?,?,?,?)",
            (role, task, iso(started), iso(started), status, "sonnet", iso(started)))
        self.conn.commit()


class DueTests(Base):
    def test_prioritetsordning_och_falt(self):
        self.forslag(frozen=SONDAG_12 - dt.timedelta(minutes=40), agent_hash="h-agent")
        self.vaktfel({"level": "error", "kind": "kalla_nere", "key": "pinnacle",
                      "message": "pinnacle 403", "since": iso(SONDAG_12 - dt.timedelta(hours=1))})
        poster = self.due(SONDAG_12)
        self.assertEqual(["motivering:stryktipset:4973:30m", "larm:kalla_nere:pinnacle",
                          "morgonrunda:2026-10-04", "forskningspass:2026-10-04",
                          "veckogenomgang:2026-W40"], [p["uppgift"] for p in poster])
        typer = {p["uppgift"].split(":")[0]: p for p in poster}
        self.assertEqual(("forskaren", "sonnet", 600, 25),
                         tuple(typer["motivering"][k] for k in
                               ("roll", "model", "timeout_s", "max_turns")))
        self.assertEqual(("driften", "sonnet", 1200, 40),
                         tuple(typer["larm"][k] for k in ("roll", "model", "timeout_s", "max_turns")))
        self.assertEqual(("driften", "sonnet", 1200, 40),
                         tuple(typer["morgonrunda"][k] for k in
                               ("roll", "model", "timeout_s", "max_turns")))
        self.assertEqual(("forskaren", "opus", 2400, 80),
                         tuple(typer["forskningspass"][k] for k in
                               ("roll", "model", "timeout_s", "max_turns")))
        self.assertEqual(("anvandaren", "sonnet", 900, 30),
                         tuple(typer["veckogenomgang"][k] for k in
                               ("roll", "model", "timeout_s", "max_turns")))
        self.assertEqual({"motivering": "medium", "larm": "medium", "morgonrunda": "medium",
                          "forskningspass": "high", "veckogenomgang": "medium"},
                         {typ: post["effort"] for typ, post in typer.items()})
        for post in poster:
            self.assertIn("SAMMANFATTNING:", post["prompt"])
            self.assertIn("12:00 svensk tid", post["prompt"])     # klockan injiceras
            self.assertFalse(post["prompt"].startswith("-"))
        self.assertIn("pinnacle 403", typer["larm"]["prompt"])
        self.assertIn("motiveringar/stryktipset-4973-30m.md", typer["motivering"]["prompt"])
        self.assertIn("120 ord", typer["motivering"]["prompt"])
        self.assertIn("512 kr", typer["motivering"]["prompt"])
        self.assertIn("agent/journal.md", typer["morgonrunda"]["prompt"])
        self.assertIn("mode=ro", typer["morgonrunda"]["prompt"])
        self.assertIn("skarmbilder/2026-10-04/", typer["veckogenomgang"]["prompt"])
        self.assertIn("forslag_forbattring", typer["veckogenomgang"]["prompt"])
        self.assertEqual("2026-10-04", typer["veckogenomgang"]["skarmbilder"])

    def test_dygnsgranser_i_svensk_tid(self):
        self.assertEqual([], self.uppgifter(TORSDAG))                       # 06:59
        self.assertEqual(["morgonrunda:2026-10-01"],
                         self.uppgifter(TORSDAG + dt.timedelta(minutes=1)))   # 07:00
        tio = dt.datetime(2026, 10, 1, 8, 0, tzinfo=UTC)                      # 10:00
        self.assertEqual(["morgonrunda:2026-10-01", "forskningspass:2026-10-01"],
                         self.uppgifter(tio))
        sent = dt.datetime(2026, 10, 1, 19, 59, tzinfo=UTC)                   # 21:59
        self.assertEqual(2, len(self.uppgifter(sent)))
        self.assertEqual([], self.uppgifter(sent + dt.timedelta(minutes=1)))  # 22:00
        # en per dygn: efter körningen inget mer i dag, men i morgon igen
        self.korning("morgonrunda:2026-10-01", tio)
        self.assertEqual(["forskningspass:2026-10-01"], self.uppgifter(tio))
        imorgon = tio + dt.timedelta(days=1)
        self.assertEqual(["morgonrunda:2026-10-02", "forskningspass:2026-10-02"],
                         self.uppgifter(imorgon))

    def test_dygnet_ar_svenskt_inte_utc(self):
        # 23:30Z = 01:30 svensk tid nästa dag: utanför fönstret, och dagnyckeln
        # följer svensk kalender.
        sen = dt.datetime(2026, 10, 1, 23, 30, tzinfo=UTC)
        self.assertEqual([], self.uppgifter(sen))
        morgon = dt.datetime(2026, 10, 2, 5, 0, tzinfo=UTC)                   # 07:00
        self.assertEqual(["morgonrunda:2026-10-02"], self.uppgifter(morgon))

    def test_veckogranser(self):
        lordag = SONDAG_12 - dt.timedelta(days=1)
        self.assertNotIn("veckogenomgang", " ".join(self.uppgifter(lordag)))
        tidig = dt.datetime(2026, 10, 4, 8, 59, tzinfo=UTC)                   # sön 10:59
        self.assertNotIn("veckogenomgang:2026-W40", self.uppgifter(tidig))
        self.assertIn("veckogenomgang:2026-W40",
                      self.uppgifter(tidig + dt.timedelta(minutes=1)))        # 11:00
        self.assertNotIn("veckogenomgang:2026-W40",
                         self.uppgifter(dt.datetime(2026, 10, 4, 20, 0, tzinfo=UTC)))
        roller.run(self.conn, self.due(SONDAG_12)[-1], runner=self.runner(),
                   now_fn=lambda: SONDAG_12)
        self.assertNotIn("veckogenomgang:2026-W40",
                         self.uppgifter(SONDAG_12 + dt.timedelta(hours=2)))
        self.assertIn("veckogenomgang:2026-W41",
                      self.uppgifter(SONDAG_12 + dt.timedelta(days=7)))

    def test_paus_och_pagaende_korning(self):
        tillstand.satt_paus(self.conn, True, source="test", now=SONDAG_12)
        self.assertEqual([], self.due(SONDAG_12))
        tillstand.satt_paus(self.conn, False, source="test", now=SONDAG_12)
        self.assertEqual(5 - 2, len(self.due(SONDAG_12)))     # morgon, forskning, vecka
        lock_path = self.root / "roller.lock"
        with open(lock_path, "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual([], roller.due(self.conn, SONDAG_12, lock_path=lock_path))
        self.assertEqual(3, len(roller.due(self.conn, SONDAG_12, lock_path=lock_path)))

    def test_kvot_slut_loggas_en_gang_per_dygn(self):
        tio = dt.datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        for i in range(tillstand.STANDARD_KVOT):
            self.korning(f"motivering:x:{i}:30m", tio - dt.timedelta(minutes=i), "forskaren")
        self.assertEqual([], self.due(tio))
        self.assertEqual([], self.due(tio + dt.timedelta(minutes=5)))
        rows = self.conn.execute(
            "SELECT ref, detail_json FROM spelai_event WHERE kind='kvot_slut'").fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-10-01", rows[0][0])
        detail = json.loads(rows[0][1])
        self.assertEqual((8, 8), (detail["anvanda"], detail["tak"]))
        self.assertIn("morgonrunda:2026-10-01", detail["vantar"])
        # nästa svenska dygn: kvoten är ny
        self.assertTrue(self.due(tio + dt.timedelta(days=1)))

    def test_beslutat_tak_klipps_mot_absoluta_taket(self):
        now = dt.datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        self.conn.execute(
            "INSERT INTO spelai_inbox (external_id, typ, kalla, rubrik, varfor, "
            "alternativ_json, created_at, file_name, payload_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            ("k1", "beslut", "Koordinatorn", "Höj taket", "test",
             json.dumps([{"text": "50", "kvot": 50}]), iso(now), "k1.json", "h"))
        inbox_id = self.conn.execute("SELECT id FROM spelai_inbox").fetchone()[0]
        self.conn.execute(
            "INSERT INTO spelai_inbox_answer (inbox_id, val, kommentar, answered_at, "
            "user_agent, misstankt) VALUES (?,?,?,?,?,?)",
            (inbox_id, "0", None, iso(now), "Mozilla/5.0", 0))
        self.conn.commit()
        self.assertEqual(tillstand.MAX_KORNINGAR_ABS, tillstand.godkant_tak(self.conn)["tak"])
        for i in range(tillstand.MAX_KORNINGAR_ABS - 1):
            self.korning(f"motivering:x:{i}:30m", now, "forskaren")
        self.assertTrue(self.due(now))                       # 11 av 12
        self.korning("motivering:x:sista:30m", now, "forskaren")
        self.assertEqual([], self.due(now))                  # 12 av 12, aldrig 50

    def test_standard_v1_ger_ingen_motivering_men_avvikande_agent_gor(self):
        frozen = SONDAG_12 - dt.timedelta(minutes=30)
        self.forslag(frozen=frozen, agent_hash="h-std")          # agenten = standarden
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("motivering")])
        self.forslag(frozen=frozen, agent_hash="h-agent", horizon="6h", number=4974)
        self.assertEqual(["motivering:stryktipset:4974:6h"],
                         [u for u in self.uppgifter(SONDAG_12) if u.startswith("motivering")])
        # äldre än 2 h: ingen motivering
        self.assertFalse([u for u in self.uppgifter(frozen + dt.timedelta(hours=2, minutes=1))
                          if u.startswith("motivering")])

    def test_ogiltigt_agentforslag_ger_ingen_motivering(self):
        self.forslag(frozen=SONDAG_12 - dt.timedelta(minutes=10), agent_hash="h-agent",
                     agent_status="ogiltigt")
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("motivering")])

    def test_motivering_kors_en_gang(self):
        self.forslag(frozen=SONDAG_12 - dt.timedelta(minutes=10), agent_hash="h-agent")
        post = self.due(SONDAG_12)[0]
        self.assertEqual("motivering:stryktipset:4973:30m", post["uppgift"])
        roller.run(self.conn, post, runner=self.runner(), now_fn=lambda: SONDAG_12)
        self.assertNotIn("motivering:stryktipset:4973:30m", self.uppgifter(SONDAG_12))

    def test_larm_bara_efter_facit_start_och_hogst_tre_per_dygn(self):
        fore = iso(START - dt.timedelta(minutes=1))
        self.vaktfel(
            {"level": "error", "kind": "kalla_nere", "key": "sofa_live", "since": fore,
             "message": "gammalt"},
            {"level": "warning", "kind": "jobb_exit", "key": "kalltest",
             "since": iso(SONDAG_12)},
            *({"level": "error", "kind": "jobb_nere", "key": f"j{i}", "message": f"nere {i}",
               "since": iso(SONDAG_12 - dt.timedelta(minutes=10 - i))} for i in range(5)))
        larm = [u for u in self.uppgifter(SONDAG_12) if u.startswith("larm")]
        self.assertEqual(["larm:jobb_nere:j0", "larm:jobb_nere:j1", "larm:jobb_nere:j2"], larm)
        clock = Klocka(SONDAG_12)
        for _ in range(3):
            post = self.due(clock())[0]
            self.assertTrue(post["uppgift"].startswith("larm:"))
            roller.run(self.conn, post, runner=self.runner(), now_fn=clock)
            clock.fram(minutes=5)
        self.assertFalse([u for u in self.uppgifter(clock()) if u.startswith("larm")])
        # nästa dygn tar de två som återstår
        nasta = clock() + dt.timedelta(days=1)
        self.assertEqual(["larm:jobb_nere:j3", "larm:jobb_nere:j4"],
                         [u for u in self.uppgifter(nasta) if u.startswith("larm")])

    def test_samma_larm_igen_med_ny_starttid_ar_nytt(self):
        since = SONDAG_12 - dt.timedelta(minutes=5)
        self.vaktfel({"level": "error", "kind": "kalla_nere", "key": "x", "since": iso(since)})
        post = self.due(SONDAG_12)[0]
        roller.run(self.conn, post, runner=self.runner(), now_fn=lambda: SONDAG_12)
        self.assertNotIn("larm:kalla_nere:x", self.uppgifter(SONDAG_12))
        self.vaktfel({"level": "error", "kind": "kalla_nere", "key": "x",
                      "since": iso(SONDAG_12 + dt.timedelta(hours=1))})
        self.assertIn("larm:kalla_nere:x", self.uppgifter(SONDAG_12 + dt.timedelta(hours=2)))

    def test_larm_om_rollernas_eget_jobb_kor_ingen_roll(self):
        self.vaktfel({"level": "error", "kind": "jobb_ej_laddat", "key": "spelai-roller",
                      "since": iso(SONDAG_12 - dt.timedelta(minutes=5))})
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("larm")])

    def test_kant_fel_ger_ingen_larmkorning(self):
        self.vaktfel({"level": "error", "kind": "kalla_nere", "key": "sofa_live",
                      "since": iso(SONDAG_12 - dt.timedelta(minutes=5)),
                      "kand": {"beslut": "Beslut 20", "till": "2026-10-31"}})
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("larm")])

    def test_trasig_eller_saknad_vaktfil_ger_inga_larm(self):
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("larm")])
        self.vakt.write_text("{inte json", encoding="utf-8")
        self.assertFalse([u for u in self.uppgifter(SONDAG_12) if u.startswith("larm")])


class TolkningTests(unittest.TestCase):
    def test_sammanfattningsraden(self):
        text = "Gjorde X.\n\n**SAMMANFATTNING:** Två larm åtgärdade, rad 1X21X21X21X21 borta."
        self.assertEqual("Två larm åtgärdade, rad [rad] borta.", roller.sammanfattning(text))
        self.assertIsNone(roller.sammanfattning("ingen rad här"))
        lang = "SAMMANFATTNING: " + "a" * 400
        self.assertEqual(200, len(roller.sammanfattning(lang)))
        # den SISTA raden gäller
        self.assertEqual("två", roller.sammanfattning(
            "SAMMANFATTNING: ett\nmer text\nSAMMANFATTNING: två"))

    def test_klar_med_anvandning_och_kostnad(self):
        tolkat = roller.tolka(svar_json(), timeout_s=600)
        self.assertEqual("klar", tolkat["status"])
        self.assertEqual("Allt grönt, inga larm.", tolkat["note"])
        self.assertEqual(0.42, tolkat["cost_usd"])
        self.assertEqual({"input_tokens": 10, "output_tokens": 20}, tolkat["usage"]["usage"])
        self.assertEqual(7, tolkat["usage"]["num_turns"])

    def test_fel_varianter(self):
        self.assertEqual("fel", roller.tolka(svar_json(is_error=True), timeout_s=60)["status"])
        maxt = roller.tolka(svar_json(subtype="error_max_turns", result=""), timeout_s=60)
        self.assertEqual("fel", maxt["status"])
        self.assertIn("error_max_turns", maxt["note"])
        tomt = roller.tolka({"returncode": 1, "stdout": "", "stderr": "kraschade"},
                            timeout_s=60)
        self.assertEqual("fel", tomt["status"])
        self.assertIn("kraschade", tomt["note"])
        tid = roller.tolka({"returncode": -15, "stdout": "", "stderr": "",
                            "timed_out": True}, timeout_s=1200)
        self.assertEqual(("timeout", "timeout efter 20 min"), (tid["status"], tid["note"]))

    def test_utan_sammanfattning_ar_anda_klar(self):
        tolkat = roller.tolka(svar_json(result="Gjorde det."), timeout_s=60)
        self.assertEqual(("klar", "(ingen SAMMANFATTNING-rad)"),
                         (tolkat["status"], tolkat["note"]))

    def test_json_efter_annan_utskrift(self):
        svar = svar_json()
        svar["stdout"] = "varning: något\n" + svar["stdout"]
        self.assertEqual("klar", roller.tolka(svar, timeout_s=60)["status"])


class RunTests(Base):
    def post(self):
        return roller.due(self.conn, SONDAG_12)[0]          # morgonrunda

    def test_en_korning_ger_exakt_en_rad_och_en_handelse(self):
        clock = Klocka(SONDAG_12)

        def kor(post):
            clock.fram(minutes=12)
            return svar_json()
        post = self.post()
        rapport = roller.run(self.conn, post, runner=kor, now_fn=clock)
        self.assertEqual("klar", rapport["status"])
        rows = self.conn.execute(
            "SELECT role, task, started_at, ended_at, status, model, usage_json, cost_usd, "
            "note FROM spelai_run").fetchall()
        self.assertEqual(1, len(rows))
        role, task, started, ended, status, model, usage_json, cost, note = rows[0]
        self.assertEqual(("driften", "morgonrunda:2026-10-04", "klar", "sonnet"),
                         (role, task, status, model))
        self.assertEqual((iso(SONDAG_12), iso(SONDAG_12 + dt.timedelta(minutes=12))),
                         (started, ended))
        self.assertEqual(0.42, cost)
        self.assertEqual(7, json.loads(usage_json)["num_turns"])
        self.assertEqual("Allt grönt, inga larm.", note)
        kinds = [r[0] for r in self.conn.execute(
            "SELECT kind FROM spelai_event WHERE kind LIKE 'roll_%' ORDER BY id")]
        self.assertEqual(["roll_start", "roll_klar"], kinds)
        klar = json.loads(self.conn.execute(
            "SELECT detail_json FROM spelai_event WHERE kind='roll_klar'").fetchone()[0])
        self.assertEqual("Allt grönt, inga larm.", klar["sammanfattning"])
        # samma uppgift igen: hoppas över, ingen ny rad
        self.assertEqual("redan startad",
                         roller.run(self.conn, post, runner=kor, now_fn=clock).get("hoppad"))
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM spelai_run").fetchone()[0])

    def test_korare_som_kraschar_ger_en_fel_rad(self):
        def kor(_post):
            raise OSError("claude saknas")
        rapport = roller.run(self.conn, self.post(), runner=kor, now_fn=lambda: SONDAG_12)
        self.assertEqual("fel", rapport["status"])
        self.assertEqual([("fel",)], [tuple(r) for r in self.conn.execute(
            "SELECT status FROM spelai_run")])
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_event WHERE kind='roll_fel'").fetchone()[0])

    def test_sigterm_under_korningen_ger_fel_avbruten(self):
        svar = {"returncode": -15, "stdout": "", "stderr": "", "avbruten": True}
        roller.run(self.conn, self.post(), runner=self.runner(svar), now_fn=lambda: SONDAG_12)
        status, note = self.conn.execute("SELECT status, note FROM spelai_run").fetchone()
        self.assertEqual("fel", status)
        self.assertIn("avbruten", note)
        detail = json.loads(self.conn.execute(
            "SELECT detail_json FROM spelai_event WHERE kind='roll_fel'").fetchone()[0])
        self.assertTrue(detail["avbruten"])

    def test_timeout_ger_timeout_rad(self):
        svar = {"returncode": -15, "stdout": "", "stderr": "", "timed_out": True}
        roller.run(self.conn, self.post(), runner=self.runner(svar), now_fn=lambda: SONDAG_12)
        self.assertEqual([("timeout", "timeout efter 20 min")], [tuple(r) for r in self.conn.execute(
            "SELECT status, note FROM spelai_run")])

    def test_avbruten_process_far_sin_rad_i_efterhand(self):
        post = self.post()
        tillstand.logga(self.conn, "roll_start", post["uppgift"],
                        {"roll": "driften", "model": "sonnet", "started_at": iso(SONDAG_12)},
                        now=SONDAG_12, dedup_key=f"roll_start:{post['dedup']}")
        later = SONDAG_12 + dt.timedelta(hours=1)
        self.assertEqual([post["uppgift"]], roller.stada_avbrutna(self.conn, now=later))
        self.assertEqual([], roller.stada_avbrutna(self.conn, now=later))
        rows = [tuple(r) for r in self.conn.execute(
            "SELECT task, status, ended_at, note FROM spelai_run")]
        self.assertEqual(1, len(rows))
        self.assertEqual(("morgonrunda:2026-10-04", "fel", None), rows[0][:3])
        self.assertIn("avbruten", rows[0][3])
        # räknas i kvoten och körs inte igen
        self.assertEqual(1, tillstand.kvot_idag(self.conn, later)["anvanda"])
        self.assertNotIn("morgonrunda:2026-10-04", self.uppgifter(later))


class TickTests(Base):
    def test_hogst_en_korning_per_varv_och_skarmbilder_fore_genomgangen(self):
        self.korning("morgonrunda:2026-10-04", SONDAG_12)
        self.korning("forskningspass:2026-10-04", SONDAG_12, "forskaren")
        tagna = []

        def skarmbild(dag):
            tagna.append(dag)
            return {"filer": ["hem-390x844.png", "hem-hel.png"], "fel": []}
        rapport = roller.tick(self.conn, now_fn=lambda: SONDAG_12, runner=self.runner(),
                              vakt_path=self.vakt, agent_data=self.agent_data,
                              skarmbild_fn=skarmbild)
        self.assertEqual(["2026-10-04"], tagna)
        self.assertEqual(1, len(self.calls))
        self.assertEqual("veckogenomgang:2026-W40", self.calls[0]["uppgift"])
        self.assertIn("hem-390x844.png, hem-hel.png", self.calls[0]["prompt"])
        self.assertNotIn("{skarmbilder}", self.calls[0]["prompt"])
        self.assertEqual("klar", rapport["korning"]["status"])

    def test_tick_kor_forsta_posten_och_skapar_motiveringskatalogen(self):
        self.forslag(frozen=SONDAG_12 - dt.timedelta(minutes=5), agent_hash="h-agent")
        rapport = roller.tick(self.conn, now_fn=lambda: SONDAG_12, runner=self.runner(),
                              vakt_path=self.vakt, agent_data=self.agent_data)
        self.assertEqual(["motivering:stryktipset:4973:30m"],
                         [p["uppgift"] for p in self.calls])
        self.assertTrue((self.agent_data / "motiveringar").is_dir())
        self.assertIn("morgonrunda:2026-10-04", rapport["vantande"])
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM spelai_run").fetchone()[0])

    def test_inget_due_inget_skrivet(self):
        self.assertEqual({}, roller.tick(self.conn, now_fn=lambda: TORSDAG,
                                         runner=self.runner(), vakt_path=self.vakt))
        self.assertEqual([], self.calls)


class CliTests(Base):
    """`cli.py spelai-roller` med falsk körare, spegel och skärmbilder."""

    def test_ett_varv_kor_en_post_och_tar_laset(self):
        from unittest import mock
        import cli
        from app import vakt as vakt_mod
        from app.spelai import skarmbilder, spegel
        from app.storage import Storage
        self.korning("morgonrunda:2026-10-04", SONDAG_12)
        self.korning("forskningspass:2026-10-04", SONDAG_12, "forskaren")
        cli_store = Storage(self.store.db_path)
        tagna, speglat = [], []
        with mock.patch.object(cli, "Storage", return_value=cli_store), \
                mock.patch.object(tillstand, "now_utc", return_value=SONDAG_12), \
                mock.patch.object(roller, "claude_runner", return_value=self.runner()), \
                mock.patch.object(spegel, "spegla",
                                  side_effect=lambda conn, now: speglat.append(now) or {}), \
                mock.patch.object(skarmbilder, "ta",
                                  side_effect=lambda dag: tagna.append(dag) or
                                  {"filer": ["hem-hel.png"], "fel": []}), \
                mock.patch.object(vakt_mod, "default_status_path", return_value=self.vakt), \
                contextlib.redirect_stdout(io.StringIO()) as utskrift:
            self.assertEqual(0, cli.cmd_spelai_roller())
        self.assertIn("spelai-roller:", utskrift.getvalue())   # loggrad när något hänt
        self.assertEqual([SONDAG_12], speglat)
        self.assertEqual(["2026-10-04"], tagna)
        self.assertEqual(["veckogenomgang:2026-W40"], [p["uppgift"] for p in self.calls])
        self.assertEqual(3, self.conn.execute("SELECT COUNT(*) FROM spelai_run").fetchone()[0])
        data = self.store.db_path.parent
        self.assertTrue((data / "spelai-roller.lock").exists())
        self.assertTrue((data / "spelai-spegel.lock").exists())


class RiktigKorareTests(unittest.TestCase):
    """Den riktiga köraren mot ett FALSKT claude-skript — aldrig claude."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, body: str) -> Path:
        path = self.root / "claude"
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    def post(self, timeout_s=30):
        return {"roll": "driften", "uppgift": "morgonrunda:2026-10-04", "prompt": "Gör X.",
                "timeout_s": timeout_s, "max_turns": 40, "model": "sonnet",
                "effort": "medium"}

    def test_kommandot_och_ren_miljo(self):
        argv = roller.kommando(self.post(), Path("/x/claude"))
        self.assertEqual(["/x/claude", "-p", "--agent", "driften", "--model", "sonnet",
                          "--effort", "medium",
                          "--permission-mode", "acceptEdits", "--permission-prompts", "none",
                          "--output-format", "json", "--max-turns", "40", "Gör X."], argv)
        with self.assertRaises(ValueError):
            roller.kommando(self.post() | {"roll": "okand"})
        for effort in ("xhigh", None):       # bara uttryckliga, kända nivåer
            with self.assertRaises(ValueError):
                roller.kommando(self.post() | {"effort": effort})
        os.environ["SPELAI_NTFY_TOPIC"] = "hemligt"
        try:
            env_ut = self.root / "env.txt"
            claude = self.fake(f'env > "{env_ut}"\npwd >> "{env_ut}"\n'
                               'printf \'{"type":"result","subtype":"success","is_error":false,'
                               '"result":"SAMMANFATTNING: ok","num_turns":1}\'\n')
            svar = roller.claude_runner(claude_bin=claude, cwd=self.root, home=self.root)(
                self.post())
        finally:
            del os.environ["SPELAI_NTFY_TOPIC"]
        self.assertEqual(0, svar["returncode"])
        self.assertEqual("klar", roller.tolka(svar, timeout_s=30)["status"])
        env = env_ut.read_text(encoding="utf-8")
        self.assertNotIn("hemligt", env)
        self.assertIn(f"PATH={self.root}/.local/bin:/usr/bin:/bin", env)
        self.assertIn(str(self.root.resolve()), env)              # arbetskatalogen

    def test_timeout_dodar_hela_processgruppen(self):
        pidfil = self.root / "barn.pid"
        claude = self.fake(f'sleep 60 &\necho $! > "{pidfil}"\nwait\n')
        t0 = time.monotonic()
        svar = roller.claude_runner(claude_bin=claude, cwd=self.root, home=self.root,
                                    grace_s=1)(self.post(timeout_s=1))
        self.assertTrue(svar["timed_out"])
        self.assertLess(time.monotonic() - t0, 20)
        barn = int(pidfil.read_text().strip())
        time.sleep(0.2)
        with self.assertRaises(ProcessLookupError):
            os.kill(barn, 0)                                     # barnbarnet dog också


if __name__ == "__main__":
    unittest.main()
