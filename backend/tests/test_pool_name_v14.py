"""pool-name-v14: apostroferna ´ och ’ tas bort, och kontextaliaset
Instituto de Cordoba → Instituto, bara mot Newells Old Boys.

Beslut driften-2026-11-07-topptipset-4436-instituto-newells-alias (Saman,
val 0). Pinnacles lagnamn och avspark ur pool_match_diagnostic (Topptipset
4436 match 8, sidopoäng 0,0/0,97 före ändringen); SvS-namnen ur draw-API:t.
Id:n är egna etiketter.
"""
import unittest

from app import odds_provider as op, pinnacle


def row(id_, home, away, start, league="Argentina - Liga Profesional",
        odds=(2.6, 3.0, 2.9)):
    return {"id": id_, "home": home, "away": away, "start": start, "league": league,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": {"line": 2.0, "O": 1.9, "U": 1.9}}


def v14(home, away, index, start, home_iso="ARG", away_iso="ARG"):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, None,
                                league_squads=True)


def ident(hit):
    return (hit["id"], hit["match_tier"], hit["swapped"]) if hit else None


SVS_4436 = "2026-11-08T02:00:00+01:00"
INSTITUTO = row("ins", "Instituto", "Newells Old Boys", "2026-11-08T01:00:00Z")


class ApostrofTests(unittest.TestCase):
    def test_apostroferna_tas_bort(self):
        for name in ("Newell´s Old Boys", "Newell’s Old Boys", "Newell's Old Boys",
                     "Newells Old Boys"):
            self.assertEqual("newells old boys", op._norm_team(name), name)
        self.assertEqual(1.0, op.team_sim("Newell´s Old Boys", "Newells Old Boys"))
        self.assertEqual(1.0, op.team_sim("Newell’s Old Boys", "Newell's Old Boys"))

    def test_globala_normaliseringen_orord(self):
        from app.oddset import norm_team
        self.assertEqual("newell´s old boys", norm_team("Newell´s Old Boys"))


class VerkligaFallTests(unittest.TestCase):
    def test_topptipset_4436_instituto_newells(self):
        self.assertEqual(("ins", "A", False), ident(v14(
            "Instituto de Cordoba", "Newell´s Old Boys", [INSTITUTO], SVS_4436)))

    def test_spegelvand_rad(self):
        swapped = row("inss", "Newells Old Boys", "Instituto", "2026-11-08T01:00:00Z")
        self.assertEqual(("inss", "A", True), ident(v14(
            "Instituto de Cordoba", "Newell´s Old Boys", [swapped], SVS_4436)))

    def test_instituto_borta(self):
        away = row("away", "Newells Old Boys", "Instituto", "2026-11-08T01:00:00Z")
        self.assertEqual(("away", "A", False), ident(v14(
            "Newell´s Old Boys", "Instituto de Cordoba", [away], SVS_4436)))

    def test_versionen(self):
        self.assertEqual("pool-name-v14", op.POOL_MATCH_VERSION)
        self.assertEqual("pool-name-v14", v14(
            "Instituto de Cordoba", "Newell´s Old Boys", [INSTITUTO],
            SVS_4436)["match_version"])


class SkyddTests(unittest.TestCase):
    def test_inget_globalt_alias(self):
        self.assertEqual("instituto de cordoba", op._norm_team("Instituto de Cordoba"))
        self.assertEqual("instituto", op._norm_team("Instituto"))
        self.assertEqual(0.0, op.team_sim("Instituto de Cordoba", "Instituto"))

    def test_annan_motstandare_far_inget_kontextalias(self):
        # Mot en annan motpart gäller kontextaliaset inte; raden prövas med
        # v8:s oförändrade regel (exakt motpart + icke-generiskt delnamn = D).
        belgrano = row("bel", "Instituto", "Belgrano", "2026-11-08T01:00:00Z")
        self.assertEqual(("bel", "D", False), ident(v14(
            "Instituto de Cordoba", "Belgrano", [belgrano], SVS_4436)))

    def test_kontextaliaset_kraver_exakt_motpart(self):
        self.assertEqual(0.0, op.pool_side_score(
            ["Instituto de Cordoba"], "Instituto", "Newell´s Old Boys", "Belgrano", 0.0))
        self.assertEqual(1.0, op.pool_side_score(
            ["Instituto de Cordoba"], "Instituto", "Newell´s Old Boys",
            "Newells Old Boys", 0.0))

    def test_avspark_utanfor_ankaret_lankas_inte(self):
        late = {**INSTITUTO, "start": "2026-11-09T01:00:00Z"}
        self.assertIsNone(v14("Instituto de Cordoba", "Newell´s Old Boys", [late],
                              SVS_4436))

    def test_kontextaliaset_kraver_kand_avspark(self):
        self.assertEqual(0.0, op.pool_side_score(
            ["Instituto de Cordoba"], "Instituto", "Newell´s Old Boys",
            "Newells Old Boys", None))


if __name__ == "__main__":
    unittest.main()
