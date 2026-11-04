"""pool-name-v12: poolaliaset LD Alajuelense → Alajuelense.

Beslut drift-2026-11-04-topptipset-4429-alajuelense-alias (Saman, val 0).
Pinnacles lagnamn och avspark ur pool_match_diagnostic 2026-11-04 17:40Z
(Topptipset 4429 match 8, sidopoäng 0,0/0,0 före aliaset); SvS-namnen ur
draw-API:t. Id:n är egna etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league="Costa Rica - Primera Division",
        odds=(4.0, 3.6, 1.8)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.5, "O": 1.9, "U": 1.9}}


def v12(home, away, index, start, home_iso="CRI", away_iso="CRI"):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SVS_4429 = "2026-11-05T03:00:00+01:00"
ESCORPIONES = row("esc", "Escorpiones Belen", "Alajuelense", "2026-11-05T02:00:00Z")


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4429_escorpiones_alajuelense(self):
        self.assertEqual(("esc", "D", False), ident(v12(
            "CD Escorpiones Belen", "LD Alajuelense", [ESCORPIONES], SVS_4429)))

    def test_spegelvand_rad(self):
        swapped = row("escs", "Alajuelense", "Escorpiones Belen", "2026-11-05T02:00:00Z")
        self.assertEqual(("escs", "D", True), ident(v12(
            "CD Escorpiones Belen", "LD Alajuelense", [swapped], SVS_4429)))

    def test_herediano_alajuelense_nivå_a(self):
        clasico = row("clasico", "Herediano", "Alajuelense", "2026-11-08T01:00:00Z")
        self.assertEqual(("clasico", "A", False), ident(v12(
            "CS Herediano", "LD Alajuelense", [clasico], "2026-11-08T02:00:00+01:00")))

    def test_versionen(self):
        self.assertEqual("pool-name-v12", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v12", v12(
            "CD Escorpiones Belen", "LD Alajuelense", [ESCORPIONES],
            SVS_4429)["match_version"])


class SkyddTests(unittest.TestCase):
    def test_aliaset_ar_exakt(self):
        self.assertEqual("alajuelense", op._norm_team("LD Alajuelense"))
        self.assertEqual("alajuelense", op._norm_team("Alajuelense"))
        self.assertEqual(1.0, op.team_sim("LD Alajuelense", "Alajuelense"))
        self.assertEqual("cd escorpiones belen", op._norm_team("CD Escorpiones Belen"))

    def test_annan_motstandare_lankas_inte(self):
        other = row("other", "Escorpiones Belen", "Saprissa", "2026-11-05T02:00:00Z")
        self.assertIsNone(v12("CD Escorpiones Belen", "LD Alajuelense", [other],
                              SVS_4429))

    def test_avspark_utanfor_ankaret_lankas_inte(self):
        late = {**ESCORPIONES, "start": "2026-11-06T02:00:00Z"}
        self.assertIsNone(v12("CD Escorpiones Belen", "LD Alajuelense", [late],
                              SVS_4429))


if __name__ == "__main__":
    unittest.main()
