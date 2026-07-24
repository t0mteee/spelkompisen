import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import main
from app.storage import Storage


class _FakeSvS:
    """Räknar hur många gånger listningen faktiskt går mot SvS-API:t."""

    calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def list_draws(self, slug, start_hint=None):
        _FakeSvS.calls += 1
        return [{"product": slug, "draw_number": 100, "state": "Open",
                 "reg_close_time": "2026-07-24T18:59:00+02:00"}]


class DrawsCacheTests(unittest.TestCase):
    """Omgångslistningen live-scannar SvS — v3-dashboardens 2-minuterspoll
    får inte träffa upstream varje gång (feedback 2026-07-24)."""

    def setUp(self):
        _FakeSvS.calls = 0
        self.tmp = tempfile.TemporaryDirectory()
        db = Path(self.tmp.name) / "test.db"
        Storage(db).close()   # skapa schema
        self.patches = [
            mock.patch.object(main, "SvenskaSpel", _FakeSvS),
            mock.patch.object(main, "Storage", lambda: Storage(db)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_andra_anropet_inom_ttl_traffar_inte_svs(self):
        first = main.draws("stryktipset")
        second = main.draws("stryktipset")
        self.assertEqual(1, _FakeSvS.calls)
        self.assertEqual(first, second)
        self.assertEqual(100, first["open"][0]["draw_number"])

    def test_utgangen_cache_hamtar_live_igen(self):
        main.draws("stryktipset")
        with mock.patch.object(main, "DRAWS_CACHE_TTL_S", 0):
            main.draws("stryktipset")
        self.assertEqual(2, _FakeSvS.calls)

    def test_produkter_cachas_separat(self):
        main.draws("stryktipset")
        main.draws("europatipset")
        self.assertEqual(2, _FakeSvS.calls)


if __name__ == "__main__":
    unittest.main()
