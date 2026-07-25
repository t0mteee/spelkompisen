"""Svenska Spels sportsbok (Oddset) drivs av **Kambi** — publikt offering-API utan auth.

  GET /offering/v2018/svenskaspel/listView/{ligaväg}.json   -> events + 1X2 ("Fulltid")
  GET /offering/v2018/svenskaspel/betoffer/event/{id}.json  -> alla marknader per match

Odds i milliodds (1420 = 1.42), linjer i milli (2500 = 2.5). Lagnamn på svenska.
Portad från vm-projektet (world_cup_2026) men generaliserad till ligavägar.
Inofficiellt CDN-API — kan ändras utan förvarning.
"""
from __future__ import annotations

from typing import Optional

import httpx

BASE_TPL = "https://eu-offering-api.kambicdn.com/offering/v2018/{op}"
BASE = BASE_TPL.format(op="svenskaspel")   # bakåtkompatibelt default
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
PARAMS = {"lang": "sv_SE", "market": "SE"}
# Fler svenska Kambi-operatörer (verifierade 2026-07-12): expektse (Expekt), atg (ATG).
# Kambis event-id:n är globala — samma match har samma id hos alla operatörer.


def _milli(o: Optional[float]) -> Optional[float]:
    return round(o / 1000, 2) if o else None


def _main_pair(pairs: list[tuple]) -> Optional[dict]:
    """pairs: [(dec_a, dec_b, line_a)] -> huvudlinan (båda oddsen närmast jämnt 2.0)."""
    best, best_score = None, 1e9
    for da, db, line in pairs:
        if da is None or db is None:
            continue
        score = abs(da - 2) + abs(db - 2)
        if score < best_score:
            best, best_score = {"a": da, "b": db, "line": line}, score
    return best


def league_events(path: str, timeout: float = 25.0,
                  operator: str = "svenskaspel", strict: bool = False) -> list[dict]:
    """Matcher + 1X2 för en ligaväg (t.ex. 'football/sweden/allsvenskan').
    Returnerar [{id, home, away, start, odds{'1','X','2'}}]. Tom lista vid fel."""
    try:
        r = httpx.get(f"{BASE_TPL.format(op=operator)}/listView/{path}.json", params=PARAMS,
                      headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception:  # noqa: BLE001 — best-effort för gamla direktanrop
        if strict:
            raise
        return []

    out: list[dict] = []
    for ev in data.get("events") or []:
        e = ev.get("event") or {}
        home, away = e.get("homeName"), e.get("awayName")
        if not home or not away:
            continue
        odds = {"1": None, "X": None, "2": None}
        for bo in ev.get("betOffers") or []:
            if (bo.get("criterion") or {}).get("label") != "Fulltid":
                continue
            for o in bo.get("outcomes") or []:
                t = o.get("type")
                if t == "OT_ONE":
                    odds["1"] = _milli(o.get("odds"))
                elif t == "OT_CROSS":
                    odds["X"] = _milli(o.get("odds"))
                elif t == "OT_TWO":
                    odds["2"] = _milli(o.get("odds"))
            break
        out.append({"id": str(e.get("id")), "home": home, "away": away,
                    "start": e.get("start"), "odds": odds})
    return out


def _side(label: Optional[str], home: str, away: str) -> Optional[str]:
    """Klassa outcome-label som hemma/borta. Klubbnamn: exakt casefold först,
    sedan prefix-match (Kambi kortar ibland, 'Hammarby' vs 'Hammarby IF')."""
    if not label:
        return None
    lbl = label.strip().casefold()
    h, a = home.strip().casefold(), away.strip().casefold()
    if lbl == h:
        return "H"
    if lbl == a:
        return "A"
    if h.startswith(lbl) or lbl.startswith(h):
        return "H"
    if a.startswith(lbl) or lbl.startswith(a):
        return "A"
    return None


def event_markets(event_id: str, home: str, away: str, timeout: float = 25.0,
                  strict: bool = False, operator: str = "svenskaspel") -> dict:
    """Asian handicap + asiatisk total + hörnor (huvudlinan) för ett event.
    -> {'ah': {H,A,line}, 'ou': {O,U,line}} (nycklar bara när kompletta). Tom vid fel.

    `operator` (2026-07-25): basen var HÅRDKODAD till svenskaspel, så
    sidoböckerna hämtades bara på 1X2 — vi jämförde i praktiken SvS mot Pinnacle
    på mål och hörnor, vilket inte är mer än man gör manuellt. Kambi-operatörer
    delar event-id, och Expekt visade sig ge 141 betOffers på samma match som
    SvS 147, med identisk marknadsstruktur (Asian totalt, Asian handicap, Antal
    hörnor). Deep-marknader per bok är alltså bara en fråga om att fråga."""
    base = BASE_TPL.format(op=operator)
    try:
        r = httpx.get(f"{base}/betoffer/event/{event_id}.json", params=PARAMS,
                      headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        bos = (r.json() or {}).get("betOffers") or []
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return {}

    ah_pairs, ou_pairs = [], []
    cor: dict[float, dict] = {}                 # {linje: {'O': odds, 'U': odds}}
    for bo in bos:
        label = ((bo.get("criterion") or {}).get("label") or "").strip()
        outs = bo.get("outcomes") or []
        if label == "Antal hörnor":             # totala hörnor, alla linjer
            for o in outs:
                ln, od = o.get("line"), _milli(o.get("odds"))
                if ln is None or not od:
                    continue
                side = ("O" if o.get("type") == "OT_OVER"
                        else "U" if o.get("type") == "OT_UNDER" else None)
                if side:
                    cor.setdefault(ln / 1000, {})[side] = od
        elif label == "Asian handicap":
            by_line: dict[float, dict] = {}
            for o in outs:
                if o.get("line") is None:
                    continue
                side = _side(o.get("label"), home, away)
                if side:
                    by_line.setdefault(abs(o["line"]), {})[side] = o
            for _, g in by_line.items():
                h, a = g.get("H"), g.get("A")
                if h and a:
                    ah_pairs.append((_milli(h.get("odds")), _milli(a.get("odds")),
                                     h.get("line") / 1000))
        elif label == "Asian totalt":
            by_line = {}
            for o in outs:
                if o.get("line") is None:
                    continue
                by_line.setdefault(o["line"], {})[o.get("type")] = o
            for line, g in by_line.items():
                ov, un = g.get("OT_OVER"), g.get("OT_UNDER")
                if ov and un:
                    ou_pairs.append((_milli(ov.get("odds")), _milli(un.get("odds")),
                                     line / 1000))

    res = {}
    ah = _main_pair(ah_pairs)
    ou = _main_pair(ou_pairs)
    co = _main_pair([(v["O"], v["U"], ln) for ln, v in cor.items()
                     if v.get("O") and v.get("U")])
    if ah:
        res["ah"] = {"H": ah["a"], "A": ah["b"], "line": ah["line"]}
    if ou:
        res["ou"] = {"O": ou["a"], "U": ou["b"], "line": ou["line"]}
    if co:
        res["cor"] = {"O": co["a"], "U": co["b"], "line": co["line"]}
    return res
