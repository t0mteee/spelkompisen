"""pool-name-v8: ensidig nivå D, dammarkören som skiljeregel för landslag och
aliaset Århus → AGF.

Beslut koordinatorn-2026-10-13-pool-namnmatchning och drift-2026-10-12-pool-
agf-alias (Saman, val 0). Raderna nedan är Pinnacles egna lagnamn, avsparkar
och liganamn ur indexet 2026-10-13 ~20:10Z och pool_match_diagnostic; SvS-
namnen och isoCode ur draw-API:t för Topptipset 4380/4382/4383. Id:n är egna
etiketter utom AGF (1637171526).
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league, odds=(2.0, 3.4, 3.6)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


def v8(home, away, index, start, home_iso=None, away_iso=None, diag=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, diag,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


CL = "UEFA - Champions League"
INTER = row("inter", "Internazionale", "Club Brugge", "2026-10-13T19:00:00Z", CL)
PSV = row("psv", "RB Leipzig", "PSV", "2026-10-13T19:00:00Z", CL)
BUCA = row("buca", "Atletico Bucaramanga", "Aguilas Doradas", "2026-10-13T23:30:00Z",
           "Colombia - Primera A")
CARTA = row("carta", "Cartagines", "Puntarenas", "2026-10-14T00:00:00Z",
            "Costa Rica - Primera Division")
AGF = row("1637171526", "AGF", "Sonderjyske", "2026-10-12T17:00:00Z", "Denmark - Superliga")
USA_SPAIN_W = row("usa-w", "USA", "Spain", "2026-10-13T23:00:00Z",
                  "International - Friendlies Women")
SVS_CL = "2026-10-13T21:00:00+02:00"


class VersionTests(unittest.TestCase):
    def test_versionen(self):
        self.assertEqual("pool-name-v8", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v8", v8("Århus", "Sönderjyske", [AGF],
                                            "2026-10-12T19:00:00+02:00")["match_version"])


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4382_inter_och_psv(self):
        self.assertEqual(("inter", "D", False),
                         ident(v8("Inter", "Club Brügge", [INTER], SVS_CL, "ITA", "BEL")))
        self.assertEqual(("psv", "D", False),
                         ident(v8("RB Leipzig", "PSV Eindhoven", [PSV], SVS_CL, "DEU", "NLD")))
        # Speglad SvS-ordning speglar oddsen.
        h = v8("Club Brügge", "Inter", [INTER], SVS_CL, "BEL", "ITA")
        self.assertEqual(("inter", "D", True), ident(h))
        self.assertEqual({"1": 3.6, "X": 3.4, "2": 2.0}, h["odds"])

    def test_topptipset_4383_bucaramanga_och_cartagines(self):
        self.assertEqual(("buca", "D", False), ident(v8(
            "Bucaramanga", "Aguilas", [BUCA], "2026-10-14T01:30:00+02:00", "COL", "COL")))
        self.assertEqual(("carta", "D", False), ident(v8(
            "CS Cartagines", "Puntarenas FC", [CARTA], "2026-10-14T02:00:00+02:00", "CRI", "CRI")))

    def test_topptipset_4383_usa_spanien_ar_damlandskampen(self):
        # SvS skrev "USA – Spanien" utan Dam; Pinnacles enda rad var damernas.
        self.assertEqual(("usa-w", "A", False), ident(v8(
            "USA", "Spanien", [USA_SPAIN_W], "2026-10-14T01:00:00+02:00", "USA", "ESP")))
        # Finns herrraden vinner den, oavsett ordning.
        men = {**USA_SPAIN_W, "id": "usa-m", "league": "International - Friendlies"}
        for index in ([USA_SPAIN_W, men], [men, USA_SPAIN_W]):
            self.assertEqual(("usa-m", "A", False), ident(v8(
                "USA", "Spanien", index, "2026-10-14T01:00:00+02:00", "USA", "ESP")))
        # U-åldrar är fortfarande veto.
        u21 = {**USA_SPAIN_W, "id": "usa-u21", "league": "International - U21 Friendlies"}
        self.assertIsNone(v8("USA", "Spanien", [u21], "2026-10-14T01:00:00+02:00", "USA", "ESP"))

    def test_topptipset_4380_arhus_ar_agf(self):
        self.assertEqual(("1637171526", "A", False), ident(v8(
            "Århus", "Sönderjyske", [AGF], "2026-10-12T19:00:00+02:00", "DNK", "DNK")))
        self.assertEqual("agf", op._norm_team("AGF Aarhus"))
        # VSK Aarhus är en annan klubb och får inget alias.
        self.assertEqual("vsk aarhus", op._norm_team("VSK Aarhus"))
        self.assertLess(op.team_sim("Århus", "VSK Aarhus"), op.HOME_AWAY_MIN)


class SkyddTests(unittest.TestCase):
    def test_d_kraver_avspark_inom_ankaret(self):
        late = {**INTER, "start": "2026-10-13T19:16:00Z"}
        self.assertIsNone(v8("Inter", "Club Brügge", [late], SVS_CL, "ITA", "BEL"))
        self.assertIsNone(v8("Inter", "Club Brügge", [INTER], None, "ITA", "BEL"))

    def test_d_rankas_efter_alla_tidigare_nivaer(self):
        exact = row("exact", "Inter", "Club Brugge", "2026-10-13T19:00:00Z", CL)
        for index in ([INTER, exact], [exact, INTER]):
            self.assertEqual(("exact", "A", False),
                             ident(v8("Inter", "Club Brügge", index, SVS_CL, "ITA", "BEL")))

    def test_exakt_lag_i_tva_rader_ar_tvetydigt(self):
        other = row("other", "Inter Miami", "Club Brugge", "2026-10-13T19:00:00Z", CL)
        diag = {}
        self.assertIsNone(v8("Inter", "Club Brügge", [INTER, other], SVS_CL, "ITA", "BEL", diag))
        self.assertEqual("ambiguous", diag["reason"])
        # Även när den andra raden inte kvalificerar alls.
        unrelated = row("u", "Genk", "Club Brugge", "2026-10-13T19:05:00Z", CL)
        self.assertIsNone(v8("Inter", "Club Brügge", [INTER, unrelated], SVS_CL, "ITA", "BEL"))

    def test_sc_trupper_och_landsnamn_ger_aldrig_d(self):
        start = "2026-10-13T19:00:00Z"
        self.assertIsNone(v8("Barcelona", "Sevilla", [row("sc", "Barcelona SC", "Sevilla", start, CL)],
                             start))
        self.assertIsNone(v8("RB Leipzig", "PSV Eindhoven",
                             [row("y", "RB Leipzig", "PSV", start, "UEFA - Youth League")], SVS_CL))
        self.assertIsNone(v8("RB Leipzig", "PSV Eindhoven",
                             [row("w", "RB Leipzig II", "PSV", start, CL)], SVS_CL))
        self.assertFalse(op.pool_weak("Ireland", "Northern Ireland"))
        self.assertFalse(op.pool_weak("Irland", "Nordirland"))
        self.assertFalse(op.pool_weak("Dundee", "Dundee United"))

    def test_pool_weak(self):
        for a, b in (("PSV Eindhoven", "PSV"), ("Aguilas", "Aguilas Doradas"),
                     ("CS Cartagines", "Cartagines"), ("Inter", "Internazionale"),
                     ("Feyenoord Rotterdam", "Feyenoord")):
            self.assertTrue(op.pool_weak(a, b), (a, b))
        for a, b in (("Inter", "Internazionale U19"), ("Int", "Internazionale"),
                     ("Town", "Luton Town"), ("Århus", "Sonderjyske"), ("PSV", "PSV")):
            self.assertFalse(op.pool_weak(a, b), (a, b))

    def test_v4_vagen_far_ingen_d(self):
        self.assertIsNone(pinnacle.match_index("Inter", "Club Brügge", "ITA", "BEL", [INTER], None))


if __name__ == "__main__":
    unittest.main()
