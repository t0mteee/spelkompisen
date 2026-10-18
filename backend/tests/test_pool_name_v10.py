"""pool-name-v10: poolaliasen Perez Zeledon → Municipal Perez Zeledon och
CS Herediano → Herediano.

Beslut drift-2026-10-18-pool-perez-zeledon-alias (Saman, val 0). Pinnacles
lagnamn och avspark ur pool_match_diagnostic 2026-10-18 15:37Z (Topptipset 4394
match 8, sidopoäng 0,0/0,0 före aliasen); SvS-namnen ur draw-API:t. Id:n är
egna etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league, odds=(2.0, 3.4, 3.6)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


def v10(home, away, index, start, home_iso=None, away_iso=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SVS_4394 = "2026-10-19T00:00:00+02:00"
PZ = row("pz", "Municipal Perez Zeledon", "Herediano", "2026-10-18T22:00:00Z",
         "Costa Rica - Primera Division")


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4394_perez_zeledon_cs_herediano(self):
        self.assertEqual(("pz", "A", False), ident(v10(
            "Perez Zeledon", "CS Herediano", [PZ], SVS_4394, "CRI", "CRI")))

    def test_spegelvand_rad(self):
        swapped = row("pzs", "Herediano", "Municipal Perez Zeledon",
                      "2026-10-18T22:00:00Z", "Costa Rica - Primera Division")
        self.assertEqual(("pzs", "A", True), ident(v10(
            "Perez Zeledon", "CS Herediano", [swapped], SVS_4394, "CRI", "CRI")))

    def test_versionen(self):
        self.assertEqual("pool-name-v10", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v10", v10(
            "Perez Zeledon", "CS Herediano", [PZ], SVS_4394)["match_version"])


class SkyddTests(unittest.TestCase):
    def test_aliasen_ar_exakta(self):
        self.assertEqual(1.0, op.team_sim("Perez Zeledon", "Municipal Perez Zeledon"))
        self.assertEqual(1.0, op.team_sim("Pérez Zeledón", "Municipal Perez Zeledon"))
        self.assertEqual(1.0, op.team_sim("CS Herediano", "Herediano"))

    def test_andra_municipal_och_cs_klubbar_rors_inte(self):
        self.assertEqual("municipal limeno", op._norm_team("Municipal Limeno"))
        self.assertEqual("cs constantine", op._norm_team("CS Constantine"))
        # "Municipal" delas, men en annan Municipal-rad vid samma avspark länkas inte.
        limeno = row("lim", "Municipal Limeno", "FAS", "2026-10-18T22:00:00Z",
                     "El Salvador - Primera Division")
        self.assertIsNone(v10("Perez Zeledon", "CS Herediano", [limeno], SVS_4394,
                              "CRI", "CRI"))

    def test_annan_motstandare_lankas_inte(self):
        other = row("other", "Alajuelense", "Herediano", "2026-10-18T22:00:00Z",
                    "Costa Rica - Primera Division")
        self.assertIsNone(v10("Perez Zeledon", "CS Herediano", [other], SVS_4394,
                              "CRI", "CRI"))

    def test_avspark_utanfor_ankaret_lankas_inte(self):
        late = {**PZ, "start": "2026-10-19T22:00:00Z"}
        self.assertIsNone(v10("Perez Zeledon", "CS Herediano", [late], SVS_4394,
                              "CRI", "CRI"))


if __name__ == "__main__":
    unittest.main()
