"""Framåtriktat facit för de signaler användaren faktiskt ser i live-radarn."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import kambi, live_radar, live_signal_ledger
from app.oddset import norm_team
from app.storage import Storage


NOW = dt.datetime(2026, 7, 31, 18, 30, tzinfo=dt.timezone.utc)


def iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def capture(at: dt.datetime, minute: int, *, xg_home: float,
            home_score: int = 0, away_score: int = 0) -> dict:
    return {
        "event_id": 88001,
        "captured_at": iso(at),
        "capture_version": live_radar.CAPTURE_VERSION,
        "league": "allsvenskan",
        "tournament": "Allsvenskan",
        "home": "Hammarby IF",
        "away": "AIK",
        "start_at": iso(NOW - dt.timedelta(minutes=minute)),
        "status": "2nd half" if minute > 45 else "1st half",
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
        "touches_box_home": 20,
        "touches_box_away": 5,
    }


class LiveSignalLedgerTests(unittest.TestCase):
    def setUp(self):
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

    def test_first_level_is_append_once_and_live_ou_is_fetched_once(self):
        # 0.8 xG-gap ⇒ watch men inte strong.
        self.store.oddset_save_live_capture(capture(
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

    def test_level_escalation_is_a_new_decision_but_repeated_level_is_not(self):
        self.store.oddset_save_live_capture(capture(
            NOW - dt.timedelta(minutes=4), 30, xg_home=0.8))
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value={}):
            live_signal_ledger.capture_signals(
                self.store, now=NOW - dt.timedelta(minutes=4))

        # 1.3 xG-gap ⇒ strong. Samma match får nu exakt en ny nivåpost.
        self.store.oddset_save_live_capture(capture(
            NOW, 34, xg_home=1.3))
        with patch.object(live_signal_ledger.kambi, "live_total",
                          return_value={}):
            live_signal_ledger.capture_signals(self.store, now=NOW)
            live_signal_ledger.capture_signals(self.store, now=NOW)

        self.assertEqual(
            ["watch", "strong"],
            [row["signal_level"] for row in self.store.live_signal_rows()])

    def test_info_moment_is_not_a_signal_bet(self):
        self.store.oddset_save_live_capture(capture(
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
        self.store.oddset_save_live_capture(first)
        self.store.oddset_save_live_capture(later)
        self.store.live_signal_save({
            "match_key": "pin:991", "match_id": "pin:991",
            "provider": "sofascore", "provider_event_id": 88001,
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
            "league": "allsvenskan", "date": "2026-07-31",
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
            self.assertEqual({}, kambi.live_total("7722", strict=True))


if __name__ == "__main__":
    unittest.main()
