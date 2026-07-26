"""Matchbook = TREDJE marknadsreferensen, ENDAST skugga (2026-07-27).

Fixturbaserat (inga nätanrop). Låser fyra saker: parsningen (bästa back +
likviditet ur samma prisnivå), identitetsdisciplinen (aldrig nya matchrader,
konflikt => hoppa), skuggspärren (matchbook ∉ BOOKS/ANCHOR_SOURCES och blir
aldrig en bok i värdemotorn — samma klass av grind som AnchorSourceTests)
samt den monotoniska likviditetsserien.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import matchbook, oddset, oddset_value, smarkets
from app.storage import Storage


def _price(odds: float, amount: float, side: str = "back") -> dict:
    return {"available-amount": amount, "currency": "EUR",
            "odds-type": "DECIMAL", "odds": odds, "decimal-odds": odds,
            "side": side, "exchange-type": "back-lay"}


def _runner(name: str, prices: list, status: str = "open") -> dict:
    return {"name": name, "status": status, "prices": prices}


def _event(eid=901, name="Hammarby vs Djurgarden",
           start="2026-07-27T17:00:00.000Z",
           competition="sweden-allsvenskan", runners=None,
           market_name="Match Odds", market_status="open") -> dict:
    """Minimal spegling av /edge/rest/events-svaret (verifierat 2026-07-27)."""
    if runners is None:
        runners = [
            _runner("Hammarby", [_price(2.5, 100.0), _price(2.4, 500.0)]),
            _runner("Djurgarden", [_price(3.2, 50.0)]),
            _runner("Draw", [_price(3.4, 25.0)]),
        ]
    return {"id": eid, "name": name, "start": start, "sport-id": 15,
            "status": "open",
            "meta-tags": [
                {"id": 15, "name": "Soccer", "type": "SPORT",
                 "url-name": "soccer"},
                {"id": 99, "name": "Liga", "type": "COMPETITION",
                 "url-name": competition},
            ],
            "markets": [{"name": market_name, "market-type": "one_x_two",
                         "status": market_status, "runners": runners}]}


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.client = matchbook.Matchbook.__new__(matchbook.Matchbook)
        self.client.last_age_s = 0

    def test_basta_back_och_likviditet_fran_samma_prisniva(self):
        rows = self.client.league_events(
            "allsvenskan", strict=True, events=[_event()])
        self.assertEqual(1, len(rows))
        row = rows[0]
        # bästa back = HÖGSTA odds; likviditeten är beloppet på DEN nivån,
        # inte summan över djupet (2.4-nivåns 500 EUR får inte läcka in).
        self.assertEqual(2.5, row["odds"]["1"])
        self.assertEqual(100.0, row["liquidity"]["1"])
        self.assertEqual(3.4, row["odds"]["X"])
        self.assertEqual(25.0, row["liquidity"]["X"])
        self.assertEqual(3.2, row["odds"]["2"])
        self.assertEqual(50.0, row["liquidity"]["2"])
        self.assertEqual("901", row["id"])

    def test_teckenmappning_ar_namnbaserad_inte_ordningsbaserad(self):
        ev = _event(runners=[
            _runner("Draw", [_price(3.4, 25.0)]),
            _runner("Djurgarden", [_price(3.2, 50.0)]),
            _runner("Hammarby", [_price(2.5, 100.0)]),
        ])
        row = self.client.league_events(
            "allsvenskan", strict=True, events=[ev])[0]
        self.assertEqual(2.5, row["odds"]["1"])
        self.assertEqual(3.2, row["odds"]["2"])
        self.assertEqual(3.4, row["odds"]["X"])

    def test_starttid_normaliseras_till_projektformat(self):
        row = self.client.league_events(
            "allsvenskan", strict=True, events=[_event()])[0]
        self.assertEqual("2026-07-27T17:00:00Z", row["start"])
        self.assertEqual("Hammarby", row["home"])
        self.assertEqual("Djurgarden", row["away"])

    def test_ofullstandig_orderbok_ger_ingen_halv_rad(self):
        ev = _event(runners=[
            _runner("Hammarby", [_price(2.5, 100.0)]),
            _runner("Djurgarden", []),          # inget back-pris
            _runner("Draw", [_price(3.4, 25.0)]),
        ])
        self.assertEqual([], self.client.league_events(
            "allsvenskan", strict=True, events=[ev]))

    def test_suspenderad_runner_hoppar_eventet(self):
        ev = _event(runners=[
            _runner("Hammarby", [_price(2.5, 100.0)]),
            _runner("Djurgarden", [_price(3.2, 50.0)], status="suspended"),
            _runner("Draw", [_price(3.4, 25.0)]),
        ])
        self.assertEqual([], self.client.league_events(
            "allsvenskan", strict=True, events=[ev]))

    def test_okand_runner_gissar_aldrig_sida(self):
        ev = _event(runners=[
            _runner("Hammarby B", [_price(2.5, 100.0)]),
            _runner("Djurgarden", [_price(3.2, 50.0)]),
            _runner("Draw", [_price(3.4, 25.0)]),
        ])
        self.assertEqual([], self.client.league_events(
            "allsvenskan", strict=True, events=[ev]))

    def test_bara_oppen_match_odds_marknad_raknas(self):
        stangd = _event(market_status="suspended")
        halvtid = _event(market_name="Half Time")
        self.assertEqual([], self.client.league_events(
            "allsvenskan", strict=True, events=[stangd, halvtid]))

    def test_lay_priser_raknas_aldrig_som_back(self):
        ev = _event(runners=[
            _runner("Hammarby", [_price(2.5, 100.0),
                                 _price(9.9, 999.0, side="lay")]),
            _runner("Djurgarden", [_price(3.2, 50.0)]),
            _runner("Draw", [_price(3.4, 25.0)]),
        ])
        row = self.client.league_events(
            "allsvenskan", strict=True, events=[ev])[0]
        self.assertEqual(2.5, row["odds"]["1"])

    def test_fel_liga_filtreras_och_okand_liganyckel_ger_tomt(self):
        ev = _event(competition="brazil-serie-a")
        self.assertEqual([], self.client.league_events(
            "allsvenskan", strict=True, events=[ev]))
        self.assertEqual([], self.client.league_events(
            "bomben", strict=True, events=[_event()]))

    def test_paginering_foljer_total(self):
        pages = []

        def fake_get(path, params=None):
            pages.append(params["offset"])
            if params["offset"] == 0:
                return {"total": 2 * matchbook.PER_PAGE + 1,
                        "events": [_event(eid=i)
                                   for i in range(matchbook.PER_PAGE)]}
            if params["offset"] == matchbook.PER_PAGE:
                return {"total": 2 * matchbook.PER_PAGE + 1,
                        "events": [_event(eid=1000 + i)
                                   for i in range(matchbook.PER_PAGE)]}
            return {"total": 2 * matchbook.PER_PAGE + 1,
                    "events": [_event(eid=9999)]}

        self.client._get = fake_get   # noqa: SLF001
        events = self.client.upcoming_events(
            after_iso="2026-07-27T15:00:00Z", until_iso="2026-07-27T18:00:00Z")
        self.assertEqual(2 * matchbook.PER_PAGE + 1, len(events))
        self.assertEqual([0, matchbook.PER_PAGE, 2 * matchbook.PER_PAGE],
                         pages)

    def test_fel_ger_tom_lista_utan_strict(self):
        def boom(path, params=None):
            raise RuntimeError("nätverksfel")
        self.client._get = boom   # noqa: SLF001
        self.assertEqual([], self.client.league_events("allsvenskan"))
        with self.assertRaises(RuntimeError):
            self.client.league_events("allsvenskan", strict=True)


class ShadowBarrierTests(unittest.TestCase):
    """🎯 ANKARE ≠ BOK, tredje varianten: SKUGGA ≠ BOK ≠ ANKARE.

    Samma grindklass som AnchorSourceTests: spärren måste ligga i test,
    inte bara i kod — 'allt utom pinnacle och ankare' hade annars gjort
    Matchbook till en bok att slå (192-flaggors-felet)."""

    def test_matchbook_ar_varken_bok_eller_ankare(self):
        self.assertNotIn("matchbook", {b["key"] for b in oddset.BOOKS})
        self.assertNotIn("matchbook", oddset_value.ANCHOR_SOURCES)
        self.assertNotEqual("matchbook", oddset_value.ANCHOR2_SOURCE)
        self.assertIn("matchbook", oddset_value.SHADOW_SOURCES,
                      "SHADOW_SOURCES-spärren får inte tas bort — då blir "
                      "skuggkällan en bok i värdemotorn")

    @staticmethod
    def _match(with_shadow: bool) -> dict:
        now = dt.datetime.now(dt.timezone.utc)
        fresh = (now - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def market(values):
            return {**values, "available": True,
                    "fetched_at": fresh, "last_seen_at": fresh}

        odds = {
            "pinnacle": {"1x2": market({"1": 2.0, "X": 3.5, "2": 3.8})},
            "svenskaspel": {"1x2": market({"1": 2.3, "X": 3.5, "2": 3.8})},
        }
        if with_shadow:
            # GENERÖSA priser: vore Matchbook en bok skulle den vinna
            # best-jämförelsen och dyka upp som bokfältet.
            odds["matchbook"] = {"1x2": market({"1": 9.9, "X": 9.9, "2": 9.9})}
        return {"id": "m1",
                "start": (now + dt.timedelta(hours=2))
                .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "odds": odds}

    def test_generost_matchbook_pris_blir_aldrig_vardebok(self):
        med, utan = self._match(True), self._match(False)
        oddset_value.attach_value([med])
        oddset_value.attach_value([utan])
        books = {v["book"] for per in med["value"].values()
                 for v in per.values()}
        self.assertNotIn("matchbook", books)
        # identiskt utfall med och utan skuggkällan — den kan inte ens
        # indirekt ändra urval, edge eller kvalitet.
        for sign, v in utan["value"]["1x2"].items():
            m = med["value"]["1x2"][sign]
            self.assertEqual((v["edge"], v["q"], v["odds"], v["book"]),
                             (m["edge"], m["q"], m["odds"], m["book"]))

    def test_payload_strippar_skuggkallan(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                now = dt.datetime.now(dt.timezone.utc)
                start = (now + dt.timedelta(hours=2)) \
                    .strftime("%Y-%m-%dT%H:%M:%SZ")
                seen = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                store.oddset_upsert_match({
                    "id": "m1", "league": "allsvenskan",
                    "home": "Hammarby", "away": "Djurgården", "start": start})
                store.oddset_save_odds(
                    "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.8}, seen)
                store.oddset_save_odds(
                    "m1", "matchbook", {"1": 2.1, "X": 3.4, "2": 3.9}, seen)
                payload = oddset.matches_payload(
                    store, light=True, include_research=True)
                match = next(m for m in payload["matches"]
                             if m["id"] == "m1")
                self.assertNotIn("matchbook", match["odds"])
                self.assertNotIn("matchbook", match.get("movement") or {})
                self.assertIn("pinnacle", match["odds"])
            finally:
                store.close()


class _Pin:
    def __init__(self):
        self.last_age_s = 0

    def reset_cache_age(self):
        pass

    def close(self):
        pass


class CollectTests(unittest.TestCase):
    """Matchbook-blocket i oddset.collect: snabbfönster, identitetsdisciplin,
    likviditetslagring — utan nätverk (alla källor stubbade)."""

    LEAGUE = {"key": "allsvenskan", "name": "Allsvenskan", "pin_id": 1,
              "kambi": "football/sweden/allsvenskan", "altenar": None}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.now = dt.datetime.now(dt.timezone.utc)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _seed(self, start_in_h: float) -> str:
        start = (self.now + dt.timedelta(hours=start_in_h)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.oddset_upsert_match({
            "id": "m1", "league": "allsvenskan",
            "home": "Hammarby", "away": "Djurgården", "start": start})
        return start

    def _collect(self, mb_events_mock) -> dict:
        with mock.patch.object(oddset, "Pinnacle", return_value=_Pin()), \
                mock.patch.object(oddset, "pinnacle_league_index",
                                  return_value=[]), \
                mock.patch.object(oddset.kambi, "league_events",
                                  return_value=[]), \
                mock.patch.object(oddset, "BOOKS", []), \
                mock.patch.object(smarkets.Smarkets, "upcoming_events",
                                  return_value=[]), \
                mock.patch.object(matchbook.Matchbook, "upcoming_events",
                                  mb_events_mock):
            return oddset.collect(
                self.store, leagues=[self.LEAGUE], deep=False)

    def test_snabbfonster_sparar_odds_och_likviditet_samma_tid(self):
        start = self._seed(2.0)
        mb = mock.Mock(return_value=[
            _event(start=start.replace("Z", ".000Z"))])
        report = self._collect(mb)

        self.assertEqual(1, mb.call_count)
        self.assertEqual(
            1, report["leagues"]["allsvenskan"]["matchbook"])
        latest = self.store.oddset_latest(["m1"])["m1"]["matchbook"]["1x2"]
        self.assertEqual(2.5, latest["1"])
        self.assertTrue(latest["available"])
        liq = self.store.conn.execute(
            "SELECT sign, available, seen_at FROM oddset_matchbook_liquidity "
            "WHERE match_id='m1' ORDER BY sign").fetchall()
        self.assertEqual([("1", 100.0), ("2", 50.0), ("X", 25.0)],
                         [(r["sign"], r["available"]) for r in liq])
        # pris och likviditet ur samma svar = exakt samma observationstid
        odds_at = {r["fetched_at"] for r in self.store.conn.execute(
            "SELECT fetched_at FROM oddset_odds "
            "WHERE match_id='m1' AND source='matchbook'")}
        self.assertEqual(odds_at, {r["seen_at"] for r in liq})
        health = next(r for r in self.store.oddset_source_health()
                      if r["source"] == "matchbook")
        self.assertTrue(health["ok"])
        # referensen har inte skapat några nya matchidentiteter
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_matches").fetchone()[0])

    def test_utanfor_snabbfonstret_ror_inte_kallan(self):
        self._seed(5.0)   # utanför FAST_WITHIN_H = 3 h
        mb = mock.Mock(return_value=[])
        self._collect(mb)

        self.assertEqual(0, mb.call_count)
        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE source='matchbook'")
            .fetchone()[0])

    def test_identitetskonflikt_hoppar_over_andra_klienten(self):
        start = self._seed(2.0).replace("Z", ".000Z")
        mb = mock.Mock(return_value=[
            _event(eid=901, name="Hammarby vs Djurgarden", start=start),
            _event(eid=902, name="Hammarby IF vs Djurgardens IF",
                   start=start,
                   runners=[
                       _runner("Hammarby IF", [_price(9.9, 1.0)]),
                       _runner("Djurgardens IF", [_price(9.9, 1.0)]),
                       _runner("Draw", [_price(9.9, 1.0)]),
                   ]),
        ])
        report = self._collect(mb)

        self.assertEqual(1, report["leagues"]["allsvenskan"]["matchbook"])
        self.assertTrue(any("matchbook identity collision" in e
                            for e in report["errors"]))
        latest = self.store.oddset_latest(["m1"])["m1"]["matchbook"]["1x2"]
        self.assertEqual(2.5, latest["1"])   # 901 vann; 902 skrevs aldrig

    def test_okand_match_skapar_aldrig_matchrad(self):
        self._seed(2.0)
        mb = mock.Mock(return_value=[
            _event(eid=903, name="Real Madrid vs Barcelona",
                   start=(self.now + dt.timedelta(hours=2))
                   .strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                   runners=[
                       _runner("Real Madrid", [_price(2.0, 10.0)]),
                       _runner("Barcelona", [_price(3.5, 10.0)]),
                       _runner("Draw", [_price(3.6, 10.0)]),
                   ])])
        report = self._collect(mb)

        self.assertEqual(0, report["leagues"]["allsvenskan"]["matchbook"])
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_matches").fetchone()[0])
        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE source='matchbook'")
            .fetchone()[0])


class LiquidityMonotonicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _rows(self, sign="1"):
        return self.store.conn.execute(
            "SELECT available, seen_at FROM oddset_matchbook_liquidity "
            "WHERE match_id='m1' AND sign=? ORDER BY seen_at, id",
            (sign,)).fetchall()

    def test_seen_at_ar_monotont_och_dedup_flyttar_klockan_framat(self):
        t1, t2, t3, t4 = ("2026-07-27T15:00:00Z", "2026-07-27T15:04:00Z",
                          "2026-07-27T15:08:00Z", "2026-07-27T15:12:00Z")
        n = self.store.oddset_save_matchbook_liquidity(
            "m1", {"1": 100.0, "X": 50.0, "2": 25.0}, t2)
        self.assertEqual(3, n)

        # föråldrat svar (t1 < t2) bär ingen ny information — skrivs aldrig,
        # varken som ny rad eller som bakåtflyttad klocka
        self.store.oddset_save_matchbook_liquidity("m1", {"1": 77.0}, t1)
        self.assertEqual([(100.0, t2)],
                         [(r["available"], r["seen_at"]) for r in self._rows()])

        # oförändrat belopp = ingen ny historikpunkt, men klockan går framåt
        self.store.oddset_save_matchbook_liquidity("m1", {"1": 100.0}, t3)
        self.assertEqual([(100.0, t3)],
                         [(r["available"], r["seen_at"]) for r in self._rows()])

        # nytt belopp = ny punkt i serien
        self.store.oddset_save_matchbook_liquidity("m1", {"1": 120.0}, t4)
        self.assertEqual([(100.0, t3), (120.0, t4)],
                         [(r["available"], r["seen_at"]) for r in self._rows()])

    def test_saknat_tecken_ror_inte_serien(self):
        t = "2026-07-27T15:00:00Z"
        n = self.store.oddset_save_matchbook_liquidity("m1", {"1": 10.0}, t)
        self.assertEqual(1, n)
        self.assertEqual([], self._rows("X"))


if __name__ == "__main__":
    unittest.main()
