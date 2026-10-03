"""Landslag i Oddset: landskoder i stället för namnlikhet (app/landslag.py)."""
import unittest
from unittest.mock import patch

from app import landslag, oddset


class LandskodTests(unittest.TestCase):
    def test_svenska_och_engelska_namn_ger_samma_kod(self):
        for sv, en, code in (("Tyskland", "Germany", "GER"),
                             ("Bosnien & Hercegovina", "Bosnia and Herzegovina", "BIH"),
                             ("Turkiet", "Türkiye", "TUR"),
                             ("Nordirland", "Northern Ireland", "NIR"),
                             ("Irland", "Republic of Ireland", "IRL"),
                             ("Färöarna", "Faroe Islands", "FRO"),
                             ("Elfenbenskusten", "Côte d’Ivoire", "CIV"),
                             ("Tjeckien", "Czechia", "CZE"),
                             ("Nederländerna", "Netherlands", "NED")):
            self.assertEqual(code, landslag.kod(sv), sv)
            self.assertEqual(code, landslag.kod(en), en)
        self.assertEqual("TRI", landslag.kod("Trinidad and Tobago"))
        self.assertEqual("TUR", landslag.kod("Turkey"))

    def test_namn_inuti_varandra_ar_olika_lag(self):
        for a, b in (("Irland", "Nordirland"), ("Ireland", "Northern Ireland"),
                     ("Niger", "Nigeria"), ("Guinea", "Guinea-Bissau"),
                     ("Kongo", "DR Kongo"), ("Sydkorea", "Nordkorea")):
            self.assertTrue(landslag.kod(a) and landslag.kod(b), (a, b))
            self.assertNotEqual(landslag.kod(a), landslag.kod(b), (a, b))

    def test_okanda_ungdoms_och_klubbnamn_ger_ingen_kod(self):
        for name in ("Sverige U21", "Sweden W", "Hammarby", "Inter", ""):
            self.assertIsNone(landslag.kod(name), name)

    def test_ett_namn_kan_aldrig_peka_pa_tva_lander(self):
        with patch.dict(landslag.LANDSLAG, {"XXX": ("Sverige",)}):
            with self.assertRaises(ValueError):
                landslag._index()      # noqa: SLF001


class LandslagsKopplingTests(unittest.TestCase):
    PIN = [
        {"id": "pin:1", "home": "Republic of Ireland", "away": "Israel",
         "start": "2026-10-04T18:45:00Z"},
        {"id": "pin:2", "home": "Northern Ireland", "away": "Georgia",
         "start": "2026-10-05T18:45:00Z"},
        {"id": "pin:3", "home": "Germany", "away": "Greece",
         "start": "2026-10-04T18:45:00Z"},
    ]

    def test_svenska_namn_kopplas_till_ratt_pinnaclematch(self):
        hit = oddset._resolve_landslag(self.PIN, "Tyskland", "Grekland",
                                       "2026-10-04T20:45:00+02:00")
        self.assertEqual("pin:3", hit["id"])

    def test_omvand_ordning_kopplas_aldrig(self):
        # Priserna vore spegelvända — hellre en egen rad.
        self.assertIsNone(oddset._resolve_landslag(
            self.PIN, "Grekland", "Tyskland", "2026-10-04T18:45:00Z"))

    def test_irland_och_nordirland_blandas_aldrig_ihop(self):
        self.assertEqual("pin:1", oddset._resolve_landslag(
            self.PIN, "Irland", "Israel", "2026-10-04T18:45:00Z")["id"])
        self.assertEqual("pin:2", oddset._resolve_landslag(
            self.PIN, "Nordirland", "Georgien", "2026-10-05T18:45:00Z")["id"])
        self.assertIsNone(oddset._resolve_landslag(
            self.PIN, "Irland", "Georgien", "2026-10-05T18:45:00Z"))
        self.assertIsNone(oddset._resolve_landslag(
            self.PIN, "Nordirland", "Israel", "2026-10-04T18:45:00Z"))

    def test_avspark_over_tva_timmar_och_tva_kandidater_ger_ingen_koppling(self):
        self.assertIsNone(oddset._resolve_landslag(
            self.PIN, "Tyskland", "Grekland", "2026-10-04T23:00:00Z"))
        dubbel = self.PIN + [{"id": "pin:4", "home": "Germany", "away": "Greece",
                              "start": "2026-10-04T19:00:00Z"}]
        self.assertIsNone(oddset._resolve_landslag(
            dubbel, "Tyskland", "Grekland", "2026-10-04T18:45:00Z"))

    def test_okant_namn_ger_ingen_koppling(self):
        self.assertIsNone(oddset._resolve_landslag(
            self.PIN, "Tyskland U21", "Grekland U21", "2026-10-04T18:45:00Z"))
        self.assertEqual(["Tyskland U21"],
                         oddset._okanda_landslag("Tyskland U21", "Grekland"))
        # Pinnacles hörnmarknader är låtsasdeltagare, inte okända landslag.
        self.assertEqual([], oddset._okanda_landslag("DR Congo (Corners)", "Uganda (Corners)"))

    def test_kallresolvern_tar_aldrig_over_ett_last_id(self):
        cands = [dict(c) for c in self.PIN]
        cands[2]["kambi_id"] = "99"
        self.assertIsNone(oddset._resolve_source(
            cands, "Tyskland", "Grekland", "2026-10-04T18:45:00Z", "100", "kambi_id",
            oddset._resolve_landslag))
        self.assertEqual("pin:3", oddset._resolve_source(
            cands, "Tyskland", "Grekland", "2026-10-04T18:45:00Z", "99", "kambi_id",
            oddset._resolve_landslag)["id"])


class LandslagsLigorTests(unittest.TestCase):
    def test_sharp_utan_modell_och_utanfor_liveradarn(self):
        from app import live_radar, oddset_data
        leagues = {lg["key"]: lg for lg in oddset.LEAGUES}
        nya = {"nations_league", "landskamper"}
        for key in nya:
            self.assertTrue(leagues[key]["landslag"], key)
            self.assertIn(key, oddset.ACTIONABLE_LEAGUE_KEYS)
            self.assertIn(key, oddset.VISIBLE_LEAGUE_KEYS)
        self.assertEqual([200719, 200721, 200726, 200727],
                         leagues["nations_league"]["pin_ids"])
        self.assertFalse(nya & set(oddset_data.MODEL_LEAGUES))
        # Liveradarn följer med sedan v13 (docs/radar-scope-v13-2026-10-03.md):
        # via Flashscore och FotMob, aldrig via Sofascore (urkopplad).
        from app import flashscore, fotmob
        self.assertFalse(nya & set(live_radar.TARGET_UT.values()))
        self.assertLessEqual(nya, set(live_radar.LEAGUE_PRIORITY))
        self.assertLessEqual(nya, set(flashscore.LEAGUE_NAMES.values()))
        self.assertLessEqual(nya, set(fotmob.LEAGUE_NAMES.values()))
        self.assertIn("landskamper", live_radar.GATED_LEAGUES)
        self.assertNotIn("WORLD: Friendly International Women", flashscore.LEAGUE_NAMES)
        # Klubbligorna kopplas som förut, på namnlikhet.
        self.assertFalse(any(lg.get("landslag") for lg in oddset.LEAGUES
                             if lg["key"] not in nya))


if __name__ == "__main__":
    unittest.main()
