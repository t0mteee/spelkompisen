import unittest
from unittest.mock import MagicMock, patch

from app import main, pool_played, pool_system_ledger


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
        main._pool_live_cache.clear()
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

    def test_snabb_och_full_lasning_delar_exakt_samma_livebild(self):
        main._pool_live_cache.clear()
        coupons = [{
            "id": 1, "product": "stryktipset", "draw_number": 5001,
            "settled_at": None, "rows_text": "1", "events_order": "[1]",
        }]
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
             patch.object(pool_played, "live_status", return_value={}) as status:
            main.pool_played_list(live=True, chance=False)
            main.pool_played_list(live=True, chance=True)

        source.get_draw_raw.assert_called_once_with("stryktipset", 5001)
        regulation.assert_called_once()
        odds.assert_called_once()
        self.assertEqual([False, True], [
            call.kwargs["include_chance"] for call in status.call_args_list])

    def test_forskningssystem_liverattas_utan_liveodds_eller_raddetaljer(self):
        main._pool_live_cache.clear()
        store = MagicMock()
        coupon = {
            "product": "stryktipset", "draw_number": 4968,
            "rows_text": "111", "events_order": "[1, 2, 3]",
            "settled": False,
        }
        states = [{"event_number": 1}]
        with patch.object(main, "Storage", return_value=store), \
             patch.object(pool_system_ledger, "system_live_coupon",
                          return_value=coupon), \
             patch.object(main, "_pool_live_states",
                          return_value=({("stryktipset", 4968): states}, {})) as source, \
             patch.object(pool_played, "live_status",
                          return_value={"n_decided": 0}) as status:
            result = main.pool_system_live(
                "stryktipset", 4968, "h3", "max40-v1-b40000-ev50")

        source.assert_called_once_with(
            store, [("stryktipset", 4968)], include_odds=False)
        status.assert_called_once_with(
            coupon, states, include_chance=False,
            include_row_details=False)
        self.assertTrue(result["available"])
        self.assertFalse(result["settled"])
        self.assertEqual({"n_decided": 0}, result["live"])
        store.close.assert_called_once()

    def test_settlat_forskningssystem_anropar_ingen_livekalla(self):
        store = MagicMock()
        with patch.object(main, "Storage", return_value=store), \
             patch.object(pool_system_ledger, "system_live_coupon",
                          return_value={"settled": True}), \
             patch.object(main, "_pool_live_states") as source:
            result = main.pool_system_live(
                "europatipset", 2602, "m20", "max40-v1-b40000-ev80")

        self.assertEqual({"available": True, "settled": True}, result)
        source.assert_not_called()
        store.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
