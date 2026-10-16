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

    def _forslag(self, frozen, close, statuses=("fryst", "fryst"), levels=(256, 512),
                 product="stryktipset", draw_number=4973, horizon="30m"):
        for level in levels:
            for role, status in zip(("agent", "standard"), statuses):
                self.conn.execute(
                    "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                    "horizon, role, status, rows_text, reg_close_time, frozen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (product, draw_number, level, horizon, role, status,
                     "1X21X21X21X21", close.isoformat(), frozen.isoformat()))
        self.conn.commit()

    def _nycklar(self):
        return sorted(k["key"] for k in notis.kandidater(self.conn, now=DAG))

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
        self.assertEqual("http://x:5176/", link)     # poolförslag: agentens app
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

    def test_sexh_aviseras_bara_missat_eller_ogiltigt(self):
        """Beslut koordinatorn-2026-10-16-notiser-pool, val 0."""
        close = DAG + dt.timedelta(hours=6)
        self._forslag(DAG, close, horizon="6h", draw_number=1)
        self._forslag(DAG, close, horizon="6h", draw_number=2,
                      statuses=("ogiltigt", "fryst"))
        self._forslag(DAG, close, horizon="6h", draw_number=3,
                      statuses=("missat", "missat"))
        self.assertEqual(["missat:stryktipset:3:6h", "pool:stryktipset:2:6h"],
                         self._nycklar())
        notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name="t")
        self.assertEqual({"Poolförslag missat", "Poolförslag klart"},
                         {t for _, t, _, _ in self.sent})
        self.assertIn("ogiltigt på 2 nivåer", self.sent[0][2] + self.sent[1][2])

    def test_topptipset_bara_med_spelstopp_12_till_22_svensk_tid(self):
        # 2026-10-04 är sommartid: svensk tid = UTC+2
        def stopp(h, m):
            return dt.datetime(2026, 10, 4, h - 2, m, tzinfo=UTC)
        fall = [("topptipset", 1, stopp(11, 59)), ("topptipset", 2, stopp(12, 0)),
                ("topptipsetextra", 3, stopp(22, 0)),
                ("topptipsetstryk", 4, stopp(22, 1)),
                ("stryktipset", 5, stopp(23, 30)), ("europatipset", 6, stopp(9, 0))]
        for product, nr, close in fall:
            self._forslag(DAG, close, product=product, draw_number=nr, levels=(256,))
        # ogiltigt och missat aviseras även utanför fönstret
        self._forslag(DAG, stopp(23, 0), product="topptipset", draw_number=7,
                      levels=(256,), statuses=("ogiltigt", "fryst"))
        self._forslag(DAG, stopp(8, 0), product="topptipsetextra", draw_number=8,
                      levels=(256,), statuses=("missat", "missat"))
        self.assertEqual(["missat:topptipsetextra:8:30m", "pool:europatipset:6:30m",
                          "pool:stryktipset:5:30m", "pool:topptipset:2:30m",
                          "pool:topptipset:7:30m", "pool:topptipsetextra:3:30m"],
                         self._nycklar())

    def test_aviseras(self):
        kl = dt.datetime(2026, 10, 4, 10, 0, 30, tzinfo=UTC)   # 12:00:30 svensk tid
        self.assertTrue(notis.aviseras("topptipset", "30m", kl))
        self.assertTrue(notis.aviseras("topptipset", "30m",
                                       kl.replace(hour=20, second=59)))  # 22:00:59
        self.assertFalse(notis.aviseras("topptipset", "30m", kl.replace(hour=20, minute=1)))
        self.assertFalse(notis.aviseras("topptipset", "30m", None))
        self.assertFalse(notis.aviseras("stryktipset", "6h", kl))
        self.assertTrue(notis.aviseras("stryktipset", "30m", kl.replace(hour=22)))

    def test_lank_for_beslut_oppnar_beslutssidan_ovrigt_agentens_app(self):
        bas = "http://100.106.151.124:5175/"
        self.assertEqual("http://100.106.151.124:5175/#/beslut/28",
                         notis.lank_for(bas, {"kind": "beslut", "inbox_id": 28}))
        self.assertEqual("http://100.106.151.124:5175/#/beslut/28",
                         notis.lank_for(bas, {"kind": "genomforande", "inbox_id": 28}))
        self.assertEqual("http://100.106.151.124:5175/#/beslut",
                         notis.lank_for(bas, {"kind": "genomforande", "inbox_id": None}))
        self.assertEqual("http://100.106.151.124:5176/",
                         notis.lank_for(bas, {"kind": "pool"}))
        self.assertEqual("http://100.106.151.124:5176/",
                         notis.lank_for(bas, {"kind": "roll_klar"}))
        # sökväg/hash i basen ignoreras; ogiltig eller saknad bas ger ingen länk
        self.assertEqual("http://h:5175/#/beslut/3",
                         notis.lank_for("http://h:5175/#/idag", {"kind": "beslut",
                                                                 "inbox_id": 3}))
        for bas in (None, "", "macbook:5175", "ftp://h/", "http://[::1"):
            self.assertIsNone(notis.lank_for(bas, {"kind": "beslut", "inbox_id": 1}))

    def test_beslutsnotisen_lankar_till_posten(self):
        self.conn.execute(
            "INSERT INTO spelai_inbox (external_id, typ, kalla, rubrik, varfor, "
            "alternativ_json, payload_hash, created_at) VALUES ('b-1', 'beslut', "
            "'Koordinatorn', 'Rubrik', 'för att', '[{\"text\": \"a\"}]', 'h', ?)",
            (DAG.strftime("%Y-%m-%dT%H:%M:%SZ"),))
        self.conn.commit()
        inbox_id = self.conn.execute("SELECT id FROM spelai_inbox").fetchone()[0]
        notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name="t",
                     link="http://h:5175/")
        self.assertEqual([f"http://h:5175/#/beslut/{inbox_id}"], [s[3] for s in self.sent])

    def test_testnotis_bokfors_med_adressen(self):
        rep = notis.testnotis(self.conn, now=DAG, sender=self.sender, topic_name="t",
                              link="http://h:5175/", inbox_id=28)
        self.assertTrue(rep["skickad"])
        self.assertEqual(("Testnotis", "http://h:5175/#/beslut/28"),
                         (self.sent[0][1], self.sent[0][3]))
        utan = notis.testnotis(self.conn, now=DAG, sender=self.sender, topic_name=None,
                               link="http://h:5175/")
        self.assertEqual((False, "ämne saknas"), (utan["skickad"], utan["orsak"]))
        self.assertEqual(1, len(self.sent))
        import json
        rader = [json.loads(d) for (d,) in self.conn.execute(
            "SELECT detail_json FROM spelai_event WHERE kind='notis_test' ORDER BY id")]
        self.assertEqual(["http://h:5175/#/beslut/28", "http://h:5175/#/beslut"],
                         [r["lank"] for r in rader])

    def test_tysta_timmar(self):
        self.assertTrue(notis.tysta_timmar(NATT))
        self.assertFalse(notis.tysta_timmar(DAG))
        self.assertTrue(notis.tysta_timmar(dt.datetime(2026, 10, 3, 21, 0, tzinfo=UTC)))
        self.assertFalse(notis.tysta_timmar(dt.datetime(2026, 10, 3, 5, 0, tzinfo=UTC)))


class RollNotisTests(unittest.TestCase):
    """Fas F: roll_klar/roll_fel/kvot_slut (app/spelai/roller.py) blir notiser."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn
        self.sent = []

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def sender(self, topic, title, message, link):
        self.sent.append((title, message))
        return True

    def handelse(self, kind, ref, detail, at, dedup):
        import json
        self.conn.execute(
            "INSERT INTO spelai_event (at, kind, ref, detail_json, dedup_key) "
            "VALUES (?,?,?,?,?)", (at.strftime("%Y-%m-%dT%H:%M:%SZ"), kind, ref,
                                   json.dumps(detail), dedup))
        self.conn.commit()

    def test_klar_fel_och_kvot_slut(self):
        self.handelse("roll_klar", "morgonrunda:2026-10-03",
                      {"typ": "morgonrunda", "status": "klar",
                       "sammanfattning": "Två larm åtgärdade. 1X21X21X21X21 " + "x" * 300},
                      DAG, "roll_slut:morgonrunda:2026-10-03")
        self.handelse("roll_fel", "forskningspass:2026-10-03",
                      {"typ": "forskningspass", "status": "timeout"}, DAG,
                      "roll_slut:forskningspass:2026-10-03")
        self.handelse("roll_fel", "larm:jobb_nere:pool",
                      {"typ": "larm", "status": "fel"}, DAG,
                      "roll_slut:larm:jobb_nere:pool:2026-10-03T12:00:00Z")
        self.handelse("kvot_slut", "2026-10-03", {"tak": 8, "anvanda": 8}, DAG,
                      "kvot_slut:2026-10-03")
        rep = notis.skicka(self.conn, now=DAG, sender=self.sender, topic_name="t")
        self.assertEqual(4, rep["skickade"])
        by_title = dict(self.sent)
        klar = by_title["Agenten: morgonrunda klar"]
        self.assertTrue(klar.startswith("Två larm åtgärdade."))
        self.assertLessEqual(len(klar), notis.SAMMANFATTNING_MAX)
        self.assertNotIn("1X21X21X21X21", klar)
        self.assertIn("nådde tidsgränsen", by_title["Agenten: forskningspass avbröts"])
        self.assertIn("misslyckades", by_title["Agenten: larmkörning misslyckades"])
        self.assertIn("8 av 8", by_title["Agenten: dagens tak nått"])
        # dedup: inget skickas igen
        self.assertEqual(0, notis.skicka(self.conn, now=DAG, sender=self.sender,
                                         topic_name="t")["skickade"])

    def test_tysta_timmar_skjuter_upp_rollnotisen(self):
        self.handelse("roll_klar", "forskningspass:2026-10-03",
                      {"typ": "forskningspass", "sammanfattning": "Klart."}, NATT,
                      "roll_slut:forskningspass:2026-10-03")
        rep = notis.skicka(self.conn, now=NATT, sender=self.sender, topic_name="t")
        self.assertEqual((0, 1), (rep["skickade"], rep["uppskjutna"]))
        morgon = NATT + dt.timedelta(hours=7)                    # 07:30 svensk tid
        self.assertEqual(1, notis.skicka(self.conn, now=morgon, sender=self.sender,
                                         topic_name="t")["skickade"])
        self.assertEqual("Agenten: forskningspass klar", self.sent[0][0])


if __name__ == "__main__":
    unittest.main()
