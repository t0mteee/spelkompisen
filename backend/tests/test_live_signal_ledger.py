"""Framåtriktat facit för de signaler användaren faktiskt ser i live-radarn."""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import flashscore, kambi, live_radar, live_signal_ledger
from app.oddset import norm_team
from app.storage import Storage


# Inne i den aktuella kohortens DEKLARERADE fönster. Fixturerna skrivs av
# dagens kod, som stämplar raden med aktuell `radar_version`; en fixtur daterad
# före fönstret blir därför korrekt `transitional` och faller ur blindkohorten.
# Datumet ska följa med vid nästa kohortstart.
# Se noten i test_radar_settlement: klockan måste ligga i den aktiva
# radarkohortens deklarerade fönster.
NOW = dt.datetime(2026, 9, 3, 5, 0, tzinfo=dt.timezone.utc)


def iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def capture(at: dt.datetime, minute: int, *, xg_home: float,
            home_score: int = 0, away_score: int = 0) -> dict:
    """En Flashscore-rad — radarns ankare sedan 2026-08-06.

    Journalen bokför signaler som payload faktiskt visar, så hjälparen måste
    följa med när ankarkällan byts. Sofascore-rader når inte längre radarn.
    """
    from app.flashscore import CAPTURE_VERSION as FS_VERSION
    return {
        "flashscore_id": "HAMAIK01",
        "captured_at": iso(at),
        "capture_version": FS_VERSION,
        "league": "allsvenskan",
        "tournament": "Allsvenskan",
        "home": "Hammarby IF",
        "away": "AIK",
        "start_at": iso(NOW - dt.timedelta(minutes=minute)),
        "minute": minute,
        "home_score": home_score,
        "away_score": away_score,
        "xg_home": xg_home,
        "xg_away": 0.2,
        "big_chances_home": 2,
        "big_chances_away": 0,
        "shots_home": 9,
        "shots_away": 3,
        "shots_on_home": 5,
        "shots_on_away": 1,
        "shots_inside_home": 8,
        "shots_inside_away": 2,
    }


class LiveSignalLedgerTests(unittest.TestCase):
    def setUp(self):
        self._source_patchers = [
            patch.object(live_signal_ledger.kambi, "live_events", return_value=[]),
            patch.object(live_signal_ledger.altenar, "live_events", return_value=[]),
            patch.object(live_signal_ledger.pinnacle.Pinnacle,
                         "soccer_live_totals", return_value=[]),
        ]
        for patcher in self._source_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.store.oddset_upsert_match({
            "id": "pin:991",
            "league": "allsvenskan",
            "home": "Hammarby",
            "away": "AIK",
            "start": iso(NOW - dt.timedelta(minutes=30)),
            "pinnacle_id": "991",
            "kambi_id": "7722",
        })

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_storage_enforces_signal_result_foreign_key(self):
        self.assertEqual(
            1, self.store.conn.execute("PRAGMA foreign_keys").fetchone()[0])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.live_signal_result_save({
                "signal_id": 999_999, "settled_at": iso(NOW),
                "final_home_score": 0, "final_away_score": 0,
            })

    def test_first_level_is_append_once_and_live_ou_is_fetched_once(self):
        # 0.8 xG-gap ⇒ watch men inte strong.
        self.store.live_flashscore_save(capture(
            NOW, 30, xg_home=0.8))
        market = {"ou": {"line": 2.5, "O": 2.08, "U": 1.74}}
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value=market) as fetch:
            first = live_signal_ledger.capture_signals(self.store, now=NOW)
            second = live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(1, first["saved"])
        self.assertEqual(0, second["saved"])
        self.assertEqual(1, fetch.call_count,
                         "ett redan loggat nivåögonblick får inte ompollas")
        row = self.store.live_signal_rows()[0]
        self.assertEqual("watch", row["signal_level"])
        self.assertEqual("xg", row["signal_type"])
        self.assertEqual(30, row["minute"])
        self.assertEqual(0, row["home_score"])
        self.assertEqual(0, row["away_score"])
        self.assertEqual(2.5, row["ou_line"])
        self.assertEqual(2.08, row["over_odds"])
        self.assertEqual("captured", row["odds_status"])
        self.assertEqual("pin:991", row["match_id"])

    def test_signal_locks_best_same_line_price_and_saves_all_sources(self):
        self.store.live_flashscore_save(capture(NOW, 30, xg_home=0.8))
        kambi_market = {"ou": {"line": 2.5, "O": 1.98, "U": 1.82}}
        ninja_rows = [{
            "id": "n1", "home": "Hammarby", "away": "AIK",
            "status": "captured", "ou": {"line": 2.5, "O": 2.08, "U": 1.72},
            "offers": [{"line": 2.5, "O": 2.08, "U": 1.72}],
        }]
        pinnacle_rows = [{
            "id": "p1", "home": "Hammarby IF", "away": "AIK",
            "status": "captured", "age_s": 20,
            "ou": {"line": 2.5, "O": 2.02, "U": 1.78},
            "offers": [{"line": 2.5, "O": 2.02, "U": 1.78}],
        }]
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value=kambi_market), \
                patch.object(live_signal_ledger.altenar, "live_events",
                             return_value=ninja_rows), \
                patch.object(live_signal_ledger.pinnacle.Pinnacle,
                             "soccer_live_totals", return_value=pinnacle_rows):
            report = live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(1, report["priced"])
        row = self.store.live_signal_facit_rows()[0]
        self.assertEqual("ninja", row["odds_source"])
        self.assertEqual(2.08, row["over_odds"])
        self.assertEqual(3, len(row["odds_quotes"]))
        self.assertEqual(1, sum(q["selected"] for q in row["odds_quotes"]))

    def test_level_escalation_is_a_new_decision_but_repeated_level_is_not(self):
        self.store.live_flashscore_save(capture(
            NOW - dt.timedelta(minutes=4), 30, xg_home=0.8))
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value={}):
            live_signal_ledger.capture_signals(
                self.store, now=NOW - dt.timedelta(minutes=4))

        # 1.3 xG-gap ⇒ strong. Samma match får nu exakt en ny nivåpost.
        self.store.live_flashscore_save(capture(
            NOW, 34, xg_home=1.3))
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value={}):
            live_signal_ledger.capture_signals(self.store, now=NOW)
            live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(
            ["watch", "strong"],
            [row["signal_level"] for row in self.store.live_signal_rows()])

    def test_info_moment_is_not_a_signal_bet(self):
        self.store.live_flashscore_save(capture(
            NOW, 30, xg_home=0.3))
        with patch.object(live_signal_ledger.kambi, "live_total") as fetch:
            report = live_signal_ledger.capture_signals(self.store, now=NOW)
        self.assertEqual(0, report["saved"])
        fetch.assert_not_called()
        self.assertEqual([], self.store.live_signal_rows())

    def test_result_settlement_saves_final_score_and_asian_over_profit(self):
        t0 = NOW - dt.timedelta(hours=5)
        first = capture(t0, 30, xg_home=0.8)
        later = capture(t0 + dt.timedelta(minutes=10), 40,
                        xg_home=1.0, home_score=1)
        self.store.live_flashscore_save(first)
        self.store.live_flashscore_save(later)
        self.store.live_signal_save({
            "match_key": "pin:991", "match_id": "pin:991",
            "provider": "flashscore", "provider_event_id": "HAMAIK01",
            "captured_at": first["captured_at"],
            "capture_version": first["capture_version"],
            "signal_version": live_radar.RADAR_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "home": "Hammarby IF", "away": "AIK",
            "start_at": first["start_at"], "minute": 30,
            "home_score": 0, "away_score": 0,
            "signal_level": "watch", "signal_type": "xg",
            "signal_team": "Hammarby IF", "signal_side": "home",
            "signal_score": 0.8, "ou_line": 2.25,
            "over_odds": 2.0, "under_odds": 1.8,
            "odds_source": "svenskaspel", "odds_status": "captured",
            "recorded_at": first["captured_at"],
        })
        self.store.oddset_save_result({
            "league": "allsvenskan", "date": NOW.date().isoformat(),
            "home": norm_team("Hammarby IF"), "away": norm_team("AIK"),
            "home_raw": "Hammarby", "away_raw": "AIK",
            "hg": 2, "ag": 0, "source": "sofa",
        })

        report = live_signal_ledger.settle_signals(self.store, now=NOW)

        self.assertEqual(1, report["settled"])
        result = self.store.live_signal_results()[0]
        self.assertEqual(2, result["final_home_score"])
        self.assertEqual(0, result["final_away_score"])
        self.assertEqual(2, result["goals_after_signal"])
        self.assertEqual(1, result["outcome_15min"])
        self.assertEqual(1, result["outcome_more_before_ft"])
        self.assertEqual("half_loss", result["over_result"])
        self.assertEqual(-0.5, result["over_profit"])
        # append-once: ett senare varv får inte skriva om facitet
        self.assertEqual(
            0, live_signal_ledger.settle_signals(
                self.store, now=NOW + dt.timedelta(hours=1))["settled"])

    def test_facit_exposes_level_rows_and_a_forward_only_gate(self):
        # Återanvänd settlementfallet ovan i minsta möjliga form.
        self.test_result_settlement_saves_final_score_and_asian_over_profit()
        report = live_signal_ledger.facit(self.store)
        self.assertEqual("collecting", report["blind_gate"]["status"])
        self.assertEqual(1, report["blind_gate"]["n_priced_settled"])
        self.assertEqual(1, len(report["rows"]))
        self.assertEqual("watch", report["rows"][0]["signal_level"])
        self.assertEqual(-0.5, report["rows"][0]["over_profit"])
        self.assertTrue(report["rows"][0]["blind_entry"])
        self.assertTrue(report["rows"][0]["test_bet"])
        self.assertIsNone(report["rows"][0]["test_bet_exclusion"])
        self.assertEqual(
            {"captured": 1}, report["blind_gate"]["odds_status_counts"])

    def test_summary_exposes_each_reason_for_missing_live_price(self):
        rows = [
            {"match_key": f"m{i}", "captured_at": iso(NOW),
             "odds_status": status}
            for i, status in enumerate((
                "captured", "no_canonical_match", "suspended",
                "source_error:HTTPStatusError"))
        ]

        summary = live_signal_ledger._summary(rows)

        self.assertEqual(4, summary["n_matches"])
        self.assertEqual({
            "captured": 1,
            "no_canonical_match": 1,
            "source_error:HTTPStatusError": 1,
            "suspended": 1,
        }, summary["odds_status_counts"])

    def test_result_matching_repairs_one_name_only_with_strict_context(self):
        signal = {
            "captured_at": iso(NOW), "start_at": iso(NOW),
            "home": "Silkeborg", "away": "Odense",
        }
        result = {
            "date": NOW.date().isoformat(), "home": "silkeborg",
            "away": "odense boldklub", "hg": 1, "ag": 0,
        }

        found = live_signal_ledger._result_for(signal, [result])

        self.assertIsNotNone(found)
        self.assertEqual(result, found[0])
        self.assertFalse(found[1])

    def test_contextual_result_matching_stays_closed_when_ambiguous(self):
        signal = {
            "captured_at": iso(NOW), "start_at": iso(NOW),
            "home": "Silkeborg", "away": "Odense",
        }
        results = [
            {"date": NOW.date().isoformat(), "home": "silkeborg",
             "away": "odense boldklub", "hg": 1, "ag": 0},
            {"date": NOW.date().isoformat(), "home": "silkeborg",
             "away": "odense city", "hg": 2, "ag": 0},
        ]

        self.assertIsNone(live_signal_ledger._result_for(signal, results))

    def test_contextual_result_matching_honours_known_rejected_clubs(self):
        self.assertFalse(
            live_signal_ledger._context_same_team("Egersund", "Haugesund"))

    def test_facit_keeps_older_signal_versions_out_of_current_gate(self):
        def save(version, match_key, event_id, minutes_ago):
            at = iso(NOW - dt.timedelta(minutes=minutes_ago))
            self.store.live_signal_save({
                "match_key": match_key, "provider": "sofascore",
                "provider_event_id": event_id, "captured_at": at,
                "capture_version": live_radar.CAPTURE_VERSION,
                "signal_version": version, "league": "allsvenskan",
                "home": f"Hem {match_key}", "away": f"Borta {match_key}",
                "signal_level": "watch", "signal_type": "xg",
                "ou_line": 2.5, "over_odds": 2.0, "under_odds": 1.8,
                "odds_status": "captured", "recorded_at": at,
            })
            signal_id = next(
                row["id"] for row in self.store.live_signal_rows()
                if row["match_key"] == match_key
                and row["signal_version"] == version)
            self.store.live_signal_result_save({
                "signal_id": signal_id, "settled_at": iso(NOW),
                "final_home_score": 2, "final_away_score": 1,
                "goals_after_signal": 3, "outcome_more_before_ft": 1,
                "over_result": "win", "over_profit": 1.0,
            })

        save(live_radar.RADAR_VERSION, "current", "101", 10)
        save("chance-gap-shadow-v2", "legacy", "102", 20)

        report = live_signal_ledger.facit(self.store)

        self.assertEqual(1, report["blind_gate"]["n_priced_settled"])
        self.assertEqual(1, len(report["rows"]))
        self.assertEqual("current", report["rows"][0]["match_key"])
        self.assertEqual(2, report["all_versions_n_signals"])
        self.assertEqual(1, len(report["historical_versions"]))
        legacy = report["historical_versions"][0]
        self.assertEqual("chance-gap-shadow-v2", legacy["signal_version"])
        self.assertEqual(1, legacy["blind_gate"]["n_priced_settled"])


class KambiLiveTotalTests(unittest.TestCase):
    @staticmethod
    def _outcomes(line, over, under, *, status="OPEN"):
        return [
            {"type": "OT_OVER", "line": line, "odds": over,
             "status": status},
            {"type": "OT_UNDER", "line": line, "odds": under,
             "status": status},
        ]

    @staticmethod
    def _offer(line, over, under, *, tags=None, status="OPEN"):
        return {
            "criterion": {
                "label": "Antal mål",
                "englishLabel": "Total Goals",
                "lifetime": "FULL_TIME",
            },
            "tags": ["OFFERED_LIVE", *(tags or [])],
            "outcomes": KambiLiveTotalTests._outcomes(
                line, over, under, status=status),
        }

    def test_prefers_open_live_main_line_from_real_kambi_shape(self):
        response = Mock()
        response.headers = {"age": "2"}
        response.json.return_value = {"betOffers": [
            self._offer(1500, 1250, 3600),
            self._offer(2500, 1580, 2160, tags=["MAIN_LINE"]),
            self._offer(3500, 2700, 1320),
        ]}

        with patch.object(kambi.httpx, "get", return_value=response):
            result = kambi.live_total("7722", strict=True)

        response.raise_for_status.assert_called_once()
        self.assertEqual(
            {"ou": {"line": 2.5, "O": 1.58, "U": 2.16}}, result)
        self.assertEqual(2, kambi.last_age_s)

    def test_never_records_suspended_outcomes_as_available(self):
        response = Mock()
        response.headers = {}
        response.json.return_value = {"betOffers": [
            self._offer(2500, 1580, 2160, tags=["MAIN_LINE"],
                        status="SUSPENDED"),
        ]}

        with patch.object(kambi.httpx, "get", return_value=response):
            result = kambi.live_total("7722", strict=True)
        # Marknaden SÅGS men var stängd — det är en suspended-observation,
        # inte "erbjöds inte", och absolut inget pris.
        self.assertEqual({"reason": "suspended"}, result)

    def test_offer_level_suspension_blocks_open_outcomes(self):
        # Verifierat i drift 2026-07-31: Kambi kan suspendera hela betOffer:n
        # medan utfallen står kvar som OPEN. Ett sådant pris går inte att
        # rygga och får aldrig bli captured.
        offer = self._offer(2500, 1800, 1880, tags=["MAIN_LINE"])
        offer["suspended"] = True
        response = Mock()
        response.headers = {}
        response.json.return_value = {"betOffers": [offer]}

        with patch.object(kambi.httpx, "get", return_value=response):
            result = kambi.live_total("7722", strict=True)
        self.assertEqual({"reason": "suspended"}, result)

    def test_missing_market_is_not_suspended(self):
        response = Mock()
        response.headers = {}
        response.json.return_value = {"betOffers": []}
        with patch.object(kambi.httpx, "get", return_value=response):
            self.assertEqual({}, kambi.live_total("7722", strict=True))

    def test_one_sided_open_market_is_not_a_suspension_observation(self):
        # Ett ensamt ÖPPET utfall utan par är en ofullständig marknad —
        # ingen stängning observerades, så "suspended" vore fabricerat.
        offer = self._offer(2500, 1580, 2160, tags=["MAIN_LINE"])
        offer["outcomes"] = offer["outcomes"][:1]
        response = Mock()
        response.headers = {}
        response.json.return_value = {"betOffers": [offer]}
        with patch.object(kambi.httpx, "get", return_value=response):
            self.assertEqual({}, kambi.live_total("7722", strict=True))


class BestLivePriceTests(unittest.TestCase):
    @staticmethod
    def _obs(source, line, over, under, *, status="captured", offers=None):
        total = {"line": line, "O": over, "U": under}
        return {
            "source": source, "provider_event_id": source,
            "checked_at": iso(NOW), "observed_at": iso(NOW), "age_s": 0,
            "status": status, "main": total,
            "offers": offers if offers is not None else [total],
        }

    def test_highest_over_price_wins_on_exact_same_line(self):
        selected, quotes = live_signal_ledger._choose_live_price([
            self._obs("svenskaspel", 2.5, 1.95, 1.85),
            self._obs("ninja", 2.5, 2.08, 1.72),
            self._obs("pinnacle", 2.5, 2.02, 1.78),
        ])
        self.assertEqual("ninja", selected["odds_source"])
        self.assertEqual(2.08, selected["over_odds"])
        self.assertEqual(1, sum(q["selected"] for q in quotes))

    def test_different_line_is_never_called_better_odds(self):
        # Pinnacle definierar linan 2.5. Ninjas högre pris gäller Ö3.5 och är
        # ett annat spel, så det får inte vinna prisjämförelsen.
        selected, quotes = live_signal_ledger._choose_live_price([
            self._obs("svenskaspel", 2.5, 1.95, 1.85),
            self._obs("ninja", 3.5, 2.40, 1.45),
            self._obs("pinnacle", 2.5, 2.02, 1.78),
        ])
        self.assertEqual("pinnacle", selected["odds_source"])
        ninja = next(q for q in quotes if q["source"] == "ninja")
        self.assertEqual("line_mismatch", ninja["status"])
        self.assertFalse(ninja["selected"])

    def test_pinnacle_alt_line_can_beat_kambi_on_kambis_line(self):
        # Stale Pinnacle får inte ankra. Om den i stället vore färsk och hade
        # 2.5 som alternativ skulle den jämföras på exakt 2.5.
        pin = self._obs("pinnacle", 3.0, 2.05, 1.75, status="stale",
                        offers=[{"line": 2.5, "O": 2.12, "U": 1.68}])
        selected, quotes = live_signal_ledger._choose_live_price([
            self._obs("svenskaspel", 2.5, 2.00, 1.80), pin,
            self._obs("ninja", 2.5, 2.06, 1.74),
        ])
        self.assertEqual("ninja", selected["odds_source"])
        self.assertEqual("stale", next(q for q in quotes
                                        if q["source"] == "pinnacle")["status"])

class LiveSignalOddsStatusTests(unittest.TestCase):
    """Oddsbokföringens felgrenar — statusfördelningen är driftkontrollens
    underlag och får aldrig ljuga om vad som faktiskt observerades."""

    def setUp(self):
        self._source_patchers = [
            patch.object(live_signal_ledger.kambi, "live_events", return_value=[]),
            patch.object(live_signal_ledger.altenar, "live_events", return_value=[]),
            patch.object(live_signal_ledger.pinnacle.Pinnacle,
                         "soccer_live_totals", return_value=[]),
        ]
        for patcher in self._source_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.store.oddset_upsert_match({
            "id": "pin:991", "league": "allsvenskan",
            "home": "Hammarby", "away": "AIK",
            "start": iso(NOW - dt.timedelta(minutes=30)),
            "pinnacle_id": "991", "kambi_id": "7722",
        })
        self.store.live_flashscore_save(capture(NOW, 30, xg_home=0.8))

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _capture_with(self, market):
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value=market):
            live_signal_ledger.capture_signals(self.store, now=NOW)
        return self.store.live_signal_rows()[0]

    def test_suspended_market_gets_its_own_status(self):
        row = self._capture_with({"reason": "suspended"})
        self.assertEqual("no_eligible_quote", row["odds_status"])
        self.assertIsNone(row["over_odds"])
        quotes = self.store.live_signal_quotes()
        svs = next(q for q in quotes if q["source"] == "svenskaspel")
        self.assertEqual("suspended", svs["status"])
        self.assertIsNotNone(svs["observed_at"])

    def test_missing_market_is_not_offered(self):
        row = self._capture_with({})
        self.assertEqual("no_eligible_quote", row["odds_status"])
        svs = next(q for q in self.store.live_signal_quotes()
                   if q["source"] == "svenskaspel")
        self.assertEqual("not_offered", svs["status"])

    def test_source_error_is_never_an_absence_observation(self):
        with patch.object(live_signal_ledger.kambi, "live_total",
                          side_effect=TimeoutError("boom")):
            live_signal_ledger.capture_signals(self.store, now=NOW)
        row = self.store.live_signal_rows()[0]
        self.assertEqual("no_eligible_quote", row["odds_status"])
        # ett fel är ingen observation — ingen observationstid får fabriceras
        self.assertIsNone(row["odds_observed_at"])
        svs = next(q for q in self.store.live_signal_quotes()
                   if q["source"] == "svenskaspel")
        self.assertEqual("source_error:TimeoutError", svs["status"])
        self.assertIsNone(svs["observed_at"])

    def test_odds_observed_at_subtracts_http_age(self):
        market = {"ou": {"line": 2.5, "O": 2.08, "U": 1.74}}
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value=market), \
                patch.object(live_signal_ledger.kambi, "last_age_s", 300), \
                patch.object(live_signal_ledger, "_now", return_value=NOW):
            live_signal_ledger.capture_signals(self.store, now=NOW)
        row = self.store.live_signal_rows()[0]
        self.assertEqual(iso(NOW - dt.timedelta(seconds=300)),
                         row["odds_observed_at"])
        self.assertEqual("flashscore", row["clock_source"])

    def test_live_kambi_list_recovers_price_without_prematch_canonical(self):
        self.store.conn.execute("DELETE FROM oddset_matches")
        self.store.conn.commit()
        market = {"ou": {"line": 2.5, "O": 2.08, "U": 1.74}}
        events = [{"id": "9090", "home": "Hammarby", "away": "AIK",
                   "group": "Allsvenskan"}]
        with patch.object(live_signal_ledger.kambi, "live_events",
                          return_value=events) as live_events, \
                patch.object(live_signal_ledger.kambi, "live_total",
                             return_value=market) as live_total:
            report = live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(1, report["priced"])
        self.assertEqual("captured", self.store.live_signal_rows()[0]["odds_status"])
        live_events.assert_called_once_with(timeout=8.0)
        live_total.assert_called_once_with("9090", timeout=8.0, strict=True)

    def test_ambiguous_live_kambi_list_never_guesses_an_odds_event(self):
        self.store.conn.execute("DELETE FROM oddset_matches")
        self.store.conn.commit()
        events = [
            {"id": "9090", "home": "Hammarby", "away": "AIK"},
            {"id": "9091", "home": "Hammarby IF", "away": "AIK"},
        ]
        with patch.object(live_signal_ledger.kambi, "live_events",
                          return_value=events), \
                patch.object(live_signal_ledger.kambi, "live_total") as live_total:
            report = live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(0, report["priced"])
        self.assertEqual("no_eligible_quote",
                         self.store.live_signal_rows()[0]["odds_status"])
        live_total.assert_not_called()


class MatchKeyLockTests(unittest.TestCase):
    """Nyckellåset: samma fysiska match får aldrig två journalnycklar."""

    def setUp(self):
        self._source_patchers = [
            patch.object(live_signal_ledger.kambi, "live_events", return_value=[]),
            patch.object(live_signal_ledger.altenar, "live_events", return_value=[]),
            patch.object(live_signal_ledger.pinnacle.Pinnacle,
                         "soccer_live_totals", return_value=[]),
        ]
        for patcher in self._source_patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_late_canonical_link_reuses_the_first_key(self):
        # Följer syns INNAN matchen finns i oddset_matches → rå nyckel.
        self.store.live_flashscore_save(capture(
            NOW - dt.timedelta(minutes=4), 30, xg_home=0.8))
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value={}):
            live_signal_ledger.capture_signals(
                self.store, now=NOW - dt.timedelta(minutes=4))
        self.assertEqual(
            "flashscore:HAMAIK01",
            self.store.live_signal_rows()[0]["match_key"])

        # Kanoniska raden dyker upp mitt i matchen; Stark eskalerar.
        self.store.oddset_upsert_match({
            "id": "pin:991", "league": "allsvenskan",
            "home": "Hammarby", "away": "AIK",
            "start": iso(NOW - dt.timedelta(minutes=34)),
            "pinnacle_id": "991", "kambi_id": "7722",
        })
        self.store.live_flashscore_save(capture(NOW, 34, xg_home=1.3))
        market = {"ou": {"line": 2.5, "O": 2.08, "U": 1.74}}
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value=market):
            live_signal_ledger.capture_signals(self.store, now=NOW)
            # och watch-nivån får INTE sparas om under den nya identiteten
            live_signal_ledger.capture_signals(self.store, now=NOW)

        rows = self.store.live_signal_rows()
        self.assertEqual(["watch", "strong"],
                         [row["signal_level"] for row in rows])
        self.assertEqual({"flashscore:HAMAIK01"},
                         {row["match_key"] for row in rows})
        # kanoniska id:t bokförs ändå informativt på eskaleringsraden
        self.assertEqual("pin:991", rows[1]["match_id"])
        facit = live_signal_ledger.facit(self.store)
        self.assertEqual(1, facit["blind_gate"]["n_matches"])

    def _saved_row(self, *, match_key, provider="sofascore",
                   provider_event_id=10852411, home="Hammarby IF",
                   away="AIK", start_at=None,
                   minutes_ago=10):
        self.store.live_signal_save({
            "match_key": match_key, "provider": provider,
            "provider_event_id": provider_event_id,
            "captured_at": iso(NOW - dt.timedelta(minutes=minutes_ago)),
            "capture_version": live_radar.CAPTURE_VERSION,
            "signal_version": live_radar.RADAR_VERSION,
            "league": "friendlies", "home": home, "away": away,
            "start_at": start_at,
            "signal_level": "watch", "signal_type": "xg",
            "odds_status": "no_canonical_match",
            "recorded_at": iso(NOW - dt.timedelta(minutes=minutes_ago)),
        })

    def test_cross_provider_flip_locks_via_team_identity(self):
        # Första raden bokförd under Sofascore-identitet...
        self._saved_row(match_key="10852411")
        # ...och nästa varv bär bara FotMob matchen (inget delat event-id).
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": "fotmob:4621334", "fotmob_id": 4621334,
            "league": "friendlies", "home": "Hammarby", "away": "AIK",
        }, NOW, live_radar.RADAR_VERSION)
        self.assertEqual("10852411", locked)

    def test_mirrored_orientation_still_locks(self):
        # Källorna är oense om hemmalaget på neutral plan — samma fysiska
        # match får inte bli två nycklar bara för att kortet är speglat.
        self._saved_row(match_key="10852411", home="AIK", away="Hammarby IF")
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": "fotmob:4621334", "fotmob_id": 4621334,
            "league": "friendlies", "home": "Hammarby", "away": "AIK",
        }, NOW, live_radar.RADAR_VERSION)
        self.assertEqual("10852411", locked)

    def test_same_provider_with_other_id_is_proof_of_another_match(self):
        # 'Inter'–'Milan' bokförd under sofascore-id 100. Ett NYTT sofascore-
        # kort med eget id (U23-derbyt, prefix-lika namn) är BEVISAT en annan
        # match — får aldrig låsas ihop och tappas.
        self._saved_row(match_key="100", provider_event_id=100,
                        home="Inter", away="Milan")
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": 200,
            "league": "friendlies", "home": "Inter U23",
            "away": "Milan Futuro",
        }, NOW, live_radar.RADAR_VERSION)
        self.assertIsNone(locked)

    def test_double_header_start_gap_never_locks(self):
        # Samma lag två gånger samma dag (försäsong): returmötet med egen
        # avspark >3 h senare är en ANNAN match.
        self._saved_row(match_key="111", provider_event_id=111,
                        start_at=iso(NOW - dt.timedelta(hours=4)))
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": "fotmob:222", "fotmob_id": 222,
            "league": "friendlies", "home": "Hammarby", "away": "AIK",
            "start_at": iso(NOW),
        }, NOW, live_radar.RADAR_VERSION)
        self.assertIsNone(locked)

    def test_ambiguous_team_match_never_locks(self):
        for key, event_id, home in (("a1", 101, "Hammarby IF"),
                                    ("a2", 102, "Hammarby FF")):
            self._saved_row(match_key=key, provider_event_id=event_id,
                            home=home)
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": "fotmob:5", "fotmob_id": 5,
            "league": "friendlies", "home": "Hammarby", "away": "AIK",
        }, NOW, live_radar.RADAR_VERSION)
        self.assertIsNone(locked)

    def test_affiliated_team_is_not_a_lock_candidate(self):
        self._saved_row(match_key="tff", provider_event_id=103,
                        home="Hammarby TFF")
        locked = live_signal_ledger._locked_key(self.store, {
            "event_id": "fotmob:5", "fotmob_id": 5,
            "league": "friendlies", "home": "Hammarby", "away": "AIK",
        }, NOW, live_radar.RADAR_VERSION)
        self.assertIsNone(locked)


class ClockPairTests(unittest.TestCase):
    """Journalen LÄSER signalens `basis` i stället för att härleda lånet igen.

    Två oberoende härledningar av samma sak gick isär i verifieringsrundan
    2026-08-01. Basis fylls i när nivån räknas och bär `<fält>_source` per
    fält, så journalen kan inte längre säga något annat än signalen — och
    lånets riktning följer automatiskt med när ankarkällan byts.
    """

    @staticmethod
    def _match(basis, **extra):
        return {"event_id": "flashscore:AB12", "captured_at": iso(NOW),
                "signal": {"basis": basis}, **extra}

    def test_fotmob_halftime_keeps_own_goals_and_borrows_only_the_clock(self):
        source = {"minute": None, "home_score": 1, "away_score": 0}
        match = self._match({
            "minute": 46, "minute_source": "flashscore",
            "home_score": 1, "home_score_source": "fotmob",
            "away_score": 0, "away_score_source": "fotmob"})
        clock = live_signal_ledger._clock("fotmob", source, match)
        # FotMobs mål (signalens basis) behålls; bara klockan lånas — ett
        # helparslån hade gett en rad som motsäger signal_score/chance_gap.
        self.assertEqual({"minute": 46, "home_score": 1, "away_score": 0,
                          "clock_source": "fotmob+flashscore",
                          "clock_observed_at": iso(NOW)}, clock)

    def test_fully_borrowed_pair_is_marked_as_the_lender_alone(self):
        source = {"minute": None, "home_score": None, "away_score": None}
        match = self._match({
            "minute": 46, "minute_source": "flashscore",
            "home_score": 1, "home_score_source": "flashscore",
            "away_score": 1, "away_score_source": "flashscore"})
        clock = live_signal_ledger._clock("fotmob", source, match)
        self.assertEqual({"minute": 46, "home_score": 1, "away_score": 1,
                          "clock_source": "flashscore",
                          "clock_observed_at": iso(NOW)}, clock)

    def test_unborrowed_card_never_names_a_lender(self):
        source = {"minute": None, "home_score": 0, "away_score": 0}
        match = self._match({
            "minute": None, "minute_source": None,
            "home_score": 0, "home_score_source": "fotmob",
            "away_score": 0, "away_score_source": "fotmob"})
        clock = live_signal_ledger._clock("fotmob", source, match)
        self.assertEqual("fotmob", clock["clock_source"])
        self.assertIsNone(clock["minute"])
        self.assertIsNone(clock["clock_observed_at"])

    def test_card_without_basis_makes_no_guess(self):
        """Historiska rader saknar basis — då gäller providerns egna värden,
        aldrig en rekonstruktion i efterhand."""
        source = {"minute": 30, "home_score": 0, "away_score": 0}
        clock = live_signal_ledger._clock(
            "flashscore", source, {"event_id": "flashscore:X", **source})
        self.assertEqual({"minute": 30, "home_score": 0, "away_score": 0,
                          "clock_source": "flashscore",
                          "clock_observed_at": None}, clock)


class SettlementGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _signal(self, **overrides):
        first = capture(NOW - dt.timedelta(hours=5), 30, xg_home=0.8)
        self.store.live_flashscore_save(first)
        row = {
            "match_key": "pin:991", "match_id": "pin:991",
            "provider": "flashscore", "provider_event_id": "HAMAIK01",
            "captured_at": first["captured_at"],
            "capture_version": first["capture_version"],
            "signal_version": live_radar.RADAR_VERSION,
            "league": "allsvenskan", "home": "Hammarby IF", "away": "AIK",
            "start_at": first["start_at"], "minute": 30,
            "home_score": 0, "away_score": 0,
            "signal_level": "watch", "signal_type": "xg",
            "ou_line": 2.25, "over_odds": 2.0, "under_odds": 1.8,
            "odds_source": "svenskaspel", "odds_status": "captured",
            "recorded_at": first["captured_at"],
        }
        row.update(overrides)
        self.store.live_signal_save(row)
        return first

    def _result(self, hg, ag):
        from app.oddset import norm_team
        self.store.oddset_save_result({
            "league": "allsvenskan", "date": NOW.date().isoformat(),
            "home": norm_team("Hammarby IF"), "away": norm_team("AIK"),
            "home_raw": "Hammarby", "away_raw": "AIK",
            "hg": hg, "ag": ag, "source": "sofa",
        })

    def test_official_final_proves_a_late_goal_before_ft(self):
        # Serien slutar direkt efter signalen (inga senare captures) men
        # officiella FT-resultatet bevisar två mål till — det får ALDRIG
        # censureras medan en identisk målfri match hade fått 0.
        self._signal()
        self._result(2, 0)
        report = live_signal_ledger.settle_signals(self.store, now=NOW)
        self.assertEqual(1, report["settled"])
        result = self.store.live_signal_results()[0]
        self.assertEqual(2, result["goals_after_signal"])
        self.assertEqual(1, result["outcome_more_before_ft"])
        self.assertIsNone(result["censored_ft"])
        # 15-minutersfönstret förblir ärligt censurerat: målens TIDPUNKT
        # är okänd utan captures som täcker fönstret.
        self.assertIsNone(result["outcome_15min"])
        self.assertEqual("window_not_covered", result["censored_15min"])

    def test_score_regress_is_invalid_not_a_crash(self):
        self._signal(home_score=1, away_score=1)
        self._result(0, 0)
        report = live_signal_ledger.settle_signals(self.store, now=NOW)
        self.assertEqual(0, report["settled"])
        self.assertEqual(1, report["ambiguous_or_invalid"])

    def test_missing_series_moment_is_invalid_not_a_crash(self):
        self._signal(captured_at=iso(NOW - dt.timedelta(hours=6)))
        self._result(2, 0)
        report = live_signal_ledger.settle_signals(self.store, now=NOW)
        self.assertEqual(0, report["settled"])
        self.assertEqual(1, report["ambiguous_or_invalid"])

    def test_null_away_goals_neither_crashes_nor_settles(self):
        self._signal()
        self._result(2, None)
        report = live_signal_ledger.settle_signals(self.store, now=NOW)
        self.assertEqual(0, report["settled"])
        self.assertEqual(1, report["waiting_result"])

    def test_recent_signal_can_refresh_result_before_settlement(self):
        self._signal(start_at=iso(NOW - dt.timedelta(hours=5, minutes=30)))

        def save_result(store, signals, *, now):
            self.assertEqual(1, len(signals))
            self.assertEqual("allsvenskan", signals[0]["league"])
            self.assertEqual(NOW, now)
            self._result(1, 0)
            return {"eligible": 1, "matched": 1, "saved": 1}

        with patch.object(live_signal_ledger.flashscore_data,
                          "refresh_recent_results",
                          side_effect=save_result) as refresh:
            report = live_signal_ledger.settle_signals(
                self.store, now=NOW, refresh_recent=True)

        refresh.assert_called_once()
        self.assertEqual(1, report["settled"])
        self.assertEqual(1, report["recent_results"]["saved"])

    def test_borrowed_journal_clock_and_score_are_the_settlement_moment(self):
        event_id = "SKg88Q3T"
        first_at = NOW - dt.timedelta(hours=5)
        common = {
            "flashscore_id": event_id,
            "capture_version": flashscore.CAPTURE_VERSION,
            "league": "allsvenskan", "tournament": "Allsvenskan",
            "home": "Hammarby IF", "away": "AIK",
            "start_at": iso(first_at - dt.timedelta(minutes=30)),
            "xg_home": 0.8, "xg_away": 0.2,
        }
        # Råprovidern saknade både klocka och ställning när statistiken sågs.
        self.store.live_flashscore_save({
            **common, "captured_at": iso(first_at), "minute": None,
            "home_score": None, "away_score": None,
        })
        self.store.live_flashscore_save({
            **common, "captured_at": iso(first_at + dt.timedelta(minutes=10)),
            "minute": 40, "home_score": 1, "away_score": 0,
        })
        self.store.live_signal_save({
            "match_key": "pin:991", "match_id": "pin:991",
            "provider": "flashscore", "provider_event_id": event_id,
            "captured_at": iso(first_at),
            "capture_version": flashscore.CAPTURE_VERSION,
            "signal_version": live_radar.RADAR_VERSION,
            "league": "allsvenskan", "home": "Hammarby IF", "away": "AIK",
            "start_at": common["start_at"],
            # Det här är signalbasen användaren faktiskt såg, lånad från Sofa.
            "minute": 30, "home_score": 0, "away_score": 0,
            "clock_source": "sofascore",
            "clock_observed_at": iso(first_at + dt.timedelta(minutes=1)),
            "signal_level": "watch", "signal_type": "xg",
            "odds_status": "not_offered", "recorded_at": iso(first_at),
        })
        self._result(2, 0)

        report = live_signal_ledger.settle_signals(self.store, now=NOW)

        self.assertEqual(1, report["settled"])
        result = self.store.live_signal_results()[0]
        self.assertEqual(1, result["outcome_15min"])
        self.assertIsNone(result["censored_15min"])
        self.assertEqual(2, result["goals_after_signal"])


class BlindGateTests(unittest.TestCase):
    """Gatens diskriminerande grenar — pass kräver undre KI90 > 0."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _seed(self, profits):
        for index, profit in enumerate(profits):
            at = iso(NOW - dt.timedelta(days=index * 2))
            self.store.live_signal_save({
                "match_key": f"m{index}", "provider": "sofascore",
                "provider_event_id": 1000 + index, "captured_at": at,
                "capture_version": live_radar.CAPTURE_VERSION,
                "signal_version": live_radar.RADAR_VERSION,
                "league": "allsvenskan", "home": f"Hem {index}",
                "away": f"Borta {index}", "signal_level": "watch",
                "signal_type": "xg", "ou_line": 2.5, "over_odds": 2.0,
                "under_odds": 1.8, "odds_source": "svenskaspel",
                "odds_status": "captured", "recorded_at": at,
            })
            # raderna är sorterade på captured_at — slå upp id via nyckeln
            signal_id = next(row["id"] for row in self.store.live_signal_rows()
                             if row["match_key"] == f"m{index}")
            self.store.live_signal_result_save({
                "signal_id": signal_id, "settled_at": iso(NOW),
                "final_home_score": 2, "final_away_score": 1,
                "goals_after_signal": 3, "outcome_more_before_ft": 1,
                "over_result": "win" if profit > 0 else "loss",
                "over_profit": profit,
            })

    def test_gate_passes_on_positive_lower_ci(self):
        with patch.object(live_signal_ledger, "BLIND_MIN_PRICED", 3), \
                patch.object(live_signal_ledger, "BLIND_MIN_DAYS", 1), \
                patch.object(live_signal_ledger, "BLIND_MIN_MATCHDAYS", 1):
            self._seed([1.0, 1.0, 1.0, 1.0])
            gate = live_signal_ledger.facit(self.store)["blind_gate"]
        self.assertEqual("pass", gate["status"])
        self.assertGreater(gate["roi_ci90"][0], 0)

    def test_gate_withholds_support_on_negative_roi(self):
        with patch.object(live_signal_ledger, "BLIND_MIN_PRICED", 3), \
                patch.object(live_signal_ledger, "BLIND_MIN_DAYS", 1), \
                patch.object(live_signal_ledger, "BLIND_MIN_MATCHDAYS", 1):
            self._seed([-1.0, -1.0, -1.0, -1.0])
            gate = live_signal_ledger.facit(self.store)["blind_gate"]
        self.assertEqual("no_support", gate["status"])

    def test_escalation_never_doubles_the_blind_cohort(self):
        with patch.object(live_signal_ledger, "BLIND_MIN_PRICED", 3), \
                patch.object(live_signal_ledger, "BLIND_MIN_DAYS", 1), \
                patch.object(live_signal_ledger, "BLIND_MIN_MATCHDAYS", 1):
            self._seed([1.0, 1.0, 1.0])
            # Stark-eskalering på match m0, också prissatt och settlad —
            # den får synas i nivågrupperna men ALDRIG i blindkohorten.
            at = iso(NOW - dt.timedelta(days=0, minutes=-20))
            self.store.live_signal_save({
                "match_key": "m0", "provider": "sofascore",
                "provider_event_id": 1000, "captured_at": at,
                "capture_version": live_radar.CAPTURE_VERSION,
                "signal_version": live_radar.RADAR_VERSION,
                "league": "allsvenskan", "home": "Hem 0", "away": "Borta 0",
                "signal_level": "strong", "signal_type": "xg",
                "ou_line": 2.5, "over_odds": 3.0, "under_odds": 1.4,
                "odds_source": "svenskaspel", "odds_status": "captured",
                "recorded_at": at,
            })
            signal_id = next(row["id"] for row in self.store.live_signal_rows()
                             if row["signal_level"] == "strong")
            self.store.live_signal_result_save({
                "signal_id": signal_id, "settled_at": iso(NOW),
                "final_home_score": 2, "final_away_score": 1,
                "goals_after_signal": 3, "outcome_more_before_ft": 1,
                "over_result": "win", "over_profit": 2.0,
            })
            report = live_signal_ledger.facit(self.store)
        self.assertEqual(3, report["blind_gate"]["n_priced_settled"])
        self.assertEqual(3, report["blind_gate"]["n_matches"])
        levels = {(g["signal_level"], g["n_signals"])
                  for g in report["groups"]}
        self.assertIn(("strong", 1), levels)
        strong = next(g for g in report["groups"]
                      if g["signal_level"] == "strong")
        self.assertEqual(0, strong["n_test_bets"])
        self.assertEqual(0, strong["n_test_bets_settled"])
        rows = {row["signal_level"]: row for row in report["rows"]
                if row["match_key"] == "m0"}
        self.assertTrue(rows["watch"]["test_bet"])
        self.assertFalse(rows["strong"]["test_bet"])
        self.assertEqual("later_signal", rows["strong"]["test_bet_exclusion"])


class SourceRoiTests(unittest.TestCase):
    """ROI per oddskälla på exakt samma lina — diagnostik, aldrig grind."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _signal(self, key: str, quotes: list[dict], *, goals=(2, 1)):
        at = iso(NOW - dt.timedelta(days=len(key)))
        best = next((q for q in quotes if q.get("selected")), None)
        self.store.live_signal_save({
            "match_key": key, "provider": "sofascore",
            "provider_event_id": abs(hash(key)) % 100000, "captured_at": at,
            "capture_version": live_radar.CAPTURE_VERSION,
            "signal_version": live_radar.RADAR_VERSION,
            "league": "allsvenskan", "home": f"Hem {key}", "away": f"Borta {key}",
            "signal_level": "watch", "signal_type": "xg",
            "ou_line": best["line"] if best else None,
            "over_odds": best["over_odds"] if best else None,
            "odds_source": best["source"] if best else None,
            "odds_status": "captured" if best else "no_eligible_quote",
            "recorded_at": at,
        }, quotes=[{"provider_event_id": None, "observed_at": at,
                    "checked_at": at, "under_odds": None, **q} for q in quotes])
        signal_id = next(row["id"] for row in self.store.live_signal_rows()
                         if row["match_key"] == key)
        self.store.live_signal_result_save({
            "signal_id": signal_id, "settled_at": iso(NOW),
            "final_home_score": goals[0], "final_away_score": goals[1],
            "goals_after_signal": sum(goals), "over_result": "win",
            "over_profit": (best["over_odds"] - 1.0) if best else None,
        })

    def test_roi_per_kalla_raknas_pa_samma_lina(self):
        # 3 mål mot lina 2,5 ⇒ Över vinner: vinsten ÄR prisskillnaden.
        self._signal("a", [
            {"source": "pinnacle", "status": "captured", "line": 2.5,
             "over_odds": 2.10, "selected": 1},
            {"source": "svenskaspel", "status": "captured", "line": 2.5,
             "over_odds": 1.90, "selected": 0},
            {"source": "ninja", "status": "no_match", "line": None,
             "over_odds": None, "selected": 0},
        ])
        per = live_signal_ledger.facit(self.store)["blind_gate"]["source_roi"]

        self.assertAlmostEqual(1.10, per["pinnacle"]["roi_over"], places=4)
        self.assertAlmostEqual(0.90, per["svenskaspel"]["roi_over"], places=4)
        # Källan som inte listade matchen får INGEN ROI-rad, men syns i asked.
        self.assertIsNone(per["ninja"]["roi_over"])
        self.assertEqual(1, per["ninja"]["n_asked"])
        self.assertEqual(0, per["ninja"]["n_priced"])

    def test_ankaret_markeras_som_ospelbart(self):
        self._signal("b", [
            {"source": "pinnacle", "status": "captured", "line": 2.5,
             "over_odds": 2.10, "selected": 1},
            {"source": "svenskaspel", "status": "captured", "line": 2.5,
             "over_odds": 1.90, "selected": 0},
        ])
        per = live_signal_ledger.facit(self.store)["blind_gate"]["source_roi"]
        self.assertFalse(per["pinnacle"]["playable"])
        self.assertTrue(per["svenskaspel"]["playable"])
        # n_best svarar på "vinner ankaret alltid prisjämförelsen?"
        self.assertEqual(1, per["pinnacle"]["n_best"])
        self.assertEqual(0, per["svenskaspel"]["n_best"])

    def test_osettlad_signal_bidrar_inte(self):
        self.store.live_signal_save({
            "match_key": "c", "provider": "sofascore", "provider_event_id": 42,
            "captured_at": iso(NOW), "capture_version": live_radar.CAPTURE_VERSION,
            "signal_version": live_radar.RADAR_VERSION, "league": "allsvenskan",
            "home": "Hem", "away": "Borta", "signal_level": "watch",
            "signal_type": "xg", "ou_line": 2.5, "over_odds": 2.0,
            "odds_source": "svenskaspel", "odds_status": "captured",
            "recorded_at": iso(NOW),
        }, quotes=[{"source": "svenskaspel", "provider_event_id": None,
                    "observed_at": iso(NOW), "checked_at": iso(NOW),
                    "status": "captured", "line": 2.5, "over_odds": 2.0,
                    "under_odds": 1.8, "selected": 1}])
        per = live_signal_ledger.facit(self.store)["blind_gate"]["source_roi"]
        self.assertEqual({}, per)


class CanonicalMatchTests(unittest.TestCase):
    """Livekort→Oddset-identitet: ett lag räcker, men aldrig vid tvetydighet."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _oddset(self, mid, home, away, *, minutes=0, league="belgian_pro_league"):
        self.store.oddset_upsert_match({
            "id": mid, "league": league, "home": home, "away": away,
            "start": iso(NOW + dt.timedelta(minutes=minutes)),
            "pinnacle_id": mid.split(":")[-1], "kambi_id": "9" + mid.split(":")[-1],
        })

    def _live(self, home, away, *, league="belgian_pro_league", minutes=0):
        return {"league": league, "home": home, "away": away,
                "start_at": iso(NOW + dt.timedelta(minutes=minutes)),
                "captured_at": iso(NOW)}

    def test_ett_lag_racker_nar_avspark_och_liga_ar_samma(self):
        # Uppmätt fall: `Charleroi` mot Oddsets `Sporting de Charleroi`.
        self._oddset("pin:501", "Lommel SK", "Sporting de Charleroi", minutes=3)
        hit = live_signal_ledger._canonical_match(
            self.store, self._live("Lommel SK", "Charleroi"))
        self.assertIsNotNone(hit)
        self.assertEqual("pin:501", hit["id"])

    def test_bada_lagen_strikt_gar_fore(self):
        self._oddset("pin:502", "KRC Genk", "Westerlo", minutes=5)
        self._oddset("pin:503", "Genk", "Westerlo", minutes=1)
        hit = live_signal_ledger._canonical_match(
            self.store, self._live("Genk", "Westerlo"))
        self.assertEqual("pin:503", hit["id"], "strikt träff ska vinna")

    def test_tva_ensidiga_kandidater_ger_ingen_lankning(self):
        # Westerlo förekommer i TVÅ Oddset-rader i samma liga och samma
        # tidsfönster (dubblett eller flyttad match). Livekortet delar då ett
        # lag med båda. Att välja den närmaste i tid vore en gissning, så
        # steg 3 ska avstå helt.
        self._oddset("pin:504", "Club Brugge", "Westerlo")
        self._oddset("pin:505", "Westerlo", "Anderlecht", minutes=1)
        self.assertIsNone(live_signal_ledger._canonical_match(
            self.store, self._live("Genk", "Westerlo")))

    def test_truppmarkor_lankas_aldrig_med_ett_lag(self):
        # `Inter` mot `Como` och `Inter U23` mot `Como` är två matcher.
        self._oddset("pin:506", "Inter U23", "Como")
        self.assertIsNone(live_signal_ledger._canonical_match(
            self.store, self._live("Inter", "Como")))

    def test_fel_liga_lankas_aldrig(self):
        self._oddset("pin:507", "Lommel SK", "Sporting de Charleroi",
                     league="danish_superliga")
        self.assertIsNone(live_signal_ledger._canonical_match(
            self.store, self._live("Lommel SK", "Charleroi")))

    def test_for_stor_avsparksskillnad_lankas_aldrig_pa_ett_lag(self):
        # Ett lag räcker BARA inom LINK_START_TOLERANCE_MIN — annars kan det
        # vara nästa omgångs match mot en annan motståndare.
        self._oddset("pin:508", "Lommel SK", "Sporting de Charleroi",
                     minutes=live_radar.LINK_START_TOLERANCE_MIN + 20)
        self.assertIsNone(live_signal_ledger._canonical_match(
            self.store, self._live("Lommel SK", "Charleroi")))

    def test_speglad_orientering_lankas(self):
        self._oddset("pin:509", "Sporting de Charleroi", "Lommel SK", minutes=2)
        hit = live_signal_ledger._canonical_match(
            self.store, self._live("Lommel SK", "Charleroi"))
        self.assertEqual("pin:509", hit["id"])


if __name__ == "__main__":
    unittest.main()
