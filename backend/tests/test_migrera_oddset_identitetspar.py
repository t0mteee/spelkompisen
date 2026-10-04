import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.storage import Storage
from scripts import migrera_oddset_identitetspar as migration

NOW = dt.datetime(2026, 10, 3, 12, 0, tzinfo=dt.timezone.utc)


def _at(days: float = 0, hours: float = 0) -> str:
    return (NOW + dt.timedelta(days=days, hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class OddsetIdentityPairMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"

    def tearDown(self):
        self.tmp.cleanup()

    def _pair(self, store: Storage, pin: str, svs: str, league: str,
              pin_names: tuple[str, str], svs_names: tuple[str, str],
              start: str) -> None:
        store.oddset_upsert_match({
            "id": f"pin:{pin}", "league": league, "home": pin_names[0],
            "away": pin_names[1], "start": start, "pinnacle_id": pin,
            "status": "pending"})
        store.oddset_upsert_match({
            "id": f"svs:{svs}", "league": league, "home": svs_names[0],
            "away": svs_names[1], "start": start, "kambi_id": svs})

    def _seed(self, *, clash: bool = False) -> None:
        store = Storage(self.db)
        try:
            # A: exakt lika namn. Pinnacle-raden har sharp, SvS-raden SvS och
            # Expekt samt en amber-modellflagga som ska ligga kvar.
            self._pair(store, "1", "2", "champions_league",
                       ("Arsenal", "Lille"), ("Arsenal", "Lille"), _at(10))
            store.oddset_save_odds("pin:1", "pinnacle",
                                   {"1": 1.50, "X": 4.40, "2": 6.50}, _at(-20))
            store.oddset_save_odds("svs:2", "svenskaspel",
                                   {"1": 1.45, "X": 4.30, "2": 6.25}, _at(-19))
            store.oddset_save_odds("svs:2", "expekt",
                                   {"1": 1.45, "X": 4.30, "2": 6.25}, _at(-19))
            store.oddset_log_flag({
                "match_id": "svs:2", "market": "m1x2", "sign": "2",
                "line": None, "league": "champions_league",
                "description": "Arsenal – Lille", "match_start": _at(10),
                "at": _at(-1), "odds": 6.25, "fair": 0.18, "edge": 0.125,
                "book": "svenskaspel", "tier": "model",
                "model_version": "m-test", "git_hash": "test"})
            # B: ena laget strikt lika, andra en översättning.
            self._pair(store, "3", "4", "europa_league",
                       ("Midtjylland", "FC Copenhagen"),
                       ("FC Midtjylland", "FC Köpenhamn"), _at(12))
            # C: för nära avspark — Flashscore-frånvaron kan ha frusits.
            self._pair(store, "5", "6", "premier_league",
                       ("Fulham", "Everton"), ("Fulham", "Everton"), _at(1))
            # D: frånvarocapture redan skriven på SvS-raden.
            self._pair(store, "7", "8", "premier_league",
                       ("Chelsea", "Brentford"), ("Chelsea", "Brentford"),
                       _at(9))
            store.conn.execute(
                "INSERT INTO oddset_absence_capture(match_id,captured_at,provider,"
                "status,source_event_id,match_start,confirmed,payload_hash,"
                "home_missing,away_missing,missing_count) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("svs:8", _at(-1), "test", "observed", "event", _at(9), 1,
                 "hash", 0, 0, 0))
            # E: tvetydig — två Pinnacle-rader passar samma SvS-rad.
            self._pair(store, "9", "10", "la_liga", ("Getafe", "Elche"),
                       ("Getafe", "Elche"), _at(11))
            store.oddset_upsert_match({
                "id": "pin:11", "league": "la_liga", "home": "Getafe CF",
                "away": "Elche", "start": _at(11), "pinnacle_id": "11"})
            # F: truppmarkör skiljer — aldrig samma match.
            self._pair(store, "12", "13", "serie_a", ("Inter", "Parma"),
                       ("Inter U23", "Parma"), _at(10))
            if clash:
                # Samma källa, marknad, tecken och tid men olika pris på båda
                # raderna: efter flytten vore det en identitetskrock.
                store.oddset_save_odds("pin:1", "expekt",
                                       {"1": 1.40, "X": 4.30, "2": 6.25},
                                       _at(-19))
            store.conn.commit()
        finally:
            store.close()

    def _plan(self) -> dict:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return migration.plan_pairs(conn, NOW)
        finally:
            conn.close()

    def _rows(self) -> dict[str, dict]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            return {row["id"]: dict(row) for row in conn.execute(
                "SELECT * FROM oddset_matches")}
        finally:
            conn.close()

    def _scalar(self, sql: str, *args) -> int:
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(sql, args).fetchone()[0]
        finally:
            conn.close()

    def test_plan_tar_bara_entydiga_kommande_par_utan_referenser(self):
        self._seed()

        plan = self._plan()

        self.assertEqual(
            [("pin:1", "svs:2", "exakt"), ("pin:3", "svs:4", "ena laget")],
            [(p["pin"], p["svs"], p["rule"]) for p in plan["pairs"]])
        reasons = {(p["pin"], p["svs"]): p["reason"] for p in plan["skipped"]}
        self.assertEqual("utanför tidsgränserna", reasons[("pin:5", "svs:6")])
        self.assertEqual("referenser", reasons[("pin:7", "svs:8")])
        self.assertEqual("tvetydig", reasons[("pin:9", "svs:10")])
        self.assertEqual("tvetydig", reasons[("pin:11", "svs:10")])
        self.assertNotIn(("pin:12", "svs:13"), reasons)
        self.assertEqual({"oddset_value_log": 1}, plan["pairs"][0]["left"])

    def test_slar_ihop_godkanda_par_utan_att_rora_priser(self):
        self._seed()
        odds_before = self._scalar("SELECT COUNT(*) FROM oddset_odds")

        result = migration.migrate(self.db, self._plan()["pairs"], NOW)

        self.assertEqual(2, result["merged"])
        self.assertEqual("ok", result["integrity"])
        self.assertEqual(1, result["value_log_left"])
        self.assertEqual(odds_before,
                         self._scalar("SELECT COUNT(*) FROM oddset_odds"))
        rows = self._rows()
        self.assertNotIn("svs:2", rows)
        self.assertNotIn("svs:4", rows)
        self.assertEqual(("1", "2", "Arsenal", "Lille"), (
            rows["pin:1"]["pinnacle_id"], rows["pin:1"]["kambi_id"],
            rows["pin:1"]["home"], rows["pin:1"]["away"]))
        self.assertEqual(("FC Midtjylland", "FC Köpenhamn", "4"), (
            rows["pin:3"]["home"], rows["pin:3"]["away"],
            rows["pin:3"]["kambi_id"]))
        self.assertEqual(3, self._scalar(
            "SELECT COUNT(DISTINCT source) FROM oddset_odds "
            "WHERE match_id='pin:1'"))
        # Amber-flaggan ligger kvar på sitt gamla id och stängs aldrig.
        self.assertEqual(1, self._scalar(
            "SELECT COUNT(*) FROM oddset_value_log WHERE match_id='svs:2'"))
        # Det som hoppades över är orört.
        for mid in ("svs:6", "svs:8", "svs:10", "svs:13"):
            self.assertIn(mid, rows)

        # Engångsskriptet är säkert att köra om.
        self.assertEqual(0, migration.migrate(
            self.db, [{"pin": "pin:1", "svs": "svs:2"}], NOW)["merged"])

    def test_kor_aldrig_mer_an_den_granskade_planen(self):
        self._seed()

        result = migration.migrate(
            self.db, [{"pin": "pin:1", "svs": "svs:2"},
                      {"pin": "pin:7", "svs": "svs:8"}], NOW)

        self.assertEqual([("pin:1", "svs:2")], result["pairs"])
        self.assertEqual([("pin:7", "svs:8")], result["not_merged_now"])
        rows = self._rows()
        self.assertIn("svs:4", rows)
        self.assertIsNone(rows["pin:3"]["kambi_id"])

    def test_samtidiga_prisvarianter_rullar_tillbaka_allt(self):
        self._seed(clash=True)
        odds_before = self._scalar("SELECT COUNT(*) FROM oddset_odds")

        with self.assertRaisesRegex(RuntimeError, "samtidiga prisvarianter"):
            migration.migrate(self.db, self._plan()["pairs"], NOW)

        rows = self._rows()
        self.assertIn("svs:2", rows)
        self.assertIn("svs:4", rows)
        self.assertIsNone(rows["pin:1"]["kambi_id"])
        self.assertEqual(odds_before,
                         self._scalar("SELECT COUNT(*) FROM oddset_odds"))
        self.assertEqual(0, self._scalar(
            "SELECT COUNT(*) FROM oddset_odds WHERE match_id='pin:1' "
            "AND source='svenskaspel'"))

    def test_namnregeln(self):
        rule = migration.link_rule
        base = {"league": "premier_league"}
        self.assertEqual("ordmängd", rule(
            {**base, "home": "Arsenal", "away": "Leeds United"},
            {**base, "home": "Arsenal", "away": "Leeds"}))
        self.assertEqual("ena laget", rule(
            {**base, "home": "Augsburg", "away": "Bayern Munich"},
            {**base, "home": "FC Augsburg", "away": "Bayern München"}))
        # PSG kopplas sedan källkopplingens alias 2026-10-04
        # (oddset.ODDS_LINK_ALIASES); namnen är fortfarande inte ordlika.
        self.assertEqual("ena laget", rule(
            {**base, "home": "Manchester City", "away": "Paris Saint-Germain"},
            {**base, "home": "Manchester City", "away": "PSG"}))
        self.assertIsNone(rule(
            {**base, "home": "Manchester City", "away": "Chelsea"},
            {**base, "home": "Manchester City", "away": "Brentford"}))
        landslag = {"league": "nations_league"}
        self.assertEqual("landskod", rule(
            {**landslag, "home": "Ireland", "away": "Northern Ireland"},
            {**landslag, "home": "Irland", "away": "Nordirland"}))
        self.assertIsNone(rule(
            {**landslag, "home": "Northern Ireland", "away": "Ireland"},
            {**landslag, "home": "Irland", "away": "Nordirland"}))


if __name__ == "__main__":
    unittest.main()
