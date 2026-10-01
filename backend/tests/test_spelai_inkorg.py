"""Inkorgen: inläsning, avvisning, dedup, svar, misstänkta svar, kvot, API-läsning."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app.spelai import api, inkorg, tillstand  # noqa: E402

NOW = START + dt.timedelta(hours=2)
SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")


def _beslut(ext_id="b-1", **extra):
    data = {"id": ext_id, "typ": "beslut", "kalla": "Koordinatorn",
            "rubrik": "Höj taket", "varfor": "Forskningspassen räcker inte.",
            "alternativ": [{"text": "Behåll 8", "rekommenderas": False, "kvot": 8},
                           {"text": "Höj till 10", "rekommenderas": True, "kvot": 10}]}
    data.update(extra)
    return data


class InkorgTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.conn = self.store.conn
        self.utkorg = Path(self.tmp.name) / "utkorg"
        self.utkorg.mkdir()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _fil(self, name, data):
        path = self.utkorg / name
        path.write_text(data if isinstance(data, str) else json.dumps(data))
        return path

    def test_giltig_fil_lases_in_och_flyttas(self):
        self._fil("a.json", _beslut(sista_tid="2026-10-02T18:00:00+02:00"))
        rep = inkorg.las_in(self.conn, self.utkorg, now=NOW)
        self.assertEqual(1, rep["inlasta"])
        self.assertTrue((self.utkorg / "inlasta" / "a.json").exists())
        self.assertFalse((self.utkorg / "a.json").exists())
        item = inkorg.lista(self.conn, now=NOW)[0]
        self.assertEqual(("beslut", "vantar", "2026-10-02T16:00:00Z"),
                         (item["typ"], item["status"], item["sista_tid"]))

    def test_ogiltiga_filer_avvisas_med_orsak(self):
        self._fil("trasig.json", "{inte json")
        self._fil("typ.json", _beslut("b-2", typ="order"))
        self._fil("tvarek.json", _beslut("b-3", alternativ=[
            {"text": "a", "rekommenderas": True}, {"text": "b", "rekommenderas": True}]))
        self._fil("utanzon.json", _beslut("b-4", sista_tid="2026-10-02T18:00:00"))
        rep = inkorg.las_in(self.conn, self.utkorg, now=NOW)
        self.assertEqual(4, rep["avvisade"])
        orsaker = {p.name: p.read_text() for p in (self.utkorg / "avvisade").glob("*.orsak.txt")}
        self.assertIn("ogiltig JSON", orsaker["trasig.json.orsak.txt"])
        self.assertIn("'typ'", orsaker["typ.json.orsak.txt"])
        self.assertIn("högst ett", orsaker["tvarek.json.orsak.txt"])
        self.assertIn("tidszon", orsaker["utanzon.json.orsak.txt"])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM spelai_inbox").fetchone()[0])

    def test_dubblett_pa_agentens_id(self):
        self._fil("a.json", _beslut())
        inkorg.las_in(self.conn, self.utkorg, now=NOW)
        self._fil("a.json", _beslut(rubrik="Ny rubrik"))
        rep = inkorg.las_in(self.conn, self.utkorg, now=NOW)
        self.assertEqual(1, rep["dubbletter"])
        self.assertEqual(1, self.conn.execute("SELECT COUNT(*) FROM spelai_inbox").fetchone()[0])
        self.assertEqual(2, len(list((self.utkorg / "inlasta").glob("a*.json"))))

    def test_svar_fran_webblasare_raknas_och_annat_ar_misstankt(self):
        self._fil("a.json", _beslut())
        inkorg.las_in(self.conn, self.utkorg, now=NOW)
        inbox_id = inkorg.lista(self.conn, now=NOW)[0]["id"]
        svar = inkorg.svara(self.conn, inbox_id, "1", None, user_agent="curl/8.7.1",
                            forwarded_for=None, client_host="127.0.0.1", now=NOW)
        self.assertTrue(svar["misstankt"])
        self.assertEqual("vantar", inkorg.lista(self.conn, now=NOW)[0]["status"])
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_event WHERE kind='svar_misstankt'").fetchone()[0])
        self.assertEqual(8, tillstand.godkant_tak(self.conn)["tak"])
        inkorg.svara(self.conn, inbox_id, "1", "ok", user_agent=SAFARI,
                     forwarded_for="100.64.0.7", client_host="127.0.0.1", now=NOW)
        item = inkorg.lista(self.conn, now=NOW)[0]
        self.assertEqual(("besvarad", "1"), (item["status"], item["svar"]["val"]))
        row = self.conn.execute("SELECT user_agent, forwarded_for, client_host FROM "
                                "spelai_inbox_answer ORDER BY id DESC").fetchone()
        self.assertEqual((SAFARI, "100.64.0.7", "127.0.0.1"), tuple(row))

    def test_ogiltigt_val_och_okand_post(self):
        self._fil("f.json", {"id": "f-1", "typ": "forslag_forbattring", "kalla": "Användaren",
                             "rubrik": "Större knappar", "varfor": "Svårt att träffa."})
        inkorg.las_in(self.conn, self.utkorg, now=NOW)
        inbox_id = inkorg.lista(self.conn, now=NOW)[0]["id"]
        with self.assertRaises(ValueError):
            inkorg.svara(self.conn, inbox_id, "0", None, user_agent=SAFARI,
                         forwarded_for=None, client_host=None, now=NOW)
        with self.assertRaises(ValueError):
            inkorg.svara(self.conn, inbox_id, "kommentar", "  ", user_agent=SAFARI,
                         forwarded_for=None, client_host=None, now=NOW)
        with self.assertRaises(LookupError):
            inkorg.svara(self.conn, 999, "nej", None, user_agent=SAFARI,
                         forwarded_for=None, client_host=None, now=NOW)
        inkorg.svara(self.conn, inbox_id, "nej", None, user_agent=SAFARI,
                     forwarded_for=None, client_host=None, now=NOW)
        self.assertEqual("besvarad", inkorg.lista(self.conn, now=NOW)[0]["status"])

    def test_kvot_ur_besvarat_beslut_och_absolut_tak(self):
        self.assertEqual(8, tillstand.kvot_idag(self.conn, NOW)["tak"])
        self._fil("a.json", _beslut())
        self._fil("b.json", _beslut("b-9", alternativ=[
            {"text": "Höj till 20", "rekommenderas": True, "kvot": 20}]))
        inkorg.las_in(self.conn, self.utkorg, now=NOW)
        ids = {i["external_id"]: i["id"] for i in inkorg.lista(self.conn, now=NOW)}
        inkorg.svara(self.conn, ids["b-1"], "1", None, user_agent=SAFARI,
                     forwarded_for=None, client_host=None, now=NOW)
        self.assertEqual(10, tillstand.godkant_tak(self.conn)["tak"])
        inkorg.svara(self.conn, ids["b-9"], "0", None, user_agent=SAFARI,
                     forwarded_for=None, client_host=None, now=NOW)
        tak = tillstand.godkant_tak(self.conn)
        self.assertEqual((12, 20), (tak["tak"], tak["begart"]))   # MAX_KORNINGAR_ABS
        self.conn.execute(
            "INSERT INTO spelai_run (role, started_at, status, recorded_at) VALUES "
            "('forskaren', ?, 'klar', ?)", (tillstand.iso(NOW), tillstand.iso(NOW)))
        kvot = tillstand.kvot_idag(self.conn, NOW)
        self.assertEqual((1, 11), (kvot["anvanda"], kvot["kvar"]))

    def test_utgangen_och_paus_som_handelser(self):
        self._fil("a.json", _beslut(sista_tid="2026-10-01T07:00:00Z"))
        inkorg.las_in(self.conn, self.utkorg, now=NOW)
        self.assertEqual("utgangen", inkorg.lista(self.conn, now=NOW)[0]["status"])
        tillstand.satt_paus(self.conn, True, source="test", now=NOW)
        self.assertTrue(tillstand.pausad(self.conn))
        tillstand.satt_paus(self.conn, False, source="test", now=NOW)
        self.assertFalse(tillstand.pausad(self.conn))
        self.assertEqual(3, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_state WHERE key IN ('paus','facit_start')"
        ).fetchone()[0])


class ApiUtanTabellerTests(unittest.TestCase):
    def test_lasvagar_svarar_tomt(self):
        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp, med_tabeller=False)
        try:
            self.assertEqual({"tabeller": False, "omgangar": [], "per_niva": []},
                             api.pool(store.conn, now=NOW))
            self.assertFalse(api.inbox(store.conn, now=NOW)["tabeller"])
            self.assertFalse(api.korningar(store.conn, now=NOW)["tabeller"])
        finally:
            store.close()
            tmp.cleanup()

    def test_spelat_och_pool_lasning(self):
        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp)
        try:
            conn = store.conn
            cur = conn.execute(
                "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                "horizon, role, status, format, rows_text, n_rows, cost_kr, "
                "reg_close_time, frozen_at) VALUES ('topptipset', 1, 256, '30m', "
                "'agent', 'fryst', 'rows', '11111111', 1, 1.0, "
                "'2026-10-03T13:59:00Z', '2026-10-03T13:29:00Z')")
            conn.commit()
            out = api.spelat(conn, {"forslag_id": cur.lastrowid}, user_agent=SAFARI,
                             forwarded_for=None, client_host=None, now=NOW)
            self.assertEqual("pool", out["typ"])
            with self.assertRaises(LookupError):
                api.spelat(conn, {"forslag_id": 999}, user_agent=SAFARI,
                           forwarded_for=None, client_host=None, now=NOW)
            view = api.pool(conn, now=NOW)
            agent = view["omgangar"][0]["nivaer"][0]["horisonter"]["30m"]["agent"]
            self.assertEqual(("fryst", 1), (agent["status"], agent["rader"]))
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()


class TillatenOriginTests(unittest.TestCase):
    """Svar tas bara emot från Spelkompisens egen beslutssida (5175/5181)."""

    def test_spelkompisens_portar_tillats(self):
        from app.spelai import inkorg as ink
        self.assertTrue(ink.tillaten_origin("http://192.168.50.100:5175"))
        self.assertTrue(ink.tillaten_origin("http://localhost:5181"))

    def test_agentens_app_och_saknad_origin_nekas(self):
        from app.spelai import inkorg as ink
        self.assertFalse(ink.tillaten_origin("http://192.168.50.100:5176"))
        self.assertFalse(ink.tillaten_origin(None))
        self.assertFalse(ink.tillaten_origin(""))
        self.assertFalse(ink.tillaten_origin("http://192.168.50.100"))
        self.assertFalse(ink.tillaten_origin("file://x"))
