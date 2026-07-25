import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import live_radar
from app.storage import Storage


NOW = dt.datetime(2026, 7, 25, 19, 10, tzinfo=dt.timezone.utc)
AT = "2026-07-25T19:10:00Z"


def event(description="2nd half"):
    return {
        "id": 123,
        "tournament": {
            "uniqueTournament": {"id": 20, "name": "Eliteserien"}},
        "homeTeam": {"name": "Home"},
        "awayTeam": {"name": "Away"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
        "startTimestamp": int((NOW - dt.timedelta(minutes=70)).timestamp()),
        "status": {"type": "inprogress", "description": description},
        "time": {
            "currentPeriodStartTimestamp":
                int((NOW - dt.timedelta(minutes=25)).timestamp())},
    }


def stats(xg=(3.0, 0.4), big=(4, 1), shots=(18, 5),
          on=(9, 2), inside=(14, 3), touches=(37, 8)):
    values = {
        "expectedGoals": xg,
        "bigChanceCreated": big,
        "totalShotsOnGoal": shots,
        "shotsOnGoal": on,
        "totalShotsInsideBox": inside,
        "touchesInOppBox": touches,
        "cornerKicks": (8, 2),
    }
    return {"statistics": [{"period": "ALL", "groups": [{
        "groupName": "all",
        "statisticsItems": [
            {"key": key, "homeValue": pair[0], "awayValue": pair[1]}
            for key, pair in values.items()
        ],
    }]}]}


class LiveRadarTests(unittest.TestCase):
    def test_global_friendly_requires_match_in_our_oddset_view(self):
        friendly = event()
        friendly["tournament"]["uniqueTournament"] = {
            "id": 853, "name": "Club Friendly Games"}
        self.assertFalse(live_radar._known_friendly(friendly, []))
        self.assertTrue(live_radar._known_friendly(friendly, [{
            "league": "friendlies", "home": "Home FC", "away": "Away",
            "start": "2026-07-25T18:00:00Z",
        }]))

    def test_capture_parses_observed_xg_and_match_clock(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)

        self.assertEqual("eliteserien", capture["league"])
        self.assertEqual(70, capture["minute"])
        self.assertEqual(3.0, capture["xg_home"])
        self.assertEqual(9, capture["shots_on_home"])
        self.assertEqual(37, capture["touches_box_home"])

    def test_large_xg_gap_is_shadow_signal_while_time_remains(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("strong", signal["level"])
        self.assertEqual("xg", signal["kind"])
        self.assertEqual("Home", signal["team"])
        self.assertEqual(2.0, signal["chance_gap"])
        self.assertEqual(20, signal["remaining_min"])

    def test_xg_missing_uses_explicitly_warned_proxy(self):
        """Proxyn måste vara märkt som proxy. Märkningen bärs av `kind` (som
        UI:t sorterar på) OCH av texten — den tidigare separata
        `warning`-raden per kort sa samma sak en tredje gången och flyttades
        till radarns fotnot 2026-07-25."""
        capture = live_radar.parse_capture(
            event(), stats(xg=(None, None)), captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("watch", signal["level"])
        self.assertEqual("proxy", signal["kind"])
        self.assertIn("proxy", signal["reason"].casefold())

    def test_missing_chance_fields_are_not_interpreted_as_zero(self):
        capture = live_radar.parse_capture(
            event(), None, captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("no_stats", signal["kind"])
        self.assertEqual("info", signal["level"])
        self.assertEqual(0.0, signal["score"])
        # texten ska peka ut KÄLLAN som gränsen, inte antyda ett mätt nollvärde
        self.assertIn("källan", signal["reason"].casefold())

    def test_late_match_does_not_signal_even_with_historical_gap(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)
        capture["minute"] = 84

        self.assertEqual("info", live_radar.radar_signal(capture)["level"])

    def test_capture_storage_is_idempotent_and_payload_is_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                capture = live_radar.parse_capture(
                    event(), stats(), captured_at=AT, now=NOW)
                self.assertEqual(1, store.oddset_save_live_capture(capture))
                self.assertEqual(0, store.oddset_save_live_capture(capture))

                payload = live_radar.payload(store, now=NOW)
                self.assertEqual("shadow", payload["mode"])
                self.assertEqual(1, payload["signal_count"])
                self.assertEqual(1, len(payload["matches"]))
            finally:
                store.close()

    def test_payload_uses_real_fifteen_minute_capture_for_recent_xg(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                previous = live_radar.parse_capture(
                    event(), stats(xg=(1.5, 0.3)),
                    captured_at="2026-07-25T18:55:00Z", now=NOW)
                current = live_radar.parse_capture(
                    event(), stats(xg=(3.0, 0.4)),
                    captured_at=AT, now=NOW)
                store.oddset_save_live_capture(previous)
                store.oddset_save_live_capture(current)

                signal = live_radar.payload(
                    store, now=NOW)["matches"][0]["signal"]
                self.assertEqual(1.5, signal["recent_xg"])
                self.assertIn("senaste 15 min", signal["reason"])
            finally:
                store.close()

    def test_source_health_fails_when_no_live_stats_can_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                def sofa(path):
                    if path == "/sport/football/events/live":
                        return {"events": [event()]}
                    raise RuntimeError("stats unavailable")

                with patch.object(live_radar, "_live_get", side_effect=sofa):
                    report = live_radar.collect(store, now=NOW)

                self.assertEqual(1, report["live"])
                self.assertEqual(0, report["stats_ok"])
                health = next(
                    row for row in store.oddset_source_health()
                    if row["source"] == "sofascore" and row["scope"] == "live")
                self.assertFalse(health["ok"])
                self.assertIn("RuntimeError", health["error"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()


class LiveRadarIsolationTests(unittest.TestCase):
    """Härdningen 2026-07-25: radarn får aldrig skada den spelbara vägen."""

    def test_radar_har_egen_httpklient_skild_fran_modellen(self):
        # Delade tidigare _sofa_get med oddset_data (xG till modellen) — en
        # shadow-poll var 5:e minut kunde då strypa den spelbara pipelinen.
        from app import oddset_data
        self.assertTrue(hasattr(live_radar, "_live_get"))
        self.assertFalse(hasattr(live_radar, "_sofa_get"))
        self.assertLess(live_radar.LIVE_TIMEOUT_S, 20.0)
        self.assertIsNot(
            live_radar._live_get, getattr(oddset_data, "_sofa_get", None))

    def test_tak_och_budget_ar_satta(self):
        self.assertGreater(live_radar.MAX_MATCHES, 0)
        self.assertLessEqual(live_radar.MAX_MATCHES, 30)
        self.assertLess(live_radar.BUDGET_S, 300)   # måste rymmas i en 5-min-tick

    def test_proxy_och_xg_har_skilda_faltnamn(self):
        import inspect
        src = inspect.getsource(live_radar.radar_signal)
        self.assertIn('"proxy_index"', src)   # enhetslöst index
        self.assertIn('"chance_gap"', src)    # xG i mål
