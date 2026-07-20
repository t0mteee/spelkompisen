"""Alt-linjelagret (steg-upp 2026-07-20): sharpens alla linjer möjliggör
samma-linje-värde och exakt-line-stängning när boken visar en annan lina."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from app import oddset_value
from app.storage import Storage


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _market(values: dict, seen: dt.datetime, available: bool = True) -> dict:
    return {**values, "available": available, "last_seen_at": _iso(seen)}


class SharpAltStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.addCleanup(self.store.close)
        self.addCleanup(self.tmp.cleanup)

    def test_dedup_per_line_and_pulled_line_marked_unavailable(self) -> None:
        t0 = dt.datetime(2026, 7, 20, 10, 0, tzinfo=dt.timezone.utc)
        pairs = [{"a": 1.90, "b": 1.92, "line": 3.0},
                 {"a": 2.30, "b": 1.62, "line": 3.25}]
        self.assertEqual(4, self.store.oddset_save_sharp_alt("m1", "ou", pairs, _iso(t0)))
        # oförändrat svar: inga nya rader, last_seen flyttas
        self.assertEqual(0, self.store.oddset_save_sharp_alt(
            "m1", "ou", pairs, _iso(t0 + dt.timedelta(minutes=4))))
        latest = self.store.oddset_sharp_alt_latest(["m1"])["m1"]["ou"]
        self.assertEqual(_iso(t0 + dt.timedelta(minutes=4)),
                         latest[3000]["last_seen_at"])
        # 3.25 försvinner ur nästa lyckade svar => plockad
        self.store.oddset_save_sharp_alt(
            "m1", "ou", pairs[:1], _iso(t0 + dt.timedelta(minutes=8)))
        latest = self.store.oddset_sharp_alt_latest(["m1"])["m1"]["ou"]
        self.assertEqual(0, latest[3250]["available"])
        self.assertEqual(1, latest[3000]["available"])

    def test_price_change_creates_history_point(self) -> None:
        t0 = dt.datetime(2026, 7, 20, 10, 0, tzinfo=dt.timezone.utc)
        self.store.oddset_save_sharp_alt(
            "m1", "ou", [{"a": 1.90, "b": 1.92, "line": 3.0}], _iso(t0))
        self.store.oddset_save_sharp_alt(
            "m1", "ou", [{"a": 1.85, "b": 1.97, "line": 3.0}],
            _iso(t0 + dt.timedelta(minutes=30)))
        hist = self.store.oddset_sharp_alt_before(
            "m1", "ou", _iso(t0 + dt.timedelta(hours=2)))
        overs = [r for r in hist if r["sign"] == "O"]
        self.assertEqual([1.90, 1.85], [r["odds"] for r in overs])


class AltLineValueTests(unittest.TestCase):
    def _match(self, now: dt.datetime, alt_seen_min: int = 5) -> dict:
        seen = now - dt.timedelta(minutes=5)
        return {
            "id": "m1", "start": _iso(now + dt.timedelta(hours=4)),
            "odds": {
                "pinnacle": {"ou": _market(
                    {"O": 1.90, "U": 1.92, "line": 3.0}, seen)},
                "svenskaspel": {"ou": _market(
                    {"O": 2.45, "U": 1.55, "line": 3.25}, seen)},
            },
            "sharp_alt": {"ou": {3250: {
                "line": 3.25, "O": 2.30, "U": 1.62, "available": 1,
                "last_seen_at": _iso(now - dt.timedelta(minutes=alt_seen_min))}}},
        }

    def test_book_line_matched_via_alt_line(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        m = self._match(now)
        oddset_value.attach_value([m])
        v = m["value"]["ou"]["O"]
        self.assertTrue(v["alt_line"])
        self.assertEqual(3.25, v["line"])
        self.assertEqual(2.45, v["odds"])
        # fair från alt-paret (2.30/1.62), inte huvudlinan
        self.assertAlmostEqual(v["fair"],
                               oddset_value._devig({"O": 2.30, "U": 1.62},
                                                   ("O", "U"))["O"], places=4)

    def test_stale_alt_line_gives_no_value(self) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        m = self._match(now, alt_seen_min=oddset_value.PRICE_MAX_AGE_MIN + 10)
        oddset_value.attach_value([m])
        self.assertNotIn("ou", m["value"])


class AltLineClosingTests(unittest.TestCase):
    def test_closing_found_on_alt_line_when_main_line_moved(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Storage(Path(tmp.name) / "test.db")
        self.addCleanup(store.close)
        start = dt.datetime.now(dt.timezone.utc)
        t1 = start - dt.timedelta(minutes=30)
        # huvudlinan låg på 3.0 hela vägen — flaggan togs på 3.25
        store.oddset_save_market("m1", "pinnacle", "ou", {
            "O": {"odds": 1.90, "line": 3.0},
            "U": {"odds": 1.92, "line": 3.0}}, _iso(t1))
        store.oddset_save_sharp_alt(
            "m1", "ou", [{"a": 2.28, "b": 1.63, "line": 3.25}], _iso(t1))
        close = oddset_value.closing_snapshot(store, {
            "match_id": "m1", "market": "ou", "sign": "O", "line": 3.25,
            "match_start": _iso(start)})
        self.assertIsNone(close["note"])
        self.assertEqual(2.28, close["odds"])
        self.assertEqual(3.0, close["closing_line"])   # huvudlinan vid stängning
        self.assertAlmostEqual(-0.25, close["line_delta"], places=4)


if __name__ == "__main__":
    unittest.main()
