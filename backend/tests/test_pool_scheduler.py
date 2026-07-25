import datetime as dt
import unittest
from unittest import mock

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
