"""GET /api/spelai/pool/forslag/{id}: andelar, matchnamn och jämförelser."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, Klocka, draw_fixture, giltigt_svar, lagg_till_omgang, ny_store  # noqa: E402

from app.spelai import api, frysning, indata, schemalaggare  # noqa: E402


class ForslagDetaljTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _frys(self):
        close = START + dt.timedelta(minutes=35)
        lagg_till_omgang(self.store, "stryktipset", 5000, close)
        draw = draw_fixture(close, START)
        clock = Klocka(START)
        indata.capture_due(self.store, "stryktipset", draw, {}, {}, jackpot=None,
                           jackpot_source="missing", now=START, sharp_stale=None)
        schemalaggare.tick(self.store, runner=giltigt_svar, clock=clock, sender=None,
                           topic_name=None, code_version="test")
        return {(r[0], r[1]): r[2] for r in self.store.conn.execute(
            "SELECT level_kr, role, id FROM spelai_pool_proposal WHERE horizon='30m' "
            "AND status='fryst'")}

    def test_detalj_med_andelar_och_jamforelse(self):
        ids = self._frys()
        self.assertIn((256, "agent"), ids)
        detalj = api.forslag(self.store.conn, ids[(256, "agent")])
        self.assertEqual(13, len(detalj["matcher"]))
        self.assertEqual("H1 – B1", detalj["matcher"][0]["match"])
        self.assertEqual(13, len(detalj["andelar"]))
        for andel in detalj["andelar"]:
            self.assertAlmostEqual(1.0, sum(andel.values()), places=6)
        self.assertIn("mot_motrollen", detalj["jamforelse"])
        self.assertNotIn("rader_lista", detalj)
        med = api.forslag(self.store.conn, ids[(256, "agent")], med_rader=True)
        self.assertEqual(detalj["rader"], len(med["rader_lista"]))

    def test_msystem_andelar_ur_tecknen(self):
        ids = self._frys()
        key = (39366, "standard")
        self.assertIn(key, ids)
        detalj = api.forslag(self.store.conn, ids[key])
        spikar = [a for a in detalj["andelar"] if max(a.values()) == 1.0]
        self.assertEqual(3, len(spikar))

    def test_okant_id_ger_none(self):
        self._frys()
        self.assertIsNone(api.forslag(self.store.conn, 999999))


if __name__ == "__main__":
    unittest.main()
