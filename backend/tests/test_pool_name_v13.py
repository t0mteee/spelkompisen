"""pool-name-v13: kontextaliaset Sarmiento → Sarmiento de Junin, bara mot Tigre.

Beslut driften-2026-11-07-topptipset-4433-sarmiento-alias (Saman, val 0).
Pinnacles lagnamn och avspark ur pool_match_diagnostic (Topptipset 4433
match 2, sidopoäng 0,0/0,0 före aliaset); SvS-namnen ur draw-API:t. Id:n är
egna etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league="Argentina - Liga Profesional",
        odds=(2.3, 3.0, 3.4)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.0, "O": 1.9, "U": 1.9}}


def v13(home, away, index, start, home_iso="ARG", away_iso="ARG"):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SVS_4433 = "2026-11-07T02:00:00+01:00"
TIGRE = row("tig", "CA Tigre", "Sarmiento de Junin", "2026-11-07T01:00:00Z")


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4433_tigre_sarmiento(self):
        self.assertEqual(("tig", "D", False), ident(v13(
            "Tigre", "Sarmiento", [TIGRE], SVS_4433)))

    def test_spegelvand_rad(self):
        swapped = row("tigs", "Sarmiento de Junin", "CA Tigre", "2026-11-07T01:00:00Z")
        self.assertEqual(("tigs", "D", True), ident(v13(
            "Tigre", "Sarmiento", [swapped], SVS_4433)))

    def test_sarmiento_hemma(self):
        home = row("home", "Sarmiento de Junin", "CA Tigre", "2026-11-07T01:00:00Z")
        self.assertEqual(("home", "D", False), ident(v13(
            "Sarmiento", "Tigre", [home], SVS_4433)))

    def test_versionen(self):
        self.assertEqual("pool-name-v14", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v14", v13(
            "Tigre", "Sarmiento", [TIGRE], SVS_4433)["match_version"])


class SkyddTests(unittest.TestCase):
    def test_inget_globalt_alias(self):
        self.assertEqual("sarmiento", op._norm_team("Sarmiento"))
        self.assertEqual("ca tigre", op._norm_team("CA Tigre"))
        self.assertEqual(0.0, op.team_sim("Sarmiento", "Sarmiento de Junin"))

    def test_annan_motstandare_lankas_inte(self):
        # Topptipset 4418: Sarmiento–Rosario mot "Sarmiento de Junin – Rosario
        # Central" vid exakt avspark. Kontextaliaset gäller bara mot Tigre.
        rosario = row("ros", "Sarmiento de Junin", "Rosario Central", "2026-10-31T00:15:00Z")
        self.assertIsNone(v13("Sarmiento", "Rosario", [rosario],
                              "2026-10-31T01:15:00+01:00"))

    def test_sarmiento_resistencia_lankas_inte(self):
        resistencia = row("res", "CA Tigre", "Sarmiento Resistencia", "2026-11-07T01:00:00Z")
        self.assertIsNone(v13("Tigre", "Sarmiento", [resistencia], SVS_4433))

    def test_motpartens_form_galler_bara_paret(self):
        self.assertEqual(0.0, op.pool_side_score(
            ["Sarmiento"], "Sarmiento de Junin", "Tigre", "Tigres UANL", 0.0))
        self.assertEqual(1.0, op.pool_side_score(
            ["Sarmiento"], "Sarmiento de Junin", "Tigre", "CA Tigre", 0.0))
        self.assertEqual(1.0, op.pool_side_score(
            ["Sarmiento"], "Sarmiento de Junin", "Tigre", "Tigre", 0.0))

    def test_avspark_utanfor_ankaret_lankas_inte(self):
        late = {**TIGRE, "start": "2026-11-08T01:00:00Z"}
        self.assertIsNone(v13("Tigre", "Sarmiento", [late], SVS_4433))

    def test_kontextaliaset_kraver_kand_avspark(self):
        self.assertEqual(0.0, op.pool_side_score(
            ["Sarmiento"], "Sarmiento de Junin", "Tigre", "CA Tigre", None))


if __name__ == "__main__":
    unittest.main()
