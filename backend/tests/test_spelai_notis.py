"""Notiser: samlade per spel och tidpunkt, tysta timmar, dedup, aldrig rader."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app.spelai import notis  # noqa: E402

UTC = dt.timezone.utc
DAG = dt.datetime(2026, 10, 3, 13, 30, tzinfo=UTC)       # 15:30 svensk tid
NATT = dt.datetime(2026, 10, 3, 22, 30, tzinfo=UTC)      # 00:30 svensk tid


class NotisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn
        self.sent = []

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def sender(self, topic, title, message, link):
        self.sent.append((topic, title, message, link))
        return True

    def _forslag(self, frozen, close, statuses=("fryst", "fryst"), levels=(256, 512)):
        for level in levels:
            for role, status in zip(("agent", "standard"), statuses):
                self.conn.execute(
                    "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                    "horizon, role, status, rows_text, reg_close_time, frozen_at) "
                    "VALUES ('stryktipset', 4973, ?, '30m', ?, ?, ?, ?, ?)",
                    (level, role, status, "1X21X21X21X21", close.isoformat(),
                     frozen.isoformat()))
        self.conn.commit()

    def test_en_samlad_notis_per_spel_och_tidpunkt_utan_rader(self):
        self._forslag(DAG, DAG + dt.timedelta(minutes=30))
        rep = notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name="t",
                           link="http://x")
        self.assertEqual(1, rep["skickade"])
        _topic, title, message, link = self.sent[0]
        self.assertEqual("Poolförslag klart", title)
        self.assertIn("Stryktipset 4973", message)
        self.assertIn("2 nivåer", message)
        self.assertNotIn("1X2", message)
        self.assertEqual("http://x", link)
        # dedup: samma händelse skickas aldrig igen
        self.assertEqual(0, notis.skicka(self.conn, now=DAG, sender=self.sender,
                                         topic_name="t")["skickade"])
        self.assertEqual(1, len(self.sent))

    def test_tysta_timmar_skjuter_upp_men_beslut_med_sista_tid_gar_fram(self):
        self._forslag(NATT, NATT + dt.timedelta(hours=8))
        self.conn.execute(
            "INSERT INTO spelai_inbox (external_id, typ, kalla, rubrik, varfor, "
            "alternativ_json, sista_tid, payload_hash, created_at) VALUES "
            "('b1','beslut','Koordinatorn','Kassaspärr','x','[]',?, 'h', ?)",
            ((NATT + dt.timedelta(hours=2)).isoformat(), NATT.isoformat()))
        self.conn.execute(
            "INSERT INTO spelai_inbox (external_id, typ, kalla, rubrik, varfor, "
            "alternativ_json, sista_tid, payload_hash, created_at) VALUES "
            "('b2','beslut','Koordinatorn','Utan tid','x','[]',NULL,'h', ?)",
            (NATT.isoformat(),))
        self.conn.commit()
        rep = notis.skicka(self.conn, now=NATT, sender=self.sender, topic_name="t")
        self.assertEqual((1, 2), (rep["skickade"], rep["uppskjutna"]))
        self.assertEqual("Nytt beslut", self.sent[0][1])
        morgon = NATT + dt.timedelta(hours=7)            # 07:30 svensk tid
        rep = notis.skicka(self.conn, now=morgon, sender=self.sender, topic_name="t")
        self.assertEqual(2, rep["skickade"])

    def test_utan_amne_bara_handelse_och_passerat_stopp_skickas_inte(self):
        self._forslag(DAG, DAG + dt.timedelta(minutes=30))
        rep = notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name=None)
        self.assertEqual((0, 1), (rep["skickade"], rep["utan_amne"]))
        self.assertEqual([], self.sent)
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_event WHERE kind='notis'").fetchone()[0])

        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp)
        try:
            self.conn = store.conn
            self._forslag(DAG, DAG - dt.timedelta(minutes=1))
            rep = notis.skicka(store.conn, now=DAG, sender=self.sender, topic_name="t")
            self.assertEqual(0, rep["skickade"])
        finally:
            store.close()
            tmp.cleanup()

    def test_missat_far_egen_notis(self):
        self._forslag(DAG, DAG + dt.timedelta(minutes=30), statuses=("missat", "missat"))
        notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name="t")
        self.assertEqual("Poolförslag missat", self.sent[0][1])

    def test_tysta_timmar(self):
        self.assertTrue(notis.tysta_timmar(NATT))
        self.assertFalse(notis.tysta_timmar(DAG))
        self.assertTrue(notis.tysta_timmar(dt.datetime(2026, 10, 3, 21, 0, tzinfo=UTC)))
        self.assertFalse(notis.tysta_timmar(dt.datetime(2026, 10, 3, 5, 0, tzinfo=UTC)))


if __name__ == "__main__":
    unittest.main()
