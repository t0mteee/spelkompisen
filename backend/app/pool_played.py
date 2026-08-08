"""Spårning av VERKLIGT spelade kuponger — facit och livestatus.

Två saker som PH3-ledgern inte kan ge:

1. **Riktigt facit.** Ledgern fryser kontrafaktiska benchmarksystem som aldrig
   lämnades in, och späder därför deras vinst mot observerad nivåpott. En kupong
   Saman faktiskt spelat ligger redan i potten — SvS publicerade belopp per
   vinnare inkluderar honom. Utdelningen är alltså `antal egna rader på nivån ×
   publicerat belopp`, RAKT. Att återanvända utspädningen här hade gett för låg
   siffra; att använda den här formeln i ledgern hade gett för hög.
2. **Livestatus för reducerade system.** SvS eget draw-API bär matchresultat
   under omgången (`match.result` med `sportEventResultType == "Current"`, plus
   `status`/`statusId`), så vi kan räkna rätt-så-långt per rad och se vilka
   rader som fortfarande kan nå en vinstnivå — utan någon ny datakälla.

FACIT ≠ LIVESTATUS (granskningsfix F4 2026-07-26): draw-payloadens
Current-score är enbart livevy. Slutfacit tas ALLTID ur settlementlagret
(`pool_event_settlement.outcome` per eventNumber — samma kanon som PH3):
Current-score kan avvika från pooltecknet (förlängning i cupmatch), och en
struken match får sitt tecken FASTSTÄLLT av SvS — den är aldrig "rätt för
alla rader". Radernas tecken paras alltid mot eventNumber via kupongens
`events_order`, aldrig positionsvis mot payloadordningen.

Ingenting här lägger spel. Knappen bokför bara att användaren själv har lämnat
in kupongen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import random
from typing import Optional

from .storage import Storage

SIGNS = ("1", "X", "2")
# v2 (2026-07-26): facit ur pool_event_settlement (officiellt outcome per
# eventNumber) i stället för draw-payloadens Current-score; events_order-join;
# hård breddvakt. v1 hann aldrig settla en kupong i drift.
SETTLEMENT_VERSION = "played-v2"

# SvS-statusar: matchen är färdigspelad och tecknet står fast.
FINISHED_STATUS_IDS = frozenset({31})       # 31 = "Slut"/Ended
FINISHED_STATUS_WORDS = frozenset({"slut", "ended", "finished", "avslutad"})


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows_hash(rows: list[str]) -> str:
    """Identitet för kupongen: exakt raduppsättning i exakt ordning."""
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def normalize_rows(rows) -> list[str]:
    """Ta emot ['1','X','2'] per rad ELLER '1X2...' och returnera strängrader."""
    out = []
    for row in rows or []:
        text = "".join(row) if isinstance(row, (list, tuple)) else str(row)
        text = "".join(ch for ch in text.upper() if ch in ("1", "X", "2"))
        if text:
            out.append(text)
    return out


def record(store: Storage, payload: dict) -> dict:
    """Bokför en spelad kupong. Idempotent per (produkt, omgång, radhash)."""
    rows = normalize_rows(payload.get("rows"))
    if not rows:
        raise ValueError("kupongen saknar rader")
    width = {len(r) for r in rows}
    if len(width) != 1:
        raise ValueError("raderna har olika antal tecken")
    row_price = float(payload.get("row_price") or 1.0)
    events = payload.get("events_order") or list(range(1, rows[0].__len__() + 1))
    digest = rows_hash(rows)
    store.conn.execute(
        "INSERT OR IGNORE INTO pool_played_coupon("
        "product, draw_number, played_at, label, build_kind, strategy, "
        "value_weight, budget, row_price, n_rows, cost_kr, events_order, "
        "rows_text, rows_hash, code_version, note) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (payload["product"], int(payload["draw_number"]), _now(),
         payload.get("label"), payload.get("build_kind"),
         payload.get("strategy"), payload.get("value_weight"),
         payload.get("budget"), row_price, len(rows),
         round(len(rows) * row_price, 2),
         json.dumps(list(events)), "\n".join(rows), digest,
         payload.get("code_version"), payload.get("note")))
    store._commit()
    row = store.conn.execute(
        "SELECT * FROM pool_played_coupon WHERE product=? AND draw_number=? "
        "AND rows_hash=?",
        (payload["product"], int(payload["draw_number"]), digest)).fetchone()
    return dict(row) if row else {}


def forget(store: Storage, coupon_id: int) -> bool:
    """Ta bort en felaktigt bokförd kupong (bara innan den settlats)."""
    cur = store.conn.execute(
        "DELETE FROM pool_played_coupon WHERE id=? AND settled_at IS NULL",
        (int(coupon_id),))
    store._commit()
    return cur.rowcount > 0


def _sign_from_score(home, away) -> Optional[str]:
    try:
        h, a = int(home), int(away)
    except (TypeError, ValueError):
        return None
    return "1" if h > a else ("2" if a > h else "X")


def event_state(draw_event: dict) -> dict:
    """{'sign': '1'|'X'|'2'|None, 'final': bool, 'score': '1-0'|None}.

    `sign` är tecknet SÅ LÅNGT — under pågående match är det preliminärt, och
    `final` säger om det står fast. Ett pågående 0–0 ger sign 'X' med
    final=False; det är information, inte ett facit.
    """
    match = draw_event.get("match") or {}
    current = None
    for res in (match.get("result") or []):
        if res.get("sportEventResultType") == "Current":
            current = res
            break
    sign = _sign_from_score((current or {}).get("home"),
                            (current or {}).get("away"))
    status_id = match.get("statusId")
    status_word = str(match.get("status") or "").casefold()
    final = bool(
        (isinstance(status_id, int) and status_id in FINISHED_STATUS_IDS)
        or status_word in FINISHED_STATUS_WORDS
        or str(match.get("sportEventStatus") or "").casefold() == "ended")
    score = (f"{current['home']}-{current['away']}"
             if current and current.get("home") is not None else None)
    return {"sign": sign, "final": final, "score": score,
            "event_number": draw_event.get("eventNumber"),
            "cancelled": bool(draw_event.get("cancelled")),
            "probs": _event_probs(draw_event),
            "home": _participant(match, "home"),
            "away": _participant(match, "away"),
            "start": match.get("matchStart"),
            # Startad men inte klar ⇒ SvS statiska prematch-odds beskriver inte
            # längre matchen. Flaggan styr om livepris måste hämtas.
            "in_progress": bool(score) and not final,
            "description": (draw_event.get("description")
                            or " - ".join(
                                p for p in (_participant(match, "home"),
                                            _participant(match, "away")) if p)
                            or None)}


def _participant(match: dict, side: str) -> Optional[str]:
    for p in (match.get("participants") or []):
        if p.get("type") == side:
            return p.get("name")
    return None


def _event_probs(draw_event: dict) -> Optional[dict]:
    """Overroundfri 1X2-sannolikhet ur SvS-oddsen, annars streck.

    Samma prioritetsordning och power-devig som analysvyn — chansen på
    kupongen får aldrig räknas på en annan sannolikhet än den vi visar. Utan
    både odds och streck returneras None; en gissad likafördelning hade sett ut
    som information.
    """
    from .analysis import _power_probs
    odds = draw_event.get("odds") or {}
    keys = {"1": "one", "X": "x", "2": "two"}
    inv = {}
    for sign, key in keys.items():
        value = _decimal(odds.get(key))
        if value and value > 1.0:
            inv[sign] = 1.0 / value
    if len(inv) == 3:
        return _power_probs(inv)
    folk = draw_event.get("svenskaFolket") or {}
    streck = {}
    for sign, key in keys.items():
        value = _decimal(folk.get(key))
        if value is not None:
            streck[sign] = max(0.001, value)
    if len(streck) == 3 and sum(streck.values()) > 0:
        total = sum(streck.values())
        return {sign: value / total for sign, value in streck.items()}
    return None


def attach_live_odds(store: Storage, states: list[dict]) -> None:
    """Byt prematch-sannolikheten mot LIVEpris för matcher som redan rullar.

    SvS pooldata bär statiska prematch-odds hela omgången. AIK–Örgryte låg
    0–2 i halvtid med 1,55 på AIK (≈60 %) medan Kambis livepris stod i 9,00
    (≈8 %) — en kupongchans räknad på det förra är inte ungefär rätt, den är
    fel. Matcher som INTE startat rör vi inte; där är prematch rätt pris.

    Hittas inget öppet livepris nollas sannolikheten i stället för att falla
    tillbaka på prematch. Chansberäkningen visar då ingen siffra alls, vilket
    är sanningen: vi vet inte.
    """
    from . import kambi
    from .analysis import _power_probs
    running = [s for s in states if s.get("in_progress")]
    if not running:
        return
    catalogue = kambi.live_events()      # ETT anrop för hela omgången
    for state in running:
        state["probs_basis"] = "live"
        event_id = _kambi_id_for(catalogue, state)
        prices = kambi.live_1x2(event_id) if event_id else {}
        if len(prices) == 3:
            state["probs"] = _power_probs({s: 1 / o for s, o in prices.items()})
        else:
            state["probs"] = None
            state["probs_basis"] = "live_saknas"


def _kambi_id_for(catalogue: list[dict], state: dict) -> Optional[str]:
    """Poolmatch → Kambis live-event via normaliserade lagnamn.

    Listan slås upp direkt i stället för via `oddset_matches`: poolerna
    innehåller Ettan, Elitettan och utländska serier som ligger helt utanför
    Oddsets tio ligor, så en Oddset-slagning tappade de flesta.

    Hemma/borta måste stämma på SAMMA sida — en spegelvänd träff kan vara ett
    returmöte, och ett pris på fel lag är värre än inget pris. Entydighet krävs.
    """
    from .live_radar import _same_team
    home, away = state.get("home"), state.get("away")
    if not (home and away):
        return None
    # `_same_team` och inte strikt `norm_team`-likhet: SvS och Kambi skiljer sig
    # på föreningssuffix (`Kristiansund` mot `Kristiansund BK`), svensk genitiv
    # och de observerade aliasen. Spärrarna mot U23/B-lag och prefixkrockar
    # följer med på köpet.
    hits = {row["id"] for row in catalogue
            if _same_team(row["home"], home) and _same_team(row["away"], away)}
    return hits.pop() if len(hits) == 1 else None


def _decimal(value) -> Optional[float]:
    """SvS skickar svenska decimaler som strängar ("5,50")."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _coupon_events(coupon: dict, width: int) -> list[int]:
    """Kupongens eventNumber per kolumn. Default 1..N när inget sparats."""
    try:
        events = [int(e) for e in json.loads(coupon.get("events_order") or "[]")]
    except (TypeError, ValueError):
        events = []
    return events if len(events) == width else list(range(1, width + 1))


def live_status(coupon: dict, states: list[dict]) -> dict:
    """Rätt-så-långt per rad + vilka rader som fortfarande kan nå varje nivå.

    Det här är svaret på "följa reducerade system live": för varje rad räknas
    säkra träffar (avgjorda matcher) och möjliga träffar (säkra + de som ännu
    inte är avgjorda). En rad kan nå nivå k om möjliga ≥ k.

    LIVEVY, aldrig facit. Tecknen paras mot eventNumber via kupongens
    `events_order` (payloadordningen är inget kontrakt), en kolumn utan
    matchande event räknas som oavgjord i stället för att tyst trunkeras, och
    en struken match är oavgjord tills SvS fastställt tecknet i settlementet.
    """
    rows = (coupon.get("rows_text") or "").split("\n")
    width = len(rows[0]) if rows and rows[0] else 0
    events = _coupon_events(coupon, width)
    by_event: dict[int, dict] = {}
    for i, state in enumerate(states):
        number = state.get("event_number")
        by_event[int(number) if number is not None else i + 1] = state
    col_states = [by_event.get(events[i]) for i in range(width)]
    decided = sum(1 for s in col_states
                  if s and s.get("final") and not s.get("cancelled"))
    best_secure = 0
    secure_hist: dict[int, int] = {}
    possible_hist: dict[int, int] = {}
    for row in rows:
        secure = possible = 0
        for i in range(width):
            state = col_states[i]
            if state is None or state.get("cancelled") or not state.get("final"):
                possible += 1        # okänd/struken/pågående kan ännu bli rätt
                continue
            hit = state.get("sign") == row[i]
            secure += int(hit)
            possible += int(hit)
        best_secure = max(best_secure, secure)
        secure_hist[secure] = secure_hist.get(secure, 0) + 1
        possible_hist[possible] = possible_hist.get(possible, 0) + 1
    alive = {level: sum(n for p, n in possible_hist.items() if p >= level)
             for level in range(max(1, width - 3), width + 1)}
    levels = sorted(alive, reverse=True)
    # Bästa NÅBARA antal rätt. Ren aritmetik — den kräver inga odds och finns
    # därför även när en livemarknad är avstängd. Utan den visade kortet bara
    # en tabell med streck när kupongen inte längre kunde nå någon vinstnivå,
    # och Saman fick räkna ut det själv ur "bäst 4 rätt" och 5 kvarvarande.
    max_possible = max(possible_hist) if possible_hist else 0
    return {"n_events": width, "n_decided": decided,
            "all_decided": bool(width and decided == width),
            "best_secure": best_secure,
            "max_possible": max_possible,
            # Ingen rad kan nå ens den lägsta redovisade vinstnivån.
            "out_of_contention": bool(levels) and max_possible < min(levels),
            "secure_dist": dict(sorted(secure_hist.items(), reverse=True)),
            "alive_per_level": dict(sorted(alive.items(), reverse=True)),
            **_chance_per_level(rows, col_states, width, levels)}


CHANCE_EXACT_MAX_COMBOS = 60000     # 3^10; över det blir uppräkningen dyr
CHANCE_SAMPLES = 20000              # Monte Carlo när uppräkning är för dyr


def _chance_per_level(rows: list[str], col_states: list[Optional[dict]],
                      width: int, levels: list[int]) -> dict:
    """P(minst EN rad når nivån) per nivå, givet oddsen på kvarvarande matcher.

    Raderna delar de kvarvarande matcherna, så utfallen är BEROENDE — en
    produkt av per-rad-sannolikheter vore fel. Vi räknar därför på hela
    utfallsrummet: rader grupperas på sitt teckenmönster över de oavgjorda
    kolumnerna, och per utfall räknas bästa totalen över grupperna.

    Saknar någon oavgjord match sannolikhet returneras inget alls — en halv
    beräkning är värre än ingen.
    """
    if not rows or not width or not levels:
        return {}
    open_cols = [i for i in range(width)
                 if not (col_states[i] and col_states[i].get("final")
                         and not col_states[i].get("cancelled"))]
    probs = []
    live_used = 0
    for i in open_cols:
        state = col_states[i] or {}
        p = state.get("probs")
        if not p or abs(sum(p.values()) - 1.0) > 0.01:
            # Namnge matchen: live-Ö/U suspenderas i sekunder vid farliga
            # lägen, så det här är oftast övergående och inte en systemlucka.
            namn = state.get("description") or "en kvarvarande match"
            note = (f"{namn} saknar öppet livepris just nu"
                    if state.get("in_progress")
                    else f"{namn} saknar odds")
            return {"chance_note": note}
        if state.get("probs_basis") == "live":
            live_used += 1
        probs.append(p)

    base: dict[tuple, int] = {}
    for row in rows:
        secure = 0
        for i in range(width):
            state = col_states[i]
            if state and state.get("final") and not state.get("cancelled"):
                secure += int(state.get("sign") == row[i])
        pattern = tuple(row[i] for i in open_cols)
        base[pattern] = max(base.get(pattern, 0), secure)
    if not open_cols:
        best = max(base.values())
        return {"chance_per_level": {lvl: (1.0 if best >= lvl else 0.0)
                                     for lvl in levels},
                "chance_basis": "avgjord"}

    groups = list(base.items())
    signs = ("1", "X", "2")
    hit = {lvl: 0.0 for lvl in levels}
    combos = 3 ** len(open_cols)

    def score(outcome: tuple) -> int:
        return max(secure + sum(1 for i, s in enumerate(pattern) if s == outcome[i])
                   for pattern, secure in groups)

    if combos <= CHANCE_EXACT_MAX_COMBOS and combos * len(groups) <= 4_000_000:
        for combo in itertools.product(signs, repeat=len(open_cols)):
            weight = 1.0
            for i, s in enumerate(combo):
                weight *= probs[i][s]
            best = score(combo)
            for lvl in levels:
                if best >= lvl:
                    hit[lvl] += weight
        basis = "exakt"
    else:
        rng = random.Random(20260802)     # fast frö: samma svar vid omladdning
        for _ in range(CHANCE_SAMPLES):
            combo = tuple(
                rng.choices(signs, weights=[p["1"], p["X"], p["2"]])[0]
                for p in probs)
            best = score(combo)
            for lvl in levels:
                if best >= lvl:
                    hit[lvl] += 1.0 / CHANCE_SAMPLES
        basis = "simulerad"
    return {"chance_per_level": {lvl: round(hit[lvl], 6) for lvl in levels},
            "chance_basis": basis, "chance_open_matches": len(open_cols),
            "chance_live_matches": live_used}


def _mark_incomplete(store: Storage, coupon: dict, note: str) -> dict:
    store.conn.execute(
        "UPDATE pool_played_coupon SET settled_at=?, payout_complete=0, "
        "settle_note=? WHERE id=?", (_now(), note, coupon["id"]))
    store._commit()
    return {"settled": True, "complete": False, "payout_kr": None,
            "roi": None, "reason": note}


def settle(store: Storage, coupon: dict, tiers: dict[int, tuple]) -> dict:
    """Slutfacit ur settlementlagret + PUBLICERADE belopp (vi var i potten).

    Facit = `pool_event_settlement.outcome` per eventNumber — samma kanon som
    PH3-ledgern. Draw-payloadens Current-score används ALDRIG här (den kan
    avvika efter förlängning, och strukna matcher får sitt tecken fastställt).
    tiers: {antal_rätt: (vinnare, belopp_per_vinnare)}. Saknas beloppet för en
    nivå vi träffat blir facitet uttryckligen ofullständigt; ROI får då INTE
    räknas som noll.
    """
    rows = (coupon.get("rows_text") or "").split("\n")
    width = len(rows[0]) if rows and rows[0] else 0
    events = _coupon_events(coupon, width)
    outcomes = {int(number): outcome for number, outcome in store.conn.execute(
        "SELECT event_number, outcome FROM pool_event_settlement "
        "WHERE product=? AND draw_number=?",
        (coupon["product"], coupon["draw_number"]))}
    if not outcomes:
        return {"settled": False,
                "reason": "settlementlagret saknar omgången än"}
    if len(outcomes) != width:
        # Hård breddvakt — settla aldrig tyst på fel antal matcher.
        return _mark_incomplete(
            store, coupon,
            f"breddfel: kupongen har {width} tecken/rad men omgången "
            f"{len(outcomes)} matcher")
    missing = sorted(e for e in events if outcomes.get(e) not in SIGNS)
    if missing:
        # Samma kanonregel som PH3: utfall saknas => aldrig "rätt för alla".
        return _mark_incomplete(
            store, coupon,
            "officiellt utfall saknas för match "
            + ",".join(str(e) for e in missing))
    facit = [outcomes[e] for e in events]
    dist: dict[int, int] = {}
    for row in rows:
        correct = sum(1 for sign, res in zip(row, facit) if sign == res)
        dist[correct] = dist.get(correct, 0) + 1
    payout = 0.0
    complete = True
    notes = []
    for correct, n_rows in dist.items():
        if correct not in tiers:
            continue                    # nivån ger ingen utdelning
        winners, amount = tiers[correct]
        if amount is None:
            complete = False
            notes.append(f"{correct} rätt saknar belopp")
            continue
        payout += n_rows * float(amount)
    cost = float(coupon.get("cost_kr") or 0.0)
    roi = ((payout - cost) / cost) if (complete and cost > 0) else None
    correct_max = max(dist) if dist else 0
    store.conn.execute(
        "UPDATE pool_played_coupon SET settled_at=?, correct_max=?, "
        "correct_dist=?, payout_kr=?, payout_complete=?, roi=?, settle_note=? "
        "WHERE id=?",
        (_now(), correct_max, json.dumps(dist),
         round(payout, 2) if complete else None, int(complete), roi,
         "; ".join(notes) or SETTLEMENT_VERSION, coupon["id"]))
    store._commit()
    return {"settled": True, "payout_kr": round(payout, 2) if complete else None,
            "roi": roi, "complete": complete,
            "correct_max": correct_max, "correct_dist": dist}


def open_coupons(store: Storage) -> list[dict]:
    return [dict(r) for r in store.conn.execute(
        "SELECT * FROM pool_played_coupon WHERE settled_at IS NULL "
        "ORDER BY played_at DESC")]


def all_coupons(store: Storage, limit: int = 100) -> list[dict]:
    return [dict(r) for r in store.conn.execute(
        "SELECT * FROM pool_played_coupon ORDER BY played_at DESC LIMIT ?",
        (int(limit),))]


def summary(store: Storage) -> dict:
    """Ärligt sammandrag: bara kompletta facit ingår i ROI."""
    rows = [r for r in all_coupons(store, 1000)]
    done = [r for r in rows if r["settled_at"] and r["payout_complete"]]
    spent = sum(float(r["cost_kr"] or 0) for r in done)
    won = sum(float(r["payout_kr"] or 0) for r in done)
    return {"n_coupons": len(rows), "n_settled": len(done),
            "n_open": sum(1 for r in rows if not r["settled_at"]),
            "spent_kr": round(spent, 2), "won_kr": round(won, 2),
            "roi": round((won - spent) / spent, 4) if spent > 0 else None,
            "note": ("ROI räknas bara på kuponger med komplett publicerad "
                     "utdelning; öppna och ofullständiga hålls utanför.")}
