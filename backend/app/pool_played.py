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

Ingenting här lägger spel. Knappen bokför bara att användaren själv har lämnat
in kupongen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Optional

from .storage import Storage

SIGNS = ("1", "X", "2")
SETTLEMENT_VERSION = "played-v1"

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
            "cancelled": bool(draw_event.get("cancelled"))}


def live_status(coupon: dict, states: list[dict]) -> dict:
    """Rätt-så-långt per rad + vilka rader som fortfarande kan nå varje nivå.

    Det här är svaret på "följa reducerade system live": för varje rad räknas
    säkra träffar (avgjorda matcher) och möjliga träffar (säkra + de som ännu
    inte är avgjorda). En rad kan nå nivå k om möjliga ≥ k.
    """
    rows = (coupon.get("rows_text") or "").split("\n")
    n_events = min(len(states), len(rows[0]) if rows and rows[0] else 0)
    decided = sum(1 for s in states[:n_events] if s.get("final"))
    best_secure = 0
    secure_hist: dict[int, int] = {}
    possible_hist: dict[int, int] = {}
    for row in rows:
        secure = possible = 0
        for i in range(n_events):
            state = states[i]
            if state.get("cancelled"):
                secure += 1          # struken match räknas som rätt
                possible += 1
                continue
            hit = state.get("sign") == row[i]
            if state.get("final"):
                secure += int(hit)
                possible += int(hit)
            else:
                possible += 1        # oavgjord match kan fortfarande bli rätt
        best_secure = max(best_secure, secure)
        secure_hist[secure] = secure_hist.get(secure, 0) + 1
        possible_hist[possible] = possible_hist.get(possible, 0) + 1
    alive = {level: sum(n for p, n in possible_hist.items() if p >= level)
             for level in range(max(1, n_events - 3), n_events + 1)}
    return {"n_events": n_events, "n_decided": decided,
            "all_decided": bool(n_events and decided == n_events),
            "best_secure": best_secure,
            "secure_dist": dict(sorted(secure_hist.items(), reverse=True)),
            "alive_per_level": dict(sorted(alive.items(), reverse=True))}


def settle(store: Storage, coupon: dict, states: list[dict],
           tiers: dict[int, tuple]) -> dict:
    """Slutfacit mot PUBLICERADE belopp — ingen utspädning (vi var i potten).

    tiers: {antal_rätt: (vinnare, belopp_per_vinnare)}. Saknas beloppet för en
    nivå vi träffat blir facitet uttryckligen ofullständigt; ROI får då INTE
    räknas som noll.
    """
    status = live_status(coupon, states)
    if not status["all_decided"]:
        return {"settled": False, "reason": "alla matcher är inte avgjorda"}
    dist = status["secure_dist"]
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
    store.conn.execute(
        "UPDATE pool_played_coupon SET settled_at=?, correct_max=?, "
        "correct_dist=?, payout_kr=?, payout_complete=?, roi=?, settle_note=? "
        "WHERE id=?",
        (_now(), status["best_secure"], json.dumps(dist),
         round(payout, 2) if complete else None, int(complete), roi,
         "; ".join(notes) or SETTLEMENT_VERSION, coupon["id"]))
    store._commit()
    return {"settled": True, "payout_kr": round(payout, 2) if complete else None,
            "roi": roi, "complete": complete,
            "correct_max": status["best_secure"], "correct_dist": dist}


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
