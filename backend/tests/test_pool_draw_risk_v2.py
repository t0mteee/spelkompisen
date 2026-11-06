"""pool-draw-risk-v2 (Samans beslut 2026-11-06, "X-skydd via Kambi").

När Pinnacle-totalen saknas styr Svenska Spels/Kambis Ö/U-lina ur
Ö/U-reservens journal samma X-skyddsregel (≤ 2,25). Pinnacle går alltid
först, linan läses vid bygget as-of och samma funktion används i appen,
PH3 och spelai-standarden.
"""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import draw_fixture, lagg_till_omgang, ny_store  # noqa: E402
from app import builder  # noqa: E402
from app import pool_reserve as r  # noqa: E402
from app import pool_system_ledger as ph3  # noqa: E402
from app.analysis import analyze_draw  # noqa: E402
from app.spelai import frysning, indata  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
START = "2026-11-07T15:00:00+00:00"


def _journal():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(r.SCHEMA)
    return conn


def _insert(conn, event, minutes_ago, status="available", line=2.25,
            product="stryktipset", draw=1, pid=None, start=START):
    t = (NOW - dt.timedelta(minutes=minutes_ago)).isoformat()
    conn.execute("INSERT INTO pool_reserve_quote VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (product, draw, event, r.SOURCE, str(pid or event), t, t, status,
                  line, 1.9, 1.9, start, "H", "B", r.VERSION))


class BuildTotalsTests(unittest.TestCase):
    def setUp(self):
        self.conn = _journal()
        self.addCleanup(self.conn.close)
        self.store = SimpleNamespace(conn=self.conn)

    def test_senaste_kontroll_fore_as_of_och_inom_90_min(self):
        _insert(self.conn, 1, 80)                     # färsk nog (≤ 90 min)
        _insert(self.conn, 2, 100)                    # för gammal
        _insert(self.conn, 3, 10, line=2.25)
        _insert(self.conn, 3, -5, line=3.0)           # efter as-of: finns inte
        totals = r.build_totals(self.store, "stryktipset", 1, NOW)
        self.assertEqual({1, 3}, set(totals))
        self.assertEqual(2.25, totals[3]["line"])
        self.assertEqual(r.SOURCE, totals[3]["source"])

    def test_kallfel_hoppas_over_men_no_market_ar_en_observation(self):
        _insert(self.conn, 1, 20)
        _insert(self.conn, 1, 5, status="source_error", line=None)
        _insert(self.conn, 2, 20)
        _insert(self.conn, 2, 5, status="no_market", line=None)
        totals = r.build_totals(self.store, "stryktipset", 1, NOW)
        self.assertEqual({1}, set(totals))

    def test_startad_match_ger_ingen_lina(self):
        _insert(self.conn, 1, 10, start=(NOW - dt.timedelta(minutes=1)).isoformat())
        self.assertEqual({}, r.build_totals(self.store, "stryktipset", 1, NOW))

    def test_utan_journal_ingen_reserv(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.assertEqual({}, r.build_totals(SimpleNamespace(conn=conn),
                                            "stryktipset", 1, NOW))


class RefreshForBuildTests(unittest.TestCase):
    def setUp(self):
        self.conn = _journal()
        self.addCleanup(self.conn.close)
        self.store = SimpleNamespace(conn=self.conn)

    def draw(self, ids):
        return SimpleNamespace(
            state="Open", draw_number=1, reg_close_time="2026-11-07T14:59:00+00:00",
            matches=[SimpleNamespace(event_number=i, kambi_id=str(pid),
                                     match_start=START, cancelled=False)
                     for i, pid in enumerate(ids, 1)])

    def quote(self, match):
        t = NOW.isoformat()
        return {"status": "available", "line": 2.25, "over_odds": 1.9,
                "under_odds": 1.9, "checked_at": t, "observed_at": t,
                "match_start": START, "home": "H", "away": "B"}

    def test_bara_matcher_utan_pinnacle_total(self):
        sharp = {1: {"total": {"line": 2.5}}, 2: {"total": {}}}
        with patch.object(r, "fetch_quote", side_effect=self.quote) as fetch:
            rep = r.refresh_for_build(self.store, "stryktipset", self.draw([11, 12, 13]),
                                      sharp, now=NOW)
        self.assertEqual(["12", "13"], [c.args[0].kambi_id for c in fetch.call_args_list])
        self.assertEqual((2, 2), (rep["calls"], rep["saved"]))

    def test_nyss_kontrollerad_lina_delas_utan_nytt_anrop(self):
        _insert(self.conn, 1, 2, product="topptipsetstryk", pid=11)
        with patch.object(r, "fetch_quote", side_effect=self.quote) as fetch:
            rep = r.refresh_for_build(self.store, "stryktipset", self.draw([11]), {},
                                      now=NOW)
        fetch.assert_not_called()
        self.assertEqual((1, 1), (rep["fresh"], rep["saved"]))
        row = self.conn.execute("SELECT checked_at FROM pool_reserve_quote "
                                "WHERE product='stryktipset'").fetchone()
        self.assertEqual((NOW - dt.timedelta(minutes=2)).isoformat(), row[0])

    def test_taket_galler_hela_varvet(self):
        varv = SimpleNamespace()
        with patch.object(r, "BUILD_MAX_CALLS", 3), \
                patch.object(r, "fetch_quote", side_effect=self.quote):
            first = r.refresh_for_build(self.store, "stryktipset",
                                        self.draw([1, 2]), {}, varv=varv, now=NOW)
            second = r.refresh_for_build(self.store, "europatipset",
                                         self.draw([3, 4]), {}, varv=varv, now=NOW)
        self.assertEqual((2, 1, 1), (first["calls"], second["calls"], second["unserved"]))

    def test_natfel_sparas_som_kallfel(self):
        with patch.object(r, "fetch_quote", side_effect=RuntimeError("nät")):
            r.refresh_for_build(self.store, "stryktipset", self.draw([1]), {}, now=NOW)
        self.assertEqual("source_error", self.conn.execute(
            "SELECT status FROM pool_reserve_quote").fetchone()[0])


class ApplyTests(unittest.TestCase):
    def analysis(self):
        close = NOW + dt.timedelta(hours=3)
        draw = draw_fixture(close, NOW, n_events=3)
        # Match 1: X ≈ 0,30 — skyddas bara med låg total.
        for sign, odds in (("1", 2.4), ("X", 3.1), ("2", 3.0)):
            draw.matches[0].outcomes[sign].odds = odds
        sharp = {2: {"bookmaker": "pinnacle", "odds": {"1": 2.0, "X": 3.4, "2": 3.8},
                     "total": {"line": 3.0, "O": 1.9, "U": 1.9}}}
        return analyze_draw(draw, sharp, {})

    def test_pinnacle_forst_kambi_annars(self):
        analysis = self.analysis()
        totals = {1: {"line": 2.25, "over_odds": 1.95, "under_odds": 1.85,
                      "source": r.SOURCE},
                  2: {"line": 2.0, "source": r.SOURCE}}
        self.assertEqual(1, builder.apply_reserve_totals(analysis, totals))
        first, second, third = analysis.matches
        self.assertEqual((2.25, r.SOURCE), (first.total_line, first.total_source))
        self.assertEqual((3.0, "pinnacle"), (second.total_line, second.total_source))
        self.assertEqual((None, None), (third.total_line, third.total_source))

    def test_kambis_lina_satter_x_skyddet(self):
        analysis = self.analysis()
        self.assertFalse(builder.draw_risk_context(analysis.matches[0])["protected"])
        builder.apply_reserve_totals(analysis, {"1": {"line": 2.25, "source": r.SOURCE}})
        context = builder.draw_risk_context(analysis.matches[0])
        self.assertTrue(context["protected"])
        self.assertEqual(("pool-draw-risk-v2", r.SOURCE),
                         (context["version"], context["total_source"]))


class FrysningTests(unittest.TestCase):
    """PH3 och spelai-standarden får samma linor och samma rader."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.now = dt.datetime(2026, 11, 7, 11, 1, tzinfo=UTC)
        self.close = self.now + dt.timedelta(minutes=178)    # h3 är due

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_freeze_pending_foljer_frysningen(self):
        draw = draw_fixture(self.close, self.now, n_events=13)
        early = self.close - dt.timedelta(minutes=200)
        self.assertFalse(ph3.freeze_pending(self.store, "stryktipset", draw, early))
        self.assertTrue(ph3.freeze_pending(self.store, "stryktipset", draw, self.now))
        ph3.freeze_due(self.store, "stryktipset", draw, now=self.now, code_version="test")
        self.assertFalse(ph3.freeze_pending(self.store, "stryktipset", draw, self.now))

    def test_ph3_och_standarden_lika_med_kambi_och_noten_sager_det(self):
        draw = draw_fixture(self.close, self.now, n_events=13)
        for sign, odds in (("1", 2.4), ("X", 3.1), ("2", 3.0)):
            draw.matches[0].outcomes[sign].odds = odds
        lagg_till_omgang(self.store, "stryktipset", 5000, self.close)
        totals = {m.event_number: {"line": 2.25, "over_odds": 1.9, "under_odds": 1.9,
                                   "observed_at": self.now.isoformat(), "source": r.SOURCE}
                  for m in draw.matches}
        ph3.freeze_due(self.store, "stryktipset", draw, now=self.now,
                       code_version="test", reserve_totals=totals)
        text, note = self.store.conn.execute(
            "SELECT rows_text, build_note FROM pool_system_ledger WHERE "
            "config_key=?", (frysning.STANDARD_CONFIGS[256],)).fetchone()
        self.assertIn("SvS/Kambi i 13 matcher (pool-draw-risk-v2)", note)
        payload = json.loads(json.dumps(indata.build_payload(
            self.store, "stryktipset", draw, "30m", {}, {}, None, "missing", None,
            self.now, reserve_totals=totals)))
        analysis, jp = frysning.analysis_from_payload(payload)
        self.assertEqual(r.SOURCE, analysis.matches[0].total_source)
        form = frysning.build_standard(payload, 256, analysis, jp)
        self.assertEqual({"".join(row) for row in ph3._decode_rows(text)},
                         set(form["rows"]))

    def test_gammalt_paket_utan_nyckel_bygger_som_forut(self):
        draw = draw_fixture(self.close, self.now, n_events=8, product="topptipset")
        payload = json.loads(json.dumps(indata.build_payload(
            self.store, "topptipset", draw, "30m", {}, {}, None, "missing", None,
            self.now)))
        payload.pop("reserve_totals")
        analysis, _jp = frysning.analysis_from_payload(payload)
        self.assertTrue(all(m.total_line is None for m in analysis.matches))


if __name__ == "__main__":
    unittest.main()
