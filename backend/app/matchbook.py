"""Matchbook — betting exchange, publikt REST-API utan auth, session eller nyckel.

Verifierat 2026-07-27 (recon med curl, artig takt — se källgränsen i CLAUDE.md:
endpointen svarar med data givet enbart publika konstanter, alltså öppen):

  GET /edge/rest/lookups/sports                      -> soccer = sport-id 15
  GET /edge/rest/events?sport-ids=15&states=open
      &after=<unix>&before=<unix>&include-prices=true
      &price-depth=3&side=back&odds-type=DECIMAL
      &currency=EUR&market-states=open&market-types=one_x_two
        -> event + "Match Odds"-marknad + runners MED priser i SAMMA svar.

PRISFORMAT: `odds-type=DECIMAL` ger `decimal-odds` direkt. `side=back` ger
back-sidan (det man faktiskt kan ta); bästa tillgängliga back = HÖGSTA odds.
Varje prisnivå bär `available-amount` (likviditet i begärd valuta, EUR) —
pris och likviditet kommer alltså ur exakt samma svar och delar en enda
observationstid (kallplanens krav). Ligatillhörighet läses ur eventets
`meta-tags` (type=COMPETITION, `url-name`).

Svaren är `cache-control: private, no-cache` utan Age-huvud (uppmätt
2026-07-27) — `last_age_s` läses ändå defensivt som kambi/altenar, så
observationstiden förblir ärlig om ett CDN-lager dyker upp.

VARFÖR VI HAR DEN: TREDJE oberoende marknadsreferensen vid sidan av Pinnacle
och Smarkets, med FAKTISK likviditet nära avspark — mer ny information än
ännu ett Kambi-/Altenar-skin (docs/bookmaker-kallplan-2026-07-25.md,
"Omedelbart byggbart reservspår: Matchbook"). ENDAST skugginsamling i
snabbfönstret: Matchbook ingår INTE i BOOKS, INTE i ANCHOR_SOURCES/
ANCHOR2_SOURCE (oddset_value.SHADOW_SOURCES spärrar värdemotorn) och får
inte skapa flaggor, notiser, CLV eller steam. Tunn likviditet får aldrig
bekräfta eller underkänna en edge — den domen fälls långt senare, av det
frysta shadow-facitet efter >= 28 dagar.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx

BASE = "https://api.matchbook.com/edge/rest"
HEADERS = {"User-Agent": "spelkompisen/1.0 (personligt analysverktyg)",
           "Accept": "application/json"}
SPORT_SOCCER = 15
MARKET_1X2 = "Match Odds"      # fulltids-1X2; market-type "one_x_two"
PRICE_DEPTH = 3
PER_PAGE = 200
MAX_PAGES = 5                  # 3h-fönstret ryms på en sida; tak mot loop-fel

# Våra liganycklar -> Matchbook COMPETITION `url-name` i eventens meta-tags.
# Verifierade mot riktiga event i utbudet 2026-07-27. MLS, Serie A, La Liga
# och Bundesliga saknades helt i utbudet vid recon (35-dagarsfönster) — lägg
# till dem FÖRST när url-name observerats mot riktiga event, aldrig på gissning
# (fel mappning ger tyst tom täckning som ser ut som källfel).
LEAGUE_TAGS = {
    "allsvenskan": "sweden-allsvenskan",
    "superettan": "sweden-superettan",
    "eliteserien": "norway-premier-league",
    "obosligaen": "norway-first-division",
    "friendlies": "elite-club-friendlies",
    "premier_league": "english-premier-league",
}


def _split_name(name: str) -> tuple[str, str]:
    for sep in (" vs ", " v ", " - "):
        if sep in name:
            home, away = name.split(sep, 1)
            return home.strip(), away.strip()
    return name.strip(), ""


def _iso(value: Optional[str]) -> Optional[str]:
    """Matchbooks '...T20:15:00.000Z' -> projektets '...T20:15:00Z'."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unix(iso: Optional[str], fallback: dt.datetime) -> int:
    if iso:
        try:
            parsed = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return int(parsed.timestamp())
        except ValueError:
            pass
    return int(fallback.timestamp())


def _best_back(prices: list[dict]) -> tuple[Optional[float], Optional[float]]:
    """(odds, tillgängligt belopp) för bästa tillgängliga back-pris.

    Back-sidan är det man faktiskt kan ta; bästa = HÖGSTA decimalodds.
    Likviditeten är `available-amount` på EXAKT den prisnivån — inte summan
    över djupet (att blanda nivåer blandar priser)."""
    best_odds, best_amount = None, None
    for p in prices or []:
        if p.get("side") != "back":
            continue
        odds = p.get("decimal-odds") or p.get("odds")
        amount = p.get("available-amount")
        if not odds or odds <= 1.0 or not amount or amount <= 0:
            continue
        if best_odds is None or odds > best_odds:
            best_odds, best_amount = float(odds), float(amount)
    return best_odds, best_amount


def _competition_urls(event: dict) -> set[str]:
    return {t.get("url-name") for t in event.get("meta-tags") or []
            if t.get("type") == "COMPETITION"}


class Matchbook:
    def __init__(self, timeout: float = 25.0):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS)
        # HTTP `Age` ur senaste lyckade svar (0 = huvudet saknas — uppmätt
        # 2026-07-27 svarar Matchbook `no-cache` utan Age; defensivt ändå).
        self.last_age_s = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Matchbook":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        r = self._client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        try:
            self.last_age_s = max(0, int(r.headers.get("age") or 0))
        except (TypeError, ValueError):
            self.last_age_s = 0
        return r.json()

    def upcoming_events(self, after_iso: Optional[str] = None,
                        until_iso: Optional[str] = None,
                        within_h: float = 3.0) -> list[dict]:
        """Fotbollsevent med 1X2-priser i ETT tidsfönster (ett anrop, delas
        mellan ligorna). Fönstret är snabbfönstret: [after, until] där until
        default är after + within_h — Matchbook pollas BARA nära avspark.
        Priserna ligger i samma svar som eventen: en enda observationstid."""
        now = dt.datetime.now(dt.timezone.utc)
        after = _unix(after_iso, now)
        before = _unix(until_iso,
                       dt.datetime.fromtimestamp(after, dt.timezone.utc)
                       + dt.timedelta(hours=within_h))
        out: list[dict] = []
        for page in range(MAX_PAGES):
            data = self._get("/events", {
                "sport-ids": SPORT_SOCCER, "states": "open",
                "after": after, "before": before,
                "per-page": PER_PAGE, "offset": page * PER_PAGE,
                "include-prices": "true", "price-depth": PRICE_DEPTH,
                "side": "back", "odds-type": "DECIMAL", "currency": "EUR",
                "market-states": "open", "market-types": "one_x_two",
                "include-event-participants": "false"})
            events = data.get("events") or []
            out.extend(events)
            total = data.get("total")
            if not events or total is None or len(out) >= total:
                break
        return out

    def league_events(self, league: str, strict: bool = False,
                      events: Optional[list[dict]] = None) -> list[dict]:
        """Normaliserade 1X2-rader för en av VÅRA liganycklar.

        Skicka in `events` från upcoming_events() för att dela ett anrop
        mellan flera ligor (då görs INGET nytt anrop — observationstiden är
        eventhämtningens). Returnerar per match:
          {id, home, away, start, odds{1,X,2}, liquidity{1,X,2}}
        där `odds` är bästa tillgängliga back-odds och `liquidity` är
        tillgängligt belopp (EUR) på exakt den prisnivån. Ofullständig
        orderbok (tecken utan back-pris) => ingen halv rad. strict=True
        låter fel bubbla upp; annars tom lista."""
        try:
            tag = LEAGUE_TAGS.get(league)
            if not tag:
                return []
            evs = events if events is not None else self.upcoming_events()
            out = []
            for event in evs:
                if tag not in _competition_urls(event):
                    continue
                row = _parse_event(event)
                if row:
                    out.append(row)
            out.sort(key=lambda r: r.get("start") or "9")
            return out
        except Exception:
            if strict:
                raise
            return []


def _parse_event(event: dict) -> Optional[dict]:
    """Ett Matchbook-event -> normaliserad rad, eller None (fail-closed).

    Teckenmappning via runnernamn: 'Draw' -> X; övriga två matchas EXAKT
    (casefoldat) mot eventnamnets halvor. Matchar de inte hoppas eventet —
    hellre en saknad rad än en gissad hemma/borta-ordning."""
    market = next((m for m in event.get("markets") or []
                   if m.get("name") == MARKET_1X2
                   and m.get("market-type") == "one_x_two"
                   and m.get("status") == "open"), None)
    if not market:
        return None
    home, away = _split_name(event.get("name") or "")
    if not home or not away:
        return None
    odds: dict[str, float] = {}
    liquidity: dict[str, float] = {}
    for runner in market.get("runners") or []:
        if runner.get("status") != "open":
            return None      # suspenderad runner = ofullständig marknad
        name = (runner.get("name") or "").strip()
        if name.casefold() == "draw":
            sign = "X"
        elif name.casefold() == home.casefold():
            sign = "1"
        elif name.casefold() == away.casefold():
            sign = "2"
        else:
            return None      # okänd runner — gissa aldrig sida
        best_odds, amount = _best_back(runner.get("prices"))
        if best_odds is None:
            continue         # tomt tecken -> trion blir ofullständig nedan
        odds[sign] = best_odds
        liquidity[sign] = amount
    if len(odds) != 3:
        return None          # ofullständig orderbok — ingen halv rad
    return {"id": str(event.get("id")), "home": home, "away": away,
            "start": _iso(event.get("start")),
            "odds": odds, "liquidity": liquidity}


def league_events(league: str, strict: bool = False) -> list[dict]:
    """Bekvämlighet: en liga, egen klient (som smarkets.league_events)."""
    with Matchbook() as client:
        return client.league_events(league, strict=strict)
