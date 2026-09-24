"""pool-sharp-freshness-v1: ett cachat Pinnacle-pris används bara om det är
högst 90 min gammalt OCH länken inte observerats tappad efter priset.

Bakgrund (audit 2026-09-24): `sharp_odds` är latest-state och rensas aldrig
när länken tappas. Europatipset 2610 match 10 visade ett pris från 08:17Z
fast matcharen sagt `ambiguous` sedan 08:47Z; Stryktipset 4971 frystes med
priser som var fyra dygn gamla.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cli
from app import main, pool_sharp_freshness as freshness
from app import pool_system_ledger
from app.analysis import analyze_draw
from app.pool_input_health import report as input_health
from app.storage import Storage
from app.svenskaspel import Draw, Match, Outcome

NOW = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)
PRODUCT, DRAW = "topptipset", 100


def _iso(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def _ago(minutes):
    return NOW - dt.timedelta(minutes=minutes)


class FreshnessStore:
    """Gemensamma fixturer: en isolerad databas med priser och captures."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.store = Storage(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def price(self, event, fetched_at, odds=(2.0, 3.4, 3.8), total=(2.5, 1.9, 1.9),
              product=PRODUCT, draw=DRAW):
        self.store.save_sharp(product, draw, [{
            "event_number": event, "bookmaker": "pinnacle",
            "odds": dict(zip(("1", "X", "2"), odds)),
            "total": dict(zip(("line", "O", "U"), total)) if total else None,
            "confidence": 1.0, "matched": f"H{event} - B{event}",
            "fetched_at": fetched_at}])

    def capture(self, event, fetched_at, status, product=PRODUCT, draw=DRAW):
        self.store.conn.execute(
            "INSERT INTO pool_market_capture (product, draw_number, source, "
            "event_number, fetched_at, status, odds_complete, streck_complete) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (product, draw, "sharp", event, fetched_at, status,
             int(status in ("matched", "derived"))))
        self.store.conn.commit()


class RuleTests(FreshnessStore, unittest.TestCase):
    def test_lank_tappad_efter_priset_ger_link_lost(self):
        self.price(10, _iso(_ago(223)))                 # 08:17Z … men för gammal också
        self.price(11, _iso(_ago(30)))
        self.capture(11, _iso(_ago(30)), "matched")
        self.capture(11, _iso(_ago(20)), "ambiguous")   # efter priset
        self.capture(11, _iso(_ago(10)), "ambiguous")
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertNotIn(11, fresh)
        self.assertEqual({"reason": "link_lost", "last_seen": _iso(_ago(30)),
                          "status": "ambiguous", "status_at": _iso(_ago(10)),
                          "lost_status": "ambiguous", "lost_at": _iso(_ago(20))},
                         stale[11])

    def test_for_gammalt_pris_ger_too_old(self):
        self.price(1, _iso(_ago(91)))
        self.capture(1, _iso(_ago(91)), "matched")
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertEqual({}, fresh)
        self.assertEqual("too_old", stale[1]["reason"])
        self.assertEqual(("matched", _iso(_ago(91))),
                         (stale[1]["status"], stale[1]["status_at"]))
        self.assertNotIn("lost_at", stale[1])

    def test_farskt_matchat_pris_anvands_i_samma_form_som_get_sharp(self):
        self.price(1, _iso(_ago(90)))                   # exakt på gränsen: ≥ t−90
        self.capture(1, _iso(_ago(120)), "not_listed")  # FÖRE priset — länken kom tillbaka
        self.capture(1, _iso(_ago(90)), "matched")
        self.price(2, _iso(_ago(5)))
        self.capture(2, _iso(_ago(5)), "derived")
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertEqual({}, stale)
        self.assertEqual(self.store.get_sharp(PRODUCT, DRAW), fresh)

    def test_utan_captures_galler_bara_aldersregeln(self):
        self.price(1, _iso(_ago(60)))
        self.price(2, _iso(_ago(200)))
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertEqual({1}, set(fresh))
        self.assertEqual({"reason": "too_old", "last_seen": _iso(_ago(200)),
                          "status": None, "status_at": None}, stale[2])

    def test_tidszoner_jamfors_som_tider_aldrig_som_strangar(self):
        # 13:20+02:00 = 11:20Z (40 min, färskt i ålder). Capturen 11:30Z
        # ligger EFTER priset men sorterar lexikografiskt FÖRE det.
        self.price(1, "2026-09-24T13:20:00+02:00")
        self.capture(1, "2026-09-24T11:30:00Z", "ambiguous")
        # 13:45+02:00 = 11:45Z är färskt vid 12:00Z trots att strängen ser
        # ut att ligga i framtiden; 12:15+02:00 = 10:15Z är 105 min gammalt
        # fast strängen sorterar efter gränsen 10:30Z.
        self.price(2, "2026-09-24T13:45:00+02:00")
        self.price(3, "2026-09-24T12:15:00+02:00")
        # En gammal rad i sharp_odds med mikrosekunder och +00:00.
        self.price(4, "2026-09-24T11:59:00.353141+00:00")
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertEqual("link_lost", stale[1]["reason"])
        self.assertEqual({2, 4}, set(fresh))
        self.assertEqual("too_old", stale[3]["reason"])
        # Klockan i sig får också ha en annan offset.
        local_now = NOW.astimezone(dt.timezone(dt.timedelta(hours=2)))
        self.assertEqual((fresh, stale), freshness.fresh_sharp(
            self.store, PRODUCT, DRAW, local_now))

    def test_captures_efter_klockan_raknas_inte(self):
        self.price(1, _iso(_ago(30)))
        self.capture(1, _iso(NOW + dt.timedelta(minutes=5)), "ambiguous")
        fresh, _stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertIn(1, fresh)

    def test_oparsbar_pristid_ar_aldrig_farsk(self):
        self.price(1, None)
        self.price(2, "trasig")
        fresh, stale = freshness.fresh_sharp(self.store, PRODUCT, DRAW, NOW)
        self.assertEqual({}, fresh)
        self.assertEqual({"too_old"}, {e["reason"] for e in stale.values()})

    def test_klockan_maste_injiceras(self):
        with self.assertRaises(TypeError):
            freshness.fresh_sharp(self.store, PRODUCT, DRAW, None)

    def test_tackning_och_orsaker(self):
        self.price(1, _iso(_ago(10)))
        self.capture(1, _iso(_ago(10)), "matched")
        self.price(2, _iso(_ago(40)))
        self.capture(2, _iso(_ago(10)), "ambiguous")
        self.price(3, _iso(_ago(300)))
        self.capture(4, _iso(_ago(10)), "not_listed")    # aldrig länkad
        cov = freshness.coverage(self.store, PRODUCT, DRAW, NOW, [1, 2, 3, 4, 5])
        self.assertEqual((5, 1), (cov["n"], cov["fresh"]))
        self.assertEqual({"ambiguous": 1, "too_old": 1, "not_listed": 1,
                          "never_observed": 1}, cov["reasons"])

    def test_forklaringar_i_svensk_tid(self):
        lost = {"reason": "link_lost", "lost_status": "ambiguous",
                "lost_at": "2026-09-24T08:47:00Z", "last_seen": "2026-09-24T08:17:00Z"}
        old = {"reason": "too_old", "last_seen": "2026-09-24T08:17:00Z"}
        self.assertEqual("Pinnacle-länken tappad (tvetydig) sedan 10:47",
                         freshness.explain(lost, NOW))
        self.assertEqual("Pinnacle-priset äldre än 90 min (senast 10:17)",
                         freshness.explain(old, NOW))
        self.assertEqual("Pinnacle-priset äldre än 90 min (senast 15/9 10:17)",
                         freshness.explain({"reason": "too_old",
                                            "last_seen": "2026-09-15T08:17:00Z"}, NOW))

    def test_stangd_omgang_bedoms_vid_spelstopp(self):
        close = "2026-09-24T12:00:00+02:00"             # 10:00Z
        self.assertEqual(dt.datetime(2026, 9, 24, 10, 0, tzinfo=dt.timezone.utc),
                         freshness.as_of(close, NOW))
        self.assertEqual(NOW, freshness.as_of("2026-09-24T20:44:00+02:00", NOW))
        self.assertEqual(NOW, freshness.as_of(None, NOW))


def _draw(close, n=3, product=PRODUCT):
    draw = Draw(product=product, draw_number=DRAW, state="Open",
                reg_close_time=close.isoformat(), net_sale=120000.0,
                row_price=1.0, fetched_at=_iso(NOW), jackpot=0.0)
    for i in range(1, n + 1):
        odds = {"1": 2.1, "X": 3.4, "2": 3.6}
        outcomes = {s: Outcome(sign=s, odds=odds[s], start_odds=odds[s],
                               streck=({"1": 45, "X": 28, "2": 27})[s],
                               streck_ref=None) for s in ("1", "X", "2")}
        draw.matches.append(Match(
            event_number=i, description=f"H{i} - B{i}", home=f"H{i}",
            away=f"B{i}", home_iso=None, away_iso=None, league="Test",
            match_start=close.isoformat(), cancelled=False, kambi_id=None,
            outcomes=outcomes))
    return draw


class AnalysisPathTests(FreshnessStore, unittest.TestCase):
    """/api/analysis och /api/system bygger på main._analyze."""

    def _fixture(self):
        self.price(1, _iso(_ago(10)))                     # färsk
        self.capture(1, _iso(_ago(10)), "matched")
        self.price(2, _iso(_ago(40)))                     # länken tappad efter priset
        self.capture(2, _iso(_ago(40)), "matched")
        self.capture(2, _iso(_ago(13)), "ambiguous")
        self.price(3, _iso(_ago(223)))                    # för gammalt
        return _draw(NOW + dt.timedelta(hours=5))

    def _analyze(self, draw):
        with patch.object(main, "_get_draw", return_value=draw), \
                patch.object(main, "Storage", side_effect=lambda: Storage(self.db)):
            return main._analyze(PRODUCT, DRAW, now=NOW)

    def test_analysen_slapper_inaktuella_priser_och_sager_varfor(self):
        analysis = self._analyze(self._fixture())
        m1, m2, m3 = analysis.matches
        self.assertEqual(2.0, m1.outcomes["1"].sharp_odds)
        self.assertTrue(m1.has_sharp)
        self.assertEqual(2.5, m1.total_line)
        self.assertIsNone(m1.sharp_stale)
        for match in (m2, m3):
            self.assertFalse(match.has_sharp)
            self.assertIsNone(match.total_line)
            self.assertTrue(all(o.sharp_odds is None and o.sharp_prob is None
                                for o in match.outcomes.values()))
        self.assertEqual("link_lost", m2.sharp_stale["reason"])
        self.assertEqual("Pinnacle-länken tappad (tvetydig) sedan 13:47",
                         m2.sharp_stale["text"])
        self.assertEqual("pool-sharp-freshness-v1", m2.sharp_stale["version"])
        self.assertEqual("too_old", m3.sharp_stale["reason"])
        self.assertEqual(_iso(_ago(223)), m3.sharp_stale["last_seen"])
        self.assertEqual("Pinnacle-priset äldre än 90 min (senast 10:17)",
                         m3.sharp_stale["text"])

    def test_api_svaret_bar_sharp_stale_och_orsaken_i_oddsvarningen(self):
        analysis = self._analyze(self._fixture())
        with patch.object(main, "_analyze", return_value=analysis):
            payload = main.analysis(PRODUCT, DRAW)
        by_event = {m["event_number"]: m for m in payload["matches"]}
        self.assertIsNone(by_event[1]["sharp_stale"])
        self.assertEqual("link_lost", by_event[2]["sharp_stale"]["reason"])
        health = payload["input_health"]
        self.assertEqual("warning", health["level"])       # nivålogiken orörd
        self.assertEqual((2, 2), (health["missing_sharp"], health["stale_sharp"]))
        reasons = {i["event_number"]: i["reason"] for i in health["issues"]}
        self.assertEqual("Pinnacle-länken tappad (tvetydig) sedan 13:47", reasons[2])
        self.assertTrue(reasons[3].startswith("Pinnacle-priset äldre än 90 min"))

    def test_stangd_omgang_visas_som_vid_spelstopp(self):
        # Spelstopp för 30 min sedan: priset (10 min före stopp) var färskt DÅ.
        self.price(1, _iso(_ago(40)))
        draw = _draw(NOW - dt.timedelta(minutes=30), n=1)
        analysis = self._analyze(draw)
        self.assertEqual(2.0, analysis.matches[0].outcomes["1"].sharp_odds)
        self.assertIsNone(analysis.matches[0].sharp_stale)


class FakeSvS:
    def get_jackpot(self, product, draw_number):
        return None


class FreezePathTests(FreshnessStore, unittest.TestCase):
    """PH3: `_pool_pit_freeze` bedömer färskheten med frysningens klocka."""

    def _svs_move(self, event, minutes_ago, odds1):
        for sign, odds in (("1", odds1), ("X", 3.4), ("2", 3.6)):
            self.store.conn.execute(
                "INSERT INTO snapshots(product, draw_number, event_number, sign, "
                "odds, start_odds, streck, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                (PRODUCT, DRAW, event, sign, odds, odds, 40, _iso(_ago(minutes_ago))))

    def _sharp_move(self, event, minutes_ago, odds1):
        for sign, odds in (("1", odds1), ("X", 3.4), ("2", 3.8)):
            self.store.conn.execute(
                "INSERT INTO sharp_snapshots(product, draw_number, event_number, "
                "sign, odds, fetched_at) VALUES (?,?,?,?,?,?)",
                (PRODUCT, DRAW, event, sign, odds, _iso(_ago(minutes_ago))))

    def test_frysningen_far_bara_farska_priser_och_svs_rorelse_for_resten(self):
        draw = _draw(NOW + dt.timedelta(minutes=178), n=8)   # h3 nyss öppen
        for event in (1, 4, 5, 6, 7, 8):
            self.price(event, _iso(_ago(8)))
            self.capture(event, _iso(_ago(8)), "matched")
        self.price(2, _iso(_ago(40)))
        self.capture(2, _iso(_ago(40)), "matched")
        self.capture(2, _iso(_ago(8)), "ambiguous")
        self.price(3, _iso(_ago(5 * 24 * 60)))              # "priser från 15/9"
        for event in (1, 2):
            self._sharp_move(event, 600, 2.4)
            self._sharp_move(event, 40, 1.9)
            self._svs_move(event, 600, 2.2)
            self._svs_move(event, 60, 2.0)
        self.store.conn.commit()

        seen = {}

        def spy(draw_arg, sharp, movement):
            seen["sharp"], seen["movement"] = dict(sharp), dict(movement)
            return analyze_draw(draw_arg, sharp, movement)

        with patch.object(pool_system_ledger, "analyze_draw", side_effect=spy):
            cli._pool_pit_freeze(self.store, FakeSvS(), PRODUCT, draw, now=NOW)

        self.assertEqual({1, 4, 5, 6, 7, 8}, set(seen["sharp"]))
        # Match 1: färsk sharp-serie med steam. Match 2: SvS-serien, inget steam.
        self.assertEqual((2.4, 1.9), (seen["movement"][(1, "1")]["first"],
                                      seen["movement"][(1, "1")]["last"]))
        self.assertIn("steam_pp", seen["movement"][(1, "1")])
        self.assertEqual((2.2, 2.0), (seen["movement"][(2, "1")]["first"],
                                      seen["movement"][(2, "1")]["last"]))
        self.assertNotIn("steam_pp", seen["movement"][(2, "1")])
        rows = self.store.conn.execute(
            "SELECT frozen_at, build_note FROM pool_system_ledger").fetchall()
        self.assertEqual(len(pool_system_ledger.benchmarks_for(PRODUCT)), len(rows))
        self.assertEqual({_iso(NOW)}, {r[0] for r in rows})
        self.assertTrue(all(
            "pool-sharp-freshness-v1: cachad Pinnacle ej använd i 2 matcher "
            "(2: tvetydig, 3: för gammal)." in (r[1] or "") for r in rows))

    def test_revisionsnoten_saknas_nar_allt_ar_farskt(self):
        self.assertEqual("", pool_system_ledger._freshness_note({}))
        self.assertEqual(
            "pool-sharp-freshness-v1: cachad Pinnacle ej använd i 1 match "
            "(7: ej listad/namn).",
            pool_system_ledger._freshness_note(
                {7: {"reason": "link_lost", "lost_status": "not_listed"}}))


class NotifyPathTests(FreshnessStore, unittest.TestCase):
    """Notisspåret är pausat, men vägen ska läsa samma färska sharp."""

    def test_notisvagen_far_bara_farska_priser(self):
        from app import notify
        draw = _draw(NOW + dt.timedelta(hours=2), n=2)
        self.price(1, _iso(_ago(5)))
        self.price(2, _iso(_ago(300)))
        seen = {}

        def spy(draw_arg, sharp, movement):
            seen["sharp"] = dict(sharp)
            return analyze_draw(draw_arg, sharp, movement)

        with patch.dict("os.environ", {"NTFY_TOPIC": "test-topic"}), \
                patch.object(notify, "analyze_draw", side_effect=spy), \
                patch.object(notify, "push", return_value=False):
            notify.check_movers(PRODUCT, draw, self.store, now=NOW)
        self.assertEqual({1}, set(seen["sharp"]))


class InputHealthTextTests(unittest.TestCase):
    def test_oddsvarningen_bar_orsaken_men_samma_niva(self):
        draw = _draw(NOW + dt.timedelta(hours=5), n=2)
        analysis = analyze_draw(draw, {1: {"odds": {"1": 2.0, "X": 3.4, "2": 3.8},
                                           "total": {"line": 2.5, "O": 1.9, "U": 1.9}}})
        analysis.matches[1].sharp_stale = {
            "reason": "too_old", "last_seen": "2026-09-24T08:17:00Z",
            "text": "Pinnacle-priset äldre än 90 min (senast 10:17)"}
        health = input_health(analysis)
        self.assertEqual("warning", health["level"])
        self.assertEqual(1, health["stale_sharp"])
        self.assertEqual("pool-sharp-freshness-v1", health["freshness_version"])
        issue = health["issues"][0]
        self.assertEqual(2, issue["event_number"])
        self.assertEqual(["Pinnacle 1X2", "Pinnacle Ö/U"], issue["missing"])
        self.assertEqual("Pinnacle-priset äldre än 90 min (senast 10:17)", issue["reason"])


if __name__ == "__main__":
    unittest.main()
