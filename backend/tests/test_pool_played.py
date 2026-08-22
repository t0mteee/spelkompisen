import itertools
import datetime as dt
import json
import random
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

from app import altenar, kambi, pinnacle, pool_played
from app.storage import Storage


def _event(home, away, status_id=31, cancelled=False, number=1):
    """Ett drawEvent i SvS-form: result[Current] + statusId 31 = Slut."""
    return {
        "eventNumber": number, "cancelled": cancelled,
        "match": {
            "statusId": status_id,
            "status": "Slut" if status_id == 31 else "Pågår",
            "sportEventStatus": "Ended" if status_id == 31 else "Live",
            "result": [
                {"sportEventResultType": "Current", "home": home, "away": away},
                {"sportEventResultType": "Halftime", "home": "0", "away": "0"},
            ],
        },
    }


def _seed_facit(store, product, draw_number, outcomes):
    """Officiellt facit i settlementlagret: {eventNumber: '1'|'X'|'2'|None}."""
    for number, outcome in outcomes.items():
        store.conn.execute(
            "INSERT INTO pool_event_settlement (product, draw_number, "
            "event_number, outcome, cancelled) VALUES (?,?,?,?,?)",
            (product, draw_number, number, outcome, int(outcome is None)))
    store.conn.commit()


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _kupong(self, rows=("111", "11X", "1X1")):
        return pool_played.record(self.store, {
            "product": "topptipset", "draw_number": 4300, "row_price": 1.0,
            "rows": list(rows), "build_kind": "värderader", "strategy": "medel",
            "value_weight": 0.5, "budget": 3.0})

    def test_bokfor_och_idempotens(self):
        first = self._kupong()
        self.assertEqual(3, first["n_rows"])
        self.assertEqual(3.0, first["cost_kr"])
        self._kupong()          # samma rader igen
        self.assertEqual(1, len(pool_played.all_coupons(self.store)))

    def test_historiken_bar_omgangens_datum_fore_settlement(self):
        close = "2026-08-09T21:29:00+02:00"
        self.store.conn.execute(
            "INSERT INTO draws (product, draw_number, state, reg_close_time) "
            "VALUES ('topptipset', 4300, 'Open', ?)", (close,))
        self.store.conn.commit()
        self._kupong()
        row = pool_played.all_coupons(self.store)[0]
        self.assertEqual(close, row["draw_close"])

    def test_rader_kan_skickas_som_listor_eller_strangar(self):
        a = pool_played.normalize_rows([["1", "X", "2"], "1x2", "1,X,2"])
        self.assertEqual(["1X2", "1X2", "1X2"], a)

    def test_olika_radlangd_avvisas(self):
        with self.assertRaisesRegex(ValueError, "olika antal"):
            pool_played.record(self.store, {
                "product": "topptipset", "draw_number": 4301,
                "row_price": 1.0, "rows": ["111", "11"]})

    def test_glomma_bort_fungerar_bara_innan_settlement(self):
        kupong = self._kupong()
        self.store.conn.execute(
            "UPDATE pool_played_coupon SET settled_at='2026-07-25T00:00:00Z' "
            "WHERE id=?", (kupong["id"],))
        self.store.conn.commit()
        self.assertFalse(pool_played.forget(self.store, kupong["id"]))


class LiveStatusTests(unittest.TestCase):
    """Livestatus för reducerade system — kärnan i Samans andra önskan."""

    def test_pagaende_match_halls_oppen_for_alla_tecken(self):
        # match 1 klar (1-0 ⇒ '1'), match 2 pågår 0-0, match 3 klar (0-1 ⇒ '2')
        states = [pool_played.event_state(_event("1", "0", number=1)),
                  pool_played.event_state(_event("0", "0", status_id=6, number=2)),
                  pool_played.event_state(_event("0", "1", number=3))]
        self.assertEqual(("1", True), (states[0]["sign"], states[0]["final"]))
        self.assertEqual(("X", False), (states[1]["sign"], states[1]["final"]))

        coupon = {"rows_text": "1X2\n112\n221", "cost_kr": 3.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(3, status["n_events"])
        self.assertEqual(2, status["n_decided"])
        self.assertFalse(status["all_decided"])
        # Raderna "1X2" och "112" har båda match 1 och 3 rätt ⇒ 2 säkra, och
        # match 2 är oavgjord så BÅDA kan nå 3 rätt — poängen med livestatus är
        # just att en oavgjord match håller alla tecken öppna. "221" har missat
        # två och kan bara nå 1.
        self.assertEqual(2, status["best_secure"])
        self.assertEqual(2, status["alive_per_level"][3])
        self.assertEqual(3, status["alive_per_level"][1])

    def test_tecken_paras_pa_eventnummer_inte_payloadordning(self):
        # Granskningsfix F4: payloaden kommer i omvänd ordning. Kolumn 1 = match
        # 1 ('1' efter 1-0), kolumn 2 = match 2 ('2' efter 0-1). Positionsvis
        # zip hade gett 0 säkra; eventNumber-join ger 2.
        states = [pool_played.event_state(_event("0", "1", number=2)),
                  pool_played.event_state(_event("1", "0", number=1))]
        coupon = {"rows_text": "12",
                  "events_order": json.dumps([1, 2]), "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(2, status["best_secure"])
        self.assertTrue(status["all_decided"])

    def test_saknad_match_trunkeras_inte_tyst(self):
        # Granskningsfix F4: payloaden har färre event än kupongen har kolumner.
        # Kolumnen utan match är oavgjord — omgången får ALDRIG bli all_decided.
        states = [pool_played.event_state(_event("1", "0", number=1))]
        coupon = {"rows_text": "11", "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(2, status["n_events"])
        self.assertFalse(status["all_decided"])
        self.assertEqual(1, status["best_secure"])
        self.assertEqual(1, status["alive_per_level"][2])   # kan ännu bli 2 rätt

    def test_struken_match_ar_oavgjord_i_livevyn(self):
        # Granskningsfix F4: SvS FASTSTÄLLER tecknet för en struken match i
        # settlementet — livevyn får inte räkna den som rätt för alla rader.
        states = [pool_played.event_state(
                      _event(None, None, cancelled=True, number=1)),
                  pool_played.event_state(_event("1", "0", number=2))]
        coupon = {"rows_text": "21", "cost_kr": 1.0}
        status = pool_played.live_status(coupon, states)
        self.assertEqual(1, status["best_secure"])
        self.assertFalse(status["all_decided"])
        self.assertEqual(1, status["alive_per_level"][2])

    def test_obelagt_forlangningstecken_presenteras_som_oppet_spann(self):
        provisional = {
            "event_number": 1, "description": "A – B", "final": True,
            "cancelled": False, "sign": "1", "sign_provisional": True,
            "extra_time": True,
            "probs": {"1": .99, "X": .005, "2": .005},
        }
        final = {"event_number": 2, "final": True, "cancelled": False,
                 "sign": "1"}
        coupon = {"rows_text": "11\nX1\n21", "cost_kr": 3.0}

        status = pool_played.live_status(coupon, [provisional, final])

        self.assertEqual(1, status["n_decided"])
        self.assertFalse(status["all_decided"])
        self.assertEqual(3, status["alive_per_level"][2])
        self.assertNotIn("chance_per_level", status)
        self.assertEqual(["A – B"], status["chance_unpriced"])

        provisional["sign_provisional"] = False
        proven = pool_played.live_status(coupon, [provisional, final])
        self.assertEqual(2, proven["n_decided"])
        self.assertTrue(proven["all_decided"])
        self.assertEqual(1, proven["alive_per_level"][2])


class AliveRowsTests(unittest.TestCase):
    """VILKA rader som lever — aggregatet ensamt går inte att agera på."""

    def _tretton(self, decided_signs, rows):
        """13 matcher där de tre sista är oavgjorda."""
        states = []
        for i, sign in enumerate(decided_signs, start=1):
            score = {"1": ("1", "0"), "X": ("1", "1"), "2": ("0", "1")}[sign]
            states.append(pool_played.event_state(_event(*score, number=i)))
        for i in range(len(decided_signs) + 1, 14):
            states.append(pool_played.event_state(
                _event("0", "0", status_id=6, number=i)))
        return {"rows_text": "\n".join(rows), "cost_kr": float(len(rows))}, states

    def test_visar_radnummer_sakra_ratt_och_vad_raden_behover(self):
        facit = "1111111111"                      # matcherna 1–10 slutade 1
        rader = ["1111111111" + "1X2",            # 10 säkra, kan nå 13
                 "1111111111" + "XX1",            # 10 säkra, kan nå 13
                 "111111111X" + "122",            # 9 säkra, kan nå 12
                 "11111111XX" + "222"]            # 8 säkra, kan nå 11
        coupon, states = self._tretton(facit, rader)

        live = pool_played.live_status(coupon, states, include_chance=False)

        self.assertEqual(2, live["alive_per_level"][13])
        self.assertEqual(3, live["alive_per_level"][12])
        # Samma tal som förut — men nu går de att peka ut.
        self.assertEqual([11, 12, 13], live["alive_rows_open_cols"])
        self.assertEqual(4, live["alive_rows_total"])
        rows = live["alive_rows"]
        self.assertEqual([1, 2, 3, 4], [r["n"] for r in rows])   # säkra fallande
        self.assertEqual([10, 10, 9, 8], [r["secure"] for r in rows])
        self.assertEqual([13, 13, 12, 11], [r["possible"] for r in rows])
        self.assertEqual([{"col": 11, "sign": "1"},
                          {"col": 12, "sign": "X"},
                          {"col": 13, "sign": "2"}], rows[0]["open"])
        self.assertEqual("XX1", "".join(o["sign"] for o in rows[1]["open"]))

    def test_dod_rad_listas_inte(self):
        # Golvnivån på ett 13-matchsspel är 10 rätt. En rad med 6 säkra och
        # 3 öppna kan som mest nå 9 och ska alltså inte stå i listan.
        facit = "1111111111"
        rader = ["1111111111" + "111",            # lever
                 "1111112222" + "111"]            # 6 säkra ⇒ max 9
        coupon, states = self._tretton(facit, rader)

        live = pool_played.live_status(coupon, states, include_chance=False)

        self.assertEqual([1], [r["n"] for r in live["alive_rows"]])
        self.assertEqual(1, live["alive_rows_total"])

    def test_listan_kapas_men_totalen_ar_sann(self):
        facit = "1111111111"
        rader = ["1111111111" + a + b + c
                 for a in "1X2" for b in "1X2" for c in "1X2"]   # 27 rader
        coupon, states = self._tretton(facit, rader)

        live = pool_played.live_status(coupon, states, include_chance=False)
        self.assertEqual(27, live["alive_rows_total"])

        with unittest.mock.patch.object(pool_played, "ALIVE_ROWS_MAX", 5):
            kapad = pool_played.live_status(coupon, states, include_chance=False)
        self.assertEqual(5, len(kapad["alive_rows"]))
        self.assertEqual(27, kapad["alive_rows_total"])   # totalen ljuger inte

    def test_struken_och_obelagd_forlangning_visas_som_oppna_kolumner(self):
        # Båda är öppna enligt _decided, så raden ska redovisas med det tecken
        # den BEHÖVER — aldrig med ett tecken vi gissat åt Svenska Spel.
        struken = pool_played.event_state(
            _event(None, None, cancelled=True, number=1))
        provisorisk = {"event_number": 2, "final": True, "cancelled": False,
                       "sign": "1", "sign_provisional": True,
                       "extra_time": True}
        klar = pool_played.event_state(_event("1", "0", number=3))
        coupon = {"rows_text": "2X1\n111", "cost_kr": 2.0}

        live = pool_played.live_status(coupon, [struken, provisorisk, klar],
                                       include_chance=False)

        self.assertEqual([1, 2], live["alive_rows_open_cols"])
        self.assertEqual("2X", "".join(
            o["sign"] for o in live["alive_rows"][0]["open"]))
        self.assertTrue(all(r["secure"] == 1 for r in live["alive_rows"]))


class SettleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _spelad(self, rows=("111", "112", "121"), events_order=None):
        payload = {"product": "topptipset", "draw_number": 4302,
                   "row_price": 1.0, "rows": list(rows)}
        if events_order:
            payload["events_order"] = events_order
        return pool_played.record(self.store, payload)

    def test_utdelning_anvander_publicerat_belopp_utan_utspadning(self):
        """En spelad kupong ligger REDAN i potten — publicerat belopp per
        vinnare inkluderar oss. Utspädning hör till kontrafaktiska system."""
        kupong = self._spelad()
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong,
                                 tiers={3: (120, 500.0), 2: (3000, 20.0)})
        self.assertTrue(res["settled"])
        self.assertTrue(res["complete"])
        # en rad med 3 rätt (500) + två rader med 2 rätt (2 × 20) = 540
        self.assertEqual(540.0, res["payout_kr"])
        self.assertAlmostEqual((540.0 - 3.0) / 3.0, res["roi"], places=4)

    def test_utan_settlement_settlas_inget(self):
        kupong = self._spelad()
        res = pool_played.settle(self.store, kupong, tiers={3: (1, 1.0)})
        self.assertFalse(res["settled"])

    def test_facit_paras_pa_eventnummer_via_events_order(self):
        # Granskningsfix F4: kupongens kolumnordning [2, 1] mot facit 1:'1',
        # 2:'2'. Rad "21" = kolumn 1 → match 2 ('2' rätt), kolumn 2 → match 1
        # ('1' rätt) ⇒ 2 rätt. Positionsvis zip hade gett 0.
        kupong = self._spelad(rows=("21",), events_order=[2, 1])
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "2"})
        res = pool_played.settle(self.store, kupong, tiers={2: (10, 100.0)})
        self.assertTrue(res["complete"])
        self.assertEqual(2, res["correct_max"])
        self.assertEqual(100.0, res["payout_kr"])

    def test_kupongdetalj_visar_rader_matchnamn_och_officiellt_facit(self):
        kupong = self._spelad(rows=("21", "22"), events_order=[2, 1])
        for number, outcome, home, away in (
                (1, "1", "Hemma ett", "Borta ett"),
                (2, "2", "Hemma två", "Borta två")):
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, description, home, away, outcome, cancelled) "
                "VALUES (?,?,?,?,?,?,?,0)",
                ("topptipset", 4302, number, f"{home} – {away}",
                 home, away, outcome))
        self.store.conn.execute(
            "INSERT INTO pool_payout_tier (product, draw_number, tier_name, "
            "correct, winners, amount) VALUES (?,?,?,?,?,?)",
            ("topptipset", 4302, "2 rätt", 2, 10, 100.0))
        self.store.conn.commit()
        pool_played.settle(self.store, kupong, tiers={2: (10, 100.0)})

        detail = pool_played.coupon_detail(self.store, kupong["id"])

        self.assertEqual("21", detail["facit"])
        self.assertTrue(detail["facit_complete"])
        self.assertTrue(detail["audit_matches_stored"])
        self.assertEqual([2, 1], [event["event_number"]
                                 for event in detail["events"]])
        self.assertEqual("Hemma två", detail["events"][0]["home"])
        self.assertEqual({2: 1, 1: 1}, detail["correct_dist"])
        self.assertEqual(
            {"index": 1, "signs": "21", "correct": 2,
             "payout_kr": 100.0, "prize_level": True},
            detail["rows"][0])
        self.assertNotIn("rows_text", detail["coupon"])

    def test_kupongdetalj_for_okand_id_saknas(self):
        self.assertIsNone(pool_played.coupon_detail(self.store, 9999))

    def test_struken_match_med_faststallt_tecken_raknas_som_tecknet(self):
        # SvS fastställer tecknet för strukna matcher — det gäller, inte
        # "rätt för alla rader".
        kupong = self._spelad(rows=("11", "12"))
        for number, outcome, cancelled in ((1, "1", 0), (2, "2", 1)):
            self.store.conn.execute(
                "INSERT INTO pool_event_settlement (product, draw_number, "
                "event_number, outcome, cancelled) VALUES (?,?,?,?,?)",
                ("topptipset", 4302, number, outcome, cancelled))
        self.store.conn.commit()
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["complete"])
        # bara raden "12" träffar den strukna matchens fastställda tecken
        self.assertEqual({2: 1, 1: 1}, res["correct_dist"])
        self.assertEqual(50.0, res["payout_kr"])

    def test_struken_utan_utfall_blir_ofullstandig_aldrig_ratt_for_alla(self):
        kupong = self._spelad(rows=("11",))
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: None})
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["settled"])
        self.assertFalse(res["complete"])
        self.assertIsNone(res["payout_kr"])
        self.assertIn("utfall saknas", res["reason"])
        self.assertEqual(0, pool_played.summary(self.store)["n_settled"])

    def test_breddfel_settlar_aldrig_tyst(self):
        # Kupongen har 2 tecken/rad men omgången 3 matcher — permanent
        # bokföringsfel, markeras ofullständigt i stället för att trunkeras.
        kupong = self._spelad(rows=("11",))
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong, tiers={2: (1, 50.0)})
        self.assertTrue(res["settled"])
        self.assertFalse(res["complete"])
        self.assertIn("breddfel", res["reason"])

    def test_saknat_belopp_ger_ofullstandigt_facit_inte_noll(self):
        kupong = self._spelad()
        _seed_facit(self.store, "topptipset", 4302, {1: "1", 2: "1", 3: "1"})
        res = pool_played.settle(self.store, kupong,
                                 tiers={3: (0, None), 2: (3000, 20.0)})
        self.assertFalse(res["complete"])
        self.assertIsNone(res["payout_kr"])
        self.assertIsNone(res["roi"])
        # ROI-summeringen får inte räkna in den
        self.assertEqual(0, pool_played.summary(self.store)["n_settled"])


class ChancePerLevelTests(unittest.TestCase):
    """Raderna delar de kvarvarande matcherna, så utfallen är BEROENDE.
    En produkt av per-rad-sannolikheter hade gett fel svar."""

    def _states(self, *specs):
        out = []
        for i, spec in enumerate(specs, start=1):
            sign, final, probs = spec
            out.append({"event_number": i, "sign": sign, "final": final,
                        "cancelled": False, "probs": probs})
        return out

    def test_dependent_rows_are_scored_over_the_whole_outcome_space(self):
        states = self._states(
            ("1", True, None), ("X", True, None),
            (None, False, {"1": 0.6, "X": 0.25, "2": 0.15}),
            (None, False, {"1": 0.5, "X": 0.3, "2": 0.2}))
        coupon = {"rows_text": "1X11\n1X22", "events_order": "[1,2,3,4]"}

        live = pool_played.live_status(coupon, states)

        self.assertEqual("exakt", live["chance_basis"])
        # 4 rätt = rad A tar båda ELLER rad B tar båda: .6*.5 + .15*.2
        self.assertAlmostEqual(0.33, live["chance_per_level"][4], places=6)
        # ≥3 = allt utom att BÅDA raderna missar båda: 1 − (.25*.3)
        self.assertAlmostEqual(0.925, live["chance_per_level"][3], places=6)
        self.assertEqual(1.0, live["chance_per_level"][2])

    def test_missing_odds_gives_an_interval_not_a_guess(self):
        """En oprissatt match ska begränsa svaret, inte radera det.

        Tidigare returnerades ingenting alls så fort EN match saknade odds,
        och hela chanskolumnen slocknade. Nu betingas beräkningen på den
        matchens tre utfall och redovisas som ett intervall — inget påstående
        om hur den går, bara gränserna den kan ge.
        """
        states = self._states(
            ("1", True, None), (None, False, None))
        coupon = {"rows_text": "11\n12", "events_order": "[1,2]"}

        live = pool_played.live_status(coupon, states)

        # Ingen punktskattning får uppstå ur en okänd match.
        self.assertNotIn("chance_per_level", live)
        self.assertIn("chance_min_per_level", live)
        lo = live["chance_min_per_level"]
        hi = live["chance_max_per_level"]
        for level in lo:
            self.assertLessEqual(lo[level], hi[level])
        # Rad "11" har redan 1 rätt, "12" har 1 rätt: minst 1 oavsett utfall.
        self.assertEqual(1.0, lo[1])
        # Exakt en rad kan nå 2 rätt, och vilken beror på den okända matchen —
        # alltså säker på 2 oavsett utfall.
        self.assertEqual(1.0, hi[2])

    def test_finished_coupon_is_certainty_not_probability(self):
        states = self._states(("1", True, None), ("X", True, None))
        coupon = {"rows_text": "1X\n12", "events_order": "[1,2]"}

        live = pool_played.live_status(coupon, states)

        self.assertEqual("avgjord", live["chance_basis"])
        self.assertEqual(1.0, live["chance_per_level"][2])

    def test_snabb_livestatus_hoppar_bara_over_chansen(self):
        states = self._states(
            ("1", True, None),
            (None, False, {"1": 0.5, "X": 0.3, "2": 0.2}))
        coupon = {"rows_text": "11\n12", "events_order": "[1,2]"}

        live = pool_played.live_status(coupon, states, include_chance=False)

        self.assertEqual(1, live["n_decided"])
        self.assertEqual(2, live["alive_per_level"][2])
        self.assertIn("matches", live)
        self.assertIn("cheer", live)
        self.assertNotIn("chance_per_level", live)
        self.assertNotIn("chance_basis", live)

    def test_bitmask_simulering_ar_identisk_med_referensloopen(self):
        """Optimeringen ändrar varken slumpföljd eller radpoäng."""
        groups = {
            ("1", "X", "2", "1"): 2,
            ("2", "1", "X", "X"): 1,
            ("X", "X", "1", "2"): 3,
        }
        probs = [
            {"1": 0.5, "X": 0.3, "2": 0.2},
            {"1": 0.2, "X": 0.4, "2": 0.4},
            {"1": 0.6, "X": 0.25, "2": 0.15},
            {"1": 0.35, "X": 0.3, "2": 0.35},
        ]
        levels = [6, 5, 4]
        samples = 250
        reference = {level: 0.0 for level in levels}
        rng = random.Random(20260802)
        signs = ("1", "X", "2")
        for _ in range(samples):
            combo = tuple(rng.choices(
                signs, weights=[p["1"], p["X"], p["2"]])[0]
                for p in probs)
            best = max(
                secure + sum(1 for i, sign in enumerate(pattern)
                             if sign == combo[i])
                for pattern, secure in groups.items())
            for level in levels:
                if best >= level:
                    reference[level] += 1.0 / samples

        # Båda de exakta vägarna stängs av: uppräkningen av hela utfallsrummet
        # OCH klotunionen. Testet gäller simuleringens bitmask-optimering, som
        # finns kvar för de kupongsystem där ingen exakt väg ryms i budgeten.
        with patch.object(pool_played, "CHANCE_EXACT_MAX_COMBOS", 0), \
             patch.object(pool_played, "CHANCE_BALL_MAX_CANDIDATES", 0), \
             patch.object(pool_played, "CHANCE_SAMPLES", samples):
            actual, basis = pool_played._hit_probabilities(
                groups, probs, levels)

        self.assertEqual("simulerad", basis)
        self.assertEqual(reference, actual)

    def test_klotunionen_ar_exakt_lika_med_full_uppräkning(self) -> None:
        """Den exakta genvägen måste ge SAMMA svar som att räkna upp allt.

        Att nå nivån L betyder att utfallet ligger inom Hamming-avstånd
        `secure + k - L` från någon rad. Klotunionen räknar bara upp de
        avstånden i stället för hela 3^k, men svaret ska vara identiskt —
        annars är det en approximation som utger sig för att vara exakt.
        """
        rng = random.Random(20260822)
        signs = ("1", "X", "2")
        for _ in range(25):
            width = rng.randint(3, 6)
            probs = []
            for _ in range(width):
                raw = [rng.uniform(0.1, 0.8) for _ in signs]
                total = sum(raw)
                probs.append(dict(zip(signs, (v / total for v in raw))))
            items = list({
                tuple(rng.choice(signs) for _ in range(width)):
                    rng.randint(0, 2)
                for _ in range(rng.randint(1, 8))
            }.items())
            levels = sorted({rng.randint(width - 2, width + 1)
                             for _ in range(3)})

            full = {level: 0.0 for level in levels}
            for combo in itertools.product(signs, repeat=width):
                weight = 1.0
                for i, sign in enumerate(combo):
                    weight *= probs[i][sign]
                best = max(secure + width
                           - sum(1 for i in range(width)
                                 if pattern[i] != combo[i])
                           for pattern, secure in items)
                for level in levels:
                    if best >= level:
                        full[level] += weight

            ball = pool_played._ball_union_probabilities(items, probs, levels)
            self.assertIsNotNone(ball)
            for level in levels:
                self.assertAlmostEqual(full[level], ball[level], places=12)

    def test_liten_chans_redovisas_aldrig_som_noll(self) -> None:
        """0 % betyder omöjligt. En chans på 3e-07 är inte omöjlig.

        `round(x, 6)` skrev toppnivån som exakt 0.0 medan alla tretton matcher
        var oavgjorda, och UI:t visar `0%` just för exakt noll. Skillnaden mot
        `<0,1%` är hela skillnaden mellan "kan inte hända" och "osannolikt".
        """
        self.assertEqual(0.0, pool_played._round_chance(0.0))
        for tiny in (3e-07, 1.2e-06, 4.9e-05):
            self.assertEqual(tiny, pool_played._round_chance(tiny))
            self.assertGreater(pool_played._round_chance(tiny), 0.0)
        self.assertEqual(0.015325, pool_played._round_chance(0.0153248))

    def test_odds_are_devigged_and_streck_is_the_fallback(self):
        # Bok utan overround (1/odds summerar redan till 1) — då är k = 1 och
        # power-metoden ska lämna sannolikheterna orörda.
        fair = pool_played._event_probs(
            {"odds": {"one": "2,00", "x": "4,00", "two": "4,00"}})
        self.assertAlmostEqual(0.5, fair["1"], places=6)
        self.assertAlmostEqual(0.25, fair["X"], places=6)

        # Med overround ska den bort, och summan bli exakt 1.
        probs = pool_played._event_probs(
            {"odds": {"one": "1,80", "x": "3,60", "two": "3,60"}})
        self.assertAlmostEqual(1.0, sum(probs.values()), places=6)
        self.assertGreater(probs["1"], probs["X"])
        self.assertLess(probs["1"], 1 / 1.80, "overrounden ska dras bort")

        folk_event = {"svenskaFolket": {"one": "60", "x": "25", "two": "15"}}
        folk = pool_played._event_probs(folk_event)
        self.assertAlmostEqual(0.6, folk["1"], places=6)

        self.assertIsNone(pool_played._event_probs({}))


CATALOGUE = {"id": "1026062550", "home": "AIK", "away": "Örgryte IS"}


class LiveOddsForRunningMatchTests(unittest.TestCase):
    """SvS pooldata bär statiska prematch-odds hela omgången. AIK–Örgryte låg
    0–2 i halvtid med 1,55 på AIK (≈60 %) medan livepriset stod i 9,00 (≈8 %)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Storage(Path(self.tmp.name) / "test.db")
        self.store.conn.execute(
            "INSERT INTO oddset_matches(id, league, home, away, start, kambi_id)"
            " VALUES('svs:1','allsvenskan','AIK','Örgryte IS',"
            "'2026-08-02T14:30:00Z','1026062550')")
        self.store._commit()

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _state(self, **over):
        state = {"event_number": 1, "sign": "2", "final": False,
                 "cancelled": False, "in_progress": True,
                 "home": "AIK", "away": "Örgryte",
                 "start": "2026-08-02T16:30:00+02:00",
                 "probs": {"1": 0.60, "X": 0.25, "2": 0.15}}
        state.update(over)
        return state

    def test_running_match_is_repriced_from_the_live_market(self):
        state = self._state()
        with patch.object(kambi, "live_events", return_value=[CATALOGUE]), \
             patch.object(kambi, "live_1x2",
                          return_value={"1": 9.0, "X": 4.5, "2": 1.3}):
            pool_played.attach_live_odds(self.store, [state])
        self.assertEqual("live", state["probs_basis"])
        self.assertEqual("svenskaspel", state["probs_source"])
        self.assertLess(state["probs"]["1"], 0.15, "prematch-favoriten ska falla")
        self.assertGreater(state["probs"]["2"], 0.65)
        self.assertAlmostEqual(1.0, sum(state["probs"].values()), places=6)

    def test_samma_liveevent_prissatts_en_gang_for_flera_kuponger(self):
        states = [self._state(), self._state()]
        with patch.object(kambi, "live_events", return_value=[CATALOGUE]), \
             patch.object(kambi, "live_1x2",
                          return_value={"1": 9.0, "X": 4.5, "2": 1.3}) as price:
            pool_played.attach_live_odds(self.store, states)

        price.assert_called_once_with("1026062550")
        self.assertTrue(all(state["probs_basis"] == "live" for state in states))

    def test_missing_live_price_clears_instead_of_falling_back(self):
        state = self._state()
        with patch.object(kambi, "live_events", return_value=[CATALOGUE]), \
             patch.object(kambi, "live_1x2", return_value={}), \
             patch.object(altenar, "live_events", return_value=[]), \
             patch.object(pinnacle.Pinnacle, "soccer_live_totals",
                          return_value=[]):
            pool_played.attach_live_odds(self.store, [state])
        self.assertIsNone(state["probs"], "prematch får aldrig återanvändas")
        self.assertEqual("live_saknas", state["probs_basis"])

    def test_ninja_reprices_when_kambi_1x2_is_closed(self):
        state = self._state()
        ninja = {"id": "77", "home": "AIK", "away": "Örgryte IS",
                 "start": state["start"], "odds_status": "captured",
                 "odds": {"1": 9.0, "X": 4.5, "2": 1.3}}
        with patch.object(kambi, "live_events", return_value=[CATALOGUE]), \
             patch.object(kambi, "live_1x2", return_value={}), \
             patch.object(altenar, "live_events", return_value=[ninja]), \
             patch.object(pinnacle.Pinnacle, "soccer_live_totals",
                          side_effect=AssertionError("Ninja ska räcka")):
            pool_played.attach_live_odds(self.store, [state])

        self.assertEqual("live", state["probs_basis"])
        self.assertEqual("ninja", state["probs_source"])
        self.assertGreater(state["probs"]["2"], 0.65)

    def test_fresh_pinnacle_is_last_fallback_but_stale_is_rejected(self):
        event = {"id": "88", "home": "AIK", "away": "Örgryte IS",
                 "start": self._state()["start"], "matchup_ids": ["881"],
                 "age_s": 400, "odds_status": "captured",
                 "odds": {"1": 8.0, "X": 4.0, "2": 1.4}}
        for age, expected in ((12, "pinnacle"), (120, None)):
            state = self._state()
            with patch.object(kambi, "live_events", return_value=[]), \
                 patch.object(altenar, "live_events", return_value=[]), \
                 patch.object(pinnacle.Pinnacle, "soccer_live_totals",
                              return_value=[event]), \
                 patch.object(pinnacle.Pinnacle, "refresh_live_1x2",
                              return_value={"status": "captured", "age_s": age,
                                            "odds": event["odds"]}):
                pool_played.attach_live_odds(self.store, [state])
            self.assertEqual(expected, state.get("probs_source"))
            self.assertEqual("live" if expected else "live_saknas",
                             state["probs_basis"])

    def test_not_started_match_keeps_its_prematch_price(self):
        state = self._state(in_progress=False)
        with patch.object(kambi, "live_events",
                          side_effect=AssertionError("får inte anropas")), \
             patch.object(kambi, "live_1x2",
                          side_effect=AssertionError("får inte anropas")):
            pool_played.attach_live_odds(self.store, [state])
        self.assertEqual(0.60, state["probs"]["1"])

    def test_lookup_matches_on_normalised_names(self):
        catalogue = [{"id": "1026062550", "home": "AIK", "away": "Örgryte IS"},
                     {"id": "9", "home": "Sirius", "away": "Häcken"}]
        self.assertEqual("1026062550",
                         pool_played._kambi_id_for(catalogue, self._state()))

    def test_mirrored_fixture_is_never_matched(self):
        """Spegelvänd träff kan vara returmötet. Ett pris på fel lag är värre
        än inget pris."""
        catalogue = [{"id": "9", "home": "Örgryte IS", "away": "AIK"}]
        self.assertIsNone(pool_played._kambi_id_for(catalogue, self._state()))

    def test_ambiguous_link_gives_no_id(self):
        catalogue = [{"id": "1", "home": "AIK", "away": "Örgryte IS"},
                     {"id": "2", "home": "AIK", "away": "Örgryte"}]
        self.assertIsNone(pool_played._kambi_id_for(catalogue, self._state()))

    def test_one_side_needs_same_start_and_unique_candidate(self):
        state = self._state(home="Hapoel Be`er Sheva FC",
                            away="Sabah Masazir",
                            start="2026-08-19T18:00:00Z")
        event = {"id": "9", "home": "Hapoel Be`er Sheva FC",
                 "away": "Qarabag", "start": "2026-08-19T18:04:00Z"}
        self.assertEqual("9", pool_played._kambi_id_for([event], state))
        self.assertIsNone(pool_played._kambi_id_for(
            [{**event, "start": "2026-08-19T20:00:00Z"}], state))
        self.assertIsNone(pool_played._kambi_id_for(
            [event, {**event, "id": "10"}], state))

    def test_running_match_without_live_price_gives_an_interval(self):
        states = [{"event_number": 1, "sign": "1", "final": True,
                   "cancelled": False, "probs": None},
                  {"event_number": 2, "sign": "2", "final": False,
                   "cancelled": False, "in_progress": True, "probs": None,
                   "probs_basis": "live_saknas"}]
        live = pool_played.live_status(
            {"rows_text": "11\n12", "events_order": "[1,2]"}, states)

        self.assertNotIn("chance_per_level", live)
        self.assertIn("chance_min_per_level", live)
        self.assertEqual(1, len(live["chance_unpriced"]))

    def test_too_many_unpriced_matches_keep_the_note(self):
        """Ett intervall över för många okända matcher säger ingenting."""
        states = [{"event_number": n, "sign": None, "final": False,
                   "cancelled": False, "in_progress": True, "probs": None,
                   "probs_basis": "live_saknas"} for n in range(1, 5)]
        live = pool_played.live_status(
            {"rows_text": "1111\n1112", "events_order": "[1,2,3,4]"}, states)

        self.assertNotIn("chance_min_per_level", live)
        # "saknar odds" var fel ord om en match som rullar — den har odds hela
        # omgången, det är livemarknaden som är stängd just då.
        self.assertIn("livemarknad", live["chance_note"])
        self.assertNotIn("saknar odds", live["chance_note"])


if __name__ == "__main__":
    unittest.main()


class PenaltyShootoutStateTests(unittest.TestCase):
    """Cupmatcher avgjorda på straffar — uppmätt fel 2026-08-08.

    Barnsley–Wigan och Preston–Huddersfield i Stryktipset 4965 hade
    statusId 33 ("Slut efter straffläggning"). Den koden saknades i
    FINISHED_STATUS_IDS, så två FÄRDIGSPELADE matcher räknades som
    pågående: kortet sa 8/13 avgjorda när det var 10/13 och påstod att fem
    matcher rullade när det bara var tre.
    """

    @staticmethod
    def _shootout(number=1):
        """SvS-form för en cupmatch: 1–1 efter full tid, 6–5 på straffar."""
        return {
            "eventNumber": number, "cancelled": False,
            "match": {
                "statusId": 33, "status": "Slut efter straffläggning",
                "result": [
                    {"sportEventResultType": "Current", "home": "1", "away": "1"},
                    {"sportEventResultType": "Halftime", "home": "0", "away": "1"},
                    {"sportEventResultType": "Fulltime", "home": "1", "away": "1"},
                    {"sportEventResultType": "Penalties", "home": "6", "away": "5"},
                ],
            },
        }

    def test_shootout_is_final_and_scored_on_normal_time(self) -> None:
        state = pool_played.event_state(self._shootout())

        self.assertTrue(state["final"])
        self.assertFalse(state["in_progress"])
        # Straffsegraren vann matchen men INTE pooltecknet: 1–1 ⇒ X.
        self.assertEqual("X", state["sign"])
        self.assertEqual("1-1", state["score"])

    def test_fulltime_beats_current_when_current_carries_penalties(self) -> None:
        """Skyddet mot Montreal–Atlanta 2024, som blev "6-7" i stället för 2–2."""
        event = self._shootout()
        event["match"]["result"][0] = {
            "sportEventResultType": "Current", "home": "6", "away": "5"}

        state = pool_played.event_state(event)

        self.assertEqual("X", state["sign"])
        self.assertEqual("1-1", state["score"])

    def test_extra_time_stops_the_live_price_hunt_but_keeps_the_sign_unknown(self) -> None:
        """Apollon Limassol–Brann, Topptipset 4260 (2026-08-11).

        Matchen följdes live genom hela förlängningen. Ordinarie tid var 1–2,
        Overtime 1–2 och Current 2–4 — `Current` bär alltså ordinarie tid PLUS
        förlängningsmålen, och kl. 21:07 stod den i 2–3 (1–2 plus ett mål i
        förlängningen). Tecknet är därför OKÄNT tills Fulltime publiceras, och
        matchen ska förbli öppen för radräkningen.

        Det som ändras är prisjakten: Kambis 1X2-marknad stänger när ordinarie
        tid är slut, så `in_progress` måste bli False. Annars letar chansmotorn
        efter ett livepris som per definition inte finns, och kupongen fick
        noten "saknar odds" på en match som hade odds hela vägen.
        """
        event = {
            "eventNumber": 7, "cancelled": False,
            "match": {
                "statusId": 20, "status": "Första övertidsperioden",
                "result": [
                    {"sportEventResultType": "Current", "home": "2", "away": "3"},
                    {"sportEventResultType": "Halftime", "home": "2", "away": "3"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertTrue(state["extra_time"])
        self.assertFalse(state["in_progress"], "ingen livemarknad att hämta")
        # POOLREGELN: poolspel fastställs på ordinarie 90 minuter, så matchen
        # är klar för kupongen även om matchen inte är slut.
        self.assertTrue(state["final"], "ordinarie tid är spelad")
        # Utan Fulltime och Overtime går ordinarie tid inte att belägga — då
        # märks tecknet, men matchen räknas ändå.
        self.assertTrue(state["sign_provisional"])

    def test_overtime_field_recovers_regulation_time_before_fulltime(self) -> None:
        """Ordinarie 2–2 (X) med ett hemmamål i förlängningen ⇒ Current 3–2.

        Publicerar SvS `Overtime` innan `Fulltime` går ordinarie tid att räkna
        fram exakt: 3–2 minus 1–0 är 2–2, alltså X och inte den etta som
        Current ensam hade gett.
        """
        event = {
            "eventNumber": 7, "cancelled": False,
            "match": {
                "statusId": 21, "status": "Andra övertidsperioden",
                "result": [
                    {"sportEventResultType": "Current", "home": "3", "away": "2"},
                    {"sportEventResultType": "Overtime", "home": "1", "away": "0"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertTrue(state["final"], "ordinarie tid är spelad")
        self.assertEqual("X", state["sign"], "3–2 minus 1–0 är 2–2")
        self.assertEqual("2-2", state["score"])
        self.assertFalse(state["sign_provisional"], "beräknad, inte gissad")

    def test_extra_time_sign_is_marked_when_regulation_cannot_be_proven(self) -> None:
        """Utan Fulltime och Overtime bär Current förlängningsmålen.

        Matchen räknas ändå — poolen är avgjord på ordinarie tid — men tecknet
        märks, eftersom 3–2 här mycket väl kan vara ett 2–2 plus ett mål i
        förlängningen.
        """
        event = {
            "eventNumber": 7, "cancelled": False,
            "match": {
                "statusId": 21, "status": "Andra övertidsperioden",
                "result": [
                    {"sportEventResultType": "Current", "home": "3", "away": "2"},
                    {"sportEventResultType": "Halftime", "home": "1", "away": "1"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertTrue(state["final"])
        self.assertTrue(state["sign_provisional"])

    def test_fulltime_beats_current_after_extra_time(self) -> None:
        # Slutdatan: Fulltime är ordinarie tid, Overtime är målen i
        # förlängningen och Current är summan av de två.
        done = {
            "eventNumber": 7, "cancelled": False,
            "match": {
                "statusId": 32, "status": "Slut efter förlängning",
                "result": [
                    {"sportEventResultType": "Current", "home": "3", "away": "2"},
                    {"sportEventResultType": "Halftime", "home": "1", "away": "1"},
                    {"sportEventResultType": "Fulltime", "home": "2", "away": "2"},
                    {"sportEventResultType": "Overtime", "home": "1", "away": "0"},
                ],
            },
        }
        state = pool_played.event_state(done)

        self.assertTrue(state["final"])
        self.assertFalse(state["extra_time"])
        self.assertFalse(state["sign_provisional"])
        self.assertEqual("X", state["sign"], "ordinarie tid var 2–2")
        self.assertEqual("2-2", state["score"])

    def test_fulltime_during_extra_time_locks_sign_without_ending_match(self) -> None:
        """Nijmegen–Olympiakos, Topptipset 4260 (2026-08-11).

        SvS publicerade Fulltime 1–1 mitt i första övertidsperioden — tvärtemot
        antagandet att Fulltime aldrig kommer under pågående match. Tecknet står
        då fast, men matchen rullar vidare, och kortet ska säga båda delarna i
        stället för att visa "slut" på en match som spelas.
        """
        event = {
            "eventNumber": 3, "cancelled": False,
            "match": {
                "statusId": 20, "status": "Första övertidsperioden",
                "result": [
                    {"sportEventResultType": "Current", "home": "1", "away": "1"},
                    {"sportEventResultType": "Fulltime", "home": "1", "away": "1"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertTrue(state["final"], "Fulltime låser tecknet")
        self.assertEqual("X", state["sign"])
        self.assertFalse(state["sign_provisional"], "ordinarie tid är publicerad")
        self.assertTrue(state["extra_time"], "matchen spelas fortfarande")
        self.assertFalse(state["in_progress"], "ingen 1X2-marknad för ordinarie tid")

    def test_flashscore_supplies_regulation_time_during_extra_time(self) -> None:
        """CSKA 1948 Sofia–Panathinaikos, Topptipset 4260 (2026-08-11).

        SvS Current stod i 1–2 i andra övertidsperioden medan ordinarie tid var
        1–1. Skillnaden är tecknet X mot 2, alltså 1 mot 7 kvarvarande rader.
        """
        state = {"score": "1-2", "sign": "2", "sign_provisional": True}

        pool_played._apply_regulation(state, {"home_score": 1, "away_score": 1})

        self.assertEqual("X", state["sign"])
        self.assertEqual("1-1", state["score"])
        self.assertFalse(state["sign_provisional"])
        self.assertEqual("flashscore", state["regulation_source"])

    def test_regulation_time_may_never_exceed_the_current_score(self) -> None:
        """Mål kan bara TILLKOMMA i förlängningen.

        Ett högre värde betyder att fel fält lästs, och då rörs inte tecknet —
        en trasig källa får aldrig flytta ett resultat.
        """
        state = {"score": "1-2", "sign": "2", "sign_provisional": True}

        pool_played._apply_regulation(state, {"home_score": 3, "away_score": 2})

        self.assertEqual("2", state["sign"], "tecknet är orört")
        self.assertTrue(state["sign_provisional"])
        self.assertNotIn("regulation_source", state)

    def test_missing_flashscore_summary_leaves_the_sign_unproven(self) -> None:
        for summary in (None, {}, {"home_score": 1, "away_score": None}):
            state = {"score": "1-2", "sign": "2", "sign_provisional": True}

            pool_played._apply_regulation(state, summary)

            self.assertTrue(state["sign_provisional"], f"vid {summary}")
            self.assertEqual("2", state["sign"])

    def test_model_is_anchored_in_the_prematch_price(self) -> None:
        """Intensiteterna ska ÅTERGE marknadens pris, inte ha en egen åsikt.

        Utan ankaret vore siffran en fristående modellgissning, och projektet
        har mätt tre gånger att modell-edges utan marknadsankare blir
        systematiskt uppblåsta.
        """
        prematch = {"1": 0.68, "X": 0.20, "2": 0.12}

        lam_home, lam_away = pool_played._lambdas_from_prematch(prematch)
        back = pool_played._signs_from_lambdas(lam_home, lam_away)

        for sign in ("1", "X", "2"):
            self.assertAlmostEqual(prematch[sign], back[sign], places=2,
                                   msg=f"tecken {sign}")

    def test_score_and_time_move_the_estimate(self) -> None:
        """En tvåmålsledning sent i matchen är nästan avgjord.

        Det var hela anledningen: kortet visade "0 %–77 %" på en kupong där
        NK Celje ledde 2–0 i andra halvlek.
        """
        prematch = {"1": 0.68, "X": 0.20, "2": 0.12}
        start = (dt.datetime.now(dt.timezone.utc)
                 - dt.timedelta(minutes=75)).isoformat()

        leading = pool_played.live_probs_from_score(
            {"prematch_probs": prematch, "score": "2-0", "start": start})
        trailing = pool_played.live_probs_from_score(
            {"prematch_probs": prematch, "score": "0-2", "start": start})

        self.assertGreater(leading["1"], 0.95)
        self.assertGreater(trailing["2"], 0.80)
        # Favoritskapet får inte överleva ett underläge.
        self.assertLess(trailing["1"], 0.10)

    def test_real_match_minute_beats_wall_clock(self) -> None:
        """Flashscores matchminut ska slå klocktiden sedan avspark.

        En match som stått stilla i paus eller haft långt tillägg har spelat
        färre minuter än klockan visar, och tid kvar är hela hävstången i
        skattningen.
        """
        prematch = {"1": 0.68, "X": 0.20, "2": 0.12}
        # Klockan säger ~85 spelade minuter, Flashscore säger 45 (paus).
        start = (dt.datetime.now(dt.timezone.utc)
                 - dt.timedelta(minutes=100)).isoformat()
        base = {"prematch_probs": prematch, "score": "0-0", "start": start}

        wall = pool_played.live_probs_from_score(dict(base))
        real = pool_played.live_probs_from_score({**base, "minute": 45})

        # Med bara fem minuter kvar är 0–0 nästan säkert kryss; med 45 kvar
        # har favoriten fortfarande gott om tid.
        self.assertGreater(wall["X"], real["X"])
        self.assertGreater(real["1"], wall["1"])

    def test_frozen_minute_in_half_time_is_used_as_is(self) -> None:
        """`minute` fryses i paus och får inte räknas upp med pausens längd."""
        state = {"minute": 45}

        self.assertEqual(45.0, pool_played._minutes_played(state))

    def test_model_needs_both_price_and_score(self) -> None:
        start = dt.datetime.now(dt.timezone.utc).isoformat()
        for state in ({"score": "1-0", "start": start},
                      {"prematch_probs": {"1": .5, "X": .3, "2": .2},
                       "start": start},
                      {"prematch_probs": {"1": .5, "X": .3, "2": .2},
                       "score": "1-0"}):
            self.assertIsNone(pool_played.live_probs_from_score(state))

    def test_finished_after_extra_time_status_counts_as_finished(self) -> None:
        """statusId 32 saknades i FINISHED_STATUS_IDS — samma lucka som 33.

        Matchen räddades bara av att ett publicerat Fulltime också räknas som
        slut. Utan Fulltime hade en färdigspelad match sett pågående ut.
        """
        match = {"statusId": 32, "status": "Slut efter förlängning", "result": []}

        self.assertTrue(pool_played.match_finished(match))
        self.assertFalse(pool_played.in_extra_time(match))

    def test_forhastat_fulltime_gor_inte_en_pagaende_match_slut(self) -> None:
        """SvS publicerade Fulltime 0–0 mitt i första halvlek.

        Nottingham–Leeds (Stryktipset 4967, event 4, 2026-08-22) bar `statusId`
        6 = "Första halvlek" 43 minuter efter avspark och var ensam bland
        omgångens tretton matcher om att ha ett publicerat `Fulltime`.
        Skyddsnätet mot okända statuskoder gjorde matchen "slut" med tecknet X
        på sex spelade kuponger. Nätet får aldrig köra över klockan.
        """
        nu = dt.datetime(2026, 8, 22, 14, 43, tzinfo=dt.timezone.utc)
        match = {"statusId": 6, "status": "Första halvlek",
                 "matchStart": "2026-08-22T16:00:00+02:00",
                 "result": [{"sportEventResultType": "Current",
                             "home": "0", "away": "0"},
                            {"sportEventResultType": "Fulltime",
                             "home": "0", "away": "0"}]}

        self.assertFalse(pool_played.match_finished(match, now=nu))
        self.assertFalse(pool_played.regulation_over(match, now=nu))

    def test_fulltime_under_forlangning_passerar_klockvetot(self) -> None:
        """Vetot är fysik, inte en statuskod — det får inte fälla äkta fall.

        Nijmegen–Olympiakos bar Fulltime 1–1 mitt i första övertidsperioden
        2026-08-11. Då har det gått långt mer än 105 minuter, så nätet ska
        fungera precis som förut.
        """
        nu = dt.datetime(2026, 8, 11, 21, 15, tzinfo=dt.timezone.utc)
        match = {"statusId": 20, "status": "Första övertidsperioden",
                 "matchStart": "2026-08-11T19:00:00+00:00",
                 "result": [{"sportEventResultType": "Fulltime",
                             "home": "1", "away": "1"}]}

        self.assertTrue(pool_played.match_finished(match, now=nu))

    def test_okand_avspark_lamnar_skyddsnatet_orort(self) -> None:
        """Ett oläsbart datum får aldrig göra en färdigspelad match öppen."""
        match = {"statusId": 99, "status": "Okänd kod", "matchStart": None,
                 "result": [{"sportEventResultType": "Fulltime",
                             "home": "2", "away": "1"}]}

        self.assertTrue(pool_played.match_finished(match))

    def test_klockvetot_gäller_bara_fulltime_inte_slutstatusen(self) -> None:
        """Vetot gatear NÄTET, aldrig en uttalad slutstatus.

        Säger SvS att matchen är slut är den slut, även om avsparken enligt
        payloaden ligger orimligt nära — annars vore ett trasigt `matchStart`
        nog för att öppna en avgjord match igen.
        """
        nu = dt.datetime(2026, 8, 22, 14, 43, tzinfo=dt.timezone.utc)
        match = {"statusId": 31, "status": "Slut",
                 "matchStart": "2026-08-22T16:00:00+02:00", "result": []}

        self.assertTrue(pool_played.match_finished(match, now=nu))

    def test_finished_shootout_is_not_reported_as_playing_extra_time(self) -> None:
        """Slutstatusen bär ordet "straffläggning" utan att något spelas."""
        state = pool_played.event_state(self._shootout())

        self.assertFalse(state["extra_time"])
        self.assertFalse(state["sign_provisional"])

    def test_running_match_without_fulltime_is_not_final(self) -> None:
        # Verifierat mot SvS: matcher i spel bär bara Current och Halftime.
        event = {
            "eventNumber": 1, "cancelled": False,
            "match": {
                "statusId": 7, "status": "Andra halvlek",
                "result": [
                    {"sportEventResultType": "Current", "home": "3", "away": "0"},
                    {"sportEventResultType": "Halftime", "home": "1", "away": "0"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertFalse(state["final"])
        self.assertTrue(state["in_progress"])
        self.assertEqual("1", state["sign"])
