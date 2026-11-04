"""pool-name-v11: poolaliasen Slavia Prag/Prague → Slavia Praha och Sparta
Prag/Prague → Sparta Praha.

Beslut 2026-11-04-europa-2622-slavia (Saman, val 0). Pinnacles lagnamn och
avspark ur pool_match_diagnostic 2026-11-04 11:31Z (Europatipset 2622 match 1,
sidopoäng 0,0/1,0 före aliasen); SvS-namnen ur draw-API:t. Id:n är egna
etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league, odds=(4.2, 3.8, 1.8)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


def v11(home, away, index, start, home_iso=None, away_iso=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SVS_2622 = "2026-11-04T21:00:00+01:00"
SLAVIA = row("slavia", "Slavia Prague", "Arsenal", "2026-11-04T20:00:00Z",
             "UEFA - Champions League")


class VerkligaFallTests(unittest.TestCase):
    def test_europatipset_2622_slavia_prag_arsenal(self):
        self.assertEqual(("slavia", "A", False), ident(v11(
            "Slavia Prag", "Arsenal", [SLAVIA], SVS_2622, "CZE", "GBR")))

    def test_spegelvand_rad(self):
        swapped = row("slavias", "Arsenal", "Slavia Prague", "2026-11-04T20:00:00Z",
                      "UEFA - Champions League")
        self.assertEqual(("slavias", "A", True), ident(v11(
            "Slavia Prag", "Arsenal", [swapped], SVS_2622, "CZE", "GBR")))

    def test_sparta_prag(self):
        sparta = row("sparta", "Sparta Prague", "Bournemouth", "2026-11-05T17:45:00Z",
                     "UEFA - Europa League")
        self.assertEqual(("sparta", "A", False), ident(v11(
            "Sparta Prag", "Bournemouth", [sparta], "2026-11-05T18:45:00+01:00",
            "CZE", "GBR")))

    def test_versionen(self):
        self.assertEqual("pool-name-v11", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v11", v11(
            "Slavia Prag", "Arsenal", [SLAVIA], SVS_2622)["match_version"])


class SkyddTests(unittest.TestCase):
    def test_aliasen_ar_exakta(self):
        for name in ("Slavia Prag", "Slavia Prague", "SK Slavia Praha"):
            self.assertEqual("slavia praha", op._norm_team(name))
        for name in ("Sparta Prag", "Sparta Prague", "AC Sparta Praha"):
            self.assertEqual("sparta praha", op._norm_team(name))
        self.assertEqual(1.0, op.team_sim("Slavia Prag", "Slavia Prague"))
        self.assertEqual(1.0, op.team_sim("Sparta Prag", "Sparta Prague"))

    def test_slavia_och_sparta_skiljs_at(self):
        self.assertLess(op.team_sim("Slavia Prag", "Sparta Prague"), 1.0)
        # En Sparta-rad vid samma avspark är bara stavningsnära (nivå F, som i
        # v10); den exakta Slavia-raden vinner på nivå A.
        sparta = row("sparta", "Sparta Prague", "Arsenal", "2026-11-04T20:00:00Z",
                     "UEFA - Champions League")
        self.assertEqual(("slavia", "A", False), ident(v11(
            "Slavia Prag", "Arsenal", [sparta, SLAVIA], SVS_2622, "CZE", "GBR")))

    def test_andra_pragklubbar_rors_inte(self):
        self.assertEqual("bohemians prag", op._norm_team("Bohemians Prag"))
        self.assertEqual("dukla prague", op._norm_team("Dukla Prague"))

    def test_annan_motstandare_lankas_inte(self):
        other = row("other", "Slavia Prague", "Chelsea", "2026-11-04T20:00:00Z",
                    "UEFA - Champions League")
        self.assertIsNone(v11("Slavia Prag", "Arsenal", [other], SVS_2622,
                              "CZE", "GBR"))

    def test_avspark_utanfor_ankaret_lankas_inte(self):
        late = {**SLAVIA, "start": "2026-11-05T20:00:00Z"}
        self.assertIsNone(v11("Slavia Prag", "Arsenal", [late], SVS_2622,
                              "CZE", "GBR"))


if __name__ == "__main__":
    unittest.main()
