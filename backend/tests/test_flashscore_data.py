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

    def _run(self, stats, day_rows=None):
        start = int((NOW - dt.timedelta(days=1)).timestamp())
        rows = day_rows if day_rows is not None else [{
            "flashscore_id": "FSX", "league": "allsvenskan",
            "home": "Hacken", "away": "Kalmar", "start_ts": start}]

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
        row = dict(self.store.conn.execute(
            "SELECT * FROM oddset_results").fetchone())
        self.assertEqual(1.9, row["xg_h"])
        self.assertEqual(0.7, row["xg_a"])
        self.assertIn("+fs", row["source"])
        self.assertEqual(2, row["hg"], "målen får aldrig röras")

    def test_never_overwrites_an_existing_sofascore_value(self):
        self._result(xg_h=1.11, xg_a=0.22, source="sofa")
        report = self._run({"xg_home": 9.9, "xg_away": 9.9})
        self.assertEqual(0, report["saknade"])
        row = dict(self.store.conn.execute(
            "SELECT * FROM oddset_results").fetchone())
        self.assertEqual(1.11, row["xg_h"])

    def test_source_without_xg_leaves_the_row_untouched(self):
        self._result()
        report = self._run({"shots_home": 12, "shots_away": 4})
        self.assertEqual(1, report["matchade"])
        self.assertEqual(0, report["fyllda"])
        row = dict(self.store.conn.execute(
            "SELECT * FROM oddset_results").fetchone())
        self.assertIsNone(row["xg_h"])

    def test_unmatched_match_is_never_guessed(self):
        self._result()
        report = self._run({"xg_home": 1.9, "xg_away": 0.7}, day_rows=[{
            "flashscore_id": "FSX", "league": "allsvenskan",
            "home": "Djurgarden", "away": "Malmo",
            "start_ts": int((NOW - dt.timedelta(days=1)).timestamp())}])
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
                    flashscore.Flashscore, "absences",
                    lambda _s, _m: (flashscore.parse_absences(payload), NOW)), \
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
        self.assertIn("Ryggskada", {p["reason"] for p in players})

    def test_empty_absence_list_writes_nothing(self):
        report = self._run(payload={"data": {"findEventById":
                                             {"eventParticipants": []}}})
        self.assertEqual(1, report["matchade"])
        self.assertEqual(0, report["med_franvaro"])

    def test_ui_meta_is_written_for_the_match(self):
        self._run()
        raw = self.store.meta_get("oddset_abs:pin:77")
        self.assertIsNotNone(raw)
        self.assertIn("Berisha", raw)


if __name__ == "__main__":
    unittest.main()
