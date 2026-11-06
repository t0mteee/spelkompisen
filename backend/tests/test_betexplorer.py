"""bet365 via Betexplorer som referensbok (beslut 2026-11-06-betexplorer-bet365, val 0).

Fixturerna är verkliga utdrag ur Betexplorers publika svar 2026-11-06 ~09:57Z:
Premier Leagues fixtursida och /match-odds/ för Everton–Coventry (OUYQUF9b,
avspark 20:00Z) med bet365 och en annan bok kvar per tabell.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app import betexplorer as be
from app import oddset, oddset_value
from app.storage import Storage

FIX = Path(__file__).parent / "fixtures"
FIXTURES = (FIX / "betexplorer_fixtures.html").read_text()
BODY = {bt: (FIX / f"betexplorer_{bt}.json").read_text() for bt in be.BET_TYPES}
NOW = dt.datetime(2026, 11, 6, 9, 57, tzinfo=dt.timezone.utc)
OBS = "2026-11-06T09:57:00Z"


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class ParseTests(unittest.TestCase):
    def test_fixtursidan_ger_id_lag_och_avspark_i_utc(self):
        rows = be.parse_fixtures(FIXTURES, NOW)
        self.assertEqual(["OUYQUF9b", "A72E8Phd", "Eyc1EfPH", "WfxZSgvB"],
                         [r["event_id"] for r in rows])
        self.assertEqual(("Everton", "Coventry", "2026-11-06T20:00:00Z"),
                         (rows[0]["home"], rows[0]["away"], rows[0]["start"]))
        # Fulham–Newcastle har tom tidcell = samma tid som Arsenal–Hull.
        self.assertEqual("2026-11-07T15:00:00Z", rows[3]["start"])

    def test_fixtursida_utan_tabell_ar_ett_kallfel(self):
        with self.assertRaises(ValueError):
            be.parse_fixtures("<html>blockerad</html>", NOW)

    def test_avsparkens_format(self):
        self.assertEqual("2026-11-07T12:30:00Z", be.parse_start("Tomorrow 13:30", NOW))
        self.assertEqual("2026-11-08T14:00:00Z", be.parse_start("08.11. 15:00", NOW))
        self.assertEqual("2027-01-01T20:00:00Z", be.parse_start("01.01.2027 21:00", NOW))
        # Sommartid: svensk tid är UTC+2.
        self.assertEqual("2027-05-01T13:00:00Z", be.parse_start("01.05.2027 15:00", NOW))
        # Utan år över årsskiftet: närmaste datum framåt.
        dec = dt.datetime(2026, 12, 30, 12, 0, tzinfo=dt.timezone.utc)
        self.assertEqual("2027-01-02T12:30:00Z", be.parse_start("02.01. 13:30", dec))
        self.assertIsNone(be.parse_start("FT", NOW))

    def test_1x2_med_bokens_egna_andringstider(self):
        p = be.parse_odds(BODY["1x2"], "1x2", "bet365", OBS)
        self.assertEqual({"1": 1.67, "X": 4.0, "2": 5.0}, p["odds"])
        # data-created är svensk tid: 06,11,2026,10,46 = 09:46Z.
        self.assertEqual("2026-11-06T09:46:00Z", p["changed"]["1"])
        self.assertEqual("2026-11-04T00:19:00Z", p["changed"]["X"])

    def test_saknad_bok_ar_none_och_skrap_ar_kallfel(self):
        self.assertIsNone(be.parse_odds(BODY["1x2"], "1x2", "Pinnacle", OBS))
        with self.assertRaises(ValueError):
            be.parse_odds("<html>", "1x2", "bet365", OBS)

    def test_andringstid_efter_observationen_sparas_inte(self):
        p = be.parse_odds(BODY["1x2"], "1x2", "bet365", "2026-11-05T00:00:00Z")
        self.assertEqual({"X": "2026-11-04T00:19:00Z"}, p["changed"])

    def test_handikapp_i_hemmalagets_tecken_och_kvartslinor(self):
        p = be.parse_odds(BODY["ah"], "ah", "bet365", OBS)
        lines = {r["line"]: (r["H"], r["A"]) for r in p["lines"]}
        self.assertEqual((7.0, 1.1), lines[-2.75])        # "-2.5, -3" = −2,75
        self.assertEqual((1.27, 3.55), lines[0.0])
        self.assertEqual(-0.75, be.main_line(p["lines"], "H", "A")["line"])

    def test_ou_huvudlina_och_ofullstandig_lina_hoppas_over(self):
        p = be.parse_odds(BODY["ou"], "ou", "bet365", OBS)
        self.assertEqual([1.5, 2.25, 2.5, 2.75], [r["line"] for r in p["lines"]])
        self.assertNotIn(7.5, [r["line"] for r in p["lines"]])   # bara ett pris
        main = be.main_line(p["lines"], "O", "U")
        self.assertEqual((2.75, 1.93, 1.93), (main["line"], main["O"], main["U"]))

    def test_takten_tatnar_mot_avspark(self):
        def due(hours_left, minutes_ago):
            start = _iso(NOW + dt.timedelta(hours=hours_left))
            asked = _iso(NOW - dt.timedelta(minutes=minutes_ago))
            return be.refresh_due(start, asked, NOW)
        self.assertTrue(be.refresh_due(_iso(NOW), None, NOW))     # aldrig frågad
        self.assertTrue(due(2, 30))
        self.assertFalse(due(2, 10))
        self.assertFalse(due(10, 60))
        self.assertTrue(due(10, 120))
        self.assertFalse(due(72, 120))
        self.assertFalse(due(72, 360))
        self.assertTrue(due(72, 720))


class ClientTests(unittest.TestCase):
    def test_artig_takt_age_avdras_och_sidans_egna_huvuden(self):
        sleeps = []
        clock = iter([0.0, 1.0, 3.0])   # 2:a anropet efter 1 s
        client = be.Betexplorer(sleep=sleeps.append, clock=lambda: next(clock),
                                now=lambda: NOW)
        fx = mock.Mock(status_code=200, text=FIXTURES, headers={"age": "430"},
                       raise_for_status=lambda: None)
        od = mock.Mock(status_code=200, text=BODY["1x2"], headers={"age": "0"},
                       raise_for_status=lambda: None)
        with mock.patch.object(client._client, "get", side_effect=[fx, od]) as get:
            f = client.fixtures("/football/england/premier-league/")
            o = client.odds("OUYQUF9b", "1x2", "bet365",
                            referer="https://www.betexplorer.com/football/england/premier-league/")
        client.close()
        self.assertEqual([be.CRAWL_DELAY_S - 1.0], sleeps)
        self.assertEqual("2026-11-06T09:49:50Z", f["observed_at"])   # 430 s Age
        self.assertEqual(OBS, o["observed_at"])
        url = get.call_args_list[1].args[0]
        self.assertTrue(url.endswith("/match-odds/OUYQUF9b/0/1x2/odds/"))
        headers = get.call_args_list[1].kwargs["headers"]
        self.assertEqual("XMLHttpRequest", headers["X-Requested-With"])
        self.assertIn("premier-league", headers["Referer"])
        self.assertEqual(2, client.calls)

    def test_arkivhistoriken_anvands_aldrig(self):
        # Historiska priser bakfylls aldrig (observationstidsregeln).
        src = Path(be.__file__).read_text()
        self.assertNotIn("/archive-odds/{", src)
        self.assertNotIn('"/archive-odds', src)


class _FakeClient:
    """Svarar med fixturerna; `missing` = marknader där bet365 saknas."""

    def __init__(self, observed: str, missing=(), fail=()):
        self.observed, self.missing, self.fail = observed, set(missing), set(fail)
        self.log = []
        self.calls = 0

    def fixtures(self, path):
        self.calls += 1
        self.log.append(("fixtures", path))
        return {"rows": be.parse_fixtures(FIXTURES, NOW), "observed_at": self.observed}

    def odds(self, event_id, bet_type, bookie, referer=None):
        self.calls += 1
        self.log.append((event_id, bet_type))
        if bet_type in self.fail:
            raise RuntimeError("503")
        parsed = (None if bet_type in self.missing
                  else be.parse_odds(BODY[bet_type], bet_type, bookie, self.observed))
        return {"parsed": parsed, "observed_at": self.observed}


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "t.db")
        self.store.oddset_upsert_match({
            "id": "pin:1", "league": "premier_league", "home": "Everton",
            "away": "Coventry City", "start": "2026-11-06T20:00:00Z"})
        self.report = {"errors": []}

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _run(self, client, now=NOW):
        return oddset._collect_betexplorer(
            self.store, self.report, client=client, clock=lambda: 0.0, now=now)

    def test_sparar_tre_marknader_med_egen_observationstid_och_presence(self):
        client = _FakeClient(OBS)
        summary = self._run(client)
        self.assertEqual(1, summary["matches"])
        latest = self.store.oddset_latest(["pin:1"])["pin:1"]["bet365"]
        self.assertEqual(1.67, latest["1x2"]["1"])
        self.assertEqual(OBS, latest["1x2"]["last_seen_at"])
        self.assertEqual((2.75, 1.93), (latest["ou"]["line"], latest["ou"]["O"]))
        self.assertEqual((-0.75, 1.85), (latest["ah"]["line"], latest["ah"]["H"]))
        caps = self.store.conn.execute(
            "SELECT market, listed, line, changed_at FROM oddset_betexplorer_capture "
            "ORDER BY id").fetchall()
        self.assertEqual(["1x2", "ou", "ah"], [c["market"] for c in caps])
        self.assertEqual({"1": "2026-11-06T09:46:00Z", "X": "2026-11-04T00:19:00Z",
                          "2": "2026-11-06T09:46:00Z"}, json.loads(caps[0]["changed_at"]))
        # Referensen skapar aldrig matchidentiteter (Leeds, Arsenal, Fulham saknas hos oss).
        self.assertEqual(1, len(self.store.oddset_matches(since="2026-11-01T00:00:00Z")))

    def test_inom_intervallet_fragas_inget_och_kant_id_sparar_fixtursidan(self):
        self._run(_FakeClient(OBS))
        again = _FakeClient(OBS)
        self.assertEqual(0, self._run(again, now=NOW + dt.timedelta(minutes=10))["due"])
        self.assertEqual([], again.log)
        later = _FakeClient("2026-11-06T18:30:00Z")
        self._run(later, now=dt.datetime(2026, 11, 6, 18, 29, tzinfo=dt.timezone.utc))
        self.assertNotIn("fixtures", [c[0] for c in later.log])   # id:t är känt
        self.assertEqual(["1x2", "ou", "ah"], [c[1] for c in later.log])

    def test_saknad_bok_markeras_och_bokfors(self):
        self._run(_FakeClient(OBS))
        later = dt.datetime(2026, 11, 6, 18, 29, tzinfo=dt.timezone.utc)
        self._run(_FakeClient("2026-11-06T18:30:00Z", missing={"1x2"}), now=later)
        latest = self.store.oddset_latest(["pin:1"])["pin:1"]["bet365"]
        self.assertFalse(latest["1x2"]["available"])
        self.assertTrue(latest["ou"]["available"])
        last = self.store.conn.execute(
            "SELECT ok, listed FROM oddset_betexplorer_capture WHERE market='1x2' "
            "ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((1, 0), (last["ok"], last["listed"]))

    def test_transportfel_bokfors_utan_att_markera_franvaro(self):
        self._run(_FakeClient(OBS))
        later = dt.datetime(2026, 11, 6, 18, 29, tzinfo=dt.timezone.utc)
        self._run(_FakeClient("2026-11-06T18:30:00Z", fail={"ou"}), now=later)
        latest = self.store.oddset_latest(["pin:1"])["pin:1"]["bet365"]
        self.assertTrue(latest["ou"]["available"])      # källfel ≠ frånvaro
        self.assertEqual(1, len(self.report["errors"]))
        failed = self.store.conn.execute(
            "SELECT COUNT(*) FROM oddset_betexplorer_capture WHERE ok=0").fetchone()[0]
        self.assertEqual(1, failed)

    def test_startad_match_sparas_aldrig(self):
        late = dt.datetime(2026, 11, 6, 19, 55, tzinfo=dt.timezone.utc)
        self._run(_FakeClient("2026-11-06T20:01:00Z"), now=late)
        self.assertNotIn("bet365", self.store.oddset_latest(["pin:1"]).get("pin:1", {}))

    def test_payload_bar_bokens_andringstid(self):
        start = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5)
        self.store.oddset_upsert_match({
            "id": "pin:2", "league": "premier_league", "home": "A", "away": "B",
            "start": _iso(start)})
        seen = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2))
        self.store.oddset_save_odds("pin:2", "bet365", {"1": 2.0, "X": 3.4, "2": 3.9}, seen)
        self.store.oddset_save_betexplorer_capture(
            "pin:2", "abcdEFGH", "bet365", "1x2", seen, True, listed=True,
            prices={"1": 2.0, "X": 3.4, "2": 3.9},
            changed_at={"1": "2026-11-06T08:00:00Z"})
        payload = oddset.matches_payload(self.store, light=True, compact_movement=True)
        row = next(m for m in payload["matches"] if m["id"] == "pin:2")
        self.assertEqual({"1": "2026-11-06T08:00:00Z"},
                         row["odds"]["bet365"]["1x2"]["book_changed_at"])


class RollTests(unittest.TestCase):
    """bet365 är en referensbok: aldrig bok att slå, aldrig ankare."""

    def test_sparrad_i_vardemotorn_och_aldrig_ankare(self):
        self.assertIn("bet365", oddset_value.REFERENCE_BOOKS)
        self.assertIn("bet365", oddset_value.ANCHOR_SOURCES)
        self.assertNotIn("bet365", oddset_value.ANCHOR_BY_MARKET.values())
        self.assertNotIn("bet365", {b["key"] for b in oddset.BOOKS})
        self.assertIn("bet365", oddset.passive_sources())
        self.assertNotIn("bet365", json.dumps(oddset_value.sharp_params()))

    def test_bet365_ger_aldrig_vardeflagga(self):
        now = dt.datetime.now(dt.timezone.utc)
        seen = now - dt.timedelta(minutes=5)
        mk = lambda v: {**v, "available": True, "last_seen_at": _iso(seen),  # noqa: E731
                        "fetched_at": _iso(seen)}
        m = {"id": "m1", "home": "A", "away": "B", "league": "mls",
             "start": _iso(now + dt.timedelta(hours=30)),
             "odds": {"smarkets": {"1x2": mk({"1": 2.0, "X": 3.6, "2": 4.0})},
                      "bet365": {"1x2": mk({"1": 3.0, "X": 3.6, "2": 4.0})}}}
        oddset_value.attach_value([m])
        self.assertNotIn("1x2", m.get("value") or {})


if __name__ == "__main__":
    unittest.main()
