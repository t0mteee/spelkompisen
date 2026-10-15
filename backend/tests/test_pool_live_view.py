"""Livesidan för poolspelen (app/pool_live_view.py) och GET /api/pool/live.

Källorna är fejkade (`states_fn`): testerna gör inga anrop till Svenska Spel,
Flashscore eller oddskällorna.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import pool_live_view as plv, pool_played
from app.storage import Storage

UTC = dt.timezone.utc
NU = dt.datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
FOLK = {"1": 50.0, "X": 30.0, "2": 20.0}


def state(n, sign=None, *, final=False, score=None, live=False, folk=FOLK):
    return {"event_number": n, "sign": sign, "final": final, "score": score,
            "in_progress": live, "cancelled": False, "sign_provisional": False,
            "extra_time": False, "postponed": False, "folk": folk,
            "home": f"Hemma {n}", "away": f"Borta {n}", "description": f"Hemma {n} - Borta {n}",
            "start": "2026-10-17T14:00:00Z", "minute": 55 if live else None,
            "probs": {"1": 0.6, "X": 0.25, "2": 0.15} if live else None,
            "probs_basis": "live" if live else None,
            "prematch_probs": {"1": 0.5, "X": 0.3, "2": 0.2}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def draw(self, product, number, close, settled=False):
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) VALUES (?,?,?,?)",
            (product, number, "Open", close))
        if settled:
            self.store.conn.execute(
                "INSERT INTO pool_draw_settlement (product, draw_number, draw_state, "
                "source_version, payload_hash, fetched_at) VALUES (?,?,?,?,?,?)",
                (product, number, "Finalized", "v", "h", "2026-10-17T00:00:00Z"))
        self.store.conn.commit()

    def kupong(self, rows, product="topptipset", number=4400):
        return pool_played.record(self.store, {
            "product": product, "draw_number": number, "row_price": 1.0,
            "rows": list(rows), "build_kind": "värderader", "budget": float(len(rows))})


class UrvalTests(Base):
    def test_stangda_osettlade_omgangar_och_kupongomgangar_inom_fonstret(self):
        self.draw("topptipset", 4400, "2026-10-17T14:59:00+02:00")       # stängd 2 h sedan
        self.draw("stryktipset", 4975, "2026-10-17T15:59:00+02:00")      # stängd 1 h sedan
        self.draw("topptipset", 4399, "2026-10-17T00:29:00+02:00", settled=True)
        self.draw("topptipset", 4401, "2026-10-16T12:00:00+02:00")       # utanför 12 h
        self.draw("bomben", 9000, "2026-10-17T15:00:00+02:00")           # Bomben följs inte
        self.draw("topptipset", 4402, "2026-10-17T17:20:00+02:00")       # stänger om 20 min
        self.draw("topptipset", 4403, "2026-10-17T19:00:00+02:00")       # om 2 h
        self.kupong(["11111111"], number=4402)
        self.kupong(["11111111"], number=4403)
        keys = [(p, n) for p, n, _c in plv.aktiva_omgangar(self.store, NU)]
        self.assertEqual([("topptipset", 4400), ("stryktipset", 4975),
                          ("topptipset", 4402)], keys)


class ByggTests(Base):
    def bygg(self, states, forecast=None):
        return plv.bygg(self.store, NU,
                        states_fn=lambda st, keys: ({k: states for k in keys}, {}),
                        forecast_fn=lambda *a: forecast)

    def test_kupongens_krav_for_alla_ratt_och_levande_nivaer(self):
        self.draw("topptipset", 4400, "2026-10-17T14:59:00+02:00")
        self.kupong(["11111111", "1111111X", "X1111111", "11112222"])
        states = ([state(1, "1", final=True, score="2-0"),
                   state(2, "1", final=True, score="1-0"),
                   state(3, "1", score="1-0", live=True)]
                  + [state(n) for n in range(4, 9)])
        out = self.bygg(states, forecast={"levels": {8: {"per_row_kr": 1000}}})
        self.assertTrue(out["active"])
        (draw,) = out["draws"]
        self.assertEqual((2, 1, True, False),
                         (draw["n_decided"], draw["n_live"], draw["started"], draw["finished"]))
        self.assertEqual({"1": 0.6, "X": 0.25, "2": 0.15}, draw["matches"][2]["live_probs"])
        self.assertEqual(55, draw["matches"][2]["minute"])
        # 50 % × 50 % × 50 % av folkets rader har alla rätt hittills.
        self.assertEqual(0.125, draw["folk_alla_ratt"])
        (kupong,) = draw["coupons"]
        self.assertEqual((8, 3), (kupong["top_level"], kupong["top_alive"]))
        krav = {k["col"]: k["signs"] for k in kupong["krav"]}
        self.assertEqual(["1"], krav[3])                  # X1111111 är död, de andra kräver 1
        self.assertEqual(["1", "X", "2"], krav[8])        # tre rader täcker 1, X och 2
        self.assertEqual({"1": 3, "X": 1}, kupong["row_signs"]["1"])
        self.assertIn(kupong["id"], out["coupon_live"])
        self.assertEqual(1000, out["coupon_live"][kupong["id"]]["forecast"]["levels"][8]["per_row_kr"])

    def test_kallfel_ger_omgangen_ett_fel_men_inte_hela_svaret(self):
        self.draw("topptipset", 4400, "2026-10-17T14:59:00+02:00")
        out = plv.bygg(self.store, NU,
                       states_fn=lambda st, keys: ({}, {k: TimeoutError() for k in keys}),
                       forecast_fn=lambda *a: None)
        self.assertEqual("TimeoutError", out["draws"][0]["error"])
        self.assertFalse(out["active"])

    def test_inget_aktivt_utan_startade_matcher(self):
        self.draw("topptipset", 4400, "2026-10-17T14:59:00+02:00")
        out = self.bygg([state(n) for n in range(1, 9)])
        self.assertFalse(out["active"])
        self.assertIsNone(out["draws"][0]["folk_alla_ratt"])


class HubTests(unittest.TestCase):
    def test_snapshot_bygger_vid_behov_och_aterbrukar_annars(self):
        klocka = [0.0]
        byggen = []

        def bygg():
            byggen.append(klocka[0])
            return {"n": len(byggen), "active": False}
        hub = plv.LiveHub(bygg, clock=lambda: klocka[0])
        self.assertEqual(1, hub.snapshot()["n"])
        klocka[0] = 30
        self.assertEqual(1, hub.snapshot()["n"])
        klocka[0] = 200
        self.assertEqual(2, hub.snapshot(max_age_s=90)["n"])

    def test_trasigt_bygge_behaller_forra_bilden(self):
        svar = [{"n": 1}]

        def bygg():
            if not svar:
                raise RuntimeError("källa nere")
            return svar.pop()
        hub = plv.LiveHub(bygg)
        self.assertEqual({"n": 1}, hub.refresh())
        self.assertEqual({"n": 1}, hub.refresh())


if __name__ == "__main__":
    unittest.main()
