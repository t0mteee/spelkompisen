import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from app import main


class JackpotSingleFlightTests(unittest.TestCase):
    def setUp(self) -> None:
        main._jackpots_cache.clear()

    def tearDown(self) -> None:
        main._jackpots_cache.clear()

    def test_concurrent_cold_requests_share_one_upstream_fetch(self) -> None:
        class FakeSvenskaSpel:
            def __init__(self) -> None:
                self.calls = 0
                self.lock = threading.Lock()

            def jackpots_payload(self) -> dict:
                with self.lock:
                    self.calls += 1
                # Håll första hämtningen öppen så övriga trådar säkert hinner
                # möta samma kalla cache.
                time.sleep(0.05)
                return {"jackpots": [1]}

        ss = FakeSvenskaSpel()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _: main._jackpots_for_ui(ss), range(6)))

        self.assertEqual(1, ss.calls)
        self.assertTrue(all(row == {"jackpots": [1]} for row in results))
