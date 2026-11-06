"""SBOBET som referenskälla (2026-11-06).

Fixturen är ett verkligt utdrag ur SBOBET:s publika datumsidor: den pågående
matchen Inter San Carlos–CS Cartagines (6/11) och Fredrikstad–Brann (8/11,
02:15 GMT+8 = 7/11 18:15Z).
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset, sbobet
from app.oddset_value import ANCHOR_SOURCES
from app.storage import Storage

FIXTURE = (Path(__file__).parent / "fixtures" / "sbobet_sample.html").read_text()


class ParseTests(unittest.TestCase):
    def test_prematch_tolkas_och_live_hoppas_over(self):
        rows = sbobet.parse_page(FIXTURE)
        self.assertEqual(["Fredrikstad"], [r["home"] for r in rows])
        r = rows[0]
        self.assertEqual(("10687531", 44386, "Brann"), (r["id"], r["league_id"], r["away"]))
        self.assertEqual("2026-11-08T18:15:00Z", r["start"])          # GMT+8 → UTC
        self.assertEqual({"1": 2.497, "X": 3.323, "2": 2.228}, r["odds"])

    def test_handikapp_i_hemmalagets_tecken(self):
        ah = sbobet.parse_page(FIXTURE)[0]["ah"]
        # SBOBET:s lina är vad hemmalaget GER; −0,25 betyder hemma +0,25.
        self.assertEqual([0.0, 0.25], [a["line"] for a in ah])
        self.assertEqual((1.73, 2.12), (ah[1]["H"], ah[1]["A"]))
        self.assertEqual(0.0, sbobet.main_line(ah)["line"])          # mest balanserad

    def test_saknat_block_ar_ett_kallfel(self):
        with self.assertRaises(ValueError):
            sbobet.parse_page("<html>ingen data</html>")
        self.assertEqual([], sbobet.parse_page("onUpdate('od',[1,1,[[2,[]],[],[]]]);"))

    def test_dagspann_i_utc(self):
        self.assertEqual(("2026-11-07T16:00:00Z", "2026-11-08T16:00:00Z"),
                         sbobet.day_span_utc(dt.date(2026, 11, 8)))


class ClientTests(unittest.TestCase):
    def test_vantar_robots_crawl_delay_och_slutar_vid_opublicerad_dag(self):
        sleeps = []
        clock = iter([0.0, 1.0, 5.0, 12.0, 12.0])   # 2:a anropet efter 1 s, 3:e efter 7 s
        client = sbobet.Sbobet(sleep=sleeps.append, clock=lambda: next(clock))
        responses = [mock.Mock(status_code=200, text=FIXTURE, raise_for_status=lambda: None),
                     mock.Mock(status_code=200, text=FIXTURE, raise_for_status=lambda: None),
                     mock.Mock(status_code=302, text="", raise_for_status=lambda: None)]
        with mock.patch.object(client._client, "get", side_effect=responses) as get:
            pages = client.week(dt.date(2026, 11, 7))
        client.close()
        self.assertEqual([True, True, False], [p["published"] for p in pages])
        self.assertEqual(3, get.call_count)                 # inget anrop efter 302
        self.assertEqual([4.0], sleeps)                     # 5 s − 1 s redan gått
        self.assertTrue(get.call_args_list[0].args[0].endswith("/euro/football/2026-11-07"))


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.store.oddset_upsert_match({"id": "m1", "league": "eliteserien",
                                        "home": "Fredrikstad", "away": "SK Brann",
                                        "start": "2026-11-08T18:15:00Z"})
        self.store.oddset_upsert_match({"id": "m2", "league": "eliteserien",
                                        "home": "Viking", "away": "KFUM Oslo",
                                        "start": "2026-11-08T15:59:00Z"})
        self.store.oddset_upsert_match({"id": "m3", "league": "eliteserien",
                                        "home": "Molde", "away": "Bodø/Glimt",
                                        "start": "2026-11-09T17:00:00Z"})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def pages(self, observed="2026-11-06T00:00:00Z"):
        return [{"date": dt.date(2026, 11, 8), "rows": sbobet.parse_page(FIXTURE),
                 "observed_at": observed, "published": True},
                {"date": dt.date(2026, 11, 9), "rows": [], "observed_at": observed,
                 "published": False}]

    def run_collect(self, pages):
        cands = self.store.oddset_matches(since="2026-11-01T00:00:00Z")
        report = {"errors": []}
        return oddset._collect_sbobet(self.store, "eliteserien", pages, cands,
                                      oddset._resolve, report), report

    def test_sparar_1x2_och_huvudlina_med_sidans_tid(self):
        (n, saved), report = self.run_collect(self.pages())
        self.assertEqual((1, 5), (n, saved))
        self.assertEqual([], report["errors"])
        rows = {(r["market"], r["sign"]): (r["line"], r["odds"], r["fetched_at"])
                for r in self.store.conn.execute(
                    "SELECT market, sign, line, odds, fetched_at FROM oddset_odds "
                    "WHERE match_id='m1' AND source='sbobet'")}
        self.assertEqual((None, 2.497, "2026-11-06T00:00:00Z"), rows[("1x2", "1")])
        self.assertEqual((0.0, 2.03, "2026-11-06T00:00:00Z"), rows[("ah", "H")])
        self.assertEqual((0.0, 1.81, "2026-11-06T00:00:00Z"), rows[("ah", "A")])

    def test_franvaro_bara_inom_publicerad_dag(self):
        for match in ("m2", "m3"):
            self.store.oddset_save_odds(match, "sbobet", {"1": 2, "X": 3, "2": 4},
                                        "2026-11-05T00:00:00Z")
        self.run_collect(self.pages())
        avail = dict(self.store.conn.execute(
            "SELECT match_id, MAX(available) FROM oddset_odds WHERE source='sbobet' "
            "AND market='1x2' GROUP BY match_id").fetchall())
        self.assertEqual(0, avail["m2"])   # 8/11 publicerad, matchen saknas ⇒ borta
        self.assertEqual(1, avail["m3"])   # 9/11 opublicerad ⇒ ingen observation

    def test_startad_match_sparas_aldrig(self):
        (n, saved), _ = self.run_collect(self.pages(observed="2026-11-08T18:16:00Z"))
        self.assertEqual((0, 0), (n, saved))

    def test_spärrad_som_bok_och_okand_liga_far_inget(self):
        self.assertIn("sbobet", ANCHOR_SOURCES)
        self.assertNotIn("bolivian_primera", sbobet.LEAGUE_IDS)
        self.assertEqual(frozenset({44386}), sbobet.LEAGUE_IDS["eliteserien"])


if __name__ == "__main__":
    unittest.main()
