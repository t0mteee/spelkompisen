"""Livekassan (fas E, 2026-10-03): agentens fiktiva livespel mot Svenska Spels liveodds.

Samans regler (designens avsnitt 7, beslut 3 i inkorgen 2026-10-03):
* fiktiv kassa 10 000 kr,
* 50–200 kr per spel, högst 3 spel och 600 kr per match,
* spärr vid 7 500 kr,
* Svenska Spels liveodds.

Koden lägger spelen i livevarvet. Agenten går igenom dem i morgonrundan, och
inga notiser skickas per spel. INGA riktiga spel läggs, aldrig.

Varv (`varv`, i spelai-tick; varje match högst en gång per `VARV_PER_MATCH_S`):
1. Pågående matcher: Svenska Spels livelista (ett anrop) snittad med Oddsets
   matcher som har kambi_id. Utan schemalagd match körs inga anrop alls.
2. Per match bokförs alla fulltidslinor för Ö/U ur Kambis liveflöde i
   `spelai_live_price`, både öppna och stängda, med observationstid efter
   anropet.
3. Agenten (`agent.live`, i sandbox utan nät, databasen mode=ro) får de nya
   priserna, Svenska Spels matchläge, matchens spel och kassan.
4. Facitsidan prövar varje föreslaget spel mot reglerna (`prova`) och bokför
   det i `spelai_live_bet`. Ett avvisat spel bokförs i journalen
   (`live_avvisat`) med skäl.

Rättning (`ratta`): ett spel rättas när matchens normaltidsresultat finns.
Resultatkällan och matchningen är desamma som i radarns signaljournal
(Flashscores färdigfeed, `oddset_data.merged_results`, `_result_for`), och
Asian-reglerna ger push och kvartslinor. `next_price_*` är nästa öppna
observerade pris på samma lina och tecken efter spelet: prisrörelsen, inte
facit.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from . import tillstand
from .tillstand import iso, utc

START_KR = 10_000.0
SPARR_KR = 7_500.0
MIN_INSATS_KR, MAX_INSATS_KR = 50.0, 200.0
MAX_SPEL_PER_MATCH = 3
MAX_INSATS_PER_MATCH_KR = 600.0
MAX_PRIS_ALDER_S = 60
VARV_PER_MATCH_S = 110            # radarns matchläge uppdateras var 2–3 min
MAX_MATCHER_PER_VARV = 12         # håller spelai-tick under minuten
AGENT_TIMEOUT_S = 20.0
SCHEMA_FORE = dt.timedelta(hours=3)        # avspark högst 3 h sedan ...
SCHEMA_EFTER = dt.timedelta(minutes=5)     # ... eller inom 5 min
RATTAS_EFTER = dt.timedelta(minutes=110)   # tidigast efter avspark
RESULTAT_SPARR = dt.timedelta(minutes=10)  # egen spärr för Flashscore-hämtningen
RESULTAT_NYCKEL = "spelai_live_resultat_at"
MARKNADER = frozenset({"ou"})
MOTIVERING_MAX = 400
TECKEN_TEXT = {"O": "över", "U": "under"}

Runner = Callable[[dict, float], object]   # sandbox.live_runner_for → AgentSvar


# ── kassa och spel ───────────────────────────────────────────────────────

def _spel(conn, where: str = "", params: tuple = ()) -> list[dict]:
    rows = conn.execute(
        "SELECT b.id, b.match_ref, b.minute, b.score, b.market, b.line, b.sign, b.odds, "
        "b.price_id, b.price_observed_at, b.stake_kr, b.model_version, b.motivation, "
        "b.placed_at, r.outcome, r.net_kr, r.settled_at, r.next_price_odds, "
        "r.next_price_observed_at FROM spelai_live_bet b "
        "LEFT JOIN spelai_live_result r ON r.bet_id = b.id " + where +
        " ORDER BY b.id", params).fetchall()
    keys = ("id", "match_ref", "minute", "score", "market", "line", "sign", "odds",
            "price_id", "price_observed_at", "stake_kr", "model_version", "motivation",
            "placed_at", "outcome", "net_kr", "settled_at", "next_price_odds",
            "next_price_observed_at")
    return [dict(zip(keys, row)) for row in rows]


def kassa(conn) -> dict:
    """Saldo = start + avgjort netto. Tillgängligt = saldo − insatser i öppna spel."""
    saldo = START_KR + float(conn.execute(
        "SELECT COALESCE(SUM(net_kr), 0) FROM spelai_live_result").fetchone()[0])
    i_spel = float(conn.execute(
        "SELECT COALESCE(SUM(b.stake_kr), 0) FROM spelai_live_bet b "
        "LEFT JOIN spelai_live_result r ON r.bet_id = b.id "
        "WHERE r.bet_id IS NULL").fetchone()[0])
    return {"start": START_KR, "sparr": SPARR_KR, "saldo": round(saldo, 2),
            "i_spel": round(i_spel, 2), "tillgangligt": round(saldo - i_spel, 2)}


def _match_for_ref(conn, match_ref: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, league, home, away, start FROM oddset_matches WHERE kambi_id=? "
        "ORDER BY start DESC LIMIT 1", (match_ref,)).fetchone()
    if row is None:
        return None
    return dict(zip(("id", "league", "home", "away", "start"), row))


def _schemalagda(conn, now: dt.datetime) -> list[dict]:
    """Oddsets matcher med Kambi-id som kan pågå nu (avspark inom fönstret)."""
    rows = conn.execute(
        "SELECT id, league, home, away, start, kambi_id FROM oddset_matches "
        "WHERE kambi_id IS NOT NULL AND start BETWEEN ? AND ?",
        (iso(now - SCHEMA_FORE), iso(now + SCHEMA_EFTER))).fetchall()
    return [dict(zip(("id", "league", "home", "away", "start", "kambi_id"), row))
            for row in rows]


def _senaste_pris_at(conn, match_ref: str) -> Optional[str]:
    row = conn.execute("SELECT MAX(fetched_at) FROM spelai_live_price WHERE match_ref=?",
                       (match_ref,)).fetchone()
    return row[0] if row else None


# ── priser ───────────────────────────────────────────────────────────────

def bokfor_priser(conn, match_ref: str, linor: list[dict], *,
                  fetched_at: dt.datetime, age_s: float = 0.0) -> list[dict]:
    """Varje lina och tecken som en rad, öppen eller stängd. Observationstid =
    hämtningstid − HTTP Age (CLAUDE.md, observationstidsregeln)."""
    observed = fetched_at - dt.timedelta(seconds=max(0.0, float(age_s or 0)))
    out = []
    for lina in linor:
        for sign in ("O", "U"):
            side = lina.get(sign) or {}
            if not side.get("odds"):
                continue
            cur = conn.execute(
                "INSERT INTO spelai_live_price (match_ref, market, line, sign, odds, "
                "market_open, observed_at, fetched_at, http_age_s, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (match_ref, "ou", float(lina["line"]), sign, float(side["odds"]),
                 int(bool(side.get("open"))), iso(observed), iso(fetched_at),
                 float(age_s or 0), "svenskaspel"))
            out.append({"price_id": cur.lastrowid, "market": "ou",
                        "line": float(lina["line"]), "sign": sign,
                        "odds": float(side["odds"]), "market_open": bool(side.get("open")),
                        "observed_at": iso(observed)})
    conn.commit()
    return out


# ── reglerna ─────────────────────────────────────────────────────────────

def prova(spel: dict, priser: dict, i_match: list[dict], kassa_nu: dict,
          now: dt.datetime) -> Optional[str]:
    """None = spelet följer reglerna, annars skälet att avvisa det."""
    try:
        pris = priser.get(int(spel.get("price_id")))
    except (TypeError, ValueError):
        return "price_id saknas"
    if pris is None:
        return "priset hör inte till varvet"
    if str(spel.get("market") or "").lower() not in MARKNADER:
        return "okänd marknad"
    try:
        line = float(spel.get("line"))
    except (TypeError, ValueError):
        return "linan saknas"
    sign = str(spel.get("sign") or "").upper()
    if abs(line - pris["line"]) > 1e-9 or sign != pris["sign"]:
        return "linan eller tecknet stämmer inte med priset"
    if not pris["market_open"]:
        return "marknaden var stängd"
    if not pris["odds"] or pris["odds"] <= 1.01:
        return "ogiltigt pris"
    alder = (now - utc(pris["observed_at"])).total_seconds()
    if alder > MAX_PRIS_ALDER_S or alder < -5:
        return f"priset är {int(alder)} s gammalt"
    try:
        stake = float(spel.get("stake_kr"))
    except (TypeError, ValueError):
        return "insatsen saknas"
    if not MIN_INSATS_KR <= stake <= MAX_INSATS_KR:
        return "insatsen ligger utanför 50–200 kr"
    if len(i_match) >= MAX_SPEL_PER_MATCH:
        return "redan 3 spel i matchen"
    if sum(float(b["stake_kr"]) for b in i_match) + stake > MAX_INSATS_PER_MATCH_KR:
        return "över 600 kr i matchen"
    if any(b["market"] == "ou" and abs(float(b["line"]) - line) < 1e-9
           and b["sign"] == sign for b in i_match):
        return "samma lina och tecken är redan spelade"
    if kassa_nu["tillgangligt"] - stake < SPARR_KR:
        return "spärren vid 7 500 kr"
    return None


def bokfor_spel(conn, match_ref: str, spel: dict, pris: dict, lage: dict,
                version: str, now: dt.datetime) -> int:
    score = (f"{lage['hemma_mal']}–{lage['borta_mal']}"
             if lage.get("hemma_mal") is not None and lage.get("borta_mal") is not None
             else None)
    motivering = " ".join(str(spel.get("motivering") or "").split())[:MOTIVERING_MAX]
    cur = conn.execute(
        "INSERT INTO spelai_live_bet (match_ref, minute, score, market, line, sign, odds, "
        "price_id, price_observed_at, stake_kr, model_version, motivation, placed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (match_ref, lage.get("minut"), score, "ou", pris["line"], pris["sign"],
         pris["odds"], pris["price_id"], pris["observed_at"], float(spel["stake_kr"]),
         version or None, motivering or None, iso(now)))
    conn.commit()
    tillstand.logga(conn, "live_spel", match_ref, {
        "bet_id": cur.lastrowid, "line": pris["line"], "sign": pris["sign"],
        "odds": pris["odds"], "stake_kr": float(spel["stake_kr"]), "version": version},
        now=now)
    return int(cur.lastrowid)


# ── ett varv ─────────────────────────────────────────────────────────────

def varv(store, *, runner: Optional[Runner], clock: Callable[[], dt.datetime],
         kambi_mod=None, interval_s: float = VARV_PER_MATCH_S) -> dict:
    """Priser och agentens spel för pågående matcher. `runner` None = avstängt."""
    if runner is None:
        return {}
    conn = store.conn
    if tillstand.pausad(conn):
        return {"pausad": True}
    now = clock()
    schemalagda = _schemalagda(conn, now)
    if not schemalagda:
        return {}
    if kambi_mod is None:
        from .. import kambi as kambi_mod
    try:
        lagen = kambi_mod.live_lagen(timeout=15.0)
    except Exception as exc:  # noqa: BLE001 — utan livelistan inga spel, nästa tick igen
        return {"fel": f"livelistan: {type(exc).__name__}"}
    lagen_at = clock()
    live = [m for m in schemalagda if str(m["kambi_id"]) in lagen]
    live.sort(key=lambda m: _senaste_pris_at(conn, str(m["kambi_id"])) or "")
    report = {"live": len(live), "matcher": 0, "priser": 0, "agent": 0,
              "spel": 0, "avvisade": 0}
    for match in live:
        if report["matcher"] >= MAX_MATCHER_PER_VARV:
            break
        ref = str(match["kambi_id"])
        senast = _senaste_pris_at(conn, ref)
        if senast and (clock() - utc(senast)).total_seconds() < interval_s:
            continue
        report["matcher"] += 1
        try:
            linor = kambi_mod.live_ou_lines(ref, timeout=8.0)
        except Exception as exc:  # noqa: BLE001 — ett matchfel stoppar inte de andra
            report.setdefault("prisfel", 0)
            report["prisfel"] += 1
            tillstand.logga(conn, "live_prisfel", ref, {"fel": type(exc).__name__},
                            now=clock(), dedup_key=f"live_prisfel:{ref}:{clock():%Y%m%d%H}")
            continue
        priser = bokfor_priser(conn, ref, linor, fetched_at=clock(),
                               age_s=getattr(kambi_mod, "last_age_s", 0) or 0)
        report["priser"] += len(priser)
        if not any(p["market_open"] for p in priser):
            continue
        i_match = _spel(conn, "WHERE b.match_ref=?", (ref,))
        kassa_nu = kassa(conn)
        if (len(i_match) >= MAX_SPEL_PER_MATCH
                or kassa_nu["tillgangligt"] - MIN_INSATS_KR < SPARR_KR):
            continue
        lage = dict(lagen.get(ref) or {})
        indata = {
            "nu": iso(clock()), "match_ref": ref,
            "lage": ({**lage, "observerad": iso(lagen_at)}
                     if lage.get("minut") is not None else None),
            "priser": priser,
            "lagda_spel": [{"market": b["market"], "line": b["line"], "sign": b["sign"],
                            "stake_kr": b["stake_kr"]} for b in i_match],
            "kassa_kr": kassa_nu["tillgangligt"]}
        svar = runner(indata, AGENT_TIMEOUT_S)
        report["agent"] += 1
        if getattr(svar, "status", None) != "ok" or not isinstance(svar.data, dict):
            report.setdefault("agentfel", 0)
            report["agentfel"] += 1
            tillstand.logga(conn, "live_agentfel", ref,
                            {"status": getattr(svar, "status", None),
                             "skal": getattr(svar, "reason", None)},
                            now=clock(), dedup_key=f"live_agentfel:{ref}:{clock():%Y%m%d%H}")
            continue
        forslag = svar.data.get("spel")
        if not isinstance(forslag, list) or not forslag:
            continue
        version = str(svar.data.get("version") or "")[:40]
        by_id = {p["price_id"]: p for p in priser}
        for spel in forslag[:MAX_SPEL_PER_MATCH]:
            if not isinstance(spel, dict):
                continue
            now_spel = clock()
            skal = prova(spel, by_id, i_match, kassa(conn), now_spel)
            if skal:
                report["avvisade"] += 1
                tillstand.logga(conn, "live_avvisat", ref, {
                    "skal": skal, "version": version,
                    "spel": {k: spel.get(k) for k in
                             ("price_id", "market", "line", "sign", "stake_kr")}},
                    now=now_spel)
                continue
            bokfor_spel(conn, ref, spel, by_id[int(spel["price_id"])], lage,
                        version, now_spel)
            report["spel"] += 1
            i_match = _spel(conn, "WHERE b.match_ref=?", (ref,))
    return report


# ── rättning ─────────────────────────────────────────────────────────────

def ou_utfall(total: int, line: float, sign: str, odds: float,
              stake: float) -> tuple[str, float]:
    """Asian Ö/U: hela linor kan bli push, kvartslinor delas på två halvor."""
    quarter = abs(line * 2 - round(line * 2)) > 1e-9
    halves = (line - 0.25, line + 0.25) if quarter else (line,)
    per_kr = []
    for half in halves:
        diff = (total - half) if sign == "O" else (half - total)
        if diff > 1e-9:
            per_kr.append(odds - 1.0)
        elif abs(diff) <= 1e-9:
            per_kr.append(0.0)
        else:
            per_kr.append(-1.0)
    profit = sum(per_kr) / len(per_kr)
    if abs(profit - (odds - 1.0)) < 1e-9:
        utfall = "vinst"
    elif profit > 1e-9:
        utfall = "halv_vinst"
    elif abs(profit) <= 1e-9:
        utfall = "push"
    elif profit > -1.0 + 1e-9:
        utfall = "halv_forlust"
    else:
        utfall = "forlust"
    return utfall, round(stake * profit, 2)


def _nasta_pris(conn, bet: dict) -> tuple[Optional[float], Optional[str]]:
    row = conn.execute(
        "SELECT odds, observed_at FROM spelai_live_price WHERE match_ref=? AND market=? "
        "AND line=? AND sign=? AND market_open=1 AND observed_at > ? "
        "ORDER BY observed_at, id LIMIT 1",
        (bet["match_ref"], bet["market"], bet["line"], bet["sign"],
         bet["price_observed_at"])).fetchone()
    return (row[0], row[1]) if row else (None, None)


def hamta_resultat(store, matcher: list[dict], now: dt.datetime) -> dict:
    """Flashscores färdigfeed för livespelens matcher, högst var tionde minut.

    Samma väg som radarns signaljournal (`refresh_recent_results`), med egen
    spärr: journalens spärr är gemensam för ITS signaler och hade annars kunnat
    hoppa över just livespelens matcher."""
    senast = utc(store.meta_get(RESULTAT_NYCKEL) or "")
    if senast is not None and now - senast < RESULTAT_SPARR:
        return {"status": "sparr"}
    from .. import flashscore_data
    signals = [{"match_key": f"spelai-live:{m['id']}", "league": m["league"],
                "home": m["home"], "away": m["away"], "start_at": m["start"]}
               for m in matcher]
    try:
        report = flashscore_data.refresh_recent_results(store, signals, now=now,
                                                        force=True)
    finally:
        store.meta_set(RESULTAT_NYCKEL, iso(now))
    return report


def _resultat(store, match: dict) -> Optional[dict]:
    from .. import oddset_data
    from ..live_signal_ledger import _result_for
    results = oddset_data.merged_results(store, match["league"])
    found = _result_for({"start_at": match["start"], "captured_at": match["start"],
                         "home": match["home"], "away": match["away"]}, results)
    return found[0] if found else None


def ratta(store, *, now: dt.datetime,
          resultat_kalla: Callable = hamta_resultat) -> dict:
    """Rätta öppna livespel vars match har ett normaltidsresultat."""
    conn = store.conn
    oppna = _spel(conn, "WHERE r.bet_id IS NULL")
    if not oppna:
        return {}
    per_match: dict[str, list[dict]] = {}
    for bet in oppna:
        per_match.setdefault(bet["match_ref"], []).append(bet)
    klara = {}
    for ref in per_match:
        match = _match_for_ref(conn, ref)
        if match and utc(match["start"]) and utc(match["start"]) + RATTAS_EFTER <= now:
            klara[ref] = match
    report = {"oppna": len(oppna), "rattade": 0, "vantar": 0}
    if not klara:
        return report
    resultat_kalla(store, list(klara.values()), now)
    for ref, match in klara.items():
        result = _resultat(store, match)
        if result is None:
            report["vantar"] += len(per_match[ref])
            continue
        total = int(result["hg"]) + int(result["ag"])
        for bet in per_match[ref]:
            utfall, netto = ou_utfall(total, float(bet["line"]), bet["sign"],
                                      float(bet["odds"]), float(bet["stake_kr"]))
            nasta_odds, nasta_at = _nasta_pris(conn, bet)
            conn.execute(
                "INSERT OR IGNORE INTO spelai_live_result (bet_id, outcome, net_kr, "
                "settled_at, next_price_odds, next_price_observed_at) VALUES (?,?,?,?,?,?)",
                (bet["id"], utfall, netto, iso(now), nasta_odds, nasta_at))
            report["rattade"] += 1
        conn.commit()
        tillstand.logga(conn, "live_rattat", ref, {
            "mal": f"{result['hg']}–{result['ag']}", "spel": len(per_match[ref])},
            now=now, dedup_key=f"live_rattat:{ref}")
    return report


# ── API ──────────────────────────────────────────────────────────────────

def _visning(bet: dict, namn: dict) -> dict:
    out = {"id": bet["id"], "match_ref": bet["match_ref"],
           "match": namn.get(bet["match_ref"]) or bet["match_ref"],
           "minut": bet["minute"], "stallning": bet["score"],
           "market": bet["market"], "marknad": "Ö/U" if bet["market"] == "ou" else bet["market"],
           "line": bet["line"], "lina": bet["line"], "sign": bet["sign"],
           "tecken": TECKEN_TEXT.get(bet["sign"], bet["sign"]), "odds": bet["odds"],
           "insats": bet["stake_kr"], "stake_kr": bet["stake_kr"],
           "motivering": bet["motivation"], "version": bet["model_version"],
           "lagd": bet["placed_at"]}
    if bet["outcome"] is not None:
        out.update({"utfall": bet["outcome"], "netto": bet["net_kr"],
                    "net_kr": bet["net_kr"], "avgjord": bet["settled_at"],
                    "nasta_odds": bet["next_price_odds"]})
    return out


def payload(conn, *, now: dt.datetime) -> dict:
    alla = _spel(conn)
    refs = sorted({b["match_ref"] for b in alla})
    namn = {}
    for ref in refs:
        match = _match_for_ref(conn, ref)
        if match:
            namn[ref] = f"{match['home']} – {match['away']}"
    oppna = [_visning(b, namn) for b in alla if b["outcome"] is None]
    avgjorda_rader = sorted((b for b in alla if b["outcome"] is not None),
                            key=lambda b: (b["settled_at"], b["id"]))
    graf, saldo = [{"saldo": START_KR, "tid": None}], START_KR
    for bet in avgjorda_rader:
        saldo += float(bet["net_kr"])
        graf.append({"saldo": round(saldo, 2), "tid": bet["settled_at"]})
    per_marknad: dict[str, dict] = {}
    for bet in avgjorda_rader:
        rad = per_marknad.setdefault(bet["market"], {"marknad": "Ö/U" if bet["market"] == "ou"
                                                     else bet["market"],
                                                     "spel": 0, "insats": 0.0, "netto": 0.0})
        rad["spel"] += 1
        rad["insats"] += float(bet["stake_kr"])
        rad["netto"] += float(bet["net_kr"])
    for rad in per_marknad.values():
        rad["roi"] = round(rad["netto"] / rad["insats"], 4) if rad["insats"] else None
        rad["insats"], rad["netto"] = round(rad["insats"], 2), round(rad["netto"], 2)
    return {"kassa": kassa(conn), "graf": graf, "oppna": oppna,
            "avgjorda": [_visning(b, namn) for b in reversed(avgjorda_rader)][:50],
            "per_marknad": list(per_marknad.values()),
            "regler": {"start_kr": START_KR, "sparr_kr": SPARR_KR,
                       "insats_kr": [MIN_INSATS_KR, MAX_INSATS_KR],
                       "max_spel_per_match": MAX_SPEL_PER_MATCH,
                       "max_insats_per_match_kr": MAX_INSATS_PER_MATCH_KR,
                       "max_prisalder_s": MAX_PRIS_ALDER_S},
            "genererad": iso(now)}
