import unittest
from unittest import mock

from app import altenar
from app.pinnacle import Pinnacle


class PinnacleLiveTotalTests(unittest.TestCase):
    def test_groups_live_modes_and_keeps_all_open_lines(self):
        parent = {
            "id": 10, "startTime": "2026-08-18T18:00:00Z",
            "participants": [
                {"alignment": "home", "name": "Hammarby"},
                {"alignment": "away", "name": "AIK"},
            ],
        }
        matchups = [
            {"id": 11, "parentId": 10, "parent": parent,
             "status": "started", "type": "matchup", "liveMode": "danger_zone"},
            {"id": 12, "parentId": 10, "parent": parent,
             "status": "started", "type": "matchup", "liveMode": "live_delay"},
        ]
        markets = [
            {"matchupId": 12, "period": 0, "type": "total", "status": "open",
             "prices": [
                 {"designation": "over", "points": 2.5, "price": 105},
                 {"designation": "under", "points": 2.5, "price": -130},
                 {"designation": "over", "points": 3.0, "price": 150},
                 {"designation": "under", "points": 3.0, "price": -190},
             ]},
        ]
        pin = Pinnacle.__new__(Pinnacle)
        pin.last_age_s = 0

        def get(path):
            pin.last_age_s = 17 if "markets" in path else 4
            return markets if "markets" in path else matchups

        pin._get = get
        rows = pin.soccer_live_totals()

        self.assertEqual(1, len(rows))
        self.assertEqual("10", rows[0]["id"])
        self.assertEqual(2, len(rows[0]["offers"]))
        self.assertEqual(17, rows[0]["age_s"])
        self.assertEqual(2.5, rows[0]["ou"]["line"])


class AltenarLiveTotalTests(unittest.TestCase):
    def test_open_and_suspended_totals_are_distinct(self):
        payload = {
            "events": [
                {"id": 1, "sportId": 66, "status": 1,
                 "name": "Hammarby vs. AIK", "marketIds": [10]},
                {"id": 2, "sportId": 66, "status": 1,
                 "name": "GAIS vs. Elfsborg", "marketIds": [20]},
            ],
            "markets": [
                {"id": 10, "typeId": 18, "sv": "2.5", "oddIds": [101, 102]},
                {"id": 20, "typeId": 18, "sv": "3.5", "oddIds": [201, 202]},
            ],
            "odds": [
                {"id": 101, "typeId": 12, "price": 2.05, "oddStatus": 0},
                {"id": 102, "typeId": 13, "price": 1.75, "oddStatus": 0},
                {"id": 201, "typeId": 12, "price": 0, "oddStatus": 7},
                {"id": 202, "typeId": 13, "price": 0, "oddStatus": 7},
            ],
        }
        rows = altenar._live_rows(payload)
        self.assertEqual("captured", rows[0]["status"])
        self.assertEqual({"O": 2.05, "U": 1.75, "line": 2.5}, rows[0]["ou"])
        self.assertEqual("suspended", rows[1]["status"])
        self.assertIsNone(rows[1]["ou"])


class PinnacleLiveRefreshTests(unittest.TestCase):
    """Per-matchup-vägen förbi bulkens 905-sekunderscache."""

    def _client(self, responses: dict, ages: dict):
        pin = Pinnacle.__new__(Pinnacle)
        pin.last_age_s = 0
        self.calls = []

        def get(path):
            self.calls.append(path)
            for key, payload in responses.items():
                if key in path:
                    pin.last_age_s = ages.get(key, 0)
                    if isinstance(payload, Exception):
                        raise payload
                    return payload
            raise AssertionError(f"oväntad väg: {path}")

        pin._get = get
        return pin

    def test_farskt_pris_hamtas_per_matchup(self):
        markets = [
            {"matchupId": 12, "period": 0, "type": "total", "status": "open",
             "prices": [{"designation": "over", "points": 2.25, "price": -128},
                        {"designation": "under", "points": 2.25, "price": 105}]},
        ]
        pin = self._client({"/matchups/12/": markets}, {"/matchups/12/": 23})
        fresh = pin.refresh_live_total(["12"])

        self.assertEqual("captured", fresh["status"])
        self.assertEqual(23, fresh["age_s"])
        self.assertEqual(2.25, fresh["ou"]["line"])

    def test_suspenderad_marknad_skiljs_fran_ingen_marknad(self):
        stangd = [{"matchupId": 12, "period": 0, "type": "total",
                   "status": "suspended", "prices": []}]
        pin = self._client({"/matchups/12/": stangd}, {"/matchups/12/": 5})
        self.assertEqual("suspended", pin.refresh_live_total(["12"])["status"])

        # Tomt svar är INGEN observation — anroparen ska behålla bulkraden
        # i stället för att skriva "inte erbjuden" på en halv mätning.
        pin = self._client({"/matchups/12/": []}, {"/matchups/12/": 5})
        self.assertIsNone(pin.refresh_live_total(["12"]))

    def test_fel_pa_ett_barn_provar_nasta(self):
        markets = [
            {"matchupId": 13, "period": 0, "type": "total", "status": "open",
             "prices": [{"designation": "over", "points": 3.0, "price": 100},
                        {"designation": "under", "points": 3.0, "price": -120}]},
        ]
        pin = self._client(
            {"/matchups/12/": RuntimeError("500"), "/matchups/13/": markets},
            {"/matchups/13/": 8})
        fresh = pin.refresh_live_total(["12", "13"])

        self.assertEqual("captured", fresh["status"])
        self.assertEqual(3.0, fresh["ou"]["line"])
        self.assertEqual(2, len(self.calls))

    def test_utan_matchup_id_gors_inget_anrop(self):
        pin = self._client({}, {})
        self.assertIsNone(pin.refresh_live_total([]))
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()
