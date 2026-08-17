import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import fotmob, live_radar
from app.storage import Storage


NOW = dt.datetime(2026, 7, 25, 19, 10, tzinfo=dt.timezone.utc)


def _ts(iso: str) -> int:
    """Epoch ur ISO — handräknade epochtal blir fel och testet blir otydligt."""
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())

AT = "2026-07-25T19:10:00Z"
START_AT = "2026-07-25T18:00:00Z"


def event(description="2nd half"):
    return {
        "id": 123,
        "tournament": {
            "uniqueTournament": {"id": 20, "name": "Eliteserien"}},
        "homeTeam": {"name": "Home"},
        "awayTeam": {"name": "Away"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
        "startTimestamp": int((NOW - dt.timedelta(minutes=70)).timestamp()),
        "status": {"type": "inprogress", "description": description},
        "time": {
            "currentPeriodStartTimestamp":
                int((NOW - dt.timedelta(minutes=25)).timestamp())},
    }


def fs_capture(store, *, flashscore_id="ANK00001", league="eliteserien",
               home="Home", away="Away", captured_at=AT, minute=70,
               home_score=1, away_score=0, xg=(3.0, 0.4), big=(4, 1),
               shots=(18, 5), on=(9, 2), inside=(14, 3), **extra):
    """Spara en Flashscore-rad — radarns ANKARE sedan 2026-08-06.

    Testerna byggde tidigare sina ankare på `oddset_save_live_capture`
    (Sofascore). Den källan är urkopplad ur radarn, så ett ankare måste nu
    komma från Flashscore. `None` i ett måttpar betyder att providern inte
    rapporterar fältet — skilt från mätt 0.
    """
    from app.flashscore import CAPTURE_VERSION as FS_VERSION
    row = {
        "flashscore_id": flashscore_id,
        "captured_at": captured_at,
        "capture_version": FS_VERSION,
        "league": league,
        "tournament": league,
        "start_at": START_AT,
        "home": home,
        "away": away,
        "minute": minute,
        "home_score": home_score,
        "away_score": away_score,
        "xg_home": xg[0], "xg_away": xg[1],
        "big_chances_home": big[0], "big_chances_away": big[1],
        "shots_home": shots[0], "shots_away": shots[1],
        "shots_on_home": on[0], "shots_on_away": on[1],
        "shots_inside_home": inside[0], "shots_inside_away": inside[1],
    }
    row.update(extra)
    store.live_flashscore_save(row)
    return row


def stats(xg=(3.0, 0.4), big=(4, 1), shots=(18, 5),
          on=(9, 2), inside=(14, 3), touches=(37, 8)):
    values = {
        "expectedGoals": xg,
        "bigChanceCreated": big,
        "totalShotsOnGoal": shots,
        "shotsOnGoal": on,
        "totalShotsInsideBox": inside,
        "touchesInOppBox": touches,
        "cornerKicks": (8, 2),
    }
    return {"statistics": [{"period": "ALL", "groups": [{
        "groupName": "all",
        "statisticsItems": [
            {"key": key, "homeValue": pair[0], "awayValue": pair[1]}
            for key, pair in values.items()
        ],
    }]}]}


class LiveRadarTests(unittest.TestCase):
    def test_valid_empty_sofa_roster_ends_previous_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                live_radar.record_presence(
                    store, live_radar.SOFA_PRESENCE_KEY, [123], AT)
                later = NOW + dt.timedelta(minutes=2)
                with patch.object(live_radar, "_live_get",
                                  return_value={"events": []}):
                    report = live_radar.collect(store, now=later)
                self.assertEqual(0, report["live"])
                presence = __import__("json").loads(
                    store.meta_get(live_radar.SOFA_PRESENCE_KEY))
                self.assertEqual([], presence["active_ids"])
                self.assertIn("123", presence["ended_at"])
            finally:
                store.close()

    def test_malformed_sofa_roster_never_ends_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                live_radar.record_presence(
                    store, live_radar.SOFA_PRESENCE_KEY, [123], AT)
                with patch.object(live_radar, "_live_get", return_value={}):
                    report = live_radar.collect(
                        store, now=NOW + dt.timedelta(minutes=2))
                self.assertIn("error", report)
                presence = __import__("json").loads(
                    store.meta_get(live_radar.SOFA_PRESENCE_KEY))
                self.assertEqual(["123"], presence["active_ids"])
                health = next(row for row in store.oddset_source_health()
                              if row["source"] == "sofascore" and
                              row["scope"] == "live")
                self.assertFalse(health["ok"])
            finally:
                store.close()

    def test_europacuperna_ar_i_radarscopet_via_huvudturneringens_ut(self):
        """Kvalet delar huvudturneringens UT hos Sofascore (verifierat
        2026-07-28), så ETT id per cup täcker även kvalrundorna. Direkt i
        TARGET_UT, inte via SOFA_UT (wp9c-fingeravtrycket)."""
        self.assertEqual("champions_league", live_radar.TARGET_UT[7])
        self.assertEqual("europa_league", live_radar.TARGET_UT[679])
        self.assertEqual("conference_league", live_radar.TARGET_UT[17015])
        for key in ("champions_league", "europa_league", "conference_league"):
            self.assertEqual(0, live_radar.LEAGUE_PRIORITY[key],
                             "cuperna får inte klippas som friendlies")

    def test_nya_toppligor_ar_i_live_scope_utan_att_andra_v22_scope(self):
        expected = {188: "bestadeild",
                    39: "danish_superliga", 38: "belgian_pro_league",
                    238: "primeira_liga", 16736: "bolivian_primera"}
        for tournament_id, league in expected.items():
            self.assertEqual(league, live_radar.TARGET_UT[tournament_id])
            self.assertNotIn(league, live_radar.SOFA_UT)
            self.assertEqual(0, live_radar.LEAGUE_PRIORITY[league])

    def test_v10_och_alla_synliga_ligor_har_liveprioritet(self):
        self.assertEqual("chance-gap-shadow-v10", live_radar.RADAR_VERSION)
        # Passerade gränser är frysta — en ändring skulle märka om historiska
        # captures och tyst blanda ihop kohorterna.
        self.assertEqual("2026-08-01T08:00:00Z",
                         live_radar.RADAR_V3_STARTED_AT)
        self.assertEqual("2026-08-01T21:00:00Z",
                         live_radar.RADAR_V4_STARTED_AT)
        self.assertEqual("2026-08-03T06:00:00Z",
                         live_radar.RADAR_V5_STARTED_AT)
        self.assertEqual("2026-08-06T16:45:00Z",
                         live_radar.RADAR_V6_STARTED_AT)
        self.assertEqual("2026-08-06T21:40:00Z",
                         live_radar.RADAR_V7_STARTED_AT)
        self.assertEqual("2026-08-09T17:15:00Z",
                         live_radar.RADAR_V8_STARTED_AT)
        self.assertEqual("2026-08-09T18:00:00Z",
                         live_radar.RADAR_V9_STARTED_AT)
        self.assertEqual("2026-08-18T00:00:00Z",
                         live_radar.RADAR_VERSION_STARTED_AT)
        for key in ("bestadeild", "premier_league", "serie_a", "la_liga",
                    "bundesliga", "danish_superliga", "belgian_pro_league",
                    "primeira_liga", "bolivian_primera"):
            self.assertEqual(0, live_radar.LEAGUE_PRIORITY[key])

    def test_global_friendly_requires_match_in_our_oddset_view(self):
        friendly = event()
        friendly["tournament"]["uniqueTournament"] = {
            "id": 853, "name": "Club Friendly Games"}
        self.assertFalse(live_radar._known_friendly(friendly, []))
        self.assertTrue(live_radar._known_friendly(friendly, [{
            "league": "friendlies", "home": "Home FC", "away": "Away",
            "start": "2026-07-25T18:00:00Z",
        }]))
        self.assertTrue(live_radar._same_team("Chelsea (Eng)", "Chelsea"))

    def test_friendly_med_spegelvant_hemmalag_slapps_in(self):
        """Odds-källorna och Sofascore är oense om hemmalaget på turné-
        matcher (Chelsea–WSW 2026-07-28 låg spegelvänd och doldes helt);
        spärren ska matcha laguppsättningen, inte planhalvorna."""
        friendly = event()
        friendly["tournament"]["uniqueTournament"] = {
            "id": 853, "name": "Club Friendly Games"}
        self.assertTrue(live_radar._known_friendly(friendly, [{
            "league": "friendlies", "home": "Away", "away": "Home FC",
            "start": "2026-07-25T18:00:00Z",
        }]))
        # Speglingen får inte öppna för fel avspark: samma lag men >2 h bort
        # (returmötet i en dubbelmatch) ska fortfarande avvisas.
        self.assertFalse(live_radar._known_friendly(friendly, [{
            "league": "friendlies", "home": "Away", "away": "Home FC",
            "start": "2026-07-25T08:00:00Z",
        }]))

    def test_ett_lag_racker_nar_kandidaten_ar_entydig(self):
        """Manchester City och Chelsea föll 2026-08-09 på MOTSTÅNDARENS namn:
        `Atl. Madrid` mot `Atlético Madrid` och `Johor DT` mot `Johor Darul
        Takzim`. Ett lag spelar en match i taget — delar exakt en Oddset-match
        i samma tidslucka ett lag med den här, är det samma match."""
        oddset = [{"league": "friendlies", "home": "Manchester City",
                   "away": "Atlético Madrid", "start": "2026-08-09T11:00:00Z"}]
        start_ts = _ts("2026-08-09T11:00:00Z")
        self.assertTrue(live_radar.known_friendly(
            "Manchester City (Eng)", "Atl. Madrid (Esp)", start_ts, oddset))
        # ... och det gäller oavsett vilken sida som är igenkännlig.
        johor = [{"league": "friendlies", "home": "Johor Darul Takzim",
                  "away": "Chelsea", "start": "2026-08-09T12:00:00Z"}]
        self.assertTrue(live_radar.known_friendly(
            "Johor DT (Mys)", "Chelsea (Eng)", start_ts + 3600, johor))

    def test_tva_kandidater_ger_avslag_inte_gissning(self):
        """Entydighet är hela säkerheten i regeln."""
        start_ts = _ts("2026-08-09T11:00:00Z")
        oddset = [
            {"league": "friendlies", "home": "Liverpool", "away": "AS Monaco",
             "start": "2026-08-09T11:00:00Z"},
            {"league": "friendlies", "home": "Liverpool", "away": "Everton",
             "start": "2026-08-09T11:10:00Z"},
        ]
        self.assertFalse(live_radar.known_friendly(
            "Liverpool (Eng)", "Nagelfar (Ger)", start_ts, oddset))

    def test_okand_avspark_ger_inget_ensidigt_slapp(self):
        """Utan avspark finns ingen tidslucka, och då håller inte argumentet."""
        oddset = [{"league": "friendlies", "home": "Liverpool",
                   "away": "AS Monaco", "start": "2026-08-09T11:00:00Z"}]
        self.assertFalse(live_radar.known_friendly(
            "Liverpool (Eng)", "Monaco (Fra)", None, oddset))

    def test_ensidigt_slapp_kraver_ratt_tidslucka(self):
        oddset = [{"league": "friendlies", "home": "Liverpool",
                   "away": "AS Monaco", "start": "2026-08-09T11:00:00Z"}]
        self.assertTrue(live_radar.known_friendly(
            "Liverpool (Eng)", "Monaco (Fra)", _ts("2026-08-09T11:00:00Z"),
            oddset))
        self.assertFalse(live_radar.known_friendly(   # sex timmar bort
            "Liverpool (Eng)", "Monaco (Fra)",
            _ts("2026-08-09T17:00:00Z"), oddset))

    def test_ensidigt_slapp_anvander_snava_fonstret(self):
        """Två timmar är toleransen när BÅDA lag stämmer, inte när ett lag är
        hela identitetsbeviset. Ett lag kan spela två träningsmatcher samma dag."""
        oddset = [{"league": "friendlies", "home": "Manchester City",
                   "away": "Atlético Madrid", "start": "2026-08-09T13:00:00Z"}]
        self.assertFalse(live_radar.known_friendly(
            "Manchester City (Eng)", "Nagelfar (Ger)",
            _ts("2026-08-09T11:00:00Z"), oddset))
        oddset[0]["start"] = "2026-08-09T11:14:00Z"
        self.assertTrue(live_radar.known_friendly(
            "Manchester City (Eng)", "Nagelfar (Ger)",
            _ts("2026-08-09T11:00:00Z"), oddset))

    def test_ensidigt_slapp_faller_stangt_pa_trasig_kand_tid(self):
        oddset = [{"league": "friendlies", "home": "Manchester City",
                   "away": "Atlético Madrid", "start": "trasig-tid"}]
        self.assertFalse(live_radar.known_friendly(
            "Manchester City (Eng)", "Nagelfar (Ger)",
            _ts("2026-08-09T11:00:00Z"), oddset))

    def test_truppmarkor_sparrar_aven_ensidigt(self):
        """`Inter` och `Inter U23` är två lag — regeln får inte slå ihop dem."""
        oddset = [{"league": "friendlies", "home": "Internazionale U23",
                   "away": "Pergolettese", "start": "2026-08-09T11:00:00Z"}]
        self.assertFalse(live_radar.known_friendly(
            "Inter (Ita)", "Como (Ita)", _ts("2026-08-09T11:00:00Z"), oddset))

    def test_capture_parses_observed_xg_and_match_clock(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)

        self.assertEqual("eliteserien", capture["league"])
        self.assertEqual(70, capture["minute"])
        self.assertEqual(3.0, capture["xg_home"])
        self.assertEqual(9, capture["shots_on_home"])
        self.assertEqual(37, capture["touches_box_home"])

    def test_large_xg_gap_is_shadow_signal_while_time_remains(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("strong", signal["level"])
        self.assertEqual("xg", signal["kind"])
        self.assertEqual("Home", signal["team"])
        self.assertEqual(2.0, signal["chance_gap"])
        self.assertEqual(20, signal["remaining_min"])

    def test_xg_missing_ger_skottsignal_markt_i_kind_inte_i_prosan(self):
        """Märkningen bärs av `kind` — som UI:t sorterar och etiketterar på —
        inte av ordet "proxy" i texten. Ordet är vårt internord och stod på tre
        ställen samtidigt (statsrad, kortrad, fotnot); det togs bort ur korten
        2026-07-25. Att xG saknas syns redan i statsraden, och förbehållet om
        att skottmåttet är oprövat står en gång i fotnoten."""
        capture = live_radar.parse_capture(
            event(), stats(xg=(None, None)), captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("watch", signal["level"])
        self.assertEqual("proxy", signal["kind"])
        self.assertNotIn("proxy", signal["reason"].casefold())

    def test_texten_lovar_inte_mer_an_nivan(self):
        """"Trycker på" stod på varje kort, även vid FÖLJER — en match i 9:e
        minuten med ett skott fick en dramatisk mening om ingenting."""
        tidig = event()
        tidig["time"]["currentPeriodStartTimestamp"] = int(
            (NOW - dt.timedelta(minutes=9)).timestamp())
        svag = live_radar.parse_capture(
            tidig, stats(xg=(None, None), big=(0, 0), shots=(1, 0),
                         on=(1, 0), inside=(0, 0), touches=(1, 0)),
            captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(svag)
        self.assertEqual("info", signal["level"])
        self.assertIn("inget utstick", signal["reason"])

        stark = live_radar.parse_capture(
            event(), stats(xg=(None, None)), captured_at=AT, now=NOW)
        aktiv = live_radar.radar_signal(stark)
        self.assertEqual("watch", aktiv["level"])
        self.assertIn("men", aktiv["reason"])          # namnger gapet
        self.assertNotIn("inget utstick", aktiv["reason"])

    def test_missing_chance_fields_are_not_interpreted_as_zero(self):
        capture = live_radar.parse_capture(
            event(), None, captured_at=AT, now=NOW)
        signal = live_radar.radar_signal(capture)

        self.assertEqual("no_stats", signal["kind"])
        self.assertEqual("info", signal["level"])
        self.assertEqual(0.0, signal["score"])
        # texten ska peka ut KÄLLAN som gränsen, inte antyda ett mätt nollvärde
        self.assertIn("källan", signal["reason"].casefold())

    def test_missing_score_is_never_interpreted_as_zero_zero(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)
        capture["home_score"] = None
        signal = live_radar.radar_signal(capture)
        self.assertEqual("no_score", signal["kind"])
        self.assertEqual("info", signal["level"])

    def test_late_match_does_not_signal_even_with_historical_gap(self):
        capture = live_radar.parse_capture(
            event(), stats(), captured_at=AT, now=NOW)
        capture["minute"] = 84

        self.assertEqual("info", live_radar.radar_signal(capture)["level"])

    def test_capture_storage_is_idempotent_and_payload_is_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                capture = live_radar.parse_capture(
                    event(), stats(), captured_at=AT, now=NOW)
                self.assertEqual(1, store.oddset_save_live_capture(capture))
                self.assertEqual(0, store.oddset_save_live_capture(capture))
                # Sofascore-lagret är fortfarande idempotent, men det NÅR inte
                # radarn längre: kortet nedan kommer från Flashscore-ankaret.
                self.assertEqual(
                    [], live_radar.payload(store, now=NOW)["matches"],
                    "sofascore-captures får inte längre bli livekort")

                fs_capture(store)
                payload = live_radar.payload(store, now=NOW)
                self.assertEqual("shadow", payload["mode"])
                self.assertEqual(1, payload["signal_count"])
                self.assertEqual(1, len(payload["matches"]))
            finally:
                store.close()

    def test_payload_doljer_matcher_utan_chansmatt_men_inte_matta_nollor(self):
        """Samans krav 2026-07-25 med dess egen nyansering.

        Matcher där källan inte rapporterar skott/chanser alls ska bort ur vyn.
        En match som är tidig och HAR mätta nollor ska däremot stanna — annars
        döljs riktiga ligamatcher de första minuterna. Skillnaden är None mot 0.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                # 1. helt utan chansfält (försäsongsmatchen) → döljs
                fs_capture(store, flashscore_id="TOM00901", home="Tom",
                           xg=(None, None), big=(None, None),
                           shots=(None, None), on=(None, None),
                           inside=(None, None))
                # 2. tidig match med MÄTTA nollor → stannar
                fs_capture(store, flashscore_id="NOLL0902", home="Noll",
                           xg=(None, None), big=(0, 0), shots=(0, 0),
                           on=(0, 0), inside=(0, 0))

                payload = live_radar.payload(store, now=NOW)
                visade = {row["event_id"] for row in payload["matches"]}
                self.assertIn("flashscore:NOLL0902", visade,
                              "mätt noll är ett värde, inte saknad data")
                self.assertNotIn("flashscore:TOM00901", visade)
                self.assertEqual(1, payload["hidden_no_stats"])
                self.assertIn("eliteserien", payload["hidden_by_league"])
            finally:
                store.close()

    def test_payload_uses_fotmob_shots_when_sofascore_has_no_stats_or_xg(self):
        """Superettan får inte döljas när FotMob har skott men saknar xG."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                sofa_event = event()
                sofa_event["id"] = 512557100
                sofa_event["tournament"]["uniqueTournament"] = {
                    "id": 46, "name": "Superettan"}
                sofa_event["homeTeam"]["name"] = "GIF Sundsvall"
                sofa_event["awayTeam"]["name"] = "Falkenbergs FF"
                store.oddset_save_live_capture(live_radar.parse_capture(
                    sofa_event, None, captured_at=AT, now=NOW))
                store.live_fotmob_save({
                    "fotmob_id": 5125571,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "superettan",
                    "tournament": "Superettan",
                    "start_at": START_AT,
                    "home": "GIF Sundsvall",
                    "away": "Falkenbergs FF",
                    "minute": 55,
                    "home_score": 1,
                    "away_score": 1,
                    "shots_home": 9,
                    "shots_away": 5,
                    "shots_on_home": 5,
                    "shots_on_away": 2,
                    "shots_inside_home": 6,
                    "shots_inside_away": 3,
                })

                result = live_radar.payload(store, now=NOW)
                self.assertEqual(1, len(result["matches"]))
                match = result["matches"][0]
                self.assertEqual("proxy", match["signal"]["kind"])
                self.assertEqual("fotmob", match["signal"]["stats_source"])
                self.assertIsNone(match["signal"]["xg_source"])
                self.assertEqual(5, match["fotmob"]["shots_on_home"])
                self.assertEqual(0, result["hidden_no_stats"])
            finally:
                store.close()

    def test_gyori_provider_alias_merges_to_one_live_card(self):
        """Samma Győr-match hade olika ordföljd hos providrarna och visades
        därför dubbelt: `ETO FC Győr` mot FotMobs `Györi ETO`."""
        self.assertTrue(live_radar._same_team(
            "RSC Anderlecht", "Anderlecht"))
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fs_capture(store, flashscore_id="GYOR0001",
                           league="conference_league",
                           home="ETO FC Győr", away="Atert Bissen",
                           xg=(None, None), big=(0, 1), shots=(1, 3),
                           on=(0, 1), inside=(1, 2))
                store.live_fotmob_save({
                    "fotmob_id": 7772026,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "conference_league",
                    "tournament": "Conference League Qualification",
                    "start_at": START_AT,
                    "home": "Györi ETO",
                    "away": "Atert Bissen",
                    "minute": 70,
                    "home_score": 0,
                    "away_score": 0,
                    "xg_home": 0.03,
                    "xg_away": 0.15,
                    "shots_on_home": 0,
                    "shots_on_away": 1,
                })

                result = live_radar.payload(store, now=NOW)
                self.assertEqual(1, len(result["matches"]))
                match = result["matches"][0]
                self.assertEqual("flashscore:GYOR0001", match["event_id"])
                self.assertEqual("fotmob", match["signal"]["stats_source"])
                self.assertEqual(0.15, match["fotmob"]["xg_away"])
            finally:
                store.close()

    def test_fresh_provider_roster_hides_matches_that_are_no_longer_live(self):
        """En lyckad ny live-lista är ett starkare slutbesked än capture-TTL:n.

        Båda providrarna har här observerat sina live-listor efter de senaste
        capturerna, och match-id:n finns inte längre kvar. Korten ska då bort
        direkt i stället för att ligga kvar i tolv minuter.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                store.oddset_save_live_capture(live_radar.parse_capture(
                    event(), stats(), captured_at=AT, now=NOW))
                store.live_fotmob_save({
                    "fotmob_id": 777001,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "superettan",
                    "tournament": "Superettan",
                    "start_at": START_AT,
                    "home": "Örebro SK",
                    "away": "Utsiktens BK",
                    "minute": 70,
                    "home_score": 0,
                    "away_score": 0,
                    "xg_home": 1.0,
                    "xg_away": 0.4,
                })
                live_radar.record_presence(
                    store, live_radar.SOFA_PRESENCE_KEY, [123], AT)
                live_radar.record_presence(
                    store, live_radar.FOTMOB_PRESENCE_KEY, [777001], AT)
                observed = "2026-07-25T19:11:00Z"
                live_radar.record_presence(
                    store, live_radar.SOFA_PRESENCE_KEY, [], observed)
                live_radar.record_presence(
                    store, live_radar.FOTMOB_PRESENCE_KEY, [], observed)

                result = live_radar.payload(
                    store, now=NOW + dt.timedelta(minutes=2))
                self.assertEqual([], result["matches"])
            finally:
                store.close()

    def test_provider_roster_older_than_capture_cannot_hide_live_match(self):
        """Ordningen skyddar mot cache/tidsförskjutning: en roster måste vara
        minst lika ny som capturen innan frånvaro får tolkas som slutsignal."""
        from app.flashscore import PRESENCE_KEY as FS_PRESENCE_KEY
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fs_capture(store, flashscore_id="ROSTER01")
                live_radar.record_presence(
                    store, FS_PRESENCE_KEY, ["ROSTER01"],
                    "2026-07-25T19:08:00Z")
                live_radar.record_presence(
                    store, FS_PRESENCE_KEY, [],
                    "2026-07-25T19:09:00Z")

                result = live_radar.payload(store, now=NOW)
                self.assertEqual(1, len(result["matches"]))
            finally:
                store.close()

    def test_payload_shows_fotmob_match_even_when_sofascore_misses_it(self):
        """Stats finns → kortet visas, även utan en Sofascore-grundrad."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                store.live_fotmob_save({
                    "fotmob_id": 777001,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "superettan",
                    "tournament": "Superettan",
                    "start_at": START_AT,
                    "home": "Örebro SK",
                    "away": "Utsiktens BK",
                    "minute": 40,
                    "home_score": 0,
                    "away_score": 0,
                    "big_chances_home": 2,
                    "big_chances_away": 0,
                    "shots_home": 8,
                    "shots_away": 2,
                    "shots_on_home": 4,
                    "shots_on_away": 1,
                    "shots_inside_home": 6,
                    "shots_inside_away": 1,
                })

                result = live_radar.payload(store, now=NOW)
                self.assertEqual(1, len(result["matches"]))
                match = result["matches"][0]
                self.assertEqual("fotmob:777001", match["event_id"])
                self.assertEqual("fotmob", match["signal"]["stats_source"])
                self.assertEqual("Örebro SK", match["home"])
                self.assertEqual(4, match["fotmob"]["shots_on_home"])
                self.assertEqual(0, result["hidden_no_stats"])
            finally:
                store.close()

    def test_fotmob_xg_wins_at_halftime_even_when_its_clock_is_empty(self):
        """Tom FotMob-klocka får inte gömma xG som faktiskt rapporteras."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fs_capture(store, flashscore_id="BPHAM001",
                           league="allsvenskan", home="IF Brommapojkarna",
                           away="Hammarby IF", minute=45,
                           home_score=0, away_score=0,
                           xg=(None, None), big=(0, 0), shots=(4, 10),
                           on=(0, 2), inside=(4, 9))
                store.live_fotmob_save({
                    "fotmob_id": 999001,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "allsvenskan",
                    "tournament": "Allsvenskan",
                    "start_at": START_AT,
                    "home": "IF Brommapojkarna",
                    "away": "Hammarby",
                    "minute": None,
                    "home_score": 0,
                    "away_score": 0,
                    "xg_home": 0.22,
                    "xg_away": 0.96,
                    "shots_on_home": 0,
                    "shots_on_away": 2,
                })

                match = live_radar.payload(store, now=NOW)["matches"][0]
                self.assertEqual("xg", match["signal"]["kind"])
                self.assertEqual("fotmob", match["signal"]["stats_source"])
                self.assertEqual("fotmob", match["signal"]["xg_source"])
                self.assertEqual(0.96, match["fotmob"]["xg_away"])
                self.assertEqual(45, match["signal"]["remaining_min"])
                self.assertEqual(45, match["signal"]["basis"]["minute"])
                self.assertEqual(
                    "flashscore", match["signal"]["basis"]["minute_source"],
                    "klockan lånas från ankaret, som numera är Flashscore")
                self.assertEqual(
                    "fotmob", match["signal"]["basis"]["home_score_source"])
            finally:
                store.close()

    def test_stale_linked_provider_can_never_bear_a_fresh_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fs_capture(store, flashscore_id="STALE001", xg=(None, None))
                store.live_fotmob_save({
                    "fotmob_id": 8001,
                    "captured_at": "2026-07-25T18:57:00Z",  # 13 min gammal
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "eliteserien", "tournament": "Eliteserien",
                    "start_at": START_AT, "home": "Home", "away": "Away",
                    "minute": 57, "home_score": 0, "away_score": 0,
                    "xg_home": 9.0, "xg_away": 0.0,
                })
                payload = live_radar.payload(store, now=NOW)
                self.assertEqual(1, len(payload["matches"]))
                self.assertEqual(
                    "flashscore",
                    payload["matches"][0]["signal"]["stats_source"])
            finally:
                store.close()

    def test_provider_link_requires_start_and_unique_non_youth_identity(self):
        anchor = {"league": "serie_a", "home": "Inter", "away": "Como",
                  "start_at": START_AT}
        u23 = {"fotmob_id": 1, "league": "serie_a", "home": "Inter U23",
               "away": "Como", "start_at": START_AT}
        self.assertFalse(live_radar._same_team("Inter", "Inter U23"))
        self.assertFalse(live_radar._same_team("Inter", "Inter Miami"))
        self.assertIsNone(live_radar._fotmob_for(anchor, [[u23]]))

        # MLS-natten 2026-08-01/02: `Los Angeles FC` normaliseras till
        # `los angeles` och flerords-prefixregeln gjorde det till samma lag som
        # `Los Angeles Galaxy`. Två MLS-klubbar som spelar samtidigt — en falsk
        # merge blandar ställning, statistik och odds från skilda matcher.
        self.assertFalse(live_radar._same_team(
            "Los Angeles FC", "Los Angeles Galaxy"))
        self.assertFalse(live_radar._same_team("Los Angeles FC", "LA Galaxy"))
        # Spärren får inte äta det legitima flerords-prefixet.
        self.assertTrue(live_radar._same_team(
            "New England", "New England Revolution"))

        no_start = dict(u23, fotmob_id=2, home="Inter", start_at=None)
        self.assertIsNone(live_radar._fotmob_for(anchor, [[no_start]]))

        first = dict(u23, fotmob_id=3, home="Inter")
        second = dict(u23, fotmob_id=4, home="Inter")
        self.assertIsNone(live_radar._fotmob_for(anchor, [[first], [second]]),
                          "tvetydiga kandidater ska aldrig väljas efter ordning")

    def test_mirrored_provider_series_is_transposed_never_raw(self):
        """Udinese–Trabzonspor 2026-08-02: Sofascore hade Udinese hemma,
        Flashscore/FotMob tvärtom — matchen låg som två kort. Spegelvänd länk
        accepteras nu, men serien MÅSTE uttryckas i ankarets orientering:
        rå länkning hade satt Trabzonspors xG på Udinese."""
        anchor = {"league": "friendlies", "home": "Udinese",
                  "away": "Trabzonspor", "start_at": START_AT}
        fs_row = {"flashscore_id": "AbC123", "league": "friendlies",
                  "home": "Trabzonspor", "away": "Udinese",
                  "start_at": START_AT, "minute": 60,
                  "home_score": 1, "away_score": 0,
                  "xg_home": 2.0, "xg_away": 0.5,
                  "shots_home": 12, "shots_away": 3}

        linked = live_radar._series_for(anchor, [[fs_row]], "flashscore_id",
                                        claimed=set())
        self.assertIsNotNone(linked)
        row = linked[-1]
        # Ankarets orientering: Udinese är hemma, så Trabzonspors 2.0 xG och
        # 1–0-ledning ska ligga på BORTA-sidan.
        self.assertEqual("Udinese", row["home"])
        self.assertEqual(0.5, row["xg_home"])
        self.assertEqual(2.0, row["xg_away"])
        self.assertEqual(0, row["home_score"])
        self.assertEqual(1, row["away_score"])
        self.assertEqual(3, row["shots_home"])
        self.assertEqual("AbC123", row["flashscore_id"], "id är osidat")

        # Direkt träff transponeras INTE.
        rak = dict(fs_row, home="Udinese", away="Trabzonspor")
        direkt = live_radar._series_for(anchor, [[rak]], "flashscore_id",
                                        claimed=set())
        self.assertEqual(2.0, direkt[-1]["xg_home"])

        # Spegling får inte öppna för fel avspark (returmöte i dubbelmatch).
        fel_start = dict(fs_row, start_at="2026-07-25T08:00:00Z")
        self.assertIsNone(live_radar._series_for(
            anchor, [[fel_start]], "flashscore_id", claimed=set()))

    def test_clockless_flashscore_row_borrows_the_anchor_clock(self):
        """Flashscores dagsfeed är CDN-fryst upp mot två minuter, så en färsk
        statrad sparas utan klocka. Chansmåtten måste stanna hos Flashscore
        medan minut/ställning lånas — med synlig proveniens."""
        capture = {
            "captured_at": "2026-08-02T14:00:00Z",
            "home": "Nordic United", "away": "Ljungskile",
            "minute": None, "home_score": None, "away_score": None,
            "xg_home": 1.9, "xg_away": 0.3,
            "shots_home": 10, "shots_away": 4,
        }
        anchor = {"minute": 63, "home_score": 0, "away_score": 0}

        signal, _ = live_radar._flashscore_signal([capture], anchor)
        basis = signal["basis"]
        self.assertEqual(63, basis["minute"])
        # Långivaren är FotMob sedan Sofascore kopplades ur radarn. Källan
        # måste följa med raden — hårdkodad proveniens blir en ren lögn så
        # snart ankaret byts.
        self.assertEqual("fotmob", basis["minute_source"])
        self.assertEqual("fotmob", basis["home_score_source"])
        self.assertEqual("flashscore", signal["stats_source"],
                         "chansmåtten får aldrig byta källa med klockan")
        self.assertEqual("strong", signal["level"])

        # Utan ankare finns ingen klocka att låna — då blir det ingen signal
        # alls, aldrig en gissad ställning.
        utan, _ = live_radar._flashscore_signal([capture], None)
        self.assertIsNone(utan["basis"]["minute_source"])
        self.assertEqual("info", utan["level"])

    def test_observed_provider_aliases_link_the_same_club(self):
        """Utan dessa blev samma match två journalkort: odds på den ena raden,
        facit på den andra, och noll bidrag till blindkohorten."""
        self.assertTrue(live_radar._same_team("LA Galaxy", "Los Angeles Galaxy"))
        self.assertTrue(live_radar._same_team("Atlanta Utd", "Atlanta United"))
        # Aliaset ska verka åt båda håll och tåla providerns egen stavning.
        self.assertTrue(live_radar._same_team("Los Angeles Galaxy", "LA Galaxy"))
        self.assertTrue(live_radar._same_team("CF Montreal", "CF Montréal"))
        # Flashscore skriver svenska klubbar utan IFK; `_NOISE` rymmer redan
        # `if`/`gif`/`bk` men inte `ifk`. Gav dubbelt kort för IFK Göteborg.
        self.assertTrue(live_radar._same_team("Goteborg", "IFK Göteborg"))
        self.assertTrue(live_radar._same_team("Norrkoping", "IFK Norrköping"))
        self.assertTrue(live_radar._same_team("Varnamo", "IFK Värnamo"))
        # Aliaset får inte dra in andra göteborgsklubbar.
        self.assertFalse(live_radar._same_team("Goteborg", "GAIS"))
        self.assertFalse(live_radar._same_team("IFK Göteborg", "Häcken"))
        # Kambi/Pinnacle skriver `PSV ` med blanksteg; normaliserat blir det
        # tre tecken och enords-spärren kräver fyra innan prefix tillåts.
        self.assertTrue(live_radar._same_team("PSV ", "PSV Eindhoven"))
        self.assertTrue(live_radar._same_team("PSV Eindhoven", "PSV"))
        # Spärren för korta namn måste stå kvar för alla ANDRA — historiken
        # rymmer aik/odd/lyn/qpr där prefixmatchning vore farlig.
        self.assertFalse(live_radar._same_team("AIK", "AIK Fotboll Ungdom"))
        self.assertFalse(live_radar._same_team("Odd", "Odense"))

    def test_international_short_names_link_with_match_context(self):
        """Europacupkvällen 2026-08-06: fyra matcher låg som dubbletter.

        Flashscore skriver kortnamn + landskod i internationellt spel medan
        de andra skriver fullnamn. Landskoden strippades redan, men det som
        blev kvar var ett ENORDSNAMN — och enords-prefix är spärrat för att
        `Inter` inte ska bli `Inter Miami`. Alias per klubb är en förlorad
        kapplöpning; varje kvalomgång drar in nya lag.
        """
        ctx = live_radar._same_team_in_context
        for short, full in (("Paide (Est)", "Paide Linnameeskond"),
                            ("SK Rapid (Aut)", "SK Rapid Wien"),
                            ("Jagiellonia (Pol)", "Jagiellonia Białystok"),
                            ("Univ. Craiova (Rou)", "Universitatea Craiova")):
            self.assertFalse(live_radar._same_team(short, full),
                             "strikta regeln ska INTE luckras upp")
            self.assertTrue(ctx(short, full), f"{short} ↔ {full}")

        # Spärrarna gäller oförändrat även i den lösare regeln.
        self.assertFalse(ctx("Los Angeles FC", "Los Angeles Galaxy"))
        self.assertFalse(ctx("Inter", "Inter U23"))
        self.assertFalse(ctx("Manchester United", "Manchester City"))
        self.assertFalse(ctx("Arsenal", "Arsenal Women"))
        # `Inter` ↔ `Inter Miami` passerar namnregeln men kan aldrig länkas:
        # skyddet är kontexten på anropsstället (samma liga, exakt avspark,
        # en enda kandidat) — därför får regeln aldrig användas fristående.
        self.assertTrue(ctx("Inter", "Inter Miami"))

    def test_context_rule_only_fills_the_gap_the_strict_rule_leaves(self):
        """Två steg: strikt först, kontextregeln bara när strikt gav noll.
        Tvetydighet länkar aldrig — varken i steg ett eller steg två."""
        anchor = {"league": "europa_league", "start_at": START_AT,
                  "home": "KuPS (Fin)", "away": "Univ. Craiova (Rou)"}

        def series(home, away, fid):
            return [{"league": "europa_league", "start_at": START_AT,
                     "home": home, "away": away, "fotmob_id": fid,
                     "captured_at": AT}]

        exact = series("KuPS", "Universitatea Craiova", 1)
        self.assertIsNotNone(live_radar._linked_series(anchor, [exact]))
        # En strikt träff får aldrig konkurrera med en lös: strikt vinner.
        strict = series("KuPS (Fin)", "Univ. Craiova (Rou)", 2)
        hit = live_radar._linked_series(anchor, [exact, strict])
        self.assertEqual(2, hit[0][-1]["fotmob_id"])
        # Två kandidater på den LÖSA regeln är tvetydighet → ingen länk.
        loose_twin = series("KuPS Kuopio", "Universitatea Craiova", 3)
        self.assertIsNone(
            live_radar._linked_series(anchor, [exact, loose_twin]))

    def test_proxy_fires_on_the_fields_the_provider_actually_sends(self):
        """v7, förregistrerad i docs/radar-proxy-v7-forregistrering-2026-08-07.

        Villkoret krävde `skott i box`, som bara finns i 43 % av matcherna —
        exakt de som ändå har xG. Proxyn tillförde därför NOLL matcher utöver
        xG-signalen medan 59 % aldrig kunde få någon signal alls.
        `farliga skott` = på mål + blockerade har 100 % täckning.
        """
        bas = {"home": "Hem", "away": "Borta", "minute": 60,
               "home_score": 0, "away_score": 0,
               "shots_on_home": 6, "shots_on_away": 1,
               "shots_blocked_home": 3, "shots_blocked_away": 0,
               "shots_home": 14, "shots_away": 3,
               "corners_home": 7, "corners_away": 1}
        signal = live_radar.radar_signal(bas)
        self.assertEqual("proxy", signal["kind"])
        self.assertEqual("watch", signal["level"],
                         "6 på mål + 3 blockerade = 9 farliga, 0 mål")
        self.assertIn("farliga", signal["reason"])

        # Tröskelvärdena är OFÖRÄNDRADE: 5 på mål minus mål, 8 farliga.
        under = live_radar.radar_signal({**bas, "shots_on_home": 4})
        self.assertEqual("info", under["level"], "4 − 0 < 5 på mål")
        fa_farliga = live_radar.radar_signal(
            {**bas, "shots_on_home": 5, "shots_blocked_home": 2})
        self.assertEqual("info", fa_farliga["level"], "5 + 2 = 7 < 8 farliga")

        # Mål äter gapet, precis som förut.
        med_mal = live_radar.radar_signal({**bas, "home_score": 2})
        self.assertEqual("info", med_mal["level"], "6 − 2 < 5")

    def test_proxy_still_prefers_big_chances_when_they_exist(self):
        """Den rikare grenen är oförändrad — v7 lägger till, tar inte bort."""
        signal = live_radar.radar_signal({
            "home": "Hem", "away": "Borta", "minute": 55,
            "home_score": 0, "away_score": 0,
            "big_chances_home": 2, "big_chances_away": 0,
            "shots_on_home": 2, "shots_on_away": 1,
            "shots_inside_home": 5, "shots_inside_away": 2})
        self.assertEqual("proxy", signal["kind"])
        self.assertEqual("watch", signal["level"], "2 stora chanser, 0 mål")
        self.assertIn("stora chanser", signal["reason"])

    def test_base_package_row_is_not_ranked_as_partial(self):
        """Rankningen måste spegla proxyns AKTIVERING. Med `inside` kvar där
        hade en rad som visst kan signalera rankats som partiell och kunnat
        döljas av en sämre källa."""
        bas = {"shots_on_home": 6, "shots_on_away": 2,
               "shots_blocked_home": 3, "shots_blocked_away": 1}
        self.assertEqual(2, live_radar._stats_rank(bas)[0])
        # xG slår fortfarande allt.
        self.assertEqual(
            4, live_radar._stats_rank({**bas, "xg_home": 1.2, "xg_away": 0.3})[0])

    def test_alias_survives_the_country_label(self):
        """Aliaset slogs upp på hela strängen, alltså på `goteborg (swe)` —
        en nyckel som aldrig finns. Varje alias slutade därmed tyst gälla så
        snart providern satte dit en landskod, och `Goteborg (Swe)` ↔
        `IFK Göteborg` låg som två kort medan testet för samma par UTAN kod
        var grönt."""
        self.assertEqual("ifk goteborg",
                         live_radar.live_norm_team("Goteborg (Swe)"))
        self.assertTrue(
            live_radar._same_team("Goteborg (Swe)", "IFK Göteborg"))
        self.assertTrue(
            live_radar._same_team("Norrkoping (Swe)", "IFK Norrköping"))
        # Spärren mot andra göteborgsklubbar gäller oförändrat.
        self.assertFalse(live_radar._same_team("Goteborg (Swe)", "GAIS"))

    def test_provider_view_carries_the_row_version_for_the_ledger(self):
        """Journalen läser `radar_version` UR vyn. Utan den härleds kohorten
        ur observerade växlingar, och varje rad efter den sista kända
        växlingen blir felaktigt transitional — alltså ur blindkohorten."""
        self.assertIn("radar_version", live_radar._FLASHSCORE_VIEW_KEYS)
        self.assertIn("radar_version", live_radar._FOTMOB_VIEW_KEYS)

    def test_sofascore_is_no_longer_a_live_source(self):
        """Urkopplad 2026-08-06: den rapporterade xG som 0.0 i stället för att
        utelämna det, vilket läser som en mätning. Resultat, modellstatistik
        och frånvaro rör den inte."""
        self.assertEqual(("flashscore", "fotmob"), live_radar.LIVE_SOURCES)
        self.assertNotIn("sofascore", live_radar._SOURCE_PRIORITY)

    def test_fotmob_ar_primar_och_vinner_vid_lika_bra_data(self):
        """Samans beslut 2026-07-28: Sofascore slutar vara primär källa.
        När båda providrarna har xG (lika rang) ska FotMob bära signalen;
        Sofascore vinner bara med strikt bättre statistik."""
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                sofa_event = event()
                sofa_event["id"] = 611001
                sofa_event["homeTeam"]["name"] = "Rosenborg"
                sofa_event["awayTeam"]["name"] = "Molde"
                store.oddset_save_live_capture(live_radar.parse_capture(
                    sofa_event, stats(xg=(1.4, 0.3)), captured_at=AT, now=NOW))
                store.live_fotmob_save({
                    "fotmob_id": 611002,
                    "captured_at": AT,
                    "capture_version": fotmob.CAPTURE_VERSION,
                    "league": "eliteserien",
                    "tournament": "Eliteserien",
                    "start_at": START_AT,
                    "home": "Rosenborg",
                    "away": "Molde",
                    "minute": 70,
                    "home_score": 1,
                    "away_score": 0,
                    "xg_home": 2.1,
                    "xg_away": 0.4,
                })

                match = live_radar.payload(store, now=NOW)["matches"][0]
                self.assertEqual("fotmob", match["signal"]["stats_source"])
                self.assertEqual("fotmob", match["signal"]["xg_source"])
                self.assertEqual(2.1, match["fotmob"]["xg_home"])
            finally:
                store.close()

    def test_payload_uses_real_fifteen_minute_capture_for_recent_xg(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                fs_capture(store, flashscore_id="DELTA001", xg=(1.5, 0.3),
                           captured_at="2026-07-25T18:55:00Z")
                fs_capture(store, flashscore_id="DELTA001", xg=(3.0, 0.4),
                           captured_at=AT)

                signal = live_radar.payload(
                    store, now=NOW)["matches"][0]["signal"]
                self.assertEqual(1.5, signal["recent_xg"])
                self.assertIn("senaste 15 min", signal["reason"])
            finally:
                store.close()

    def test_source_health_fails_when_no_live_stats_can_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                def sofa(path):
                    if path == "/sport/football/events/live":
                        return {"events": [event()]}
                    raise RuntimeError("stats unavailable")

                with patch.object(live_radar, "_live_get", side_effect=sofa):
                    report = live_radar.collect(store, now=NOW)

                self.assertEqual(1, report["live"])
                self.assertEqual(0, report["stats_ok"])
                self.assertIn(
                    '"active_ids":["123"]',
                    store.meta_get(live_radar.SOFA_PRESENCE_KEY))
                health = next(
                    row for row in store.oddset_source_health()
                    if row["source"] == "sofascore" and row["scope"] == "live")
                self.assertFalse(health["ok"])
                self.assertIn("RuntimeError", health["error"])
            finally:
                store.close()

    def test_partial_sofa_stats_failure_is_not_green_in_health_or_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                first = event()
                second = event()
                second["id"] = 124
                second["homeTeam"] = {"name": "Other Home"}

                def sofa(path):
                    if path == "/sport/football/events/live":
                        return {"events": [first, second]}
                    if path == "/event/123/statistics":
                        return stats()
                    raise RuntimeError("stats unavailable")

                with patch.object(live_radar, "_live_get", side_effect=sofa):
                    report = live_radar.collect(store, now=NOW)

                self.assertEqual(2, report["live"])
                self.assertEqual(1, report["stats_ok"])
                self.assertFalse(report["health_ok"])
                health = next(
                    row for row in store.oddset_source_health()
                    if row["source"] == "sofascore" and row["scope"] == "live")
                self.assertFalse(health["ok"])
                self.assertEqual(2, health["event_count"])
                self.assertIn("124: RuntimeError", health["error"])
                # Radarns payload rapporterar bara sina EGNA livekällor;
                # Sofascores hälsa finns kvar i lagret för resultatspåret.
                self.assertNotIn(
                    "sofascore",
                    {row["source"] for row
                     in live_radar.payload(store, now=NOW)["source_health"]})
            finally:
                store.close()

    def test_payload_last_run_is_common_watermark_for_live_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                for source, checked in (
                        ("flashscore", "2026-07-25T19:10:00Z"),
                        ("fotmob", "2026-07-25T19:09:00Z"),
                        # Sofascore kontrolleras fortfarande för resultat och
                        # frånvaro, men får INTE hålla tillbaka radarns
                        # vattenstämpel — den är inte längre en livekälla.
                        ("sofascore", "2026-07-25T18:00:00Z")):
                    store.oddset_record_source_health(
                        source, "-", "live", checked, True, 0)
                payload = live_radar.payload(store, now=NOW)
                self.assertEqual("2026-07-25T19:09:00Z", payload["last_run"])
                self.assertEqual(
                    {"flashscore", "fotmob"}, set(payload["source_runs"]))
                self.assertEqual(
                    ["flashscore", "fotmob"], payload["sources"])
                self.assertEqual(2, len(payload["source_health"]))
            finally:
                store.close()

    def test_payload_has_no_common_watermark_when_a_source_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Storage(Path(tmp) / "test.db")
            try:
                store.oddset_record_source_health(
                    "flashscore", "-", "live", AT, True, 0)
                store.meta_set("live_radar_last_run", AT)
                payload = live_radar.payload(store, now=NOW)
                self.assertIsNone(payload["last_run"])
                self.assertEqual({"flashscore"}, set(payload["source_runs"]))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()


class LiveRadarIsolationTests(unittest.TestCase):
    """Härdningen 2026-07-25: radarn får aldrig skada den spelbara vägen."""

    def test_radar_har_egen_httpklient_skild_fran_modellen(self):
        # Delade tidigare _sofa_get med oddset_data (xG till modellen) — en
        # shadow-poll var 5:e minut kunde då strypa den spelbara pipelinen.
        from app import oddset_data
        self.assertTrue(hasattr(live_radar, "_live_get"))
        self.assertFalse(hasattr(live_radar, "_sofa_get"))
        self.assertLess(live_radar.LIVE_TIMEOUT_S, 20.0)
        self.assertIsNot(
            live_radar._live_get, getattr(oddset_data, "_sofa_get", None))

    def test_tak_och_budget_ar_satta(self):
        self.assertGreater(live_radar.MAX_MATCHES, 0)
        # 30→60 (Samans beslut 2026-07-28): en kvaltorsdag spelar 53 cup-
        # matcher samtidigt och kvalen har chansdata — gränsen här finns för
        # att nästa höjning också ska vara ett medvetet beslut, inte en drift.
        self.assertLessEqual(live_radar.MAX_MATCHES, 60)
        self.assertLess(live_radar.BUDGET_S, 300)   # måste rymmas i en 5-min-tick

    def test_proxy_och_xg_har_skilda_faltnamn(self):
        import inspect
        src = inspect.getsource(live_radar.radar_signal)
        self.assertIn('"proxy_index"', src)   # enhetslöst index
        self.assertIn('"chance_gap"', src)    # xG i mål
