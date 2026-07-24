import unittest
from unittest import mock

from app import smarkets


def _fake_get(path, params=None):
    """Minimal spegling av Smarkets v3-svar (verifierad struktur 2026-07-24)."""
    if path == "/events/":
        return {"events": [
            {"id": "1", "name": "Degerfors IF vs Djurgardens", "bettable": True,
             "full_slug": "/sport/football/sweden-allsvenskan/2026/07/25/x",
             "start_datetime": "2026-07-25T13:00:00Z"},
            {"id": "2", "name": "Annan vs Match", "bettable": True,
             "full_slug": "/sport/football/england-premier-league/2026/08/21/y",
             "start_datetime": "2026-08-21T19:00:00Z"},
            {"id": "3", "name": "Ospelbar vs Match", "bettable": False,
             "full_slug": "/sport/football/sweden-allsvenskan/2026/07/26/z",
             "start_datetime": "2026-07-26T13:00:00Z"},
        ]}
    if path.startswith("/events/") and path.endswith("/markets/"):
        return {"markets": [
            {"id": "m1", "event_id": "1", "name": "Full-time result",
             "state": "open"},
            {"id": "m9", "event_id": "1", "name": "Total goals", "state": "open"},
            {"id": "m8", "event_id": "1", "name": "Full-time result",
             "state": "suspended"},
        ]}
    if path.endswith("/contracts/"):
        return {"contracts": [
            {"id": "c1", "market_id": "m1", "slug": "home"},
            {"id": "c2", "market_id": "m1", "slug": "draw"},
            {"id": "c3", "market_id": "m1", "slug": "away"},
        ]}
    if path.endswith("/quotes/"):
        return {
            "c1": {"bids": [{"price": 2000}, {"price": 1900}],
                   "offers": [{"price": 2100}, {"price": 2200}]},
            "c2": {"bids": [{"price": 2400}], "offers": [{"price": 2600}]},
            "c3": {"bids": [{"price": 5400}], "offers": [{"price": 5600}]},
        }
    raise AssertionError(f"oväntad path: {path}")


class SmarketsTests(unittest.TestCase):
    def setUp(self):
        self.client = smarkets.Smarkets.__new__(smarkets.Smarkets)
        self.client._get = _fake_get   # noqa: SLF001

    def test_pris_till_decimalodds(self):
        # Smarkets-pris = sannolikhet × 100 ⇒ 2000 = 20 % = odds 5,00
        self.assertAlmostEqual(5.0, smarkets._decimal(2000))
        self.assertAlmostEqual(1.8182, smarkets._decimal(5500), places=3)
        self.assertIsNone(smarkets._decimal(0))
        self.assertIsNone(smarkets._decimal(None))

    def test_mid_ligger_mellan_back_och_lay(self):
        rows = self.client.league_events("allsvenskan", strict=True)
        self.assertEqual(1, len(rows))
        row = rows[0]
        for sign in ("1", "X", "2"):
            back, lay, mid = row["back"][sign], row["lay"][sign], row["odds"][sign]
            self.assertLessEqual(back, mid)   # back = lägsta offer ⇒ lägst odds
            self.assertGreaterEqual(lay, mid)
        # 2000/2100 ⇒ mid 2050 ⇒ 4,878
        self.assertAlmostEqual(4.878, row["odds"]["1"], places=2)

    def test_lagnamn_och_starttid_normaliseras(self):
        row = self.client.league_events("allsvenskan", strict=True)[0]
        self.assertEqual("Degerfors IF", row["home"])
        self.assertEqual("Djurgardens", row["away"])
        self.assertEqual("2026-07-25T13:00:00Z", row["start"])

    def test_ospelbara_event_och_stangda_marknader_hoppas(self):
        rows = self.client.league_events("allsvenskan", strict=True)
        # event 3 är bettable=False, marknad m8 är suspended, m9 är fel typ
        self.assertEqual(["1"], [r["id"] for r in rows])

    def test_okand_liga_ger_tom_lista(self):
        self.assertEqual([], self.client.league_events("bomben", strict=True))

    def test_alla_vara_ligor_ar_mappade(self):
        from app.oddset import LEAGUES
        for league in LEAGUES:
            self.assertIn(league["key"], smarkets.LEAGUE_SLUGS,
                          msg=f"{league['key']} saknar Smarkets-slug")

    def test_fel_ger_tom_lista_utan_strict(self):
        def boom(path, params=None):
            raise RuntimeError("nätverksfel")
        self.client._get = boom   # noqa: SLF001
        self.assertEqual([], self.client.league_events("allsvenskan"))
        with self.assertRaises(RuntimeError):
            self.client.league_events("allsvenskan", strict=True)


if __name__ == "__main__":
    unittest.main()
