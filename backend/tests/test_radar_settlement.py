"""Settlement av radarns capture-ögonblick (shadow) — kontraktet i praktiken.

Testerna låser de förregistrerade reglerna i docs/live-radar-2026-07-25.md:
utfall A/B ur senare captures i SAMMA serie, censur i stället för gissning,
append-once utan omskrivning, delad tröskelfunktion och strikt
provider-separation. Momentfacitet är uttryckligen rå-providerdiagnostik;
signaljournalen bär UI:ts eventuella lånade klocka/ställning.
"""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import flashscore, fotmob, live_radar, live_settlement
from app.storage import Storage
from scripts import migrera_radar_event_id_text, migrera_radar_settlement

# Ligger efter aktuell kohortgräns så att T0-captures hamnar i den
# AKTUELLA kohorten — facit rapporterar bara aktuell RADAR_VERSION. Fixturerna
# skrivs av dagens kod, som stämplar raden med dagens version; en fixtur
# daterad före fönstret blir därför korrekt `transitional`. Datumet ska följa
# med vid VARJE ny kohortstart — T0 ligger 5 h före NOW och måste också rymmas.
# Klockan ligger i den AKTIVA radarkohortens fönster. Flyttas gränsen
# (ny signalversion) måste den här följa med, annars blir fixturens
# captures `transitional` och tillhör per definition ingen kohort.
NOW = dt.datetime(2026, 9, 3, 5, 0, tzinfo=dt.timezone.utc)
T0 = NOW - dt.timedelta(hours=5)     # stängd serie: sista capture > 3 h gammal
HISTORICAL_NOW = dt.datetime(2026, 8, 4, 12, 0, tzinfo=dt.timezone.utc)


def iso(when: dt.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def sofa_capture(event_id, at, minute, home_score=0, away_score=0,
                 status="2nd half", **fields):
    row = {
        "event_id": event_id, "captured_at": iso(at),
        "capture_version": live_radar.CAPTURE_VERSION,
        "league": "eliteserien", "tournament": "Eliteserien",
        "home": "Home", "away": "Away", "start_at": None,
        "status": status, "minute": minute,
        "home_score": home_score, "away_score": away_score,
    }
    row.update(fields)
    return row


def fotmob_capture(fotmob_id, at, minute, home_score=0, away_score=0,
                   xg=(1.8, 0.2)):
    return {
        "fotmob_id": fotmob_id, "captured_at": iso(at),
        "capture_version": fotmob.CAPTURE_VERSION,
        "league": "eliteserien", "tournament": "Eliteserien",
        "home": "Home", "away": "Away", "start_at": None,
        "minute": minute, "home_score": home_score, "away_score": away_score,
        "xg_home": xg[0], "xg_away": xg[1],
    }


def flashscore_capture(flashscore_id, at, minute, home_score=0, away_score=0,
                       xg=(1.8, 0.2)):
    return {
        "flashscore_id": flashscore_id, "captured_at": iso(at),
        "capture_version": flashscore.CAPTURE_VERSION,
        "league": "eliteserien", "tournament": "Eliteserien",
        "home": "Home", "away": "Away", "start_at": None,
        "minute": minute, "home_score": home_score, "away_score": away_score,
        "xg_home": xg[0], "xg_away": xg[1],
    }


class RadarSettlementTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self._tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def rows(self):
        return self.store.live_settlement_rows()

    # (a) mål inom 15 minuter SPELTID ⇒ utfall A = 1
    def test_goal_within_play_window_settles_outcome_a_as_one(self):
        self.store.oddset_save_live_capture(sofa_capture(1, T0, 30))
        self.store.oddset_save_live_capture(
            sofa_capture(1, T0 + dt.timedelta(minutes=10), 40, home_score=1))

        report = live_settlement.settle_moments(self.store, now=NOW)

        self.assertEqual(2, report["settled"])
        moment = self.rows()[0]
        self.assertEqual(1, moment["outcome_15min"])
        self.assertIsNone(moment["censored_15min"])
        self.assertEqual(1, moment["outcome_more_before_ft"])
        self.assertEqual(0, moment["score_diff"])

    # (b) inga täckande captures ⇒ CENSORERAT — aldrig gissat som nej
    def test_uncovered_window_is_censored_never_zero(self):
        # helt utan senare captures
        self.store.oddset_save_live_capture(sofa_capture(2, T0, 30))
        # mål SYNS först efter fönstret — tidpunkten är tvetydig
        self.store.oddset_save_live_capture(sofa_capture(3, T0, 30))
        self.store.oddset_save_live_capture(
            sofa_capture(3, T0 + dt.timedelta(minutes=22), 52, home_score=1))

        live_settlement.settle_moments(self.store, now=NOW)

        ensam = next(r for r in self.rows() if r["event_id"] == "2")
        self.assertIsNone(ensam["outcome_15min"])
        self.assertEqual("window_not_covered", ensam["censored_15min"])
        self.assertIsNone(ensam["outcome_more_before_ft"])
        self.assertEqual("no_final_capture", ensam["censored_ft"])

        tvetydig = next(r for r in self.rows()
                        if r["event_id"] == "3" and r["minute"] == 30)
        self.assertIsNone(tvetydig["outcome_15min"], "gap över fönstergränsen "
                          "får inte tolkas som nej — och inte som ja")
        self.assertEqual("window_not_covered", tvetydig["censored_15min"])
        # men målet FÖRE full tid är bevisat observerat
        self.assertEqual(1, tvetydig["outcome_more_before_ft"])

    # (c) utfall B: ytterligare mål ⇒ 1; oavgjort slut utan fler mål ⇒ 0
    def test_more_goals_before_ft_and_final_draw(self):
        self.store.oddset_save_live_capture(
            sofa_capture(4, T0, 60, home_score=1, away_score=1))
        self.store.oddset_save_live_capture(
            sofa_capture(4, T0 + dt.timedelta(minutes=12), 72,
                         home_score=2, away_score=1))
        self.store.oddset_save_live_capture(
            sofa_capture(5, T0, 70, home_score=1, away_score=1))
        self.store.oddset_save_live_capture(
            sofa_capture(5, T0 + dt.timedelta(minutes=25), 90,
                         home_score=1, away_score=1, status="Ended"))

        live_settlement.settle_moments(self.store, now=NOW)

        med_mal = next(r for r in self.rows()
                       if r["event_id"] == "4" and r["minute"] == 60)
        self.assertEqual(1, med_mal["outcome_more_before_ft"])

        oavgjord = next(r for r in self.rows()
                        if r["event_id"] == "5" and r["minute"] == 70)
        self.assertEqual(0, oavgjord["outcome_more_before_ft"],
                         "slutstatus-capture med samma total bevisar 0")
        self.assertEqual(0, oavgjord["outcome_15min"])

    # (d) idempotens: två körningar ⇒ inga dubbletter, ingen omskrivning
    def test_settlement_is_append_once(self):
        self.store.oddset_save_live_capture(sofa_capture(6, T0, 30))
        self.store.oddset_save_live_capture(
            sofa_capture(6, T0 + dt.timedelta(minutes=10), 40, home_score=1))

        first = live_settlement.settle_moments(self.store, now=NOW)
        before = self.rows()
        second = live_settlement.settle_moments(
            self.store, now=NOW + dt.timedelta(hours=1))

        self.assertEqual(2, first["settled"])
        self.assertEqual(0, second["settled"])
        self.assertEqual(before, self.rows(),
                         "settlade rader får aldrig skrivas om")

    def test_alphanumeric_flashscore_id_is_idempotent_on_second_run(self):
        event_id = "SKg88Q3T"
        self.store.live_flashscore_save(
            flashscore_capture(event_id, T0, 30))
        self.store.live_flashscore_save(flashscore_capture(
            event_id, T0 + dt.timedelta(minutes=10), 40, home_score=1))

        first = live_settlement.settle_moments(self.store, now=NOW)
        second = live_settlement.settle_moments(
            self.store, now=NOW + dt.timedelta(hours=1))

        self.assertEqual(2, first["settled"])
        self.assertEqual(0, second["settled"])
        self.assertEqual({event_id}, {row["event_id"] for row in self.rows()
                                     if row["provider"] == "flashscore"})

    def test_pending_previous_capture_version_is_not_abandoned(self):
        event_id = "old-v1-event"
        first_at = dt.datetime(2026, 8, 1, 18, 0, tzinfo=dt.timezone.utc)
        first = flashscore_capture(event_id, first_at, 30)
        later = flashscore_capture(
            event_id, first_at + dt.timedelta(minutes=10), 40, home_score=1)
        first["capture_version"] = "flashscore-live-v1"
        later["capture_version"] = "flashscore-live-v1"
        # Historisk capture producerad av v3-koden. Versionen bärs av raden;
        # utan den skulle dagens skrivare stämpla v5, och en v5-rad i v3:s
        # deklarerade fönster är per definition `transitional`.
        first["radar_version"] = live_radar.RADAR_V3_VERSION
        later["radar_version"] = live_radar.RADAR_V3_VERSION
        self.store.live_flashscore_save(first)
        self.store.live_flashscore_save(later)

        report = live_settlement.settle_moments(
            self.store, now=HISTORICAL_NOW)

        self.assertEqual(2, report["settled"])
        rows = [row for row in self.rows() if row["event_id"] == event_id]
        self.assertEqual({"flashscore-live-v1"},
                         {row["capture_version"] for row in rows})
        self.assertEqual({"chance-gap-shadow-v3"},
                         {row["signal_version"] for row in rows})

    def test_cohort_needs_both_the_right_code_and_the_declared_window(self):
        """Två villkor, inte ett — annars glider kohorterna isär.

        Den gamla regeln prövade bara det deklarerade fönstret. Då hamnade
        2 168 v5-producerade ögonblick (57 % av v4-kohorten) under v4, eftersom
        v5-gränsen råkade sättas 16 h efter att koden faktiskt bytte.
        """
        cases = (
            # (event, capturetid, kod som producerade, förväntad kohort)
            ("match", dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc),
             live_radar.RADAR_V3_VERSION, "chance-gap-shadow-v3"),
            ("nyare-kod", dt.datetime(2026, 8, 2, 15, 0,
                                      tzinfo=dt.timezone.utc),
             live_radar.RADAR_V5_VERSION, live_radar.RADAR_TRANSITIONAL),
            ("aldre-kod", dt.datetime(2026, 8, 1, 9, 0,
                                      tzinfo=dt.timezone.utc),
             live_radar.RADAR_V2_VERSION, live_radar.RADAR_TRANSITIONAL),
            ("ren-v5", dt.datetime(2026, 8, 3, 6, 1, tzinfo=dt.timezone.utc),
             live_radar.RADAR_V5_VERSION, "chance-gap-shadow-v5"),
        )
        for event_id, captured_at, produced_by, _ in cases:
            self.store.oddset_save_live_capture(
                sofa_capture(event_id, captured_at, 30, xg_home=0.3,
                             xg_away=0.2, radar_version=produced_by))

        live_settlement.settle_moments(self.store, now=HISTORICAL_NOW)

        versions = {row["event_id"]: row["signal_version"]
                    for row in self.rows()}
        for event_id, _, _, expected in cases:
            self.assertEqual(expected, versions[event_id], event_id)

    def test_historical_row_without_version_uses_observed_switches(self):
        """Rader från före kolumnen infördes har NULL och måste härledas.

        Journalens observerade växlingar är beviset. Inne i en växling vet vi
        inte vilken kod som körde — då är raden transitional, aldrig gissad.
        """
        inside_switch = dt.datetime(2026, 8, 1, 11, 40, tzinfo=dt.timezone.utc)
        clearly_v3 = dt.datetime(2026, 8, 1, 12, 0, tzinfo=dt.timezone.utc)
        for event_id, at in (("i-vaxling", inside_switch),
                             ("efter-vaxling", clearly_v3)):
            self.store.oddset_save_live_capture(
                sofa_capture(event_id, at, 30, xg_home=0.3, xg_away=0.2))
        # Historik: kolumnen fanns inte när raderna skrevs.
        self.store.conn.execute(
            "UPDATE oddset_live_capture SET radar_version=NULL")
        self.store.conn.commit()

        live_settlement.settle_moments(self.store, now=HISTORICAL_NOW)

        versions = {row["event_id"]: row["signal_version"]
                    for row in self.rows()}
        self.assertEqual(live_radar.RADAR_TRANSITIONAL, versions["i-vaxling"])
        self.assertEqual("chance-gap-shadow-v3", versions["efter-vaxling"])

    # (e) signalen räknas om med den DELADE funktionen — ingen egen kopia
    def test_signal_recomputation_uses_shared_radar_signal(self):
        self.store.oddset_save_live_capture(
            sofa_capture(7, T0, 30, xg_home=1.5, xg_away=0.2))

        with patch.object(live_radar, "radar_signal",
                          return_value={"level": "strong",
                                        "kind": "xg"}) as shared:
            live_settlement.settle_moments(self.store, now=NOW)

        self.assertTrue(shared.called)
        row = self.rows()[0]
        self.assertEqual(1, row["signal"], "signalen ska komma ur exakt den "
                         "funktion payloaden använder")
        self.assertEqual("xg", row["signal_type"])
        self.assertEqual(live_radar.RADAR_VERSION, row["signal_version"])

    def test_recomputed_signal_matches_frozen_policy_without_mock(self):
        self.store.oddset_save_live_capture(
            sofa_capture(8, T0, 30, xg_home=1.5, xg_away=0.2))

        live_settlement.settle_moments(self.store, now=NOW)

        row = self.rows()[0]
        self.assertEqual(1, row["signal"])          # 1.5 xG mot 0 mål = strong
        self.assertEqual("xg", row["signal_type"])

    # (f) xG-källor blandas ALDRIG: sofa settlas mot sofa, fotmob mot fotmob
    def test_providers_are_never_mixed(self):
        # Sofascore: proxysignal, en enda capture — inget facit kan hämtas
        self.store.oddset_save_live_capture(
            sofa_capture(9, T0, 60, big_chances_home=4, shots_on_home=9,
                         shots_inside_home=14, touches_box_home=37,
                         big_chances_away=0, shots_on_away=1,
                         shots_inside_away=1, touches_box_away=2))
        # FotMob: SAMMA match (samma lag/liga) har xG och ett mål i fönstret
        self.store.live_fotmob_save(fotmob_capture(9001, T0, 60))
        self.store.live_fotmob_save(
            fotmob_capture(9001, T0 + dt.timedelta(minutes=10), 70,
                           home_score=1, xg=(1.9, 0.2)))

        live_settlement.settle_moments(self.store, now=NOW)

        sofa_row = next(r for r in self.rows()
                        if r["provider"] == "sofascore")
        self.assertEqual("proxy", sofa_row["signal_type"],
                         "sofa-signalen får inte lyftas av FotMobs xG")
        self.assertIsNone(sofa_row["outcome_15min"],
                          "sofa-ögonblicket får inte settlas mot "
                          "FotMob-seriens mål")
        self.assertEqual("window_not_covered", sofa_row["censored_15min"])

        fm_row = next(r for r in self.rows()
                      if r["provider"] == "fotmob" and r["minute"] == 60)
        self.assertEqual("xg", fm_row["signal_type"])
        self.assertEqual(1, fm_row["signal"])
        self.assertEqual(1, fm_row["outcome_15min"])

    # öppna serier settlas inte alls — ingen rad kan behöva skrivas om
    def test_open_series_waits(self):
        self.store.oddset_save_live_capture(
            sofa_capture(10, NOW - dt.timedelta(minutes=30), 30))

        report = live_settlement.settle_moments(self.store, now=NOW)

        self.assertEqual(0, report["settled"])
        self.assertEqual(1, report["open_series"])
        self.assertEqual([], self.rows())

    # facit: träffandel mot villkorad basrate ur icke-signal-ögonblicken
    def test_facit_compares_against_conditioned_base_rate(self):
        # signalögonblick (xg, strong): mål i fönstret ⇒ utfall A = 1
        self.store.oddset_save_live_capture(
            sofa_capture(11, T0, 30, xg_home=1.5, xg_away=0.2))
        self.store.oddset_save_live_capture(
            sofa_capture(11, T0 + dt.timedelta(minutes=12), 42, home_score=1,
                         xg_home=1.6, xg_away=0.2))
        # kontroller i SAMMA cell (eliteserien × 30–45 × ställning 0),
        # xG-täckta men utan signal: ett ja och ett nej ⇒ basrate 0,5
        self.store.oddset_save_live_capture(
            sofa_capture(12, T0, 30, xg_home=0.3, xg_away=0.2))
        self.store.oddset_save_live_capture(
            sofa_capture(12, T0 + dt.timedelta(minutes=14), 44, home_score=1,
                         xg_home=0.4, xg_away=0.2))
        self.store.oddset_save_live_capture(
            sofa_capture(13, T0, 30, xg_home=0.3, xg_away=0.2))
        self.store.oddset_save_live_capture(
            sofa_capture(13, T0 + dt.timedelta(minutes=17), 47,
                         xg_home=0.4, xg_away=0.2))

        live_settlement.settle_moments(self.store, now=NOW)
        report = live_settlement.facit(self.store)

        self.assertEqual("shadow", report["mode"])
        self.assertEqual("raw_provider", report["moment_basis"])
        self.assertIn("signaljournalen", report["moment_basis_description"])
        group = report["groups"]["xg"]
        self.assertEqual(1, group["n_signal_moments"])
        outcome = group["outcomes"]["outcome_15min"]
        self.assertEqual(1, outcome["n_resolved"])
        self.assertEqual(1.0, outcome["rate"])
        self.assertEqual(0.5, outcome["base_rate"])
        self.assertEqual(2, outcome["control_resolved"])
        self.assertIn("mode=shadow", live_settlement.format_facit(report))

    def test_facit_never_mixes_signal_versions(self):
        common = {
            "provider": "sofascore", "captured_at": iso(T0),
            "capture_version": live_radar.CAPTURE_VERSION,
            "league": "eliteserien", "minute": 30, "score_diff": 0,
            "signal": 1, "signal_type": "xg", "outcome_15min": 1,
            "outcome_more_before_ft": 1, "settled_at": iso(NOW),
        }
        self.store.live_settlement_save({
            **common, "event_id": "current",
            "signal_version": live_radar.RADAR_VERSION,
        })
        self.store.live_settlement_save({
            **common, "event_id": "legacy",
            "signal_version": "chance-gap-shadow-v2",
        })

        report = live_settlement.facit(self.store)

        self.assertEqual(1, report["n_moments"])
        self.assertEqual(2, report["all_versions_n_moments"])
        self.assertEqual(1, report["groups"]["xg"]["n_signal_moments"])
        self.assertEqual(1, len(report["historical_versions"]))
        legacy = report["historical_versions"][0]
        self.assertEqual("chance-gap-shadow-v2", legacy["signal_version"])
        self.assertEqual(1, legacy["n_moments"])


class RadarSettlementMigrationTests(unittest.TestCase):
    def test_migration_is_additive_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE legacy(id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO legacy VALUES(1)")
            conn.commit()
            conn.close()

            first = migrera_radar_settlement.migrate(db)
            second = migrera_radar_settlement.migrate(db)

            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertEqual("ok", second["integrity"])
            self.assertEqual(15, len(second["columns"]))
            self.assertEqual(0, second["count"])
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(1, conn.execute(
                    "SELECT COUNT(*) FROM legacy").fetchone()[0])
            finally:
                conn.close()

    def test_event_id_text_migration_preserves_rows_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy-integer.db"
            conn = sqlite3.connect(db)
            conn.execute("""
                CREATE TABLE oddset_live_moment_settlement (
                    provider TEXT NOT NULL,
                    event_id INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    capture_version TEXT NOT NULL,
                    league TEXT,
                    minute INTEGER,
                    score_diff INTEGER,
                    signal INTEGER NOT NULL,
                    signal_type TEXT,
                    signal_version TEXT NOT NULL,
                    outcome_15min INTEGER,
                    outcome_more_before_ft INTEGER,
                    censored_15min TEXT,
                    censored_ft TEXT,
                    settled_at TEXT NOT NULL,
                    PRIMARY KEY(provider,event_id,captured_at,capture_version)
                )
            """)
            conn.execute(
                "INSERT INTO oddset_live_moment_settlement "
                "(provider,event_id,captured_at,capture_version,signal,"
                "signal_version,settled_at) VALUES(?,?,?,?,?,?,?)",
                ("flashscore", "SKg88Q3T", iso(T0), "fs-v1", 1,
                 "chance-gap-shadow-v3", iso(NOW)))
            conn.commit()
            conn.close()

            first = migrera_radar_event_id_text.migrate(db)
            second = migrera_radar_event_id_text.migrate(db)

            self.assertTrue(first["rebuilt"])
            self.assertFalse(second["rebuilt"])
            self.assertEqual("TEXT", second["columns"]["event_id"])
            self.assertEqual(1, second["count"])
            self.assertEqual("ok", second["integrity"])
            self.assertEqual(0, second["foreign_key_errors"])
            conn = sqlite3.connect(db)
            try:
                self.assertEqual("SKg88Q3T", conn.execute(
                    "SELECT event_id FROM oddset_live_moment_settlement"
                ).fetchone()[0])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()


class CohortBoundaryTests(unittest.TestCase):
    """Kohortregeln mot det verkliga glappet 2026-08-02/03.

    `RADAR_*_STARTED_AT` är handskrivna avsikter; journalen daterar när koden
    verkligen bytte. Glider de isär ska rader bli `transitional` — aldrig
    tyst hamna i föregående kohort.
    """

    def test_declared_start_after_the_real_switch_yields_transitional(self):
        # v5-koden körde från ~2026-08-02T14:07Z men v5 deklarerades först
        # 2026-08-03T06:00Z. 16 timmar däremellan ägs av ingen kohort.
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-02T15:14:08Z",
                                  produced_by=live_radar.RADAR_V5_VERSION))
        self.assertEqual(
            "chance-gap-shadow-v5",
            live_radar.cohort_for("2026-08-03T15:12:16Z",
                                  produced_by=live_radar.RADAR_V5_VERSION))

    def test_v8_scope_start_is_a_clean_boundary(self):
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-09T17:14:59Z",
                                  produced_by=live_radar.RADAR_V8_VERSION))
        self.assertEqual(
            live_radar.RADAR_V8_VERSION,
            live_radar.cohort_for("2026-08-09T17:15:00Z",
                                  produced_by=live_radar.RADAR_V8_VERSION))
        # Även fallbacken för eventuella historiska rader utan eget
        # radar_version känner den observerade växlingen.
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-09T17:00:00Z"))
        self.assertEqual(
            live_radar.RADAR_V8_VERSION,
            live_radar.cohort_for("2026-08-09T17:15:00Z"))

    def test_v9_bolivia_scope_start_is_a_clean_boundary(self):
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-09T17:59:59Z",
                                  produced_by=live_radar.RADAR_V9_VERSION))
        self.assertEqual(
            live_radar.RADAR_V9_VERSION,
            live_radar.cohort_for("2026-08-09T18:00:00Z",
                                  produced_by=live_radar.RADAR_V9_VERSION))
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-09T17:24:30Z"))
        self.assertEqual(
            live_radar.RADAR_V9_VERSION,
            live_radar.cohort_for("2026-08-09T18:00:00Z"))

    def test_v10_best_live_price_start_is_a_clean_boundary(self):
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-17T23:59:59Z",
                                  produced_by=live_radar.RADAR_V10_VERSION))
        self.assertEqual(
            live_radar.RADAR_V10_VERSION,
            live_radar.cohort_for("2026-08-18T00:00:00Z",
                                  produced_by=live_radar.RADAR_V10_VERSION))

    def test_v12_championship_scope_start_is_a_clean_boundary(self):
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-09-02T21:59:59Z",
                                  produced_by=live_radar.RADAR_V12_VERSION))
        self.assertEqual(
            live_radar.RADAR_V12_VERSION,
            live_radar.cohort_for("2026-09-02T22:00:00Z",
                                  produced_by=live_radar.RADAR_V12_VERSION))

    def test_declared_start_before_the_real_switch_yields_transitional(self):
        # v3 deklarerades 08:00Z men koden bytte först ~11:32–11:47Z.
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-01T09:00:00Z"))
        self.assertEqual(
            "chance-gap-shadow-v3",
            live_radar.cohort_for("2026-08-01T12:00:00Z"))

    def test_inside_an_observed_switch_is_never_guessed(self):
        self.assertIsNone(live_radar.produced_by_at("2026-08-01T11:40:00Z"))
        self.assertEqual(
            live_radar.RADAR_TRANSITIONAL,
            live_radar.cohort_for("2026-08-01T11:40:00Z"))

    def test_before_the_evidence_horizon_keeps_its_declared_label(self):
        """Journalen fanns inte — en påhittad transitional vore inte ärligare.

        Känd, dokumenterad begränsning: v1→v2-växlingen går inte att validera.
        """
        self.assertIsNone(live_radar.produced_by_at("2026-07-25T08:03:38Z"))
        self.assertEqual("chance-gap-shadow-v2",
                         live_radar.cohort_for("2026-07-25T08:03:38Z"))

    def test_a_row_never_falls_into_the_previous_cohort(self):
        """Kontamineringsspärren: fel kohort ⇒ transitional, aldrig vN−1."""
        for at in ("2026-08-01T09:00:00Z", "2026-08-02T15:14:08Z",
                   "2026-08-02T23:00:00Z"):
            cohort = live_radar.cohort_for(
                at, produced_by=live_radar.declared_version_at(at) + "-fel")
            self.assertEqual(live_radar.RADAR_TRANSITIONAL, cohort, at)
