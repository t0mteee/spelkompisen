"""Oddset-delen: enskilda matcher per liga — sharp (Pinnacle) vs Svenska Spel (Kambi).

Insamlingen hämtar per liga Pinnacles matchups + raka marknader (1X2/AH/ÖU, huvudlina)
och Kambis listView + betoffer, matchar ihop källorna på normaliserat klubbnamn +
avsparkstid och sparar odds-snapshots med dedup (skriv bara vid förändring).

Liga-id:n och Kambi-vägar verifierade 2026-07-12 (docs/plan.md, "Prober").
"""
from __future__ import annotations

import datetime as dt
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

from . import kambi
from . import oddset_value
from .derive import derive_1x2
from .pinnacle import Pinnacle, american_to_decimal
from .storage import Storage

LEAGUES = [
    {"key": "allsvenskan", "name": "Allsvenskan", "pin_id": 1728,
     "kambi": "football/sweden/allsvenskan"},
    {"key": "eliteserien", "name": "Eliteserien", "pin_id": 2333,
     "kambi": "football/norway/eliteserien"},
    {"key": "friendlies", "name": "Träningsmatcher", "pin_id": 1863,
     "kambi": "football/club_friendly_matches"},
]

# Fler svenska böcker (jämförelse + hitta boken som hänger efter). Kambi-operatörer
# delar event-id:n med svenskaspel → matchning är trivial. 1X2 räcker (deep-marknader
# hämtas bara från SvS). Altenar kräver operatörens integrationsnamn — väntar på det.
BOOKS = [
    {"key": "expekt", "name": "Expekt", "kambi_op": "expektse"},
]

DEEP_MARKETS_DAYS = 7      # Kambi AH/ÖU per event bara för matcher inom N dygn
LIST_WINDOW_H_BACK = 2     # visa matcher som startat för < 2 h sedan
LIST_WINDOW_D_FWD = 10


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- klubbnamnsmatchning -----------------------------------------------------

# vanliga föreningssuffix som skiljer källorna åt ("Hammarby IF" vs "Hammarby")
_NOISE = {"if", "ff", "fk", "bk", "sk", "ik", "ib", "is", "fc", "afc", "aif",
          "gif", "cf", "ac", "sc", "bp", "kff"}
_CHARMAP = str.maketrans({"ø": "o", "Ø": "o", "æ": "a", "Æ": "a", "đ": "d", "ð": "d",
                          "ł": "l", "ß": "ss", "/": " ", "-": " ", ".": " ", "'": ""})


def norm_team(name: str) -> str:
    """Normalisera klubbnamn för källmatchning: gemener, inga diakriter,
    föreningssuffix borta (om något annat blir kvar)."""
    s = (name or "").translate(_CHARMAP)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    toks = [t for t in s.split() if t]
    kept = [t for t in toks if t not in _NOISE]
    return " ".join(kept or toks)


def _team_sim(a: str, b: str) -> float:
    na, nb = norm_team(a), norm_team(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _match_score(home_a: str, away_a: str, start_a: Optional[str],
                 home_b: str, away_b: str, start_b: Optional[str]) -> float:
    ta, tb = _parse_ts(start_a), _parse_ts(start_b)
    if ta and tb and abs((ta - tb).total_seconds()) > 2 * 3600:
        return 0.0
    return (_team_sim(home_a, home_b) + _team_sim(away_a, away_b)) / 2


def _resolve(cands: list[dict], home: str, away: str, start: Optional[str],
             min_score: float = 0.55) -> Optional[dict]:
    """Hitta befintlig match (samma liga) för ett källevent — bästa fuzzy-träff."""
    best, best_s = None, min_score
    for c in cands:
        s = _match_score(home, away, start, c["home"], c["away"], c["start"])
        if s > best_s:
            best, best_s = c, s
    return best


# --- Pinnacle per liga ---------------------------------------------------------

def _main_pair(prices: list[dict], key_a: str, key_b: str) -> Optional[dict]:
    """Huvudlinan bland alternativa linjer: båda decimaloddsen närmast jämnt 2.0."""
    groups: dict[float, dict] = {}
    for p in prices:
        if p.get("points") is None:
            continue
        groups.setdefault(abs(p["points"]), {})[p.get("designation")] = p
    best, best_score = None, 1e9
    for _, g in groups.items():
        if key_a not in g or key_b not in g:
            continue
        da, db = american_to_decimal(g[key_a]["price"]), american_to_decimal(g[key_b]["price"])
        if not da or not db:
            continue
        score = abs(da - 2) + abs(db - 2)
        if score < best_score:
            best, best_score = {"a": da, "b": db, "line": g[key_a]["points"]}, score
    return best


def pinnacle_league_index(pin: Pinnacle, league_id: int) -> list[dict]:
    """Ligans matcher i decimalodds (2 anrop). Moneyline i första hand; saknas den
    härleds 1X2 ur spread+total (odds_source='derived'). AH/ÖU/hörnor = huvudlinan.
    Hörn-specials är barn-matchups (units='Corners') som mappas till föräldern."""
    matchups = pin._get(f"/leagues/{league_id}/matchups")
    markets = pin._get(f"/leagues/{league_id}/markets/straight")
    cor_parent = {m["id"]: m.get("parentId") for m in matchups
                  if m.get("units") == "Corners" and m.get("parentId")}
    ml: dict = {}
    spread: dict[int, list] = {}
    total: dict[int, list] = {}
    cor_total: dict[int, list] = {}
    for x in markets:
        if x.get("period") != 0:
            continue
        mid, t = x.get("matchupId"), x.get("type")
        if mid in cor_parent:
            if t == "total":
                cor_total.setdefault(cor_parent[mid], []).extend(x.get("prices", []))
            continue
        if t == "moneyline":
            ml[mid] = x
        elif t == "spread":
            spread.setdefault(mid, []).extend(x.get("prices", []))
        elif t == "total":
            total.setdefault(mid, []).extend(x.get("prices", []))

    out: list[dict] = []
    for m in matchups:
        if m.get("parent") is not None or m.get("type") != "matchup":
            continue
        parts = {p.get("alignment"): p.get("name") for p in m.get("participants", [])}
        home, away = parts.get("home"), parts.get("away")
        if not home or not away:
            continue
        mid = m["id"]
        mk = ml.get(mid)
        if mk:
            prices = {p.get("designation"): american_to_decimal(p.get("price"))
                      for p in mk.get("prices", []) if p.get("designation")}
            odds = {"1": prices.get("home"), "X": prices.get("draw"), "2": prices.get("away")}
            source = "pinnacle"
        else:
            odds = derive_1x2(spread.get(mid, []), total.get(mid, []))
            source = "derived" if odds else None
            odds = odds or {"1": None, "X": None, "2": None}
        ah = _main_pair(spread.get(mid, []), "home", "away")
        ou = _main_pair(total.get(mid, []), "over", "under")
        co = _main_pair(cor_total.get(mid, []), "over", "under")
        out.append({
            "id": str(mid), "home": home, "away": away,
            "start": m.get("startTime"), "status": m.get("status"),
            "odds": odds, "odds_source": source,
            "ah": {"H": ah["a"], "A": ah["b"], "line": ah["line"]} if ah else None,
            "ou": {"O": ou["a"], "U": ou["b"], "line": ou["line"]} if ou else None,
            "cor": {"O": co["a"], "U": co["b"], "line": co["line"]} if co else None,
        })
    out.sort(key=lambda r: r.get("start") or "")
    return out


# --- insamling -----------------------------------------------------------------

_PAIR_KEYS = {"ah": ("H", "A"), "ou": ("O", "U"), "cor": ("O", "U")}


def _save_pair_markets(store: Storage, mid: str, source: str, row: dict, at: str) -> int:
    n = 0
    for market, (k1, k2) in _PAIR_KEYS.items():
        v = row.get(market)
        if v:
            n += store.oddset_save_market(mid, source, market, {
                k1: {"odds": v[k1], "line": v["line"]},
                k2: {"odds": v[k2], "line": v["line"]}}, at)
    return n


def collect(store: Storage) -> dict:
    """Hämta odds för alla ligor från båda källorna. Returnerar rapport per liga."""
    at = _now_iso()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    deep_until = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=DEEP_MARKETS_DAYS)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    report: dict = {"at": at, "leagues": {}, "errors": []}
    pin = Pinnacle()
    try:
        for lg in LEAGUES:
            cands = [m for m in store.oddset_matches(since=since) if m["league"] == lg["key"]]
            rows_saved, n_pin, n_kambi = 0, 0, 0

            try:
                pin_rows = pinnacle_league_index(pin, lg["pin_id"])
            except Exception as e:  # noqa: BLE001 — Arcadia Cloudflare-blockar ibland
                pin_rows = []
                report["errors"].append(f"pinnacle {lg['key']}: {e}")
            for r in pin_rows:
                ex = next((c for c in cands if c.get("pinnacle_id") == r["id"]), None) \
                    or _resolve(cands, r["home"], r["away"], r["start"])
                mid = ex["id"] if ex else f"pin:{r['id']}"
                m = {"id": mid, "league": lg["key"], "home": r["home"], "away": r["away"],
                     "start": r["start"], "pinnacle_id": r["id"], "status": r.get("status")}
                store.oddset_upsert_match(m, prefer_names=False)
                if not ex:
                    cands.append(m)
                elif not ex.get("pinnacle_id"):
                    ex["pinnacle_id"] = r["id"]
                if (r.get("start") or "9") <= at:
                    continue   # startad match = live-odds — förorena inte serierna
                if r["odds_source"]:
                    rows_saved += store.oddset_save_odds(mid, r["odds_source"], r["odds"], at)
                rows_saved += _save_pair_markets(store, mid, "pinnacle", r, at)
                n_pin += 1

            kambi_rows = kambi.league_events(lg["kambi"])
            if not kambi_rows:
                report["errors"].append(f"kambi {lg['key']}: inga events")
            for e in kambi_rows:
                ex = next((c for c in cands if c.get("kambi_id") == e["id"]), None) \
                    or _resolve(cands, e["home"], e["away"], e["start"])
                mid = ex["id"] if ex else f"svs:{e['id']}"
                m = {"id": mid, "league": lg["key"], "home": e["home"], "away": e["away"],
                     "start": e["start"], "kambi_id": e["id"]}
                # Kambis svenska namn vinner som visningsnamn
                store.oddset_upsert_match(m, prefer_names=True)
                if not ex:
                    cands.append(m)
                elif not ex.get("kambi_id"):
                    ex["kambi_id"] = e["id"]
                if (e.get("start") or "9") <= at:
                    continue   # live — spara inte
                rows_saved += store.oddset_save_odds(mid, "svenskaspel", e["odds"], at)
                if (e.get("start") or "9") <= deep_until:
                    mk = kambi.event_markets(e["id"], e["home"], e["away"])
                    rows_saved += _save_pair_markets(store, mid, "svenskaspel", mk, at)
                    time.sleep(0.25)   # paca CDN:et
                n_kambi += 1

            # sidoböcker (1X2): samma Kambi-event-id:n som svenskaspel
            n_books = 0
            for book in BOOKS:
                for e in kambi.league_events(lg["kambi"], operator=book["kambi_op"]):
                    ex = next((c for c in cands if c.get("kambi_id") == e["id"]), None) \
                        or _resolve(cands, e["home"], e["away"], e["start"])
                    if not ex or (e.get("start") or "9") <= at:
                        continue   # skapa inga matcher från sidoböcker; hoppa live
                    rows_saved += store.oddset_save_odds(ex["id"], book["key"], e["odds"], at)
                    n_books += 1

            report["leagues"][lg["key"]] = {
                "pinnacle": n_pin, "kambi": n_kambi, "books": n_books,
                "saved_rows": rows_saved}
    finally:
        pin.close()
    store.meta_set("oddset_last_run", at)
    # Etapp 3: resultat/xG/Elo till modellen (throttlat i modulen — oftast no-op)
    try:
        from . import oddset_data
        report["data"] = oddset_data.refresh_all(store)
    except Exception as e:  # noqa: BLE001
        report["errors"].append(f"modeldata: {e}")
    # Etapp 2: värde-flaggor → CLV-logg + ntfy, och stängningar för startade matcher
    try:
        payload = matches_payload(store)
        vs = oddset_value.log_and_notify(store, payload["matches"])
        vs["closings"] = oddset_value.resolve_closings(store)
        report["value"] = vs
    except Exception as e:  # noqa: BLE001 — får inte fälla insamlingen
        report["errors"].append(f"värde/notiser: {e}")
    return report


# --- läs-API ---------------------------------------------------------------------

def matches_payload(store: Storage) -> dict:
    """Matchlistan i tidsordning med senaste odds + rörelseserier per källa."""
    now = dt.datetime.now(dt.timezone.utc)
    frm = (now - dt.timedelta(hours=LIST_WINDOW_H_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to = (now + dt.timedelta(days=LIST_WINDOW_D_FWD)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ms = store.oddset_matches(since=frm, until=to)
    ids = [m["id"] for m in ms]
    latest = store.oddset_latest(ids)
    movement = store.oddset_movement(ids)
    out = []
    for m in ms:
        out.append({**m, "odds": latest.get(m["id"], {}),
                    "movement": movement.get(m["id"], {})})
    out.sort(key=lambda r: (r.get("start") or "9", r["id"]))
    oddset_value.attach_value(out)
    oddset_value.attach_steam(out)
    try:
        from . import oddset_model
        oddset_model.attach_model(store, out)
    except Exception:  # noqa: BLE001 — modellen (amber) får aldrig fälla listan
        pass
    return {"matches": out,
            "leagues": [{"key": lg["key"], "name": lg["name"]} for lg in LEAGUES],
            "last_run": store.meta_get("oddset_last_run")}
