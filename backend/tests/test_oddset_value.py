import datetime as dt
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from app import oddset_model, oddset_value
from app.storage import Storage


def _market(values: dict, seen: dt.datetime, available: bool = True) -> dict:
    market = {**values, "available": available,
              "last_seen_at": seen.strftime("%Y-%m-%dT%H:%M:%SZ")}
    market.setdefault("fetched_at", market["last_seen_at"])
    return market


class PriceFreshnessTests(unittest.TestCase):
    def test_stale_book_price_is_excluded_from_value(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1", "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"1x2": _market(
                    {"1": 2.0, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
                "svenskaspel": {"1x2": _market(
                    {"1": 2.3, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=60))},
            },
        }

        oddset_value.attach_value([match])
        self.assertFalse(match["odds"]["svenskaspel"]["1x2"]["fresh"])
        self.assertEqual({}, match["value"])

    def test_recent_confirmation_allows_value(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1", "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"1x2": _market(
                    {"1": 2.0, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
                "svenskaspel": {"1x2": _market(
                    {"1": 2.3, "X": 3.5, "2": 3.8}, now - dt.timedelta(minutes=5))},
            },
        }

        oddset_value.attach_value([match])
        self.assertTrue(match["odds"]["svenskaspel"]["1x2"]["fresh"])
        self.assertIn("1", match["value"]["1x2"])

    def test_fresh_ninja_corner_price_can_be_best_and_proven_held(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1",
            "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"cor": _market(
                    {"O": 1.91, "U": 1.91, "line": 9.5,
                     "fetched_at": (now - dt.timedelta(minutes=5)).strftime(
                         "%Y-%m-%dT%H:%M:%SZ")},
                    now - dt.timedelta(minutes=4))},
                "svenskaspel": {"cor": _market(
                    {"O": 1.90, "U": 1.85, "line": 9.5}, now - dt.timedelta(minutes=3))},
                "ninjacasino": {"cor": _market(
                    {"O": 2.20, "U": 1.65, "line": 9.5,
                     "fetched_at": (now - dt.timedelta(minutes=40)).strftime(
                         "%Y-%m-%dT%H:%M:%SZ")},
                    now - dt.timedelta(minutes=2))},
            },
        }

        oddset_value.attach_value([match])

        value = match["value"]["cor"]["O"]
        self.assertEqual("ninjacasino", value["book"])
        self.assertTrue(value["held_after_sharp"])
        self.assertGreater(value["edge"], 0.09)

    def test_ninja_is_not_called_held_without_post_sharp_confirmation(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        match = {
            "id": "m1",
            "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": {
                "pinnacle": {"ou": _market(
                    {"O": 1.91, "U": 1.91, "line": 2.5,
                     "fetched_at": (now - dt.timedelta(minutes=5)).strftime(
                         "%Y-%m-%dT%H:%M:%SZ")},
                    now - dt.timedelta(minutes=4))},
                "ninjacasino": {"ou": _market(
                    {"O": 2.20, "U": 1.65, "line": 2.5,
                     "fetched_at": (now - dt.timedelta(minutes=30)).strftime(
                         "%Y-%m-%dT%H:%M:%SZ")},
                    now - dt.timedelta(minutes=10))},
            },
        }

        oddset_value.attach_value([match])

        value = match["value"]["ou"]["O"]
        self.assertEqual("ninjacasino", value["book"])
        self.assertNotIn("held_after_sharp", value)


class SignalVersionTests(unittest.TestCase):
    def test_model_data_change_does_not_fragment_sharp_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                before = oddset_value.signal_versions(store)
                with mock.patch.dict(oddset_model.MODEL_PARAMS,
                                     {"result_merge_v": 999}):
                    after = oddset_value.signal_versions(store)
            finally:
                store.close()

        self.assertEqual(before["sharp"], after["sharp"])
        self.assertNotEqual(before["model"], after["model"])


class ClosingFreshnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _flag(self, start: dt.datetime) -> None:
        self.store.oddset_log_flag({
            "match_id": "m1", "market": "1x2", "sign": "1",
            "league": "mls", "description": "A – B",
            "match_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at": (start - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": 2.2, "fair": 0.5, "edge": 0.1,
            "book": "svenskaspel", "model_version": "s-test", "git_hash": "abc",
        })

    def _pair_flag(self, start: dt.datetime, market: str, sign: str,
                   line: float) -> None:
        self.store.oddset_log_flag({
            "match_id": "m1", "market": market, "sign": sign, "line": line,
            "league": "mls", "description": "A – B",
            "match_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "at": (start - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "odds": 2.0, "fair": 0.5, "edge": 0.05,
            "book": "svenskaspel", "tier": "model",
            "model_version": "m-test", "git_hash": "abc",
        })

    def _pair_prices(self, market: str, line: float, at: dt.datetime) -> None:
        signs = ("H", "A") if market == "ah" else ("O", "U")
        self.store.oddset_save_market(
            "m1", "pinnacle", market,
            {signs[0]: {"odds": 1.9, "line": line},
             signs[1]: {"odds": 1.95, "line": line}},
            at.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_old_unconfirmed_sharp_price_is_not_used_as_closing(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        old = (start - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, old)
        self._flag(start)

        self.assertEqual(1, oddset_value.resolve_closings(self.store))
        row = self.store.oddset_clv_rows()[0]
        self.assertIn("äldre än", row["closing_note"])
        self.assertIsNone(row["closing_fair"])

    def test_unchanged_price_confirmed_near_start_is_valid_closing(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        old = (start - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = (start - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        odds = {"1": 2.0, "X": 3.5, "2": 3.8}
        self.store.oddset_save_odds("m1", "pinnacle", odds, old)
        self.store.oddset_save_odds("m1", "pinnacle", odds, recent)
        self._flag(start)

        self.assertEqual(1, oddset_value.resolve_closings(self.store))
        row = self.store.oddset_clv_rows()[0]
        self.assertIsNone(row["closing_note"])
        self.assertIsNotNone(row["closing_fair"])

    def test_post_kickoff_price_is_never_used_as_closing(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        pre = (start - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        post = (start + dt.timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, pre)
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 1.6, "X": 4.2, "2": 5.0}, post)
        self._flag(start)

        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]

        self.assertEqual(2.0, row["closing_odds"])
        expected = oddset_value._devig(
            {"1": 2.0, "X": 3.5, "2": 3.8}, ("1", "X", "2"))["1"]
        self.assertAlmostEqual(expected, row["closing_fair"], places=4)

    def test_pair_closing_requires_both_signs_on_one_line(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        at = (start - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_market(
            "m1", "pinnacle", "ou",
            {"O": {"odds": 1.9, "line": 3.25},
             "U": {"odds": 1.95, "line": 3.5}}, at)
        self._pair_flag(start, "mou", "O", 3.25)

        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]

        self.assertEqual("inkonsistent sharp-stängningslina", row["closing_note"])
        self.assertIsNone(row["closing_fair"])

    def test_line_move_is_resolved_category_when_flag_line_is_old(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        self._pair_prices("ou", 3.25, start - dt.timedelta(hours=2))
        self._pair_prices("ou", 3.5, start - dt.timedelta(minutes=10))
        self._pair_flag(start, "mou", "O", 3.25)

        self.assertEqual(1, oddset_value.resolve_closings(self.store))
        row = self.store.oddset_clv_rows()[0]
        self.assertEqual("linje flyttad", row["closing_note"])
        self.assertEqual(3.5, row["closing_line"])
        self.assertEqual(0.25, row["line_delta"])
        self.assertEqual(0.25, row["line_move_score"])
        self.assertIsNone(row["closing_fair"])
        stats = oddset_value.clv_report(self.store)["model"]
        self.assertEqual(1, stats["n_line_moved"])
        self.assertEqual(1, stats["n_line_moved_positive"])

    def test_fresh_exact_line_keeps_close_ev_and_records_later_move(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        self._pair_prices("ou", 3.25, start - dt.timedelta(minutes=30))
        self._pair_prices("ou", 3.5, start - dt.timedelta(minutes=10))
        self._pair_flag(start, "mou", "O", 3.25)

        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]
        self.assertIsNone(row["closing_note"])
        self.assertIsNotNone(row["closing_fair"])
        self.assertEqual(0.25, row["line_move_score"])

    def test_home_handicap_shortening_has_positive_move_score(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        self._pair_prices("ah", -0.5, start - dt.timedelta(minutes=30))
        self._pair_prices("ah", -0.75, start - dt.timedelta(minutes=10))
        self._pair_flag(start, "mah", "H", -0.5)

        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]
        self.assertEqual(-0.25, row["line_delta"])
        self.assertEqual(0.25, row["line_move_score"])


class ClosingDriftTests(unittest.TestCase):
    """v8, förregistrerad i docs/closing-drift-v8-forregistrering-2026-08-07.

    Vi jämförde bokens pris mot Pinnacles NUVARANDE pris, alltså som om
    dagens pris vore stängningen. Mätt på 10 908 parade observationer driftar
    Pinnacle systematiskt per band: favoriter −0,61 pp, outsiders +0,32 pp.
    Följden i facitet var att favoritflaggorna gav +0,29 % close-EV med ett
    KI som rymmer noll, medan outsiders gav +5,96 %.
    """

    def test_favoriter_dras_ned_och_outsiders_upp_tidigt(self) -> None:
        fair = {"1": 0.60, "X": 0.25, "2": 0.15}
        ut = oddset_value.drift_adjust(fair, hours_to_start=24.0)
        self.assertAlmostEqual(0.60 - 0.0060, ut["1"], places=6)
        self.assertAlmostEqual(0.25, ut["X"], places=6, msg="mittbandet orört")
        self.assertAlmostEqual(0.15 + 0.0030, ut["2"], places=6)

    def test_driften_krymper_nara_avspark(self) -> None:
        """Mätt: driften är ~5× mindre vid T−20m än vid T−3h."""
        fair = {"1": 0.60, "X": 0.25, "2": 0.15}
        sent = oddset_value.drift_adjust(fair, hours_to_start=0.3)
        self.assertAlmostEqual(0.60 - 0.0012, sent["1"], places=6)
        self.assertAlmostEqual(0.15 + 0.0007, sent["2"], places=6)
        tidigt = oddset_value.drift_adjust(fair, hours_to_start=24.0)
        self.assertLess(abs(sent["1"] - 0.60), abs(tidigt["1"] - 0.60))

    def test_bandet_sätts_på_ojusterad_sannolikhet(self) -> None:
        """Annars blir gränsen cirkulär: en justering skulle kunna flytta ett
        tecken mellan band och därmed ändra sin egen justering."""
        fair = {"1": 0.5005, "X": 0.3, "2": 0.1995}
        ut = oddset_value.drift_adjust(fair, hours_to_start=24.0)
        # 0,5005 är favorit FÖRE justering och ska dras ned med favorittalet
        self.assertAlmostEqual(0.5005 - 0.0060, ut["1"], places=6)
        # 0,1995 är outsider före justering
        self.assertAlmostEqual(0.1995 + 0.0030, ut["2"], places=6)

    def test_utan_starttid_justeras_ingenting(self) -> None:
        """Hellre oförändrad än gissad regim."""
        fair = {"1": 0.60, "X": 0.25, "2": 0.15}
        self.assertEqual(fair, oddset_value.drift_adjust(fair, None))

    def test_justeringen_ingar_i_signalversionen(self) -> None:
        """Selektionen ändras ⇒ facitet MÅSTE börja om."""
        self.assertIn("closing_drift", oddset_value.SHARP_PARAMS)
        self.assertEqual("band-v8",
                         oddset_value.SHARP_PARAMS["closing_drift"])

    def test_sannolikheter_haller_sig_inom_intervallet(self) -> None:
        extrem = {"1": 0.9995, "X": 0.0004, "2": 0.0001}
        ut = oddset_value.drift_adjust(extrem, hours_to_start=24.0)
        for p in ut.values():
            self.assertGreater(p, 0.0)
            self.assertLess(p, 1.0)


class AnchorSourceTests(unittest.TestCase):
    """🎯 ANKARE ≠ BOK + andra ankaret som REN mätning.

    Ankarkontamineringen 2026-07-25 (192 felaktiga flaggor) uppstod för att
    `attach_value` byggde boklistan som "allt utom pinnacle". Spärren fanns
    därefter i koden men i inget test — dessa fall är den saknade grinden.
    """

    @staticmethod
    def _match(with_anchor: bool = True, anchor_odds: Optional[dict] = None) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        fresh = now - dt.timedelta(minutes=5)
        odds = {
            "pinnacle": {"1x2": _market({"1": 2.0, "X": 3.5, "2": 3.8}, fresh)},
            "svenskaspel": {"1x2": _market({"1": 2.3, "X": 3.5, "2": 3.8}, fresh)},
        }
        if with_anchor:
            odds[oddset_value.ANCHOR2_SOURCE] = {
                "1x2": _market(anchor_odds or {"1": 2.05, "X": 3.45, "2": 3.75},
                               fresh)}
        return {"id": "m1",
                "start": (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "odds": odds}

    def test_ankarkallan_blir_aldrig_en_bok_att_hitta_varde_hos(self) -> None:
        # Smarkets ligger med GENERÖSA priser: vore den en bok skulle den vinna
        # `best`-jämförelsen och dyka upp som bokfältet.
        match = self._match(anchor_odds={"1": 9.9, "X": 9.9, "2": 9.9})
        oddset_value.attach_value([match])
        books = {v["book"] for per in match["value"].values() for v in per.values()}
        self.assertNotIn(oddset_value.ANCHOR2_SOURCE, books)
        self.assertTrue(oddset_value.ANCHOR_SOURCES,
                        "ANCHOR_SOURCES får inte tömmas — då blir börsen en bok")
        for src in oddset_value.ANCHOR_SOURCES:
            self.assertNotIn(src, books)

    def test_andra_ankaret_andrar_inte_urval_edge_eller_kvalitet(self) -> None:
        """Mätningen är skugga: identiskt utfall med och utan ankare 2."""
        med, utan = self._match(True), self._match(False)
        oddset_value.attach_value([med])
        oddset_value.attach_value([utan])
        for sign, v in utan["value"]["1x2"].items():
            m = med["value"]["1x2"][sign]
            self.assertEqual((v["edge"], v["q"], v["odds"], v["book"]),
                             (m["edge"], m["q"], m["odds"], m["book"]))

    def test_andra_ankaret_ar_bortkopplat_men_sparren_star_kvar(self) -> None:
        """Smarkets kopplades bort som ankare 2026-08-07: den har 56 030
        priser på 1X2 och NOLL på AH/Ö/U/hörnor, så den kunde bara mäta 24 %
        av flaggorna och 271 frånvaronoteringar var brus om ett känt hål.

        SPÄRREN i ANCHOR_SOURCES är en annan sak och MÅSTE stå kvar — utan
        den blir Smarkets en spelbar bok igen (184 av 476 felaktiga flaggor
        2026-07-25)."""
        match = self._match()
        oddset_value.attach_value([match])
        self.assertNotIn("anchor2", match["value"]["1x2"]["1"],
                         "ankare 2 ska inte längre skrivas på posten")
        self.assertIn("smarkets", oddset_value.ANCHOR_SOURCES,
                      "säkerhetsspärren får aldrig tas bort med mätningen")
        # och Smarkets får fortfarande aldrig bli den bok vi hittar värde hos
        self.assertNotEqual("smarkets", match["value"]["1x2"]["1"]["book"])

    def test_stangningen_mater_bada_ankarna(self) -> None:
        """Stängningen ska spara ankare 2:s fair — och lämna den NULL när
        ankaret inte har en färsk komplett marknad (halvmätt ser ut som
        enighet och är därför värre än omätt)."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
                recent = (start - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
                store.oddset_save_odds("m1", "pinnacle",
                                       {"1": 2.0, "X": 3.5, "2": 3.8}, recent)
                store.oddset_save_odds("m1", oddset_value.ANCHOR2_SOURCE,
                                       {"1": 2.1, "X": 3.4, "2": 3.7}, recent)
                # ankare 2 saknar helt marknad i den andra matchen
                store.oddset_save_odds("m2", "pinnacle",
                                       {"1": 2.0, "X": 3.5, "2": 3.8}, recent)
                for mid in ("m1", "m2"):
                    store.oddset_log_flag({
                        "match_id": mid, "market": "1x2", "sign": "1",
                        "league": "mls", "description": "A – B",
                        "match_start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "at": (start - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "odds": 2.2, "fair": 0.5, "edge": 0.1,
                        "book": "svenskaspel", "model_version": "s-test",
                        "git_hash": "abc"})

                oddset_value.resolve_closings(store)
                rows = {r["match_id"]: r for r in store.oddset_clv_rows()}
                self.assertIsNotNone(rows["m1"]["anchor2_closing_fair"])
                self.assertIsNotNone(rows["m1"]["closing_fair"])
                self.assertIsNone(rows["m2"]["anchor2_closing_fair"])
                self.assertIsNotNone(rows["m2"]["closing_fair"],
                                     "huvudstängningen får inte bero på ankare 2")
            finally:
                store.close()

    def test_signalversionen_ror_sig_inte_av_skuggmatningen(self) -> None:
        """Ändras urvalet av ankare 2 MÅSTE signal_version bumpas — annars
        blandas två olika signaler i samma facitgrupp. Så länge mätningen är
        skugga får den inte finnas i SHARP_PARAMS."""
        self.assertNotIn("anchor2", oddset_value.SHARP_PARAMS)
        self.assertNotIn(oddset_value.ANCHOR2_SOURCE,
                         str(oddset_value.SHARP_PARAMS))


if __name__ == "__main__":
    unittest.main()
