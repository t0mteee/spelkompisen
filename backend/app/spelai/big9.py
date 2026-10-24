"""Big 9 (ATG) på facitsidan: indatapaket, standard, rättning och missat.

Beslut driften-2026-10-24-big9-atg (val 0). Sedan beslut 2026-10-24-sp96-ar-big9
(val 0) är det SP96 (nya Big 9: utan Wild Card, 6–9 rätt, uttag 25 %) som mäts;
gamla BIG9 samlas bara in (`atg.MEASURED`). Samma flöde som Svenska Spels
poolspel (indata → frysning → rättning), men med ATG:s omgång som underlag:

* Paketet sparas i `spelai_input` när ATG-insamlingen (`app/atg.py`) läser en
  `SELL_OPEN`-omgång inne i ett horisontfönster (6h [T−6h, T−5h30], 30m
  [T−35, T−30]); samma fönster och frister som `indata`. `draw_number` =
  ATG:s `serialNumber`, `reg_close_time` = `startTime`. Ospelade matchers
  platshållarresultat (`result`/`score`/`liveData`) tas bort ur paketet.
* Nivå: 256 kr = 512 rader à 0,50 kr. Format `rows`, nio tokens per rad
  (`nivaer.atg_symboler`): i SP96 bara cellerna, i BIG9 exakt ett Wild Card.
* Standard: `big9_builder.build_rows`, strategi medel, budgeten = nivån, en
  `config_key` per spelform (`STANDARD_KEYS`). Återbetalningsandelen läses ur
  omgångens publicerade potter (`payout_ratio`), annars 1 − uttag.
* Rättning: ATG:s FINALIZED-post. En match räknas bara med `status DECIDED`;
  struken match (`CANCELED`/`canceledAt`) är rätt för alla; Wild Card är rätt.
  Utdelning per egen vinnande rad = potten / (publicerade vinnande enheter +
  våra), nedåt till hela kronor, 0 under minimiutdelningen — samma regel som
  ATG:s publicerade belopp (ommätt mot 101 omgångar, noll avvikelser). En
  grupp utan vinnare har ändå sin pott publicerad, så facit blir komplett.
* Missat: bara fönster som öppnade efter `facit_start_big9` (skrivs av
  scripts/migrera_atg.py) räknas — de 101 gamla omgångarna är inga missar.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import statistics
from typing import Optional

from .. import atg, big9_builder
from . import indata, nivaer, schema, tillstand
from .tillstand import iso, utc

SCHEMA_VERSION = "spelai-indata-big9-v2"
SETTLEMENT_VERSION = "spelai-big9-v1"
# En nyckel per spelform: SP96 och BIG9 har olika regler och mäts aldrig ihop.
STANDARD_KEYS = {"big9": {256: "big9-varderader-v1-b256-medel"},
                 "sp96": {256: "big9-varderader-v1-sp96-b256-medel"}}
# Potterna för de lägre vinstgrupperna får skilja högst så mycket i
# återbetalningsandel för att andelen ska läsas ur potterna.
RATIO_TOLERANCE = 0.005
START_KEY = "facit_start_big9"
TURNOVER_N = 8
CANCELLED_NOTE = "omgången ställdes in (ATG CANCELED)"
UNRESOLVABLE_NOTE = "utfall saknas för minst en match"
_STRIP_MATCH = ("result", "score", "liveData")


def galler(product: str) -> bool:
    return product in atg.MEASURED


def standard_key(product: str, level) -> Optional[str]:
    return STANDARD_KEYS.get(product, {}).get(int(level))


def payout_ratio(record: dict, product: str) -> tuple[float, str]:
    """Återbetalningsandel (andel av omsättningen) för vinstpotterna.

    Ur omgångens publicerade potter för de LÄGRE vinstgrupperna (toppgruppen
    bär jackpoten): pott / (omsättning × andel), när alla grupper ger samma
    andel inom `RATIO_TOLERANCE` och den inte överstiger 1 − uttag. Annars
    1 − uttag. SP96 omgång 517: 72,75 % mot uttagets 75 %; BIG9: 65 % = uttaget."""
    cfg = atg.PRODUCTS[product]
    nominal = 1.0 - float(record.get("takeoutPercentage") or 0) / 100.0
    pool = record.get("pool") or {}
    turnover = float(pool.get("turnover") or 0)
    payouts = pool.get("payouts") or {}
    top = max(cfg["splits"])
    estimates = []
    for k, share in cfg["splits"].items():
        pot = (payouts.get(str(k)) or {}).get("pot")
        if k == top or not isinstance(pot, (int, float)) or pot <= 0:
            continue
        if turnover > 0:
            estimates.append(pot / (turnover * share))
    if (estimates and max(estimates) - min(estimates) <= RATIO_TOLERANCE
            and statistics.fmean(estimates) <= nominal + RATIO_TOLERANCE):
        return min(statistics.fmean(estimates), nominal), "atg_potter"
    return nominal, "uttag"


# ── indatapaketet ────────────────────────────────────────────────────────

def _match_payload(m: dict) -> dict:
    odds = m.get("odds") or {}
    return {
        "event_number": int(m.get("number")),
        "id": m.get("id"),
        "home": ((m.get("homeTeam") or {}).get("name")),
        "away": ((m.get("awayTeam") or {}).get("name")),
        "league": ((m.get("championship") or {}).get("name")),
        "start": m.get("startTime"),
        "status": m.get("status"),
        "cancelled": bool(m.get("canceledAt")) or m.get("status") == "CANCELED",
        "odds": {k: odds.get(k) for k in ("home", "tie", "away", "over", "under")},
        "odds_source": odds.get("source"),
        "odds_updated": odds.get("lastUpdated"),
        "streck": m.get("betDistribution"),
        "kambi_id": (m.get("kambi") or {}).get("eventId"),
        "sportradar_id": (m.get("sportradar") or {}).get("eventId"),
    }


def _turnover(conn, product: str, live: float, close: dt.datetime) -> dict:
    finals = atg.final_turnovers(conn, product, close, TURNOVER_N)
    projected = statistics.median(finals) if finals else None
    used = max(live, projected or 0.0)
    basis = (f"max(live, median av {len(finals)} senaste slutomsättningar)"
             if finals else "live (ingen avslutad omgång observerad)")
    return {"live": live, "projected": projected, "used": used, "basis": basis,
            "n_final": len(finals)}


def build_payload(conn, product: str, obs: dict, horizon: str,
                  now: dt.datetime) -> dict:
    record = obs["record"]
    cfg = atg.PRODUCTS[product]
    close = obs["start"]
    pool = record.get("pool") or {}
    live = float(pool.get("turnover") or 0) / 100.0
    ratio, ratio_source = payout_ratio(record, product)
    payouts = pool.get("payouts") or {}
    top = max(cfg["splits"])
    top_pot = (payouts.get(str(top)) or {}).get("pot")
    jackpot = None
    if isinstance(top_pot, (int, float)):
        jackpot = max(0.0, top_pot / 100.0 - live * ratio * cfg["splits"][top])
    matches = sorted((_match_payload(m) for m in record.get("matches") or []),
                     key=lambda m: m["event_number"])
    start, end = indata.window(close, horizon)
    observed = obs["observed_at"]
    return {
        "schema": SCHEMA_VERSION,
        "spel": "atg",
        "product": product,
        "draw_number": int(record["serialNumber"]),
        "horizon": horizon,
        "observed_at": iso(observed),
        "captured_at": iso(now),
        "reg_close_time": iso(close),
        "window": {"start": iso(start), "end": iso(end)},
        "nivaer": list(nivaer.nivaer_for(product)),
        "n_matches": len(matches),
        "events_order": [m["event_number"] for m in matches],
        "rader": {"radpris_kr": cfg["row_price"],
                  "tokens": list(nivaer.atg_symboler(product)),
                  "wildcard": cfg["wildcard"],
                  "format": ("nio tokens med mellanslag i matchordning; cell = "
                             "1X2 + O/U (över/under 2,5)"
                             + (", W = Wild Card (exakt ett per rad)"
                                if cfg["wildcard"] else "; inget Wild Card"))},
        "omgang": {
            "id": record.get("id"), "game_type": record.get("gameType"),
            "namn": record.get("name"), "status": record.get("status"),
            "uttag_procent": record.get("takeoutPercentage"),
            "aterbetalning": {"andel": ratio, "kalla": ratio_source},
            "ou_grans": record.get("overUnderLimit"),
            "vinstgrupper": {str(k): v for k, v in cfg["splits"].items()},
            "pool": {"omsattning_kr": live,
                     "antal_spel": pool.get("numberOfBets"),
                     "antal_system": pool.get("numberOfSystems"),
                     "enhet_kr": (pool.get("unitStake") or 0) / 100.0,
                     "minsta_utdelning_kr": (pool.get("minUnitDividend") or 0) / 100.0,
                     "jackpot_kr": (pool.get("jackpotAmount") or 0) / 100.0,
                     "potter_kr": {k: (v or {}).get("pot", 0) / 100.0
                                   for k, v in payouts.items()},
                     "tidpunkt": pool.get("timestamp")},
            "matches": matches,
        },
        "turnover": _turnover(conn, product, live, close),
        "jackpot": {"value": jackpot, "source": "atg_pool_top_pot"
                    if jackpot is not None else "missing"},
        "underlag_tider": {"atg": iso(observed), "omsattning": iso(observed),
                           "sharp": None},
    }


def capture_due(conn, product: str, obs: dict, *, now: dt.datetime) -> dict:
    """Spara paket för de horisonter vars fönster omgången observerades i."""
    report = {"captured": [], "skipped": None}
    if not galler(product):
        report["skipped"] = "mäts inte (samlas bara in)"
        return report
    if not schema.tables_exist(conn, ("spelai_input",)):
        report["skipped"] = "spelai-tabellerna saknas"
        return report
    close, observed = obs.get("start"), obs.get("observed_at")
    if close is None or observed is None or observed >= close:
        report["skipped"] = "ingen giltig stopp- eller observationstid"
        return report
    serial = int(obs["record"]["serialNumber"])
    for horizon in indata.HORIZONS:
        start, end = indata.window(close, horizon)
        if not (start <= observed <= end):
            continue
        if conn.execute("SELECT 1 FROM spelai_input WHERE product=? AND "
                        "draw_number=? AND horizon=?",
                        (product, serial, horizon)).fetchone():
            continue
        payload = build_payload(conn, product, obs, horizon, now)
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        cur = conn.execute(
            "INSERT OR IGNORE INTO spelai_input (product, draw_number, horizon, "
            "observed_at, captured_at, reg_close_time, schema_version, "
            "payload_json, payload_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (product, serial, horizon, payload["observed_at"], payload["captured_at"],
             payload["reg_close_time"], SCHEMA_VERSION, text, indata.payload_hash(text)))
        conn.commit()
        if cur.rowcount == 1:
            report["captured"].append(horizon)
    return report


# ── standarden ───────────────────────────────────────────────────────────

def round_from_payload(payload: dict) -> big9_builder.Big9Round:
    product = payload["product"]
    cfg = atg.PRODUCTS[product]
    omgang = payload["omgang"]
    limit = float(omgang.get("ou_grans") or 2.5)
    matches, notes = [], []
    for m in omgang["matches"]:
        q = big9_builder.folk_distribution(m.get("streck"))
        if q is None:
            raise ValueError(f"match {m['event_number']} saknar folkets fördelning")
        p = big9_builder.cell_probabilities(m.get("odds"), limit)
        source = "odds"
        if p is None:
            p, source = dict(q), "streck"
        share = 0.0
        wildcard = (m.get("streck") or {}).get("wildcard")
        if cfg["wildcard"] and isinstance(wildcard, (int, float)):
            share = max(0.0, min(1.0, wildcard / 100.0))
        matches.append(big9_builder.Big9Match(
            number=m["event_number"], p=p, q=q, wildcard_share=share, p_source=source))
    pool = omgang.get("pool") or {}
    turnover = payload.get("turnover") or {}
    notes.append(f"omsättning {turnover.get('used', 0):.0f} kr ({turnover.get('basis')})")
    ratio = (omgang.get("aterbetalning") or {}).get("andel")
    if not isinstance(ratio, (int, float)) or ratio <= 0:
        ratio = 1.0 - float(omgang.get("uttag_procent") or 0) / 100.0
    notes.append(f"återbetalning {ratio:.2%} "
                 f"({(omgang.get('aterbetalning') or {}).get('kalla', 'uttag')})")
    return big9_builder.Big9Round(
        product=product, matches=matches,
        turnover=float(turnover.get("used") or pool.get("omsattning_kr") or 0.0),
        row_price=cfg["row_price"],
        payout_ratio=float(ratio),
        splits=dict(cfg["splits"]),
        jackpot=float((payload.get("jackpot") or {}).get("value") or 0.0),
        min_dividend=float(pool.get("minsta_utdelning_kr") or 0.0),
        wildcard=cfg["wildcard"], notes=notes)


def build_standard(payload: dict, level: int, rnd=None) -> dict:
    rnd = rnd or round_from_payload(payload)
    system = big9_builder.build_rows(rnd, float(level), value_weight=0.5)
    out = nivaer.validera(payload["product"], level,
                          {"format": "rows", "rows": system.rows},
                          n_matches=len(rnd.matches))
    out["config_key"] = standard_key(payload["product"], level)
    out["note"] = system.note
    return out


# ── rättning ─────────────────────────────────────────────────────────────

def outcomes(record: dict) -> Optional[dict]:
    """eventNumber → cell, eller "*" för struken match. None = utfall saknas."""
    out = {}
    for m in record.get("matches") or []:
        number = int(m.get("number"))
        if m.get("canceledAt") or m.get("status") == "CANCELED":
            out[number] = "*"
            continue
        result = m.get("result") or {}
        sign = big9_builder.WINNER_SIGN.get(result.get("winner"))
        goal = big9_builder.GOALS_SIGN.get(result.get("goals"))
        if m.get("status") != "DECIDED" or sign is None or goal is None:
            return None
        out[number] = sign + goal
    return out


def correct_count(tokens: list[str], facit: list[str]) -> int:
    return sum(1 for token, res in zip(tokens, facit)
               if token == big9_builder.WILDCARD or res == "*" or token == res)


def counterfactual(record: dict, events: list[int], rows: list[str],
                   cost: Optional[float]) -> Optional[dict]:
    result = outcomes(record)
    if result is None or any(e not in result for e in events):
        return None
    facit = [result[e] for e in events]
    dist: dict[int, int] = {}
    for text in rows:
        k = correct_count(text.split(), facit)
        dist[k] = dist.get(k, 0) + 1
    pool = record.get("pool") or {}
    payouts = pool.get("payouts") or {}
    minimum = float(pool.get("minUnitDividend") or 0)
    payout, published, complete, notes = 0.0, 0.0, True, []
    for k, own in dist.items():
        tier = payouts.get(str(k))
        if own <= 0 or tier is None:
            continue
        pot, units = tier.get("pot"), tier.get("qualifyingUnits")
        if not isinstance(pot, (int, float)) or not isinstance(units, (int, float)):
            complete = False
            notes.append(f"{k} rätt saknar pott eller vinnande enheter")
            continue
        per_unit = math.floor(pot / (units + own) / 100.0) * 100.0
        if per_unit < minimum:
            per_unit = 0.0
        payout += own * per_unit / 100.0
        published += own * float(tier.get("unitDividend") or 0) / 100.0
    note = ("egen vinst utspädd mot ATG:s publicerade pott och vinnande enheter "
            "(nedåt till hela kr, 0 under minimiutdelningen)"
            if complete else "; ".join(notes))
    roi = (round(payout / cost - 1.0, 4) if complete and cost else None)
    return {"dist": dist, "correct_max": max(dist) if dist else 0,
            "payout": round(payout, 2) if complete else None,
            "published": round(published, 2), "complete": complete,
            "note": note, "roi": roi}


def settle(conn, *, now: dt.datetime) -> dict:
    report = {"rattade": 0, "installda": 0, "olosliga": 0}
    if not atg.tables_exist(conn):
        return report
    rows = conn.execute(
        "SELECT p.id, p.product, p.draw_number, p.events_order, p.rows_text, "
        "p.cost_kr FROM spelai_pool_proposal p WHERE p.status='fryst' AND "
        f"p.product IN ({','.join('?' * len(atg.MEASURED))}) AND NOT EXISTS ("
        "SELECT 1 FROM spelai_pool_result r WHERE r.proposal_id=p.id)",
        atg.MEASURED).fetchall()
    for proposal_id, product, serial, events_order, rows_text, cost in rows:
        latest = atg.latest_observation(conn, product, serial)
        if latest is None or latest["status"] not in atg.DONE_STATES:
            continue
        base = (proposal_id, iso(now), SETTLEMENT_VERSION)
        if latest["status"] == "CANCELED":
            conn.execute(
                "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
                "settlement_version, cost_kr, note) VALUES (?,?,?,?,?)",
                (*base, cost, CANCELLED_NOTE))
            report["installda"] += 1
            continue
        events = [int(e) for e in (events_order or "").split(",") if e]
        lines = [line for line in (rows_text or "").splitlines() if line]
        facit = counterfactual(latest["record"], events, lines, cost)
        if facit is None:
            conn.execute(
                "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
                "settlement_version, cost_kr, note) VALUES (?,?,?,?,?)",
                (*base, cost, UNRESOLVABLE_NOTE))
            report["olosliga"] += 1
            continue
        conn.execute(
            "INSERT OR IGNORE INTO spelai_pool_result (proposal_id, settled_at, "
            "settlement_version, correct_max, correct_dist, payout_kr, "
            "published_payout_kr, payout_complete, cost_kr, roi, note) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (*base, facit["correct_max"], json.dumps(facit["dist"], sort_keys=True),
             facit["payout"], facit["published"], int(facit["complete"]), cost,
             facit["roi"], facit["note"]))
        report["rattade"] += 1
    if rows:
        conn.commit()
    return report


# ── missat ───────────────────────────────────────────────────────────────

def facit_start(conn) -> Optional[dt.datetime]:
    return utc(tillstand.hamta(conn, START_KEY))


def rounds_for_missed(conn) -> list[tuple[str, int, str, dt.datetime]]:
    """(produkt, omgång, läge, spelstopp) för de mätta ATG-omgångarna."""
    if not atg.tables_exist(conn):
        return []
    return [(r["product"], r["serial"], r["status"], r["start"])
            for r in atg.latest_rounds(conn, atg.MEASURED) if r["start"]]
