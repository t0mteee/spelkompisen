"""Historikens familjeläge: Topptipsets tre slugs är EN historik.

Topptipset Dagens/Stryk/Extra är samma spel hos Svenska Spel — åtta matcher,
samma vinstplan — men tre omgångsserier med egna nummer. Familjeläget slår ihop
dem i historiken utan att röra produktidentiteten: varje rad bär kvar sin egen
slug så detaljuppslag och djuplänkar pekar rätt.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import main
from app.storage import Storage


def _hist(product, family=False):
    """Anropar endpointen direkt. `limit` måste anges: dess default är ett
    FastAPI-Query-objekt som bara löses ut via HTTP-lagret."""
    return main.pool_history(product=product, limit=400, family=family)


def _settle(store, product, draw, close, net_sale, top_winners, top_amount,
            state="Finalized"):
    store.conn.execute(
        "INSERT OR REPLACE INTO pool_draw_settlement (product, draw_number, "
        "draw_state, reg_close_time, net_sale, row_price, n_events, "
        "n_cancelled, product_name, payload_hash, fetched_at, source_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (product, draw, state, close, net_sale, 1.0, 8, 0,
         product, f"h{product}{draw}", "2026-08-12T00:00:00Z", 1))
    store.conn.execute(
        "INSERT OR REPLACE INTO pool_payout_tier (product, draw_number, "
        "tier_name, correct, winners, amount) VALUES (?,?,?,?,?,?)",
        (product, draw, "8 rätt", 8, top_winners, top_amount))
    store.conn.commit()


class PoolHistoryFamilyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.db"
        store = Storage(self.path)
        # Tre produkter, egna nummerserier, om vartannat i tiden.
        _settle(store, "topptipset", 4260, "2026-08-11T18:59:00+02:00", 1_419_016, 1598, 621.0)
        _settle(store, "topptipsetextra", 1856, "2026-08-09T13:59:00+02:00", 1_159_402, 348, 2332.0)
        _settle(store, "topptipsetstryk", 975, "2026-08-08T15:59:00+02:00", 500_000, 0, None)
        _settle(store, "topptipset", 4259, "2026-08-10T18:59:00+02:00",
                0, 0, 0.0, state="Cancelled")
        _settle(store, "stryktipset", 4965, "2026-08-08T15:59:00+02:00", 14_231_193, 11, 526_040.0)
        store.close()
        patcher = mock.patch.object(main, "Storage", lambda *a, **k: Storage(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_familjen_ger_en_historik_med_alla_tre_serierna(self):
        svar = _hist("topptipset", family=True)

        self.assertEqual(svar["total"], 3)
        self.assertEqual(sorted(svar["products"]),
                         ["topptipset", "topptipsetextra", "topptipsetstryk"])
        self.assertEqual([d["draw_number"] for d in svar["draws"]], [4260, 1856, 975])

    def test_utan_familj_ar_svaret_oforandrat(self):
        svar = _hist("topptipset")

        self.assertEqual(svar["total"], 1)
        self.assertEqual(svar["products"], ["topptipset"])
        self.assertEqual([d["draw_number"] for d in svar["draws"]], [4260])

    def test_varje_rad_bar_sin_egen_produkt(self):
        svar = _hist("topptipset", family=True)

        # Utan detta pekar detaljuppslaget /api/pool/history?draw=1856 på
        # topptipset i stället för topptipsetextra och hittar ingenting.
        self.assertEqual(
            {d["draw_number"]: d["product"] for d in svar["draws"]},
            {4260: "topptipset", 1856: "topptipsetextra", 975: "topptipsetstryk"})

    def test_utdelningsnivaer_paras_pa_produkt_och_omgang(self):
        svar = _hist("topptipset", family=True)
        per_draw = {d["draw_number"]: d for d in svar["draws"]}

        self.assertEqual(per_draw[1856]["top_amount"], 2332.0)
        self.assertEqual(per_draw[4260]["top_amount"], 621.0)

    def test_statistiken_raknas_over_hela_familjen(self):
        svar = _hist("topptipset", family=True)

        # Median betald toppvinst över 621 och 2332 (975 saknar vinnare).
        self.assertAlmostEqual(svar["stats"]["median_top_amount"], (621.0 + 2332.0) / 2)
        # En av tre omgångar rullade.
        self.assertAlmostEqual(svar["stats"]["rollover_rate"], 1 / 3)
        self.assertAlmostEqual(
            svar["stats"]["mean_turnover"], (1_419_016 + 1_159_402 + 500_000) / 3)

    def test_installd_omgang_bevaras_i_arkivet_men_inte_i_statistiken(self):
        svar = _hist("topptipset", family=True)

        self.assertEqual(3, svar["total"])
        self.assertEqual(4, svar["archive_total"])
        self.assertEqual(1, svar["cancelled_count"])
        self.assertNotIn(4259, [d["draw_number"] for d in svar["draws"]])
        self.assertAlmostEqual(1 / 3, svar["stats"]["rollover_rate"])

    def test_familjen_blandar_aldrig_in_andra_spel(self):
        svar = _hist("topptipset", family=True)

        self.assertNotIn(4965, [d["draw_number"] for d in svar["draws"]])

    def test_okand_familjenyckel_faller_tillbaka_pa_produkten(self):
        svar = _hist("stryktipset", family=True)

        self.assertEqual(svar["products"], ["stryktipset"])
        self.assertEqual(svar["total"], 1)

    def test_listan_ar_kronologisk_inte_pa_omgangsnummer(self):
        # Extra 1856 är ett LÄGRE nummer men stängde senare än Stryk 975.
        svar = _hist("topptipset", family=True)
        closes = [d["close"] for d in svar["draws"]]

        self.assertEqual(closes, sorted(closes, reverse=True))


if __name__ == "__main__":
    unittest.main()
