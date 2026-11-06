"""anchor-v1 (Samans beslut 2026-11-06): Smarkets ankrar 1X2, SBOBET handikapp.

Pinnacle spärrar Sverige sedan 2026-11-05 09:30Z. Testerna här låser att de nya
ankarna används i hela kedjan (värde, steam, notisvakt, stängning, ledger) och
att Pinnacle varken värderar eller stänger något som loggats efter bytet.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import oddset_ledger, oddset_value
from app.storage import Storage

SIGNS = ("1", "X", "2")


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _market(values: dict, seen: dt.datetime) -> dict:
    return {**values, "available": True, "last_seen_at": _iso(seen),
            "fetched_at": _iso(seen)}


def _match(odds: dict, hours_to_start: float = 30.0) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    return {"id": "m1", "home": "A", "away": "B", "league": "mls",
            "start": _iso(now + dt.timedelta(hours=hours_to_start)),
            "odds": odds}


class KonfigurationTests(unittest.TestCase):
    def test_ankarna_per_marknad(self) -> None:
        self.assertEqual({"1x2": "smarkets", "ah": "sbobet"},
                         oddset_value.ANCHOR_BY_MARKET)
        self.assertNotIn("pinnacle", oddset_value.ANCHOR_BY_MARKET.values())
        # ankarna är aldrig böcker att hitta värde hos
        for src in oddset_value.ANCHOR_BY_MARKET.values():
            self.assertIn(src, oddset_value.ANCHOR_SOURCES)

    def test_signalversionen_byter_och_pinnacleperioden_ar_ordagrann(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                new = oddset_value.signal_versions(store)
                with mock.patch.object(oddset_value, "ANCHOR_BY_MARKET",
                                       oddset_value.LEGACY_ANCHORS):
                    old = oddset_value.signal_versions(store)
            finally:
                store.close()
        self.assertNotEqual(new["sharp"], old["sharp"])
        self.assertNotEqual(new["model"], old["model"])
        legacy = oddset_value.sharp_params(oddset_value.LEGACY_ANCHORS)
        self.assertEqual("band-v8", legacy["closing_drift"])
        self.assertTrue(legacy["alt_lines"])
        self.assertNotIn("anchors", legacy)
        current = oddset_value.sharp_params()
        self.assertIsNone(current["closing_drift"])
        self.assertFalse(current["alt_lines"])


class VardeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seen = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)

    def test_1x2_vardes_mot_smarkets_utan_drift_och_ignorerar_pinnacle(self) -> None:
        sm = {"1": 2.0, "X": 3.6, "2": 4.0}
        m = _match({
            "smarkets": {"1x2": _market(sm, self.seen)},
            "pinnacle": {"1x2": _market({"1": 1.6, "X": 4.0, "2": 6.0}, self.seen)},
            "svenskaspel": {"1x2": _market({"1": 2.3, "X": 3.3, "2": 3.6}, self.seen)},
        })
        oddset_value.attach_value([m])
        v = m["value"]["1x2"]["1"]
        self.assertEqual("smarkets", v["anchor"])
        self.assertEqual("svenskaspel", v["book"])
        # ingen driftjustering: fair = ren devigad Smarkets (30 h kvar hade
        # gett band-v8:s tidiga regim om den använts)
        expected = oddset_value._devig(sm, SIGNS)["1"]
        self.assertAlmostEqual(expected, v["fair"], places=4)

    def test_ingen_1x2_flagga_utan_smarkets_aven_med_farsk_pinnacle(self) -> None:
        m = _match({
            "pinnacle": {"1x2": _market({"1": 1.6, "X": 4.0, "2": 6.0}, self.seen)},
            "svenskaspel": {"1x2": _market({"1": 2.3, "X": 3.3, "2": 3.6}, self.seen)},
        })
        oddset_value.attach_value([m])
        self.assertNotIn("1x2", m["value"])

    def test_handikapp_vardes_mot_sbobet_pa_samma_lina(self) -> None:
        m = _match({
            "sbobet": {"ah": _market({"H": 1.95, "A": 1.95, "line": -0.5}, self.seen)},
            "svenskaspel": {"ah": _market({"H": 2.15, "A": 1.75, "line": -0.5}, self.seen)},
            "unibet": {"ah": _market({"H": 2.60, "A": 1.50, "line": -0.75}, self.seen)},
        })
        m["sharp_alt"] = {"ah": {"-0.75": {"H": 1.7, "A": 2.2}}}
        oddset_value.attach_value([m])
        v = m["value"]["ah"]["H"]
        self.assertEqual("sbobet", v["anchor"])
        self.assertEqual("svenskaspel", v["book"])     # annan lina räknas aldrig
        self.assertEqual(-0.5, v["line"])
        self.assertNotIn("alt_line", v)

    def test_ou_och_horn_har_inget_ankare(self) -> None:
        m = _match({
            "pinnacle": {"ou": _market({"O": 1.9, "U": 1.9, "line": 2.5}, self.seen),
                         "cor": _market({"O": 1.9, "U": 1.9, "line": 9.5}, self.seen)},
            "svenskaspel": {"ou": _market({"O": 2.4, "U": 1.6, "line": 2.5}, self.seen),
                            "cor": _market({"O": 2.4, "U": 1.6, "line": 9.5}, self.seen)},
        })
        oddset_value.attach_value([m])
        self.assertNotIn("ou", m["value"])
        self.assertNotIn("cor", m["value"])

    def test_sbobet_och_smarkets_ar_aldrig_bocker(self) -> None:
        m = _match({
            "smarkets": {"1x2": _market({"1": 2.0, "X": 3.6, "2": 4.0}, self.seen)},
            "sbobet": {"1x2": _market({"1": 3.0, "X": 3.6, "2": 4.0}, self.seen)},
        })
        oddset_value.attach_value([m])
        self.assertNotIn("1x2", m["value"])


class SteamTests(unittest.TestCase):
    def test_steam_ur_smarkets_serie(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        seen = now - dt.timedelta(minutes=5)
        then = _iso(now - dt.timedelta(hours=7))
        cur = {"1": 1.8, "X": 3.8, "2": 5.0}
        m = _match({"smarkets": {"1x2": _market(cur, seen)}})
        m["movement"] = {"smarkets": {"1x2": {
            s: {"pts": [{"t": then, "o": o0}, {"t": _iso(seen), "o": cur[s]}]}
            for s, o0 in (("1", 2.2), ("X", 3.5), ("2", 3.6))}}}
        # Pinnacle-serie åt andra hållet får inte påverka
        m["movement"]["pinnacle"] = {"1x2": {
            s: {"pts": [{"t": then, "o": 1.5}, {"t": _iso(seen), "o": 3.0}]}
            for s in SIGNS}}
        oddset_value.attach_price_status([m], now)
        oddset_value.attach_steam([m])
        self.assertGreater(m["steam"]["1"]["h6"], 0)


class NotisvaktTests(unittest.TestCase):
    def test_notis_kraver_ankaret_i_varvet(self) -> None:
        seen = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        m = _match({
            "smarkets": {"1x2": _market({"1": 2.0, "X": 3.6, "2": 4.0}, seen)},
            "svenskaspel": {"1x2": _market({"1": 2.6, "X": 3.3, "2": 3.6}, seen)},
        })
        oddset_value.attach_value([m])
        self.assertGreaterEqual(m["value"]["1x2"]["1"]["q"], oddset_value.Q_NOTIFY)
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "t.db")
            try:
                with mock.patch.object(oddset_value.notify, "enabled",
                                       return_value=False):
                    utan = oddset_value.log_and_notify(
                        store, [m], present={("m1", "svenskaspel", "1x2"),
                                             ("m1", "pinnacle", "1x2")})
                    self.assertGreaterEqual(utan["gated"], 1)
                    self.assertIsNone(store.meta_get("oddset_ntfy_edge:m1:1x2:1"))
                    oddset_value.log_and_notify(
                        store, [m], present={("m1", "svenskaspel", "1x2"),
                                             ("m1", "smarkets", "1x2")})
                    note = store.meta_get("oddset_ntfy_edge:m1:1x2:1")
                    self.assertIsNotNone(note)
                    self.assertIn("Smarkets", note)
                    versions = {r["model_version"]
                                for r in store.oddset_clv_rows()}
                    self.assertEqual({oddset_value.signal_versions(store)["sharp"]},
                                     versions)
            finally:
                store.close()


class StangningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        # flaggorna i testerna loggas 3 h före avspark: bytet ligger före dem
        self.switch = mock.patch.object(oddset_value, "ANCHOR_SWITCH_AT",
                                        "2026-01-01T00:00:00Z")
        self.switch.start()

    def tearDown(self) -> None:
        self.switch.stop()
        self.store.close()
        self.tmp.cleanup()

    def test_kallor_fore_och_efter_bytet(self) -> None:
        fore = {"first_at": "2025-12-31T08:00:00Z"}
        efter = {"first_at": "2026-01-02T08:00:00Z"}
        cs = oddset_value.closing_sources
        self.assertEqual(("pinnacle", "derived"), cs(fore, "1x2"))
        self.assertEqual(("pinnacle", "derived"), cs(fore, "ou"))
        self.assertEqual(("smarkets",), cs(efter, "1x2"))
        self.assertEqual(("sbobet",), cs(efter, "ah"))
        self.assertEqual((), cs(efter, "ou"))
        self.assertEqual((), cs(efter, "cor"))
        # prediktioner bär sitt ankare och stängs mot just det
        self.assertEqual(("pinnacle", "derived"),
                         cs({"captured_at": "2026-11-07T08:00:00Z",
                             "fair_source": "pinnacle"}, "1x2"))
        self.assertEqual(("sbobet",),
                         cs({"captured_at": "2026-11-07T08:00:00Z",
                             "fair_source": "sbobet"}, "ah"))

    def _flag(self, market: str, sign: str, start: dt.datetime,
              line=None) -> None:
        self.store.oddset_log_flag({
            "match_id": "m1", "market": market, "sign": sign, "line": line,
            "league": "mls", "description": "A – B",
            "match_start": _iso(start),
            "at": _iso(start - dt.timedelta(hours=3)),
            "odds": 2.2, "fair": 0.5, "edge": 0.1,
            "book": "svenskaspel", "model_version": "s-test", "git_hash": "abc"})

    def test_1x2_stangs_mot_smarkets_och_inte_pinnacle(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        pre = _iso(start - dt.timedelta(minutes=10))
        sm = {"1": 2.0, "X": 3.6, "2": 4.0}
        self.store.oddset_save_odds("m1", "smarkets", sm, pre)
        self.store.oddset_save_odds("m1", "pinnacle",
                                    {"1": 1.5, "X": 4.5, "2": 7.0}, pre)
        self._flag("1x2", "1", start)
        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]
        self.assertIsNone(row["closing_note"])
        self.assertEqual(2.0, row["closing_odds"])
        self.assertAlmostEqual(oddset_value._devig(sm, SIGNS)["1"],
                               row["closing_fair"], places=4)

    def test_handikapp_stangs_mot_sbobet(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        pre = _iso(start - dt.timedelta(minutes=10))
        self.store.oddset_save_market(
            "m1", "sbobet", "ah", {"H": {"odds": 1.9, "line": -0.5},
                                   "A": {"odds": 2.0, "line": -0.5}}, pre)
        self._flag("ah", "H", start, line=-0.5)
        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]
        self.assertIsNone(row["closing_note"])
        self.assertEqual(1.9, row["closing_odds"])

    def test_modellflagga_pa_ou_far_ingen_stangning(self) -> None:
        start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
        pre = _iso(start - dt.timedelta(minutes=10))
        self.store.oddset_save_market(
            "m1", "pinnacle", "ou", {"O": {"odds": 1.9, "line": 2.5},
                                     "U": {"odds": 1.95, "line": 2.5}}, pre)
        self._flag("mou", "O", start, line=2.5)
        oddset_value.resolve_closings(self.store)
        row = self.store.oddset_clv_rows()[0]
        self.assertEqual("inget ankare för marknaden", row["closing_note"])
        self.assertIsNone(row["closing_fair"])


class LedgerTests(unittest.TestCase):
    def test_sharp_prediktioner_ur_ankarna(self) -> None:
        seen = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        m = _match({
            "smarkets": {"1x2": _market({"1": 2.0, "X": 3.6, "2": 4.0}, seen)},
            "sbobet": {"1x2": _market({"1": 2.4, "X": 3.6, "2": 4.0}, seen),
                       "ah": _market({"H": 1.95, "A": 1.95, "line": -0.5}, seen)},
            "pinnacle": {"ou": _market({"O": 1.9, "U": 1.9, "line": 2.5}, seen)},
            "svenskaspel": {"1x2": _market({"1": 2.3, "X": 3.3, "2": 3.6}, seen),
                            "ah": _market({"H": 2.1, "A": 1.75, "line": -0.5}, seen)},
        })
        oddset_value.attach_price_status([m], dt.datetime.now(dt.timezone.utc))
        rows = oddset_ledger._sharp_rows(m)
        by = {(r["market"], r["sign"]): r for r in rows}
        self.assertEqual("smarkets", by[("1x2", "1")]["fair_source"])
        self.assertEqual("sbobet", by[("ah", "H")]["fair_source"])
        self.assertNotIn(("ou", "O"), by)
        # SBOBET:s 1X2 (2,40) är ingen bok att jämföra mot
        self.assertEqual("svenskaspel", by[("1x2", "1")]["book"])


if __name__ == "__main__":
    unittest.main()
