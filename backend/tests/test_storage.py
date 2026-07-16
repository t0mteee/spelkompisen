import tempfile
import unittest
from pathlib import Path

from app.storage import Storage


class BulkTransactionTests(unittest.TestCase):
    def test_bulk_rolls_back_all_writes_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                with self.assertRaises(RuntimeError):
                    with store.bulk():
                        store.meta_set("first", "1")
                        store.meta_set("second", "2")
                        raise RuntimeError("abort")
                self.assertIsNone(store.meta_get("first"))
                self.assertIsNone(store.meta_get("second"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
