"""Livekassan (fas E): priser, regler, agentens spel, rättning och API-svaret."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spelai_fixtur import START, ny_store  # noqa: E402
from app import kambi, live_signal_ledger  # noqa: E402
from app.spelai import livekassa, sandbox, schemalaggare, tillstand  # noqa: E402
from app.spelai.sandbox import AgentSvar  # noqa: E402

UTC = dt.timezone.utc
NU = dt.datetime(2026, 10, 3, 17, 30, tzinfo=UTC)
AVSPARK = NU - dt.timedelta(minutes=60)
REF = "9001"


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Klocka:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def fram(self, **kw):
        self.t += dt.timedelta(**kw)


class FejkKambi:
    last_age_s = 0

    def __init__(self, lagen=None, linor=None):
        self.lagen = lagen if lagen is not None else {
            REF: {"minut": 60, "period": "SECOND_HALF", "hemma_mal": 1, "borta_mal": 0}}
        self.linor = linor if linor is not None else [
            {"line": 2.5, "main": True,
             "O": {"odds": 2.10, "open": True}, "U": {"odds": 1.70, "open": True}},
            {"line": 1.5, "main": False,
             "O": {"odds": 1.30, "open": False}, "U": {"odds": 3.20, "open": False}}]
        self.anrop = []

    def live_lagen(self, timeout=15.0):
        self.anrop.append("lagen")
        return self.lagen

    def live_ou_lines(self, ref, timeout=8.0):
        self.anrop.append(("linor", ref))
        return self.linor


class FejkAgent:
    def __init__(self, svar=None):
        self.svar = svar
        self.indata = []

    def __call__(self, indata, timeout):
        self.indata.append(indata)
        if callable(self.svar):
            return self.svar(indata)
        return self.svar or AgentSvar("ok", data={
            "version": "live-ou-v0", "spel": [], "avstar": "inget värde"})


def spela(line=2.5, sign="O", stake=50):
    def svar(indata):
        pris = next(p for p in indata["priser"] if p["line"] == line and p["sign"] == sign)
        return AgentSvar("ok", data={"version": "live-ou-v0", "avstar": None, "spel": [{
            "price_id": pris["price_id"], "market": "ou", "line": line, "sign": sign,
            "stake_kr": stake, "motivering": "test"}]})
    return svar


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ny_store(self.tmp, start=START)
        self.conn = self.store.conn
        self.store.oddset_upsert_match({
            "id": f"svs:{REF}", "league": "nations_league", "home": "Kroatien",
            "away": "England", "start": iso(AVSPARK), "kambi_id": REF})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def bets(self):
        return livekassa._spel(self.conn)  # noqa: SLF001

    def events(self, kind):
        return self.conn.execute("SELECT ref, detail_json FROM spelai_event WHERE kind=?",
                                 (kind,)).fetchall()

    def lagg_in(self, *, stake=50.0, net=None, line=2.5, sign="O", ref=REF):
        cur = self.conn.execute(
            "INSERT INTO spelai_live_bet (match_ref, market, line, sign, odds, "
            "price_observed_at, stake_kr, placed_at) VALUES (?,?,?,?,?,?,?,?)",
            (ref, "ou", line, sign, 2.0, iso(NU), stake, iso(NU)))
        if net is not None:
            self.conn.execute(
                "INSERT INTO spelai_live_result (bet_id, outcome, net_kr, settled_at) "
                "VALUES (?,?,?,?)", (cur.lastrowid, "forlust" if net < 0 else "vinst",
                                     net, iso(NU)))
        self.conn.commit()


class VarvTests(Base):
    def test_bokfor_priser_och_agentens_spel(self):
        kambi_f, agent, klocka = FejkKambi(), FejkAgent(spela()), Klocka(NU)
        rep = livekassa.varv(self.store, runner=agent, clock=klocka, kambi_mod=kambi_f)
        self.assertEqual((1, 1, 4, 1, 1, 0),
                         (rep["live"], rep["matcher"], rep["priser"], rep["agent"],
                          rep["spel"], rep["avvisade"]))
        indata = agent.indata[0]
        self.assertEqual(REF, indata["match_ref"])
        self.assertEqual((60, 1, 0), (indata["lage"]["minut"], indata["lage"]["hemma_mal"],
                                      indata["lage"]["borta_mal"]))
        self.assertEqual(10_000.0, indata["kassa_kr"])
        self.assertEqual([], indata["lagda_spel"])
        self.assertEqual({True, False}, {p["market_open"] for p in indata["priser"]})
        bet = self.bets()[0]
        self.assertEqual((2.5, "O", 2.10, 50.0, 60, "1–0", "live-ou-v0"),
                         (bet["line"], bet["sign"], bet["odds"], bet["stake_kr"],
                          bet["minute"], bet["score"], bet["model_version"]))
        self.assertEqual(iso(NU), bet["price_observed_at"])
        self.assertEqual(4, self.conn.execute(
            "SELECT COUNT(*) FROM spelai_live_price").fetchone()[0])
        self.assertEqual(1, len(self.events("live_spel")))

    def test_samma_match_hamtas_inte_igen_inom_intervallet(self):
        kambi_f, klocka = FejkKambi(), Klocka(NU)
        livekassa.varv(self.store, runner=FejkAgent(), clock=klocka, kambi_mod=kambi_f)
        klocka.fram(seconds=30)
        rep = livekassa.varv(self.store, runner=FejkAgent(), clock=klocka, kambi_mod=kambi_f)
        self.assertEqual(0, rep["matcher"])
        klocka.fram(seconds=120)
        rep = livekassa.varv(self.store, runner=FejkAgent(), clock=klocka, kambi_mod=kambi_f)
        self.assertEqual(1, rep["matcher"])
        self.assertEqual(2, sum(1 for a in kambi_f.anrop if a != "lagen"))

    def test_utan_schemalagd_match_inga_anrop_och_av_utan_runner(self):
        kambi_f = FejkKambi()
        senare = Klocka(NU + dt.timedelta(days=2))
        self.assertEqual({}, livekassa.varv(self.store, runner=FejkAgent(), clock=senare,
                                            kambi_mod=kambi_f))
        self.assertEqual({}, livekassa.varv(self.store, runner=None, clock=Klocka(NU),
                                            kambi_mod=kambi_f))
        self.assertEqual([], kambi_f.anrop)

    def test_pausad_lagger_inga_spel(self):
        tillstand.satt_paus(self.conn, True, source="test", now=NU)
        kambi_f = FejkKambi()
        rep = livekassa.varv(self.store, runner=FejkAgent(spela()), clock=Klocka(NU),
                             kambi_mod=kambi_f)
        self.assertEqual({"pausad": True}, rep)
        self.assertEqual([], kambi_f.anrop)

    def test_stangda_marknader_kor_inte_agenten(self):
        linor = [{"line": 2.5, "main": True, "O": {"odds": 2.0, "open": False},
                  "U": {"odds": 1.8, "open": False}}]
        agent = FejkAgent(spela())
        rep = livekassa.varv(self.store, runner=agent, clock=Klocka(NU),
                             kambi_mod=FejkKambi(linor=linor))
        self.assertEqual((2, 0), (rep["priser"], rep["agent"]))
        self.assertEqual([], agent.indata)

    def test_avvisat_spel_bokfors_i_journalen(self):
        rep = livekassa.varv(self.store, runner=FejkAgent(spela(stake=500)), clock=Klocka(NU),
                             kambi_mod=FejkKambi())
        self.assertEqual((0, 1), (rep["spel"], rep["avvisade"]))
        self.assertEqual([], self.bets())
        self.assertIn("50–200", self.events("live_avvisat")[0][1])

    def test_agentfel_bokfors_en_gang_per_timme(self):
        agent, klocka = FejkAgent(AgentSvar("fel", reason="timeout efter 20 s")), Klocka(NU)
        livekassa.varv(self.store, runner=agent, clock=klocka, kambi_mod=FejkKambi())
        klocka.fram(seconds=150)
        livekassa.varv(self.store, runner=agent, clock=klocka, kambi_mod=FejkKambi())
        self.assertEqual(2, len(agent.indata))
        self.assertEqual(1, len(self.events("live_agentfel")))

    def test_sparren_stoppar_agenten(self):
        self.lagg_in(stake=200, net=-2_480, ref="annan")    # saldo 7 520 kr
        agent = FejkAgent(spela())
        rep = livekassa.varv(self.store, runner=agent, clock=Klocka(NU), kambi_mod=FejkKambi())
        self.assertEqual(0, rep["agent"])
        self.assertEqual([], agent.indata)


class ReglerTests(Base):
    def setUp(self):
        super().setUp()
        self.pris = {7: {"price_id": 7, "market": "ou", "line": 2.5, "sign": "O",
                         "odds": 2.1, "market_open": True, "observed_at": iso(NU)}}
        self.kassa = {"tillgangligt": 10_000.0}

    def prova(self, spel=None, i_match=(), kassa_nu=None, now=NU, pris=None):
        base = {"price_id": 7, "market": "ou", "line": 2.5, "sign": "O", "stake_kr": 50}
        return livekassa.prova({**base, **(spel or {})}, pris or self.pris, list(i_match),
                               kassa_nu or self.kassa, now)

    def bet(self, stake=50.0, line=2.5, sign="U"):
        return {"market": "ou", "line": line, "sign": sign, "stake_kr": stake}

    def test_giltigt_spel(self):
        self.assertIsNone(self.prova())
        self.assertIsNone(self.prova({"stake_kr": 200}))

    def test_varje_regel_avvisar(self):
        fall = {
            "insatsen ligger utanför 50–200 kr": [{"stake_kr": 40}, {"stake_kr": 250}],
            "priset hör inte till varvet": [{"price_id": 8}],
            "price_id saknas": [{"price_id": None}],
            "linan eller tecknet stämmer inte med priset": [{"line": 3.5}, {"sign": "U"}],
            "okänd marknad": [{"market": "1x2"}],
        }
        for skal, varianter in fall.items():
            for spel in varianter:
                self.assertEqual(skal, self.prova(spel), spel)
        stangd = {7: {**self.pris[7], "market_open": False}}
        self.assertEqual("marknaden var stängd", self.prova(pris=stangd))
        self.assertEqual("priset är 61 s gammalt",
                         self.prova(now=NU + dt.timedelta(seconds=61)))
        self.assertEqual("redan 3 spel i matchen",
                         self.prova(i_match=[self.bet(line=x) for x in (0.5, 1.5, 3.5)]))
        self.assertEqual("över 600 kr i matchen",
                         self.prova({"stake_kr": 200},
                                    i_match=[self.bet(200, 0.5), self.bet(250, 1.5)]))
        self.assertEqual("samma lina och tecken är redan spelade",
                         self.prova(i_match=[self.bet(sign="O")]))
        self.assertEqual("spärren vid 7 500 kr",
                         self.prova(kassa_nu={"tillgangligt": 7_540.0}))


class RattningTests(Base):
    GRID_LINES = (0.5, 1.0, 1.25, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0)

    def test_asian_utfall_for_over_och_under(self):
        fall = [((3, 2.5, "O"), ("vinst", 50.0)), ((2, 2.5, "O"), ("forlust", -50.0)),
                ((2, 2.0, "O"), ("push", 0.0)), ((2, 2.25, "O"), ("halv_forlust", -25.0)),
                ((3, 2.75, "O"), ("halv_vinst", 25.0)), ((2, 2.5, "U"), ("vinst", 50.0)),
                ((2, 2.25, "U"), ("halv_vinst", 25.0)), ((3, 2.75, "U"), ("halv_forlust", -25.0))]
        for (total, line, sign), forvantat in fall:
            self.assertEqual(forvantat, livekassa.ou_utfall(total, line, sign, 2.0, 50.0),
                             (total, line, sign))

    def test_over_rattas_exakt_som_radarns_signaljournal(self):
        etiketter = {"win": "vinst", "half_win": "halv_vinst", "push": "push",
                     "half_loss": "halv_forlust", "loss": "forlust"}
        for total in range(0, 7):
            for line in self.GRID_LINES:
                label, per_kr = live_signal_ledger._over_profit(total, line, 1.9)  # noqa: SLF001
                utfall, netto = livekassa.ou_utfall(total, line, "O", 1.9, 100.0)
                self.assertEqual((etiketter[label], round(per_kr * 100, 2)), (utfall, netto))

    def rattat_spel(self):
        klocka = Klocka(NU)
        livekassa.varv(self.store, runner=FejkAgent(spela()), clock=klocka,
                       kambi_mod=FejkKambi())
        klocka.fram(seconds=120)
        senare = [{"line": 2.5, "main": True, "O": {"odds": 1.95, "open": True},
                   "U": {"odds": 1.85, "open": True}}]
        livekassa.varv(self.store, runner=FejkAgent(), clock=klocka,
                       kambi_mod=FejkKambi(linor=senare))
        return klocka

    def test_rattar_med_resultat_och_nasta_pris_en_gang(self):
        self.rattat_spel()
        efter = AVSPARK + dt.timedelta(hours=2)
        hamtat = []
        with patch.object(livekassa, "_resultat", return_value={"hg": 2, "ag": 1}):
            rep = livekassa.ratta(self.store, now=efter,
                                  resultat_kalla=lambda s, m, n: hamtat.append(m))
            self.assertEqual((1, 1, 0), (rep["oppna"], rep["rattade"], rep["vantar"]))
            self.assertEqual({}, livekassa.ratta(self.store, now=efter,
                                                 resultat_kalla=lambda s, m, n: None))
        bet = self.bets()[0]
        self.assertEqual(("vinst", 55.0, 1.95), (bet["outcome"], bet["net_kr"],
                                                 bet["next_price_odds"]))
        self.assertEqual("Kroatien", hamtat[0][0]["home"])
        self.assertEqual(1, len(self.events("live_rattat")))

    def test_vantar_utan_resultat_och_fore_slutet(self):
        self.rattat_spel()
        kallat = []
        tidigt = livekassa.ratta(self.store, now=AVSPARK + dt.timedelta(minutes=60),
                                 resultat_kalla=lambda s, m, n: kallat.append(m))
        self.assertEqual((1, 0), (tidigt["oppna"], tidigt["rattade"]))
        self.assertEqual([], kallat)
        with patch.object(livekassa, "_resultat", return_value=None):
            rep = livekassa.ratta(self.store, now=AVSPARK + dt.timedelta(hours=2),
                                  resultat_kalla=lambda s, m, n: None)
        self.assertEqual((0, 1), (rep["rattade"], rep["vantar"]))

    def test_resultathamtningen_har_egen_sparr(self):
        matcher = [{"id": "svs:9001", "league": "nations_league", "home": "Kroatien",
                    "away": "England", "start": iso(AVSPARK)}]
        with patch("app.flashscore_data.refresh_recent_results",
                   return_value={"saved": 1}) as refresh:
            livekassa.hamta_resultat(self.store, matcher, NU)
            self.assertEqual({"status": "sparr"},
                             livekassa.hamta_resultat(self.store, matcher,
                                                      NU + dt.timedelta(minutes=5)))
            livekassa.hamta_resultat(self.store, matcher, NU + dt.timedelta(minutes=11))
        self.assertEqual(2, refresh.call_count)
        signal = refresh.call_args.args[1][0]
        self.assertEqual(("nations_league", "Kroatien", iso(AVSPARK)),
                         (signal["league"], signal["home"], signal["start_at"]))
        self.assertTrue(refresh.call_args.kwargs["force"])


class PayloadTests(Base):
    def test_kassa_graf_spel_och_marknader(self):
        self.lagg_in(stake=50.0, net=55.0)
        self.lagg_in(stake=100.0, line=1.5, sign="U")
        data = livekassa.payload(self.conn, now=NU)
        self.assertEqual({"start": 10_000.0, "sparr": 7_500.0, "saldo": 10_055.0,
                          "i_spel": 100.0, "tillgangligt": 9_955.0}, data["kassa"])
        self.assertEqual([10_000.0, 10_055.0], [p["saldo"] for p in data["graf"]])
        oppet = data["oppna"][0]
        self.assertEqual(("Kroatien – England", "Ö/U", 1.5, "under", 100.0),
                         (oppet["match"], oppet["marknad"], oppet["lina"], oppet["tecken"],
                          oppet["insats"]))
        self.assertEqual(("vinst", 55.0), (data["avgjorda"][0]["utfall"],
                                           data["avgjorda"][0]["netto"]))
        self.assertEqual([{"marknad": "Ö/U", "spel": 1, "insats": 50.0, "netto": 55.0,
                           "roi": 1.1}], data["per_marknad"])
        self.assertEqual(3, data["regler"]["max_spel_per_match"])


class KambiTests(unittest.TestCase):
    class Svar:
        def __init__(self, payload):
            self.payload, self.headers, self.status_code = payload, {}, 200

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def offer(self, line, over, under, *, tags=("OFFERED_LIVE", "MAIN_LINE"),
              lifetime="FULL_TIME", suspended=None, status=("OPEN", "OPEN"),
              label="Antal mål"):
        return {"criterion": {"label": label, "lifetime": lifetime},
                "tags": list(tags), "suspended": suspended, "outcomes": [
                    {"type": "OT_OVER", "line": line, "odds": over, "status": status[0]},
                    {"type": "OT_UNDER", "line": line, "odds": under, "status": status[1]}]}

    def test_alla_fulltidslinor_oppna_och_stangda(self):
        payload = {"betOffers": [
            self.offer(1500, 1450, 2400),
            self.offer(2500, 2430, 1450, tags=("OFFERED_LIVE",), suspended=True),
            self.offer(3500, 4000, 1200, status=("OPEN", "SUSPENDED"), tags=("OFFERED_LIVE",)),
            self.offer(3000, 3000, 1300, tags=("OFFERED_PREMATCH",)),
            self.offer(500, 1100, 6000, lifetime="FIRST_HALF")]}
        with patch.object(kambi.httpx, "get", return_value=self.Svar(payload)):
            linor = kambi.live_ou_lines("9001")
        by_line = {lina["line"]: lina for lina in linor}
        self.assertEqual([1.5, 2.5, 3.5], sorted(by_line))
        self.assertEqual(({"odds": 1.45, "open": True}, True),
                         (by_line[1.5]["O"], by_line[1.5]["main"]))
        self.assertFalse(by_line[2.5]["O"]["open"])
        self.assertTrue(by_line[3.5]["O"]["open"])
        self.assertFalse(by_line[3.5]["U"]["open"])

    def test_livelistan_ger_bara_fotboll_med_svenska_spels_lage(self):
        payload = {"liveEvents": [
            {"event": {"id": 1, "sport": "FOOTBALL"},
             "liveData": {"matchClock": {"minute": 63, "periodId": "SECOND_HALF"},
                          "score": {"home": "1", "away": "0"}}},
            {"event": {"id": 2, "sport": "TENNIS"}, "liveData": {}},
            {"event": {"id": 3, "sport": "FOOTBALL"}}]}
        with patch.object(kambi.httpx, "get", return_value=self.Svar(payload)):
            lagen = kambi.live_lagen()
        self.assertEqual({"1", "3"}, set(lagen))
        self.assertEqual({"minut": 63, "period": "SECOND_HALF", "hemma_mal": 1,
                          "borta_mal": 0}, lagen["1"])
        self.assertIsNone(lagen["3"]["minut"])


class KopplingTests(unittest.TestCase):
    def test_agent_live_kors_i_samma_sandbox_utan_nivaer(self):
        cfg = sandbox.AgentConfig(db_path=Path("/d/s.db"), agent_dir=Path("/a"),
                                  python=Path("/a/py"), data_dir=Path("/x"),
                                  profile=Path("/p.sb"))
        cmd = sandbox.command(cfg, Path("/t/in.json"), None, "agent.live")
        self.assertEqual(["-m", "agent.live", "--indata", "/t/in.json"],
                         cmd[cmd.index("-m"):])
        self.assertIn("--nivaer", sandbox.command(cfg, Path("/t/in.json"), [256]))
        with self.assertRaises(ValueError):
            sandbox.command(cfg, Path("/t/in.json"), None, "agent.annat")

    def test_schemalaggaren_har_livestegen_fore_chatten(self):
        steg = schemalaggare.STEG
        self.assertLess(steg.index("livespel"), steg.index("liverattning"))
        self.assertEqual("chatt", steg[-1])


if __name__ == "__main__":
    unittest.main()
