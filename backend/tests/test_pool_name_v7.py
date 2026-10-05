"""pool-name-v7: ligans dammarkör är veto för landslag och skiljeregel för klubbar.

Damernas Champions League 30/9 (Topptipset 4359) fanns i Pinnacles index med
exakt avspark men fick i v6 ingen länk: ligan gav kandidaten markören women,
SvS-namnet saknade den. Raderna nedan är Pinnacles egna lagnamn, avsparkar och
liganamn ur pool_match_diagnostic 2026-09-29 23:12Z (diagnostiken lagrar
inget id, så id:na är egna etiketter). Rader med id "syn-*" är syntetiska
herr-/damrader med samma lagnamn och avspark (den adversariala kontrollen).
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import odds_provider as op, pinnacle, sharp_service
from app.pinnacle import Pinnacle
from app.storage import Storage


def row(id_, home, away, start, league, odds=(2.0, 3.4, 3.6)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


WCL = "UEFA - Women's Champions League"
HACKEN_JUVENTUS_W = row("wcl-hacken", "Hacken", "Juventus", "2026-09-30T16:45:00Z", WCL,
                        (2.9, 3.5, 2.3))
HACKEN_JUVENTUS_M = {**HACKEN_JUVENTUS_W, "id": "syn-herr", "league": "UEFA - Champions League",
                     "odds": {"1": 4.0, "X": 3.8, "2": 1.8}}
LYON_CHELSEA_W = row("wcl-lyon", "Lyon", "Chelsea", "2026-09-30T19:00:00Z", WCL)
RANGERS_HAMMARBY_W = row("wcl-rangers", "Rangers", "Hammarby", "2026-09-30T18:00:00Z", WCL)
RANGERS_HAMMARBY_M = {**RANGERS_HAMMARBY_W, "id": "syn-herr", "league": "Scotland - Premiership"}
PARIS_ARSENAL_W = row("wcl-paris", "Paris FC", "Arsenal", "2026-09-30T16:45:00Z", WCL)
PARIS_ARSENAL_M = {**PARIS_ARSENAL_W, "id": "syn-herr", "league": "France - Ligue 1"}
WIGAN_BLACKPOOL_W = row("syn-dam", "Wigan", "Blackpool", "2026-09-22T18:00:00Z",
                        "England - Women National League")
WIGAN_BLACKPOOL_M = row("efl", "Wigan Athletic", "Blackpool", "2026-09-22T18:00:00Z",
                        "England - League One")
CHINA_JAPAN_W = row("syn-dam", "China", "Japan", "2026-09-30T11:00:00Z",
                    "International - Friendlies Women")
CHINA_JAPAN_M = {**CHINA_JAPAN_W, "id": "syn-herr", "league": "International - Friendlies"}
CZECHIA_SPAIN_W = row("syn-dam", "Czechia", "Spain", "2026-09-30T11:00:00Z",
                      "UEFA - Women's Euro Qualifiers")
SVS_HAC_JUV = "2026-09-30T18:45:00+02:00"      # = 16:45Z
SVS_LYO_CHE = "2026-09-30T21:00:00+02:00"      # = 19:00Z
SVS_RAN_HAM = "2026-09-30T20:00:00+02:00"      # = 18:00Z
SVS_WIG_BLA = "2026-09-22T20:00:00+02:00"      # = 18:00Z
SVS_CHN_JPN = "2026-09-30T13:00:00+02:00"      # = 11:00Z


def v7(home, away, index, start, home_iso=None, away_iso=None, diag=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, diag,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


class DamformerINamnetTests(unittest.TestCase):
    def test_svs_damformer_normaliseras_till_women(self):
        cases = {"Rangers LFC": "rangers women", "Arsenal WFC": "arsenal women",
                 "Heart of Midlothian WFC": "heart of midlothian women",
                 "Kina Dam": "kina women", "Ryssland Dam": "ryssland women",
                 "Apollon Limasoll dam": "apollon limasoll women",
                 "Apollon Ladies Limassol": "apollon limassol women",
                 "Chelsea Women": "chelsea women", "Bayern Frauen": "bayern women",
                 "Chelsea women": "chelsea women"}
        for name, expected in cases.items():
            self.assertEqual(expected, op._norm_team(name), name)
            self.assertEqual({"women"}, set(op._squad(op._norm_team(name))), name)

    def test_klubbnamn_utan_damform_ar_ororda(self):
        for name, expected in {"Amsterdam": "amsterdam", "Damac": "damac", "Rangers": "rangers",
                               "Notts County": "notts county", "Group F": "group f"}.items():
            self.assertEqual(expected, op._norm_team(name), name)
            self.assertEqual(set(), set(op._squad(op._norm_team(name))), name)

    def test_women_marked_galler_matchen(self):
        self.assertTrue(op.women_marked("Paris FC", "Arsenal WFC"))
        self.assertTrue(op.women_marked("Kina Dam", "Japan"))
        self.assertFalse(op.women_marked("Paris FC", "Arsenal"))
        self.assertFalse(op.women_marked("Häcken", "Juventus"))
        self.assertFalse(op.women_marked(None, ""))

    def test_versionen(self):
        self.assertEqual("pool-name-v7", op.POOL_MATCH_VERSION)


class DamklubbTests(unittest.TestCase):
    def test_damcupsrad_lankas_for_omarkt_klubbnamn(self):
        h = v7("Häcken", "Juventus", [HACKEN_JUVENTUS_W], SVS_HAC_JUV, "SWE", "ITA")
        self.assertEqual(("wcl-hacken", "A", False), ident(h))
        self.assertEqual(HACKEN_JUVENTUS_W["odds"], h["odds"])
        self.assertEqual(HACKEN_JUVENTUS_W["total"], h["total"])
        self.assertEqual("pool-name-v7", h["match_version"])
        self.assertEqual(("wcl-lyon", "A", False),
                         ident(v7("Lyon", "Chelsea", [LYON_CHELSEA_W], SVS_LYO_CHE, "FRA", "ENG")))
        # Speglad orientering följer med som för alla rader.
        h = v7("Juventus", "Häcken", [HACKEN_JUVENTUS_W], SVS_HAC_JUV, "ITA", "SWE")
        self.assertEqual(("wcl-hacken", "A", True), ident(h))
        self.assertEqual({"1": 2.3, "X": 3.5, "2": 2.9}, h["odds"])
        # Utan ligamarkörer (Bomben, v5-jämförelsen) länkades raden redan förut.
        self.assertEqual("wcl-hacken", pinnacle.match_index(
            "Häcken", "Juventus", "SWE", "ITA", [HACKEN_JUVENTUS_W], SVS_HAC_JUV)["id"])

    def test_herrrad_vinner_som_i_v6(self):
        for index in ([HACKEN_JUVENTUS_W, HACKEN_JUVENTUS_M], [HACKEN_JUVENTUS_M, HACKEN_JUVENTUS_W]):
            diag = {}
            h = v7("Häcken", "Juventus", index, SVS_HAC_JUV, "SWE", "ITA", diag)
            self.assertEqual(("syn-herr", "A", False), ident(h))
            self.assertEqual(HACKEN_JUVENTUS_M["odds"], h["odds"])
            self.assertEqual({}, diag)                 # ingen tvetydighet, inget avslag

    def test_herrrad_pa_lagre_niva_vinner_anda(self):
        # Beslut i v7: en damrad ur ligan konkurrerar aldrig när en herrrad
        # kvalificerar inom ankaret, oavsett nivå. Det är v6:s val bevarat.
        h = v7("Wigan", "Blackpool", [WIGAN_BLACKPOOL_W, WIGAN_BLACKPOOL_M], SVS_WIG_BLA, "ENG", "ENG")
        self.assertEqual(("efl", "B", False), ident(h))
        # Utan herrrad länkas damraden på nivå A.
        self.assertEqual(("syn-dam", "A", False),
                         ident(v7("Wigan", "Blackpool", [WIGAN_BLACKPOOL_W], SVS_WIG_BLA, "ENG", "ENG")))

    def test_tva_damrader_ar_tvetydiga(self):
        other = {**HACKEN_JUVENTUS_W, "id": "syn-dam2", "league": "International - Club Friendlies Women"}
        diag = {}
        self.assertIsNone(v7("Häcken", "Juventus", [HACKEN_JUVENTUS_W, other], SVS_HAC_JUV,
                             "SWE", "ITA", diag))
        self.assertEqual(("ambiguous", 2, "A"),
                         (diag["reason"], diag["qualifying_candidates"], diag["qualifying_tier"]))

    def test_u_alder_reserv_och_ungdom_ar_fortsatt_veto(self):
        for league in ("UEFA - Women's U19 Championship", "Sweden - U21 League",
                       "Sweden - Reserve League Women", "UEFA - Youth League"):
            diag = {}
            self.assertIsNone(v7("Häcken", "Juventus", [{**HACKEN_JUVENTUS_W, "league": league}],
                                 SVS_HAC_JUV, "SWE", "ITA", diag), league)
            self.assertEqual(("name_mismatch", 0), (diag["reason"], diag["qualifying_candidates"]))

    def test_svs_dammarkering_lankar_bara_damrad(self):
        self.assertEqual(("wcl-rangers", "A", False),
                         ident(v7("Rangers LFC", "Hammarby", [RANGERS_HAMMARBY_W], SVS_RAN_HAM, "SCO", "SWE")))
        diag = {}
        self.assertIsNone(v7("Rangers LFC", "Hammarby", [RANGERS_HAMMARBY_M], SVS_RAN_HAM, "SCO", "SWE", diag))
        self.assertEqual(("name_mismatch", 0), (diag["reason"], diag["qualifying_candidates"]))
        # Herrraden gör inte damlänken tvetydig.
        self.assertEqual(("wcl-rangers", "A", False),
                         ident(v7("Rangers LFC", "Hammarby", [RANGERS_HAMMARBY_M, RANGERS_HAMMARBY_W],
                                  SVS_RAN_HAM, "SCO", "SWE")))
        # SvS märker ofta bara ena laget: markören gäller matchen.
        self.assertEqual(("wcl-paris", "A", False),
                         ident(v7("Paris FC", "Arsenal WFC", [PARIS_ARSENAL_W, PARIS_ARSENAL_M],
                                  SVS_HAC_JUV, "FRA", "ENG")))
        self.assertIsNone(v7("Paris FC", "Arsenal WFC", [PARIS_ARSENAL_M], SVS_HAC_JUV, "FRA", "ENG"))
        # Speglad SvS-ordning.
        self.assertEqual(("wcl-rangers", "A", True),
                         ident(v7("Hammarby", "Rangers LFC", [RANGERS_HAMMARBY_W], SVS_RAN_HAM, "SWE", "SCO")))


class DamlandslagTests(unittest.TestCase):
    def test_omarkt_landslag_lankas_aldrig_till_damrad(self):
        # SvS skriver "Kina Dam": ett omärkt landslag är herrlandslaget (v6:s veto kvar).
        diag = {}
        self.assertIsNone(v7("Kina", "Japan", [CHINA_JAPAN_W], SVS_CHN_JPN, "CHN", "JPN", diag))
        self.assertEqual(("name_mismatch", 0), (diag["reason"], diag["qualifying_candidates"]))
        self.assertEqual(("syn-herr", "A", False),
                         ident(v7("Kina", "Japan", [CHINA_JAPAN_W, CHINA_JAPAN_M], SVS_CHN_JPN, "CHN", "JPN")))

    def test_dam_i_svs_namnet_lankar_damraden(self):
        self.assertEqual(("syn-dam", "A", False),
                         ident(v7("Kina Dam", "Japan Dam", [CHINA_JAPAN_W], SVS_CHN_JPN, "CHN", "JPN")))
        self.assertIsNone(v7("Kina Dam", "Japan Dam", [CHINA_JAPAN_M], SVS_CHN_JPN, "CHN", "JPN"))
        self.assertEqual(("syn-dam", "A", False),
                         ident(v7("Kina Dam", "Japan Dam", [CHINA_JAPAN_M, CHINA_JAPAN_W], SVS_CHN_JPN,
                                  "CHN", "JPN")))
        # Ensidig markering (Topptipset 1266: "Tjeckien Dam – Spanien") gäller matchen.
        self.assertEqual(("syn-dam", "A", False),
                         ident(v7("Tjeckien Dam", "Spanien", [CZECHIA_SPAIN_W], SVS_CHN_JPN, "CZE", "ESP")))
        self.assertEqual(("syn-dam", "A", True),
                         ident(v7("Spanien", "Tjeckien Dam", [CZECHIA_SPAIN_W], SVS_CHN_JPN, "ESP", "CZE")))


class AliasTests(unittest.TestCase):
    def test_sporting_jax(self):
        usl = row("usl", "Miami FC", "Sporting Club Jacksonville", "2026-09-30T23:00:00Z",
                  "USA - USL Championship")
        self.assertEqual(("usl", "A", False),
                         ident(v7("Miami FC", "Sporting Jax", [usl], "2026-10-01T01:00:00+02:00", "USA", "USA")))

    def test_junior_ar_junior_de_barranquilla_men_inte_juniors(self):
        col = row("col", "Atletico Nacional", "Junior de Barranquilla", "2026-10-01T01:00:00Z",
                  "Colombia - Primera A")
        self.assertEqual(("col", "A", False),
                         ident(v7("Atlético Nacional", "Junior", [col], "2026-10-01T03:00:00+02:00", "COL", "COL")))
        lib = row("lib", "Junior de Barranquilla", "River Plate", "2026-10-01T01:00:00Z",
                  "CONMEBOL - Libertadores")
        self.assertIsNone(v7("Boca Juniors", "River Plate", [lib], "2026-10-01T03:00:00+02:00", "ARG", "ARG"))

    def test_estudiantes_bara_i_belagd_kontext(self):
        arg = row("arg", "Platense", "Estudiantes de La Plata", "2026-10-02T00:15:00Z",
                  "Argentina - Primera Division")
        self.assertEqual(("arg", "A", False),
                         ident(v7("Platense", "Estudiantes", [arg], "2026-10-02T02:15:00+02:00", "ARG", "ARG")))
        # Ett generellt Estudiantes-alias finns fortfarande inte (Rio Cuarto, Caseros).
        other = row("lib", "Corinthians", "Estudiantes de La Plata", "2026-10-02T00:15:00Z",
                    "CONMEBOL - Libertadores")
        self.assertIsNone(v7("Corinthians", "Estudiantes", [other], "2026-10-02T02:15:00+02:00", "BRA", "ARG"))


    def test_topptipset_4369_argentina_och_colombia(self):
        # Pinnacles egna namn, avsparkar och id:n ur indexet 2026-10-05.
        est = row("1637175501", "Estudiantes de La Plata", "Gimnasia Mendoza",
                  "2026-10-05T22:00:00Z", "Argentina - Liga Pro")
        ban = row("1637175522", "Banfield", "Rosario Central", "2026-10-06T00:15:00Z",
                  "Argentina - Liga Pro")
        med = row("1637185133", "Independiente Medellin", "Independiente Santa Fe",
                  "2026-10-06T00:00:00Z", "Colombia - Primera A")
        index = [est, ban, med]
        self.assertEqual(("1637175501", "A", False), ident(v7(
            "Estudiantes", "Gimnasia y Esgrima Mendoza", index, "2026-10-06T00:00:00+02:00",
            "ARG", "ARG")))
        self.assertEqual(("1637175522", "A", False), ident(v7(
            "Banfield", "Rosario", index, "2026-10-06T02:15:00+02:00", "ARG", "ARG")))
        self.assertEqual(("1637185133", "A", False), ident(v7(
            "Independiente Medellin", "Santa Fe", index, "2026-10-06T02:00:00+02:00",
            "COL", "COL")))

    def test_rosario_och_santa_fe_bara_mot_belagd_motstandare(self):
        leones = row("syn-leones", "Banfield", "Leones de Rosario", "2026-10-06T00:15:00Z",
                     "Argentina - Liga Pro")
        self.assertIsNone(v7("Banfield", "Rosario", [leones], "2026-10-06T02:15:00+02:00",
                             "ARG", "ARG"))
        union = row("syn-union", "Union de Santa Fe", "Defensa y Justicia",
                    "2026-10-10T00:45:00Z", "Argentina - Liga Pro")
        self.assertIsNone(v7("Santa Fe", "Defensa y Justicia", [union],
                             "2026-10-10T02:45:00+02:00", "ARG", "ARG"))
        central = row("syn-central", "Rosario Central", "Racing Club", "2026-10-06T00:15:00Z",
                      "Argentina - Liga Pro")
        self.assertIsNone(v7("Rosario", "Racing Club", [central], "2026-10-06T02:15:00+02:00",
                             "ARG", "ARG"))


class OforandradeVagarTests(unittest.TestCase):
    def test_bomben_far_inga_ligamarkorer_men_svs_damform_galler(self):
        pin = Pinnacle.__new__(Pinnacle)
        # Märkt SvS-lag länkas aldrig till en omärkt rad, oavsett liga (ingen läses här).
        for index in ([RANGERS_HAMMARBY_M], [RANGERS_HAMMARBY_W]):
            self.assertIsNone(pin.match("Rangers LFC", "Hammarby", "SCO", "SWE", index,
                                        match_start=SVS_RAN_HAM))
        # Omärkt klubbnamn mot omärkt rad: v5-beteendet, som förut.
        self.assertEqual("wcl-hacken", pin.match("Häcken", "Juventus", "SWE", "ITA",
                                                 [HACKEN_JUVENTUS_W], match_start=SVS_HAC_JUV)["id"])

    def test_vagen_utan_svs_avspark_ar_v4(self):
        self.assertIsNone(v7("Rangers LFC", "Hammarby", [RANGERS_HAMMARBY_W], None, "SCO", "SWE"))
        self.assertEqual("v4", v7("Häcken", "Juventus", [HACKEN_JUVENTUS_W], None, "SWE", "ITA")["match_tier"])


def _draw(home, away, home_iso, away_iso, start):
    return SimpleNamespace(draw_number=4359, matches=[SimpleNamespace(
        event_number=1, home=home, away=away, home_iso=home_iso, away_iso=away_iso,
        match_start=start)])


class SharpServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        self.index: list = []
        tests = self

        class FakePinnacle:
            last_age_s = 120
            last_retrieved_at = "2026-09-29T23:12:13Z"
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
            "topptipset", draw=_draw("Häcken", "Juventus", "SWE", "ITA", SVS_HAC_JUV),
            varv=sharp_service.VarvIndex())

    def test_damcupsraden_ger_odds_i_poolmatcharen(self):
        result = self.collect([HACKEN_JUVENTUS_W])
        self.assertEqual({1: "matched"}, result["status"])
        self.assertEqual(("wcl-hacken", "Hacken", "pool-name-v7"),
                         (result["hits"][1]["id"], result["hits"][1]["home"],
                          result["hits"][1]["match_version"]))

    def test_herrraden_vinner_i_poolmatcharen(self):
        result = self.collect([HACKEN_JUVENTUS_W, HACKEN_JUVENTUS_M])
        self.assertEqual({1: "matched"}, result["status"])
        self.assertEqual("syn-herr", result["hits"][1]["id"])


if __name__ == "__main__":
    unittest.main()
