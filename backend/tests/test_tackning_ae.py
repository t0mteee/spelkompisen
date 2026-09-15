"""Täckningspaketet 2026-09-14 (beslut a–e i overlamning-2026-09-13-pooltackning):
fönster före as-of, fördröjt bygge, delat Pinnacle-index per varv, Oddsets
namnregel i poolmatcharen och diagnostik av avslag."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import odds_provider, pinnacle, pool_dataset, sharp_service
from app.storage import Storage

UTC = dt.timezone.utc


class WindowTests(unittest.TestCase):
    def test_fonstret_ar_symmetriskt_kring_horisonten(self):
        close = dt.datetime(2026, 9, 20, 14, 0, tzinfo=UTC)
        cases = {1485: "h24", 1440: "h24", 1395: "h24", 1500: None, 1380: None,
                 225: "h3", 180: "h3", 135: "h3", 240: None, 120: None,
                 30: "m20", 20: "m20", 10: "m20", 35: None, 5: None}
        for minutes_before, expected in cases.items():
            now = close - dt.timedelta(minutes=minutes_before)
            self.assertEqual(expected, pool_dataset.horizon_window_open(close.isoformat(), now),
                             f"T−{minutes_before} min")

    def test_bygget_vantar_tills_fonstret_stangt_plus_cdn_marginal(self):
        cutoff = dt.datetime(2026, 9, 20, 11, 0, tzinfo=UTC)          # h3-as-of
        wait = pool_dataset.TIMING_TOLERANCE_MIN["h3"] + pool_dataset.BUILD_AFTER_WINDOW_MIN
        self.assertFalse(pool_dataset.horizon_ready(cutoff, "h3", cutoff))
        self.assertFalse(pool_dataset.horizon_ready(cutoff, "h3", cutoff + dt.timedelta(minutes=wait - 1)))
        self.assertTrue(pool_dataset.horizon_ready(cutoff, "h3", cutoff + dt.timedelta(minutes=wait)))
        self.assertTrue(pool_dataset.horizon_ready(cutoff, "m20", cutoff + dt.timedelta(minutes=10 + 16)))
        self.assertGreaterEqual(pool_dataset.BUILD_AFTER_WINDOW_MIN, 16)   # ≥ Pinnacles max-age 905 s

    def test_build_draw_bygger_inte_en_oppen_horisont(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                close = dt.datetime(2026, 9, 20, 14, 0, tzinfo=UTC)
                calls = []
                with patch.object(pool_dataset, "_captures", side_effect=lambda *a, **k: calls.append(a) or {}):
                    # 10 min efter h3-as-of: förut byggdes horisonten här; nu väntar den.
                    rep = pool_dataset.build_draw(store, "topptipset", 1, close.isoformat(),
                                                  now=close - dt.timedelta(minutes=170))
                self.assertEqual(0, rep["built"])
                self.assertEqual([], [a for a in calls if a[4] == pool_dataset._iso(close - dt.timedelta(minutes=180))])
            finally:
                store.close()


class NameRuleTests(unittest.TestCase):
    def test_obekraftade_delnamn_ar_inte_samma_klubb(self):
        for a, b in (("Inter", "Inter Miami"), ("Barcelona", "Barcelona SC"),
                     ("United", "Manchester United")):
            with self.subTest(a=a, b=b):
                self.assertEqual(0.0, odds_provider.team_sim(a, b))
                self.assertEqual(0.0, odds_provider.team_sim(b, a))
        self.assertEqual(1.0, odds_provider.team_sim("Barcelona SC", "Barcelona SC"))

    def test_exakt_inter_vinner_oavsett_indexordning(self):
        start = "2026-09-15T18:00:00Z"
        wrong = dict(home="Inter Miami", away="Lazio", start=start,
                     odds={"1": 6.0, "X": 4.0, "2": 1.5})
        right = dict(home="Inter", away="Lazio", start=start,
                     odds={"1": 1.5, "X": 4.0, "2": 6.0})
        for index in ([wrong, right], [right, wrong]):
            hit = pinnacle.match_index("Inter", "Lazio", None, None, index, start)
            self.assertEqual("Inter", hit["home"])
            self.assertEqual(1.5, hit["odds"]["1"])
            self.assertEqual(odds_provider.POOL_MATCH_VERSION, hit["match_version"])

    def test_flera_kandidater_avstar_oavsett_ordning_och_pris(self):
        start = "2026-09-15T18:00:00Z"
        first = dict(home="Inter", away="Lazio", start=start,
                     odds={"1": 1.5, "X": 4.0, "2": 6.0})
        second = {**first, "start": "2026-09-16T18:00:00Z",
                  "odds": {"1": 6.0, "X": 4.0, "2": 1.5}}
        for index in ([first, second], [second, first], [first, first]):
            diag = {}
            self.assertIsNone(pinnacle.match_index("Inter", "Lazio", None, None, index, start, diag))
            self.assertEqual("ambiguous", diag["reason"])
            self.assertEqual(2, diag["qualifying_candidates"])

    def test_tvetydig_orientering_avstar_men_entydig_speglar_odds(self):
        start = "2026-09-15T18:00:00Z"
        odds = {"1": 1.5, "X": 4.0, "2": 6.0}
        # Samma landslagsalternativ på båda sidor gör båda orienteringarna möjliga.
        diag = {}
        self.assertIsNone(pinnacle.match_index("Sweden", "Sverige", "SWE", "SWE",
            [dict(home="Sweden", away="Sweden", start=start, odds=odds)], start, diag))
        self.assertEqual("ambiguous", diag["reason"])
        hit = pinnacle.match_index("Lazio", "Inter", None, None,
            [dict(home="Inter", away="Lazio", start=start, odds=odds)], start)
        self.assertTrue(hit["swapped"])
        self.assertEqual({"1": 6.0, "X": 4.0, "2": 1.5}, hit["odds"])

    def test_kortnamn_mot_fullt_klubbnamn_ar_traff(self):
        for a, b in (("Leeds", "Leeds United"), ("Nottingham", "Nottingham Forest"),
                     ("Tottenham", "Tottenham Hotspur"), ("Frankfurt", "Eintracht Frankfurt"),
                     ("Sabah Masazir", "Sabah FK"), ("Hull", "Hull City"), ("QPR", "Queens Park Rangers")):
            self.assertEqual(1.0, odds_provider.team_sim(a, b), (a, b))
        self.assertEqual(1.0, odds_provider._best_side(["Leeds", None], "Leeds United"))

    def test_diagnostikens_forsta_fynd_ar_alias(self):
        # Bekräftade 2026-09-14 ur pool_match_diagnostic: samma motståndare, samma avspark.
        for a, b in (("CR Brasil", "CRB"), ("Royale Union SG", "Union Saint-Gilloise"),
                     ("Milton Keynes Dons", "MK Dons")):
            self.assertEqual(1.0, odds_provider.team_sim(a, b), (a, b))

    def test_truppmarkorer_och_kanda_falska_par_falls(self):
        self.assertEqual(0.0, odds_provider.team_sim("Inter", "Inter U23"))
        self.assertEqual(0.0, odds_provider.team_sim("Como Women", "Como"))
        self.assertEqual(frozenset({"u21"}), odds_provider._squad("sweden u21"))
        self.assertEqual(0.0, odds_provider.team_sim("Egersund", "Haugesund"))   # TEAM_REJECTED_LINKS
        self.assertLess(odds_provider.team_sim("Wigan", "Wycombe"), 0.6)
        self.assertEqual(0.0, odds_provider.team_sim("", "Leeds"))

    def test_matcharen_tar_de_fyra_kanda_paren_och_diagnosticerar_avslag(self):
        start = "2026-09-05T14:00:00Z"
        index = [{"home": h, "away": a, "start": start, "odds": {"1": 2.0, "X": 3.4, "2": 3.6},
                  "odds_source": "pinnacle", "total": None}
                 for h, a in (("Brighton", "Leeds United"), ("Nottingham Forest", "Tottenham Hotspur"),
                              ("Mainz 05", "Eintracht Frankfurt"), ("Manchester United", "Sabah FK"),
                              ("Wycombe", "Bolton"))]
        for home, away in (("Brighton", "Leeds"), ("Nottingham", "Tottenham"),
                           ("Mainz", "Frankfurt"), ("Manchester United", "Sabah Masazir")):
            hit = pinnacle.match_index(home, away, None, None, index, "2026-09-05T16:00:00+02:00")
            self.assertIsNotNone(hit, (home, away))
            self.assertGreaterEqual(hit["confidence"], odds_provider.COMBINED_MIN)
        diag = {}
        miss = pinnacle.match_index("Wigan", "Bolton", None, None, index, "2026-09-05T16:00:00+02:00", diag)
        self.assertIsNone(miss)
        self.assertEqual(("Wycombe", "Bolton"), (diag["cand_home"], diag["cand_away"]))
        self.assertEqual(1.0, diag["side_away"])
        self.assertLess(diag["side_home"], odds_provider.HOME_AWAY_MIN)
        # Utanför tidsfönstret finns ingen kandidat alls — ingen diagnostik heller.
        far = {}
        self.assertIsNone(pinnacle.match_index("Wigan", "Bolton", None, None, index, "2026-09-09T16:00:00+02:00", far))
        self.assertEqual({}, far)


def _draw(matches):
    return SimpleNamespace(draw_number=4969, matches=[
        SimpleNamespace(event_number=i, home=h, away=a, home_iso=None, away_iso=None,
                        match_start="2026-09-05T16:00:00+02:00")
        for i, (h, a) in enumerate(matches, start=1)])


class VarvIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        self.fetches = 0
        index = [{"home": "Brighton", "away": "Leeds United", "start": "2026-09-05T14:00:00Z",
                  "odds": {"1": 2.0, "X": 3.4, "2": 3.6}, "odds_source": "pinnacle", "total": None}]
        tests = self

        class FakePinnacle:
            last_age_s = 120
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def soccer_index(self, include_without_odds=False):
                tests.fetches += 1
                return index
        self.patches = [patch.object(sharp_service, "Pinnacle", FakePinnacle),
                        patch.object(sharp_service, "Storage", lambda *a, **k: Storage(self.db))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_ett_index_per_varv_delas_av_alla_omgangar(self):
        varv = sharp_service.VarvIndex()
        first = sharp_service.collect_pinnacle("stryktipset", draw=_draw([("Brighton", "Leeds")]), varv=varv)
        second = sharp_service.collect_pinnacle("topptipset", draw=_draw([("Brighton", "Leeds"), ("Wigan", "Bolton")]), varv=varv)
        self.assertEqual(1, self.fetches)
        self.assertFalse(first["shared_index"]); self.assertTrue(second["shared_index"])
        self.assertEqual(first["fetched_at"], second["fetched_at"])   # samma observation, samma tid
        self.assertEqual({1: "matched"}, first["status"])
        self.assertEqual({1: "matched", 2: "not_listed"}, second["status"])
        self.assertEqual("Brighton", second["diagnostics"][2]["cand_home"])

    def test_tvetydighet_sparas_som_egen_status_utan_odds(self):
        draw = _draw([("Brighton", "Leeds")])
        varv = sharp_service.VarvIndex()
        sharp_service.collect_pinnacle("stryktipset", draw=draw, varv=varv, cache=False)
        varv.index = varv.index + varv.index
        result = sharp_service.collect_pinnacle("stryktipset", draw=draw, varv=varv)
        self.assertEqual({1: "ambiguous"}, result["status"])
        self.assertEqual({}, result["hits"])
        store = Storage(self.db)
        try:
            pool_dataset.record_sharp_capture(store, "stryktipset", draw, result)
            rows = store.conn.execute(
                "SELECT status, odds_complete FROM pool_market_capture").fetchall()
            self.assertEqual([("ambiguous", 0)], [tuple(row) for row in rows])
            self.assertEqual(1, store.conn.execute(
                "SELECT COUNT(*) FROM pool_match_diagnostic").fetchone()[0])
        finally:
            store.close()

    def test_sparren_galler_bara_forsta_hamtningen_och_forbigas_av_varvets_fonster(self):
        store = Storage(self.db)
        store.meta_set(sharp_service._PINNACLE_LAST_FETCH_KEY,
                       dt.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        store.close()
        skipped = sharp_service.collect_pinnacle("stryktipset", draw=_draw([("Brighton", "Leeds")]),
                                                 varv=sharp_service.VarvIndex())
        self.assertIn("skipped", skipped)
        self.assertEqual(0, self.fetches)
        forced = sharp_service.VarvIndex(force=True)
        got = sharp_service.collect_pinnacle("stryktipset", draw=_draw([("Brighton", "Leeds")]), varv=forced)
        self.assertEqual({1: "matched"}, got["status"])
        self.assertEqual(1, self.fetches)

    def test_diagnostiken_bokfors_och_raknar_varv(self):
        varv = sharp_service.VarvIndex()
        for _ in range(2):
            sharp_service.collect_pinnacle("stryktipset", draw=_draw([("Wigan", "Bolton")]), varv=varv)
        store = Storage(self.db)
        try:
            rows = store.conn.execute(
                "SELECT event_number, svs_home, cand_home, cand_away, side_home, side_away, n_seen "
                "FROM pool_match_diagnostic").fetchall()
        finally:
            store.close()
        rows = [tuple(r) for r in rows]
        self.assertEqual([(1, "Wigan", "Brighton", "Leeds United", rows[0][4], rows[0][5], 2)], rows)
        self.assertLess(rows[0][4], odds_provider.HOME_AWAY_MIN)
        self.assertEqual(1, self.fetches)

    def test_kallfel_delar_varvet_utan_falska_captures(self):
        with patch.object(sharp_service, "Pinnacle") as pin:
            pin.return_value.__enter__.return_value.soccer_index.side_effect = RuntimeError("source unavailable")
            varv = sharp_service.VarvIndex(force=True)
            first = sharp_service.collect_pinnacle("stryktipset", draw=_draw([("Brighton", "Leeds")]), varv=varv)
            second = sharp_service.collect_pinnacle("topptipset", draw=_draw([("Brighton", "Leeds")]), varv=varv)
            self.assertEqual(1, pin.call_count)
            self.assertEqual(first["pinnacle_error"], second["pinnacle_error"])
            store = Storage(self.db)
            try:
                self.assertEqual(0, pool_dataset.record_sharp_capture(store, "topptipset", second["draw"], second))
            finally:
                store.close()
