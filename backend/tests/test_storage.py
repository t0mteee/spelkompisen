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


class PoolSharpTotalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_total_cache_and_change_only_snapshot_are_point_in_time(self):
        total = {"line": 2.25, "O": 1.97, "U": 1.93}
        odds = {"1": 2.66, "X": 2.99, "2": 3.16}
        hit = {"event_number": 8, "bookmaker": "pinnacle",
               "odds": odds, "total": total, "confidence": 0.99,
               "matched": "Deportivo - Valencia",
               "fetched_at": "2026-08-30T12:00:00Z"}

        self.assertEqual(1, self.store.save_sharp(
            "europatipset", 2604, [hit]))
        cached = self.store.get_sharp("europatipset", 2604)[8]
        self.assertEqual(total, cached["total"])
        self.store.save_sharp("europatipset", 2604, [{
            **hit, "total": None, "fetched_at": "2026-08-30T12:05:00Z",
        }])
        self.assertEqual(
            total, self.store.get_sharp("europatipset", 2604)[8]["total"])

        hits = {8: hit}
        self.assertEqual(3, self.store.save_sharp_snapshot(
            "europatipset", 2604, hits, "2026-08-30T12:00:00Z"))
        self.assertEqual(0, self.store.save_sharp_snapshot(
            "europatipset", 2604, hits, "2026-08-30T12:05:00Z"))
        changed = {8: {**hit, "total": {**total, "O": 2.01}}}
        # Returvärdet behåller sin gamla betydelse: antal nya 1X2-punkter.
        self.assertEqual(0, self.store.save_sharp_snapshot(
            "europatipset", 2604, changed, "2026-08-30T12:10:00Z"))

        rows = self.store.conn.execute(
            "SELECT line,over_odds,under_odds,fetched_at "
            "FROM sharp_total_snapshots ORDER BY id").fetchall()
        self.assertEqual(2, len(rows))
        self.assertEqual((2.25, 1.97, 1.93, "2026-08-30T12:00:00Z"),
                         tuple(rows[0]))
        self.assertEqual((2.25, 2.01, 1.93, "2026-08-30T12:10:00Z"),
                         tuple(rows[1]))


class OddsetPresenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_unchanged_price_updates_confirmation_without_movement_row(self) -> None:
        odds = {"1": 2.1, "X": 3.4, "2": 3.2}
        self.assertEqual(3, self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:00:00Z"))
        self.assertEqual(0, self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:30:00Z"))

        count = self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_odds WHERE match_id='m1'").fetchone()[0]
        self.assertEqual(3, count)
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertTrue(market["available"])
        self.assertEqual("2026-07-16T10:30:00Z", market["last_seen_at"])
        self.assertEqual("2026-07-16T10:00:00Z", market["fetched_at"])

    def test_missing_selection_suspends_market_and_reappearance_restores_it(self) -> None:
        odds = {"1": 2.1, "X": 3.4, "2": 3.2}
        self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:00:00Z")
        self.store.oddset_save_odds(
            "m1", "svenskaspel", {**odds, "X": None}, "2026-07-16T10:10:00Z")
        market = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertFalse(market["available"])
        self.assertFalse(market["selections"]["X"]["available"])

        self.store.oddset_save_odds(
            "m1", "svenskaspel", odds, "2026-07-16T10:20:00Z")
        restored = self.store.oddset_latest(["m1"])["m1"]["svenskaspel"]["1x2"]
        self.assertTrue(restored["available"])
        self.assertEqual("2026-07-16T10:20:00Z", restored["last_seen_at"])

    def test_available_derived_market_replaces_suspended_direct_market(self) -> None:
        self.store.oddset_save_odds(
            "m1", "pinnacle", {"1": 2.0, "X": 3.5, "2": 3.6},
            "2026-07-16T10:00:00Z")
        self.store.oddset_mark_market_unavailable("m1", "pinnacle", "1x2")
        self.store.oddset_save_odds(
            "m1", "derived", {"1": 2.1, "X": 3.4, "2": 3.4},
            "2026-07-16T10:10:00Z")

        market = self.store.oddset_latest(["m1"])["m1"]["pinnacle"]["1x2"]
        self.assertTrue(market["available"])
        self.assertTrue(market["derived"])
        self.assertEqual(2.1, market["1"])

    def test_source_health_roundtrips_error_state(self) -> None:
        self.store.oddset_record_source_health(
            "pinnacle", "mls", "markets", "2026-07-16T10:00:00Z",
            False, 0, "blocked")
        health = self.store.oddset_source_health()
        self.assertEqual(1, len(health))
        self.assertFalse(health[0]["ok"])
        self.assertEqual("blocked", health[0]["error"])


class OddsetValueIdentityTests(unittest.TestCase):
    def test_line_and_signal_version_are_independent_identities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                base = {
                    "match_id": "m1", "market": "ah", "sign": "H",
                    "league": "mls", "description": "A – B",
                    "match_start": "2026-07-17T10:00:00Z",
                    "at": "2026-07-16T10:00:00Z", "odds": 2.1,
                    "fair": 0.5, "edge": 0.05, "book": "svenskaspel",
                    "tier": "sharp", "git_hash": "abc",
                }
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v1"})
                store.oddset_log_flag({**base, "line": -0.75, "model_version": "s-v1"})
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v2"})
                store.oddset_log_flag({**base, "line": -0.5, "model_version": "s-v1",
                                       "edge": 0.08, "at": "2026-07-16T10:30:00Z"})

                rows = store.oddset_clv_rows()
                self.assertEqual(3, len(rows))
                v1 = next(r for r in rows if r["line"] == -0.5
                          and r["model_version"] == "s-v1")
                self.assertEqual(0.05, v1["first_edge"])
                self.assertEqual(0.08, v1["best_edge"])
            finally:
                store.close()


class OddsetAbsenceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_latest_capture_roundtrips_player_identity_and_position(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "15171583", "match_start": "2026-07-17T02:30:00Z",
            "confirmed": False, "payload_hash": "hash-1",
        }
        players = [{
            "side": "away", "player_id": 794516, "name": "Yohei Takaoka",
            "position": "G", "reason_code": 13, "reason": "avstängd",
            "description": "red_card_suspension",
            "expected_end": "2026-07-17T03:30:00+00:00",
            "apps": 13, "rating": 6.91,
        }]

        self.assertEqual(1, self.store.oddset_save_absence_capture(capture, players))
        latest = self.store.oddset_latest_absences(["m1"])["m1"]

        self.assertFalse(latest["confirmed"])
        self.assertEqual("15171583", latest["source_event_id"])
        self.assertEqual([], latest["home"])
        self.assertEqual("sofa:794516", latest["away"][0]["player_id"])
        self.assertEqual("G", latest["away"][0]["position"])
        self.assertEqual(13, latest["away"][0]["reason_code"])

    def test_empty_new_capture_replaces_current_list_but_preserves_history(self) -> None:
        base = {
            "match_id": "m1", "source_event_id": "1",
            "match_start": "2026-07-17T02:30:00Z", "confirmed": False,
        }
        self.store.oddset_save_absence_capture(
            {**base, "captured_at": "2026-07-16T10:00:00Z", "payload_hash": "h1"},
            [{"side": "home", "player_id": 7, "name": "A", "reason": "skada"}])
        self.store.oddset_save_absence_capture(
            {**base, "captured_at": "2026-07-16T12:00:00Z", "payload_hash": "h2"}, [])

        latest = self.store.oddset_latest_absences(["m1"])["m1"]
        history = self.store.oddset_absence_history("m1")

        self.assertEqual([], latest["home"])
        self.assertEqual([], latest["away"])
        self.assertEqual(2, len(history))
        self.assertEqual(1, history[0]["missing_count"])
        self.assertEqual(0, history[1]["missing_count"])

    def test_same_capture_is_idempotent(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "1", "match_start": None, "confirmed": False,
            "payload_hash": "h1",
        }
        players = [{"side": "home", "name": "No id", "reason": "skada"}]

        self.assertEqual(1, self.store.oddset_save_absence_capture(capture, players))
        self.assertEqual(0, self.store.oddset_save_absence_capture(capture, players))
        self.assertEqual(1, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_player").fetchone()[0])

    def test_invalid_player_rolls_back_capture_atomically(self) -> None:
        capture = {
            "match_id": "m1", "captured_at": "2026-07-16T10:00:00Z",
            "source_event_id": "1", "match_start": None, "confirmed": False,
            "payload_hash": "h1",
        }
        with self.assertRaises(ValueError):
            self.store.oddset_save_absence_capture(
                capture, [{"side": "unknown", "name": "A"}])

        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_absence_capture").fetchone()[0])

    def test_sources_are_collected_and_freshest_unconfirmed_capture_is_displayed(self) -> None:
        base = {"match_id": "m1", "match_start": None, "confirmed": False}
        self.store.oddset_save_absence_capture({
            **base, "captured_at": "2026-07-16T12:00:00Z",
            "provider": "flashscore", "status": "observed",
            "source_event_id": "fs:A", "payload_hash": "fs",
        }, [{"side": "home", "player_id": "fs:X", "name": "Tunn"}])
        self.store.oddset_save_absence_capture({
            **base, "captured_at": "2026-07-16T11:59:00Z",
            "provider": "sofascore", "status": "observed",
            "source_event_id": "7", "payload_hash": "sofa",
        }, [{"side": "home", "player_id": 7, "name": "Rik",
             "position": "F", "apps": 18, "rating": 7.1}])

        selected = self.store.oddset_latest_absences(["m1"])["m1"]
        self.assertEqual("flashscore", selected["provider"])
        self.assertEqual("Tunn", selected["home"][0]["name"])
        self.assertEqual("fs:X", selected["home"][0]["player_id"])

    def test_same_second_provider_captures_never_mix_players(self) -> None:
        base = {
            "match_id": "m1", "captured_at": "2026-07-16T12:00:00Z",
            "match_start": None, "confirmed": False, "status": "observed",
        }
        self.store.oddset_save_absence_capture({
            **base, "provider": "flashscore", "source_event_id": "fs:A",
            "payload_hash": "fs",
        }, [{"side": "home", "player_id": "fs:X", "name": "Flash"}])
        self.store.oddset_save_absence_capture({
            **base, "provider": "sofascore", "source_event_id": "7",
            "payload_hash": "sofa",
        }, [{"side": "away", "player_id": 7, "name": "Sofa"}])

        selected = self.store.oddset_latest_absences(["m1"])["m1"]
        self.assertEqual("sofascore", selected["provider"])
        self.assertEqual([], selected["home"])
        self.assertEqual(["Sofa"], [p["name"] for p in selected["away"]])
        self.assertEqual(2, len(self.store.oddset_absence_history("m1")))


class OddsetEloHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    @staticmethod
    def _rating(club: str, elo: float, frm: str, to: str,
                country: str = "SWE") -> dict:
        return {"club_key": club.casefold(), "club_raw": club,
                "country": country, "level": 1, "elo": elo,
                "valid_from": frm, "valid_to": to}

    def test_latest_daily_capture_ignores_historical_anchor(self) -> None:
        daily = {"captured_at": "2026-07-16T10:00:00Z",
                 "requested_date": "2026-07-16", "source": "daily",
                 "payload_hash": "daily"}
        anchor = {"captured_at": "2026-07-16T11:00:00Z",
                  "requested_date": "2024-07-01", "source": "backfill-anchor",
                  "payload_hash": "anchor"}
        self.assertEqual(1, self.store.oddset_save_elo_capture(
            daily, [self._rating("Hammarby", 1507.7, "2026-07-13", "2026-07-19")]))
        self.store.oddset_save_elo_capture(
            anchor, [self._rating("Hammarby", 1399.9, "2024-06-03", "2024-07-07")])

        self.assertEqual({"hammarby": 1508}, self.store.oddset_latest_elo())
        self.assertEqual(0, self.store.oddset_save_elo_capture(
            daily, [self._rating("Hammarby", 1507.7, "2026-07-13", "2026-07-19")]))

    def test_as_of_uses_inclusive_provider_intervals(self) -> None:
        rows = [
            self._rating("Hammarby", 1391.1, "2024-04-08", "2024-04-15"),
            self._rating("Hammarby", 1405.3, "2024-04-16", "2024-04-21"),
            self._rating("Brann", 1600.2, "2024-04-01", "2024-04-30", "NOR"),
        ]
        self.assertEqual(3, self.store.oddset_save_elo_history(
            rows, "2026-07-16T10:00:00Z"))
        self.assertEqual(0, self.store.oddset_save_elo_history(
            rows, "2026-07-16T11:00:00Z"))

        self.assertEqual({"brann": 1600, "hammarby": 1391},
                         self.store.oddset_elo_as_of("2024-04-15"))
        self.assertEqual({"brann": 1600, "hammarby": 1405},
                         self.store.oddset_elo_as_of("2024-04-16"))

    def test_invalid_country_rolls_back_capture_atomically(self) -> None:
        capture = {"captured_at": "2026-07-16T10:00:00Z",
                   "requested_date": "2026-07-16", "source": "daily",
                   "payload_hash": "bad"}
        with self.assertRaises(ValueError):
            self.store.oddset_save_elo_capture(
                capture, [self._rating("Ajax", 1700, "2026-01-01", "2026-12-31",
                                       "NED")])
        self.assertEqual(0, self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_elo_capture").fetchone()[0])


class OddsetSourceHealthHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def test_every_check_is_kept_while_latest_state_is_overwritten(self) -> None:
        """Kärnan: latest-state svarar bara 'vad sa källan sist'."""
        for at, ok, n in (("2026-08-02T12:00:00Z", True, 5),
                          ("2026-08-02T12:02:00Z", False, 0),
                          ("2026-08-02T12:04:00Z", True, 6)):
            self.store.oddset_record_source_health(
                "flashscore", "-", "live", at, ok, n,
                None if ok else "TimeoutException")
        latest = [r for r in self.store.oddset_source_health()
                  if r["source"] == "flashscore"]
        self.assertEqual(1, len(latest))
        self.assertEqual("2026-08-02T12:04:00Z", latest[0]["checked_at"])

        hist = self.store.oddset_source_health_history(source="flashscore")
        self.assertEqual(3, len(hist))
        self.assertEqual(["2026-08-02T12:04:00Z", "2026-08-02T12:02:00Z",
                          "2026-08-02T12:00:00Z"], [r["checked_at"] for r in hist])
        # Felvarvet mitt i får inte försvinna — det är hela poängen.
        failed = next(r for r in hist if not r["ok"])
        self.assertEqual("2026-08-02T12:02:00Z", failed["checked_at"])
        self.assertEqual("TimeoutException", failed["error"])

    def test_a_missing_round_is_visible_as_a_gap(self) -> None:
        """Flashscore-frågan: syns det att en källa INTE kördes i ett varv?"""
        for at in ("2026-08-02T12:00:00Z", "2026-08-02T12:02:00Z",
                   "2026-08-02T12:05:00Z", "2026-08-02T12:07:00Z"):
            self.store.oddset_record_source_health("sofascore", "-", "live", at, True, 6)
        for at in ("2026-08-02T12:00:00Z", "2026-08-02T12:05:00Z"):
            self.store.oddset_record_source_health("flashscore", "-", "live", at, True, 6)
        fs = self.store.oddset_source_health_history(source="flashscore", scope="live")
        sofa = self.store.oddset_source_health_history(source="sofascore", scope="live")
        self.assertEqual(2, len(fs))
        self.assertEqual(4, len(sofa))

    def test_same_observation_time_is_appended_once(self) -> None:
        for _ in range(3):
            self.store.oddset_record_source_health(
                "fotmob", "-", "live", "2026-08-02T12:00:00Z", True, 4)
        self.assertEqual(
            1, len(self.store.oddset_source_health_history(source="fotmob")))

    def test_since_filter_and_prune_keep_the_recent_window(self) -> None:
        self.store.oddset_record_source_health(
            "pinnacle", "allsvenskan", "1x2", "2026-05-01T12:00:00Z", True, 9)
        self.store.oddset_record_source_health(
            "pinnacle", "allsvenskan", "1x2", "2026-08-02T12:00:00Z", True, 9)
        self.assertEqual(1, len(self.store.oddset_source_health_history(
            since="2026-07-01T00:00:00Z")))
        # Gammal rad beskärs, färsk lämnas kvar.
        self.assertEqual(1, self.store.oddset_prune_source_health_log(keep_days=30))
        kvar = self.store.oddset_source_health_history(source="pinnacle")
        self.assertEqual(["2026-08-02T12:00:00Z"], [r["checked_at"] for r in kvar])
        # Latest-state rörs aldrig av beskärningen.
        self.assertTrue(any(r["source"] == "pinnacle"
                            for r in self.store.oddset_source_health()))


class SeedHintTests(unittest.TestCase):
    """Scanhintet för produkter utan listnings-API (2026-08-09).

    Topptipset hittas genom nummerscanning 80 nummer framåt från ett hint.
    API-vägen läste hintet ur meta, insamlingsvarvet körde på kodens statiska
    seed (4177) — när Dagens passerade 4248 låg omgångarna utanför varvets
    scanfönster och Topptipset Dagens slutade TYST samlas 2026-08-04 medan
    appen visade omgångarna som vanligt. En definition, båda vägarna.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_tomt_hint_ar_none_inte_krasch(self):
        self.assertIsNone(self.store.seed_hint("topptipset"))

    def test_hintet_gar_bara_framat(self):
        self.store.store_seed("topptipset", [{"draw_number": 4259}])
        self.assertEqual(4259, self.store.seed_hint("topptipset"))
        # Ett kort scanresultat får ALDRIG backa hintet — nästa varv hade då
        # blivit ännu blindare, precis den spiral som gömde buggen.
        self.store.store_seed("topptipset", [{"draw_number": 4200}])
        self.assertEqual(4259, self.store.seed_hint("topptipset"))
        self.store.store_seed("topptipset", [{"draw_number": 4262}])
        self.assertEqual(4262, self.store.seed_hint("topptipset"))

    def test_tom_lista_lamnar_hintet_orort(self):
        self.store.store_seed("topptipset", [{"draw_number": 4259}])
        self.store.store_seed("topptipset", [])
        self.store.store_seed("topptipset", None)
        self.assertEqual(4259, self.store.seed_hint("topptipset"))

    def test_tar_bade_objekt_och_dictar(self):
        class Draw:
            draw_number = 1861
        self.store.store_seed("topptipsetextra", [Draw()])
        self.assertEqual(1861, self.store.seed_hint("topptipsetextra"))

    def test_skrapigt_varde_kraschar_inte_uppslaget(self):
        self.store.meta_set("latest_topptipset", "inte-ett-tal")
        self.assertIsNone(self.store.seed_hint("topptipset"))


if __name__ == "__main__":
    unittest.main()
