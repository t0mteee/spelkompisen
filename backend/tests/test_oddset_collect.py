import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import altenar, oddset
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

    def test_match_source_ids_are_write_once(self) -> None:
        self.store.oddset_upsert_match({
            "id": "m1", "league": "test", "home": "Other", "away": "Names",
            "start": self.start, "pinnacle_id": "p2", "kambi_id": "k2",
        }, prefer_names=True)

        match = self.store.oddset_match("m1")
        self.assertEqual("p1", match["pinnacle_id"])
        self.assertEqual("k1", match["kambi_id"])
        self.assertEqual("Other", match["home"])  # namn får fortfarande uppdateras

    def test_source_id_lookup_is_global_and_field_is_whitelisted(self) -> None:
        self.assertEqual(
            "m1",
            self.store.oddset_match_by_source_id(
                "pinnacle_id", "p1")["id"])
        with self.assertRaises(ValueError):
            self.store.oddset_match_by_source_id("id OR 1=1", "p1")

    def test_two_pinnacle_events_can_never_share_one_canonical_match(self) -> None:
        self.store.oddset_upsert_match({
            "id": "pin:100", "league": "test",
            "home": "Karlsruher SC", "away": "Inter",
            "start": self.start, "pinnacle_id": "100",
        })
        common = {
            "start": self.start, "status": "open",
            "odds_source": "pinnacle", "ah": None, "ou": None, "cor": None,
            "alt": {},
        }
        rows = [
            {**common, "id": "100", "home": "Karlsruher SC",
             "away": "Internazionale",
             "odds": {"1": 3.57, "X": 5.47, "2": 1.51}},
            {**common, "id": "200", "home": "Novara",
             "away": "Internazionale U23",
             "odds": {"1": 1.93, "X": 3.28, "2": 3.33}},
        ]

        self._collect(mock.Mock(return_value=rows))

        self.assertEqual("100", self.store.oddset_match("pin:100")["pinnacle_id"])
        novara = self.store.oddset_match("pin:200")
        self.assertIsNotNone(novara)
        self.assertEqual("Novara", novara["home"])
        prices = self.store.oddset_latest(["pin:100", "pin:200"])
        self.assertEqual(3.57, prices["pin:100"]["pinnacle"]["1x2"]["1"])
        self.assertEqual(1.93, prices["pin:200"]["pinnacle"]["1x2"]["1"])

    def test_corrupt_canonical_identity_is_quarantined_from_value(self) -> None:
        self.store.oddset_upsert_match({
            "id": "pin:100", "league": "test",
            "home": "Karlsruher SC", "away": "Inter",
            "start": self.start, "pinnacle_id": "200",
        })
        at = self.now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_save_odds(
            "pin:100", "pinnacle",
            {"1": 2.0, "X": 3.5, "2": 3.8}, at)
        self.store.oddset_save_odds(
            "pin:100", "svenskaspel",
            {"1": 6.4, "X": 4.0, "2": 1.5}, at)

        match = next(
            row for row in oddset.matches_payload(
                self.store, light=True, include_research=True)["matches"]
            if row["id"] == "pin:100")
        self.assertEqual("identity", match["data_conflict"]["kind"])
        self.assertEqual({}, match["value"])
        self.assertNotIn("steam", match)

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

    def test_missing_altenar_ou_in_list_suspends_previous_price(self) -> None:
        # Granskningsfix F1 (2026-07-26): matchen finns kvar i Altenars
        # lyckade listsvar men Ö/U-marknaden är plockad. Det gamla priset får
        # inte ligga kvar som spelbart spökpris i upp till 45 min — samma
        # invariant som cor-vägen och SvS-deep.
        league = {**self.league, "altenar": 999}
        event = {"id": "k1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.2, "X": 3.4, "2": 3.3}}
        with_ou = {"id": "a1", "home": "Home", "away": "Away",
                   "start": self.start,
                   "odds": {"1": 2.25, "X": 3.3, "2": 3.2},
                   "ou": {"O": 1.8, "U": 1.9, "line": 2.5}}
        without_ou = {key: value for key, value in with_ou.items()
                      if key != "ou"}
        books = [{"key": "ninjacasino", "name": "Ninja",
                  "altenar": "ninjacasinose"}]
        for rows in ([with_ou], [without_ou]):
            with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                    mock.patch.object(oddset, "pinnacle_league_index",
                                      return_value=[]), \
                    mock.patch.object(oddset.kambi, "league_events",
                                      return_value=[event]), \
                    mock.patch.object(oddset.kambi, "event_markets",
                                      return_value={}), \
                    mock.patch.object(oddset, "BOOKS", books), \
                    mock.patch.object(altenar, "league_events",
                                      return_value=rows), \
                    mock.patch.object(altenar, "event_markets",
                                      return_value={}), \
                    mock.patch.object(oddset.time, "sleep"):
                oddset.collect(self.store, leagues=[league], deep=False)

        market = self.store.oddset_latest(["m1"])["m1"]["ninjacasino"]["ou"]
        self.assertFalse(market["available"])

    def test_svs_deep_markets_use_call_time_not_round_start(self) -> None:
        # Granskningsfix F2 (2026-07-26): observationstidsregeln p.3 — en
        # ligaloop kan pågå 25 min, så deep-marknader ska bära per-anropstid,
        # aldrig varvstarten.
        base = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        ticks = {"n": 0}

        def fake_now() -> str:
            ticks["n"] += 1
            return (base + dt.timedelta(seconds=ticks["n"])).strftime(
                "%Y-%m-%dT%H:%M:%SZ")

        event = {"id": "k1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.2, "X": 3.4, "2": 3.3}}
        deep = {"ah": {"H": 1.9, "A": 1.95, "line": -0.25}}
        with mock.patch.object(oddset, "_now_iso", side_effect=fake_now), \
                mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[event]), \
                mock.patch.object(oddset.kambi, "event_markets", return_value=deep), \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(oddset.time, "sleep"):
            report = oddset.collect(self.store, leagues=[self.league], deep=False)

        ah = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["ah"]
        self.assertGreater(ah["last_seen_at"], report["at"])

    def test_book_cdn_age_backdates_confirmation(self) -> None:
        # Granskningsfix F3 (2026-07-26): bokssidans "kvar"-bevis ska dra av
        # HTTP Age precis som Pinnacle — annars kan ett CDN-cachat svar
        # "återbekräfta" ett pris efter sharpflytten.
        league = {**self.league, "altenar": 999}
        ninja = {"id": "a1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.25, "X": 3.3, "2": 3.2}}
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index",
                                  return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events",
                                  return_value=[]), \
                mock.patch.object(
                    oddset, "BOOKS",
                    [{"key": "ninjacasino", "name": "Ninja",
                      "altenar": "ninjacasinose"}]), \
                mock.patch.object(altenar, "league_events",
                                  return_value=[ninja]), \
                mock.patch.object(altenar, "last_age_s", 120), \
                mock.patch.object(altenar, "event_markets", return_value={}), \
                mock.patch.object(oddset.time, "sleep"):
            report = oddset.collect(self.store, leagues=[league], deep=False)

        seen = dt.datetime.fromisoformat(
            self.store.oddset_latest(
                ["m1"])["m1"]["ninjacasino"]["1x2"]["last_seen_at"]
            .replace("Z", "+00:00"))
        retrieved = dt.datetime.fromisoformat(
            report["at"].replace("Z", "+00:00"))
        self.assertAlmostEqual(
            120, (retrieved - seen).total_seconds(), delta=5)

    def test_altenar_corners_are_fetched_from_event_details(self) -> None:
        league = {**self.league, "altenar": 999}
        event = {"id": "k1", "home": "Home", "away": "Away", "start": self.start,
                 "odds": {"1": 2.2, "X": 3.4, "2": 3.3}}
        ninja = {**event, "id": "a1",
                 "odds": {"1": 2.25, "X": 3.3, "2": 3.2},
                 "ou": {"O": 1.8, "U": 1.9, "line": 2.5}}
        corner = {"cor": {"O": 1.7, "U": 2.05, "line": 9.5}}
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index", return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events", return_value=[event]), \
                mock.patch.object(oddset.kambi, "event_markets", return_value={}), \
                mock.patch.object(
                    oddset, "BOOKS",
                    [{"key": "ninjacasino", "name": "Ninja",
                      "altenar": "ninjacasinose"}]), \
                mock.patch.object(altenar, "league_events", return_value=[ninja]), \
                mock.patch.object(
                    altenar, "event_markets", return_value=corner) as details, \
                mock.patch.object(oddset.time, "sleep"):
            oddset.collect(self.store, leagues=[league], deep=False)

        details.assert_called_once_with(
            "a1", integration="ninjacasinose", strict=True)
        latest = self.store.oddset_latest(["m1"])["m1"]["ninjacasino"]
        self.assertEqual(9.5, latest["cor"]["line"])
        self.assertEqual(1.7, latest["cor"]["O"])
        self.assertEqual(2.05, latest["cor"]["U"])
        self.assertTrue(latest["cor"]["available"])


class ResearchLeagueIsolationTests(unittest.TestCase):
    def test_global_live_health_survives_regular_league_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                store.oddset_record_source_health(
                    "flashscore", "-", "live", "2026-07-25T08:00:00Z",
                    True, 2)
                store.oddset_record_source_health(
                    "pinnacle", "hidden-test", "markets",
                    "2026-07-25T08:00:00Z", True, 2)
                payload = oddset.matches_payload(store, light=True)
            finally:
                store.close()

        health = {(row["source"], row["scope"])
                  for row in payload["source_health"]}
        self.assertIn(("flashscore", "live"), health)
        self.assertNotIn(("pinnacle", "markets"), health)

    def test_disconnected_sources_are_filtered_out_of_health(self) -> None:
        """`oddset_source_health` städas aldrig, så en urkopplad källa ligger
        kvar och åldras tyst till "fel" i UI:t. Sofascore stod som livekälla
        timmar efter bortkopplingen (2026-08-06) och Betinia sedan
        2026-07-24. Filtret härleds ur källistorna, så nästa bortkoppling
        städar sig själv."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                for dead in ("sofascore", "betinia"):
                    store.oddset_record_source_health(
                        dead, "-", "live", "2026-07-25T08:00:00Z", True, 2)
                store.oddset_record_source_health(
                    "flashscore", "-", "live", "2026-07-25T08:00:00Z", True, 2)
                payload = oddset.matches_payload(store, light=True)
            finally:
                store.close()

        sources = {row["source"] for row in payload["source_health"]}
        self.assertNotIn("sofascore", sources)
        self.assertNotIn("betinia", sources)
        self.assertIn("flashscore", sources)
        # spärren mot Smarkets som BOK är en annan sak och står kvar
        self.assertIn("smarkets", oddset.active_sources())

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

    def test_europaligorna_ar_fullt_foljda(self) -> None:
        """Samans beslut 2026-08-07 inför säsongsstarten: PL, Serie A, La Liga
        och Bundesliga följs som Allsvenskan — sidoböcker, deep, värdesignaler,
        CLV och notiser.

        Spärren behövdes aldrig för SHARP-tiern: den är ren oddsjämförelse och
        har inget med V2.2:s modellhypotes att göra. V2.2 kör vidare på sin
        EGEN `SCOPE_LEAGUES`.
        """
        stora = {"premier_league", "serie_a", "la_liga", "bundesliga"}
        self.assertTrue(stora <= oddset.ACTIONABLE_LEAGUE_KEYS)
        self.assertTrue(stora <= oddset.VISIBLE_LEAGUE_KEYS)
        self.assertFalse(stora & set(oddset.RESEARCH_LEAGUE_KEYS))
        # V2.2 äger fortfarande sitt eget scope, oberoende av ligaflaggan
        from app import oddset_v22
        self.assertTrue(stora <= set(oddset_v22.SCOPE_LEAGUES))

    def test_nya_toppligor_ar_synliga_sharp_ligor_med_verifierade_idn(self) -> None:
        expected = {
            "danish_superliga": (1913, "football/denmark/superligaen"),
            "belgian_pro_league": (1817, "football/belgium/jupiler_pro_league"),
            "primeira_liga": (2386, "football/portugal/primeira_liga"),
            "bolivian_primera": (5595, "football/bolivia"),
        }
        by_key = {league["key"]: league for league in oddset.LEAGUES}
        from app import oddset_data, oddset_v22
        for key, (pin_id, kambi_path) in expected.items():
            self.assertEqual(pin_id, by_key[key]["pin_id"])
            self.assertEqual(kambi_path, by_key[key]["kambi"])
            self.assertIn(key, oddset.ACTIONABLE_LEAGUE_KEYS)
            self.assertIn(key, oddset.VISIBLE_LEAGUE_KEYS)
            self.assertNotIn(key, oddset_data.MODEL_LEAGUES)
            self.assertNotIn(key, oddset_v22.SCOPE_LEAGUES)

    def test_visibility_and_actionability_are_independent_properties(self) -> None:
        """Mekanismen finns kvar även när ingen liga använder den just nu —
        synlig liga får aldrig automatiskt bli actionable."""
        self.assertEqual(
            {lg["key"] for lg in oddset.LEAGUES},
            oddset.ACTIONABLE_LEAGUE_KEYS | set(oddset.RESEARCH_LEAGUE_KEYS))
        self.assertTrue(
            oddset.ACTIONABLE_LEAGUE_KEYS <= oddset.VISIBLE_LEAGUE_KEYS)

    def test_europaligorna_far_vardefalt_som_ovriga(self) -> None:
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
                # Färska priser från båda källorna → båda ligorna ska nu få
                # värdeunderlag. Före 2026-08-07 sanerades PL-raden bort.
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

        # Båda ligorna finns, båda med odds OCH värdeunderlag. Före
        # 2026-08-07 saknade PL-raden `value` och bar en `research`-flagga.
        by_id = {row["id"]: row for row in regular["matches"]}
        self.assertEqual({"public", "research"}, set(by_id))
        self.assertIn("pinnacle", by_id["research"]["odds"])
        self.assertIn("value", by_id["research"])
        self.assertIn("value", by_id["public"])
        self.assertNotIn("research", by_id["research"],
                         "ingen forskningsmärkning kvar")
        # Den interna payloaden ger samma sak (den var ofiltrerad redan förr).
        internal_research = next(
            row for row in internal["matches"] if row["id"] == "research")
        self.assertIn("value", internal_research)
        # Ligalistan bär ingen forskningsflagga längre.
        leagues = {row["key"]: row for row in regular["leagues"]}
        self.assertIn("premier_league", leagues)
        self.assertNotIn("research", leagues["premier_league"])
        self.assertNotIn("research", leagues["allsvenskan"])

    def test_next_round_shown_when_list_window_is_empty(self) -> None:
        # Säsongsuppehåll: premiären ligger utanför 10-dagarsfönstret. UI-
        # payloaden visar då ligans nästa omgång; den interna
        # insamlings-payloaden behåller det strikta fönstret.
        #
        # Gällde tidigare bara forskningsligor och blev tyst död kod när de
        # fyra stora gjordes fullt följda — problemet är allmänt.
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
        # Båda ligorna saknar match i fönstret och får därför sin nästa
        # omgång — men bara omgången, aldrig pl-3 en vecka senare.
        self.assertEqual({"pl-1", "pl-2", "future-public"}, ids)
        self.assertNotIn("pl-3", ids)
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

    def test_europaligorna_hamtar_deep_och_sidobocker(self) -> None:
        """Före 2026-08-07 spärrade `research_only` både deep-marknader och
        sidoböcker för de fyra stora — därför fanns inga AH/Ö/U och ingen
        Expekt/Ninja att jämföra mot. Nu hämtas de som för Allsvenskan."""
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

        deep.assert_called()


class MultiSourceLeagueTests(unittest.TestCase):
    """Europacuperna är TVÅ ligor hos Pinnacle och TVÅ vägar hos Kambi
    (huvudturnering + kval) — collect ska hämta och slå ihop samtliga."""

    def test_cupliga_hamtar_alla_pin_id_och_kambi_vagar(self) -> None:
        league = {"key": "cuptest", "name": "Cuptest",
                  "pin_ids": [11, 12],
                  "kambi_paths": ["football/cup",
                                  "football/cup_qualification"],
                  "altenar": None}
        start = (dt.datetime.now(dt.timezone.utc) +
                 dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def pin_index(_pin, league_id):
            return [{"id": f"p{league_id}", "home": f"Hemma{league_id}",
                     "away": f"Borta{league_id}", "start": start,
                     "odds_source": "pinnacle",
                     "odds": {"1": 2.0, "X": 3.5, "2": 3.8}}]

        def kambi_events(path, **_kw):
            stage = "kval" if "qualification" in path else "huvud"
            return [{"id": f"k-{stage}", "home": f"KHemma-{stage}",
                     "away": f"KBorta-{stage}", "start": start,
                     "odds": {"1": 2.1, "X": 3.4, "2": 3.6}}]

        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with mock.patch.object(oddset, "Pinnacle",
                                       return_value=_Pin()), \
                        mock.patch.object(oddset, "pinnacle_league_index",
                                          side_effect=pin_index) as pin_calls, \
                        mock.patch.object(oddset.kambi, "league_events",
                                          side_effect=kambi_events) as kb_calls, \
                        mock.patch.object(oddset, "BOOKS", []):
                    oddset.collect(store, leagues=[league], deep=False)
                fetched_ids = [c.args[1] for c in pin_calls.call_args_list]
                fetched_paths = [c.args[0] for c in kb_calls.call_args_list]
                ms = store.oddset_matches(since="2000-01-01T00:00:00Z",
                                          until="2100-01-01T00:00:00Z")
            finally:
                store.close()

        self.assertEqual([11, 12], fetched_ids)
        self.assertEqual(["football/cup", "football/cup_qualification"],
                         fetched_paths)
        # 2 Pinnacle-batchar + 2 Kambi-batchar, ingen tappad på vägen
        self.assertEqual(4, len([m for m in ms if m["league"] == "cuptest"]))

    def test_alias_kollapsar_forkortning_och_felstavning(self) -> None:
        """IBV-fallet: Pinnacle 'IBV' och Kambi 'ÍB Vestmennaeyjar' ska bli
        samma identitet. Aliaset sitter SIST i norm_team så exakta, fuzzy
        och radarjämförelser alla ser kanoniskt namn."""
        self.assertEqual("vestmannaeyjar", oddset.norm_team("IBV"))
        self.assertEqual("vestmannaeyjar",
                         oddset.norm_team("ÍB Vestmennaeyjar"))
        self.assertEqual(1.0, oddset._team_sim("IBV", "ÍB Vestmennaeyjar"))
        # Okända namn passerar orörda — listan är observerade par, ingen regel.
        self.assertEqual("fram reykjavik", oddset.norm_team("Fram Reykjavík"))

    def test_vanlig_liga_faller_tillbaka_pa_singelfalten(self) -> None:
        self.assertEqual([1728], oddset._pin_ids(
            {"key": "allsvenskan", "pin_id": 1728}))
        self.assertEqual(["football/sweden/allsvenskan"], oddset._kambi_paths(
            {"key": "allsvenskan", "kambi": "football/sweden/allsvenskan"}))


if __name__ == "__main__":
    unittest.main()
