import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset
from app.pinnacle import Pinnacle, cache_adjusted_iso
from app.storage import Storage


class _Pin:
    def __init__(self, age_s: int = 0) -> None:
        self.last_age_s = age_s

    def reset_cache_age(self) -> None:
        # Testdubbeln behåller den förvalda åldern för nästa svar.
        pass

    def close(self) -> None:
        pass


class PinnacleCacheAgeTests(unittest.TestCase):
    def test_http_age_backdates_price_observation(self) -> None:
        self.assertEqual(
            "2026-07-25T10:45:00Z",
            cache_adjusted_iso("2026-07-25T11:00:00Z", 900),
        )

    def test_invalid_age_never_moves_observation_into_future(self) -> None:
        self.assertEqual(
            "2026-07-25T11:00:00Z",
            cache_adjusted_iso("2026-07-25T11:00:00Z", -30),
        )

    def test_price_endpoint_age_wins_over_matchup_endpoint_age(self) -> None:
        matchup_response = mock.MagicMock(
            headers={"age": "600"}, json=mock.Mock(return_value=[]))
        market_response = mock.MagicMock(
            headers={"age": "60"}, json=mock.Mock(return_value=[]))
        pin = Pinnacle.__new__(Pinnacle)
        pin._client = mock.MagicMock()
        pin._client.get.side_effect = [matchup_response, market_response]
        pin.last_age_s = 0

        self.assertEqual([], pin.soccer_index())
        self.assertEqual(60, pin.last_age_s)


class CollectionPresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime.now(dt.timezone.utc)
        self.start = (self.now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.league = {"key": "test", "name": "Test", "pin_id": 1,
                       "kambi": "football/test", "altenar": None}
        self.store.oddset_upsert_match({
            "id": "m1", "league": "test", "home": "Home", "away": "Away",
            "start": self.start, "pinnacle_id": "p1", "kambi_id": "k1",
        })
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8},
            self.now.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _collect(self, pin_rows) -> dict:
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", pin_rows), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[]), \
                mock.patch.object(oddset, "BOOKS", []):
            return oddset.collect(self.store, leagues=[self.league], deep=False)

    def test_failed_source_does_not_suspend_last_confirmed_price(self) -> None:
        report = self._collect(mock.Mock(side_effect=RuntimeError("blocked")))

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertTrue(market["available"])
        self.assertTrue(any("blocked" in e for e in report["errors"]))
        health = next(r for r in self.store.oddset_source_health()
                      if r["source"] == "pinnacle")
        self.assertFalse(health["ok"])

    def test_successful_response_without_event_suspends_price(self) -> None:
        self._collect(mock.Mock(return_value=[]))

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertFalse(market["available"])

    def _collect_cached(self, odds: dict, age_s: int = 900):
        row = {
            "id": "p1", "home": "Home", "away": "Away", "start": self.start,
            "status": "open", "odds": odds,
            "odds_source": "pinnacle", "ah": None, "ou": None, "cor": None,
            "alt": {},
        }
        pin = _Pin(age_s=age_s)
        with mock.patch.object(oddset, "Pinnacle", return_value=pin), \
                mock.patch.object(
                    oddset, "pinnacle_league_index", return_value=[row]), \
                mock.patch.object(
                    oddset.kambi, "league_events", return_value=[]), \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(
                    oddset.oddset_value, "log_and_notify",
                    return_value={"logged": 0, "pushed": 0, "gated": 0}) as notify:
            report = oddset.collect(
                self.store, leagues=[self.league], deep=False)
        observed = dt.datetime.fromisoformat(
            self.store.oddset_latest(
                ["m1"])["m1"]["pinnacle"]["1x2"]["last_seen_at"]
            .replace("Z", "+00:00"))
        return report, observed, notify

    def test_cached_pinnacle_price_uses_origin_time_and_is_not_current_presence(
            self) -> None:
        # FÖRSTA observationen av en match ur ett 900 s gammalt CDN-objekt:
        # observationstiden ska bakåtdateras till objektets ursprung, och
        # priset får INTE räknas som "sett i detta varv" av notisgrinden.
        # (setUp:s m1 har redan en färsk bekräftelse — därför en ny match.)
        self.store.oddset_upsert_match({
            "id": "m2", "league": "test", "home": "Ny", "away": "Match",
            "start": self.start, "pinnacle_id": "p2",
        })
        report, notify = self._collect_cached_new_match()
        observed = dt.datetime.fromisoformat(
            self.store.oddset_latest(
                ["m2"])["m2"]["pinnacle"]["1x2"]["last_seen_at"]
            .replace("Z", "+00:00"))
        retrieved = dt.datetime.fromisoformat(
            report["at"].replace("Z", "+00:00"))
        self.assertAlmostEqual(
            900, (retrieved - observed).total_seconds(), delta=2)
        self.assertEqual(
            900, report["leagues"]["test"]["pinnacle_cache_age_s"])
        present = notify.call_args.kwargs["present"]
        self.assertNotIn(("m2", "pinnacle", "1x2"), present)

    def _collect_cached_new_match(self, age_s: int = 900):
        row = {
            "id": "p2", "home": "Ny", "away": "Match", "start": self.start,
            "status": "open", "odds": {"1": 2.5, "X": 3.4, "2": 3.1},
            "odds_source": "pinnacle", "ah": None, "ou": None, "cor": None,
            "alt": {},
        }
        pin = _Pin(age_s=age_s)
        with mock.patch.object(oddset, "Pinnacle", return_value=pin), \
                mock.patch.object(
                    oddset, "pinnacle_league_index", return_value=[row]), \
                mock.patch.object(
                    oddset.kambi, "league_events", return_value=[]), \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(
                    oddset.oddset_value, "log_and_notify",
                    return_value={"logged": 0, "pushed": 0, "gated": 0}) as notify:
            report = oddset.collect(
                self.store, leagues=[self.league], deep=False)
        return report, notify

    def test_stale_cache_object_is_skipped_not_written(self) -> None:
        # Ett CDN-objekt vars ursprung är ÄLDRE än vår senaste bekräftelse bär
        # ingen ny information om nuvarande pris. Det får varken skrivas
        # bakåtdaterat (rad före tidigare observation) eller med nutid (lögn
        # om färskhet) — det ska hoppas över.
        before = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self._collect_cached({"1": 2.5, "X": 3.4, "2": 3.1})
        after = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertEqual(before["1"], after["1"])          # priset orört
        self.assertEqual(before["last_seen_at"], after["last_seen_at"])

    def test_cache_age_never_moves_a_confirmed_observation_backwards(self) -> None:
        # MONOTONISPÄRR (2026-07-25): setUp har redan bekräftat samma pris NU.
        # Ett cacheobjekt från 900 s tillbaka bär inte ny information och får
        # därför inte flytta färskhetsklockan bakåt — annars blir raden osynlig
        # för "senaste"-sorteringen och nästa varv skriver en falsk
        # rörelsepunkt för ett oförändrat pris.
        before = self.store.oddset_latest(
            ["m1"])["m1"]["pinnacle"]["1x2"]["last_seen_at"]
        _, observed, _ = self._collect_cached({"1": 2.0, "X": 3.5, "2": 3.8})
        self.assertEqual(
            before, observed.strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_fast_poll_fetches_deep_markets_inside_three_hours(self) -> None:
        event = {"id": "k1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.2, "X": 3.4, "2": 3.3}}
        deep = {"ah": {"H": 1.9, "A": 1.95, "line": -0.25},
                "ou": {"O": 1.88, "U": 1.98, "line": 2.75}}
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[event]), \
                mock.patch.object(oddset.kambi, "event_markets", return_value=deep) as markets, \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(oddset.time, "sleep"):
            oddset.collect(self.store, leagues=[self.league], deep=False)

        markets.assert_called_once()
        latest = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]
        self.assertTrue(latest["ah"]["available"])
        self.assertTrue(latest["ou"]["available"])


class ResearchLeagueIsolationTests(unittest.TestCase):
    def test_global_live_health_survives_regular_league_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                store.oddset_record_source_health(
                    "sofascore", "-", "live", "2026-07-25T08:00:00Z",
                    True, 2)
                store.oddset_record_source_health(
                    "pinnacle", "hidden-test", "markets",
                    "2026-07-25T08:00:00Z", True, 2)
                payload = oddset.matches_payload(store, light=True)
            finally:
                store.close()

        health = {(row["source"], row["scope"])
                  for row in payload["source_health"]}
        self.assertIn(("sofascore", "live"), health)
        self.assertNotIn(("pinnacle", "markets"), health)

    def test_fast_research_poll_uses_known_moneyline_single_endpoint(self) -> None:
        class Pin:
            def _get(self, path):
                self.path = path
                return [{
                    "matchupId": 7, "period": 0, "type": "moneyline",
                    "prices": [
                        {"designation": "home", "price": -110},
                        {"designation": "draw", "price": 250},
                        {"designation": "away", "price": 300},
                    ],
                }]

        pin = Pin()
        rows = oddset.pinnacle_known_moneylines(pin, 1980, [{
            "id": "pin:7", "pinnacle_id": "7", "home": "Home",
            "away": "Away", "start": "2026-08-21T19:00:00Z",
        }])

        self.assertEqual("/leagues/1980/markets/straight", pin.path)
        self.assertEqual(1, len(rows))
        self.assertAlmostEqual(1.91, rows[0]["odds"]["1"])
        self.assertAlmostEqual(3.5, rows[0]["odds"]["X"])
        self.assertAlmostEqual(4.0, rows[0]["odds"]["2"])

    def test_visibility_and_actionability_are_independent_properties(self) -> None:
        # Beställning 2026-07-24: forskningsligorna SYNS i ordinarie vyn men
        # är fortsatt icke-actionable. Egenskaperna får aldrig smälta ihop.
        research = {"premier_league", "serie_a", "la_liga", "bundesliga"}
        self.assertEqual(research, set(oddset.RESEARCH_LEAGUE_KEYS))
        self.assertTrue(research <= oddset.VISIBLE_LEAGUE_KEYS)
        self.assertFalse(research & oddset.ACTIONABLE_LEAGUE_KEYS)
        self.assertEqual(
            {lg["key"] for lg in oddset.LEAGUES},
            oddset.ACTIONABLE_LEAGUE_KEYS | oddset.RESEARCH_LEAGUE_KEYS)

    def test_research_leagues_visible_but_sanitized_in_regular_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            start = (now + dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                store.oddset_upsert_match({
                    "id": "public", "league": "allsvenskan", "home": "A",
                    "away": "B", "start": start,
                })
                store.oddset_upsert_match({
                    "id": "research", "league": "premier_league", "home": "C",
                    "away": "D", "start": start,
                })
                # Färska priser från båda källorna → attach_value skulle ge
                # ett värdeunderlag; ordinarie payloaden ska ändå sanera det.
                for mid in ("public", "research"):
                    store.oddset_save_odds(
                        mid, "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, at)
                    store.oddset_save_odds(
                        mid, "svenskaspel", {"1": 2.3, "X": 3.4, "2": 3.6}, at)

                regular = oddset.matches_payload(store, light=True)
                internal = oddset.matches_payload(
                    store, light=True, include_research=True)
            finally:
                store.close()

        # Synlig: forskningsmatchen finns i ordinarie payloaden, märkt,
        # med odds och rörelseserier kvar.
        by_id = {row["id"]: row for row in regular["matches"]}
        self.assertEqual({"public", "research"}, set(by_id))
        self.assertTrue(by_id["research"]["research"])
        self.assertNotIn("research", by_id["public"])
        self.assertIn("pinnacle", by_id["research"]["odds"])
        # Icke-actionable: inget värde-/modellunderlag i ordinarie payloaden…
        self.assertNotIn("value", by_id["research"])
        self.assertNotIn("model", by_id["research"])
        self.assertIn("value", by_id["public"])
        # …men den interna insamlings-payloaden är ofiltrerad (ledger/V2.2).
        internal_research = next(
            row for row in internal["matches"] if row["id"] == "research")
        self.assertIn("value", internal_research)
        # Ligalistan bär forskningsflaggan så UI:t kan märka filtret.
        leagues = {row["key"]: row for row in regular["leagues"]}
        self.assertIn("premier_league", leagues)
        self.assertTrue(leagues["premier_league"].get("research"))
        self.assertNotIn("research", leagues["allsvenskan"])

    def test_research_next_round_shown_when_list_window_is_empty(self) -> None:
        # Säsongsuppehåll: premiären ligger utanför 10-dagarsfönstret. UI-
        # payloaden visar då forskningsligans nästa omgång; ordinarie ligor
        # och den interna insamlings-payloaden behåller det strikta fönstret.
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            premiere = (now + dt.timedelta(days=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
            same_round = (now + dt.timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
            next_round = (now + dt.timedelta(days=28)).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                store.oddset_upsert_match({
                    "id": "pl-1", "league": "premier_league", "home": "A",
                    "away": "B", "start": premiere,
                })
                store.oddset_upsert_match({
                    "id": "pl-2", "league": "premier_league", "home": "C",
                    "away": "D", "start": same_round,
                })
                store.oddset_upsert_match({
                    "id": "pl-3", "league": "premier_league", "home": "E",
                    "away": "F", "start": next_round,
                })
                store.oddset_upsert_match({
                    "id": "future-public", "league": "allsvenskan", "home": "G",
                    "away": "H", "start": premiere,
                })

                regular = oddset.matches_payload(store, light=True)
                internal = oddset.matches_payload(
                    store, light=True, include_research=True)
            finally:
                store.close()

        ids = {row["id"] for row in regular["matches"]}
        self.assertEqual({"pl-1", "pl-2"}, ids)   # omgången, inte pl-3/public
        self.assertTrue(all(row["research"] for row in regular["matches"]))
        self.assertFalse({row["id"] for row in internal["matches"]})

    def test_collect_never_passes_research_matches_to_value_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            start = (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            league = next(row for row in oddset.LEAGUES
                          if row["key"] == "premier_league")
            try:
                store.oddset_upsert_match({
                    "id": "research", "league": "premier_league", "home": "C",
                    "away": "D", "start": start,
                })
                store.oddset_save_odds(
                    "research", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, at)
                store.oddset_save_odds(
                    "research", "svenskaspel", {"1": 2.3, "X": 3.4, "2": 3.6}, at)
                with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                        mock.patch.object(oddset, "pinnacle_league_index",
                                          return_value=[]), \
                        mock.patch.object(oddset.kambi, "league_events",
                                          return_value=[]), \
                        mock.patch.object(oddset.oddset_value, "log_and_notify",
                                          return_value={}) as spy:
                    oddset.collect(store, leagues=[league], deep=False)
            finally:
                store.close()

        spy.assert_called_once()
        passed = spy.call_args.args[1]
        self.assertFalse([m for m in passed
                          if m.get("league") in oddset.RESEARCH_LEAGUE_KEYS])

    def test_research_leagues_skip_deep_markets_and_sidebooks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            now = dt.datetime.now(dt.timezone.utc)
            start = (now + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            league = next(row for row in oddset.LEAGUES
                          if row["key"] == "premier_league")
            event = {"id": "k-eu", "home": "Home", "away": "Away",
                     "start": start, "odds": {"1": 2.0, "X": 3.5, "2": 4.0}}
            try:
                with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                        mock.patch.object(oddset, "pinnacle_league_index",
                                          return_value=[]), \
                        mock.patch.object(oddset.kambi, "league_events",
                                          return_value=[event]), \
                        mock.patch.object(oddset.kambi, "event_markets") as deep:
                    oddset.collect(store, leagues=[league], deep=False)
            finally:
                store.close()

        deep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
