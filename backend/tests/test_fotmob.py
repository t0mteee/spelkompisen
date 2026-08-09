import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import fotmob, live_radar
from app.storage import Storage


# Förkortad kopia av ett verkligt matchDetails-svar (Degerfors–Djurgården,
# Allsvenskan, 2026-07-25 65'): FotMob upprepar samma nyckel i flera grupper och
# har rubrikrader med None-värden, vilket parsern måste tåla.
DETAILS = {
    "header": {"status": {"liveTime": {"short": "65‎’‎"}}},
    "content": {"stats": {"Periods": {"All": {"stats": [
        {"title": "Top stats", "stats": [
            {"key": "expected_goals", "title": "Expected goals (xG)",
             "stats": ["0.73", "1.45"]},
            {"key": "total_shots", "title": "Total shots", "stats": [8, 11]},
            {"key": "ShotsOnTarget", "title": "Shots on target", "stats": [0, 4]},
            {"key": "big_chance", "title": "Big chances", "stats": [1, 2]},
        ]},
        {"title": "Expected goals (xG)", "stats": [
            # rubrikrad utan värden — får ALDRIG skriva över den riktiga
            {"key": "expected_goals", "title": "Expected goals (xG)",
             "stats": [None, None]},
            {"key": "expected_goals_on_target", "title": "xG on target (xGOT)",
             "stats": ["0.00", "0.98"]},
            {"key": "expected_goals_open_play", "title": "xG open play",
             "stats": ["0.63", "1.45"]},
        ]},
        {"title": "Shots", "stats": [
            {"key": "shots_inside_box", "title": "Shots inside box",
             "stats": [4, 6]},
        ]},
    ]}}}},
}


class ParseTests(unittest.TestCase):
    def test_plockar_xg_och_skott_ur_all_perioden(self):
        stats = fotmob.parse_stats(DETAILS)
        self.assertEqual(0.73, stats["xg_home"])
        self.assertEqual(1.45, stats["xg_away"])
        self.assertEqual(0.98, stats["xgot_away"])
        self.assertEqual(0.63, stats["xg_open_home"])
        self.assertEqual(8, stats["shots_home"])
        self.assertEqual(4, stats["shots_on_away"])
        self.assertEqual(6, stats["shots_inside_away"])

    def test_rubrikrad_med_none_skriver_inte_over_riktigt_varde(self):
        """Första KOMPLETTA paret vinner; None får aldrig radera xG."""
        self.assertEqual(0.73, fotmob.parse_stats(DETAILS)["xg_home"])

    def test_tom_statistik_ger_tomt_resultat_inte_nollor(self):
        """Ingen statistik ⇒ ingen rad. Nollor hade sett ut som 0.00 xG."""
        self.assertEqual({}, fotmob.parse_stats({}))
        self.assertEqual({}, fotmob.parse_stats(
            {"content": {"stats": {"Periods": {"All": {"stats": []}}}}}))

    def test_matchminut_lases_ur_headern(self):
        self.assertEqual(65, fotmob.parse_minute(DETAILS))
        self.assertIsNone(fotmob.parse_minute({}))

    def test_stallning_lases_ur_samma_details_svar(self):
        payload = {**DETAILS, "header": {"status": {
            "liveTime": {"short": "65′"}, "scoreStr": "2 - 1"}}}
        self.assertEqual((2, 1), fotmob.parse_score(payload))
        self.assertEqual((None, None), fotmob.parse_score(DETAILS))

    def test_okant_resultatformat_gissar_aldrig_nollor(self):
        self.assertEqual((0, 1), fotmob._score_pair("0 - 1"))
        self.assertEqual((2, 0), fotmob._score_pair("2–0"))
        self.assertEqual((None, None), fotmob._score_pair(None))
        self.assertEqual((None, None), fotmob._score_pair("uppskjuten"))

    def test_ligamappningen_ar_explicit_aldrig_fuzzy(self):
        """Handbolls-läxan: ett liganamn kan bära en annan sport, så mappningen
        matchar på (land, exakt namn) — inte på likhet."""
        self.assertEqual("allsvenskan", fotmob.LEAGUE_NAMES[("SWE", "Allsvenskan")])
        self.assertNotIn(("DEN", "Allsvenskan"), fotmob.LEAGUE_NAMES)
        self.assertNotIn(("SWE", "Allsvenskan Handboll"), fotmob.LEAGUE_NAMES)

    def test_europacupernas_kval_och_huvudturnering_delar_liganyckel(self):
        """FotMob har SEPARATA ligor för kval och huvudturnering — båda ska
        landa på samma projektnyckel så radarserien överlever säsongsbytet."""
        for cup, key in (("Champions League", "champions_league"),
                         ("Europa League", "europa_league"),
                         ("Conference League", "conference_league")):
            self.assertEqual(key, fotmob.LEAGUE_NAMES[("INT", cup)])
            self.assertEqual(
                key, fotmob.LEAGUE_NAMES[("INT", f"{cup} Qualification")])

    def test_toppligor_och_besta_har_explicit_live_mapping(self):
        expected = {
            ("ENG", "Premier League"): "premier_league",
            ("ITA", "Serie A"): "serie_a",
            ("ESP", "LaLiga"): "la_liga",
            ("GER", "Bundesliga"): "bundesliga",
            ("ISL", "Besta deild karla"): "bestadeild",
            ("ISL", "Besta deildin"): "bestadeild",
            ("DEN", "Superligaen"): "danish_superliga",
            ("BEL", "Belgian Pro League"): "belgian_pro_league",
            ("POR", "Liga Portugal"): "primeira_liga",
            ("BOL", "Primera División"): "bolivian_primera",
        }
        for provider_name, league in expected.items():
            self.assertEqual(league, fotmob.LEAGUE_NAMES[provider_name])


class FriendlyScopeTests(unittest.TestCase):
    """Club Friendlies är global: samma Oddset-spärr som Sofascore-varvet,
    inkl. spegelvänd hemma/borta (primärkälle-beslutet 2026-07-28)."""

    KNOWN = [{"league": "friendlies",
              "home": "Western Sydney Wanderers", "away": "Chelsea",
              "start": "2026-07-28T09:45:00Z"}]

    def _match(self, home, away, league="friendlies",
               start="2026-07-28T09:45:00.000Z"):
        return {"league": league, "home": home, "away": away,
                "start_at": start, "minute_label": "27’"}

    def test_spegelvand_friendly_i_oddset_slapps_in(self):
        live = [self._match("Chelsea", "Western Sydney Wanderers")]
        self.assertEqual(live, fotmob._scope_friendlies(None, live, self.KNOWN))

    def test_fotmobs_kortnamn_matchar_oddsets_fulla_namn(self):
        """FotMob listar 'Western Sydney' — spärren jämför med `_same_team`
        (prefix ≥4), inte exakt likhet; annars föll turnématchen bort igen
        (uppmätt live 2026-07-28, Chelsea–WSW)."""
        live = [self._match("Chelsea", "Western Sydney")]
        self.assertEqual(live, fotmob._scope_friendlies(None, live, self.KNOWN))

    def test_okand_friendly_filtreras_fore_detaljanropet(self):
        live = [self._match("Trafford FC", "Bury FC")]
        self.assertEqual([], fotmob._scope_friendlies(None, live, self.KNOWN))

    def test_ligamatcher_gar_alltid_forbi_sparren(self):
        live = [self._match("Rosenborg", "Molde", league="eliteserien")]
        self.assertEqual(live, fotmob._scope_friendlies(None, live, []))

    def test_taket_klipper_friendlies_fore_riktiga_ligor(self):
        """Riktiga ligor sorteras först, mest kvarvarande speltid först."""
        friendly = self._match("Chelsea", "Western Sydney Wanderers")
        sen_liga = dict(self._match("AIK", "Häcken", league="allsvenskan"),
                        minute_label="80’")
        tidig_liga = self._match("Rosenborg", "Molde", league="eliteserien")
        ordning = sorted([friendly, sen_liga, tidig_liga], key=fotmob._rank)
        self.assertEqual([tidig_liga, sen_liga, friendly], ordning)


class ObservationTimeTests(unittest.TestCase):
    """🕐 Observationstidsregeln: hämtningstid − Age, per anrop."""

    class _Resp:
        def __init__(self, age):
            self.headers = {"age": age} if age is not None else {}

    def test_age_dras_av_fran_hamtningstiden(self):
        at = dt.datetime(2026, 7, 25, 14, 0, 0, tzinfo=dt.timezone.utc)
        self.assertEqual("2026-07-25T13:59:20Z",
                         fotmob._observed_at(self._Resp("40"), at))

    def test_saknad_eller_trasig_age_ger_hamtningstiden(self):
        at = dt.datetime(2026, 7, 25, 14, 0, 0, tzinfo=dt.timezone.utc)
        for header in (None, "", "trasig", "-5"):
            self.assertEqual("2026-07-25T14:00:00Z",
                             fotmob._observed_at(self._Resp(header), at))


class RosterValidationTests(unittest.TestCase):
    def test_malformed_200_never_empties_presence(self):
        """{} och leagues:null är transportfel, inte "inga matcher live"."""
        checked = dt.datetime(2026, 8, 1, 21, 10, tzinfo=dt.timezone.utc)
        for payload in ({}, {"leagues": None}):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                store = Storage(Path(tmp) / "test.db")
                try:
                    live_radar.record_presence(
                        store, live_radar.FOTMOB_PRESENCE_KEY, ["KEEP1"],
                        "2026-08-01T21:08:00Z")
                    response = Mock()
                    response.headers = {}
                    response.json.return_value = payload
                    response.raise_for_status = Mock()
                    with patch.object(fotmob.httpx.Client, "get",
                                      return_value=response), \
                            patch.object(fotmob, "_now", return_value=checked):
                        report = fotmob.collect(store, known_matches=[])

                    self.assertFalse(report["health_ok"])
                    self.assertIn("leagues-lista", report["error"])
                    presence = json.loads(store.meta_get(
                        live_radar.FOTMOB_PRESENCE_KEY))
                    self.assertEqual(["KEEP1"], presence["active_ids"])
                    self.assertNotIn("KEEP1", presence["ended_at"])
                    health = next(
                        row for row in store.oddset_source_health()
                        if row["source"] == "fotmob" and
                        row["scope"] == "live")
                    self.assertFalse(health["ok"])
                finally:
                    store.close()

    def test_explicit_empty_leagues_list_is_valid(self):
        response = Mock()
        response.headers = {}
        response.json.return_value = {"leagues": []}
        response.raise_for_status = Mock()
        with patch.object(fotmob.httpx.Client, "get", return_value=response):
            with fotmob.FotMob() as api:
                rows, _observed_at = api.matches()
        self.assertEqual([], rows)


class StorageTests(unittest.TestCase):
    def test_captures_ligger_i_egen_tabell_skild_fran_sofascore(self):
        """xG blandas ALDRIG mellan providers — separata tabeller är spärren."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                row = {"fotmob_id": 5107545, "captured_at": "2026-07-25T14:23:04Z",
                       "capture_version": fotmob.CAPTURE_VERSION,
                       "league": "allsvenskan", "tournament": "Allsvenskan",
                       "home": "Degerfors", "away": "Djurgården",
                       "minute": 65, "home_score": 0, "away_score": 1,
                       "xg_home": 0.73, "xg_away": 1.45}
                self.assertEqual(1, store.live_fotmob_save(row))
                self.assertEqual(0, store.live_fotmob_save(row))   # append-once
                got = store.live_fotmob_captures()
                self.assertEqual(1, len(got))
                self.assertEqual(0.73, got[0]["xg_home"])
                # Sofascore-tabellen är orörd
                self.assertEqual([], store.oddset_live_captures())
            finally:
                store.close()

    def test_collect_marks_transition_from_live_to_finished(self):
        """En lyckad FotMob-lista ska ta bort ett nyss avslutat kort snabbare
        än capture-TTL:n, men bara efter att eventet faktiskt setts live."""
        active = {
            "fotmob_id": 991001,
            "league": "allsvenskan",
            "tournament": "Allsvenskan",
            "home": "AIK",
            "away": "Häcken",
            "start_at": "2026-07-25T18:00:00Z",
            "started": True,
            "finished": False,
            "cancelled": False,
            "minute_label": "70’",
            "score": "1 - 0",
        }

        class FakeFotMob:
            def __init__(self, listing, observed):
                self.listing = listing
                self.observed = observed

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return None

            def matches(self, _date=None):
                return self.listing, self.observed

            def details(self, _fotmob_id):
                return DETAILS, "2026-07-25T19:10:01Z"

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with patch.object(
                        fotmob, "FotMob",
                        return_value=FakeFotMob(
                            [active], "2026-07-25T19:10:00Z")):
                    self.assertEqual(
                        1, fotmob.collect(store, known_matches=[])["live"])
                first = json.loads(store.meta_get(
                    "live_radar_fotmob_presence"))
                # id:t lagras som ogenomskinlig sträng sedan 2026-08-01
                # (Flashscores är alfanumeriskt)
                self.assertEqual(["991001"], first["active_ids"])
                self.assertEqual({}, first["ended_at"])

                finished = dict(active, finished=True)
                with patch.object(
                        fotmob, "FotMob",
                        return_value=FakeFotMob(
                            [finished], "2026-07-25T19:12:00Z")):
                    self.assertEqual(
                        0, fotmob.collect(store, known_matches=[])["live"])
                second = json.loads(store.meta_get(
                    "live_radar_fotmob_presence"))
                self.assertEqual([], second["active_ids"])
                self.assertEqual(
                    "2026-07-25T19:12:00Z",
                    second["ended_at"]["991001"])
                health = next(row for row in store.oddset_source_health()
                              if row["source"] == "fotmob" and
                              row["scope"] == "live")
                self.assertTrue(health["ok"])
                self.assertEqual(0, health["event_count"])
            finally:
                store.close()

    def test_collect_prefers_details_score_over_older_listing_score(self):
        active = {
            "fotmob_id": 991002, "league": "allsvenskan",
            "tournament": "Allsvenskan", "home": "AIK", "away": "Häcken",
            "start_at": "2026-07-25T18:00:00Z", "started": True,
            "finished": False, "cancelled": False, "minute_label": "65′",
            "score": "0 - 0",
        }
        details = {**DETAILS, "header": {"status": {
            "liveTime": {"short": "65′"}, "scoreStr": "1 - 0"}}}

        class FakeFotMob:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self, _date=None):
                return [active], "2026-07-25T19:10:00Z"
            def details(self, _fotmob_id):
                return details, "2026-07-25T19:10:01Z"

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with patch.object(fotmob, "FotMob", return_value=FakeFotMob()):
                    self.assertEqual(1, fotmob.collect(
                        store, known_matches=[])["saved"])
                row = store.live_fotmob_captures()[0]
                self.assertEqual((1, 0),
                                 (row["home_score"], row["away_score"]))
            finally:
                store.close()

    def test_partial_stats_failure_is_not_green_in_health_or_payload(self):
        now = dt.datetime(2026, 8, 1, 21, 10, tzinfo=dt.timezone.utc)
        start = (now - dt.timedelta(minutes=65)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")

        def match(match_id, home):
            return {
                "fotmob_id": match_id, "league": "allsvenskan",
                "tournament": "Allsvenskan", "home": home, "away": "Away",
                "start_at": start, "started": True, "finished": False,
                "cancelled": False, "minute_label": "65′", "score": "0 - 0",
            }

        details = {**DETAILS, "header": {"status": {
            "liveTime": {"short": "65′"}, "scoreStr": "0 - 0"}}}

        class PartialFotMob:
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self, _date=None):
                return ([match(991010, "OK"), match(991011, "FAIL")],
                        now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            def details(self, match_id):
                if match_id == 991011:
                    raise RuntimeError("stats unavailable")
                return details, now.strftime("%Y-%m-%dT%H:%M:%SZ")

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with patch.object(fotmob, "FotMob", return_value=PartialFotMob()), \
                        patch.object(fotmob, "_now", return_value=now):
                    report = fotmob.collect(store, known_matches=[])
                self.assertEqual(1, report["saved"])
                self.assertEqual(1, report["stats_ok"])
                self.assertFalse(report["health_ok"])
                health = next(
                    row for row in store.oddset_source_health()
                    if row["source"] == "fotmob" and row["scope"] == "live")
                self.assertFalse(health["ok"])
                self.assertEqual(2, health["event_count"])
                self.assertIn("FAIL: RuntimeError", health["error"])
                payload_health = next(
                    row for row in live_radar.payload(store, now=now)[
                        "source_health"]
                    if row["source"] == "fotmob")
                self.assertFalse(payload_health["ok"])
                self.assertIn("RuntimeError", payload_health["error"])
            finally:
                store.close()

    def test_collect_refreshes_listing_before_using_fallback_score(self):
        initial = {
            "fotmob_id": 991003, "league": "allsvenskan",
            "tournament": "Allsvenskan", "home": "AIK", "away": "Häcken",
            "start_at": "2026-07-25T18:00:00Z", "started": True,
            "finished": False, "cancelled": False, "minute_label": "65′",
            "score": "0 - 0",
        }
        refreshed = {**initial, "score": "1 - 0"}

        class FakeFotMob:
            def __init__(self): self.calls = 0
            def __enter__(self): return self
            def __exit__(self, *_exc): return None
            def matches(self, _date=None):
                self.calls += 1
                if self.calls == 1:
                    return [initial], "2026-07-25T19:10:00Z"
                return [refreshed], "2026-07-25T19:10:29Z"
            def details(self, _fotmob_id):
                # Ingen scoreStr: fallback är tillåten först efter att
                # rosterlistan förnyats till samma observationstid.
                return DETAILS, "2026-07-25T19:10:30Z"

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fake = FakeFotMob()
                with patch.object(fotmob, "FotMob", return_value=fake):
                    self.assertEqual(1, fotmob.collect(
                        store, known_matches=[])["saved"])
                self.assertEqual(2, fake.calls)
                row = store.live_fotmob_captures()[0]
                self.assertEqual((1, 0),
                                 (row["home_score"], row["away_score"]))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
