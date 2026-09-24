"""GET /api/external-odds är ren läsning (2026-09-24).

Endpointen anropade `collect_pinnacle(cache=True)`: den hämtade Pinnacle,
skrev `sharp_odds`/`sharp_snapshots` och satte dubbeltrafikspärren utan
närvarorad. Nu visar den bara vad insamlingen redan observerat.
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main
from app.storage import Storage

PRODUCT = "stryktipset"


def _iso(at):
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


class Fixture:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.store = Storage(self.db)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def capture(self, draw, event, fetched_at, status, source="sharp", complete=None):
        if complete is None:
            complete = status in ("matched", "derived") if source == "sharp" else True
        self.store.conn.execute(
            "INSERT INTO pool_market_capture (product, draw_number, source, "
            "event_number, fetched_at, status, odds_complete, streck_complete) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (PRODUCT, draw, source, event, fetched_at, status, int(complete)))
        self.store.conn.commit()

    def price(self, draw, event, fetched_at, odds=(2.0, 3.4, 3.8)):
        self.store.save_sharp(PRODUCT, draw, [{
            "event_number": event, "bookmaker": "pinnacle",
            "odds": dict(zip(("1", "X", "2"), odds)), "total": None,
            "confidence": 1.0, "matched": f"H{event} - B{event}",
            "fetched_at": fetched_at}])
        self.store.save_sharp_snapshot(
            PRODUCT, draw, {event: {"odds": dict(zip(("1", "X", "2"), odds))}},
            fetched_at)


class NoNetwork(Exception):
    pass


def _boom(*_args, **_kwargs):
    raise NoNetwork("GET /api/external-odds får inte hämta något")


class ExternalOddsReadOnlyTests(Fixture, unittest.TestCase):
    """GET /api/external-odds: bara det insamlingen redan observerat."""

    NOW = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)
    DRAW = 4972

    def ago(self, minutes):
        return _iso(self.NOW - dt.timedelta(minutes=minutes))

    def fixture(self, close):
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES (?,?,?,?)", (PRODUCT, self.DRAW, "Open", _iso(close)))
        self.store.conn.commit()
        self.price(self.DRAW, 1, self.ago(10))
        self.capture(self.DRAW, 1, self.ago(10), "matched")
        self.price(self.DRAW, 2, self.ago(40))
        self.capture(self.DRAW, 2, self.ago(40), "matched")
        self.capture(self.DRAW, 2, self.ago(13), "ambiguous")
        self.capture(self.DRAW, 3, self.ago(13), "not_listed")
        self.store.pool_match_diagnostic_record(PRODUCT, self.DRAW, {
            3: {"svs_home": "Hammarby", "svs_away": "AIK",
                "candidates": [
                    {"cand_home": "Hammarby IF", "cand_away": "AIK Solna", "score": 0.71},
                    {"cand_home": "Hammarby W", "cand_away": "AIK W", "score": 0.4}]}},
            self.ago(13))
        for event in (1, 2, 3, 4):
            self.capture(self.DRAW, event, self.ago(5), "observed", source="svs",
                         complete=event != 4)

    def counts(self):
        tables = ("sharp_odds", "sharp_snapshots", "pool_market_capture",
                  "pool_match_diagnostic", "meta", "snapshots")
        return {t: self.store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables} | {"meta_rows": self.store.conn.execute(
                    "SELECT key, value FROM meta ORDER BY key").fetchall()}

    def call(self, draw, now=None):
        from app import sharp_service
        with patch.object(main, "Storage", side_effect=lambda: Storage(self.db)), \
                patch.object(sharp_service, "collect_pinnacle", _boom), \
                patch.object(main, "_get_draw", _boom), \
                patch.object(main, "SvenskaSpel", _boom), \
                patch("app.pinnacle.Pinnacle", _boom):
            if now is None:
                return main.external_odds(PRODUCT, draw)
            return main._external_odds_view(Storage(self.db), PRODUCT, draw, now)

    def test_inget_natanrop_och_inga_skrivningar(self):
        self.fixture(self.NOW + dt.timedelta(hours=5))
        before = self.counts()
        payload = self.call(self.DRAW)
        self.assertEqual(before, self.counts())
        self.assertTrue(payload["read_only"])
        self.assertEqual(self.DRAW, payload["draw_number"])
        self.assertEqual(4, len(payload["matches"]))

    def test_lank_pris_farskhet_och_kandidat(self):
        self.fixture(self.NOW + dt.timedelta(hours=5))
        payload = self.call(self.DRAW, now=self.NOW)
        m = {row["event_number"]: row for row in payload["matches"]}
        self.assertEqual(("matched", True), (m[1]["status"], m[1]["fresh"]))
        self.assertEqual({"1": 2.0, "X": 3.4, "2": 3.8}, m[1]["external"]["odds"])
        self.assertEqual(self.ago(10), m[1]["external"]["observed_at"])
        self.assertIsNone(m[1]["stale"])
        # Länken tappad efter priset: priset visas som observerat men inaktuellt.
        self.assertEqual(("ambiguous", False), (m[2]["status"], m[2]["fresh"]))
        self.assertEqual("link_lost", m[2]["stale"]["reason"])
        self.assertEqual("Pinnacle-länken tappad (tvetydig) sedan 13:47", m[2]["stale"]["text"])
        self.assertEqual(self.ago(13), m[2]["status_at"])
        # Avvisad: närmaste kandidat ur pool_match_diagnostic, inget pris.
        self.assertIsNone(m[3]["external"])
        self.assertEqual("not_listed", m[3]["status"])
        self.assertEqual(("Hammarby IF", "AIK Solna", 0.71),
                         (m[3]["candidate"]["home"], m[3]["candidate"]["away"],
                          m[3]["candidate"]["score"]))
        self.assertEqual("Hammarby - AIK", m[3]["description"])
        # Aldrig observerad av sharp-insamlingen; SvS-odds saknades.
        self.assertEqual("never_observed", m[4]["status"])
        self.assertFalse(m[4]["ss_has_odds"])
        self.assertTrue(m[1]["ss_has_odds"])
        self.assertEqual((1, 2), (payload["n_fresh"], payload["n_cached"]))
        self.assertEqual(self.ago(10), payload["last_observed_at"])
        self.assertFalse(payload["closed"])

    def test_stangd_omgang_bedoms_vid_spelstopp(self):
        # Spelstopp NOW−30. Priset NOW−40 var 10 min gammalt vid stoppet och
        # alltså färskt då; not_listed NOW−5 kom efter stoppet och räknas inte.
        close = self.NOW - dt.timedelta(minutes=30)
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES (?,?,?,?)", (PRODUCT, self.DRAW, "Closed", _iso(close)))
        self.store.conn.commit()
        self.price(self.DRAW, 1, self.ago(40))
        self.capture(self.DRAW, 1, self.ago(40), "matched")
        self.capture(self.DRAW, 1, self.ago(5), "not_listed")   # efter stoppet
        payload = self.call(self.DRAW, now=self.NOW + dt.timedelta(hours=3))
        row = payload["matches"][0]
        self.assertTrue(payload["closed"])
        self.assertEqual(_iso(close), payload["as_of"])
        self.assertEqual(("matched", True), (row["status"], row["fresh"]))

    def test_lika_likhet_avgors_av_senaste_observation_som_tid(self):
        self.capture(self.DRAW, 5, self.ago(3), "not_listed")
        # "13:50+02:00" är 11:50Z: senare som sträng, tidigare som tid.
        self.store.pool_match_diagnostic_record(PRODUCT, self.DRAW, {
            5: {"cand_home": "A", "cand_away": "B", "score": 0.6}},
            "2026-09-24T13:50:00+02:00")
        self.store.pool_match_diagnostic_record(PRODUCT, self.DRAW, {
            5: {"cand_home": "C", "cand_away": "D", "score": 0.6}},
            "2026-09-24T11:55:00Z")
        payload = self.call(self.DRAW, now=self.NOW)
        self.assertEqual("C", payload["matches"][0]["candidate"]["home"])

    def test_utan_draw_valjs_lokal_oppen_omgang_utan_natanrop(self):
        self.fixture(self.NOW + dt.timedelta(hours=5))
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES (?,?,?,?)", (PRODUCT, 4973, "Open",
                                 _iso(self.NOW + dt.timedelta(days=7))))
        self.store.conn.commit()
        self.assertEqual(self.DRAW, main._local_open_draw(self.store, PRODUCT, self.NOW))
        self.assertIsNone(main._local_open_draw(self.store, "europatipset", self.NOW))


if __name__ == "__main__":
    unittest.main()


class CollectorStartTests(unittest.TestCase):
    """POST /api/collector/start får aldrig starta en parallell insamlare."""

    def test_start_vagras_och_ingen_trad_startas(self):
        from fastapi import HTTPException
        from app import main
        from app.collector import collector
        with self.assertRaises(HTTPException) as caught:
            main.collector_start()
        self.assertEqual(409, caught.exception.status_code)
        self.assertFalse(collector.running)
