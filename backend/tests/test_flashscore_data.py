"""Flashscore som modelldatakälla: frånvaro + xG-komplettering (2026-08-01).

Frånvarofixturen är ett formattroget utdrag ur det skarpa GraphQL-svaret för
Häcken–Kalmar (Sjdjc0cm), hämtat 2026-08-01.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import flashscore, flashscore_data
from app.oddset import norm_team
from app.storage import Storage

NOW = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc)

ABSENCE_PAYLOAD = {"data": {"findEventById": {"eventParticipants": [
    {"type": {"side": "HOME"}, "lineup": {"missingPlayers": [
        {"reason": "Ryggskada",
         "player": {"participantId": "UVnq6dH9", "name": "Berisha E."}},
        {"reason": "Gula kort",
         "player": {"participantId": "X2", "name": "Lindberg J."}},
    ]}},
    {"type": {"side": "AWAY"}, "lineup": {"missingPlayers": [
        {"reason": "Axelskada",
         "player": {"participantId": "X3", "name": "Ohman F."}},
    ]}},
]}}}


class ParseAbsenceTests(unittest.TestCase):
    def test_reads_side_name_and_reason(self):
        rows = flashscore.parse_absences(ABSENCE_PAYLOAD)
        self.assertEqual(3, len(rows))
        self.assertEqual(
            {("home", "Berisha E.", "Ryggskada"),
             ("home", "Lindberg J.", "Gula kort"),
             ("away", "Ohman F.", "Axelskada")},
            {(r["side"], r["name"], r["reason"]) for r in rows})

    def test_missing_lineup_yields_nothing_not_a_guess(self):
        self.assertEqual([], flashscore.parse_absences(
            {"data": {"findEventById": {"eventParticipants": [
                {"type": {"side": "HOME"}, "lineup": None}]}}}))
        self.assertEqual([], flashscore.parse_absences({}))

    def test_observation_distinguishes_valid_empty_from_unavailable(self):
        valid_empty = {"data": {"findEventById": {"eventParticipants": [
            {"type": {"side": "HOME"}, "lineup": {"missingPlayers": []}},
            {"type": {"side": "AWAY"}, "lineup": {"missingPlayers": []}},
        ]}}}
        self.assertEqual("observed", flashscore.parse_absence_observation(
            valid_empty)["status"])
        self.assertEqual([], flashscore.parse_absence_observation(
            valid_empty)["players"])
        self.assertEqual("unavailable", flashscore.parse_absence_observation(
            {"data": {"findEventById": {"eventParticipants": []}}})["status"])


class TeamMatchTests(unittest.TestCase):
    def test_prefix_rule_links_known_spellings(self):
        self.assertTrue(flashscore_data._same("Ostersund", "Östersunds FK"))
        self.assertTrue(flashscore_data._same("Hacken", "BK Häcken"))

    def test_short_or_unrelated_names_never_link(self):
        self.assertFalse(flashscore_data._same("AIK", "AFC"))
        self.assertFalse(flashscore_data._same("Inter", "Internacional"))

    def test_country_suffix_is_stripped_before_matching(self):
        # Flashscore märker träningsmatcher: 'Chelsea (Eng)'
        self.assertTrue(flashscore_data._same("Chelsea (Eng)", "Chelsea"))
        self.assertTrue(flashscore_data._same("Inter (Ita)", "Inter"))
        self.assertFalse(flashscore_data._same("Inter (Ita)", "Internacional"))

    def test_different_clubs_with_similar_names_never_link(self):
        # Hammarby TFF är en ANNAN klubb än Hammarby IF
        self.assertFalse(flashscore_data._same("Hammarby", "Hammarby TFF"))

    def test_ambiguous_candidates_are_never_linked(self):
        # två poster som normaliserar till samma lag = dubblett hos källan
        cands = [{"league": "allsvenskan", "home": "Hammarby IF",
                  "away": "AIK", "flashscore_id": "A"},
                 {"league": "allsvenskan", "home": "Hammarby",
                  "away": "AIK", "flashscore_id": "B"}]
        self.assertIsNone(flashscore_data._find(
            cands, "allsvenskan", "Hammarby", "AIK"))


class RefreshLiveResultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.start = NOW - dt.timedelta(hours=3)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _signal(self, **over):
        row = {
            "match_key": "pin:hacken", "provider": "flashscore",
            "provider_event_id": "vRkjOT13", "league": "allsvenskan",
            "home": "Hacken", "away": "Halmstad",
            "start_at": self.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "captured_at": (NOW - dt.timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"), "minute": 69,
        }
        row.update(over)
        return row

    def _finished(self, **over):
        row = {
            "flashscore_id": "vRkjOT13", "league": "allsvenskan",
            "home": "Hacken", "away": "Halmstad",
            "start_ts": int(self.start.timestamp()),
            "stage": "3", "home_score": 1, "away_score": 0,
        }
        row.update(over)
        return row

    def _run(self, signals=None, rows=None):
        signals = signals or [self._signal()]
        rows = rows if rows is not None else [self._finished()]

        def day(_self, offset, status):
            self.assertEqual(flashscore.STATUS_FINISHED, status)
            return (rows if offset == -1 else [], NOW)

        with patch.object(flashscore.Flashscore, "day", day):
            return flashscore_data.refresh_recent_results(
                self.store, signals, now=NOW, force=True)

    def test_saves_explicit_flashscore_finish_for_signal(self):
        report = self._run()

        self.assertEqual(1, report["matched"])
        self.assertEqual(1, report["saved"])
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual((1, 0), (row["hg"], row["ag"]))
        self.assertEqual("flashscore", row["source"])

    def test_flashscore_signal_requires_the_same_provider_id(self):
        report = self._run(rows=[self._finished(flashscore_id="OTHER")])

        self.assertEqual(0, report["matched"])
        self.assertEqual([], self.store.oddset_results("allsvenskan"))

    def test_extra_time_or_penalty_stage_waits_for_safer_facit(self):
        report = self._run(rows=[self._finished(stage="16")])

        self.assertEqual(0, report["matched"])
        self.assertEqual([], self.store.oddset_results("allsvenskan"))

    def test_reserve_provider_requires_unique_team_and_start_match(self):
        signal = self._signal(provider="fotmob", provider_event_id="123")
        rows = [self._finished(), self._finished(
            flashscore_id="LATE", start_ts=int(
                (self.start + dt.timedelta(hours=4)).timestamp()))]

        report = self._run(signals=[signal], rows=rows)

        self.assertEqual(1, report["matched"])
        self.assertEqual(1, report["saved"])

    def test_recent_filter_ignores_still_live_and_old_signals(self):
        signals = [
            self._signal(match_key="live", start_at=(
                NOW - dt.timedelta(minutes=95)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")),
            self._signal(match_key="old", start_at=(
                NOW - dt.timedelta(hours=37)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ")),
            self._signal(match_key="ready"),
        ]

        recent = flashscore_data._recent_signals(signals, NOW)

        self.assertEqual(["ready"], [row["match_key"] for row in recent])


class RefreshXgTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.date = (NOW - dt.timedelta(days=1)).date().isoformat()

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _result(self, **over):
        row = {"league": "allsvenskan", "date": self.date,
               "home": norm_team("BK Häcken"), "away": norm_team("Kalmar FF"),
               "home_raw": "BK Häcken", "away_raw": "Kalmar FF",
               "hg": 2, "ag": 1, "source": "fd"}
        row.update(over)
        self.store.oddset_save_result(row)
        self.store.oddset_upsert_match({
            "id": f"pin:{self.date}", "league": "allsvenskan",
            "home": "BK Häcken", "away": "Kalmar FF",
            "start": (NOW - dt.timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        })

    def _run(self, stats, day_rows=None):
        start = int((NOW - dt.timedelta(days=1)).timestamp())
        rows = day_rows if day_rows is not None else [{
            "flashscore_id": "FSX", "league": "allsvenskan",
            "home": "Hacken", "away": "Kalmar", "start_ts": start,
            "home_score": 2, "away_score": 1}]

        def day(_self, offset, _status):
            return (rows if offset == -1 else [], NOW)

        with patch.object(flashscore.Flashscore, "day", day), \
                patch.object(flashscore.Flashscore, "stats",
                             lambda _s, _m: (stats, NOW)), \
                patch.object(flashscore_data, "_now", return_value=NOW):
            return flashscore_data.refresh_xg(self.store, force=True)

    def test_fills_missing_xg(self):
        self._result()
        report = self._run({"xg_home": 1.9, "xg_away": 0.7,
                            "corners_home": 6, "corners_away": 3})
        self.assertEqual(1, report["fyllda"])
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(1.9, row["xg_h"])
        self.assertEqual(0.7, row["xg_a"])
        self.assertEqual("fd", row["source"])
        self.assertEqual("flashscore", row["stats_provider"])
        self.assertEqual(2, row["hg"], "målen får aldrig röras")

    def test_flashscore_and_sofascore_are_stored_separately(self):
        """Båda lagras — men Sofascore vinner urvalet sedan 2026-08-21.

        Flashscore läser bevisligen −0,19 xG per lag lägre än Sofascore och
        började samla först 2026-08-06, så den vann uteslutande på de nyaste
        matcherna och gav den tidsviktade fitten ett skalbyte mitt i serien.
        Raden ska fortfarande FINNAS (den är korskontrollen), bara inte väljas.
        """
        self._result(xg_h=1.11, xg_a=0.22, source="sofa")
        report = self._run({"xg_home": 9.9, "xg_away": 9.9})
        self.assertEqual(1, report["fyllda"])
        stats = self.store.oddset_result_stats("allsvenskan")
        self.assertEqual({"flashscore", "sofascore"},
                         {row["provider"] for row in stats})
        selected = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(1.11, selected["xg_h"])
        self.assertEqual("sofascore", selected["stats_provider"])

    def test_flashscore_fyller_nar_sofascore_saknar_matchen(self):
        """Fallbacken finns kvar: utan Sofascore-par vinner Flashscore."""
        self._result()
        self._run({"xg_home": 9.9, "xg_away": 8.8})
        selected = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(9.9, selected["xg_h"])
        self.assertEqual("flashscore", selected["stats_provider"])

    def test_xg_can_complete_a_corners_only_row_without_reusing_its_time(self):
        self._result()
        corners_at = (NOW - dt.timedelta(hours=2)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_result_stats({
            "league": "allsvenskan", "date": self.date,
            "home": norm_team("BK Häcken"), "away": norm_team("Kalmar FF"),
            "provider": "flashscore", "provider_event_id": "FSX",
            "observed_at": corners_at, "cor_h": 8, "cor_a": 1,
        })

        report = self._run({"xg_home": 1.9, "xg_away": 0.7})

        self.assertEqual(1, report["fyllda"])
        raw = self.store.oddset_result_stats(
            "allsvenskan", provider="flashscore")[0]
        self.assertEqual(corners_at, raw["corners_observed_at"])
        self.assertEqual("2026-08-01T12:00:00Z", raw["xg_observed_at"])
        selected = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(corners_at, selected["corners_observed_at"])
        self.assertEqual("2026-08-01T12:00:00Z", selected["xg_observed_at"])
        self.assertEqual((8, 1), (selected["cor_h"], selected["cor_a"]))

    def test_partial_pair_uses_the_time_when_the_pair_became_complete(self):
        self._result()
        base = {
            "league": "allsvenskan", "date": self.date,
            "home": norm_team("BK Häcken"), "away": norm_team("Kalmar FF"),
            "provider": "flashscore",
        }
        self.store.oddset_save_result_stats({
            **base, "xg_h": 1.9, "observed_at": "2026-08-01T10:00:00Z",
        })
        self.store.oddset_save_result_stats({
            **base, "xg_a": 0.7, "observed_at": "2026-08-01T11:00:00Z",
        })

        selected = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual((1.9, 0.7), (selected["xg_h"], selected["xg_a"]))
        self.assertEqual("2026-08-01T11:00:00Z", selected["xg_observed_at"])

    def test_source_without_xg_leaves_the_row_untouched(self):
        self._result()
        report = self._run({"shots_home": 12, "shots_away": 4})
        self.assertEqual(1, report["matchade"])
        self.assertEqual(0, report["fyllda"])
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertIsNone(row["xg_h"])

    def test_unmatched_match_is_never_guessed(self):
        self._result()
        report = self._run({"xg_home": 1.9, "xg_away": 0.7}, day_rows=[{
            "flashscore_id": "FSX", "league": "allsvenskan",
            "home": "Djurgarden", "away": "Malmo",
            "start_ts": int((NOW - dt.timedelta(days=1)).timestamp()),
            "home_score": 2, "away_score": 1}])
        self.assertEqual(0, report["matchade"])
        self.assertEqual(0, report["fyllda"])

    def test_same_teams_and_score_are_disambiguated_by_observed_start(self):
        self._result()
        reference = int((NOW - dt.timedelta(days=1)).timestamp())
        report = self._run({"xg_home": 1.9, "xg_away": 0.7}, day_rows=[
            {"flashscore_id": "RIGHT", "league": "allsvenskan",
             "home": "Hacken", "away": "Kalmar", "start_ts": reference,
             "home_score": 2, "away_score": 1},
            {"flashscore_id": "WRONG", "league": "allsvenskan",
             "home": "Hacken", "away": "Kalmar", "start_ts": reference + 5 * 3600,
             "home_score": 2, "away_score": 1},
        ])
        self.assertEqual(1, report["fyllda"])
        stat = self.store.oddset_result_stats("allsvenskan", provider="flashscore")[0]
        self.assertEqual("RIGHT", stat["provider_event_id"])

    def test_missing_reference_start_fails_closed(self):
        row = {"league": "allsvenskan", "date": self.date,
               "home": "hacken", "away": "kalmar", "home_raw": "BK Häcken",
               "away_raw": "Kalmar FF", "hg": 2, "ag": 1, "source": "fd"}
        self.store.oddset_save_result(row)
        report = self._run({"xg_home": 1.9, "xg_away": 0.7})
        self.assertEqual(0, report["matchade"])
        self.assertEqual(0, report["fyllda"])


class RefreshAbsenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")
        self.store.oddset_upsert_match({
            "id": "pin:77", "league": "allsvenskan",
            "home": "BK Häcken", "away": "Kalmar FF",
            "start": (NOW + dt.timedelta(hours=3)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "pinnacle_id": "77", "kambi_id": "78"})

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def _run(self, payload=ABSENCE_PAYLOAD):
        rows = [{"flashscore_id": "Sjdjc0cm", "league": "allsvenskan",
                 "home": "Hacken", "away": "Kalmar",
                 "start_ts": int((NOW + dt.timedelta(hours=3)).timestamp())}]
        with patch.object(flashscore.Flashscore, "day",
                          lambda _s, o, _st: (rows if o == 0 else [], NOW)), \
                patch.object(
                    flashscore.Flashscore, "absence_observation",
                    lambda _s, _m: (
                        flashscore.parse_absence_observation(payload), NOW)), \
                patch.object(flashscore_data, "_now", return_value=NOW):
            return flashscore_data.refresh_absences(self.store, force=True)

    def test_saves_pit_capture_with_flashscore_provenance(self):
        report = self._run()
        self.assertEqual(1, report["med_franvaro"])
        capture = dict(self.store.conn.execute(
            "SELECT * FROM oddset_absence_capture").fetchone())
        self.assertTrue(capture["source_event_id"].startswith("fs:"),
                        "proveniensen måste gå att skilja i efterhand")
        players = [dict(r) for r in self.store.conn.execute(
            "SELECT * FROM oddset_absence_player")]
        self.assertEqual(3, len(players))
        self.assertTrue(all(p["player_id"].startswith("fs:") for p in players))
        self.assertIn("Ryggskada", {p["reason"] for p in players})

    def test_valid_empty_absence_list_is_persisted(self):
        report = self._run(payload={"data": {"findEventById":
            {"eventParticipants": [
                {"type": {"side": "HOME"}, "lineup": {"missingPlayers": []}},
                {"type": {"side": "AWAY"}, "lineup": {"missingPlayers": []}},
            ]}}})
        self.assertEqual(1, report["matchade"])
        self.assertEqual(0, report["med_franvaro"])
        self.assertEqual(1, report["observerade"])
        capture = self.store.oddset_absence_history("pin:77")[0]
        self.assertEqual("observed", capture["status"])
        self.assertEqual(0, capture["missing_count"])

    def test_unavailable_is_persisted_but_not_selected_for_ui(self):
        report = self._run(payload={"data": {"findEventById":
                                             {"eventParticipants": []}}})
        self.assertEqual(1, report["unavailable"])
        self.assertEqual({}, self.store.oddset_latest_absences(["pin:77"]))

    def test_transport_error_is_not_recorded_as_unavailable(self):
        rows = [{"flashscore_id": "Sjdjc0cm", "league": "allsvenskan",
                 "home": "Hacken", "away": "Kalmar",
                 "start_ts": int((NOW + dt.timedelta(hours=3)).timestamp())}]
        with patch.object(flashscore.Flashscore, "day",
                          lambda _s, o, _st: (rows if o == 0 else [], NOW)), \
                patch.object(flashscore.Flashscore, "absence_observation",
                             side_effect=RuntimeError("network")), \
                patch.object(flashscore_data, "_now", return_value=NOW):
            report = flashscore_data.refresh_absences(self.store, force=True)
        self.assertEqual(0, report["unavailable"])
        self.assertEqual([], self.store.oddset_absence_history("pin:77"))

    def test_ui_meta_is_written_for_the_match(self):
        self._run()
        raw = self.store.meta_get("oddset_abs:pin:77")
        self.assertIsNotNone(raw)
        self.assertIn("Berisha", raw)


if __name__ == "__main__":
    unittest.main()


class SourcePriorityTests(unittest.TestCase):
    """Flashscore primär, Sofascore alternativ 3 — ordningen måste hålla
    även när den sämre källan skriver sist i samma varv."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_a_later_source_never_overwrites_a_stored_xg(self):
        base = {"league": "allsvenskan", "date": "2026-07-27",
                "home": norm_team("BK Häcken"), "away": norm_team("AIK"),
                "hg": 0, "ag": 0, "source": "fd"}
        self.store.oddset_save_result({**base, "xg_h": 1.99, "xg_a": 0.16})
        # Sofascore kör efteråt med ett annat värde
        self.store.oddset_save_result({**base, "xg_h": 9.9, "xg_a": 9.9})
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(1.99, row["xg_h"])
        self.assertEqual(0.16, row["xg_a"])

    def test_gaps_are_still_filled_by_a_later_source(self):
        base = {"league": "allsvenskan", "date": "2026-07-27",
                "home": norm_team("BK Häcken"), "away": norm_team("AIK"),
                "hg": 0, "ag": 0, "source": "fd"}
        self.store.oddset_save_result(base)
        self.store.oddset_save_result({**base, "xg_h": 1.5, "xg_a": 0.4})
        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual(1.5, row["xg_h"])

    def test_absence_sources_are_distinguishable_by_provenance(self):
        # olika captured_at: capture-lagret är append-once per (match, tid)
        for at, source_event_id in (("2026-08-01T10:00:00Z", "fs:ABC123"),
                                    ("2026-08-01T10:05:00Z", "998877")):
            self.store.oddset_save_absence_capture({
                "match_id": "pin:1", "captured_at": at,
                "source_event_id": source_event_id,
                "match_start": "2026-08-01T15:00:00Z",
                "confirmed": 0, "payload_hash": source_event_id,
            }, [])
        sources = self.store.oddset_absence_sources(
            ["pin:1"], "2026-08-01T00:00:00Z")
        self.assertEqual({"flashscore", "sofascore"}, sources["pin:1"])

    def test_old_flashscore_capture_does_not_block_a_fresh_sofascore_run(self):
        self.store.oddset_save_absence_capture({
            "match_id": "pin:1", "captured_at": "2026-07-20T10:00:00Z",
            "source_event_id": "fs:GAMMAL", "match_start": None,
            "confirmed": 0, "payload_hash": "x"}, [])
        sources = self.store.oddset_absence_sources(
            ["pin:1"], "2026-08-01T00:00:00Z")
        self.assertEqual({}, sources)

    def test_football_data_identity_wins_even_when_sofa_created_row_first(self):
        identity = {"league": "allsvenskan", "date": "2026-07-27",
                    "home": "hacken", "away": "aik"}
        self.store.oddset_save_result({
            **identity, "source": "sofa", "home_raw": "BK Häcken",
            "away_raw": "AIK Fotboll", "hg": 10, "ag": 9,
        })
        self.store.oddset_save_result({
            **identity, "source": "fd", "home_raw": "Hacken",
            "away_raw": "AIK", "hg": 1, "ag": 1,
        })
        self.store.oddset_save_result({**identity, "source": "sofa",
                                      "xg_h": 1.2, "xg_a": 0.4})

        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual("fd", row["source"])
        self.assertEqual("Hacken", row["home_raw"])
        self.assertEqual("AIK", row["away_raw"])
        self.assertEqual((1, 1), (row["hg"], row["ag"]))

    def test_xg_and_corners_keep_separate_pair_provenance(self):
        base = {"league": "allsvenskan", "date": "2026-07-27",
                "home": "hacken", "away": "aik", "hg": 0, "ag": 0,
                "source": "fd"}
        self.store.oddset_save_result({**base, "cor_h": 7, "cor_a": 3,
                                      "stats_provider": "football_data"})
        self.store.oddset_save_result_stats({
            "league": "allsvenskan", "date": "2026-07-27",
            "home": "hacken", "away": "aik", "provider": "flashscore",
            "xg_h": 1.8, "xg_a": 0.4,
        })

        row = self.store.oddset_results("allsvenskan")[0]
        self.assertEqual((1.8, 0.4, "flashscore"),
                         (row["xg_h"], row["xg_a"], row["xg_provider"]))
        self.assertEqual((7, 3, "football_data"),
                         (row["cor_h"], row["cor_a"], row["corners_provider"]))
