"""Betfair Exchange och BetInAsia mätta mot Smarkets/SBOBET.

Beslut driften-2026-11-06-betexplorer-per-bok, val 0: "samla Betfair Exchange
och BetInAsia (1X2, Ö/U 2,5, AH) ... och mät dem mot Smarkets/SBOBET innan något
ankare ändras". Det här är den mätningen — BESKRIVANDE, ingen grind och inget
beslut. Att göra någon av böckerna till ankare är ett eget beslut och en ny
signalversion (anchor-v1 i oddset_value står orörd).

PARNING (observationstidsregeln): varje lyckad Betexplorer-capture där boken
listades (`oddset_betexplorer_capture`, egen observationstid t) paras med
referensens pris SOM DET VAR VID t: per tecken den senaste raden i
`oddset_odds` med `fetched_at` ≤ t, bekräftad inom `MAX_AGE_MIN` före t
(`last_seen_at` ≥ t − 45 min, samma färskhet som värdemotorn) och på EXAKT
samma lina. Inget pris efter t används. `available` läses inte: flaggan skrivs
om på senaste raden när marknaden försvinner och säger inget om läget vid t.

MÅTT per bok och marknad (sannolikheter devigade med power-metoden, som
värdemotorn): par, matcher, medelavvikelse |p_bok − p_ref| över tecknen (pp),
snedhet per tecken (p_bok − p_ref, pp), bokens och referensens marginal, och
bokens prisålder (t minus Betexplorers senaste ändringstid, median i minuter)
som mått på om aggregatet släpar. Paren är inte oberoende (samma match frågas
upp till en gång i timmen); `matcher` är det som räknas som underlag.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from typing import Optional

VERSION = "betexplorer-matning-v1"
BOOKS = ("betfair_ex", "betinasia")
REFERENCE = {"1x2": "smarkets", "ou": "smarkets", "ah": "sbobet"}
SIGNS = {"1x2": ("1", "X", "2"), "ou": ("O", "U"), "ah": ("H", "A")}
MAX_AGE_MIN = 45        # = oddset_value.PRICE_MAX_AGE_MIN (låst i testerna)


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _devig(prices: dict, signs: tuple) -> Optional[dict[str, float]]:
    from .oddset_value import _devig as devig
    return devig(prices, signs)


def _margin(prices: dict, signs: tuple) -> float:
    return sum(1.0 / prices[s] for s in signs) - 1.0


def reference_at(store, match_id: str, source: str, market: str,
                 line: Optional[float], at: str) -> Optional[dict]:
    """Referensens pris per tecken vid `at`, eller None om något tecken saknar
    ett färskt pris på samma lina före `at`."""
    oldest = _iso(_t(at) - dt.timedelta(minutes=MAX_AGE_MIN))
    out = {}
    for sign in SIGNS[market]:
        r = store.conn.execute(
            "SELECT odds, line, last_seen_at FROM oddset_odds WHERE match_id=? "
            "AND source=? AND market=? AND sign=? AND fetched_at<=? "
            "ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (match_id, source, market, sign, at)).fetchone()
        if not r or not r["odds"] or r["odds"] <= 1.0 or r["last_seen_at"] < oldest:
            return None
        if market != "1x2" and (r["line"] is None or line is None
                                or abs(r["line"] - line) > 1e-6):
            return None
        out[sign] = r["odds"]
    return out


def _book_age_min(changed: dict, at: str) -> Optional[float]:
    times = [v for v in (changed or {}).values() if v]
    if not times:
        return None
    return (_t(at) - _t(max(times))).total_seconds() / 60.0


def compare(store, since: Optional[str] = None,
            until: Optional[str] = None) -> dict:
    """Mätningen: {"version", "since", "until", "groups": [...]}, en grupp per
    bok × marknad, i BOOKS- och SIGNS-ordning."""
    where = ["book IN (%s)" % ",".join("?" * len(BOOKS)), "ok=1"]
    args: list = list(BOOKS)
    if since:
        where.append("observed_at>=?")
        args.append(since)
    if until:
        where.append("observed_at<?")
        args.append(until)
    caps = store.conn.execute(
        "SELECT match_id, book, market, observed_at, listed, line, prices, "
        f"changed_at FROM oddset_betexplorer_capture WHERE {' AND '.join(where)} "
        "ORDER BY observed_at, id", args).fetchall()
    acc: dict[tuple[str, str], dict] = {
        (b, m): {"asked": 0, "listed": 0, "pairs": [], "matches": set()}
        for b in BOOKS for m in SIGNS}
    for c in caps:
        key = (c["book"], c["market"])
        if key not in acc:
            continue
        g = acc[key]
        g["asked"] += 1
        if not c["listed"] or not c["prices"]:
            continue
        g["listed"] += 1
        market, signs = c["market"], SIGNS[c["market"]]
        prices = json.loads(c["prices"])
        if any(not prices.get(s) or prices[s] <= 1.0 for s in signs):
            continue
        ref = reference_at(store, c["match_id"], REFERENCE[market], market,
                           c["line"], c["observed_at"])
        if not ref:
            continue
        p_book, p_ref = _devig(prices, signs), _devig(ref, signs)
        if not p_book or not p_ref:
            continue
        g["matches"].add(c["match_id"])
        g["pairs"].append({
            "diff": {s: 100.0 * (p_book[s] - p_ref[s]) for s in signs},
            "margin_book": _margin(prices, signs),
            "margin_ref": _margin(ref, signs),
            "age": _book_age_min(json.loads(c["changed_at"]) if c["changed_at"] else {},
                                 c["observed_at"])})
    groups = []
    for (book, market), g in acc.items():
        signs, pairs = SIGNS[market], g["pairs"]
        row = {"book": book, "market": market, "reference": REFERENCE[market],
               "line": 2.5 if market == "ou" else None,
               "asked": g["asked"], "listed": g["listed"], "pairs": len(pairs),
               "matches": len(g["matches"])}
        if pairs:
            ages = [p["age"] for p in pairs if p["age"] is not None]
            row.update({
                "mae_pp": round(statistics.fmean(
                    statistics.fmean(abs(p["diff"][s]) for s in signs) for p in pairs), 2),
                "bias_pp": {s: round(statistics.fmean(p["diff"][s] for p in pairs), 2)
                            for s in signs},
                "max_pp": round(max(abs(p["diff"][s]) for p in pairs for s in signs), 2),
                "margin_book": round(statistics.fmean(p["margin_book"] for p in pairs), 4),
                "margin_ref": round(statistics.fmean(p["margin_ref"] for p in pairs), 4),
                "book_age_median_min": round(statistics.median(ages), 1) if ages else None})
        groups.append(row)
    return {"version": VERSION, "since": since, "until": until, "groups": groups}


LABELS = {"betfair_ex": "Betfair Exchange", "betinasia": "BetInAsia",
          "smarkets": "Smarkets", "sbobet": "SBOBET"}


def format_report(rep: dict) -> str:
    """Textrapporten för `cli.py betexplorer-matning`."""
    lines = [f"{rep['version']} — Betfair Exchange/BetInAsia mot Smarkets (1X2, Ö/U 2,5) "
             f"och SBOBET (handikapp, samma lina)",
             f"fönster: {rep['since'] or 'allt'} – {rep['until'] or 'nu'} · beskrivande, "
             "inget beslut; ankarbyte är ett eget beslut", ""]
    head = (f"{'bok':<17}{'marknad':<8}{'mot':<10}{'frågat':>7}{'listat':>7}"
            f"{'par':>6}{'match':>6}{'|Δ| pp':>8}{'max pp':>8}{'marg bok':>9}"
            f"{'marg ref':>9}{'ålder':>7}  snedhet pp")
    lines.append(head)
    for g in rep["groups"]:
        base = (f"{LABELS[g['book']]:<17}{g['market']:<8}{LABELS[g['reference']]:<10}"
                f"{g['asked']:>7}{g['listed']:>7}{g['pairs']:>6}{g['matches']:>6}")
        if not g["pairs"]:
            lines.append(base + f"{'–':>8}")
            continue
        age = g.get("book_age_median_min")
        bias = " ".join(f"{s} {v:+.2f}" for s, v in g["bias_pp"].items())
        lines.append(base + f"{g['mae_pp']:>8.2f}{g['max_pp']:>8.2f}"
                     f"{100 * g['margin_book']:>8.1f}%{100 * g['margin_ref']:>8.1f}%"
                     f"{(f'{age:.0f}m' if age is not None else '–'):>7}  {bias}")
    return "\n".join(lines)
