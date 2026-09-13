"""Förregistrerade researchgrindar och pit-total-grinden — avlästa i OBEROENDE,
PARADE omgångar, aldrig i kuponger."""
import tempfile
import unittest
from pathlib import Path

from app import pool_dataset
from app import pool_system_ledger as psl
from app.storage import Storage
from app.svenskaspel import family_of

LEDGER_COLS = ("product, draw_number, horizon, config_key, frozen_at, lag_min, timely, "
               "code_version, budget, strategy, value_weight, row_price, n_rows, cost_kr, "
               "events_order, rows_text, rows_hash, n_events_covered, turnover_used, "
               "turnover_basis, jackpot_used, settled_at, correct_max, payout_kr, "
               "payout_complete, roi")


def freeze(store, product, draw, horizon, key, *, timely=True, correct_max=None,
           payout_complete=None):
    settled_at = None if correct_max is None else "2026-09-02T00:00:00Z"
    store.conn.execute(
        f"INSERT INTO pool_system_ledger ({LEDGER_COLS}) VALUES "
        "(?,?,?,?,'2026-09-01T10:00:00Z',2,?,'test',5000,'medel',0.5,1,5000,5000,"
        "'1','1','hash',1,1000,'live',0,?,?,?,?,?)",
        (product, draw, horizon, key, int(timely), settled_at, correct_max,
         0.0 if correct_max is not None else None, payout_complete,
         0.0 if payout_complete else None))
    store.conn.commit()


class ResearchGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_ph5_parar_alla_fyra_armarna_per_produkt_och_frystid(self):
        keys = [c["key"] for c in psl.PH5_FORWARD_CONFIGS]
        for k in keys:                                   # 5001: parad
            freeze(self.store, "stryktipset", 5001, "h3", k, correct_max=10, payout_complete=1)
        for k in keys[:3]:                               # 5002: en arm saknas
            freeze(self.store, "stryktipset", 5002, "h3", k, correct_max=9, payout_complete=1)
        for i, k in enumerate(keys):                     # 5003: en arm sen
            freeze(self.store, "stryktipset", 5003, "h3", k, timely=i > 0,
                   correct_max=11, payout_complete=1)
        for k in keys:                                   # 5004: öppen
            freeze(self.store, "stryktipset", 5004, "h3", k)
        for k in keys:                                   # 5005: utdelning ej komplett
            freeze(self.store, "stryktipset", 5005, "h3", k, correct_max=12, payout_complete=0)
        # Pensionerad v3-nyckel hör till en annan version och räknas inte.
        freeze(self.store, "stryktipset", 5006, "h3", psl.PH5_RETIRED_CONFIGS[0]["key"],
               correct_max=13, payout_complete=1)
        for k in keys:                                   # Europa är en egen serie
            freeze(self.store, "europatipset", 2610, "m20", k, correct_max=8, payout_complete=1)

        rep = psl.research_gate(self.store, "ph5")
        self.assertEqual(("ph5-v4", 40, False), (rep["version"], rep["required"], rep["closed"]))
        cells = {(c["unit"], c["horizon"]): c for c in rep["cells"]}
        c = cells[("stryktipset", "h3")]
        self.assertEqual((5, 1, 4, 1), (c["forward_draws"], c["open_draws"],
                                        c["settled_draws"], c["paired_draws"]))
        self.assertEqual({"saknad arm": 1, "sen frysning": 1, "utdelning ej komplett": 1},
                         c["dropout"])
        self.assertEqual("samlar", c["status"])
        self.assertEqual(1, cells[("europatipset", "m20")]["paired_draws"])
        self.assertEqual(2, len(cells))

    def test_poolopt_paras_mot_championen_per_arm_over_familjen(self):
        arm = psl.POOLOPT_FORWARD_CONFIGS[0]["key"]
        freeze(self.store, "topptipset", 4310, "h3", arm, correct_max=7, payout_complete=1)
        freeze(self.store, "topptipset", 4310, "h3", psl.CHAMPION_KEY, correct_max=6, payout_complete=1)
        freeze(self.store, "topptipsetextra", 1865, "h3", arm, correct_max=8, payout_complete=1)
        freeze(self.store, "topptipsetstryk", 980, "h3", arm, correct_max=5, payout_complete=1)
        freeze(self.store, "topptipsetstryk", 980, "h3", psl.CHAMPION_KEY, correct_max=5, payout_complete=0)
        rep = psl.research_gate(self.store, "poolopt")
        self.assertEqual((120, "champion", "family"),
                         (rep["end_after_forward_draws"], rep["pair"], rep["unit"]))
        cells = {(c["unit"], c["horizon"], c["arm"]): c for c in rep["cells"]}
        c = cells[(family_of("topptipset"), "h3", arm)]
        self.assertEqual("träff", c["arm_label"])
        self.assertEqual((3, 3, 1), (c["forward_draws"], c["settled_draws"], c["paired_draws"]))
        self.assertEqual({"saknad champion": 1, "sen frysning": 0, "utdelning ej komplett": 1},
                         c["dropout"])

    def test_maxtest_ar_preliminart_fran_tio_par_och_klart_vid_fyrtio(self):
        keys = [c["key"] for c in psl.MATHMAX_FORWARD_CONFIGS]
        for draw in range(5000, 5010):
            for k in keys:
                freeze(self.store, "stryktipset", draw, "m20", k, correct_max=9, payout_complete=1)
        cell = psl.research_gate(self.store, "mathmax")["cells"][0]
        self.assertEqual((10, "samlar", "preliminärt från 10 par"),
                         (cell["paired_draws"], cell["status"], cell["note"]))
        for draw in range(5010, 5040):
            for k in keys:
                freeze(self.store, "stryktipset", draw, "m20", k, correct_max=9, payout_complete=1)
        cell = psl.research_gate(self.store, "mathmax")["cells"][0]
        self.assertEqual((40, "underlag klart"), (cell["paired_draws"], cell["status"]))

    def test_max40_ar_avslutad(self):
        rep = psl.research_gate(self.store, "max40")
        self.assertEqual(("max40-v1", True, []), (rep["version"], rep["closed"], rep["cells"]))
        freeze(self.store, "stryktipset", 4960, "h3", psl.MAX40_RETIRED_CONFIGS[0]["key"],
               correct_max=10, payout_complete=1)
        self.assertEqual("avslutad", psl.research_gate(self.store, "max40")["cells"][0]["status"])

    def test_versionen_kommer_ur_nyckeln(self):
        self.assertEqual("mathmax-v2", psl.research_version(["mathmax-v2-dr1-b39366-ev50"]))
        self.assertEqual("poolopt-v1", psl.research_version(["poolopt-v1-b256-traff"]))
        self.assertIsNone(psl.research_version(["dr1-b256-medel"]))


class TotalGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _rows(self, product, draw, horizon, flags, version=pool_dataset.TOTAL_FEATURE_VERSION):
        for event, eligible in enumerate(flags, start=1):
            self.store.conn.execute(
                "INSERT INTO pool_pit_total_features (product, draw_number, horizon, "
                "event_number, feature_version, asof, computed_at, total_lag_min, "
                "total_eligible, line) VALUES (?,?,?,?,?,'2026-09-05T10:00:00Z',"
                "'2026-09-05T10:00:00Z',1,?,?)",
                (product, draw, horizon, event, version, eligible, 2.5 if eligible else None))
        self.store.conn.commit()

    def test_raknar_kompletta_attamatchsomgangar_per_horisont(self):
        self._rows("topptipset", 4400, "h3", [1] * 8)
        self._rows("topptipset", 4401, "h3", [1] * 7 + [0])
        self._rows("topptipsetextra", 1870, "m20", [1] * 8)
        self._rows("stryktipset", 5000, "h3", [1] * 13)
        self._rows("topptipset", 4399, "h3", [1] * 8, version="pit-total-v0")
        rep = pool_dataset.total_gate(self.store)
        self.assertEqual(40, rep["required_complete_draws"])
        h3 = rep["horizons"]["h3"]
        self.assertEqual((2, 1, 16, 15, 1), (h3["observed"], h3["complete"], h3["rows"],
                                             h3["eligible_rows"], h3["other_observed"]))
        m20 = rep["horizons"]["m20"]
        self.assertEqual((1, 1), (m20["observed"], m20["complete"]))
        self.assertEqual(0, rep["horizons"]["h24"]["observed"])
