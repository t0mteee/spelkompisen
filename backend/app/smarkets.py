"""Smarkets — betting exchange, publikt REST-API utan auth eller nyckel.

Verifierat 2026-07-24. Fyra anrop räcker för en hel liga (allt batchbart):

  GET /v3/events/?type=football_match&state=upcoming&limit=1000
        -> alla kommande fotbollsevent; ligan ligger i `full_slug`
           (t.ex. /sport/football/sweden-allsvenskan/2026/07/25/...).
           SIDINDELAT sedan 2026-09-19 (mellan 16:00Z och 16:14Z): Smarkets
           ger högst 50 event per svar, sorterade på id, oavsett `limit`, och
           pekar vidare med `pagination.next_page`. Utan bläddring såg vi bara
           de 50 äldsta eventen, och från 2026-09-22 gav nästan alla ligor
           0 rader med ok-status. upcoming_events() följer därför sidorna.
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
import urllib.parse
from typing import Optional

import httpx

BASE = "https://api.smarkets.com/v3"
HEADERS = {"User-Agent": "spelkompisen/1.0 (personligt analysverktyg)",
           "Accept": "application/json"}
MARKET_1X2 = "Full-time result"
SIGN_BY_SLUG = {"home": "1", "draw": "X", "away": "2"}
EVENT_LIMIT = 1000  # begärd sidstorlek; Smarkets ger högst 50 sedan 2026-09-19
MAX_PAGES = 60      # tak för bläddringen; 2026-10-03 räckte 19 sidor (916 event)
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
    # Avläst ur aktuella, bettable full_slug-rader 2026-09-02.
    "championship": "england-championship",
    "serie_a": "italy-serie-a",
    "la_liga": "spain-la-liga",
    "bundesliga": "germany-bundesliga",
    # Observerade i upcoming-listan 2026-08-09 med riktiga, bettable event.
    "danish_superliga": "denmark-superliga",
    "belgian_pro_league": "belgium-first-division-a",
    "primeira_liga": "portugal-primeira-liga",
    "bolivian_primera": "bolivia-primera-division",
    # Avläst ur Smarkets egna full_slug 2026-08-21 (8 kommande event), inte
    # mönsterhärledd: /sport/football/france-ligue-1/...
    "ligue_1": "france-ligue-1",
    # Smarkets kör TVÅ aktiva slugs för Besta deild (uppmätt 2026-07-27:
    # en bettable match under vardera) — värdet får därför vara en tupel.
    "bestadeild": ("iceland-premier-league", "iceland-besta-deild"),
    # Europacuperna. Ligafasens slugs avlästa 2026-10-03 ur Smarkets egna
    # full_slug i den sidbläddrade upcoming-listan (18 event vardera) och ur
    # kompetitionsnoderna under /sport/football: uefa-champions-league
    # (25363462), uefa-europa-league (25502999), uefa-europa-conference-league
    # (42371743). Kvalnoderna *-qualification (41813154/41813166/42279468) är
    # fortfarande aktiva; kvalslugsen observerades 2026-07-28 och gav rader
    # till 2026-08-27 (CL 39, EL 51, Conference 145 matcher), men listar inga
    # event förrän nästa kval. De tidigare huvudslugsen
    # `international-clubs-uefa-*` (CL/EL mönsterhärledda ur en Conference-
    # slug från juli) finns inte bland noderna, och Europa Leagues första
    # ligafasomgång 16–17/9, före sidindelningen, fick inga Smarkets-rader.
    "champions_league": ("uefa-champions-league",
                         "uefa-champions-league-qualification"),
    "europa_league": ("uefa-europa-league",
                      "uefa-europa-league-qualification"),
    "conference_league": ("uefa-europa-conference-league",
                          "uefa-europa-conference-league-qualification"),
    # Landslagen, avlästa 2026-10-03 ur den sidbläddrade listan: Nations
    # League A–D 10/8/8/2 event och `international-friendlies` 9 event. Den
    # tidigare noteringen "0 av 50" byggde på första sidan ensam. Noderna
    # uefa-nations-league-finals och -promotion-relegation finns men saknar
    # event och ligger utanför Pinnacle-scopet A–D. Landslag kopplas på
    # landskod (oddset._resolve_landslag), aldrig fuzzy; alla 69 landsnamn
    # i listan gav en FIFA-kod.
    "nations_league": ("uefa-nations-league-a", "uefa-nations-league-b",
                       "uefa-nations-league-c", "uefa-nations-league-d"),
    "landskamper": "international-friendlies",
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

    def _get(self, path: str,
             params: Optional[dict | list[tuple[str, str]]] = None) -> dict:
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
        """Alla kommande fotbollsevent, sida för sida (delas mellan ligorna).

        `next_page` följs ordagrant: det är Smarkets egen fråga för nästa sida
        (samma filter + `pagination_last_id`). Tar listan inte slut inom
        MAX_PAGES är det ett FEL, aldrig en kortare lista — collect() markerar
        varje kandidat som saknas i svaret `unavailable`, och en sida vi aldrig
        läste är ingen observation (observationstidsregeln 6).
        """
        params: dict | list[tuple[str, str]] = {
            "type": "football_match", "state": "upcoming", "limit": EVENT_LIMIT}
        events: list[dict] = []
        for _ in range(MAX_PAGES):
            data = self._get("/events/", params)
            events.extend(data.get("events") or [])
            next_page = (data.get("pagination") or {}).get("next_page")
            if not next_page:
                return events
            params = urllib.parse.parse_qsl(
                urllib.parse.urlsplit(next_page).query)
        raise RuntimeError(
            f"smarkets: listan tog inte slut på {MAX_PAGES} sidor "
            f"({len(events)} event) — en ofullständig lista används inte")

    def league_events(self, league: str, strict: bool = False,
                      events: Optional[list[dict]] = None) -> list[dict]:
        """Normaliserade 1X2-rader för en av VÅRA ligenycklar.

        Skicka in `events` från upcoming_events() för att dela bläddringen
        mellan flera ligor. Returnerar per match:
          {id, home, away, start, odds{1,X,2}, back{1,X,2}, lay{1,X,2}}
        där `odds` är MID (fair-ankaret) och `back` är det man faktiskt kan
        ta. strict=True låter fel bubbla upp; annars tom lista.
        """
        try:
            slugs = LEAGUE_SLUGS.get(league)
            if not slugs:
                return []
            if isinstance(slugs, str):
                slugs = (slugs,)
            evs = events if events is not None else self.upcoming_events()
            mine = [e for e in evs
                    if any(f"/{s}/" in (e.get("full_slug") or "")
                           for s in slugs)
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
