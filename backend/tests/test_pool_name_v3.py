import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import odds_provider as op, pinnacle
from app.storage import Storage
from scripts.pool_tackning_rapport import _load_oddset, _replay

START = "2026-09-19T14:00:00Z"


def event(home, away):
    return dict(home=home, away=away, start=START,
                odds={"1": 2, "X": 3.4, "2": 3.5})


class PoolNameV3Tests(unittest.TestCase):
    def test_belagda_par_fran_4971(self):
        for a, b in (("Coventry", "Coventry City"), ("Ipswich", "Ipswich Town"),
                     ("Newcastle", "Newcastle United"), ("Derby", "Derby County"),
                     ("Lincoln", "Lincoln City"), ("Swansea", "Swansea City"),
                     ("Blackburn", "Blackburn Rovers"), ("Preston", "Preston North End")):
            self.assertEqual(1, op.team_sim(a, b), (a, b))
            self.assertEqual(0, op.team_sim(a, b + " U21"))

    def test_hornrader_ger_aldrig_malodds(self):
        for suffix in ("Corners", "Cards"):
            name = "Portsmouth (" + suffix + ")"
            self.assertIsNone(pinnacle.match_index(name, "Blackburn", None, None,
                                                  [event(name, "Blackburn")], START))

    def test_audit_visar_fem_ledtradar_utan_att_godkanna_delnamn(self):
        games = [event("Inter Miami", "Lazio")]
        games += [event("Internacional" + str(i), "Lazio") for i in range(6)]
        diag = {}
        self.assertIsNone(pinnacle.match_index("Inter", "Lazio", None, None, games, START, diag))
        self.assertEqual(5, len(diag["candidates"]))
        self.assertTrue(any(d["cand_home"] == "Inter Miami" for d in diag["candidates"]))
        self.assertEqual(0, next(d["side_home"] for d in diag["candidates"]
                                if d["cand_home"] == "Inter Miami"))
        with tempfile.TemporaryDirectory() as temp:
            store = Storage(Path(temp) / "test.db")
            try:
                detail = {"svs_home": "Inter", "svs_away": "Lazio", **diag}
                store.pool_match_diagnostic_record("stryktipset", 1, {1: detail}, START)
                self.assertEqual(5, store.conn.execute("SELECT COUNT(*) FROM pool_match_diagnostic").fetchone()[0])
            finally:
                store.close()

    def test_rapport_ser_pinnacle_lankad_till_svs_id(self):
        c = sqlite3.connect(":memory:")
        self.addCleanup(c.close)
        c.execute("CREATE TABLE oddset_matches(id,league,home,away,start,kambi_id,pinnacle_id)")
        c.execute("CREATE TABLE oddset_odds(match_id,source,fetched_at)")
        c.execute("INSERT INTO oddset_matches VALUES('svs:1','test','Portsmouth','Blackburn',?,'1','2')", (START,))
        c.execute("INSERT INTO oddset_odds VALUES('svs:1','pinnacle','2026-09-18T14:00:00Z')")
        _, rows = _load_oddset(c)
        self.assertEqual(1, len(rows))
        self.assertIn("namnform ej sparad", _replay(pinnacle, rows, "Portsmouth", "Blackburn", START, START)["utfall"])

    def test_hornrad_ar_inte_bevis_i_rapport(self):
        row = (dt.datetime.fromisoformat(START.replace("Z", "+00:00")),
               "Portsmouth (Corners)", "Blackburn (Corners)", "test", None, START)
        self.assertEqual("ingen Pinnacle-rad hos Oddset",
                         _replay(pinnacle, [row], "Portsmouth", "Blackburn", START, START)["utfall"])
