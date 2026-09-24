"""pool-name-v5: tidsankare, nivåer A/B/C/F, generiska delnamn och landslag.

Raderna är Pinnacles egna (id, avspark, odds, total) ur indexet 2026-09-24
12:25Z, se docs/overlamningar/overlamning-2026-09-24-poolnamn-v5.md.
"""
import tempfile
import unittest
from pathlib import Path

from app import odds_provider as op, pinnacle
from app.storage import Storage


def row(id_, home, away, start, odds=(2.0, 3.4, 3.6), total=None):
    return {"id": id_, "home": home, "away": away, "start": start,
            "odds": dict(zip("1X2", odds)), "odds_source": "pinnacle",
            "total": total or {"line": 2.5, "O": 1.9, "U": 1.9}}


PLYMOUTH = row("1636986820", "Plymouth Argyle", "Burton Albion", "2026-09-26T14:00:00Z",
               (1.58, 4.23, 5.16), {"line": 2.75, "O": 1.85, "U": 1.97})
CAMBRIDGE = row("1636963352", "Cambridge United", "AFC Wimbledon", "2026-09-26T14:00:00Z",
                (1.85, 3.52, 4.28), {"line": 2.25, "O": 1.85, "U": 1.98})
SWINDON = row("1637080857", "Swindon Town", "Accrington Stanley", "2026-09-26T14:00:00Z",
              (2.24, 3.59, 2.97))
ENGLAND_SPAIN = row("1636346499", "England", "Spain", "2026-09-26T18:45:00Z", (2.96, 3.42, 2.48))
FINLAND_SPAIN = row("1636333034", "Finland", "Spain", "2026-09-25T15:30:00Z", (6.06, 4.52, 1.45))
TURKIYE_FRANCE = row("1636333025", "Turkiye", "France", "2026-09-25T18:45:00Z", (7.87, 4.84, 1.42))
UKRAINE_TURKIYE = row("1636480685", "Ukraine", "Turkiye", "2026-09-26T16:00:00Z", (2.31, 3.49, 2.89))
HUNGARY_UKRAINE = row("1636346503", "Hungary", "Ukraine", "2026-09-25T18:45:00Z", (2.31, 3.25, 3.23))
CZECHIA_CROATIA = row("1636333033", "Czechia", "Croatia", "2026-09-26T18:45:00Z", (3.4, 3.55, 2.18))
SVS_SAT_1600 = "2026-09-26T16:00:00+02:00"      # = 14:00Z
SVS_ENG_ESP = "2026-09-26T20:45:00+02:00"       # = 18:45Z
SVS_TUR_FRA = "2026-09-25T20:45:00+02:00"       # = 18:45Z


def hit(home, away, index, start=SVS_SAT_1600, home_iso=None, away_iso=None, diag=None):
    return pinnacle.match_index(home, away, home_iso, away_iso, index, start, diag)


class GeneriskaDelnamnTests(unittest.TestCase):
    def test_plymouth_burton_ar_delnamn_pa_bada_sidor(self):
        h = hit("Plymouth", "Burton", [PLYMOUTH], home_iso="ENG", away_iso="ENG")
        self.assertEqual(("1636986820", "C", False), (h["id"], h["match_tier"], h["swapped"]))
        self.assertEqual(PLYMOUTH["odds"], h["odds"])
        self.assertEqual(PLYMOUTH["total"], h["total"])          # samma fysiska match
        self.assertEqual(op.POOL_MATCH_VERSION, h["match_version"])
        self.assertEqual("pool-name-v6", h["match_version"])

    def test_cambridge_wimbledon_exakt_plus_delnamn(self):
        h = hit("Cambridge", "Wimbledon", [CAMBRIDGE], home_iso="ENG", away_iso="ENG")
        self.assertEqual(("1636963352", "B"), (h["id"], h["match_tier"]))
        self.assertEqual(0.9, h["confidence"])
        # Omvänd SvS-orientering speglar 1X2 men totalen följer samma id.
        h = hit("Wimbledon", "Cambridge", [CAMBRIDGE])
        self.assertTrue(h["swapped"])
        self.assertEqual({"1": 4.28, "X": 3.52, "2": 1.85}, h["odds"])
        self.assertEqual(CAMBRIDGE["total"], h["total"])

    def test_klubbformsord_ar_delnamn_men_identitetsord_inte(self):
        for a, b in (("Plymouth", "Plymouth Argyle"), ("Burton", "Burton Albion"),
                     ("Crewe", "Crewe Alexandra"), ("Accrington", "Accrington Stanley"),
                     ("Novorizontino", "Gremio Novorizontino"), ("Tijuana", "Club Tijuana"),
                     ("Pereira", "Deportivo Pereira"), ("Galway", "Galway United")):
            self.assertTrue(op.pool_part(a, b), (a, b))
            self.assertTrue(op.pool_part(b, a), (b, a))
            self.assertEqual(0.0, op.team_sim(a, b))           # team_sim orörd
        self.assertTrue(op.pool_part("Plymouth U21", "Plymouth Argyle U21"))   # samma trupp
        for a, b in (("Inter", "Inter Miami"), ("Barcelona", "Barcelona SC"),
                     ("United", "Manchester United"), ("Queens Park", "Queens Park Rangers"),
                     ("Sheffield", "Sheffield Wednesday"), ("Albacete", "Atletico Albacete"),
                     ("Las Palmas", "Las Palmas Atletico"), ("Paris FC", "Paris 13 Atletico"),
                     ("Estudiantes", "Estudiantes de Caseros"), ("Aguilas", "Aguilas Doradas"),
                     ("Fortaleza", "Fortaleza CEIF"), ("Athletic", "Athletic Club"),
                     ("Plymouth", "Plymouth Argyle U21"), ("Plymouth", "Plymouth Argyle Women"),
                     ("Oman", "Oman Club"), ("Arab Emirates", "United Arab Emirates")):
            self.assertFalse(op.pool_part(a, b), (a, b))

    def test_belagda_olika_klubbar_ar_aldrig_delnamn(self):
        for a, b in (("Dundee", "Dundee United"), ("Dundee FC", "Dundee United"),
                     ("Oxford", "Oxford City"), ("America", "Club America"),
                     ("Guarani", "Club Guarani"), ("Morön BK", "Deportivo Moron"),
                     ("Deportivo Municipal", "Municipal"), ("Bangor City", "Bangor"),
                     ("Eskilstuna City", "AFC Eskilstuna"), ("Club Aurora", "Aurora FC")):
            self.assertFalse(op.pool_part(a, b), (a, b))

    def test_dundee_mot_dundee_united_lankar_inte(self):
        start = "2026-10-10T16:00:00+02:00"
        dundee_utd = row("1637159055", "Dundee United", "Hibernian", "2026-10-10T14:00:00Z")
        dundee_fc = row("1637158349", "Falkirk", "Dundee FC", "2026-10-10T14:00:00Z")
        # Annan motståndare, och även samma motståndare: Dundee är inte Dundee United.
        self.assertIsNone(hit("Dundee", "St Mirren", [dundee_utd], start))
        self.assertIsNone(hit("Dundee", "Hibernian", [dundee_utd], start))
        self.assertEqual("1637158349", hit("Falkirk", "Dundee", [dundee_utd, dundee_fc], start)["id"])
        # Derbyt: exakt orientering (A) vinner, spegelvända delnamn blockerar inte.
        derby = row("d", "Dundee FC", "Dundee United", "2026-10-10T14:00:00Z", (2.5, 3.3, 2.9))
        h = hit("Dundee", "Dundee United", [derby], start)
        self.assertEqual(("A", False), (h["match_tier"], h["swapped"]))

    def test_inter_och_barcelona_skyddade_aven_vid_exakt_motstandare_och_avspark(self):
        start = "2026-09-15T18:00:00Z"
        miami = row("m", "Inter Miami", "Lazio", start)
        barca_sc = row("sc", "Barcelona SC", "Sevilla", start)
        self.assertIsNone(hit("Inter", "Lazio", [miami], start))
        self.assertIsNone(hit("Barcelona", "Sevilla", [barca_sc], start))
        right = row("fcb", "Barcelona", "Sevilla", start)
        for index in ([barca_sc, right], [right, barca_sc]):
            self.assertEqual("fcb", hit("Barcelona", "Sevilla", index, start)["id"])


class TidsankareTests(unittest.TestCase):
    def test_bara_kandidater_inom_15_min_ar_behoriga(self):
        for minutes, linked in ((0, True), (15, True), (16, False), (-15, True), (-16, False)):
            start = f"2026-09-26T14:{minutes:02d}:00Z" if minutes >= 0 else \
                f"2026-09-26T13:{60 + minutes:02d}:00Z"
            with self.subTest(minutes=minutes):
                h = hit("Plymouth", "Burton", [{**PLYMOUTH, "start": start}])
                self.assertEqual(linked, h is not None)

    def test_kand_svs_avspark_men_okand_kandidat_ar_inte_behorig(self):
        for start in (None, "", "trasig-tid"):
            self.assertIsNone(hit("Brighton", "Leeds", [row("x", "Brighton", "Leeds United", start)]))

    def test_svs_avspark_saknas_ger_v4_vagen(self):
        # Utan SvS-avspark: v4 oförändrad, alltså inga delnamn och ingen nivå A–F.
        self.assertIsNone(hit("Plymouth", "Burton", [PLYMOUTH], start=None))
        h = hit("Brighton", "Leeds", [row("x", "Brighton", "Leeds United", "2026-09-26T14:00:00Z")],
                start=None)
        self.assertEqual(("x", "v4"), (h["id"], h["match_tier"]))
        # v4:s tvetydighetsvakt räknar hela indexet, även ett dygn bort.
        first = row("a", "Inter", "Lazio", "2026-09-15T18:00:00Z")
        second = row("b", "Inter", "Lazio", "2026-09-16T18:00:00Z")
        diag = {}
        self.assertIsNone(hit("Inter", "Lazio", [first, second], start=None, diag=diag))
        self.assertEqual(("ambiguous", 2), (diag["reason"], diag["qualifying_candidates"]))


class NivaTests(unittest.TestCase):
    def test_tva_kandidater_pa_samma_niva_och_avspark_ar_tvetydigt(self):
        twin = {**SWINDON, "id": "twin", "start": "2026-09-26T14:10:00Z"}
        for index in ([SWINDON, twin], [twin, SWINDON]):
            diag = {}
            self.assertIsNone(hit("Swindon", "Accrington", index, diag=diag))
            self.assertEqual(("ambiguous", 2, "C"),
                             (diag["reason"], diag["qualifying_candidates"], diag["qualifying_tier"]))
        # Två orienteringar på samma nivå är också tvetydigt.
        mirrored = row("m", "Burton Albion", "Plymouth Argyle", "2026-09-26T14:00:00Z")
        diag = {}
        self.assertIsNone(hit("Plymouth", "Burton", [PLYMOUTH, mirrored], diag=diag))
        self.assertEqual("ambiguous", diag["reason"])

    def test_lagre_niva_blockerar_aldrig_en_hogre(self):
        exact = row("exakt", "Plymouth", "Burton", "2026-09-26T14:00:00Z")
        for index in ([PLYMOUTH, exact], [exact, PLYMOUTH]):
            h = hit("Plymouth", "Burton", index)
            self.assertEqual(("exakt", "A"), (h["id"], h["match_tier"]))
        # B slår C, C slår F.
        b_row = row("b", "Plymouth Argyle", "Burton", "2026-09-26T14:00:00Z")
        self.assertEqual("B", hit("Plymouth", "Burton", [PLYMOUTH, b_row])["match_tier"])
        f_row = row("f", "Plymuoth", "Burtno", "2026-09-26T14:00:00Z")
        self.assertEqual("F", hit("Plymuoth", "Burton", [f_row])["match_tier"])
        self.assertEqual("C", hit("Plymouth", "Burton", [f_row, PLYMOUTH])["match_tier"])


class LandslagTests(unittest.TestCase):
    def test_england_spanien_lankar_ratt_trots_finland_spain_27_h_bort(self):
        for index in ([ENGLAND_SPAIN, FINLAND_SPAIN], [FINLAND_SPAIN, ENGLAND_SPAIN]):
            h = hit("England", "Spanien", index, SVS_ENG_ESP, "ENG", "ESP")
            self.assertEqual(("1636346499", "A"), (h["id"], h["match_tier"]))

    def test_england_spanien_lankar_ingenting_nar_ratt_rad_saknas(self):
        diag = {}
        self.assertIsNone(hit("England", "Spanien", [FINLAND_SPAIN], SVS_ENG_ESP, "ENG", "ESP", diag))
        self.assertEqual(("name_mismatch", "Finland"), (diag["reason"], diag["cand_home"]))
        # Även en omärkt U21-rad med samma avspark: England~Finland är olika länder.
        same_time = {**FINLAND_SPAIN, "start": ENGLAND_SPAIN["start"]}
        self.assertIsNone(hit("England", "Spanien", [same_time], SVS_ENG_ESP, "ENG", "ESP"))

    def test_turkiet_frankrike_lankar_ratt_trots_ukraine_turkiye(self):
        index = [UKRAINE_TURKIYE, TURKIYE_FRANCE, HUNGARY_UKRAINE]
        h = hit("Turkiet", "Frankrike", index, SVS_TUR_FRA, "TUR", "FRA")
        self.assertEqual(("1636333025", "A"), (h["id"], h["match_tier"]))
        self.assertEqual({"1": 7.87, "X": 4.84, "2": 1.42}, h["odds"])
        # Rätt rad saknas: varken Ukraine–Turkiye dagen efter eller Hungary–
        # Ukraine vid samma avspark (France~Ukraine 0,615) får länkas.
        self.assertIsNone(hit("Turkiet", "Frankrike", [UKRAINE_TURKIYE, HUNGARY_UKRAINE],
                              SVS_TUR_FRA, "TUR", "FRA"))

    def test_tjeckien_kroatien_blir_czechia_croatia(self):
        h = hit("Tjeckien", "Kroatien", [CZECHIA_CROATIA], SVS_ENG_ESP, "CZE", "HRV")
        self.assertEqual(("1636333033", "A"), (h["id"], h["match_tier"]))
        self.assertEqual("Czech Republic", op.english_name("CZE"))   # delad helper orörd

    def test_klubb_med_landskod_far_aldrig_landsnamn(self):
        start = "2026-09-30T21:00:00+02:00"
        nations = row("n", "Spain", "France", "2026-09-30T19:00:00Z")
        self.assertIsNone(hit("Real Madrid", "PSG", [nations], start, "ESP", "FRA"))
        # Vestmannaeyja–Valur → Iceland–Switzerland (historisk felkoppling).
        iceland = row("i", "Iceland", "Switzerland", "2026-09-30T19:00:00Z")
        self.assertIsNone(hit("Vestmannaeyja", "Valur", [iceland], start, "ISL", "ISL"))
        # Bomben 18570: hockeyn Leksand–Almtuna (SWE) fick i v4 Sweden–Poland.
        sweden = row("1636867977", "Sweden", "Poland", "2026-09-28T18:45:00Z")
        self.assertIsNone(hit("Leksand", "Almtuna", [sweden], "2026-09-27T16:30:00+02:00", "SWE", "SWE"))
        self.assertIsNone(hit("Leksand", "Almtuna", [{**sweden, "start": "2026-09-27T14:30:00Z"}],
                              "2026-09-27T16:30:00+02:00", "SWE", "SWE"))

    def test_svenskt_landsnamn_och_sv_s_avkortningar_kanns_igen(self):
        for name, iso in (("Tjeckien", "CZE"), ("Turkiet", "TUR"), ("Nederländerna", "NLD"),
                          ("Nederländ", "NLD"), ("Liechtens", "LIE"), ("Bosnien/H", "BIH"),
                          ("Bosnien & Hercegovina", "BIH"), ("Bosnien o", "BIH"),
                          ("Nordirlan", "NIR"), ("Skottland", "SCO"), ("England", "ENG"),
                          ("St. Lucia", "LCA"), ("St. Kitts & Nevis", "KNA"), ("Moldavien", "MDA"),
                          ("DR Kongo", "COD"), ("Kosovo", "XXK"), ("Sydkorea", "KOR"),
                          ("Sverige U21", "SWE")):
            self.assertTrue(op.pool_name_candidates(name, iso)[1], (name, iso))
        for name, iso in (("Real Madrid", "ESP"), ("Galway", "IRL"), ("Öster", "SWE"),
                          ("Nashville", "USA"), ("Leksand", "SWE"), ("Irland", None),
                          ("Ned", "NLD"), ("Irland", "NIR"), ("Brasil de Pelotas", "BRA")):
            self.assertFalse(op.pool_name_candidates(name, iso)[1], (name, iso))
        self.assertIn("Czechia", op.pool_name_candidates("Tjeckien", "CZE")[0])
        self.assertIn("Turkiye", op.pool_name_candidates("Turkiet", "TUR")[0])
        self.assertIn("Northern Ireland", op.pool_name_candidates("Nordirlan", "NIR")[0])

    def test_landsnamn_matchas_bara_exakt(self):
        # Fuzzy mellan två länder vid samma avspark: aldrig en länk.
        start = "2026-09-30T20:45:00+02:00"
        for svs, iso, pin in (("Österrike", "AUT", "Australia"), ("Island", "ISL", "Ireland"),
                              ("Slovakien", "SVK", "Slovenia"), ("Niger", "NER", "Nigeria")):
            index = [row("x", pin, "Kosovo", "2026-09-30T18:45:00Z")]
            self.assertIsNone(hit(svs, "Kosovo", index, start, iso, "XXK"), svs)
        # Samma land i annan skrivform är exakt.
        index = [row("s", "St. Kitts and Nevis", "Grenada", "2026-09-30T18:45:00Z")]
        self.assertEqual("A", hit("St. Kitts & Nevis", "Grenada", index, start, "KNA", "GRD")["match_tier"])


class AliasOchDiagnostikTests(unittest.TestCase):
    def test_nya_belagda_alias(self):
        cases = (("Nashville", "Toronto FC", "USA",
                  row("1636866540", "Nashville SC", "Toronto FC", "2026-09-27T00:30:00Z"),
                  "2026-09-27T02:30:00+02:00", "A"),
                 ("Once Caldas", "Bucaramanga", "COL",
                  row("1636734323", "Once Caldas", "Atletico Bucaramanga", "2026-09-26T01:15:00Z"),
                  "2026-09-26T03:15:00+02:00", "A"),
                 ("Pereira", "Internacional de Bogota.", "COL",
                  row("1636816733", "Deportivo Pereira", "Inter Bogota", "2026-09-26T21:00:00Z"),
                  "2026-09-26T23:00:00+02:00", "B"))
        for home, away, iso, event, start, tier in cases:
            h = hit(home, away, [event], start, iso, iso)
            self.assertEqual((event["id"], tier), (h["id"], h["match_tier"]), home)
        self.assertEqual(0.0, op.team_sim("Barcelona", "Barcelona SC"))    # SC-regeln kvar

    def test_tvetydiga_kortnamn_far_inget_alias(self):
        start = "2026-09-28T03:10:00+02:00"
        cali = row("1636918709", "Deportivo Cali", "Aguilas Doradas", "2026-09-28T01:10:00Z")
        self.assertIsNone(hit("Deportivo Cali", "Aguilas", [cali], start, "COL", "COL"))
        self.assertEqual(0.0, op.team_sim("Aguilas", "Aguilas Doradas"))

    def test_estudiantes_kontextalias_ar_niva_a_och_fortsatt_bundet(self):
        event = row("1636054672", "Lanus", "Estudiantes de La Plata", "2026-09-22T00:15:00Z")
        h = hit("Lanús", "Estudiantes", [event], "2026-09-22T00:15:00Z", "ARG", "ARG")
        self.assertEqual(("1636054672", "A"), (h["id"], h["match_tier"]))
        caseros = {**event, "id": "c", "away": "Estudiantes de Caseros"}
        self.assertIsNone(hit("Lanús", "Estudiantes", [caseros], "2026-09-22T00:15:00Z", "ARG", "ARG"))

    def test_hornrader_ar_fortfarande_utesparrade(self):
        corners = row("c", "Plymouth Argyle (Corners)", "Burton Albion (Corners)", "2026-09-26T14:00:00Z")
        self.assertIsNone(hit("Plymouth", "Burton", [corners]))

    def test_diagnostiken_bokfors_som_forut(self):
        diag = {}
        wrong = row("w", "Wycombe Wanderers", "Bolton Wanderers", "2026-09-26T14:00:00Z")
        self.assertIsNone(hit("Wigan", "Bolton", [wrong, FINLAND_SPAIN], diag=diag))
        self.assertEqual(("name_mismatch", 0, None),
                         (diag["reason"], diag["qualifying_candidates"], diag["qualifying_tier"]))
        self.assertEqual(("Wycombe Wanderers", "Bolton Wanderers"), (diag["cand_home"], diag["cand_away"]))
        self.assertEqual("pool-name-v6", diag["match_version"])
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(Path(temp) / "t.db")
            try:
                detail = {"svs_home": "Wigan", "svs_away": "Bolton", "match_start": SVS_SAT_1600, **diag}
                self.assertEqual(len(diag["candidates"]),
                                 store.pool_match_diagnostic_record("stryktipset", 1, {1: detail}, SVS_SAT_1600))
            finally:
                store.close()
        # Utanför diagnostikens 36 h-fönster: ingen kandidat och ingen diagnostik.
        far = {}
        self.assertIsNone(hit("Wigan", "Bolton", [wrong], "2026-10-05T16:00:00+02:00", diag=far))
        self.assertEqual({}, far)


if __name__ == "__main__":
    unittest.main()
