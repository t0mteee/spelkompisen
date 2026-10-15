"""pool-name-v9: svenska klubbnamn utan klubbform och genitiv-s, och aliaset
SC Delhi → Sporting Club Delhi.

Beslut koordinatorn-2026-10-15-pinnacle-alias (Saman, val 0). Raderna nedan är
Pinnacles egna lagnamn och avsparkar ur pool_match_diagnostic 2026-10-15
~08:24Z; SvS-namnen ur draw-API:t för Topptipset 4386/4390/4395. Id:n är egna
etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league, odds=(2.0, 3.4, 3.6)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


def v9(home, away, index, start, home_iso=None, away_iso=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SANDVIKEN = row("sand", "Sandvikens IF", "Ostersunds FK", "2026-10-17T13:00:00Z",
                "Sweden - Superettan")
VARBERG = row("varb", "Varbergs BoIS", "Helsingborgs", "2026-10-19T17:05:00Z",
              "Sweden - Superettan")
DELHI = row("delhi", "Sporting Club Delhi", "Mohun Bagan", "2026-10-16T14:00:00Z",
            "India - Super League")


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4390_sandviken_ostersund(self):
        self.assertEqual(("sand", "A", False), ident(v9(
            "Sandviken", "Östersund", [SANDVIKEN], "2026-10-17T15:00:00+02:00", "SWE", "SWE")))

    def test_topptipset_4395_varberg_helsingborg(self):
        # Varbergs BoIS blir exakt; Helsingborgs (utan IF) är ett delnamn och
        # länkas genom v8:s nivå D inom ankaret.
        self.assertEqual(("varb", "D", False), ident(v9(
            "Varberg", "Helsingborg", [VARBERG], "2026-10-19T19:05:00+02:00", "SWE", "SWE")))

    def test_topptipset_4386_sc_delhi(self):
        self.assertEqual(("delhi", "A", False), ident(v9(
            "SC Delhi", "Mohun Bagan", [DELHI], "2026-10-16T16:00:00+02:00", "IND", "IND")))

    def test_versionen(self):
        self.assertEqual("pool-name-v9", op.POOL_MATCH_VERSION)


class RegelTests(unittest.TestCase):
    def test_klubbform_och_genitiv_tas_bort(self):
        for svs, pin in (("Sandviken", "Sandvikens IF"), ("Östersund", "Östersunds FK"),
                         ("Varberg", "Varbergs BoIS"), ("Helsingborg", "Helsingborgs IF"),
                         ("Kristiansund", "Kristiansunds BK"), ("Häcken", "BK Häcken")):
            self.assertEqual(1.0, op.team_sim(svs, pin), (svs, pin))
            self.assertEqual(1.0, op.team_sim(pin, svs), (pin, svs))

    def test_namn_som_slutar_pa_s_ar_oforandrade(self):
        self.assertEqual(1.0, op.team_sim("Degerfors", "Degerfors IF"))
        self.assertEqual("degerfors", op._norm_team("Degerfors"))
        # Utan klubbform tas inget s bort: Rangers/Ranger och Helsingborgs
        # ensamt är inte exakt (Helsingborgs länkas bara via nivå D).
        self.assertLess(op.team_sim("Helsingborg", "Helsingborgs"), 1.0)
        self.assertLess(op.team_sim("Ranger", "Rangers"), 1.0)

    def test_bara_ordet_fore_formen_och_bara_de_fyra_formerna(self):
        self.assertIsNone(op._swedish_key("Malmö FF"))
        self.assertIsNone(op._swedish_key("Örgryte IS"))
        self.assertLess(op.team_sim("Malmo", "Malmos FF"), 1.0)
        # Formen FÖRE namnet tar inget s (IF Brommapojkarna, FK Haugesund).
        self.assertEqual("haugesund", op._swedish_key("FK Haugesund"))
        self.assertLess(op.team_sim("Brommapojkarna", "IF Brommapojkarnas"), 1.0)

    def test_truppmarkoren_bevaras(self):
        self.assertEqual(0.0, op.team_sim("Sandviken", "Sandvikens IF U21"))
        self.assertEqual(1.0, op.team_sim("Sandviken U21", "Sandvikens IF U21"))

    def test_annan_klubb_lanks_inte(self):
        other = row("other", "Gefle IF", "Ostersunds FK", "2026-10-17T13:00:00Z",
                    "Sweden - Superettan")
        self.assertIsNone(v9("Sandviken", "Östersund", [other],
                             "2026-10-17T15:00:00+02:00", "SWE", "SWE"))

    def test_sc_delhi_ar_inget_globalt_sc_alias(self):
        # Barcelona ≠ Barcelona SC gäller fortfarande.
        self.assertLess(op.team_sim("Barcelona", "Barcelona SC"), 1.0)
        self.assertLess(op.team_sim("SC Delhi", "Delhi"), 1.0)


if __name__ == "__main__":
    unittest.main()
