"""P2 (2026-07-28): utfalls-facit för värdeflaggor + resultat-ENDAST-ligor.

Close-EV äger grindarna; utfallet är validering. Dessa tester låser
(1) att resultat-ENDAST-vägen aldrig gör statistik-anrop och sparar
normaltid (straffar får inte räknas i cupfacit), och (2) att
resolve_outcomes settlar 1X2-flaggor via samma join som modellspåret.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset_data, oddset_value
from app.storage import Storage


class ResultsOnlyIngestTests(unittest.TestCase):
    def test_results_only_hoppar_statistikanropet_och_sparar_normaltid(self):
        event = {
            "id": 991,
            "status": {"type": "finished"},
            "startTimestamp": 1785340800,
            "homeTeam": {"name": "GNK Dinamo Zagreb"},
            "awayTeam": {"name": "FC Thun"},
            # cupkval: current inkluderar förlängning/straffar — normaltid
            # är facit för 1X2 (Montreal–Atlanta-läxan)
            "homeScore": {"normaltime": 2, "current": 3},
            "awayScore": {"normaltime": 2, "current": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                with mock.patch.object(
                        oddset_data, "_sofa_get",
                        side_effect=AssertionError("statistik ska inte hämtas")):
                    self.assertTrue(oddset_data._ingest_event(
                        store, "champions_league", event, results_only=True))
                rows = [dict(r) for r in
                        store.oddset_results("champions_league")]
                self.assertEqual(1, len(rows))
                self.assertEqual(2, rows[0]["hg"])
                self.assertEqual(2, rows[0]["ag"])
                self.assertEqual("dinamo zagreb", rows[0]["home"])
                self.assertTrue(store.meta_get("oddset_sofa_seen:991"))
            finally:
                store.close()

    def test_result_only_ligorna_ror_inte_sofa_ut(self):
        """RESULT_ONLY_UT är en EGEN tabell — SOFA_UT ingår i wp9c-/V2.2-
        fingeravtrycken och får inte ändras utanför en omfrysning."""
        for lg in oddset_data.RESULT_ONLY_UT:
            self.assertNotIn(lg, oddset_data.SOFA_UT)


class ResolveOutcomeTests(unittest.TestCase):
    def test_settlar_1x2_flaggor_mot_facit_och_lamnar_ovissa(self):
        now = dt.datetime.now(dt.timezone.utc)
        start = (now - dt.timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                store.oddset_upsert_match({
                    "id": "m1", "league": "champions_league",
                    "home": "Dinamo Zagreb", "away": "Thun", "start": start})
                store.oddset_upsert_match({
                    "id": "m2", "league": "champions_league",
                    "home": "Celje", "away": "Egnatia", "start": start})
                for mid, sign in (("m1", "1"), ("m1", "2"), ("m2", "1")):
                    store.conn.execute(
                        "INSERT INTO oddset_value_log (match_id, market, sign,"
                        " line_key, league, match_start, first_odds,"
                        " model_version) VALUES (?,?,?,?,?,?,?,?)",
                        (mid, "1x2", sign, -1, "champions_league", start,
                         2.10, "legacy"))
                store._commit()
                store.oddset_save_result({
                    "league": "champions_league", "date": start[:10],
                    "home": "dinamo zagreb", "away": "thun",
                    "hg": 2, "ag": 0, "source": "sofa"})

                n = oddset_value.resolve_outcomes(store)

                self.assertEqual(2, n)   # m2 saknar resultat och lämnas öppen
                rows = {(r[0], r[1]): (r[2], r[3]) for r in store.conn.execute(
                    "SELECT match_id, sign, outcome, outcome_key "
                    "FROM oddset_value_log")}
                self.assertEqual(1, rows[("m1", "1")][0])   # hemmaseger: rätt
                self.assertEqual(0, rows[("m1", "2")][0])   # borta: fel
                self.assertIsNotNone(rows[("m1", "1")][1])
                self.assertIsNone(rows[("m2", "1")][0])
            finally:
                store.close()

    def test_utfallsstatistiken_ar_display_och_tal_tomma_grupper(self):
        self.assertEqual(
            {"n_outcomes": 0, "result_roi": None, "hit_rate": None},
            oddset_value._outcome_stats([]))
        stats = oddset_value._outcome_stats([
            {"outcome": 1, "first_odds": 2.0},
            {"outcome": 0, "first_odds": 3.0},
            {"outcome": None, "first_odds": 2.0},   # osettlad räknas inte
        ])
        self.assertEqual(2, stats["n_outcomes"])
        self.assertEqual(0.0, stats["result_roi"])   # (1.0 + -1.0) / 2
        self.assertEqual(0.5, stats["hit_rate"])


if __name__ == "__main__":
    unittest.main()
