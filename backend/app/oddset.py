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
     "kambi": "football/sweden/allsvenskan", "altenar": 3537},
    {"key": "superettan", "name": "Superettan", "pin_id": 2476,
     "kambi": "football/sweden/superettan", "altenar": 4825},
    {"key": "eliteserien", "name": "Eliteserien", "pin_id": 2333,
     "kambi": "football/norway/eliteserien", "altenar": 3458},
    {"key": "obosligaen", "name": "OBOS-ligaen", "pin_id": 2331,
     "kambi": "football/norway/obos-ligaen", "altenar": None},
    {"key": "mls", "name": "MLS", "pin_id": 2663,
     "kambi": "football/usa/mls", "altenar": None},
    {"key": "friendlies", "name": "Träningsmatcher", "pin_id": 1863,
     "kambi": "football/club_friendly_matches", "altenar": None},
    # Forskningsligor för V2.2-EU. `research_only` styr insamlingsdjup och
    # actionability: lätt insamling (1X2, ingen deep/sidoböcker/frånvaro), inga
    # värdesignaler/Kelly/notiser/CLV, ingen ordinarie model-capture — V2.2-
    # shadowen äger modellspåret tills experimentet klarat sin forwarddom.
    # `visible_in_ui` (beställning 2026-07-24) är ett OBEROENDE produktbeslut:
    # matcherna syns i ordinarie Oddset-vy med odds/prisålder/rörelser och
    # forskningsmärkning. Synlig liga är INTE automatiskt actionable.
    {"key": "premier_league", "name": "Premier League", "pin_id": 1980,
     "kambi": "football/england/premier_league", "altenar": None,
     "research_only": True, "visible_in_ui": True},
    {"key": "serie_a", "name": "Serie A", "pin_id": 2436,
     "kambi": "football/italy/serie_a", "altenar": None,
     "research_only": True, "visible_in_ui": True},
    {"key": "la_liga", "name": "La Liga", "pin_id": 2196,
     "kambi": "football/spain/la_liga", "altenar": None,
     "research_only": True, "visible_in_ui": True},
    {"key": "bundesliga", "name": "Bundesliga", "pin_id": 1842,
     "kambi": "football/germany/bundesliga", "altenar": None,
     "research_only": True, "visible_in_ui": True},
]
# Actionable = får skapa spelbar signal, Kelly, notis och CLV-/value_log-rader.
ACTIONABLE_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES if not league.get("research_only"))
# Synlig i ordinarie UI-payload (/api/oddset/matches utan interna flaggor).
VISIBLE_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES
    if not league.get("research_only") or league.get("visible_in_ui"))
RESEARCH_LEAGUE_KEYS = frozenset(
    league["key"] for league in LEAGUES if league.get("research_only"))

# Fler böcker (jämförelse + hitta boken som hänger efter). Kambi-operatörer delar
# event-id:n med svenskaspel (trivial matchning); Altenar-böcker matchas fuzzy på
# namn+avspark. 1X2 räcker (deep-marknader hämtas bara från SvS).
# Expekt kör Kambi via LeoVegas-avtalet (verifierat: Kambi-pressrelease, t.o.m. 2027).
BOOKS = [
    {"key": "expekt", "name": "Expekt", "kambi_op": "expektse"},
    {"key": "betinia", "name": "Betinia", "altenar": "betinia"},
]

DEEP_MARKETS_DAYS = 7      # Kambi AH/ÖU per event bara för matcher inom N dygn
LIST_WINDOW_H_BACK = 2     # visa matcher som startat för < 2 h sedan
LIST_WINDOW_D_FWD = 10

# Snabbpoll (backlog A1): 30-min-pollen är för långsam för lag-fönstret — när
# avspark närmar sig körs lätta varv (Pinnacle + böckernas 1X2 samt SvS-deep
# för matcherna i 3h-fönstret; ingen modelldata) i samma launchd-pass.
# OBS: backloggen skrev "<36 h" men det vore i praktiken kontinuerlig polling
# dygnet runt (Pinnacle Cloudflare-blockar på IP-nivå) — 3 h täcker lineup-
# fönstret + sena steamen och håller volymen nere. Bara ligor med match i
# fönstret pollas.
FAST_WITHIN_H = 3.0        # snabbvarv när nästa avspark är inom N h
FAST_SLEEP_S = 240         # 4 min mellan snabbvarven (A1: 3–5 min)

# Forskningsligor under säsongsuppehåll: 10-dagarsfönstret är tomt ända fram
# till premiären — ordinarie UI-payloaden visar då ligans NÄSTA omgång
# (matcher inom några dygn från första kommande avspark) så att en synlig
# liga inte ser trasig ut. Gäller BARA UI-vägen; insamlings-payloaden
# (include_research=True) behåller det strikta fönstret.
RESEARCH_NEXT_ROUND_SPAN_D = 4
RESEARCH_LOOKAHEAD_D = 45


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


def _resolve_team_pair(cands: list[dict], home: str, away: str,
                       min_score: float = 0.80) -> Optional[dict]:
    """Entydig lagparslänk utan tid.

    Används bara för research-only höst/vår-ligor där Kambi publicerar hela
    premiäromgången på en gemensam placeholdertid innan TV-tiderna är satta.
    Hemma/borta-paret förekommer bara en gång per ligasäsong; oentydighet ger
    alltid None i stället för en gissning.
    """
    ranked = sorted((
        ((_team_sim(home, cand["home"]) + _team_sim(away, cand["away"])) / 2,
         cand)
        for cand in cands
    ), key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < min_score:
        return None
    if len(ranked) > 1 and abs(ranked[0][0] - ranked[1][0]) < 0.05:
        return None
    return ranked[0][1]


# --- Pinnacle per liga ---------------------------------------------------------

def _alt_pairs(prices: list[dict], key_a: str, key_b: str) -> list[dict]:
    """ALLA kompletta linjepar ur sharpens svar (inte bara huvudlinan).
    Alternativlinjerna gör samma-linje-jämförelse möjlig när boken visar en
    annan lina än sharpens huvudlina — utan dem dog 67 % av AH- och ~40 % av
    Ö/U-jämförelserna på olika-linje-regeln (mätt 2026-07-20)."""
    groups: dict[float, dict] = {}
    for p in prices:
        if p.get("points") is None:
            continue
        groups.setdefault(abs(p["points"]), {})[p.get("designation")] = p
    out = []
    for _, g in groups.items():
        if key_a not in g or key_b not in g:
            continue
        da, db = american_to_decimal(g[key_a]["price"]), american_to_decimal(g[key_b]["price"])
        if not da or not db:
            continue
        out.append({"a": da, "b": db, "line": g[key_a]["points"]})
    out.sort(key=lambda r: r["line"])
    return out


def _main_pair(prices: list[dict], key_a: str, key_b: str) -> Optional[dict]:
    """Huvudlinan bland alternativa linjer: båda decimaloddsen närmast jämnt 2.0."""
    best, best_score = None, 1e9
    for pair in _alt_pairs(prices, key_a, key_b):
        score = abs(pair["a"] - 2) + abs(pair["b"] - 2)
        if score < best_score:
            best, best_score = pair, score
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
            "alt": {"ah": _alt_pairs(spread.get(mid, []), "home", "away"),
                    "ou": _alt_pairs(total.get(mid, []), "over", "under"),
                    "cor": _alt_pairs(cor_total.get(mid, []), "over", "under")},
        })
    out.sort(key=lambda r: r.get("start") or "")
    return out


def pinnacle_known_moneylines(pin: Pinnacle, league_id: int,
                              cands: list[dict]) -> list[dict]:
    """Ett enda Pinnacle-anrop för kända researchmatcher i snabbfönstret.

    Fullvarvet har redan fryst matchup-ID, lag och avspark. Vid 4-minutersvarv
    behövs därför bara marknadssvaret; det halverar Pinnacle-trafiken för de
    fyra nya ligorna. Endast direkt moneyline accepteras eftersom V2.2 ändå
    förbjuder härledd sharp-1X2.
    """
    known = {
        str(cand["pinnacle_id"]): cand for cand in cands
        if cand.get("pinnacle_id")
    }
    moneylines = {}
    for market in pin._get(f"/leagues/{league_id}/markets/straight"):
        matchup_id = str(market.get("matchupId"))
        if (matchup_id in known and market.get("period") == 0 and
                market.get("type") == "moneyline"):
            moneylines[matchup_id] = market
    out = []
    for matchup_id, market in moneylines.items():
        cand = known[matchup_id]
        prices = {
            price.get("designation"): american_to_decimal(price.get("price"))
            for price in market.get("prices", [])
        }
        out.append({
            "id": matchup_id, "home": cand["home"], "away": cand["away"],
            "start": cand["start"], "status": cand.get("status"),
            "odds": {
                "1": prices.get("home"), "X": prices.get("draw"),
                "2": prices.get("away"),
            },
            "odds_source": "pinnacle", "ah": None, "ou": None, "cor": None,
            "alt": {},
        })
    return out


# --- insamling -----------------------------------------------------------------

_PAIR_KEYS = {"ah": ("H", "A"), "ou": ("O", "U"), "cor": ("O", "U")}


def _observe_pair_markets(store: Storage, mid: str, source: str,
                          row: dict, at: str) -> int:
    """Registrera alla parmarknader efter ett lyckat källsvar.

    Även en saknad marknad är information: en tidigare rad ska då markeras
    unavailable i stället för att ligga kvar som ett spelbart spökpris.
    """
    n = 0
    for market, (k1, k2) in _PAIR_KEYS.items():
        v = row.get(market)
        rows = ({
                k1: {"odds": v[k1], "line": v["line"]},
                k2: {"odds": v[k2], "line": v["line"]}}
                if v else {})
        n += store.oddset_save_market(mid, source, market, rows, at)
    return n


def collect(store: Storage, leagues: Optional[list[dict]] = None,
            deep: bool = True) -> dict:
    """Hämta odds för alla ligor från båda källorna. Returnerar rapport per liga.

    deep=False är snabbvarvet (A1): Pinnacle + böckernas 1X2, samt Kambi-deep
    endast för matcher i 3h-fönstret. Modelldata/modellfit hoppas över. leagues
    begränsar till ligor med match i snabbfönstret."""
    at = _now_iso()
    now = dt.datetime.now(dt.timezone.utc)
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    list_until = (now + dt.timedelta(days=LIST_WINDOW_D_FWD)).strftime("%Y-%m-%dT%H:%M:%SZ")
    deep_until = (now + dt.timedelta(days=DEEP_MARKETS_DAYS)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    fast_until = (now + dt.timedelta(hours=FAST_WITHIN_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: dict = {"at": at, "leagues": {}, "errors": []}
    # Notisvakten (WP2-mini, granskningen runda 2): allt som faktiskt sågs i
    # DETTA varvs lyckade svar — (match_id, källa, marknad). Misslyckad källa
    # eller saknad marknad hamnar aldrig här → notiser kan inte citera priser
    # som kan vara plockade/suspenderade. Gamla priser i DB räcker inte.
    present: set[tuple] = set()
    pin = Pinnacle()
    try:
        for lg in (LEAGUES if leagues is None else leagues):
            research_only = bool(lg.get("research_only"))
            cands = [m for m in store.oddset_matches(since=since, until=list_until)
                     if m["league"] == lg["key"]]
            rows_saved, n_pin, n_kambi = 0, 0, 0

            pin_ok, pin_error = True, None
            try:
                pin_rows = (
                    pinnacle_known_moneylines(pin, lg["pin_id"], cands)
                    if not deep and research_only and any(
                        cand.get("pinnacle_id") for cand in cands)
                    else pinnacle_league_index(pin, lg["pin_id"])
                )
            except Exception as e:  # noqa: BLE001 — Arcadia Cloudflare-blockar ibland
                pin_rows = []
                pin_ok, pin_error = False, str(e)
                report["errors"].append(f"pinnacle {lg['key']}: {e}")
            store.oddset_record_source_health(
                "pinnacle", lg["key"], "markets", at, pin_ok, len(pin_rows), pin_error)
            pin_seen: set[str] = set()
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
                pin_seen.add(str(r["id"]))
                if r["odds_source"]:
                    rows_saved += store.oddset_save_odds(mid, r["odds_source"], r["odds"], at)
                    other = "derived" if r["odds_source"] == "pinnacle" else "pinnacle"
                    store.oddset_mark_market_unavailable(mid, other, "1x2")
                    if all(r["odds"].get(s) for s in ("1", "X", "2")):
                        present.add((mid, "pinnacle", "1x2"))
                else:
                    store.oddset_mark_market_unavailable(mid, "pinnacle", "1x2")
                    store.oddset_mark_market_unavailable(mid, "derived", "1x2")
                if not research_only:
                    rows_saved += _observe_pair_markets(
                        store, mid, "pinnacle", r, at)
                    for mk_ in _PAIR_KEYS:
                        if r.get(mk_):
                            present.add((mid, "pinnacle", mk_))
                        # sharpens ALLA linjer (tom lista efter lyckat svar =
                        # tidigare linjer markeras plockade)
                        store.oddset_save_sharp_alt(
                            mid, mk_, (r.get("alt") or {}).get(mk_) or [], at)
                n_pin += 1

            if pin_ok:
                for c in cands:
                    pid = c.get("pinnacle_id")
                    if not pid or str(pid) in pin_seen or (c.get("start") or "9") <= at:
                        continue
                    store.oddset_mark_market_unavailable(c["id"], "pinnacle", "1x2")
                    store.oddset_mark_market_unavailable(c["id"], "derived", "1x2")
                    if not research_only:
                        for market in _PAIR_KEYS:
                            store.oddset_mark_market_unavailable(
                                c["id"], "pinnacle", market)

            kambi_ok, kambi_error = True, None
            try:
                kambi_rows = kambi.league_events(lg["kambi"], strict=True)
            except Exception as e:  # noqa: BLE001
                kambi_rows = []
                kambi_ok, kambi_error = False, str(e)
                report["errors"].append(f"kambi {lg['key']}: {e}")
            store.oddset_record_source_health(
                "svenskaspel", lg["key"], "1x2", at, kambi_ok,
                len(kambi_rows), kambi_error)
            kambi_seen: set[str] = set()
            deep_errors: list[str] = []
            deep_checked = 0
            for e in kambi_rows:
                id_match = next(
                    (c for c in cands if c.get("kambi_id") == e["id"]), None)
                timed_match = _resolve(
                    cands, e["home"], e["away"], e["start"])
                # Kambis tidiga höst/vår-scheman använder ibland en gemensam
                # placeholdertid för nästan hela omgången. Pinnacle-raden är
                # då starttidskanon; team-only används endast mot en redan
                # verifierad Pinnacle-identitet i researchligor.
                team_match = (
                    _resolve_team_pair(
                        [cand for cand in cands if cand.get("pinnacle_id")],
                        e["home"], e["away"])
                    if research_only else None
                )
                ex = team_match or id_match or timed_match
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
                kambi_seen.add(str(e["id"]))
                rows_saved += store.oddset_save_odds(mid, "svenskaspel", e["odds"], at)
                if all(e["odds"].get(s) for s in ("1", "X", "2")):
                    present.add((mid, "svenskaspel", "1x2"))
                market_until = deep_until if deep else fast_until
                if (not research_only and
                        (e.get("start") or "9") <= market_until):
                    deep_checked += 1
                    try:
                        mk = kambi.event_markets(
                            e["id"], e["home"], e["away"], strict=True)
                        rows_saved += _observe_pair_markets(
                            store, mid, "svenskaspel", mk, at)
                        for mk_ in _PAIR_KEYS:
                            if mk.get(mk_):
                                present.add((mid, "svenskaspel", mk_))
                    except Exception as exc:  # ett eventfel får inte dölja resten
                        deep_errors.append(f"{e['id']}: {exc}")
                        report["errors"].append(
                            f"kambi-deep {lg['key']} {e['id']}: {exc}")
                    time.sleep(0.25)   # paca CDN:et
                n_kambi += 1

            if kambi_ok:
                market_until = deep_until if deep else fast_until
                for c in cands:
                    kid = c.get("kambi_id")
                    if not kid or str(kid) in kambi_seen or (c.get("start") or "9") <= at:
                        continue
                    store.oddset_mark_market_unavailable(
                        c["id"], "svenskaspel", "1x2")
                    if (not research_only and
                            (c.get("start") or "9") <= market_until):
                        for market in _PAIR_KEYS:
                            store.oddset_mark_market_unavailable(
                                c["id"], "svenskaspel", market)
            store.oddset_record_source_health(
                "svenskaspel", lg["key"], "deep", at,
                kambi_ok and not deep_errors, deep_checked,
                "; ".join(deep_errors) if deep_errors else kambi_error)

            # sidoböcker (1X2): Kambi-operatörer delar event-id:n, Altenar matchas fuzzy
            n_books = 0
            for book in (() if research_only else BOOKS):
                if not book.get("kambi_op") and not (book.get("altenar") and lg.get("altenar")):
                    continue
                book_ok, book_error = True, None
                try:
                    if book.get("kambi_op"):
                        b_rows = kambi.league_events(
                            lg["kambi"], operator=book["kambi_op"], strict=True)
                    else:
                        from . import altenar
                        b_rows = altenar.league_events(
                            lg["altenar"], integration=book["altenar"], strict=True)
                except Exception as exc:  # noqa: BLE001
                    b_rows = []
                    book_ok, book_error = False, str(exc)
                    report["errors"].append(f"{book['key']} {lg['key']}: {exc}")
                store.oddset_record_source_health(
                    book["key"], lg["key"], "1x2", at, book_ok,
                    len(b_rows), book_error)
                book_seen: set[str] = set()
                for e in b_rows:
                    ex = next((c for c in cands if c.get("kambi_id") == e["id"]), None) \
                        if book.get("kambi_op") else None
                    ex = ex or _resolve(cands, e["home"], e["away"], e["start"])
                    if not ex or (e.get("start") or "9") <= at:
                        continue   # skapa inga matcher från sidoböcker; hoppa live
                    rows_saved += store.oddset_save_odds(ex["id"], book["key"], e["odds"], at)
                    book_seen.add(ex["id"])
                    if all(e["odds"].get(s) for s in ("1", "X", "2")):
                        present.add((ex["id"], book["key"], "1x2"))
                    n_books += 1
                if book_ok:
                    for c in cands:
                        if c["id"] in book_seen or (c.get("start") or "9") <= at:
                            continue
                        store.oddset_mark_market_unavailable(
                            c["id"], book["key"], "1x2")

            report["leagues"][lg["key"]] = {
                "pinnacle": n_pin, "kambi": n_kambi, "books": n_books,
                "saved_rows": rows_saved}
    finally:
        pin.close()
    store.meta_set("oddset_last_run", at)
    # Etapp 3: resultat/xG/Elo till modellen (throttlat i modulen — oftast no-op)
    if deep:
        try:
            from . import oddset_data
            report["data"] = oddset_data.refresh_all(store)
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"modeldata: {e}")
    # Etapp 2/WP5: samma point-in-time-payload driver både handlingsloggen och
    # forskningsledgern. Snabbvarvet fittar modellen ENDAST när en ny fast
    # horisont öppnas; annars förblir det lätt.
    try:
        payload = matches_payload(store, light=not deep, include_research=True)
        from . import oddset_ledger
        if deep:
            report["ledger_capture"] = oddset_ledger.capture_predictions(
                store, payload["matches"])
        else:
            # V2.2:s forskningsligor ingår inte i produktmodellens ordinarie
            # due-lista. Fitta bara de matcher vars fasta shadowhorisont är ny,
            # innan sharp + feature + shadow fryses atomärt.
            from . import oddset_model, oddset_v22
            due_v22 = oddset_v22.due_matches(store, payload["matches"])
            if due_v22:
                oddset_model.attach_model(
                    store, due_v22,
                    allowed_leagues=set(oddset_v22.SCOPE_LEAGUES),
                    fit_pools=oddset_v22.FIT_POOLS)
            sharp_capture = oddset_ledger.capture_predictions(
                store, payload["matches"], tiers=("sharp",))
            due_model = oddset_ledger.due_model_matches(store, payload["matches"])
            missing_model = [match for match in due_model if not match.get("model")]
            if missing_model:
                oddset_model.attach_model(store, missing_model)
            model_capture = oddset_ledger.capture_predictions(
                store, due_model, tiers=("model",))
            report["ledger_capture"] = {
                key: sharp_capture[key] + model_capture[key]
                for key in sharp_capture}
        actionable = [
            match for match in payload["matches"]
            if match.get("league") in ACTIONABLE_LEAGUE_KEYS
        ]
        vs = oddset_value.log_and_notify(store, actionable, present=present)
        vs["closings"] = oddset_value.resolve_closings(store)
        report["value"] = vs
    except Exception as e:  # noqa: BLE001 — får inte fälla insamlingen
        report["errors"].append(f"värde/notiser: {e}")
    try:
        from . import oddset_ledger
        report["ledger_closings"] = oddset_ledger.resolve_closings(store)
        oddset_ledger.prediction_report(store, update_states=True)
    except Exception as e:  # noqa: BLE001 — ledgern får inte fälla insamlingen
        report["errors"].append(f"prediction-ledger: {e}")
    return report


def hours_to_next_start(store: Storage) -> Optional[float]:
    """Timmar till nästa framtida avspark (styr snabbpollen)."""
    now = dt.datetime.now(dt.timezone.utc)
    ms = store.oddset_matches(since=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    starts = [_parse_ts(m.get("start")) for m in ms]
    hrs = [(t - now).total_seconds() / 3600 for t in starts if t]
    return min(hrs) if hrs else None


def fast_leagues(store: Storage) -> list[dict]:
    """Ligorna med avspark inom FAST_WITHIN_H — bara de pollas i snabbvarven."""
    now = dt.datetime.now(dt.timezone.utc)
    ms = store.oddset_matches(
        since=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        until=(now + dt.timedelta(hours=FAST_WITHIN_H)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    keys = {m["league"] for m in ms}
    return [lg for lg in LEAGUES if lg["key"] in keys]


# --- läs-API ---------------------------------------------------------------------

def _research_next_round(store: Storage, windowed: list[dict],
                         now: dt.datetime) -> list[dict]:
    """Nästa omgång för synliga forskningsligor utan match i listfönstret."""
    empty = (RESEARCH_LEAGUE_KEYS & VISIBLE_LEAGUE_KEYS) \
        - {m["league"] for m in windowed}
    if not empty:
        return []
    future = store.oddset_matches(
        since=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        until=(now + dt.timedelta(days=RESEARCH_LOOKAHEAD_D))
        .strftime("%Y-%m-%dT%H:%M:%SZ"))
    extra: list[dict] = []
    for key in sorted(empty):
        rows = sorted((m for m in future if m["league"] == key),
                      key=lambda r: r.get("start") or "9")
        first = _parse_ts(rows[0].get("start")) if rows else None
        if not first:
            continue
        cutoff = (first + dt.timedelta(days=RESEARCH_NEXT_ROUND_SPAN_D)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        extra.extend(m for m in rows if (m.get("start") or "9") <= cutoff)
    return extra


def matches_payload(store: Storage, light: bool = False,
                    include_research: bool = False) -> dict:
    """Matchlistan i tidsordning med senaste odds + rörelseserier per källa.
    light=True (snabbvarven) hoppar frånvaro + modell — modellfitten är dyr
    och amber-flaggorna är inte tidskritiska; 30-min-varvet tar dem.
    include_research=True är den INTERNA insamlings-payloaden (alla ligor,
    V2.2-forskningsmodell, ofiltrerat värde-underlag). Ordinarie API:t kör
    False: forskningsligor med visible_in_ui visas då med odds, prisålder
    och rörelser, märkta research=True, men utan värde-/modellfält —
    synlighet och actionability är två oberoende egenskaper. Är list-
    fönstret tomt för en forskningsliga (säsongsuppehåll) visas ligans
    nästa omgång i stället (_research_next_round)."""
    now = dt.datetime.now(dt.timezone.utc)
    frm = (now - dt.timedelta(hours=LIST_WINDOW_H_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to = (now + dt.timedelta(days=LIST_WINDOW_D_FWD)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ms = store.oddset_matches(since=frm, until=to)
    if not include_research:
        ms = [match for match in ms if match["league"] in VISIBLE_LEAGUE_KEYS]
        ms.extend(_research_next_round(store, ms, now))
    ids = [m["id"] for m in ms]
    latest = store.oddset_latest(ids)
    movement = store.oddset_movement(ids)
    alt = store.oddset_sharp_alt_latest(ids)
    out = []
    for m in ms:
        row = {**m, "odds": latest.get(m["id"], {}),
               "movement": movement.get(m["id"], {}),
               "sharp_alt": alt.get(m["id"], {})}
        if m["league"] in RESEARCH_LEAGUE_KEYS:
            row["research"] = True
        out.append(row)
    out.sort(key=lambda r: (r.get("start") or "9", r["id"]))
    oddset_value.attach_value(out)
    oddset_value.attach_steam(out)
    for m in out:   # internt underlag för värdemotorn — inte API-last
        m.pop("sharp_alt", None)
        # Synlig ≠ actionable: ordinarie payloaden bär inga värde-/Kelly-
        # underlag för forskningsligor (V2.2:s dom är inte fälld).
        if not include_research and m.get("research"):
            m.pop("value", None)
    if not light:
        try:
            from . import oddset_data
            for mid, ab in oddset_data.get_absences(store, ids).items():
                next(m for m in out if m["id"] == mid)["absences"] = ab
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import oddset_data, oddset_model
            oddset_model.attach_model(
                store, out, allowed_leagues=oddset_data.MODEL_LEAGUES)
            if include_research:
                from . import oddset_v22
                oddset_model.attach_model(
                    store, out,
                    allowed_leagues=oddset_data.RESEARCH_MODEL_LEAGUES,
                    fit_pools=oddset_v22.FIT_POOLS)
        except Exception:  # noqa: BLE001 — modellen (amber) får aldrig fälla listan
            pass
    visible_leagues = [
        league for league in LEAGUES
        if include_research or league["key"] in VISIBLE_LEAGUE_KEYS
    ]
    health = store.oddset_source_health()
    if not include_research:
        health = [
            row for row in health
            if row.get("league") in VISIBLE_LEAGUE_KEYS
        ]
    leagues_out = []
    for lg in visible_leagues:
        entry = {"key": lg["key"], "name": lg["name"]}
        if lg.get("research_only"):
            entry["research"] = True
        leagues_out.append(entry)
    return {"matches": out,
            "leagues": leagues_out,
            "last_run": store.meta_get("oddset_last_run"),
            "source_health": health}
