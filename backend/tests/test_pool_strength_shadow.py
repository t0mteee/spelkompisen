import datetime as dt
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pool_strength_shadow
from app.storage import Storage
from app.svenskaspel import Draw, Match, Outcome


NOW = dt.datetime(2026, 8, 10, 12, 0, tzinfo=dt.timezone.utc)


def _manifest(*, model_version="m-test", horizons=None, decision=None,
              min_events=300):
    horizons = horizons or ["h24", "h3", "m20"]
    return {
        "experiment": "pool-strength-blend-test",
        "source_versions": {"model_signal_version": model_version},
        "collection": {"starts_at": "2026-08-10T00:00:00Z"},
        "scope": {
            "horizons": horizons,
            "decision_horizons": decision or ["h3", "m20"],
        },
        "gate": {
            "minimum_settled_events_per_horizon": min_events,
            "minimum_settled_per_league": 1,
            "minimum_represented_leagues": 1,
            "minimum_span_days": 1,
        },
    }


def _match(event, league="Allsvenskan", home="Hammarby", away="AIK"):
    outcomes = {
        sign: Outcome(sign, odd, odd, None, None)
        for sign, odd in zip(("1", "X", "2"), (2.0, 3.5, 4.0))
    }
    return Match(event, f"{home} - {away}", home, away, None, None,
                 league, "2026-08-10T17:00:00Z", False, None, outcomes)


def _draw(matches):
    return Draw("stryktipset", 9001, "Open", "2026-08-10T15:00:00Z",
                None, 1.0, "2026-08-10T12:00:00Z", matches=matches)


class PoolStrengthIdentityTests(unittest.TestCase):
    def test_blend_ar_en_linjarkombination_som_summeras_till_ett(self):
        sharp = {"1": 0.50, "X": 0.30, "2": 0.20}
        model = {"1": 0.30, "X": 0.30, "2": 0.40}
        blended = pool_strength_shadow._blend(sharp, model, 0.10)
        self.assertAlmostEqual(0.48, blended["1"])
        self.assertAlmostEqual(0.30, blended["X"])
        self.assertAlmostEqual(0.22, blended["2"])
        self.assertAlmostEqual(1.0, sum(blended.values()))

    def test_ligaidentifiering_ar_explicit_och_inte_fuzzy(self):
        self.assertEqual("allsvenskan",
                         pool_strength_shadow._league_key("Allsvenskan"))
        self.assertIsNone(pool_strength_shadow._league_key(
            "Allsvenskan kval"))
        self.assertIsNone(pool_strength_shadow._league_key("EFL Cup"))

    def test_lagidentifiering_tar_exakt_kanon_fore_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fit = {"teams": {"ifk goteborg": {}, "goteborg": {}}}
                with patch("app.pool_strength_shadow.oddset_data._alias_map",
                           return_value={"ifk goteborg": "goteborg"}):
                    self.assertEqual("ifk goteborg",
                                     pool_strength_shadow._canonical_team(
                                         store, "allsvenskan", fit,
                                         "IFK Göteborg"))
            finally:
                store.close()


class PoolStrengthCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_fryser_alla_matchrader_men_bara_sakra_ar_eligible(self):
        draw = _draw([
            _match(1),
            _match(2, league="EFL Cup", home="Chelsea", away="Leeds"),
        ])
        sharp = {"hits": {
            1: {"odds": {"1": 2.0, "X": 3.5, "2": 4.0}},
            2: {"odds": {"1": 1.8, "X": 3.8, "2": 4.8}},
        }}
        model = {"1": 0.55, "X": 0.25, "2": 0.20}
        with (patch("app.pool_strength_shadow.load_manifest",
                    return_value=_manifest()),
              patch("app.pool_strength_shadow.model_signal_version",
                    return_value="m-test"),
              patch("app.pool_strength_shadow.shadow_version",
                    return_value="ps-test"),
              patch("app.pool_strength_shadow._model_probs",
                    return_value=(model, "ok"))):
            first = pool_strength_shadow.capture_due(
                self.store, "stryktipset", draw, sharp, now=NOW)
            second = pool_strength_shadow.capture_due(
                self.store, "stryktipset", draw, sharp, now=NOW)

        self.assertEqual("h3", first["horizon"])
        self.assertEqual(2, first["captured"])
        self.assertEqual(1, first["eligible"])
        self.assertEqual(0, second["captured"])
        rows = self.store.conn.execute(
            "SELECT event_number,eligible,issue,p_blend10_1 "
            "FROM pool_strength_shadow_capture ORDER BY event_number").fetchall()
        self.assertEqual((1, 1, None), tuple(rows[0][:3]))
        self.assertIsNotNone(rows[0][3])
        self.assertEqual((2, 0, "unsupported_league", None), tuple(rows[1]))

    def test_andrad_modellversion_faller_stangt_utan_rader(self):
        with (patch("app.pool_strength_shadow.load_manifest",
                    return_value=_manifest(model_version="m-old")),
              patch("app.pool_strength_shadow.model_signal_version",
                    return_value="m-new")):
            result = pool_strength_shadow.capture_due(
                self.store, "stryktipset", _draw([_match(1)]),
                {"hits": {1: {"odds": {"1": 2, "X": 3, "2": 4}}}},
                now=NOW)
        self.assertEqual("model_source_version_changed", result["error"])
        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM pool_strength_shadow_capture").fetchone()[0])

    def test_report_mater_parad_logloss_och_blir_candidate_forst_vid_gate(self):
        for draw_number in range(1, 11):
            captured = f"2026-08-{draw_number:02d}T12:00:00Z"
            self.store.conn.execute(
                "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
                "horizon,event_number,shadow_version,model_signal_version,"
                "captured_at,target_at,delay_min,match_start,league_raw,league,"
                "home,away,eligible,issue,p_sharp_1,p_sharp_x,p_sharp_2,"
                "p_model_1,p_model_x,p_model_2,p_blend10_1,p_blend10_x,"
                "p_blend10_2,p_blend20_1,p_blend20_x,p_blend20_2) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("stryktipset", draw_number, "h3", 1, "ps-test", "m-test",
                 captured, captured, 0, captured, "Allsvenskan", "allsvenskan",
                 f"H{draw_number}", f"A{draw_number}", 1, None,
                 .40, .30, .30, .60, .20, .20, .50, .25, .25, .55, .225, .225))
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement "
                "(product,draw_number,event_number,outcome,cancelled) "
                "VALUES ('stryktipset',?,?, '1',0)", (draw_number, 1))
        self.store.conn.commit()
        manifest = _manifest(horizons=["h3"], decision=["h3"], min_events=10)
        with (patch("app.pool_strength_shadow.load_manifest",
                    return_value=manifest),
              patch("app.pool_strength_shadow.shadow_version",
                    return_value="ps-test")):
            report = pool_strength_shadow.report(self.store,
                                                  product="stryktipset")
        primary = next(metric for metric in report["horizons"]["h3"]["metrics"]
                       if metric["candidate"] == "blend10")
        self.assertEqual("candidate", report["status"])
        self.assertFalse(report["actionable"])
        self.assertEqual(10, primary["n"])
        self.assertAlmostEqual(math.log(.50 / .40),
                               primary["mean_delta_logloss"], places=6)
        self.assertIsNotNone(primary["ci90"])

    def test_familjerapport_tar_alla_slugs_men_raknar_samma_match_en_gang(self):
        values = (.40, .30, .30, .60, .20, .20,
                  .50, .25, .25, .55, .225, .225)
        for product, draw in (("topptipset", 4260),
                              ("topptipsetextra", 1856)):
            self.store.conn.execute(
                "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
                "horizon,event_number,shadow_version,model_signal_version,"
                "captured_at,target_at,delay_min,match_start,league_raw,league,"
                "home,away,eligible,issue,p_sharp_1,p_sharp_x,p_sharp_2,"
                "p_model_1,p_model_x,p_model_2,p_blend10_1,p_blend10_x,"
                "p_blend10_2,p_blend20_1,p_blend20_x,p_blend20_2) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw, "h3", 1, "ps-test", "m-test",
                 "2026-08-10T12:00:00Z", "2026-08-10T12:00:00Z", 0,
                 "2026-08-10T17:00:00Z", "Allsvenskan", "allsvenskan",
                 "Hammarby", "AIK", 1, None, *values))
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement "
                "(product,draw_number,event_number,outcome,cancelled) "
                "VALUES (?,?,1,'1',0)", (product, draw))
        self.store.conn.commit()
        with (patch("app.pool_strength_shadow.load_manifest",
                    return_value=_manifest(horizons=["h3"], decision=["h3"])),
              patch("app.pool_strength_shadow.shadow_version",
                    return_value="ps-test")):
            report = pool_strength_shadow.report(
                self.store,
                products=["topptipset", "topptipsetstryk", "topptipsetextra"])

        self.assertEqual(1, report["captured"])
        self.assertEqual(1, report["settled"])
        self.assertEqual(
            ["topptipset", "topptipsetstryk", "topptipsetextra"],
            report["products"])



class PoolStrengthStopTests(unittest.TestCase):
    """capture_due vägrar TYST vid bytt modellversion (21/8 i drift). Status
    måste då säga "stoppad" med orsak — aldrig "samlar"."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _capture(self, captured_at, event=1):
        self.store.conn.execute(
            "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
            "horizon,event_number,shadow_version,model_signal_version,"
            "captured_at,target_at,delay_min,match_start,league_raw,league,"
            "home,away,eligible,issue) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("stryktipset", 1, "h3", event, "ps-test", "m-old", captured_at,
             captured_at, 0, captured_at, "Allsvenskan", "allsvenskan",
             "Hammarby", "AIK", 0, "missing_sharp"))
        self.store.conn.commit()

    def _patched(self, current="m-new", manifest_model="m-old"):
        return (patch("app.pool_strength_shadow.load_manifest",
                      return_value=_manifest(model_version=manifest_model)),
                patch("app.pool_strength_shadow.model_signal_version",
                      return_value=current),
                patch("app.pool_strength_shadow.shadow_version",
                      return_value="ps-test"))

    def test_bytt_modellversion_ger_stoppad_med_orsak_och_senaste_capture(self):
        self._capture("2026-08-20T10:00:00Z")
        self._capture("2026-08-21T20:12:09Z", event=2)
        load, model, version = self._patched()
        with load, model, version:
            report = pool_strength_shadow.report(self.store)
            stop = pool_strength_shadow.stop_status(self.store)
        self.assertEqual("stoppad", report["status"])
        self.assertTrue(stop["stopped"])
        self.assertEqual("model_source_version_changed", stop["reason"])
        self.assertEqual("2026-08-21T20:12:09Z", stop["last_capture_at"])
        self.assertEqual("modellversionen byttes (m-old → m-new), senaste "
                         "capture 21/8 22:12", stop["text"])
        self.assertEqual(stop, report["stopped"])

    def test_samma_modellversion_samlar_som_forut(self):
        self._capture("2026-08-21T20:12:09Z")
        load, model, version = self._patched(current="m-old")
        with load, model, version:
            report = pool_strength_shadow.report(self.store)
        self.assertEqual("samlar", report["status"])
        self.assertIsNone(report["stopped"])

    def test_nadd_datagrind_star_kvar_som_candidate_aven_om_stoppad(self):
        self.store.conn.execute(
            "INSERT INTO pool_strength_shadow_capture (product,draw_number,"
            "horizon,event_number,shadow_version,model_signal_version,"
            "captured_at,target_at,delay_min,match_start,league_raw,league,"
            "home,away,eligible,issue,p_sharp_1,p_sharp_x,p_sharp_2,"
            "p_model_1,p_model_x,p_model_2,p_blend10_1,p_blend10_x,"
            "p_blend10_2,p_blend20_1,p_blend20_x,p_blend20_2) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("stryktipset", 1, "h3", 1, "ps-test", "m-old",
             "2026-08-21T12:00:00Z", "2026-08-21T12:00:00Z", 0,
             "2026-08-21T17:00:00Z", "Allsvenskan", "allsvenskan", "H", "A",
             1, None, .4, .3, .3, .6, .2, .2, .5, .25, .25, .55, .225, .225))
        self.store.conn.execute(
            "INSERT INTO pool_event_settlement "
            "(product,draw_number,event_number,outcome,cancelled) "
            "VALUES ('stryktipset',1,1,'1',0)")
        self.store.conn.commit()
        with (patch("app.pool_strength_shadow.load_manifest",
                    return_value=_manifest(model_version="m-old", horizons=["h3"],
                                           decision=["h3"], min_events=1)),
              patch("app.pool_strength_shadow.model_signal_version",
                    return_value="m-new"),
              patch("app.pool_strength_shadow.shadow_version",
                    return_value="ps-test")):
            report = pool_strength_shadow.report(self.store)
        self.assertEqual("candidate", report["status"])
        self.assertTrue(report["stopped"]["stopped"])

    def test_gater_och_testkatalogen_visar_stoppet(self):
        from app import gater, pool_tests
        self._capture("2026-08-21T20:12:09Z")
        load, model, version = self._patched()
        prognos = {"stryktipset": {"ph4_oot": 8, "ph4_oot_krav": 40}}
        with load, model, version, patch("app.main.turnover_prognos",
                                         return_value=prognos):
            rows = gater._strength(self.store)
            catalog = pool_tests.catalog(self.store)
        self.assertEqual("stoppad", rows[0]["status"])
        self.assertIn("STOPPAD: modellversionen byttes (m-old → m-new)", rows[0]["anm"])
        self.assertTrue(all(row["status"] == "stoppad" for row in rows[1:]))
        test = next(t for t in catalog["tests"] if t["id"] == "poolstyrka")
        self.assertEqual("stoppad", test["status"])
        self.assertIn("stoppad", pool_tests.RANK)


if __name__ == "__main__":
    unittest.main()
