"""Chattbudet: rapporter till agentens chatt, låst mottagare, dedup och tysta timmar."""
import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app.spelai import budkrok, chattbud, schemalaggare  # noqa: E402

UTC = dt.timezone.utc
DAG = dt.datetime(2026, 10, 3, 13, 30, tzinfo=UTC)       # 15:30 svensk tid
NATT = dt.datetime(2026, 10, 3, 22, 30, tzinfo=UTC)      # 00:30 svensk tid
REPO = Path("/Users/saman/spel-ai-kompisen")
MAL = "spel-ai-kompisen-7e"


def sessioner(*extra):
    return [{"name": "rahbari-f6", "cwd": "/Users/saman/rahbari", "kind": "interactive",
             "startedAt": 1}, *extra,
            {"name": MAL, "cwd": str(REPO), "kind": "interactive", "startedAt": 100}]


def strom(*block, cost=0.008):
    """Fejkad stream-json från `claude -p`."""
    rader = []
    for b in block:
        rader.append(json.dumps(b))
    rader.append(json.dumps({"type": "result", "subtype": "success",
                             "total_cost_usd": cost}))
    return "\n".join(rader)


def send(tool_id, to, success=True, is_error=False):
    return (
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tool_id, "name": "SendMessage",
             "input": {"to": to, "message": "x"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error,
             "content": json.dumps({"success": success})}]}},
    )


class FejkRunner:
    """Svarar på `claude agents --json` och på budet; minns varje anrop."""

    def __init__(self, sessions=None, stdout=None, returncode=0):
        self.sessions = sessioner() if sessions is None else sessions
        self.stdout = stdout
        self.returncode = returncode
        self.anrop = []

    def __call__(self, argv, timeout_s):
        self.anrop.append(argv)
        if argv[1:3] == ["agents", "--json"]:
            return {"returncode": 0, "stdout": json.dumps(self.sessions)}
        out = self.stdout if self.stdout is not None else strom(*send("t1", MAL))
        return {"returncode": self.returncode, "stdout": out, "stderr": "",
                "timed_out": False}

    @property
    def bud(self):
        return [a for a in self.anrop if a[1] == "-p"]


class ValjMalTests(unittest.TestCase):
    def test_aldsta_chattsessionen_i_agentrepot(self):
        senare = {"name": "spel-ai-kompisen-9a", "cwd": str(REPO),
                  "kind": "interactive", "startedAt": 500}
        self.assertEqual(MAL, chattbud.valj_mal(sessioner(senare), REPO))

    def test_andra_kataloger_typer_och_namn_valjs_aldrig(self):
        fel = [{"name": "spel-ai-kompisen-x", "cwd": "/Users/saman/spelkompisen",
                "kind": "interactive", "startedAt": 1},
               {"name": "spel-ai-kompisen-y", "cwd": str(REPO), "kind": "background",
                "startedAt": 1},
               {"name": "Spelkompisen Server Auto", "cwd": str(REPO),
                "kind": "interactive", "startedAt": 1},
               {"name": "spel-ai-kompisen; rm -rf", "cwd": str(REPO),
                "kind": "interactive", "startedAt": 1}, "skräp"]
        self.assertIsNone(chattbud.valj_mal(fel, REPO))
        self.assertIsNone(chattbud.valj_mal(None, REPO))


class TextTests(unittest.TestCase):
    def poster(self):
        return [
            {"key": "roll:morgonrunda:2026-10-03", "kind": "roll_klar",
             "title": "Agenten: morgonrunda klar", "message": "Inga fel."},
            {"key": "beslut:7", "kind": "beslut", "title": "Nytt beslut",
             "message": "Ett nytt beslut väntar på ditt svar: Kassaspärr"},
            {"key": "pool:stryktipset:4973:30m", "kind": "pool",
             "title": "Poolförslag klart", "message": "Stryktipset 4973: klart."},
        ]

    def test_viktigast_forst_och_forsta_raden_star_for_sig_sjalv(self):
        text = chattbud.meddelande(self.poster(), now=DAG)
        rader = text.splitlines()
        self.assertEqual("Ett nytt beslut väntar på ditt svar: Kassaspärr", rader[0])
        self.assertIn("• Poolförslag klart — Stryktipset 4973: klart.", rader)
        self.assertLess(text.index("Poolförslag"), text.index("morgonrunda"))
        self.assertIn("Beslut besvaras på Spelkompisens beslutssida.", text)
        self.assertTrue(rader[-1].startswith("(Facitsidan 15:30"))

    def test_styrtecken_avgransare_och_langd_tvattas(self):
        post = {"key": "roll:x", "kind": "roll_klar", "title": "Agenten: x klar",
                "message": "rad\x1b[2Jett >>> slut <<< till " + "y" * 900}
        text = chattbud.meddelande([post], now=DAG)
        self.assertNotIn("\x1b", text)
        self.assertNotIn(">>>", text)
        self.assertNotIn("<<<", text)
        self.assertLessEqual(len(text.splitlines()[0]), chattbud.POST_MAX)

    def test_manga_poster_kapas(self):
        poster = [{"key": f"roll:{i}", "kind": "roll_klar", "title": f"T{i}",
                   "message": "m"} for i in range(12)]
        text = chattbud.meddelande(poster, now=DAG)
        self.assertIn("och 4 till", text)


class KommandoTests(unittest.TestCase):
    def test_begransat_lage_och_kroken_lases_till_mottagaren(self):
        argv = chattbud.kommando(MAL, "hej", claude_bin=Path("/x/claude"),
                                 python="/py", krok=Path("/k/budkrok.py"))
        for flagga in ("--restricted", "--strict-mcp-config", "--no-session-persistence"):
            self.assertIn(flagga, argv)
        self.assertEqual("SendMessage", argv[argv.index("--tools") + 1])
        self.assertEqual("acceptEdits", argv[argv.index("--permission-mode") + 1])
        self.assertEqual("none", argv[argv.index("--permission-prompts") + 1])
        settings = json.loads(argv[argv.index("--settings") + 1])
        hook = settings["hooks"]["PreToolUse"][0]
        self.assertEqual("SendMessage", hook["matcher"])
        self.assertEqual(f"/py -B /k/budkrok.py {MAL}", hook["hooks"][0]["command"])
        self.assertTrue(argv[-1].startswith(f"Mottagare: {MAL}\n"))

    def test_ogiltigt_namn_avvisas(self):
        for namn in ("", "a b", "x;rm", "-p", "å", "rahbari-f6", "spel-ai-kompisen x"):
            with self.assertRaises(ValueError):
                chattbud.kommando(namn, "hej")


class TolkaTests(unittest.TestCase):
    def test_lyckat(self):
        out = chattbud.tolka(strom(*send("a", MAL)), MAL)
        self.assertEqual((True, 1, 0.008), (out["ok"], out["levererade"], out["cost_usd"]))
        self.assertNotIn("andra_anrop", out)

    def test_fel_mottagare_misslyckat_svar_och_inget_anrop(self):
        self.assertFalse(chattbud.tolka(strom(*send("a", "rahbari-f6")), MAL)["ok"])
        self.assertFalse(chattbud.tolka(strom(*send("a", MAL, success=False)), MAL)["ok"])
        self.assertFalse(chattbud.tolka(strom(*send("a", MAL, is_error=True)), MAL)["ok"])
        out = chattbud.tolka(strom(), MAL)
        self.assertEqual((False, "inget SendMessage"), (out["ok"], out["orsak"]))
        self.assertFalse(chattbud.tolka("inte json", MAL)["ok"])

    def test_stoppat_anrop_bredvid_lyckat_redovisas(self):
        out = chattbud.tolka(strom(*send("a", "rahbari-f6", is_error=True),
                                   *send("b", MAL)), MAL)
        self.assertTrue(out["ok"])
        self.assertEqual("rahbari-f6", out["andra_anrop"][0]["till"])


class BudkrokTests(unittest.TestCase):
    def kor(self, data, argv=(MAL,), raw=None):
        with contextlib.redirect_stderr(io.StringIO()):     # orsaken går till stderr
            return budkrok.main(list(argv), io.StringIO(raw or json.dumps(data)))

    def test_ratt_mottagare_tillats(self):
        self.assertEqual(0, self.kor({"tool_name": "SendMessage",
                                      "tool_input": {"to": MAL, "message": "x"}}))

    def test_allt_annat_stoppas(self):
        for data in ({"tool_name": "SendMessage", "tool_input": {"to": "rahbari-f6"}},
                     {"tool_name": "SendMessage",
                      "tool_input": {"to": f"{MAL} [e10388]"}},
                     {"tool_name": "SendMessage",
                      "tool_input": {"to": MAL, "notify_when_idle": True}},
                     {"tool_name": "Bash", "tool_input": {"command": "ls"}},
                     {"tool_name": "SendMessage"}, ["inte", "dict"]):
            self.assertEqual(2, self.kor(data), data)
        self.assertEqual(2, self.kor({"tool_name": "SendMessage",
                                      "tool_input": {"to": MAL}}, argv=()))
        self.assertEqual(2, self.kor(None, raw="inte json"))


class SkickaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def handelse(self, kind, ref, detail, at, dedup):
        self.conn.execute(
            "INSERT INTO spelai_event (at, kind, ref, detail_json, dedup_key) "
            "VALUES (?,?,?,?,?)", (at.strftime("%Y-%m-%dT%H:%M:%SZ"), kind, ref,
                                   json.dumps(detail), dedup))
        self.conn.commit()

    def forslag(self, horizon, frozen, close):
        for role in ("agent", "standard"):
            self.conn.execute(
                "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                "horizon, role, status, rows_text, reg_close_time, frozen_at) "
                "VALUES ('stryktipset', 4973, 256, ?, ?, 'fryst', ?, ?, ?)",
                (horizon, role, "1X21X21X21X21", close.isoformat(), frozen.isoformat()))
        self.conn.commit()

    def beslut(self, external_id, created, sista=None):
        cur = self.conn.execute(
            "INSERT INTO spelai_inbox (external_id, typ, kalla, rubrik, varfor, "
            "alternativ_json, sista_tid, payload_hash, created_at) VALUES "
            "(?, 'beslut', 'Driften', 'Kassaspärr', 'x', '[]', ?, 'h', ?)",
            (external_id, sista.isoformat() if sista else None, created.isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def handelser(self, kind):
        return self.conn.execute("SELECT ref, detail_json FROM spelai_event WHERE kind=? "
                                 "ORDER BY id", (kind,)).fetchall()

    def test_levererar_en_gang_och_aldrig_igen(self):
        self.handelse("roll_klar", "morgonrunda:2026-10-03",
                      {"typ": "morgonrunda", "sammanfattning": "Inga fel."}, DAG,
                      "roll_slut:morgonrunda:2026-10-03")
        self.forslag("30m", DAG, DAG + dt.timedelta(minutes=30))
        runner = FejkRunner()
        rep = chattbud.skicka(self.conn, now=DAG, runner=runner, repo=REPO)
        self.assertEqual({"skickade": 2, "mal": MAL}, rep)
        self.assertEqual(1, len(runner.bud))
        prompt = runner.bud[0][-1]
        self.assertIn("Poolförslag klart — Stryktipset 4973", prompt)
        self.assertIn("Agenten: morgonrunda klar — Inga fel.", prompt)
        self.assertNotIn("1X21X2", prompt)
        self.assertEqual(2, len(self.handelser("chatt")))
        leverans = json.loads(self.handelser("chatt_leverans")[0][1])
        self.assertEqual((0.008, 1), (leverans["cost_usd"], leverans["levererade"]))
        # dedup: nästa tick skickar ingenting och anropar ingen modell
        self.assertEqual({}, chattbud.skicka(self.conn, now=DAG, runner=runner, repo=REPO))
        self.assertEqual(1, len(runner.bud))

    def test_sexh_forslag_besvarade_beslut_och_passerat_stopp_hoppas_over(self):
        self.forslag("6h", DAG, DAG + dt.timedelta(hours=6))
        inbox_id = self.beslut("b1", DAG)
        self.conn.execute("INSERT INTO spelai_inbox_answer (inbox_id, val, answered_at) "
                          "VALUES (?, '1', ?)", (inbox_id, DAG.isoformat()))
        self.conn.commit()
        runner = FejkRunner()
        self.assertEqual({}, chattbud.skicka(self.conn, now=DAG, runner=runner, repo=REPO))
        self.assertEqual([], runner.anrop)

    def test_tysta_timmar_skjuter_upp_men_beslut_med_sista_tid_gar_fram(self):
        self.handelse("roll_klar", "forskningspass:2026-10-03",
                      {"typ": "forskningspass", "sammanfattning": "Klart."}, NATT,
                      "roll_slut:forskningspass:2026-10-03")
        self.beslut("b2", NATT, sista=NATT + dt.timedelta(hours=2))
        runner = FejkRunner()
        rep = chattbud.skicka(self.conn, now=NATT, runner=runner, repo=REPO)
        self.assertEqual(1, rep["skickade"])
        self.assertIn("Kassaspärr", runner.bud[0][-1])
        self.assertNotIn("forskningspass", runner.bud[0][-1])
        morgon = NATT + dt.timedelta(hours=7)                   # 07:30 svensk tid
        self.assertEqual(1, chattbud.skicka(self.conn, now=morgon, runner=runner,
                                            repo=REPO)["skickade"])

    def test_ingen_chattsession_ger_inget_modellanrop(self):
        self.beslut("b3", DAG)
        runner = FejkRunner(sessions=[{"name": "rahbari-f6", "cwd": "/x",
                                       "kind": "interactive", "startedAt": 1}])
        self.assertEqual({"ingen_chatt": True},
                         chattbud.skicka(self.conn, now=DAG, runner=runner, repo=REPO))
        self.assertEqual([], runner.bud)
        self.assertEqual([], self.handelser("chatt"))

    def test_misslyckad_leverans_bokfors_och_vantar_innan_nytt_forsok(self):
        self.beslut("b4", DAG)
        runner = FejkRunner(stdout=strom(*send("a", "rahbari-f6", is_error=True)))
        rep = chattbud.skicka(self.conn, now=DAG, runner=runner, repo=REPO)
        self.assertIn("fel", rep)
        self.assertEqual(1, len(self.handelser("chatt_fel")))
        self.assertEqual([], self.handelser("chatt"))
        snart = DAG + dt.timedelta(minutes=5)
        rep = chattbud.skicka(self.conn, now=snart, runner=runner, repo=REPO)
        self.assertEqual({"vantar": 1, "omforsok_efter_fel": True}, rep)
        self.assertEqual(1, len(runner.bud))
        runner.stdout = None                                     # nu lyckas budet
        senare = DAG + dt.timedelta(minutes=11)
        self.assertEqual(1, chattbud.skicka(self.conn, now=senare, runner=runner,
                                            repo=REPO)["skickade"])

    def test_avstangt_utan_runner(self):
        self.beslut("b5", DAG)
        self.assertEqual({}, chattbud.skicka(self.conn, now=DAG, runner=None))

    def test_schemalaggaren_kor_chattsteget_sist(self):
        self.assertEqual("chatt", schemalaggare.STEG[-1])
        self.beslut("b6", DAG)
        runner = FejkRunner()
        report = schemalaggare.tick(self.store, runner=None, clock=lambda: DAG,
                                    utkorg=Path(self.tmp.name) / "utkorg",
                                    sender=None, topic_name=None, chatt_runner=runner)
        self.assertEqual({"skickade": 1, "mal": MAL}, report["chatt"])


if __name__ == "__main__":
    unittest.main()
