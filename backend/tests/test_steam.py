"""steam.py: devigade sannolikhetsskift (pp) över 6/24/72 h ur sharp-serien.
🔥-flaggan bygger på det här; modulen hade noll tester."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import steam
from app.storage import Storage

NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.timezone.utc)


def _iso(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class SteamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _sharp(self, event, hours_ago, odds1, oddsx, odds2, product="stryktipset", draw=5000):
        at = _iso(NOW - dt.timedelta(hours=hours_ago))
        for sign, odds in (("1", odds1), ("X", oddsx), ("2", odds2)):
            self.store.conn.execute(
                "INSERT INTO sharp_snapshots(product, draw_number, event_number, sign, odds, fetched_at) "
                "VALUES (?,?,?,?,?,?)", (product, draw, event, sign, odds, at))
        self.store.conn.commit()

    def test_skift_i_procentenheter_med_tecken_och_fonster(self):
        # Hemmalaget går från 2,00 till 1,70 på 30 timmar: pengar på 1:an.
        self._sharp(1, 30, 2.00, 3.50, 3.60)
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        rows = {(r["event_number"], r["sign"]): r
                for r in steam.steam_table(self.store, "stryktipset", 5000)}
        one, two = rows[(1, "1")], rows[(1, "2")]
        self.assertGreater(one["primary"], 0)
        self.assertLess(two["primary"], 0)
        # 6h- och 24h-fönstret ser samma äldre mätning; 72h når före serien.
        self.assertEqual(one["pp"]["6"], one["pp"]["24"])
        self.assertIsNone(one["pp"]["72"])
        # Devigade sannolikheter summerar till 1 — skiften därmed till 0.
        self.assertAlmostEqual(0.0, sum(r["primary"] for r in rows.values()), places=1)
        self.assertAlmostEqual(1.0, sum(r["p_now"] for r in rows.values()), places=3)

    def test_sorteras_pa_storsta_skift(self):
        self._sharp(1, 30, 2.00, 3.50, 3.60)
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        self._sharp(2, 30, 2.50, 3.20, 2.80)
        self._sharp(2, 0, 2.45, 3.20, 2.85)   # nästan stilla
        rows = steam.steam_table(self.store, "stryktipset", 5000)
        self.assertEqual(1, rows[0]["event_number"])
        self.assertEqual([abs(r["primary"]) for r in rows],
                         sorted((abs(r["primary"]) for r in rows), reverse=True))

    def test_match_utan_alla_tre_tecken_hoppas_over(self):
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        self.store.conn.execute(
            "INSERT INTO sharp_snapshots(product, draw_number, event_number, sign, odds, fetched_at) "
            "VALUES ('stryktipset',5000,2,'1',1.5,?)", (_iso(NOW),))
        self.store.conn.commit()
        rows = steam.steam_table(self.store, "stryktipset", 5000)
        self.assertEqual({1}, {r["event_number"] for r in rows})

    def test_tom_omgang(self):
        self.assertEqual([], steam.steam_table(self.store, "stryktipset", 5000))
        self.assertEqual({}, steam.movement_with_steam(self.store, "stryktipset", 5000))

    def test_movement_with_steam_bar_steam_pp(self):
        self._sharp(1, 30, 2.00, 3.50, 3.60)
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        merged = steam.movement_with_steam(self.store, "stryktipset", 5000)
        self.assertIn((1, "1"), merged)
        self.assertGreater(merged[(1, "1")]["steam_pp"], 0)
        self.assertLess(merged[(1, "2")]["steam_pp"], 0)

    def _svs(self, event, hours_ago, odds1, streck1=40, product="stryktipset", draw=5000):
        at = _iso(NOW - dt.timedelta(hours=hours_ago))
        for sign, odds, streck in (("1", odds1, streck1), ("X", 3.40, 30), ("2", 3.60, 30)):
            self.store.conn.execute(
                "INSERT INTO snapshots(product, draw_number, event_number, sign, odds, "
                "start_odds, streck, fetched_at) VALUES (?,?,?,?,?,?,?,?)",
                (product, draw, event, sign, odds, odds, streck, at))
        self.store.conn.commit()

    def test_inaktuell_sharp_serie_ersatts_av_svs_serien_utan_steam(self):
        """pool-sharp-freshness-v1: en sharp-serie som stannade när länken
        tappades får inte presenteras som aktuell rörelse."""
        for event in (1, 2):
            self._sharp(event, 30, 2.00, 3.50, 3.60)
            self._sharp(event, 0, 1.70, 3.80, 4.50)
            self._svs(event, 30, 2.10)
            self._svs(event, 1, 1.95)
        before = steam.movement_with_steam(self.store, "stryktipset", 5000)
        merged = steam.movement_with_steam(self.store, "stryktipset", 5000,
                                           stale={2: {"reason": "link_lost"}})
        # Match 1 orörd: sharp-serien och steam precis som utan regeln.
        self.assertEqual(before[(1, "1")], merged[(1, "1")])
        self.assertEqual((2.00, 1.70), (merged[(1, "1")]["first"], merged[(1, "1")]["last"]))
        # Match 2: SvS-oddsens serie, inget devigat steam-skift.
        self.assertEqual((2.10, 1.95), (merged[(2, "1")]["first"], merged[(2, "1")]["last"]))
        self.assertNotIn("steam_pp", merged[(2, "1")])
        self.assertEqual((40, 40), (merged[(2, "1")]["streck_first"],
                                    merged[(2, "1")]["streck_last"]))

    def test_alla_sharp_inaktuella_ger_samma_svs_fallback_som_utan_sharp(self):
        self._sharp(1, 30, 2.00, 3.50, 3.60)
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        self._svs(1, 30, 2.10)
        self._svs(1, 1, 1.95)
        self._svs(2, 30, 3.00)
        merged = steam.movement_with_steam(self.store, "stryktipset", 5000, stale=[1])
        self.assertEqual(2.10, merged[(1, "1")]["first"])
        self.assertEqual(3.00, merged[(2, "1")]["first"])
        self.assertFalse(any("steam_pp" in entry for entry in merged.values()))

    def test_steam_tabellen_visar_inte_inaktuella_matcher_som_nu(self):
        self._sharp(1, 30, 2.00, 3.50, 3.60)
        self._sharp(1, 0, 1.70, 3.80, 4.50)
        self._sharp(2, 30, 2.50, 3.20, 2.80)
        self._sharp(2, 0, 2.20, 3.20, 3.20)
        rows = steam.steam_table(self.store, "stryktipset", 5000, exclude={2: {}})
        self.assertEqual({1}, {r["event_number"] for r in rows})
        self.assertEqual({1, 2}, {r["event_number"] for r in
                                  steam.steam_table(self.store, "stryktipset", 5000)})
