"""Smarkets — betting exchange, publikt REST-API utan auth eller nyckel.

Verifierat 2026-07-24. Fyra anrop räcker för en hel liga (allt batchbart):

  GET /v3/events/?type=football_match&state=upcoming&limit=1000
        -> alla kommande fotbollsevent; ligan ligger i `full_slug`
           (t.ex. /sport/football/sweden-allsvenskan/2026/07/25/...)
  GET /v3/events/{id1,id2,...}/markets/     -> marknader, 1X2 = "Full-time result"
  GET /v3/markets/{m1,m2,...}/contracts/    -> kontrakt, slug home/draw/away
  GET /v3/markets/{m1,m2,...}/quotes/       -> orderboken per kontrakt

PRISFORMAT: `price` är sannolikhet × 100 (2041 = 20,41 %), alltså
decimalodds = 10000 / price. `bids` är order att köpa kontraktet, `offers`
order att sälja det. Den som vill BACKA ett utfall köper till bästa (lägsta)
offer; bästa bid är vad man kan lägga emot till.

VARFÖR VI HAR DEN: Smarkets är en BÖRS, inte en bok att slå. Uppmätt
overround ~2,2 % mot Svenska Spels 2,6 % — den är alltså skarpare än allt
mjukt vi når. Nyttan är metodisk: `mid` (mittpunkten mellan bästa bid och
bästa offer) är ett fair-pris som knappt behöver devigas, och fungerar som
ETT ANDRA SHARP-ANKARE vid sidan av Pinnacle. Idag mäts varje edge bara mot
vår egen power-devigning av Pinnacle, och metodvalet rör ~3 pp medan
flaggtröskeln är 2 pp — ett börspris låter oss kontrollera devigen i stället
för att lita på den. Se docs/forbattringar.md.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

BASE = "https://api.smarkets.com/v3"
HEADERS = {"User-Agent": "spelkompisen/1.0 (personligt analysverktyg)",
           "Accept": "application/json"}
MARKET_1X2 = "Full-time result"
SIGN_BY_SLUG = {"home": "1", "draw": "X", "away": "2"}
EVENT_LIMIT = 1000
BATCH = 40          # max id:n per batchat anrop — håll URL:en rimlig

# Våra ligor → Smarkets ligasegment i full_slug (verifierat 2026-07-24;
# alla tio hade kommande event, club-friendlies hela 102).
LEAGUE_SLUGS = {
    "allsvenskan": "sweden-allsvenskan",
    "superettan": "sweden-superettan",
    "eliteserien": "norway-premier-league",
    "obosligaen": "norway-first-division",
    "mls": "us-major-league-soccer",
    "friendlies": "club-friendlies",
    "premier_league": "england-premier-league",
    "serie_a": "italy-serie-a",
    "la_liga": "spain-la-liga",
    "bundesliga": "germany-bundesliga",
}


def _decimal(price: Optional[float]) -> Optional[float]:
    """Smarkets-pris (sannolikhet × 100) → decimalodds."""
    if not price or price <= 0:
        return None
    return round(10000.0 / float(price), 4)


def _split_name(name: str) -> tuple[str, str]:
    for sep in (" vs ", " v ", " - "):
        if sep in name:
            home, away = name.split(sep, 1)
            return home.strip(), away.strip()
    return name.strip(), ""


class Smarkets:
    def __init__(self, timeout: float = 25.0):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Smarkets":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        r = self._client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _batched(self, path_fmt: str, ids: list[str], key: str) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), BATCH):
            chunk = ",".join(ids[i:i + BATCH])
            out.extend(self._get(path_fmt.format(ids=chunk)).get(key) or [])
        return out

    def _quotes(self, market_ids: list[str]) -> dict:
        out: dict = {}
        for i in range(0, len(market_ids), BATCH):
            chunk = ",".join(market_ids[i:i + BATCH])
            out.update(self._get(f"/markets/{chunk}/quotes/") or {})
        return out

    def upcoming_events(self) -> list[dict]:
        """Alla kommande fotbollsevent (ett anrop, delas mellan ligorna)."""
        data = self._get("/events/", {"type": "football_match",
                                      "state": "upcoming",
                                      "limit": EVENT_LIMIT})
        return data.get("events") or []

    def league_events(self, league: str, strict: bool = False,
                      events: Optional[list[dict]] = None) -> list[dict]:
        """Normaliserade 1X2-rader för en av VÅRA ligenycklar.

        Skicka in `events` från upcoming_events() för att dela ett anrop
        mellan flera ligor. Returnerar per match:
          {id, home, away, start, odds{1,X,2}, back{1,X,2}, lay{1,X,2}}
        där `odds` är MID (fair-ankaret) och `back` är det man faktiskt kan
        ta. strict=True låter fel bubbla upp; annars tom lista.
        """
        try:
            slug = LEAGUE_SLUGS.get(league)
            if not slug:
                return []
            evs = events if events is not None else self.upcoming_events()
            mine = [e for e in evs
                    if f"/{slug}/" in (e.get("full_slug") or "")
                    and e.get("bettable")]
            if not mine:
                return []
            by_event = {e["id"]: e for e in mine}
            markets = self._batched("/events/{ids}/markets/",
                                    list(by_event), "markets")
            ftr = [m for m in markets
                   if m.get("name") == MARKET_1X2 and m.get("state") == "open"]
            if not ftr:
                return []
            market_ids = [m["id"] for m in ftr]
            contracts = self._batched("/markets/{ids}/contracts/",
                                      market_ids, "contracts")
            quotes = self._quotes(market_ids)

            by_market: dict[str, dict] = {}
            for contract in contracts:
                sign = SIGN_BY_SLUG.get(contract.get("slug"))
                if sign:
                    by_market.setdefault(contract["market_id"], {})[sign] = \
                        contract["id"]

            out = []
            for market in ftr:
                signs = by_market.get(market["id"]) or {}
                event = by_event.get(market.get("event_id"))
                if not event or len(signs) != 3:
                    continue
                mid, back, lay = {}, {}, {}
                for sign, contract_id in signs.items():
                    book = quotes.get(str(contract_id)) or {}
                    bids = book.get("bids") or []
                    offers = book.get("offers") or []
                    # bästa bid = högsta pris; bästa offer = lägsta pris
                    best_bid = max((b["price"] for b in bids), default=None)
                    best_offer = min((o["price"] for o in offers), default=None)
                    lay[sign] = _decimal(best_bid)
                    back[sign] = _decimal(best_offer)
                    if best_bid and best_offer:
                        mid[sign] = _decimal((best_bid + best_offer) / 2.0)
                if len(mid) != 3:
                    continue    # ofullständig orderbok — ingen halv rad
                home, away = _split_name(event.get("name") or "")
                out.append({
                    "id": event["id"], "home": home, "away": away,
                    "start": _iso(event.get("start_datetime")),
                    "odds": mid, "back": back, "lay": lay,
                })
            out.sort(key=lambda r: r.get("start") or "9")
            return out
        except Exception:
            if strict:
                raise
            return []


def _iso(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def league_events(league: str, strict: bool = False) -> list[dict]:
    """Bekvämlighet: en liga, egen klient (som kambi.league_events)."""
    with Smarkets() as client:
        return client.league_events(league, strict=strict)
