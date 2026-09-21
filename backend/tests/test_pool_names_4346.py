"""Observerade par 2026-09-21: riktiga priser ska följa rätt fysisk match."""
import unittest

from app import odds_provider, pinnacle


class PoolNames4346Tests(unittest.TestCase):
    start = "2026-09-22T00:15:00Z"

    def event(self, home="Lanus", away="Estudiantes de La Plata", **extra):
        return {"id": "1636054672", "home": home, "away": away,
                "start": self.start, "odds": {"1": 2.26, "X": 2.95, "2": 3.97},
                "odds_source": "pinnacle", "total": {"line": 1.75, "O": 1.83, "U": 2.07},
                **extra}

    def match(self, index, home="Lanús", away="Estudiantes", start=None):
        return pinnacle.match_index(home, away, "ARG", "ARG", index,
                                    self.start if start is None else start)

    def test_bekraftat_par_far_bade_1x2_och_total(self):
        event = self.event()
        hit = self.match([event])
        self.assertEqual(event["id"], hit["id"])
        self.assertEqual(event["odds"], hit["odds"])
        self.assertEqual(event["total"], hit["total"])
        self.assertEqual("pool-name-v4", hit["match_version"])
        # Ett generellt Estudiantes-alias skulle även träffa andra klubbar.
        self.assertEqual(0, odds_provider.team_sim("Estudiantes", "Estudiantes de La Plata"))

    def test_andra_estudiantes_och_trupper_far_aldrig_lanka(self):
        right = self.event()
        for name in ("Estudiantes de Caseros", "Estudiantes Rio Cuarto",
                     "Estudiantes de La Plata U20", "Estudiantes de La Plata Women"):
            wrong = self.event(away=name, id="wrong")
            with self.subTest(name=name):
                self.assertIsNone(self.match([wrong]))
                for index in ([wrong, right], [right, wrong]):
                    self.assertEqual(right["id"], self.match(index)["id"])

    def test_kontextalias_kraver_motstandare_och_nara_kand_tid(self):
        for opponent in ("Lanus U20", "Flamengo"):
            self.assertIsNone(self.match([self.event(home=opponent)], home=opponent))
        for time in (None, "trasig-tid", "2026-09-22T00:31:00Z"):
            self.assertIsNone(self.match([self.event(start=time)]))
        self.assertIsNone(pinnacle.match_index("Lanús", "Estudiantes", None, None,
                                              [self.event()], None))

    def test_spegling_och_tvetydighet_bevaras(self):
        event = self.event()
        hit = self.match([event], home="Estudiantes", away="Lanús")
        self.assertTrue(hit["swapped"])
        self.assertEqual({"1": 3.97, "X": 2.95, "2": 2.26}, hit["odds"])
        self.assertEqual(event["total"], hit["total"])
        self.assertIsNone(self.match([event, {**event, "id": "other"}]))

    def test_cuiaba_alias_total_och_truppvakt(self):
        event = self.event(home="Cuiaba", away="Nautico", id="1636640777",
                           total={"line": 2.25, "O": 2.07, "U": 1.82})
        hit = self.match([event], home="Cuiaba Esporte", away="Nautico")
        self.assertEqual(event["id"], hit["id"])
        self.assertEqual(event["total"], hit["total"])
        for name in ("Cuiaba U20", "Cuiaba Women", "Cuiaba (Corners)"):
            self.assertIsNone(self.match([{**event, "home": name}],
                                        home="Cuiaba Esporte", away="Nautico"))
