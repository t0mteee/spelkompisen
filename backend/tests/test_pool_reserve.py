import datetime as dt
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import pool_reserve as r
from scripts.migrera_pool_reserve import migrate


class ReserveTests(unittest.TestCase):
    now = dt.datetime(2026,9,21,15,tzinfo=dt.timezone.utc)
    start = "2026-09-21T17:00:00Z"

    def payload(self):
        return {"events":[{"id":1,"start":self.start,"sport":"FOOTBALL",
                           "state":"NOT_STARTED","homeName":"Home","awayName":"Away"}],
                "betOffers":[{"eventId":1,"criterion":{"label":"Asian totalt",
                    "occurrenceType":"GOALS","lifetime":"FULL_TIME"},"tags":["MAIN_LINE"],
                    "outcomes":[{"type":"OT_OVER","status":"OPEN","line":2250,"odds":1910},
                                {"type":"OT_UNDER","status":"OPEN","line":2250,"odds":1840}]}]}

    def test_exakt_provider_id_fulltid_och_oppet_par(self):
        q=r.parse_quote(self.payload(),"1",self.start,self.now)
        self.assertEqual(("available",2.25,1.91,1.84),
                         (q["status"],q["line"],q["over_odds"],q["under_odds"]))
        self.assertEqual("identity_unverified",r.parse_quote(self.payload(),"2",self.start,self.now)["status"])

    def test_status_tid_och_lina_faller_stangt(self):
        for key,value in (("start",None),("start","trasig"),("state","STARTED"),("sport","HOCKEY")):
            data=self.payload(); data["events"][0][key]=value
            self.assertEqual("identity_unverified",r.parse_quote(data,1,self.start,self.now)["status"])
        for key,value in (("status","SUSPENDED"),("line",2500),("odds",0),("odds",float('nan'))):
            data=self.payload();data["betOffers"][0]["outcomes"][1][key]=value
            self.assertEqual("no_market",r.parse_quote(data,1,self.start,self.now)["status"])
        data=self.payload();data["betOffers"][0]["criterion"]["lifetime"]="FIRST_HALF"
        self.assertEqual("no_market",r.parse_quote(data,1,self.start,self.now)["status"])

    def test_schema_backup_ingen_bakfyllning(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'db';backup=Path(tmp)/'backup'
            with closing(sqlite3.connect(db)) as c:c.execute('CREATE TABLE old_data(id INTEGER)')
            result=migrate(db,backup)
            self.assertEqual("ok",result["integrity_check"])
            with closing(sqlite3.connect(backup)) as c:
                self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='pool_reserve_quote'").fetchone())
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(0,c.execute('SELECT count(*) FROM pool_reserve_quote').fetchone()[0])

    def test_kallfel_ar_inte_franvaro_och_gamla_priser_ar_inte_farska(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row;conn.executescript(r.SCHEMA)
        self.addCleanup(conn.close)
        store=SimpleNamespace(conn=conn)
        def insert(status, checked):
            conn.execute('INSERT INTO pool_reserve_quote VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('topptipset',1,1,r.SOURCE,'1',checked,checked,status,2.25,1.9,1.9,
                 self.start,'Home','Away',r.VERSION))
        insert('available','2026-09-21T14:50:00+00:00')
        insert('source_error','2026-09-21T14:55:00+00:00')
        q=r.read_for_draw(store,'topptipset',1,self.now)[1]
        self.assertTrue(q['available']);self.assertTrue(q['source_error']);self.assertFalse(q['used_by_builder'])
        self.assertFalse(r.read_for_draw(store,'topptipset',1,self.now+dt.timedelta(hours=1))[1]['available'])
        insert('no_market','2026-09-21T14:59:00+00:00')
        self.assertFalse(r.read_for_draw(store,'topptipset',1,self.now)[1]['available'])

    def test_budget_cooldown_och_separat_journal(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row;conn.executescript(r.SCHEMA)
        self.addCleanup(conn.close)
        store=SimpleNamespace(conn=conn,get_sharp=lambda *args:{})
        start=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat()
        draw=SimpleNamespace(state='Open',draw_number=1,matches=[SimpleNamespace(
            event_number=i,kambi_id=str(i),match_start=start,cancelled=False) for i in range(1,7)])
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        quote={'status':'not_listed','checked_at':now,'observed_at':now}
        with patch.object(r,'fetch_quote',return_value=quote) as fetch:
            varv=SimpleNamespace()
            self.assertEqual(3,r.collect(store,'topptipset',draw,varv))
            self.assertEqual(0,r.collect(store,'topptipset',draw,varv))
            self.assertEqual(3,fetch.call_count)
            self.assertEqual(3,r.collect(store,'topptipsetextra',draw,varv))
            self.assertEqual(3,fetch.call_count)
            self.assertEqual(now,conn.execute("SELECT observed_at FROM pool_reserve_quote WHERE product='topptipsetextra' LIMIT 1").fetchone()[0])
            self.assertEqual(3,r.collect(store,'topptipset',draw,SimpleNamespace()))
            self.assertEqual(0,r.collect(store,'topptipset',draw,SimpleNamespace()))

    def test_aldsta_matcher_prioriteras_nar_basvarvet_ar_langre_an_cooldown(self):
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row;conn.executescript(r.SCHEMA)
        self.addCleanup(conn.close)
        store=SimpleNamespace(conn=conn,get_sharp=lambda *args:{})
        now=dt.datetime.now(dt.timezone.utc)
        start=(now+dt.timedelta(days=1)).isoformat()
        draw=SimpleNamespace(state='Open',draw_number=1,matches=[SimpleNamespace(
            event_number=i,kambi_id=str(i),match_start=start,cancelled=False) for i in range(1,7)])
        old=(now-dt.timedelta(minutes=31)).isoformat()
        with patch.object(r,'fetch_quote',return_value={
                'status':'not_listed','checked_at':old,'observed_at':old}):
            r.collect(store,'topptipset',draw,SimpleNamespace())
        with patch.object(r,'fetch_quote',return_value={
                'status':'not_listed','checked_at':now.isoformat(),'observed_at':now.isoformat()}) as fetch:
            r.collect(store,'topptipset',draw,SimpleNamespace())
            self.assertEqual([4,5,6],[call.args[0].event_number for call in fetch.call_args_list])

    def test_inaktuell_pinnacle_total_haller_inte_reserven_borta(self):
        """pool-sharp-freshness-v1: en gammal eller länktappad Pinnacle-total
        räknas som saknad, annars får matchen aldrig något reservunderlag."""
        from app.storage import Storage
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "db")
            try:
                store.conn.executescript(r.SCHEMA)
                ago = lambda minutes: (self.now - dt.timedelta(minutes=minutes)
                                       ).strftime("%Y-%m-%dT%H:%M:%SZ")
                for event, minutes in ((1, 10), (2, 120), (3, 30)):
                    store.save_sharp("topptipset", 1, [{
                        "event_number": event, "bookmaker": "pinnacle",
                        "odds": {"1": 2.0, "X": 3.4, "2": 3.8},
                        "total": {"line": 2.5, "O": 1.9, "U": 1.9},
                        "confidence": 1.0, "matched": "H - B",
                        "fetched_at": ago(minutes)}])
                store.conn.execute(
                    "INSERT INTO pool_market_capture (product,draw_number,source,"
                    "event_number,fetched_at,status,odds_complete) "
                    "VALUES ('topptipset',1,'sharp',3,?,'ambiguous',0)", (ago(5),))
                store.conn.commit()
                draw = SimpleNamespace(state='Open', draw_number=1, matches=[
                    SimpleNamespace(event_number=i, kambi_id=str(i),
                                    match_start=self.start, cancelled=False)
                    for i in (1, 2, 3)])
                quote = {'status': 'not_listed', 'checked_at': self.now.isoformat(),
                         'observed_at': self.now.isoformat()}
                with patch.object(r, 'fetch_quote', return_value=quote) as fetch:
                    r.collect(store, 'topptipset', draw, SimpleNamespace(), now=self.now)
                self.assertEqual([2, 3], sorted(
                    call.args[0].event_number for call in fetch.call_args_list))
            finally:
                store.close()
