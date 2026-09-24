import datetime as dt
import itertools
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import pool_capture_refresh as refresh, pool_dataset, sharp_service
from app.pinnacle import Pinnacle
from app.storage import Storage

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 14, 16, 37, tzinfo=UTC)
ODDS = {"1": 2.0, "X": 3.0, "2": 4.0}
TOTAL = {"line": 2.5, "O": 1.9, "U": 1.95}


class DetailCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.draw = SimpleNamespace(draw_number=4333, reg_close_time="2026-09-14T16:59:00Z",
            matches=[SimpleNamespace(event_number=1, cancelled=False)])
        self.result = {"fetched_at": "2026-09-14T16:27:50Z",
                       "hits": {1: {"id": "123", "odds": ODDS, "total": TOTAL}}}
        self.quote = {"odds": ODDS, "total": TOTAL, "retrieved_at": "2026-09-14T16:37:01Z",
                      "fetched_at": "2026-09-14T16:35:00Z", "cache_age_s": 121,
                      "cache_age_valid": True}
        self.mock = patch.object(refresh, "Pinnacle")
        self.pin = self.mock.start().return_value.__enter__.return_value
        self.pin.prematch_quote.side_effect = lambda _: dict(self.quote)
        self.varv = sharp_service.VarvIndex()

    def tearDown(self):
        self.mock.stop()
        self.store.close()
        self.tmp.cleanup()

    def run_capture(self, now=NOW, product="topptipset", varv=None, **kwargs):
        return refresh.capture_missing(self.store, product, self.draw, self.result,
            varv or self.varv, now=now, **kwargs)

    def test_70_sekunders_luckan_raddas_med_riktig_pristid(self):
        result = self.run_capture()
        self.assertEqual(1, result["captured"])
        cap = self.store.conn.execute("SELECT fetched_at,status,odds_complete FROM pool_market_capture").fetchone()
        self.assertEqual(("2026-09-14T16:35:00Z", "matched", 1), tuple(cap))
        rows = self.store.conn.execute("SELECT DISTINCT fetched_at FROM sharp_snapshots").fetchall()
        self.assertEqual([("2026-09-14T16:35:00Z",)], [tuple(r) for r in rows])
        pool_dataset.build_total_draw(self.store, "topptipset", 4333, self.draw.reg_close_time,
                                     now=NOW + dt.timedelta(hours=1))
        row = self.store.conn.execute("SELECT total_eligible,line FROM pool_pit_total_features WHERE horizon='m20'").fetchone()
        self.assertEqual((1, 2.5), tuple(row))

    def test_gammal_eller_framtida_eller_ofullstandig_quote_avvisas(self):
        variants = [(dict(fetched_at="2026-09-14T16:27:50Z"), "observerad_fore_fonstret"),
                    (dict(fetched_at="2026-09-14T16:40:00Z"), "pristid_efter_hamtning"),
                    (dict(retrieved_at="2026-09-14T16:40:00Z"), "hamtad_efter_as_of"),
                    (dict(total=None), "ofullstandig_total"),
                    (dict(cache_age_valid=False), "age_ogiltig"),
                    (dict(odds={"1": 2, "X": 3}), "ofullstandig_1x2"),
                    (dict(total={**TOTAL, "O": float("nan")}), "ej_finit")]
        original = dict(self.quote)
        for change, reason in variants:
            with self.subTest(change=change):
                self.store.conn.execute("DELETE FROM meta")
                self.store.conn.commit()
                self.quote = {**original, **change}
                result = self.run_capture(varv=sharp_service.VarvIndex())
                self.assertEqual(0, result["captured"])
                self.assertEqual({reason: 1}, result["reasons"])
                self.assertEqual(result["rejected"], sum(result["reasons"].values()))
        self.assertEqual(0, self.store.conn.execute("SELECT count(*) FROM pool_market_capture").fetchone()[0])

    def reject_once(self, **change):
        self.quote = {**self.quote, **change}
        result = self.run_capture(varv=sharp_service.VarvIndex())
        self.assertEqual((0, 1), (result["captured"], result["rejected"]))
        return result

    def test_varje_avslagsorsak_namnges(self):
        """D3: varje orsak i REJECT_REASONS utom den logiskt omöjliga."""
        cases = {
            "pristid_saknas": dict(fetched_at=None),
            "hamtningstid_saknas": dict(retrieved_at="trasig"),
            "age_ogiltig": dict(cache_age_valid=None),
            "pristid_efter_hamtning": dict(fetched_at="2026-09-14T16:37:30Z"),
            "hamtad_efter_as_of": dict(retrieved_at="2026-09-14T16:39:01Z"),
            "observerad_fore_fonstret": dict(fetched_at="2026-09-14T16:28:59Z"),
            "ofullstandig_1x2": dict(odds={**ODDS, "2": 1.0}),
            "ofullstandig_total": dict(total={**TOTAL, "line": None}),
            "ej_finit": dict(total={**TOTAL, "U": float("inf")}),
            "total_odds_ogiltiga": dict(total={**TOTAL, "O": 1.0}),
        }
        original = dict(self.quote)
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                self.store.conn.execute("DELETE FROM meta")
                self.quote = dict(original)
                self.assertEqual({reason: 1}, self.reject_once(**change)["reasons"])
        self.assertEqual(set(refresh.REJECT_REASONS) - {
            "observerad_efter_as_of", "ej_nyare_an_bulk", "aldre_an_senaste_observation"},
            set(cases))

    def test_ej_nyare_an_bulk(self):
        # Bulken i fönstret men utan komplett 1X2 ger ett försök; svaret är
        # ändå inte nyare än bulken.
        self.result.update(fetched_at="2026-09-14T16:35:00Z")
        self.result["hits"][1]["odds"] = {"1": 2.0}
        self.assertEqual({"ej_nyare_an_bulk": 1}, self.reject_once()["reasons"])

    def test_aldre_an_senaste_observation(self):
        self.store.save_sharp_snapshot("topptipset", 4333, {1: {"odds": ODDS}},
                                       "2026-09-14T16:36:00Z")
        result = self.reject_once()
        self.assertEqual({"aldre_an_senaste_observation": 1}, result["reasons"])
        self.assertEqual(0, self.store.conn.execute(
            "SELECT count(*) FROM pool_market_capture").fetchone()[0])

    def test_senaste_observation_jamfors_som_tid_inom_samma_sekund(self):
        """`…Z` sorterar efter `….5+00:00` som text men är en halv sekund äldre."""
        self.store.save_sharp_snapshot("topptipset", 4333, {1: {"odds": ODDS}},
                                       "2026-09-14T16:35:00.500000+00:00")
        result = self.run_capture()
        self.assertEqual(0, result["captured"])
        self.assertEqual({"aldre_an_senaste_observation": 1}, result["reasons"])

    def test_loggrad_per_forsok_med_id_orsak_och_tider(self):
        self.quote = {**self.quote, "cache_age_valid": False}
        self.run_capture()
        result = self.run_capture(product="topptipsetextra")   # samma varv: delat svar
        lines = list(refresh.log_lines(result))
        self.assertEqual(1, len(lines))
        self.assertIn("id 123 match 1: age_ogiltig", lines[0])
        self.assertIn("pristid 2026-09-14T16:35:00Z", lines[0])
        self.assertIn("hämtad 2026-09-14T16:37:01Z", lines[0])
        self.assertIn("Age 121 s", lines[0])
        self.assertIn("svar hämtat tidigare i varvet", lines[0])
        self.store.conn.execute("DELETE FROM meta")
        self.pin.prematch_quote.side_effect = TimeoutError()
        result = self.run_capture(varv=sharp_service.VarvIndex())
        self.assertEqual({}, result["reasons"])
        self.assertEqual(["m20-reserv id 123 match 1: kallfel (TimeoutError, begärd "
                          "2026-09-14T16:37:00Z) · pristid – · hämtad – · Age – s"],
                         list(refresh.log_lines(result)))
        self.pin.prematch_quote.side_effect = lambda _: dict(self.quote)
        self.quote = {**self.quote, "cache_age_valid": True}
        self.store.conn.execute("DELETE FROM meta")
        result = self.run_capture(varv=sharp_service.VarvIndex())
        self.assertEqual(1, result["captured"])
        self.assertIn("match 1: godtagen", next(refresh.log_lines(result)))

    def test_utanfor_fonstret_ingen_trafik(self):
        for delta in (-9, 3):
            self.run_capture(now=NOW + dt.timedelta(minutes=delta))
        self.pin.prematch_quote.assert_not_called()

    def test_giltig_bulk_och_giltig_tidigare_capture_ger_ingen_extrafragning(self):
        self.result["fetched_at"] = "2026-09-14T16:33:00Z"
        self.assertEqual(0, self.run_capture()["attempted"])
        self.result["fetched_at"] = "2026-09-14T16:27:50Z"
        self.assertEqual(1, self.run_capture()["captured"])
        self.assertEqual(0, self.run_capture(varv=sharp_service.VarvIndex())["attempted"])
        self.assertEqual(1, self.pin.prematch_quote.call_count)

    def test_samma_provider_id_delas_mellan_produkter_och_speglas(self):
        self.run_capture()
        self.result["hits"][1]["swapped"] = True
        self.run_capture(product="topptipsetextra")
        self.assertEqual(1, self.pin.prematch_quote.call_count)
        row = self.store.conn.execute("SELECT odds FROM sharp_snapshots WHERE product='topptipsetextra' AND sign='1'").fetchone()
        self.assertEqual(4, row[0])

    def test_kallfel_skaper_inte_falsk_franvaro_och_far_cooldown(self):
        self.pin.prematch_quote.side_effect = TimeoutError()
        self.assertEqual(1, self.run_capture()["errors"])
        self.run_capture(varv=sharp_service.VarvIndex())
        self.assertEqual(1, self.pin.prematch_quote.call_count)
        self.assertEqual(0, self.store.conn.execute("SELECT count(*) FROM pool_market_capture").fetchone()[0])

    def test_tidsbudget_och_matchtak(self):
        self.varv.detail_deadline = 10
        self.run_capture(clock=lambda: 11)
        self.pin.prematch_quote.assert_not_called()
        self.varv.detail_deadline = None
        self.varv.detail_quotes = {str(i): None for i in range(refresh.MAX_REQUESTS)}
        self.run_capture()
        self.pin.prematch_quote.assert_not_called()

    def test_slut_budget_hoppar_inte_over_redan_hamtade_svar(self):
        """C9: budgeten stoppar nya anrop, inte redan hämtade svar i varvet."""
        self.draw.matches = [SimpleNamespace(event_number=1, cancelled=False),
                             SimpleNamespace(event_number=2, cancelled=False)]
        self.result["hits"] = {1: {"id": "123", "odds": ODDS, "total": TOTAL},
                               2: {"id": "456", "odds": ODDS, "total": TOTAL}}
        self.varv.detail_deadline = 10
        # Match 2:s svar hämtades redan i varvet av en annan produkt.
        self.varv.detail_quotes = {"456": dict(self.quote)}
        result = self.run_capture(clock=lambda: 11)
        self.pin.prematch_quote.assert_not_called()
        self.assertEqual(1, result["captured"])
        events = [r[0] for r in self.store.conn.execute(
            "SELECT event_number FROM pool_market_capture")]
        self.assertEqual([2], events)

    def test_aterlast_bulk_far_inte_backa_snapshots(self):
        # Även oförändrat 1X2: ingen ny 1X2-punkt vid reservhämtningen.
        self.store.save_sharp_snapshot("topptipset", 4333, {1: {"odds": ODDS}},
                                       "2026-09-14T16:20:00Z")
        self.run_capture()
        self.store.save_sharp_snapshot("topptipset", 4333,
            {1: {"odds": {**ODDS, "1": 6}, "total": {**TOTAL, "line": 3.5}}},
            "2026-09-14T16:27:50Z")
        self.assertEqual(3, self.store.conn.execute("SELECT count(*) FROM sharp_snapshots").fetchone()[0])
        self.assertEqual(1, self.store.conn.execute("SELECT count(*) FROM sharp_total_snapshots").fetchone()[0])


class QuoteParserTests(unittest.TestCase):
    def test_bara_exakt_id_helmatch_och_oppna_marknader(self):
        rows = [dict(matchupId=123, period=0, type="moneyline", status="open", prices=[
            dict(designation="home", price=100), dict(designation="draw", price=200),
            dict(designation="away", price=300)]),
            dict(matchupId=123, period=0, type="total", status="open", prices=[
            dict(designation="over", price=-110, points=2.5),
            dict(designation="under", price=-110, points=2.5)])]
        with Pinnacle() as pin, patch.object(Pinnacle, "_get", return_value=rows) as get:
            pin.last_age_s = 121
            result = pin.prematch_quote("123")
            self.assertEqual(ODDS, result["odds"])
            self.assertEqual(2.5, result["total"]["line"])
            get.assert_called_once_with("/matchups/123/markets/straight", attempts=1)
            self.assertEqual(121, (pool_dataset._parse(result["retrieved_at"]) - pool_dataset._parse(result["fetched_at"])).total_seconds())
            self.assertIsNone(pin.prematch_quote("999")["odds"])
            rows[0]["status"] = "suspended"
            self.assertIsNone(pin.prematch_quote("123")["odds"])


def _gammalt_avslag(quote, start, target, bulk_time):
    """Avslagsvillkoret ORDAGRANT som det stod före D3 (ekvivalensfacit)."""
    observed = pool_dataset._parse(quote.get("fetched_at"))
    retrieved = pool_dataset._parse(quote.get("retrieved_at"))
    odds, total = quote.get("odds") or {}, quote.get("total") or {}
    return bool(not observed or not retrieved or not quote.get("cache_age_valid") or
            observed > retrieved or retrieved > target or
            not start <= observed <= target or observed <= bulk_time or
            not all(odds.get(s, 0) > 1 for s in ("1", "X", "2")) or
            not all(total.get(k) is not None for k in ("line", "O", "U")) or
            not all(math.isfinite(float(v)) for v in [*odds.values(), *total.values()]) or
            total["O"] <= 1 or total["U"] <= 1)


class RejectReasonEquivalenceTests(unittest.TestCase):
    def test_samma_svar_godtas_och_avvisas_som_fore_d3(self):
        """Även undantag (None som odds, text som total) uppstår likadant."""
        start = dt.datetime(2026, 9, 14, 16, 29, tzinfo=UTC)
        target = dt.datetime(2026, 9, 14, 16, 39, tzinfo=UTC)
        times = [None, "trasig", "2026-09-14T16:27:50Z", "2026-09-14T16:29:00Z",
                 "2026-09-14T16:35:00Z", "2026-09-14T16:36:00Z", "2026-09-14T16:39:00Z",
                 "2026-09-14T16:40:00Z", "2026-09-14T18:36:00+02:00"]
        retrieved = [None, "2026-09-14T16:37:01Z", "2026-09-14T16:39:00Z",
                     "2026-09-14T16:40:00Z", "2026-09-14T16:34:00Z"]
        nan = float("nan")
        odds = [ODDS, {"1": 2, "X": 3}, None, {**ODDS, "1": 1.0}, {**ODDS, "2": nan},
                {**ODDS, "X": None}, {**ODDS, "2": float("inf")}]
        totals = [TOTAL, None, {**TOTAL, "line": None}, {**TOTAL, "O": nan},
                  {**TOTAL, "O": 1.0}, {**TOTAL, "U": 0.5}, {**TOTAL, "O": "x"},
                  {**TOTAL, "U": float("inf")}, {**TOTAL, "extra": None}]
        bulks = [dt.datetime(2026, 9, 14, 16, 27, 50, tzinfo=UTC),
                 dt.datetime(2026, 9, 14, 16, 35, tzinfo=UTC)]

        def outcome(fn, *args):
            try:
                return ("värde", fn(*args))
            except Exception as exc:  # noqa: BLE001 — undantaget är en del av beteendet
                return ("undantag", type(exc))

        seen = set()
        for f, r, valid, o, t, bulk in itertools.product(
                times, retrieved, (True, False, None), odds, totals, bulks):
            quote = {"fetched_at": f, "retrieved_at": r, "cache_age_valid": valid,
                     "odds": o, "total": t}
            old = outcome(_gammalt_avslag, quote, start, target, bulk)
            new = outcome(refresh.reject_reason, quote, start, target, bulk)
            if new[0] == "värde":
                seen.add(new[1])
                new = ("värde", new[1] is not None)
            self.assertEqual(old, new, quote)
        # Varje orsak nås i rutnätet utom databasorsaken (egen test ovan) och
        # `observerad_efter_as_of`, som de två föregående villkoren utesluter.
        self.assertNotIn("observerad_efter_as_of", seen)
        self.assertEqual(set(refresh.REJECT_REASONS) | {None},
                         seen | {"observerad_efter_as_of", "aldre_an_senaste_observation"})
