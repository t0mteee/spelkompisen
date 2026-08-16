import unittest
from unittest.mock import MagicMock, patch

from app import main, pool_played


class PoolPlayedApiTests(unittest.TestCase):
    def test_detaljendpoint_hamtar_en_kupong_utan_liveanrop(self):
        store = MagicMock()
        detail = {"coupon": {"id": 7}, "events": [], "rows": []}
        with patch.object(main, "Storage", return_value=store), \
             patch.object(pool_played, "coupon_detail",
                          return_value=detail) as load:
            result = main.pool_played_detail(7)

        self.assertEqual(detail, result)
        load.assert_called_once_with(store, 7)
        store.close.assert_called_once()

    def test_samma_omgang_hamtas_en_gang_och_snabbvagen_skippar_chans(self):
        coupons = [
            {"id": 1, "product": "europatipset", "draw_number": 2598,
             "settled_at": None, "rows_text": "11", "events_order": "[1,2]"},
            {"id": 2, "product": "europatipset", "draw_number": 2598,
             "settled_at": None, "rows_text": "12", "events_order": "[1,2]"},
        ]
        store = MagicMock()
        source = MagicMock()
        source.__enter__.return_value = source
        source.get_draw_raw.return_value = {
            "drawEvents": [{"eventNumber": 1, "match": {}}]}

        with patch.object(main, "Storage", return_value=store), \
             patch.object(main, "SvenskaSpel", return_value=source), \
             patch.object(pool_played, "all_coupons", return_value=coupons), \
             patch.object(pool_played, "summary", return_value={}), \
             patch.object(pool_played, "attach_regulation_time") as regulation, \
             patch.object(pool_played, "attach_live_odds") as odds, \
             patch.object(pool_played, "live_status",
                          return_value={"n_decided": 0}) as status:
            result = main.pool_played_list(live=True, chance=False)

        source.get_draw_raw.assert_called_once_with("europatipset", 2598)
        regulation.assert_called_once()
        odds.assert_called_once()
        self.assertEqual(2, status.call_count)
        self.assertTrue(all(
            call.kwargs["include_chance"] is False
            for call in status.call_args_list))
        self.assertTrue(result["live_included"])
        self.assertFalse(result["chance_included"])
        self.assertTrue(all("rows_text" not in coupon
                            and "events_order" not in coupon
                            for coupon in result["coupons"]))


if __name__ == "__main__":
    unittest.main()
