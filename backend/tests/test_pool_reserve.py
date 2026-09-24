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


def varv_run(store, product, draw, varv, now=None):
    """Registrera en produkt och kör kön, som ett basvarv med EN produkt."""
    r.register(store, product, draw, varv, now=now)
    return r.run_queue(store, varv, now=now)


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
            self.assertEqual(3,varv_run(store,'topptipset',draw,varv)["saved"])
            self.assertEqual(0,varv_run(store,'topptipset',draw,varv)["saved"])
            self.assertEqual(3,fetch.call_count)
            self.assertEqual(3,varv_run(store,'topptipsetextra',draw,varv)["saved"])
            self.assertEqual(3,fetch.call_count)
            self.assertEqual(now,conn.execute("SELECT observed_at FROM pool_reserve_quote WHERE product='topptipsetextra' LIMIT 1").fetchone()[0])
            self.assertEqual(3,varv_run(store,'topptipset',draw,SimpleNamespace())["saved"])
            self.assertEqual(0,varv_run(store,'topptipset',draw,SimpleNamespace())["saved"])

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
            varv_run(store,'topptipset',draw,SimpleNamespace())
        with patch.object(r,'fetch_quote',return_value={
                'status':'not_listed','checked_at':now.isoformat(),'observed_at':now.isoformat()}) as fetch:
            varv_run(store,'topptipset',draw,SimpleNamespace())
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
                    varv_run(store, 'topptipset', draw, SimpleNamespace(), now=self.now)
                self.assertEqual([2, 3], sorted(
                    call.args[0].event_number for call in fetch.call_args_list))
            finally:
                store.close()


class ReserveQueueTests(unittest.TestCase):
    """C3: EN gemensam kö per basvarv i stället för först-till-kvarn per produkt."""
    now = dt.datetime(2026, 9, 24, 15, tzinfo=dt.timezone.utc)

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(r.SCHEMA)
        self.addCleanup(self.conn.close)
        self.store = SimpleNamespace(conn=self.conn, get_sharp=lambda *args: {})
        self.fetch = patch.object(r, 'fetch_quote', side_effect=self.quote)
        self.fetched = self.fetch.start()
        self.addCleanup(self.fetch.stop)

    def at(self, minutes):
        return self.now + dt.timedelta(minutes=minutes)

    def quote(self, match):
        """Per-anropstid som fetch_quote: sätts vid anropet, inte vid varvstart."""
        checked = self.at(1).isoformat()
        return {'status': 'not_listed', 'checked_at': checked, 'observed_at': checked}

    def draw(self, ids, close_min, state='Open', start_min=24 * 60):
        start = self.at(start_min).isoformat()
        return SimpleNamespace(state=state, draw_number=ids[0],
            reg_close_time=self.at(close_min).isoformat(),
            matches=[SimpleNamespace(event_number=i + 1, kambi_id=str(pid), match_start=start,
                                     cancelled=False) for i, pid in enumerate(ids)])

    def checked_before(self, pid, minutes, product='stryktipset', status='not_listed',
                       match_start=None):
        t = self.at(-minutes).isoformat()
        self.conn.execute('INSERT INTO pool_reserve_quote VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (product, 1, int(pid), r.SOURCE, str(pid), t, t, status, None, None, None,
             match_start, None, None, r.VERSION))

    def called(self):
        return [call.args[0].kambi_id for call in self.fetched.call_args_list]

    def test_andra_produkten_far_anrop_nar_forsta_har_manga_kandidater(self):
        """Stryktipset registreras först med sex kandidater; Topptipset stänger
        närmare. Förr tog stryktipsets collect hela budgeten direkt."""
        varv = SimpleNamespace()
        self.assertEqual(6, r.register(self.store, 'stryktipset',
                                       self.draw(range(1, 7), close_min=48 * 60), varv, now=self.now))
        self.assertEqual(2, r.register(self.store, 'topptipset',
                                       self.draw([11, 12], close_min=180), varv, now=self.now))
        self.fetched.assert_not_called()          # registrering gör inga nätanrop
        report = r.run_queue(self.store, varv, now=self.now)
        self.assertEqual(['11', '12', '1'], self.called())
        self.assertEqual((8, 3, 5), (report['candidates'], report['calls'], report['unserved']))

    def test_aldrig_kontrollerad_forst_sedan_aldst_kontroll_sedan_spelstopp(self):
        for pid, minutes in ((1, 20), (2, 40), (3, 30), (4, 40)):
            self.checked_before(pid, minutes)
        varv = SimpleNamespace()
        r.register(self.store, 'stryktipset', self.draw([1, 2, 3], close_min=600), varv, now=self.now)
        r.register(self.store, 'europatipset', self.draw([4], close_min=300), varv, now=self.now)
        r.register(self.store, 'topptipset', self.draw([11], close_min=900), varv, now=self.now)
        r.run_queue(self.store, varv, now=self.now)
        # 11 aldrig kontrollerad; 2 och 4 lika gamla -> närmast spelstopp (4) först.
        self.assertEqual(['11', '4', '2'], self.called())

    def test_cooldown_respekteras_och_observationen_delas_utan_ny_tid(self):
        self.checked_before(1, 5)                  # inom 15 min: inget anrop
        self.checked_before(2, 16)                 # utanför: nytt anrop
        varv = SimpleNamespace()
        r.register(self.store, 'topptipsetstryk', self.draw([1, 2], close_min=300), varv, now=self.now)
        report = r.run_queue(self.store, varv, now=self.now)
        self.assertEqual(['2'], self.called())
        self.assertEqual(1, report['cooldown'])
        shared = self.conn.execute("SELECT checked_at, observed_at FROM pool_reserve_quote "
                                   "WHERE product='topptipsetstryk' AND provider_event_id='1'").fetchone()
        self.assertEqual((self.at(-5).isoformat(),) * 2, tuple(shared))

    def test_aldrig_fler_an_tre_anrop_per_varv(self):
        varv = SimpleNamespace()
        for n, product in enumerate(('stryktipset', 'europatipset', 'topptipset')):
            r.register(self.store, product, self.draw([10 * n + i for i in range(1, 5)],
                                                      close_min=300 + n), varv, now=self.now)
        self.assertEqual(3, r.run_queue(self.store, varv, now=self.now)['calls'])
        r.register(self.store, 'topptipsetextra', self.draw([41, 42], close_min=60), varv, now=self.now)
        self.assertEqual(0, r.run_queue(self.store, varv, now=self.now)['calls'])
        self.assertEqual(3, self.fetched.call_count)
        self.assertEqual(0, r.run_queue(self.store, varv, now=self.now)['candidates'])  # kön tömd

    def test_tidsbudgeten_galler_fran_forsta_anropet(self):
        varv = SimpleNamespace()
        r.register(self.store, 'stryktipset', self.draw([1, 2, 3], close_min=300), varv, now=self.now)
        ticks = iter([0, 0, r.BUDGET_S, r.BUDGET_S])
        r.run_queue(self.store, varv, now=self.now, clock=lambda: next(ticks))
        self.assertEqual(['1'], self.called())

    def test_inga_anrop_for_stangda_omgangar_eller_bomben(self):
        varv = SimpleNamespace()
        self.assertEqual(0, r.register(self.store, 'stryktipset',
            self.draw([1], close_min=300, state='Closed'), varv, now=self.now))
        self.assertEqual(0, r.register(self.store, 'bomben', self.draw([2], close_min=300),
                                       varv, now=self.now))
        self.assertEqual(0, r.register(self.store, 'topptipset', self.draw([3], close_min=-1),
                                       varv, now=self.now))
        # Öppen vid registreringen men stängd (eller startad) när kön körs.
        r.register(self.store, 'europatipset', self.draw([4], close_min=2), varv, now=self.now)
        r.register(self.store, 'topptipsetextra', self.draw([5], close_min=300, start_min=2),
                   varv, now=self.now)
        report = r.run_queue(self.store, varv, now=self.at(3))
        self.fetched.assert_not_called()
        self.assertEqual((2, 0, 0), (report['candidates'], report['calls'], report['saved']))

    def test_samma_provider_id_i_tva_produkter_kostar_ett_anrop(self):
        varv = SimpleNamespace()
        r.register(self.store, 'stryktipset', self.draw([7], close_min=600), varv, now=self.now)
        r.register(self.store, 'topptipsetstryk', self.draw([7], close_min=300), varv, now=self.now)
        self.assertEqual(2, r.run_queue(self.store, varv, now=self.now)['saved'])
        self.assertEqual(['7'], self.called())
        rows = self.conn.execute("SELECT product, checked_at, observed_at FROM pool_reserve_quote "
                                 "ORDER BY product").fetchall()
        self.assertEqual(['stryktipset', 'topptipsetstryk'], [row[0] for row in rows])
        self.assertEqual(1, len({(row[1], row[2]) for row in rows}))

    def test_tillganglig_quote_delas_bara_vid_samma_avspark(self):
        start = self.at(24 * 60).isoformat()
        self.checked_before(7, 5, status='available', match_start=start)
        varv = SimpleNamespace()
        same = self.draw([7], close_min=300)
        moved = self.draw([7], close_min=300, start_min=26 * 60)
        r.register(self.store, 'topptipset', same, varv, now=self.now)
        r.register(self.store, 'topptipsetextra', moved, varv, now=self.now)
        self.assertEqual(1, r.run_queue(self.store, varv, now=self.now)['saved'])
        self.fetched.assert_not_called()
        self.assertEqual(['stryktipset', 'topptipset'], [row[0] for row in self.conn.execute(
            "SELECT product FROM pool_reserve_quote ORDER BY product")])

    def test_senaste_kontroll_jamfors_som_tid_inte_strang(self):
        # Som sträng är 14:40Z den senaste; som tid är 12:55-02:00 (= 14:55Z)
        # det, alltså fem minuter gammal och inom cooldown.
        for checked in ('2026-09-24T14:40:00Z', '2026-09-24T12:55:00-02:00'):
            self.conn.execute('INSERT INTO pool_reserve_quote VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('stryktipset', 1, 1, r.SOURCE, '1', checked, checked,
                 'not_listed', None, None, None, None, None, None, r.VERSION))
        varv = SimpleNamespace()
        r.register(self.store, 'stryktipset', self.draw([1], close_min=300), varv, now=self.now)
        self.assertEqual(1, r.run_queue(self.store, varv, now=self.now)['cooldown'])
        self.fetched.assert_not_called()

    def test_loggraden_namnger_valda_id(self):
        varv = SimpleNamespace()
        r.register(self.store, 'topptipset', self.draw([11], close_min=180), varv, now=self.now)
        line = r.summary_line(r.run_queue(self.store, varv, now=self.now))
        self.assertIn('1 anrop av 1 kandidater', line)
        self.assertIn('topptipset 11 #1 (id 11, aldrig kontrollerad, not_listed)', line)

    def test_basvarvet_kor_kon_en_gang_efter_produktloopen(self):
        import cli
        order = []
        with patch.object(cli, '_any_horizon_window_open', return_value=False), \
                patch.object(cli, 'cmd_snapshot',
                             side_effect=lambda product, varv: order.append(product)), \
                patch.object(cli, '_run_reserve_queue',
                             side_effect=lambda varv: order.append('kö')):
            cli._snapshot_all_pools()
        self.assertEqual([*cli.PRODUCTS, 'kö'], order)
