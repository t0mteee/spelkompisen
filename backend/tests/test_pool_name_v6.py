"""pool-name-v6: truppmarkörer ur Pinnacles LIGANAMN i poolmatcharen.

Pinnacle skriver U21- och damlag utan markör i lagnamnet; markören finns bara
i ligans namn. Raderna är Pinnacles egna (id, avspark, liga, odds) ur indexet
2026-09-24 18:06Z. Rader med id "syn-*" är syntetiska: samma lagnamn och
avspark som rätt rad men i en U21- eller damliga (den adversariala kontrollen).
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

from app import odds_provider as op, pinnacle, sharp_service
from app.pinnacle import Pinnacle
from app.storage import Storage


def row(id_, home, away, start, league, odds=(2.0, 3.4, 3.6)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


U21 = "UEFA - U21 Euro Championship Qualifiers"
WSL = "England - Women Super League"
ENGLAND_SPAIN = row("1636346499", "England", "Spain", "2026-09-26T18:45:00Z",
                    "UEFA - Nations League A", (3.0, 3.43, 2.45))
ENGLAND_SPAIN_U21 = {**ENGLAND_SPAIN, "id": "syn-u21", "league": U21,
                     "odds": {"1": 1.5, "X": 4.0, "2": 6.0}}
ENGLAND_SPAIN_W = {**ENGLAND_SPAIN, "id": "syn-dam", "league": "International - Friendlies Women",
                   "odds": {"1": 1.2, "X": 6.0, "2": 12.0}}
FINLAND_SPAIN_U21 = row("1636333034", "Finland", "Spain", "2026-09-25T15:30:00Z", U21,
                        (5.93, 4.47, 1.47))
CHELSEA_ARSENAL_W = row("1637151400", "Chelsea", "Arsenal", "2026-09-27T15:30:00Z", WSL,
                        (2.42, 3.42, 2.64))
CHELSEA_ARSENAL = {**CHELSEA_ARSENAL_W, "id": "syn-herr", "league": "England - Premier League",
                   "odds": {"1": 2.1, "X": 3.5, "2": 3.3}}
PACHUCA_SANTOS_W = row("1637110429", "Pachuca", "Santos Laguna", "2026-09-26T23:00:00Z",
                       "Mexico - Liga MX Women", (1.2, 6.86, 9.96))
SANTOS_PACHUCA = row("1637110372", "Santos Laguna", "Pachuca", "2026-09-27T03:05:00Z",
                     "Mexico - Liga MX", (3.01, 3.74, 2.22))
SVS_ENG_ESP = "2026-09-26T20:45:00+02:00"       # = 18:45Z
SVS_FIN_ESP = "2026-09-25T17:30:00+02:00"       # = 15:30Z
SVS_CHE_ARS = "2026-09-27T17:30:00+02:00"       # = 15:30Z
SVS_PAC_SAN = "2026-09-27T01:00:00+02:00"       # = 26/9 23:00Z


def v6(home, away, index, start, home_iso=None, away_iso=None, diag=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, diag,
                                league_squads=True)


def v5(home, away, index, start, home_iso=None, away_iso=None, diag=None):
    """Samma funktion utan ligamarkörer = v5-beteendet (Bomben, jämförelsen)."""
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, diag)


class LigamarkorTests(unittest.TestCase):
    def test_u_aldrar_ur_liganamnet(self):
        cases = {U21: ("u21",), "International - Friendlies U19": ("u19",),
                 "International - Friendlies U20": ("u20",), "Asian Games U23": ("u23",),
                 "Norway - U19 League": ("u19",), "Brazil - Paulista U20": ("u20",),
                 "England - Professional Development League U21": ("u21",),
                 "FIFA - U-17 World Cup": ("u17",), "Friendlies Under 21": ("u21",),
                 "Portugal - U23 Championship": ("u23",), "Some League U14": ()}
        for league, expected in cases.items():
            self.assertEqual(expected, op.league_squad(league), league)

    def test_damformer_ur_liganamnet(self):
        for league in (WSL, "USA - National Womens Soccer League", "Mexico - Liga MX Women",
                       "Asian Games - Women", "Iceland - Urvalsdeild Women",
                       "England - National League Cup Women", "Brazil - Brasileiro Women",
                       "Norway - Toppserien Women", "Israel - Premier League Women",
                       "Spain - Liga F", "Sweden - Damallsvenskan", "Sweden - Elitettan",
                       "Germany - Frauen Bundesliga", "France - Division 1 Féminine",
                       "Spain - Primera Division Femenina", "Mexico - Liga MX Femenil",
                       "Italy - Serie A Femminile", "International - Friendlies (W)",
                       "Australia - A-League Women", "Australia - W-League",
                       "Japan - WE League", "USA - NWSL", "England - WSL",
                       "UEFA - Women's Champions League", "Female Friendlies"):
            self.assertEqual(("women",), op.league_squad(league), league)

    def test_reserv_och_ungdom(self):
        self.assertEqual(("reserves",), op.league_squad("Argentina - Reserve League"))
        self.assertEqual(("reserves",), op.league_squad("Argentina - Liga Pro Reserves"))
        self.assertEqual(("reserves", "u20"), op.league_squad("El Salvador - Reserve League U20"))
        self.assertEqual(("youth",), op.league_squad("UEFA - Youth League"))
        self.assertEqual(("youth",), op.league_squad("Italy - Campionato Primavera 1"))
        # En U-ålder räcker; "Youth" läggs inte till bredvid den.
        self.assertEqual(("u20",), op.league_squad("Argentina - Youth League U20"))

    def test_seniorligor_far_inga_markorer(self):
        for league in ("England - Premier League", "England - League 2", "Germany - Bundesliga 2",
                       "UEFA - Nations League A", "International - Friendlies", "Mexico - Liga MX",
                       "Mexico - Liga de Expansión MX", "Sweden - Division 1 Norra",
                       "Spain - Segunda Federacion", "Argentina - Liga Pro", "Brazil - Serie A",
                       "UEFA - Champions League Group F", "Switzerland - 1. Liga Classic",
                       "Italy - Serie C Group A", "Panama - Liga Prom", "", None):
            self.assertEqual((), op.league_squad(league), league)
        # Medvetet utanför listan: vuxna klubbar (Junior Cup), Welsh Premier
        # League (WPL), OS-turneringen och Premier League 2 (inte belagt).
        for league in ("Scotland - Junior Cup", "Wales - WPL", "Olympic Games",
                       "England - Premier League 2"):
            self.assertEqual((), op.league_squad(league), league)

    def test_markoren_laggs_bara_till_nar_den_saknas(self):
        self.assertEqual("Sweden u21", op.with_league_squad("Sweden", ("u21",)))
        self.assertEqual("Sweden U21", op.with_league_squad("Sweden U21", ("u21",)))
        self.assertEqual("Chelsea women", op.with_league_squad("Chelsea", ("women",)))
        self.assertEqual("Chelsea", op.with_league_squad("Chelsea", ()))
        self.assertEqual("pool-name-v6", op.POOL_MATCH_VERSION)


class SoccerIndexLigaTests(unittest.TestCase):
    def test_indexet_behaller_ligans_namn(self):
        pin = Pinnacle.__new__(Pinnacle)
        pin.last_age_s = 0
        matchups = [{"id": 10, "parent": None, "type": "matchup", "startTime": "2026-09-25T18:30:00Z",
                     "league": {"id": 1, "name": U21, "ageLimit": 20},
                     "participants": [{"alignment": "home", "name": "England"},
                                      {"alignment": "away", "name": "Kazakhstan"}]},
                    {"id": 11, "parent": None, "type": "matchup", "startTime": "2026-09-25T18:45:00Z",
                     "participants": [{"alignment": "home", "name": "Home"},
                                      {"alignment": "away", "name": "Away"}]}]
        markets = [{"matchupId": mid, "period": 0, "type": "moneyline", "prices": [
            {"designation": "home", "price": 150}, {"designation": "draw", "price": 200},
            {"designation": "away", "price": 175}]} for mid in (10, 11)]
        pin._get = mock.Mock(side_effect=[matchups, markets])
        rows = pin.soccer_index()
        self.assertEqual([U21, None], [r["league"] for r in rows])
        self.assertEqual(("England", "Kazakhstan"), (rows[0]["home"], rows[0]["away"]))


class U21Tests(unittest.TestCase):
    def test_u21_rad_vid_samma_avspark_gor_inte_seniorlanken_tvetydig(self):
        index = [ENGLAND_SPAIN_U21, ENGLAND_SPAIN, ENGLAND_SPAIN_W]
        h = v6("England", "Spanien", index, SVS_ENG_ESP, "ENG", "ESP")
        self.assertEqual(("1636346499", "A", False), (h["id"], h["match_tier"], h["swapped"]))
        self.assertEqual(ENGLAND_SPAIN["odds"], h["odds"])
        self.assertEqual("pool-name-v6", h["match_version"])
        # v5 som jämförelse: tre rader med samma namn på nivå A ⇒ tvetydig, ingen länk.
        diag = {}
        self.assertIsNone(v5("England", "Spanien", index, SVS_ENG_ESP, "ENG", "ESP", diag))
        self.assertEqual("ambiguous", diag["reason"])

    def test_utan_seniorrad_lankas_aldrig_u21_eller_damraden(self):
        for index in ([ENGLAND_SPAIN_U21], [ENGLAND_SPAIN_W], [ENGLAND_SPAIN_U21, ENGLAND_SPAIN_W]):
            diag = {}
            self.assertIsNone(v6("England", "Spanien", index, SVS_ENG_ESP, "ENG", "ESP", diag))
            self.assertEqual(("name_mismatch", 0), (diag["reason"], diag["qualifying_candidates"]))
            self.assertIn(diag["cand_league"], (U21, ENGLAND_SPAIN_W["league"]))
        # v5 länkade den ensamma U21-raden: det är felet v6 stänger.
        self.assertEqual("syn-u21", v5("England", "Spanien", [ENGLAND_SPAIN_U21], SVS_ENG_ESP,
                                       "ENG", "ESP")["id"])

    def test_verklig_u21_rad_finland_spanien(self):
        # Pinnacles rad 1636333034 är U21-kvalet. Seniorlaget länkas aldrig dit.
        self.assertIsNone(v6("Finland", "Spanien", [FINLAND_SPAIN_U21], SVS_FIN_ESP, "FIN", "ESP"))
        self.assertEqual("1636333034", v5("Finland", "Spanien", [FINLAND_SPAIN_U21], SVS_FIN_ESP,
                                          "FIN", "ESP")["id"])
        # SvS-lag med samma markör (Sverige U21-formen) länkas på nivå A.
        h = v6("Finland U21", "Spanien U21", [FINLAND_SPAIN_U21], SVS_FIN_ESP, "FIN", "ESP")
        self.assertEqual(("1636333034", "A", False), (h["id"], h["match_tier"], h["swapped"]))
        h = v6("Spanien U21", "Finland U21", [FINLAND_SPAIN_U21], SVS_FIN_ESP, "ESP", "FIN")
        self.assertEqual(("1636333034", True), (h["id"], h["swapped"]))
        self.assertEqual({"1": 1.47, "X": 4.47, "2": 5.93}, h["odds"])
        # v5 kunde aldrig länka SvS U21-namn mot Pinnacles omärkta rad.
        self.assertIsNone(v5("Finland U21", "Spanien U21", [FINLAND_SPAIN_U21], SVS_FIN_ESP,
                             "FIN", "ESP"))

    def test_svs_u21_lankas_inte_till_seniorraden(self):
        self.assertIsNone(v6("England U21", "Spanien U21", [ENGLAND_SPAIN], SVS_ENG_ESP, "ENG", "ESP"))
        h = v6("England U21", "Spanien U21", [ENGLAND_SPAIN, ENGLAND_SPAIN_U21], SVS_ENG_ESP,
               "ENG", "ESP")
        self.assertEqual(("syn-u21", "A"), (h["id"], h["match_tier"]))


class DamTests(unittest.TestCase):
    def test_wsl_chelsea_arsenal(self):
        h = v6("Chelsea", "Arsenal", [CHELSEA_ARSENAL_W, CHELSEA_ARSENAL], SVS_CHE_ARS)
        self.assertEqual(("syn-herr", "A"), (h["id"], h["match_tier"]))
        self.assertIsNone(v6("Chelsea", "Arsenal", [CHELSEA_ARSENAL_W], SVS_CHE_ARS))
        self.assertEqual("1637151400", v5("Chelsea", "Arsenal", [CHELSEA_ARSENAL_W], SVS_CHE_ARS)["id"])
        # Speglat (Arsenal–Chelsea) hjälper inte heller.
        self.assertIsNone(v6("Arsenal", "Chelsea", [CHELSEA_ARSENAL_W], SVS_CHE_ARS))

    def test_liga_mx_women_pachuca_santos(self):
        self.assertIsNone(v6("Pachuca", "Santos Laguna", [PACHUCA_SANTOS_W, SANTOS_PACHUCA], SVS_PAC_SAN))
        self.assertEqual("1637110429",
                         v5("Pachuca", "Santos Laguna", [PACHUCA_SANTOS_W], SVS_PAC_SAN)["id"])

    def test_svs_dam_ar_fortfarande_ingen_truppmarkor(self):
        # SvS skriver "Kina Dam". Dam ≠ women i truppregeln (oförändrat från v5):
        # ingen länk, varken till dam- eller herrraden.
        self.assertIsNone(v6("Chelsea Dam", "Arsenal Dam", [CHELSEA_ARSENAL_W], SVS_CHE_ARS))
        self.assertIsNone(v6("Chelsea Dam", "Arsenal Dam", [CHELSEA_ARSENAL], SVS_CHE_ARS))


class OforandradeVagarTests(unittest.TestCase):
    def test_bomben_via_pinnacle_match_laser_inte_ligan(self):
        pin = Pinnacle.__new__(Pinnacle)
        for index in ([ENGLAND_SPAIN_U21], [ENGLAND_SPAIN, ENGLAND_SPAIN_U21], [CHELSEA_ARSENAL_W]):
            stripped = [{k: v for k, v in g.items() if k != "league"} for g in index]
            for home, away, hi, ai, start in (("England", "Spanien", "ENG", "ESP", SVS_ENG_ESP),
                                              ("Chelsea", "Arsenal", "ENG", "ENG", SVS_CHE_ARS)):
                self.assertEqual(v5(home, away, stripped, start, hi, ai),
                                 pin.match(home, away, hi, ai, index, match_start=start))

    def test_vagen_utan_svs_avspark_far_inga_ligamarkorer(self):
        for index in ([FINLAND_SPAIN_U21], [CHELSEA_ARSENAL_W]):
            for home, away in (("Finland", "Spain"), ("Chelsea", "Arsenal")):
                with_flag = v6(home, away, index, None)
                self.assertEqual(v5(home, away, index, None), with_flag)
        self.assertEqual("v4", v6("Chelsea", "Arsenal", [CHELSEA_ARSENAL_W], None)["match_tier"])

    def test_rader_utan_liga_beter_sig_som_i_v5(self):
        plain = [{k: v for k, v in g.items() if k != "league"}
                 for g in (ENGLAND_SPAIN, CHELSEA_ARSENAL_W, FINLAND_SPAIN_U21)]
        for home, away, hi, ai, start in (("England", "Spanien", "ENG", "ESP", SVS_ENG_ESP),
                                          ("Chelsea", "Arsenal", None, None, SVS_CHE_ARS),
                                          ("Finland", "Spanien", "FIN", "ESP", SVS_FIN_ESP)):
            self.assertEqual(v5(home, away, plain, start, hi, ai), v6(home, away, plain, start, hi, ai))


def _draw(home, away, home_iso, away_iso, start):
    return SimpleNamespace(draw_number=4972, matches=[SimpleNamespace(
        event_number=1, home=home, away=away, home_iso=home_iso, away_iso=away_iso,
        match_start=start)])


class SharpServiceTests(unittest.TestCase):
    """Poolmatcharen i sharp_service är den enda vägen med ligamarkörer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        self.index: list = []
        tests = self

        class FakePinnacle:
            last_age_s = 120
            last_retrieved_at = "2026-09-24T18:06:04Z"
            def __enter__(self): return self
            def __exit__(self, *exc): return False
            def soccer_index(self, include_without_odds=False):
                return tests.index
        self.patches = [patch.object(sharp_service, "Pinnacle", FakePinnacle),
                        patch.object(sharp_service, "Storage", lambda *a, **k: Storage(self.db))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def collect(self, index):
        self.index = index
        return sharp_service.collect_pinnacle(
            "stryktipset", draw=_draw("England", "Spanien", "ENG", "ESP", SVS_ENG_ESP),
            varv=sharp_service.VarvIndex())

    def test_u21_raden_ensam_ger_inget_odds_och_diagnostik(self):
        result = self.collect([ENGLAND_SPAIN_U21])
        self.assertEqual({1: "not_listed"}, result["status"])
        self.assertEqual({}, result["hits"])
        self.assertEqual(U21, result["diagnostics"][1]["cand_league"])
        store = Storage(self.db)
        try:   # diagnostiktabellen har oförändrade kolumner och tar emot raden
            self.assertEqual([("England", "Spain")], [tuple(r) for r in store.conn.execute(
                "SELECT cand_home, cand_away FROM pool_match_diagnostic").fetchall()])
        finally:
            store.close()

    def test_seniorraden_lankas_trots_u21_och_damrad(self):
        result = self.collect([ENGLAND_SPAIN_U21, ENGLAND_SPAIN_W, ENGLAND_SPAIN])
        self.assertEqual({1: "matched"}, result["status"])
        self.assertEqual("1636346499", result["hits"][1]["id"])
        self.assertEqual("England", result["hits"][1]["home"])     # Pinnacles råa namn


if __name__ == "__main__":
    unittest.main()
