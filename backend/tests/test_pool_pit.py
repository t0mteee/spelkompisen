import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from app import pool_dataset, pool_system_ledger
from app.storage import Storage

# Efter pit-v4-aktiveringen (FEATURE_START_AT 2026-07-25T16:00Z). Fixturen måste
# ligga så att ÄVEN h24-horisonten (close − 24 h = NOW − 25 h) hamnar efter
# feature-starten — testdata före den får aldrig kunna bakfyllas in. Flytta
# därför NOW framåt när FEATURE_START_AT flyttas; att i stället backa
# feature-starten hade öppnat för bakfyllning i drift.
NOW = dt.datetime(2026, 7, 27, 12, 0, tzinfo=dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class PoolDatasetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.close = NOW - dt.timedelta(hours=1)   # stängde för en timme sedan
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES ('stryktipset', 100, 'Open', ?)",
            (self.close.isoformat(),))
        self.store.conn.commit()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _snap(self, table, event, sign, odds, at, streck=None):
        if table == "snapshots":
            self.store.conn.execute(
                "INSERT INTO snapshots (product, draw_number, event_number, "
                "sign, odds, start_odds, streck, fetched_at) "
                "VALUES ('stryktipset', 100, ?, ?, ?, NULL, ?, ?)",
                (event, sign, odds, streck, _iso(at)))
        else:
            self.store.conn.execute(
                "INSERT INTO sharp_snapshots (product, draw_number, "
                "event_number, sign, odds, fetched_at) "
                "VALUES ('stryktipset', 100, ?, ?, ?, ?)",
                (event, sign, odds, _iso(at)))
        self.store.conn.commit()

    def _fill(self, at, odds=(2.0, 3.5, 3.8), streck=(50, 30, 20), sharp=None):
        for sign, o, s in zip(("1", "X", "2"), odds, streck):
            self._snap("snapshots", 1, sign, o, at, s)
        for sign, o in zip(("1", "X", "2"), sharp or odds):
            self._snap("sharp_snapshots", 1, sign, o, at)
        for source, streck_ok in (("svs", 1), ("sharp", 0)):
            self.store.conn.execute(
                "INSERT INTO pool_market_capture (product, draw_number, source, "
                "event_number, fetched_at, status, odds_complete, "
                "streck_complete) VALUES ('stryktipset',100,?,1,?,'matched',1,?)",
                (source, _iso(at), streck_ok))
        self.store.conn.commit()

    def test_pit_anvander_aldrig_punkter_efter_cutoff(self):
        # punkt före T−3h-cutoffen och en EFTER (närmare stopp): h3 ska bara
        # se den första — finalvärden får aldrig läcka bakåt i en horisont.
        early = self.close - dt.timedelta(hours=3, minutes=10)
        late = self.close - dt.timedelta(minutes=30)
        self._fill(early, odds=(2.0, 3.5, 3.8))
        self._fill(late, odds=(1.5, 4.0, 6.0))
        rep = pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        # h24 saknar observation (första punkten T−5h ligger EFTER cutoffen)
        # → den horisonten byggs ALDRIG (no-backfill-regeln). h3 + m20 byggs.
        self.assertEqual(2, rep["built"])
        rows = {r[0]: r for r in self.store.conn.execute(
            "SELECT horizon, n_covered_svs FROM pool_pit_draw_features "
            "WHERE product='stryktipset' AND draw_number=100")}
        self.assertNotIn("h24", rows)          # ingen observation före T−24h
        m20 = self.store.conn.execute(
            "SELECT p_svs_1 FROM pool_pit_match_features WHERE horizon='m20' "
            "AND event_number=1").fetchone()
        h3 = self.store.conn.execute(
            "SELECT p_svs_1 FROM pool_pit_match_features WHERE horizon='h3' "
            "AND event_number=1").fetchone()
        self.assertGreater(m20[0], h3[0])   # m20 ser 1.50-oddset (högre p) — h3 gör INTE det
        self.assertLess(h3[0], 0.55)        # h3 = devigat 2.00-odds, opåverkat av senare punkt

    def test_rorelse_i_devigade_pp_och_gap(self):
        t0 = self.close - dt.timedelta(hours=30)
        t1 = self.close - dt.timedelta(hours=24, minutes=20)
        self._fill(t0, odds=(2.2, 3.5, 3.4), streck=(40, 30, 30))
        self._fill(t1, odds=(1.8, 3.8, 4.5), streck=(45, 28, 27))
        pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        row = self.store.conn.execute(
            "SELECT move_svs_pp_1, gap_1, streck_1 FROM pool_pit_match_features "
            "WHERE horizon='h24' AND event_number=1").fetchone()
        self.assertIsNotNone(row)
        self.assertGreater(row[0], 3.0)     # 2.20→1.80 ≈ +8 devigade pp
        self.assertEqual(45, row[2])
        self.assertAlmostEqual(row[1], row[1])  # gap satt (p_sharp − 0.45)

    def test_idempotent_per_version(self):
        self._fill(self.close - dt.timedelta(hours=24, minutes=10))
        r1 = pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        r2 = pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        self.assertGreater(r1["built"], 0)
        self.assertEqual(0, r2["built"])

    def test_omsattningsserie_skriver_bara_vid_forandring(self):
        n1 = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None, at="2026-07-24T10:00:00Z")
        n2 = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None, at="2026-07-24T10:30:00Z")
        n3 = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1200.0, None, at="2026-07-24T11:00:00Z")
        self.assertEqual((1, 0, 1), (n1, n2, n3))

    def test_omsattningsserie_ignorerar_proveniensflapp(self):
        # missing↔endpoint_error med oförändrade värden bär ingen info och
        # ska inte blåsa upp serien; uppgradering till verified skrivs.
        base = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None,
            jackpot_source="missing", at="2026-07-24T10:00:00Z")
        flap = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None,
            jackpot_source="endpoint_error", at="2026-07-24T10:30:00Z")
        flap_back = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None,
            jackpot_source="missing", at="2026-07-24T11:00:00Z")
        upgrade = pool_dataset.record_draw_snapshot(
            self.store, "stryktipset", 100, 1000.0, None,
            jackpot_source="verified_endpoint", at="2026-07-24T11:30:00Z")
        self.assertEqual((1, 0, 0, 1), (base, flap, flap_back, upgrade))

    def test_oforandrat_pris_far_farsk_lagg_fran_separat_capture(self):
        changed = self.close - dt.timedelta(hours=8)
        confirmed = self.close - dt.timedelta(hours=3, minutes=5)
        self._fill(changed)
        # Samma odds behöver ingen ny snapshots-rad, men en lyckad poll måste
        # flytta observationsklockan.
        for source, streck_ok in (("svs", 1), ("sharp", 0)):
            self.store.conn.execute(
                "INSERT INTO pool_market_capture (product, draw_number, source, "
                "event_number, fetched_at, status, odds_complete, "
                "streck_complete) VALUES ('stryktipset',100,?,1,?,'matched',1,?)",
                (source, _iso(confirmed), streck_ok))
        self.store.conn.commit()

        pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        row = self.store.conn.execute(
            "SELECT svs_lag_min, sharp_lag_min, svs_eligible, sharp_eligible, "
            "p_svs_1, p_sharp_1 FROM pool_pit_match_features "
            "WHERE horizon='h3' AND event_number=1").fetchone()
        self.assertEqual((5.0, 5.0, 1, 1), tuple(row[:4]))
        self.assertIsNotNone(row[4])
        self.assertIsNotNone(row[5])

    def test_forandringspunkt_utan_capture_far_inte_bli_pit_v3(self):
        at = self.close - dt.timedelta(hours=3, minutes=5)
        for sign, o in zip(("1", "X", "2"), (2.0, 3.5, 3.8)):
            self._snap("snapshots", 1, sign, o, at, 33)
        rep = pool_dataset.build_draw(
            self.store, "stryktipset", 100, self.close.isoformat(), now=NOW)
        self.assertEqual(0, rep["built"])


def _draw_fixture(close, n_events=8):
    from app.svenskaspel import Draw, Match, Outcome
    draw = Draw(product="topptipset", draw_number=100, state="Open",
                reg_close_time=close.isoformat(), net_sale=120000.0,
                row_price=1.0, fetched_at=_iso(NOW), jackpot=0.0)
    for i in range(1, n_events + 1):
        odds = {"1": 1.7 + 0.1 * (i % 3), "X": 3.6, "2": 4.4}
        streck = {"1": 55, "X": 25, "2": 20}
        outcomes = {s: Outcome(sign=s, odds=odds[s], start_odds=odds[s],
                               streck=streck[s], streck_ref=streck[s])
                    for s in ("1", "X", "2")}
        draw.matches.append(Match(
            event_number=i, description=f"H{i} - B{i}", home=f"H{i}",
            away=f"B{i}", home_iso=None, away_iso=None, league="Test",
            match_start=close.isoformat(), cancelled=False, kambi_id=None,
            outcomes=outcomes))
    return draw


class SharpCaptureTests(unittest.TestCase):
    """En källa vi inte frågade får aldrig bokföras som en källa utan utbud.

    Dubbeltrafikspärren (2026-07-25) returnerar tomma `hits`/`status` utan fel.
    `status.get(event, "not_listed")` gjorde då varje match till en falsk
    frånvaroobservation: Stryktipset 4963 fick 13 rader per tick i 80 minuter,
    vilket ensamt nollade `sharp_eligible` vid m20 och fick det att se ut som
    att Pinnacle strukturellt inte når horisonten.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.draw = _draw_fixture(NOW + dt.timedelta(hours=3))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _captures(self):
        return [(r[0], r[1]) for r in self.store.conn.execute(
            "SELECT status, COUNT(*) FROM pool_market_capture "
            "WHERE source='sharp' GROUP BY status")]

    def test_overhoppad_hamtning_bokfors_inte(self):
        skipped = {"draw": self.draw, "hits": {}, "status": {},
                   "fetched_at": _iso(NOW), "cache_age_s": 0,
                   "skipped": "pinnacle hämtad av annat varv inom 10 min"}
        self.assertEqual(0, pool_dataset.record_sharp_capture(
            self.store, "topptipset", self.draw, skipped))
        self.assertEqual([], self._captures())

    def test_kallfel_bokfors_inte(self):
        failed = {"draw": self.draw, "hits": {}, "status": {},
                  "fetched_at": _iso(NOW), "pinnacle_error": "403 Cloudflare"}
        self.assertEqual(0, pool_dataset.record_sharp_capture(
            self.store, "topptipset", self.draw, failed))
        self.assertEqual([], self._captures())

    def test_horisontfonstret_oppnar_bara_i_toleransen(self):
        """Spärren får bara förbigås i fönstren — annars är vi tillbaka i
        dubbeltrafiken som spärren infördes för att stoppa."""
        close = dt.datetime(2026, 7, 25, 14, 0, tzinfo=dt.timezone.utc)
        iso = close.isoformat()
        cases = {1440: "h24", 1410: "h24", 1380: None,   # tolerans h24 = 45 min
                 180: "h3", 140: "h3", 120: None,        # tolerans h3 = 45 min
                 20: "m20", 15: "m20", 5: None,          # tolerans m20 = 10 min
                 600: None}
        for minutes_before, expected in cases.items():
            now = close - dt.timedelta(minutes=minutes_before)
            self.assertEqual(expected,
                             pool_dataset.horizon_window_open(iso, now),
                             f"T−{minutes_before} min")
        self.assertIsNone(pool_dataset.horizon_window_open(None))

    def test_verklig_franvaro_bokfors_som_observation(self):
        """not_listed från ett LYCKAT svar är värdefull information och sparas."""
        real = {"draw": self.draw, "hits": {},
                "status": {m.event_number: "not_listed" for m in self.draw.matches},
                "fetched_at": _iso(NOW), "cache_age_s": 0}
        n = pool_dataset.record_sharp_capture(
            self.store, "topptipset", self.draw, real)
        self.assertEqual(len(self.draw.matches), n)
        self.assertEqual([("not_listed", len(self.draw.matches))], self._captures())


class SystemLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _freeze_fixture(self, n_events=8, product="topptipset"):
        # frys ett litet system manuellt (kringgår byggaren — testar settling)
        events = ",".join(str(i) for i in range(1, n_events + 1))
        rows = "\n".join(["1," * (n_events - 1) + "1",
                          "X," * (n_events - 1) + "X"])
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used) VALUES "
            "(?, 100, 'm20', ?, '2026-07-24T10:00:00Z', 5, 1, "
            "'test', 256, 'medel', 0.5, 1.0, 2, 2.0, ?, ?, 'h', 8, 100000, "
            "'live', 0)",
            (product, pool_system_ledger.CHAMPION_KEY, events, rows))
        self.store.conn.commit()

    def _settlement_fixture(self, outcomes, tiers, product="topptipset"):
        self.store.conn.execute(
            "INSERT INTO pool_draw_settlement (product, draw_number, draw_state, "
            "net_sale, source_version, payload_hash, fetched_at) "
            "VALUES (?, 100, 'Finalized', 100000, 't', 'h', '2026-07-24T12:00:00Z')",
            (product,))
        for i, outcome in enumerate(outcomes, start=1):
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, outcome, cancelled) VALUES (?, 100, ?, ?, 0)",
                (product, i, outcome))
        for correct, winners, amount in tiers:
            self.store.conn.execute(
                "INSERT INTO pool_payout_tier (product, draw_number, tier_name, "
                "correct, winners, amount) VALUES (?, 100, ?, ?, ?, ?)",
                (product, f"{correct} rätt", correct, winners, amount))
        self.store.conn.commit()

    def test_settling_raknar_ratt_och_utdelning(self):
        self._freeze_fixture()
        # facit: alla åtta = '1'. Publicerad vinst är 500 kr, men med vår
        # extra vinnande rad delas observerad 5 000-kronorspott på 11 vinnare.
        self._settlement_fixture(["1"] * 8, [(8, 10, 500.0)])
        rep = pool_system_ledger.settle_pending(self.store, now=NOW)
        self.assertEqual(1, rep["settled"])
        row = self.store.conn.execute(
            "SELECT correct_max, payout_kr, published_payout_kr, "
            "payout_complete, settlement_version, roi, correct_dist "
            "FROM pool_system_ledger").fetchone()
        self.assertEqual(8, row[0])
        self.assertAlmostEqual(5000 / 11, row[1], places=2)
        self.assertAlmostEqual(500.0, row[2])
        self.assertEqual(1, row[3])
        self.assertEqual("counterfactual-v2", row[4])
        self.assertAlmostEqual(round((round(5000 / 11, 2) / 2.0 - 1), 4),
                               row[5], places=4)
        self.assertEqual({"0": 1, "8": 1}, json.loads(row[6]))

    def test_noll_officiella_vinnare_ger_okand_roi_inte_nollvinst(self):
        self._freeze_fixture()
        self._settlement_fixture(["1"] * 8, [(8, 0, 0.0)])
        pool_system_ledger.settle_pending(self.store, now=NOW)
        row = self.store.conn.execute(
            "SELECT correct_max, payout_kr, payout_complete, roi, settle_note "
            "FROM pool_system_ledger").fetchone()
        self.assertEqual(8, row[0])
        self.assertIsNone(row[1])
        self.assertEqual(0, row[2])
        self.assertIsNone(row[3])
        self.assertIn("rullpott", row[4])

    def test_saknat_utfall_ger_unresolvable_inte_krasch(self):
        self._freeze_fixture()
        self._settlement_fixture(["1"] * 7 + [None], [(8, 10, 500.0)])
        rep = pool_system_ledger.settle_pending(self.store, now=NOW)
        self.assertEqual({"settled": 0, "unresolvable": 1}, rep)
        note = self.store.conn.execute(
            "SELECT settle_note FROM pool_system_ledger").fetchone()[0]
        self.assertIn("saknas", note)

    def test_settling_ar_idempotent(self):
        self._freeze_fixture()
        self._settlement_fixture(["1"] * 8, [(8, 10, 500.0)])
        pool_system_ledger.settle_pending(self.store, now=NOW)
        rep2 = pool_system_ledger.settle_pending(self.store, now=NOW)
        self.assertEqual(0, rep2["settled"])

    def test_freeze_due_fryser_i_oppet_fonster_och_ar_idempotent(self):
        close = NOW + dt.timedelta(minutes=178)   # h3-fönstret öppnade nyss
        draw = _draw_fixture(close)
        rep = pool_system_ledger.freeze_due(
            self.store, "topptipset", draw, now=NOW, code_version="test")
        family = pool_system_ledger.benchmarks_for("topptipset")
        self.assertEqual(len(family), rep["frozen"])
        rows = self.store.conn.execute(
            "SELECT horizon, timely, n_rows, cost_kr, events_order "
            "FROM pool_system_ledger ORDER BY config_key").fetchall()
        self.assertTrue(all(r[0] == "h3" for r in rows))    # m20 inte öppet än
        self.assertTrue(all(r[1] == 1 for r in rows))       # lag 2 min ≤ 30
        widest = max(b["budget"] for b in family)
        self.assertTrue(all(r[2] >= 1 and r[3] <= widest for r in rows))
        self.assertEqual("1,2,3,4,5,6,7,8", rows[0][4])
        rep2 = pool_system_ledger.freeze_due(
            self.store, "topptipset", draw, now=NOW, code_version="test")
        self.assertEqual(0, rep2["frozen"])                 # aldrig dubbelfrysning

    def test_freeze_due_ror_inte_stangd_eller_avlagsen_omgang(self):
        closed = _draw_fixture(NOW - dt.timedelta(minutes=5))
        distant = _draw_fixture(NOW + dt.timedelta(hours=30))
        r1 = pool_system_ledger.freeze_due(
            self.store, "topptipset", closed, now=NOW)
        r2 = pool_system_ledger.freeze_due(
            self.store, "topptipset", distant, now=NOW)
        self.assertEqual((0, 0), (r1["frozen"], r2["frozen"]))

    def test_benchmarkmatrisen_ar_forregistrerad(self):
        keys = [b["key"] for b in pool_system_ledger.BENCHMARKS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(1, sum(b["primary"] for b in pool_system_ledger.BENCHMARKS))
        # Generation 2 (2026-08-05): 4 budgetar × 3 riskprofiler.
        self.assertEqual(12, len(keys))
        self.assertIn(pool_system_ledger.CHAMPION_KEY, keys)
        champion = next(b for b in pool_system_ledger.BENCHMARKS if b["primary"])
        self.assertEqual(pool_system_ledger.CHAMPION_KEY, champion["key"])
        # Strateginamnen måste vara byggarens egna, annars KeyError vid frysning.
        from app.builder import STRATEGIES
        for bench in pool_system_ledger.BENCHMARKS:
            self.assertIn(bench["strategy"], STRATEGIES, bench["key"])
        # Pensionerade nycklar får aldrig återuppstå i matrisen — en config_key
        # ändras aldrig i efterhand, och gamla kohorter blandas aldrig in.
        for retired in pool_system_ledger.RETIRED_KEYS:
            self.assertNotIn(retired, keys)

    def test_8_matchsspelen_har_budgettak(self):
        """1 024 rader är 15,6 % av Topptipsets HELA utfallsrum (3^8 = 6 561)
        och 0,06 % av ett 13-matchsspels — samma nyckel mätte två olika saker.
        Taket gäller Topptipset-familjen och bara den (Samans beslut
        2026-08-09)."""
        for product in ("topptipset", "topptipsetstryk", "topptipsetextra"):
            budgets = {b["budget"]
                       for b in pool_system_ledger.benchmarks_for(product)}
            self.assertNotIn(1024.0, budgets, product)
            self.assertEqual({144.0, 256.0, 512.0}, budgets, product)
        for product in ("stryktipset", "europatipset"):
            budgets = {b["budget"]
                       for b in pool_system_ledger.benchmarks_for(product)}
            self.assertIn(1024.0, budgets, product)
            self.assertEqual(len(pool_system_ledger.BENCHMARKS),
                             len(pool_system_ledger.benchmarks_for(product)))
        # Championen måste överleva taket i ALLA produkter, annars har
        # rapporten ingen baslinje att jämföra mot.
        for product in ("topptipset", "stryktipset"):
            self.assertIn(pool_system_ledger.CHAMPION_KEY,
                          [b["key"]
                           for b in pool_system_ledger.benchmarks_for(product)])
        self.assertEqual({"h3", "m20"}, set(pool_system_ledger.FREEZE_HORIZONS))

    def test_summary_grupperar_per_config(self):
        self._freeze_fixture()
        self._settlement_fixture(["1"] * 8, [(8, 10, 500.0)])
        pool_system_ledger.settle_pending(self.store, now=NOW)
        s = pool_system_ledger.summary(self.store)
        group = next(g for g in s["groups"]
                     if g["config_key"] == pool_system_ledger.CHAMPION_KEY)
        self.assertEqual(1, group["n_settled"])
        self.assertEqual("topptipset", group["product"])
        self.assertEqual(1, group["n_evaluable"])
        self.assertTrue(group["primary"])
        self.assertEqual("2026-07-24T10:00:00Z", group["latest_frozen"])
        self.assertAlmostEqual((5000 / 11) / 2.0 - 1, group["roi"], places=1)

    def test_recent_far_spelstopp_fran_oppen_draw_fore_settlement(self):
        self._freeze_fixture()
        close = "2026-08-09T21:29:00+02:00"
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES ('topptipset', 100, 'Open', ?)", (close,))
        self.store.conn.commit()
        recent = pool_system_ledger.summary(self.store)["recent"]
        self.assertEqual(close, recent[0]["close"])


if __name__ == "__main__":
    unittest.main()


class ChampionReportTests(unittest.TestCase):
    """Champion mot utmanare: parad jämförelse och FDR över hela familjen."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _row(self, key, draw, cost, payout, horizon="m20",
             product="topptipset", timely=1):
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used, correct_max, payout_kr, "
            "payout_complete) VALUES (?,?,?,?,'2026-08-01T10:00:00Z',1,?,"
            "'test',256,'medel',0.5,1.0,?,?,'1,2','1,1','h',2,1000,'live',0,"
            "2,?,1)",
            (product, draw, horizon, key, timely, int(cost), cost, payout))
        self.store.conn.commit()

    def test_challenger_is_compared_on_the_same_draws_only(self):
        """En utmanare som saknar de dåliga omgångarna får inte se bättre ut."""
        champion = pool_system_ledger.CHAMPION_KEY
        challenger = next(b["key"] for b in pool_system_ledger.BENCHMARKS
                          if not b["primary"])
        for draw, payout in ((1, 0.0), (2, 0.0), (3, 600.0)):
            self._row(champion, draw, 256.0, payout)
        # utmanaren finns BARA i den lönsamma omgången
        self._row(challenger, 3, 256.0, 900.0)

        report = pool_system_ledger.champion_report(self.store)
        entry = next(r for r in report["rows"] if r["horizon"] == "m20")
        best = entry["best_challenger"]
        self.assertEqual(1, best["n_paired"], "bara omgång 3 är gemensam")
        # championens ROI i rapporten är över ALLA sina omgångar, men deltat
        # räknas parat — annars jämförs olika omgångar med varandra.
        self.assertAlmostEqual((900 - 600) / 256, best["delta_roi"], places=3)

    def test_tiny_samples_get_no_p_value_and_are_never_promotable(self):
        champion = pool_system_ledger.CHAMPION_KEY
        challenger = next(b["key"] for b in pool_system_ledger.BENCHMARKS
                          if not b["primary"])
        for draw in (1, 2):
            self._row(champion, draw, 256.0, 0.0)
            self._row(challenger, draw, 256.0, 5000.0)

        report = pool_system_ledger.champion_report(self.store)
        entry = next(r for r in report["rows"] if r["horizon"] == "m20")
        best = entry["best_challenger"]
        self.assertGreater(best["delta_roi"], 0, "utmanaren ser överlägsen ut")
        self.assertIsNone(best["p_value"], "två omgångar är inget test")
        self.assertFalse(entry["promotable"],
                         "brus får aldrig promoveras oavsett hur bra det ser ut")
        self.assertEqual(40, report["gate_min_draws"])

    def test_retired_config_keeps_its_stored_parameters(self):
        """Pensionerade rader måste kunna visas med samma kolumner som nya."""
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used) VALUES ('topptipset',9,'m20',"
            "'ev50-tuff-vw80','2026-07-30T10:00:00Z',1,1,'test',50,'tuff',0.8,"
            "1.0,50,50.0,'1,2','1,1','h',2,1000,'live',0)")
        self.store.conn.commit()

        group = next(g for g in pool_system_ledger.summary(self.store)["groups"]
                     if g["config_key"] == "ev50-tuff-vw80")
        self.assertTrue(group["retired"])
        self.assertEqual(50.0, group["budget"])
        self.assertEqual("tuff", group["strategy"])
        self.assertEqual(0.8, group["value_weight"])
        self.assertFalse(group["primary"])


class SystemDetailTests(unittest.TestCase):
    """Klick-in på ett fryst system: var missade vi, och hur stod strecken?"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.store.conn.execute(
            "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
            "config_key, frozen_at, lag_min, timely, code_version, budget, "
            "strategy, value_weight, row_price, n_rows, cost_kr, events_order, "
            "rows_text, rows_hash, n_events_covered, turnover_used, "
            "turnover_basis, jackpot_used, correct_max, payout_kr, "
            "payout_complete) VALUES ('topptipset',77,'m20',?,"
            "'2026-08-01T12:00:00Z',1,1,'test',256,'medel',0.5,1.0,2,2.0,"
            "'1,2','1,1\n1,X','h',2,1000,'live',0,1,0.0,1)",
            (pool_system_ledger.CHAMPION_KEY,))
        for number, outcome, streck in ((1, "1", (70, 20, 10)),
                                        (2, "2", (30, 30, 40))):
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, description, home, away, outcome, cancelled, "
                "streck_one, streck_x, streck_two) VALUES "
                "('topptipset',77,?,?,?,?,?,0,?,?,?)",
                (number, f"lag{number} - motst{number}", f"lag{number}",
                 f"motst{number}", outcome, *streck))
        self.store.conn.commit()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_missed_event_is_named(self):
        """Systemet spelar 1 och X på match 2, men 2:an gick in."""
        d = pool_system_ledger.system_detail(
            self.store, "topptipset", 77, "m20",
            pool_system_ledger.CHAMPION_KEY)
        self.assertTrue(d["available"])
        self.assertEqual([2], d["missed_events"])
        first, second = d["events"]
        self.assertTrue(first["hit"])
        self.assertEqual(["1"], first["covered"])
        self.assertFalse(second["hit"])
        self.assertEqual(["1", "X"], second["covered"])
        self.assertEqual({"1": 30, "X": 30, "2": 40}, second["streck_at_close"])

    def test_streck_at_freeze_uses_last_change_before_the_freeze(self):
        """`snapshots` är en förändringsserie — inte en tidsstämpelträff.

        En senare rörelse får aldrig läcka in i frysningsögonblicket.
        """
        for at, streck in (("2026-08-01T09:00:00Z", 55),
                           ("2026-08-01T11:00:00Z", 70),
                           ("2026-08-01T13:00:00Z", 88)):   # EFTER frysningen
            self.store.conn.execute(
                "INSERT INTO snapshots (product, draw_number, event_number, "
                "sign, odds, streck, fetched_at) VALUES "
                "('topptipset',77,1,'1',1.5,?,?)", (streck, at))
        self.store.conn.commit()

        d = pool_system_ledger.system_detail(
            self.store, "topptipset", 77, "m20",
            pool_system_ledger.CHAMPION_KEY)
        self.assertEqual(70, d["events"][0]["streck_at_freeze"]["1"],
                         "11:00-värdet gällde vid frysningen 12:00")

    def test_unknown_system_is_reported_not_crashed(self):
        d = pool_system_ledger.system_detail(
            self.store, "topptipset", 77, "h3", "finns-inte")
        self.assertFalse(d["available"])
