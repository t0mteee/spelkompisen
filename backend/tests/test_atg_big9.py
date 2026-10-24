"""ATG Big 9 (beslut driften-2026-10-24-big9-atg): insamling, kadens, nivå och
format, byggaren, frysning på facitsidan, rättning och missat.

Sedan beslut 2026-10-24-sp96-ar-big9 (val 0) är SP96 (nya Big 9, utan Wild
Card, 6–9 rätt) den mätta produkten; gamla BIG9 samlas bara in. BIG9:s Wild
Card-regler prövas kvar i byggaren och rättningen, som inte beror på vad som mäts."""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import Klocka, giltigt_svar, ny_store  # noqa: E402
from app import atg, big9_builder  # noqa: E402
from app.spelai import api, big9, frysning, indata, nivaer, ratta, tillstand  # noqa: E402
from app.spelai.sandbox import AgentSvar  # noqa: E402

UTC = dt.timezone.utc
CLOSE = dt.datetime(2026, 10, 31, 14, 0, tzinfo=UTC)
BIG9_START = dt.datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

# folkets fördelning per match (sex celler) och odds
DIST = {"home": {"over": 30.0, "under": 12.0}, "tie": {"over": 8.0, "under": 14.0},
        "away": {"over": 24.0, "under": 12.0}}
ODDS = {"home": 2.2, "tie": 3.6, "away": 3.1, "over": 1.75, "under": 2.05}


# SP96 omgång 517: potterna för 6–8 rätt = omsättning × 72,75 % × andelen.
SP96_RATIO = 0.7275


def default_payouts(game_type, turnover_ore):
    if game_type == "BIG9":
        return {"7": {"pot": int(turnover_ore * 0.65 * 0.4)},
                "8": {"pot": int(turnover_ore * 0.65 * 0.2)},
                "9": {"pot": int(turnover_ore * 0.65 * 0.4) + 10_000_000}}
    return {"6": {"pot": int(turnover_ore * SP96_RATIO * 0.35)},
            "7": {"pot": int(turnover_ore * SP96_RATIO * 0.15)},
            "8": {"pot": int(turnover_ore * SP96_RATIO * 0.15)},
            "9": {"pot": int(turnover_ore * SP96_RATIO * 0.35) + 10_000_000}}


def record(serial=600, status="SELL_OPEN", close=CLOSE, game_type="SP96",
           results=None, payouts=None, turnover_ore=80_000_000):
    matches = []
    for i in range(1, 10):
        odds = dict(ODDS, home=round(1.6 + 0.2 * i, 2))
        dist = {k: dict(v) for k, v in DIST.items()}
        if game_type == "BIG9":
            dist["wildcard"] = 100 / 9
        m = {"id": f"m{i}", "number": str(i), "startTime": atg.iso(close),
             "status": "UPCOMING", "championship": {"name": "Premier League"},
             "homeTeam": {"name": f"H{i}"}, "awayTeam": {"name": f"B{i}"},
             "odds": odds, "betDistribution": dist,
             # platshållare som ATG skickar även för ospelade matcher
             "result": {"winner": "tie", "goals": "under"},
             "score": {"home": 0, "away": 0}}
        if results:
            res = results[i - 1]
            if res == "*":
                m.update(status="CANCELED", canceledAt="2026-10-31T18:00:00Z")
                m.pop("result")
            else:
                winner = {"1": "home", "X": "tie", "2": "away"}[res[0]]
                m.update(status="DECIDED",
                         result={"winner": winner,
                                 "goals": "over" if res[1] == "O" else "under"})
        matches.append(m)
    big9_regler = game_type == "BIG9"
    return {"id": f"{game_type}_{serial}", "status": status, "gameType": game_type,
            "name": "Lördag", "takeoutPercentage": 35 if big9_regler else 25,
            "overUnderLimit": 2.5,
            "startTime": atg.iso(close), "serialNumber": serial,
            "pool": {"turnover": turnover_ore, "unitStake": 50,
                     "minUnitDividend": 1500 if big9_regler else 1000,
                     "jackpotAmount": 0, "numberOfBets": 1000,
                     "payouts": payouts or default_payouts(game_type, turnover_ore)},
            "matches": matches}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp)
        self.conn = self.store.conn
        atg.apply_schema(self.conn)
        tillstand.satt(self.conn, big9.START_KEY, tillstand.iso(BIG9_START),
                       source="test", now=BIG9_START)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def fetch(self, records, at):
        return atg.run_pass(
            self.conn, clock=lambda: at, fetch=lambda: (records, {"http_status": 200}),
            force=True, on_round=lambda conn, product, obs, now: big9.capture_due(
                conn, product, obs, now=now))

    def payload(self, horizon="30m"):
        row = self.conn.execute("SELECT payload_json FROM spelai_input WHERE "
                                "horizon=?", (horizon,)).fetchone()
        return json.loads(row[0])


class InsamlingTests(_Base):
    def test_oppen_omgang_skrivs_varje_hamtning_avgjord_en_gang(self):
        t = CLOSE - dt.timedelta(days=2)
        old = record(serial=500, status="FINALIZED", close=CLOSE - dt.timedelta(days=7),
                     results=["1O"] * 9)
        for k in range(3):
            self.fetch([record(), old, {"gameType": "SP5", "id": "x"}],
                       t + dt.timedelta(hours=k))
        counts = dict(self.conn.execute(
            "SELECT status, COUNT(*) FROM atg_round_observation GROUP BY status"))
        self.assertEqual({"SELL_OPEN": 3, "FINALIZED": 1}, counts)
        self.assertEqual(3, self.conn.execute(
            "SELECT COUNT(*) FROM atg_offering_capture WHERE ok=1").fetchone()[0])

    def test_misslyckad_hamtning_bokfors_och_tabellerna_ar_append_only(self):
        def boom():
            raise atg.FetchError("HTTP 503", 503)
        rep = atg.run_pass(self.conn, clock=lambda: CLOSE, fetch=boom, force=True)
        self.assertIn("fel", rep)
        row = self.conn.execute("SELECT ok, http_status FROM atg_offering_capture").fetchone()
        self.assertEqual((0, 503), tuple(row))
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("UPDATE atg_offering_capture SET ok=1")
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM atg_offering_capture")

    def test_saknade_tabeller_hoppar_over(self):
        conn = sqlite3.connect(":memory:")
        try:
            self.assertIn("skipped", atg.run_pass(conn, clock=lambda: CLOSE))
        finally:
            conn.close()

    def test_kadens(self):
        t0 = CLOSE - dt.timedelta(days=3)
        self.assertTrue(atg.fetch_due(self.conn, t0)[0])
        self.fetch([record()], t0)
        self.assertFalse(atg.fetch_due(self.conn, t0 + dt.timedelta(hours=5))[0])
        self.assertTrue(atg.fetch_due(self.conn, t0 + dt.timedelta(hours=6))[0])
        # inom 7 h före spelstopp: var 30:e minut
        t1 = CLOSE - dt.timedelta(hours=6, minutes=50)
        self.fetch([record()], t1)
        self.assertFalse(atg.fetch_due(self.conn, t1 + dt.timedelta(minutes=20))[0])
        self.assertTrue(atg.fetch_due(self.conn, t1 + dt.timedelta(minutes=30))[0])
        # i 30m-fönstret: varje pool-tick (≥ 4 min)
        t2 = CLOSE - dt.timedelta(minutes=40)
        self.fetch([record()], t2)
        self.assertTrue(atg.fetch_due(self.conn, CLOSE - dt.timedelta(minutes=34))[0])
        # efter spelstopp: var 30:e minut tills FINALIZED
        t3 = CLOSE + dt.timedelta(hours=1)
        self.fetch([record(status="SELL_CLOSED")], t3)
        self.assertTrue(atg.fetch_due(self.conn, t3 + dt.timedelta(minutes=30))[0])
        self.fetch([record(status="FINALIZED", results=["1O"] * 9)],
                   t3 + dt.timedelta(minutes=30))
        self.assertFalse(atg.fetch_due(self.conn, t3 + dt.timedelta(hours=2))[0])

    def test_paket_bara_for_sp96_i_fonstret_utan_platshallarresultat(self):
        at = CLOSE - dt.timedelta(minutes=33)
        rep = self.fetch([record(), record(serial=601, game_type="BIG9")], at)
        captured = {(f["product"], tuple(f["facit"]["captured"])) for f in rep["facit"]}
        self.assertIn(("sp96", ("30m",)), captured)
        self.assertIn(("big9", ()), captured)        # gamla BIG9: bara insamling
        rows = self.conn.execute("SELECT product, draw_number, horizon, observed_at "
                                 "FROM spelai_input").fetchall()
        self.assertEqual([("sp96", 600, "30m", atg.iso(at))], [tuple(r) for r in rows])
        payload = self.payload()
        self.assertEqual([256], payload["nivaer"])
        self.assertEqual(list(range(1, 10)), payload["events_order"])
        self.assertEqual(list(big9_builder.CELLS), payload["rader"]["tokens"])
        self.assertFalse(payload["rader"]["wildcard"])
        for m in payload["omgang"]["matches"]:
            self.assertNotIn("result", m)
            self.assertNotIn("score", m)
        self.assertEqual(800_000.0, payload["turnover"]["live"])
        self.assertEqual("atg_potter", payload["omgang"]["aterbetalning"]["kalla"])
        self.assertAlmostEqual(SP96_RATIO, payload["omgang"]["aterbetalning"]["andel"],
                               places=4)
        self.assertAlmostEqual(100_000.0, payload["jackpot"]["value"], places=0)
        # utanför fönstret: inget paket
        self.fetch([record(serial=602, close=CLOSE + dt.timedelta(hours=3))], at)
        self.assertEqual(1, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_input").fetchone()[0])

    def test_projicerad_omsattning_ur_avslutade_omgangar(self):
        for k in range(3):
            self.fetch([record(serial=590 + k, status="FINALIZED", results=["1O"] * 9,
                               close=CLOSE - dt.timedelta(days=7 * (k + 1)),
                               turnover_ore=100_000_000 + k * 10_000_000)],
                       CLOSE - dt.timedelta(days=1, minutes=k))
        self.fetch([record()], CLOSE - dt.timedelta(minutes=33))
        turnover = self.payload()["turnover"]
        self.assertEqual(1_100_000.0, turnover["projected"])
        self.assertEqual(1_100_000.0, turnover["used"])
        self.assertEqual(3, turnover["n_final"])


class NivaTests(unittest.TestCase):
    def rad(self, w=0, cell="1O"):
        return " ".join("W" if i == w else cell for i in range(9))

    def rad96(self, cell="1O", first="1O"):
        return " ".join([first] + [cell] * 8)

    def test_giltiga_rader(self):
        form = nivaer.validera("sp96", 256, {"format": "rows",
                                             "rows": [self.rad96(), self.rad96("XU")]})
        self.assertEqual(2, form["n_rows"])
        self.assertEqual(1.0, form["cost_kr"])
        self.assertEqual((256,), nivaer.nivaer_for("sp96"))
        self.assertEqual((), nivaer.nivaer_for("big9"))    # gamla BIG9 mäts inte
        self.assertIn("sp96", nivaer.produkter())
        self.assertNotIn("big9", nivaer.produkter())
        self.assertEqual("Big 9", nivaer.produktnamn("sp96"))
        self.assertEqual(big9_builder.CELLS, nivaer.atg_symboler("sp96"))
        self.assertEqual(big9_builder.TOKENS, nivaer.atg_symboler("big9"))

    def test_ogiltiga_rader(self):
        cases = {
            "ogiltig token W": [self.rad96(first="W")],     # SP96 har inget Wild Card
            "tokens": ["1O XU 1O"],
            "ogiltig token 1X": [self.rad96().replace("1O", "1X", 1)],
            "dubblett": [self.rad96(), self.rad96()],
        }
        for orsak, rows in cases.items():
            with self.assertRaises(nivaer.Ogiltigt, msg=orsak) as ctx:
                nivaer.validera("sp96", 256, {"format": "rows", "rows": rows})
            self.assertIn(" ".join(orsak.split()[:2]).lower()
                          if orsak.startswith("ogiltig") else orsak.lower(),
                          str(ctx.exception).lower())
        many = [" ".join(big9_builder.CELLS[(k // 6 ** j) % 6] for j in range(9))
                for k in range(513)]
        with self.assertRaises(nivaer.Ogiltigt) as ctx:
            nivaer.validera("sp96", 256, {"format": "rows", "rows": many})
        self.assertIn("över nivån", str(ctx.exception))
        with self.assertRaises(nivaer.Ogiltigt):
            nivaer.validera("sp96", 512, {"format": "rows", "rows": [self.rad96()]})
        with self.assertRaises(nivaer.Ogiltigt):     # gamla BIG9 har inga nivåer
            nivaer.validera("big9", 256, {"format": "rows", "rows": [self.rad()]})


class ByggareTests(unittest.TestCase):
    def test_cellerna_traffar_bada_marknaderna(self):
        p = big9_builder.cell_probabilities(ODDS)
        self.assertAlmostEqual(1.0, sum(p.values()), places=9)
        x12 = big9_builder._devig([ODDS["home"], ODDS["tie"], ODDS["away"]])
        ou = big9_builder._devig([ODDS["over"], ODDS["under"]])
        self.assertAlmostEqual(x12[0], p["1O"] + p["1U"], places=6)
        self.assertAlmostEqual(x12[1], p["XO"] + p["XU"], places=6)
        self.assertAlmostEqual(ou[0], p["1O"] + p["XO"] + p["2O"], places=6)
        # kryss hänger ihop med under (Poissonsambandet)
        self.assertGreater(p["XU"], p["XO"])
        self.assertIsNone(big9_builder.cell_probabilities({"home": 2.0}))

    def test_minimiutdelning(self):
        self.assertEqual(0.0, big9_builder._dividend(1000.0, 99.0, 15.0))
        self.assertEqual(20.0, big9_builder._dividend(1000.0, 49.0, 15.0))
        self.assertEqual(1000.0, big9_builder._dividend(1000.0, 0.0, 15.0))

    def runda(self, wildcard, splits):
        p = big9_builder.cell_probabilities(ODDS)
        q = big9_builder.folk_distribution(DIST)
        matches = [big9_builder.Big9Match(number=i, p=p, q=q,
                                          wildcard_share=1 / 9 if wildcard else 0.0)
                   for i in range(1, 10)]
        return big9_builder.Big9Round(
            product="x", matches=matches, turnover=800_000.0, row_price=0.5,
            payout_ratio=0.7275, splits=splits, min_dividend=10.0, wildcard=wildcard)

    def test_wild_card_i_gamla_big9(self):
        system = big9_builder.build_rows(self.runda(True, atg.PRODUCTS["big9"]["splits"]),
                                         20.0)
        self.assertEqual(40, system.n_rows)
        self.assertTrue(all(r.split().count("W") == 1 for r in system.rows))

    def test_sp96_utan_wild_card_och_sex_ratt_ger_pott(self):
        rnd = self.runda(False, atg.PRODUCTS["sp96"]["splits"])
        self.assertEqual({6, 7, 8, 9}, set(big9_builder.prize_pools(rnd)))
        system = big9_builder.build_rows(rnd, 20.0)
        self.assertEqual(40, system.n_rows)
        self.assertFalse(any("W" in r.split() for r in system.rows))
        row = tuple(system.rows[0].split())
        # 6 rätt bär en egen pott: utan den blir radens EV lägre
        self.assertGreater(big9_builder.row_ev(rnd, row),
                           big9_builder.row_ev(rnd, row, {k: v for k, v in
                                               big9_builder.prize_pools(rnd).items()
                                               if k != 6}))


class AterbetalningTests(unittest.TestCase):
    def test_andelen_ur_potterna_och_reserv_till_uttaget(self):
        ratio, source = big9.payout_ratio(record(), "sp96")
        self.assertEqual("atg_potter", source)
        self.assertAlmostEqual(SP96_RATIO, ratio, places=4)
        ratio, source = big9.payout_ratio(record(game_type="BIG9"), "big9")
        self.assertEqual("atg_potter", source)
        self.assertAlmostEqual(0.65, ratio, places=4)
        # oense potter eller inga potter: 1 − uttag
        oense = default_payouts("SP96", 80_000_000)
        oense["7"]["pot"] *= 2
        for payouts in (oense, {"9": {"pot": 1}}):
            rec = record(payouts=payouts)
            self.assertEqual((0.75, "uttag"), big9.payout_ratio(rec, "sp96"))


class FrysningTests(_Base):
    def freeze(self, svar_fn=giltigt_svar, at=None):
        at = at or CLOSE - dt.timedelta(minutes=33)
        self.fetch([record()], at)
        return frysning.process_inputs(
            self.conn, lambda payload, levels, timeout: svar_fn(payload, levels, timeout),
            clock=Klocka(at))

    def proposals(self):
        self.conn.row_factory = sqlite3.Row
        try:
            return {r["role"]: dict(r) for r in self.conn.execute(
                "SELECT * FROM spelai_pool_proposal WHERE product='sp96'")}
        finally:
            self.conn.row_factory = None

    def test_standard_ar_big9_byggaren_och_svs_rader_ar_ogiltiga(self):
        self.freeze()
        rows = self.proposals()
        std = rows["standard"]
        self.assertEqual("fryst", std["status"])
        self.assertEqual("big9-varderader-v1-sp96-b256-medel", std["config_key"])
        self.assertEqual(512, std["n_rows"])
        self.assertEqual(256.0, std["cost_kr"])
        lines = std["rows_text"].splitlines()
        self.assertTrue(all(len(line.split()) == 9 and "W" not in line.split()
                            for line in lines))
        self.assertIn("återbetalning 72.75% (atg_potter)", std["reason"])
        self.assertEqual(len(lines), len(set(lines)))
        self.assertIn("big9-varderader-v1", std["reason"])
        self.assertEqual("ogiltigt", rows["agent"]["status"])
        self.assertIn("tokens", rows["agent"]["reason"])
        # samma paket ⇒ samma rader (deterministisk)
        again = big9.build_standard(self.payload(), 256)
        self.assertEqual(std["rows_hash"], again["rows_hash"])

    def test_agentens_big9_rader_fryses(self):
        def svar(payload, levels, timeout):
            rows = [" ".join("XU" if i == w else "1O" for i in range(9)) for w in range(9)]
            return AgentSvar("ok", data={"version": "agent-big9-v1", "forslag": {
                "256": {"format": "rows", "rows": rows}}})
        self.freeze(svar)
        agent = self.proposals()["agent"]
        self.assertEqual("fryst", agent["status"])
        self.assertEqual(9, agent["n_rows"])
        self.assertEqual(4.5, agent["cost_kr"])

    def test_api_andelar_och_matchnamn(self):
        self.freeze()
        std_id = self.proposals()["standard"]["id"]
        out = api.forslag(self.conn, std_id)
        self.assertEqual("H1 – B1", out["matcher"][0]["match"])
        self.assertEqual(set(big9_builder.CELLS), set(out["andelar"][0]))
        self.assertAlmostEqual(1.0, sum(out["andelar"][0].values()))


class RattaTests(_Base):
    FACIT = ["1O", "XU", "2O", "1U", "1O", "2U", "XO", "1O", "*"]

    def settle_record(self, own_rows, payouts, game_type="BIG9"):
        rec = record(status="FINALIZED", results=self.FACIT, payouts=payouts,
                     game_type=game_type)
        return big9.counterfactual(rec, list(range(1, 10)), own_rows,
                                   len(own_rows) * 0.5)

    def test_utdelning_som_atg_och_wild_card_och_struken_match(self):
        right = " ".join(self.FACIT[:8] + ["2U"])          # struken match: rätt
        eight = " ".join(["W"] + ["2U"] + self.FACIT[2:8] + ["2U"])  # W rätt, en miss
        payouts = {"9": {"pot": 50_000_000, "qualifyingUnits": 99.0, "unitDividend": 500000},
                   "8": {"pot": 10_000_000, "qualifyingUnits": 9999.5, "unitDividend": 0,
                         "jackpot": True},
                   "7": {"pot": 1_000, "qualifyingUnits": 0.0, "unitDividend": 0}}
        facit = self.settle_record([right, eight], payouts)
        self.assertEqual({9: 1, 8: 1}, facit["dist"])
        self.assertTrue(facit["complete"])
        self.assertEqual(5000.0, facit["payout"])          # 50 000 000/(99+1) öre
        self.assertEqual(5000.0, facit["published"])
        self.assertEqual(0.0, facit["payout"] - 5000.0)    # 8 rätt under 15 kr ⇒ 0
        self.assertAlmostEqual(5000.0 / 1.0 - 1.0, facit["roi"])

    def test_sp96_sex_ratt_och_minimiutdelning_10_kr(self):
        # fem rätt + struken match (rätt för alla) = 6; sex rätt + struken = 7
        six = " ".join(self.FACIT[:5] + ["1O", "1U", "2U", "2U"])
        seven = " ".join(self.FACIT[:6] + ["1U", "2U", "2U"])
        payouts = {"6": {"pot": 1_000_000, "qualifyingUnits": 999.0, "unitDividend": 0},
                   "7": {"pot": 5_000_000, "qualifyingUnits": 99.0, "unitDividend": 50000}}
        facit = self.settle_record([six, seven], payouts, game_type="SP96")
        self.assertEqual({6: 1, 7: 1}, facit["dist"])
        # 6 rätt: 1 000 000/(999+1) = 1 000 öre = 10 kr — precis minimiutdelningen
        self.assertEqual(10.0 + 500.0, facit["payout"])
        payouts["6"]["qualifyingUnits"] = 1000.0         # 9,99 kr ⇒ 0
        facit = self.settle_record([six, seven], payouts, game_type="SP96")
        self.assertEqual(500.0, facit["payout"])

    def test_grupp_utan_vinnare_ger_hela_potten(self):
        right = " ".join(self.FACIT[:8] + ["1O"])
        payouts = {"9": {"pot": 12_345_678, "qualifyingUnits": 0.0, "unitDividend": 0,
                         "jackpot": True}}
        facit = self.settle_record([right], payouts)
        self.assertEqual(123_456.0, facit["payout"])        # nedåt till hela kronor
        self.assertEqual(0.0, facit["published"])

    def test_ospelad_match_ar_inget_facit(self):
        rec = record(status="FINALIZED")                    # bara platshållare
        self.assertIsNone(big9.counterfactual(rec, list(range(1, 10)), ["x"], 0.5))

    def test_settle_skriver_append_once_och_installd_omgang(self):
        # standarden och agenten för SP96 rättas mot ATG:s FINALIZED-post
        self.freeze_both()
        self.fetch([record(status="FINALIZED", results=self.FACIT)],
                   CLOSE + dt.timedelta(hours=3))
        rep = ratta.settle(self.store, now=CLOSE + dt.timedelta(hours=3))
        self.assertEqual(2, rep["rattade"])
        again = ratta.settle(self.store, now=CLOSE + dt.timedelta(hours=4))
        self.assertEqual(0, again["rattade"])
        notes = [r[0] for r in self.conn.execute(
            "SELECT settlement_version FROM spelai_pool_result")]
        self.assertEqual([big9.SETTLEMENT_VERSION] * 2, notes)

    def test_installd(self):
        self.freeze_both()
        self.fetch([record(status="CANCELED")], CLOSE + dt.timedelta(hours=3))
        rep = ratta.settle(self.store, now=CLOSE + dt.timedelta(hours=3))
        self.assertEqual(2, rep["installda"])

    def freeze_both(self):
        def svar(payload, levels, timeout):
            rows = [" ".join("XU" if i == 0 else "1O" for i in range(9))]
            return AgentSvar("ok", data={"version": "a", "forslag": {
                "256": {"format": "rows", "rows": rows}}})
        at = CLOSE - dt.timedelta(minutes=33)
        self.fetch([record()], at)
        frysning.process_inputs(self.conn, lambda p, lv, t: svar(p, lv, t),
                                clock=Klocka(at))


class MissatTests(_Base):
    def test_missat_bara_efter_big9_start(self):
        old = record(serial=500, status="FINALIZED", results=["1O"] * 9,
                     close=BIG9_START - dt.timedelta(days=7))
        self.fetch([record(), old], CLOSE - dt.timedelta(days=1))
        rep = frysning.mark_missed(self.conn, now=CLOSE + dt.timedelta(minutes=10))
        self.assertEqual(4, rep["missat"])     # 600: två horisonter × två roller
        serials = {r[0] for r in self.conn.execute(
            "SELECT DISTINCT draw_number FROM spelai_pool_proposal")}
        self.assertEqual({600}, serials)

    def test_utan_big9_start_inga_missar(self):
        conn = self.conn
        tmp = tempfile.TemporaryDirectory()
        store = ny_store(tmp)
        try:
            atg.apply_schema(store.conn)
            self.conn = store.conn
            self.fetch([record()], CLOSE - dt.timedelta(days=1))
            rep = frysning.mark_missed(store.conn, now=CLOSE + dt.timedelta(minutes=10))
            self.assertEqual(0, rep["missat"])
        finally:
            self.conn = conn
            store.close()
            tmp.cleanup()


class PerNivaTests(_Base):
    def test_big9_raknas_separat(self):
        for product, number in (("sp96", 600), ("stryktipset", 5000)):
            for role in ("agent", "standard"):
                cur = self.conn.execute(
                    "INSERT INTO spelai_pool_proposal (product, draw_number, level_kr, "
                    "horizon, role, status, reg_close_time, frozen_at, cost_kr) "
                    "VALUES (?,?,256,'30m',?,'fryst',?,?,256)",
                    (product, number, role, atg.iso(CLOSE), atg.iso(CLOSE)))
                self.conn.execute(
                    "INSERT INTO spelai_pool_result (proposal_id, settled_at, "
                    "settlement_version, payout_kr, payout_complete, cost_kr) "
                    "VALUES (?,?,?,?,1,256)", (cur.lastrowid, atg.iso(CLOSE), "t", 100.0))
        self.conn.commit()
        svs = api.per_niva(self.conn)
        atg_rows = api.per_niva(self.conn, atg=True)
        self.assertEqual([1], [r["parade_omgangar"] for r in svs])
        self.assertEqual([1], [r["parade_omgangar"] for r in atg_rows])
        self.assertIn("per_niva_atg", api.pool(self.conn, now=CLOSE))


class FonsterTests(unittest.TestCase):
    def test_samma_fonster_som_svenska_spel(self):
        start, end = indata.window(CLOSE, "6h")
        self.assertEqual(CLOSE - dt.timedelta(hours=6), start)
        self.assertEqual(CLOSE - dt.timedelta(hours=5, minutes=30), end)


if __name__ == "__main__":
    unittest.main()
