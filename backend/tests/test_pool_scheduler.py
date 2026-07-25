import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.storage import Storage

import cli
from cli import pool_tick_due


NOW = dt.datetime(2026, 7, 25, 10, 0, tzinfo=dt.timezone.utc)


class PoolSchedulerTests(unittest.TestCase):
    def test_first_tick_runs_a_base_capture(self) -> None:
        self.assertTrue(pool_tick_due(None, None, now=NOW))

    def test_cold_pool_is_throttled_between_base_captures(self) -> None:
        last = NOW - dt.timedelta(minutes=12)
        self.assertFalse(pool_tick_due(last, 8.0, now=NOW))
        self.assertTrue(pool_tick_due(
            NOW - dt.timedelta(minutes=31), 8.0, now=NOW))

    def test_hot_pool_runs_every_tick_without_changing_tolerance(self) -> None:
        last = NOW - dt.timedelta(minutes=2)
        self.assertTrue(pool_tick_due(last, 0.3, now=NOW))

    def test_closed_pool_does_not_keep_dense_mode_alive(self) -> None:
        last = NOW - dt.timedelta(minutes=2)
        self.assertFalse(pool_tick_due(last, -0.1, now=NOW))

    def test_total_source_failure_is_retried_next_tick(self) -> None:
        store = mock.MagicMock()
        store.meta_get.return_value = None
        with mock.patch.object(cli, "Storage", return_value=store) as storage, \
                mock.patch.object(
                    cli, "_hours_to_next_pool_close", return_value=None), \
                mock.patch.object(
                    cli, "_snapshot_all_pools", return_value=(None, 0)):
            cli.cmd_pool_tick()

        self.assertEqual(1, storage.call_count)
        store.meta_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class PinnacleDoubleTrafficTests(unittest.TestCase):
    """Två launchd-jobb får inte dubbelhämta Pinnacles bulk-endpoints."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_nyligen_hamtad_ger_skip(self):
        from app import sharp_service
        import datetime as dt
        self.assertFalse(sharp_service._pinnacle_fetched_recently(self.store))
        now = dt.datetime.now(dt.timezone.utc)
        self.store.meta_set(
            sharp_service._PINNACLE_LAST_FETCH_KEY,
            now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertTrue(sharp_service._pinnacle_fetched_recently(self.store))
        # äldre än fönstret ⇒ hämta igen
        gammal = now - dt.timedelta(
            seconds=sharp_service.PINNACLE_MIN_INTERVAL_S + 60)
        self.store.meta_set(
            sharp_service._PINNACLE_LAST_FETCH_KEY,
            gammal.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertFalse(sharp_service._pinnacle_fetched_recently(self.store))

    def test_intervallet_ligger_under_cdn_cachens_livslangd(self):
        from app import sharp_service
        # 905 s CDN-cache: spärren ska inte vara längre än så, annars missar
        # vi ett objektbyte.
        self.assertLess(sharp_service.PINNACLE_MIN_INTERVAL_S, 905)


class LiveDenseTests(unittest.TestCase):
    """Radarns förtätning inom femminutersjobbet (Samans önskan 2026-07-25).

    Förtätningen ligger INNE i jobbet i stället för i ett tätare
    launchd-intervall, så budgeten är det enda som håller oss från att krocka
    med nästa tick. Den regeln testas här — tillsammans med att vi inte pollar
    vidare när det inte finns någon match värd att visa.
    """

    def _kor(self, visible: int, budget: int, interval: int) -> list[int]:
        sovit: list[int] = []
        with mock.patch.object(cli, "_live_pass", return_value=({}, {})), \
             mock.patch("app.live_radar.payload",
                        return_value={"matches": [{}] * visible}):
            cli.cmd_live_tick(budget, interval, sleep=sovit.append)
        return sovit

    def test_forbrukar_inte_mer_an_budgeten(self):
        """4 min budget / 2 min intervall = tre varv (0s, 120s, 240s), två
        sömner. Terminering får INTE bero på att väggklockan hinner gå — en
        sådan loop snurrar för evigt när klockan står still."""
        self.assertEqual([120, 120], self._kor(visible=3, budget=240, interval=120))

    def test_tatare_intervall_ger_fler_varv_inom_samma_budget(self):
        self.assertEqual([60] * 4, self._kor(visible=3, budget=240, interval=60))

    def test_budget_noll_ger_ett_enda_varv(self):
        self.assertEqual([], self._kor(visible=3, budget=0, interval=120))

    def test_slutar_direkt_nar_ingen_match_har_chansdata(self):
        """Annars hade vi bränt 30 anrop varannan minut på matcher som döljs."""
        self.assertEqual([], self._kor(visible=0, budget=240, interval=120))

    def test_budgeten_ryms_i_femminutersjobbet(self):
        self.assertLess(cli.LIVE_DENSE_BUDGET_S, 300)
        self.assertLessEqual(cli.LIVE_DENSE_INTERVAL_S,
                             cli.LIVE_DENSE_BUDGET_S)
