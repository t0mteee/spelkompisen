"""Facitsidans frysning: indatapaket, fönster, standard = PH3, agent, missat, paus."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import (START, Klocka, draw_fixture, giltigt_svar,  # noqa: E402
                           lagg_till_omgang, ny_store)
from app import pool_system_ledger as ph3  # noqa: E402
from app.spelai import frysning, indata, nivaer, schemalaggare, tillstand  # noqa: E402
from app.spelai.sandbox import AgentSvar  # noqa: E402

UTC = dt.timezone.utc
CLOSE = dt.datetime(2026, 10, 3, 13, 59, tzinfo=UTC)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def capture(self, product="topptipset", number=4400, n_events=8,
                horizon="30m", close=CLOSE, offset_min=2.0):
        start, _end = indata.window(close, horizon)
        observed = start + dt.timedelta(minutes=offset_min)
        draw = draw_fixture(close, observed, product=product, number=number,
                            n_events=n_events)
        lagg_till_omgang(self.store, product, number, close)
        rep = indata.capture_due(self.store, product, draw, {}, {}, jackpot=None,
                                 now=observed)
        return observed, rep

    def runner(self, svar_fn=giltigt_svar):
        def run(payload, levels, timeout):
            self.calls.append((payload["product"], payload["horizon"], list(levels), timeout))
            return svar_fn(payload, levels, timeout)
        return run

    def rows(self, **where):
        sql = "SELECT * FROM spelai_pool_proposal"
        if where:
            sql += " WHERE " + " AND ".join(f"{k}=?" for k in where)
        return [dict(r) for r in self.store.conn.execute(
            sql + " ORDER BY level_kr, role", tuple(where.values()))]


class CaptureTests(_Base):
    def test_6h_fonstret_och_toleransen(self):
        _obs, rep = self.capture(horizon="6h", offset_min=1)
        self.assertEqual(["6h"], rep["captured"])
        # T−5h29 ligger utanför 30-minuterstoleransen
        draw = draw_fixture(CLOSE, CLOSE - dt.timedelta(hours=5, minutes=29),
                            product="topptipset", number=4401, n_events=8)
        rep = indata.capture_due(self.store, "topptipset", draw, now=CLOSE)
        self.assertEqual([], rep["captured"])
        # före fönstret
        draw = draw_fixture(CLOSE, CLOSE - dt.timedelta(hours=6, minutes=1),
                            product="topptipset", number=4402, n_events=8)
        self.assertEqual([], indata.capture_due(self.store, "topptipset", draw,
                                                now=CLOSE)["captured"])

    def test_30m_fonstret_35_till_30(self):
        for minutes, number, expected in ((36, 4410, []), (33, 4411, ["30m"]),
                                          (30, 4412, ["30m"]), (29, 4413, [])):
            draw = draw_fixture(CLOSE, CLOSE - dt.timedelta(minutes=minutes),
                                product="topptipset", number=number, n_events=8)
            rep = indata.capture_due(self.store, "topptipset", draw, now=CLOSE)
            self.assertEqual(expected, rep["captured"], minutes)

    def test_ett_paket_per_horisont(self):
        observed, rep = self.capture()
        self.assertEqual(["30m"], rep["captured"])
        draw = draw_fixture(CLOSE, observed + dt.timedelta(minutes=1),
                            product="topptipset", number=4400, n_events=8)
        self.assertEqual([], indata.capture_due(self.store, "topptipset", draw,
                                                now=CLOSE)["captured"])
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM spelai_input").fetchone()[0])

    def test_utan_tabeller_hander_ingenting(self):
        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp, med_tabeller=False)
        try:
            draw = draw_fixture(CLOSE, CLOSE - dt.timedelta(minutes=33),
                                product="topptipset", n_events=8)
            rep = indata.capture_due(store, "topptipset", draw, now=CLOSE)
            self.assertEqual("spelai-tabellerna saknas", rep["skipped"])
            self.assertEqual({"fel": "spelai-tabellerna saknas — kör "
                                     "scripts/migrera_spelai.py"},
                             schemalaggare.tick(store, runner=None,
                                                clock=Klocka(CLOSE)))
        finally:
            store.close()
            tmp.cleanup()

    def test_draw_sharp_movement_tur_och_retur(self):
        draw = draw_fixture(CLOSE, CLOSE - dt.timedelta(minutes=33))
        self.assertEqual(draw, indata.draw_from_payload(
            json.loads(json.dumps(indata.draw_to_payload(draw)))))
        sharp = {3: {"odds": {"1": 2.0, "X": 3.4, "2": 3.9}, "total": None,
                     "bookmaker": "pinnacle", "confidence": 1.0, "matched": "A - B",
                     "fetched_at": "2026-10-03T13:20:00Z"}}
        self.assertEqual(sharp, indata.decode_sharp(json.loads(json.dumps(
            indata.encode_sharp(sharp)))))
        movement = {(3, "1"): {"first": 2.1, "last": 2.0, "steam_pp": 1.5},
                    (3, "X"): {"streck_first": 25, "streck_last": 27}}
        self.assertEqual(movement, indata.decode_movement(json.loads(json.dumps(
            indata.encode_movement(movement)))))


class ProcessTests(_Base):
    def test_topptipset_standard_och_agent_frysta_med_underlag(self):
        observed, _ = self.capture()
        rep = frysning.process_inputs(self.store.conn, self.runner(),
                                      clock=Klocka(observed + dt.timedelta(seconds=40)))
        self.assertEqual(1, rep["frysta"])
        rows = self.rows()
        self.assertEqual([("agent", "fryst"), ("standard", "fryst")],
                         [(r["role"], r["status"]) for r in rows])
        standard = next(r for r in rows if r["role"] == "standard")
        self.assertEqual(256, standard["n_rows"])
        self.assertEqual("dr1-b256-medel", standard["config_key"])
        self.assertEqual("standard:dr1-b256-medel", standard["strategy_version"])
        agent = next(r for r in rows if r["role"] == "agent")
        self.assertEqual("falsk-v1", agent["strategy_version"])
        input_id = self.store.conn.execute("SELECT id FROM spelai_input").fetchone()[0]
        for row in rows:
            self.assertEqual(input_id, row["input_id"])
            self.assertEqual(tillstand.iso(observed), row["input_observed_at"])
            self.assertEqual(tillstand.iso(observed), row["obs_svs_at"])
            self.assertEqual("1,2,3,4,5,6,7,8", row["events_order"])
        # agenten anropas EN gång med produktens nivåer och tidsfrist ≤ 180 s
        self.assertEqual(1, len(self.calls))
        self.assertEqual([256], self.calls[0][2])
        self.assertLessEqual(self.calls[0][3], 180)

    def test_om_bearbetning_ar_idempotent(self):
        observed, _ = self.capture()
        clock = Klocka(observed + dt.timedelta(seconds=40))
        frysning.process_inputs(self.store.conn, self.runner(), clock=clock)
        rep = frysning.process_inputs(self.store.conn, self.runner(), clock=clock)
        self.assertEqual(0, rep["frysta"])
        self.assertEqual(1, len(self.calls))
        self.assertEqual(2, len(self.rows()))

    def test_30m_mer_an_5_min_efter_observation_ar_missat(self):
        observed, _ = self.capture()
        rep = frysning.process_inputs(
            self.store.conn, self.runner(),
            clock=Klocka(observed + dt.timedelta(minutes=5, seconds=1)))
        self.assertEqual(2, rep["missat"])
        self.assertEqual({"missat"}, {r["status"] for r in self.rows()})
        self.assertEqual([], self.calls)

    def test_paus_ger_pausad_inte_missat(self):
        observed, _ = self.capture()
        tillstand.satt_paus(self.store.conn, True, source="test", now=observed)
        rep = frysning.process_inputs(self.store.conn, self.runner(),
                                      clock=Klocka(observed + dt.timedelta(seconds=30)))
        self.assertEqual(2, rep["pausad"])
        self.assertEqual({"pausad"}, {r["status"] for r in self.rows()})
        self.assertEqual([], self.calls)

    def test_agentens_saknade_och_ogiltiga_niva(self):
        observed, _ = self.capture()
        frysning.process_inputs(
            self.store.conn,
            self.runner(lambda p, lv, t: AgentSvar("ok", data={"version": "v", "forslag": {}})),
            clock=Klocka(observed + dt.timedelta(seconds=30)))
        agent = self.rows(role="agent")[0]
        self.assertEqual("ogiltigt", agent["status"])
        self.assertIn("nivån 256 saknas", agent["reason"])
        self.assertEqual("fryst", self.rows(role="standard")[0]["status"])

    def test_en_ogiltig_niva_paverkar_inte_de_andra(self):
        observed, _ = self.capture(product="stryktipset", number=4000, n_events=13)

        def svar(payload, levels, timeout):
            out = giltigt_svar(payload, levels, timeout)
            out.data["forslag"]["512"]["rows"].append(out.data["forslag"]["512"]["rows"][0])
            return out

        fake = {"format": "rows", "rows": ["1" * 13], "tecken": None, "n_rows": 1,
                "cost_kr": 1.0, "rows_hash": "x", "motivering": None,
                "config_key": "k", "note": None}
        with patch.object(frysning, "build_standard", return_value=fake):
            frysning.process_inputs(self.store.conn, self.runner(svar),
                                    clock=Klocka(observed + dt.timedelta(seconds=30)))
        status = {r["level_kr"]: r["status"] for r in self.rows(role="agent")}
        self.assertEqual({256: "fryst", 512: "ogiltigt", 5000: "fryst",
                          20000: "fryst", 39366: "fryst"}, status)
        self.assertIn("dubblett", self.rows(role="agent", level_kr=512)[0]["reason"])
        self.assertEqual([[256, 512, 5000, 20000, 39366]], [c[2] for c in self.calls])

    def test_agentfel_ger_ogiltigt_med_stderr_och_saknad_agent_ger_saknas(self):
        observed, _ = self.capture()
        frysning.process_inputs(
            self.store.conn,
            self.runner(lambda p, lv, t: AgentSvar("fel", reason="agenten avslutade med kod 1",
                                                   stderr="Traceback: boom")),
            clock=Klocka(observed + dt.timedelta(seconds=30)))
        agent = self.rows(role="agent")[0]
        self.assertEqual(("ogiltigt", "agenten avslutade med kod 1", "Traceback: boom"),
                         (agent["status"], agent["reason"], agent["agent_stderr"]))
        self.assertEqual("fryst", self.rows(role="standard")[0]["status"])

        observed2, _ = self.capture(number=4401, close=CLOSE + dt.timedelta(hours=1))
        frysning.process_inputs(
            self.store.conn,
            self.runner(lambda p, lv, t: AgentSvar("saknas", reason="sandbox saknas")),
            clock=Klocka(observed2 + dt.timedelta(seconds=30)))
        agent = self.rows(role="agent", draw_number=4401)[0]
        self.assertEqual(("saknas", "sandbox saknas"), (agent["status"], agent["reason"]))

    def test_append_only_gar_inte_att_skriva_over(self):
        observed, _ = self.capture()
        frysning.process_inputs(self.store.conn, self.runner(),
                                clock=Klocka(observed + dt.timedelta(seconds=30)))
        import sqlite3
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("UPDATE spelai_pool_proposal SET status='missat'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.store.conn.execute("DELETE FROM spelai_input")


class MissedTests(_Base):
    def test_missat_nar_inget_paket_kom_i_fonstret(self):
        close = START + dt.timedelta(hours=10)
        lagg_till_omgang(self.store, "topptipset", 4500, close)
        now = close - dt.timedelta(hours=5, minutes=27)        # 6h-fönstret + 3 min
        rep = frysning.mark_missed(self.store.conn, now=now)
        self.assertEqual(2, rep["missat"])
        rows = self.rows(draw_number=4500)
        self.assertEqual({("6h", "missat")}, {(r["horizon"], r["status"]) for r in rows})
        # idempotent
        self.assertEqual(0, frysning.mark_missed(self.store.conn, now=now)["missat"])
        # 30m senare
        rep = frysning.mark_missed(self.store.conn, now=close - dt.timedelta(minutes=27))
        self.assertEqual(2, rep["missat"])

    def test_fonster_fore_facit_start_raknas_aldrig(self):
        close = START + dt.timedelta(hours=3)       # 6h-fönstret öppnade före START
        lagg_till_omgang(self.store, "stryktipset", 4972, close)
        lagg_till_omgang(self.store, "stryktipset", 4900, START - dt.timedelta(days=60))
        frysning.mark_missed(self.store.conn, now=close - dt.timedelta(hours=2))
        self.assertEqual([], self.rows())

    def test_pausad_och_installd(self):
        close = START + dt.timedelta(hours=10)
        lagg_till_omgang(self.store, "topptipset", 4501, close)
        lagg_till_omgang(self.store, "topptipset", 4502, close, state="Cancelled")
        tillstand.satt_paus(self.store.conn, True, source="test", now=START)
        frysning.mark_missed(self.store.conn, now=close - dt.timedelta(hours=5))
        self.assertEqual({"pausad"}, {r["status"] for r in self.rows(draw_number=4501)})
        self.assertEqual([], self.rows(draw_number=4502))


class StandardLikaPH3Tests(unittest.TestCase):
    """Standarden ska ge EXAKT samma rader som motsvarande PH3-config på samma
    underlag — det finns ingen parallell byggare."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.now = dt.datetime(2026, 10, 3, 11, 1, tzinfo=UTC)
        self.close = self.now + dt.timedelta(minutes=178)    # PH3:s h3 är öppet

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _jamfor(self, product, number, n_events, levels):
        draw = draw_fixture(self.close, self.now, product=product, number=number,
                            n_events=n_events)
        ph3.freeze_due(self.store, product, draw, now=self.now, code_version="test")
        payload = indata.build_payload(self.store, product, draw, "30m", {}, {},
                                       None, "missing", None, self.now)
        payload = json.loads(json.dumps(payload))      # som paketet i tabellen
        analysis, jp = frysning.analysis_from_payload(payload)
        for level in levels:
            key = frysning.STANDARD_CONFIGS[level]
            text = self.store.conn.execute(
                "SELECT rows_text FROM pool_system_ledger WHERE product=? AND "
                "draw_number=? AND config_key=?", (product, number, key)).fetchone()
            self.assertIsNotNone(text, key)
            expected = {"".join(r) for r in ph3._decode_rows(text[0])}
            form = frysning.build_standard(payload, level, analysis, jp)
            got = (set(nivaer.expandera(form["tecken"])) if form["format"] == "msystem"
                   else set(form["rows"]))
            self.assertEqual(expected, got, f"{product} {level} ({key})")
            self.assertEqual(len(expected), form["n_rows"])

    def test_256_och_512_lika_ph3(self):
        self._jamfor("topptipset", 4000, 8, [256])
        self._jamfor("stryktipset", 4000, 13, [256, 512])

    def test_5000_20000_och_39366_lika_forskningsfamiljerna(self):
        self._jamfor("europatipset", 2700, 13, [5000, 20000, 39366])

    def test_standardconfigs_ar_medel(self):
        for level in nivaer.NIVAER_STORA:
            config = frysning.standard_config(level)
            self.assertEqual("medel", config["strategy"])
            self.assertEqual(0.5, config["value_weight"])
            self.assertEqual(float(level), config["budget"])


class TickTests(_Base):
    def test_tick_kor_alla_steg_med_injicerad_klocka(self):
        observed, _ = self.capture()
        sent = []
        report = schemalaggare.tick(
            self.store, runner=self.runner(),
            clock=Klocka(observed + dt.timedelta(seconds=30)),
            utkorg=Path(self.tmp.name) / "utkorg",
            sender=lambda *a: sent.append(a) or True, topic_name="test-amne")
        self.assertEqual(1, report["frysning"]["frysta"])
        # 30m-förslaget frystes; 6h-fönstret passerade utan paket ⇒ missat
        self.assertEqual(2, report["missat"]["missat"])
        self.assertEqual({"Poolförslag klart", "Poolförslag missat"},
                         {args[1] for args in sent})
        self.assertEqual(2, report["notiser"]["skickade"])


if __name__ == "__main__":
    unittest.main()
