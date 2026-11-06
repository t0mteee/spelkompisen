"""pool-reference-v1: exakt Kambi-koppling och WP2-färskhet, aldrig en gissning."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from app import pool_reference
from app.storage import Storage

AT = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class ReferensTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.store.conn.execute(
            "INSERT INTO oddset_matches(id, league, home, away, start, kambi_id, updated_at) "
            "VALUES('svs:111','allsvenskan','Hammarby','Elfsborg','2026-11-06T18:00:00Z','111',?)",
            (_iso(AT),))
        self.draw = NS(matches=[NS(event_number=1, kambi_id="111"),
                                NS(event_number=2, kambi_id="999"),
                                NS(event_number=3, kambi_id=None)])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def save(self, source, minutes_before, odds=(1.45, 5.0, 7.5)):
        self.store.oddset_save_odds("svs:111", source, dict(zip("1X2", odds)),
                                    _iso(AT - dt.timedelta(minutes=minutes_before)))

    def test_farsk_smarkets_och_sbobet_via_kambi_id(self):
        self.save("smarkets", 10)
        self.save("sbobet", 20, (1.40, 4.6, 6.8))
        out = pool_reference.read_for_draw(self.store, self.draw, AT)
        self.assertEqual({1}, set(out))          # 999 saknar Oddset-rad, 3 saknar id
        self.assertEqual({"smarkets", "sbobet"}, set(out[1]))
        sm = out[1]["smarkets"]
        self.assertEqual((1.45, 5.0, 7.5), (sm["1"], sm["X"], sm["2"]))
        self.assertAlmostEqual(1.0, sum(sm["fair"].values()), places=3)
        self.assertEqual("Sm", sm["short"])

    def test_gammalt_pris_och_pris_efter_as_of_visas_inte(self):
        self.save("smarkets", 60)                 # äldre än 45 min
        self.store.oddset_save_odds("svs:111", "sbobet",
                                    {"1": 1.4, "X": 4.6, "2": 6.8},
                                    _iso(AT + dt.timedelta(minutes=5)))
        self.assertEqual({}, pool_reference.read_for_draw(self.store, self.draw, AT))

    def test_pinnacle_raknas_aldrig_som_referens(self):
        self.save("pinnacle", 5)
        self.assertEqual({}, pool_reference.read_for_draw(self.store, self.draw, AT))


if __name__ == "__main__":
    unittest.main()


class OuReferensTests(ReferensTests):
    def save_ou(self, minutes_before, line=2.5, odds=(1.62, 2.61)):
        self.store.oddset_save_market(
            "svs:111", "smarkets", "ou",
            {"O": {"odds": odds[0], "line": line}, "U": {"odds": odds[1], "line": line}},
            _iso(AT - dt.timedelta(minutes=minutes_before)))

    def test_smarkets_ou_huvudlina(self):
        self.save_ou(10)
        out = pool_reference.read_ou_for_draw(self.store, self.draw, AT)
        self.assertEqual({1}, set(out))
        self.assertEqual((2.5, 1.62, 2.61), (out[1]["line"], out[1]["O"], out[1]["U"]))
        self.assertAlmostEqual(1.0, sum(out[1]["fair"].values()), places=3)

    def test_gammal_ou_visas_inte_och_1x2_bar_ingen_lina(self):
        self.save_ou(60)
        self.save("smarkets", 5)
        self.assertEqual({}, pool_reference.read_ou_for_draw(self.store, self.draw, AT))
        self.assertNotIn("line", pool_reference.read_for_draw(
            self.store, self.draw, AT)[1]["smarkets"])
