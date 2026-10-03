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


# Ligafasens och landslagens full_slug är ordagranna ur Smarkets sidbläddrade
# upcoming-lista 2026-10-03. Kvalets rader har samma form; kvalsegmenten
# observerades 2026-07-28 men listar inga event förrän nästa kval.
SLUG_FIXTURES = {
    "cl": "/sport/football/uefa-champions-league/2026/10/14/19-00/"
          "shakhtar-donetsk-vs-aek-athens",
    "cl-kval": "/sport/football/uefa-champions-league-qualification/"
               "2026/07/29/18-00/a-vs-b",
    "el": "/sport/football/uefa-europa-league/2026/10/15/16-45/"
          "sc-uniao-torreense-vs-sunderland",
    "el-kval": "/sport/football/uefa-europa-league-qualification/"
               "2026/07/31/17-00/c-vs-d",
    "ecl": "/sport/football/uefa-europa-conference-league/2026/10/15/16-45/"
           "kaa-gent-vs-agf-aarhus",
    "ecl-kval": "/sport/football/uefa-europa-conference-league-qualification/"
                "2026/07/30/16-00/e-vs-f",
    "nl-a": "/sport/football/uefa-nations-league-a/2026/10/03/16-00/"
            "croatia-vs-england",
    "nl-b": "/sport/football/uefa-nations-league-b/2026/10/03/18-45/"
            "north-macedonia-vs-scotland",
    "nl-c": "/sport/football/uefa-nations-league-c/2026/10/03/13-00/"
            "finland-vs-albania",
    "nl-d": "/sport/football/uefa-nations-league-d/2026/10/04/16-00/"
            "malta-vs-andorra",
    "vanskap": "/sport/football/international-friendlies/2026/10/03/14-00/"
               "india-vs-brazil",
}


def _orderbok_for_alla(path, params=None):
    """Komplett 1X2-orderbok för varje id i ett batchat anrop."""
    ids = path.split("/")[2].split(",")
    if path.startswith("/events/") and path.endswith("/markets/"):
        return {"markets": [{"id": f"m-{i}", "event_id": i,
                             "name": "Full-time result", "state": "open"}
                            for i in ids]}
    if path.endswith("/contracts/"):
        return {"contracts": [{"id": f"{m}-{s}", "market_id": m, "slug": s}
                              for m in ids for s in ("home", "draw", "away")]}
    if path.endswith("/quotes/"):
        return {f"{m}-{s}": {"bids": [{"price": 3000}],
                             "offers": [{"price": 3400}]}
                for m in ids for s in ("home", "draw", "away")}
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

    def _ids_per_liga(self, leagues):
        events = [{"id": key, "name": "Hemma vs Borta", "bettable": True,
                   "full_slug": slug, "start_datetime": "2026-10-15T19:00:00Z"}
                  for key, slug in SLUG_FIXTURES.items()]
        self.client._get = _orderbok_for_alla   # noqa: SLF001
        return {league: {r["id"] for r in self.client.league_events(
                    league, strict=True, events=events)}
                for league in leagues}

    def test_cupernas_slugs_avlasta_2026_10_03(self):
        # Ligafas + kval per cup; "uefa-europa-league" får inte ta
        # Conference-raderna eller kvalets och tvärtom.
        self.assertEqual({
            "champions_league": {"cl", "cl-kval"},
            "europa_league": {"el", "el-kval"},
            "conference_league": {"ecl", "ecl-kval"},
        }, self._ids_per_liga(
            ("champions_league", "europa_league", "conference_league")))

    def test_landslagens_slugs_avlasta_2026_10_03(self):
        self.assertEqual({
            "nations_league": {"nl-a", "nl-b", "nl-c", "nl-d"},
            "landskamper": {"vanskap"},
        }, self._ids_per_liga(("nations_league", "landskamper")))

    def test_upcoming_foljer_sidorna_till_slutet(self):
        # Sedan 2026-09-19 ger Smarkets högst 50 event per svar och pekar
        # vidare med next_page; första sidan ensam är inte hela listan.
        fragor = []

        def sidor(path, params=None):
            fragor.append(dict(params))
            if "pagination_last_id" not in fragor[-1]:
                return {"events": [{"id": "1"}, {"id": "2"}],
                        "pagination": {"next_page": (
                            "?state=upcoming&type=football_match&limit=50"
                            "&sort=id&pagination_last_id=2")}}
            return {"events": [{"id": "3"}], "pagination": {"next_page": None}}

        self.client._get = sidor   # noqa: SLF001
        self.assertEqual(["1", "2", "3"],
                         [e["id"] for e in self.client.upcoming_events()])
        # nästa sida är Smarkets egen fråga, ordagrant
        self.assertEqual({"state": "upcoming", "type": "football_match",
                          "limit": "50", "sort": "id",
                          "pagination_last_id": "2"}, fragor[1])
        self.assertEqual(2, len(fragor))

    def test_ofullstandig_bladdring_ar_ett_fel_inte_en_kortare_lista(self):
        # En oläst sida får aldrig bli "matchen saknas hos Smarkets".
        def utan_slut(path, params=None):
            sista = int(dict(params).get("pagination_last_id", 0)) + 1
            return {"events": [{"id": str(sista)}],
                    "pagination": {"next_page": f"?pagination_last_id={sista}"}}

        self.client._get = utan_slut   # noqa: SLF001
        with mock.patch.object(smarkets, "MAX_PAGES", 3):
            with self.assertRaises(RuntimeError):
                self.client.upcoming_events()


if __name__ == "__main__":
    unittest.main()
