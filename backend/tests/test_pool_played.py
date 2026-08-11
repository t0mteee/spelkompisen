import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import kambi, pool_played
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
        self.assertLess(state["probs"]["1"], 0.15, "prematch-favoriten ska falla")
        self.assertGreater(state["probs"]["2"], 0.65)
        self.assertAlmostEqual(1.0, sum(state["probs"].values()), places=6)

    def test_missing_live_price_clears_instead_of_falling_back(self):
        state = self._state()
        with patch.object(kambi, "live_events", return_value=[CATALOGUE]), \
             patch.object(kambi, "live_1x2", return_value={}):
            pool_played.attach_live_odds(self.store, [state])
        self.assertIsNone(state["probs"], "prematch får aldrig återanvändas")
        self.assertEqual("live_saknas", state["probs_basis"])

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

    def test_extra_time_decides_the_pool_sign_but_not_the_match(self) -> None:
        """Apollon Limassol–Brann, Topptipset 4260 (2026-08-11).

        statusId 20 = "Första övertidsperioden": ordinarie tid slut 2–3, alltså
        står pooltecknet fast. Utan den skillnaden räknades matchen som helt
        öppen, chansmotorn jagade ett livepris som inte finns när ordinarie tid
        är slut, och kupongen fick noten "saknar odds" på en match som hade
        odds hela vägen.
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

        self.assertTrue(state["final"], "ordinarie tid är spelad")
        self.assertTrue(state["extra_time"])
        self.assertFalse(state["in_progress"], "ingen livemarknad att hämta")
        self.assertEqual("2", state["sign"])
        self.assertEqual("2-3", state["score"])
        # Current kan förorenas av ett förlängningsmål innan Fulltime kommer.
        self.assertTrue(state["sign_provisional"])

    def test_extra_time_prefers_period_sums_over_current(self) -> None:
        """Ett mål i förlängningen får inte flytta pooltecknet.

        Halvlekssummorna är immuna mot förlängningsmål: Halftime 1–0 plus
        Period2 0–1 är ordinarie tid 1–1 även när Current hunnit bli 2–1.
        """
        event = {
            "eventNumber": 7, "cancelled": False,
            "match": {
                "statusId": 21, "status": "Andra övertidsperioden",
                "result": [
                    {"sportEventResultType": "Current", "home": "2", "away": "1"},
                    {"sportEventResultType": "Halftime", "home": "1", "away": "0"},
                    {"sportEventResultType": "Period2", "home": "0", "away": "1"},
                ],
            },
        }

        state = pool_played.event_state(event)

        self.assertEqual("X", state["sign"], "ordinarie tid var 1–1")
        self.assertEqual("1-1", state["score"])
        # Fortfarande preliminärt: SvS skrev om `Halftime` mitt i förlängningen
        # på Apollon–Brann 2026-08-11, så summan är bättre än Current men inte
        # ett facit. Bara Fulltime låser tecknet.
        self.assertTrue(state["sign_provisional"])

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
