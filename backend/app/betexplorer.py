"""Betexplorer — bet365 som REFERENSBOK (beslut 2026-11-06-betexplorer-bet365, val 0).

Verifierat 2026-11-06 från serverns svenska IP (källgränsen i CLAUDE.md: en
publik sida som svarar med data utan utmaning eller session är öppen; robots.txt
spärrar bara /ad/, /redirect/, /bookmaker/ och vissa ?-parametrar):

  GET /football/<land>/<liga>/fixtures/
        -> HTML med ligans kommande matcher: avspark, lag och matchens
           åttateckens-id sist i länken (/everton-coventry/OUYQUF9b/).
  GET /match-odds/<id>/0/<1x2|ou|ah>/odds/?lang=en
        -> JSON {"odds": "<html>"}: en rad per bok, för Ö/U och AH en tabell
           per lina. Sidan själv anropar adressen (match_load_tabs i sidans
           publika JavaScript) med Referer och X-Requested-With.

Ingen nyckel, ingen cookie, ingen utmaning. `/archive-odds/` (prishistoriken per
bok) används ALDRIG: historiska priser bakfylls inte (observationstidsregeln).

FORMAT (uppmätt 2026-11-06, Everton–Coventry):
  bokrad     <tr data-bid="16" ...> med bokens namn; bet365 = data-bookie="bet365".
  priscell   <td class="... table-main__detail-odds ..." data-odd="1.67"
             data-created="06,11,2026,10,46"> — data-created är när BOKEN
             senast ändrade priset, i svensk tid (UTC+1 i november: 10:46 =
             09:46Z, hämtat 09:57Z). Den tiden sparas som bokens ändringstid,
             aldrig som vår observationstid.
  lina       <td class="table-main__doubleparameter">-2.5, -3</td>: kvartslina
             = medelvärdet (−2,75). AH-linan är HEMMALAGETS handikapp (Everton
             −2,75 till 7,00), samma tecken som Pinnacle lagras med.
  avspark    fixtursidans "Today 21:00", "Tomorrow 13:30", "08.11. 15:00" eller
             "01.01.2027 21:00" i svensk tid; en tom cell (&nbsp;) betyder samma
             tid som raden ovanför. Everton–Coventry "Today 21:00" = 20:00Z.

TAKT: minst CRAWL_DELAY_S mellan anropen (robots.txt anger ingen; Driften
provade med 2 s). Svaren bär `max-age=3600, max-age=1` och Age: 0; Age dras
ändå av före observationstiden (observationstidsregeln p.2), som sätts EFTER
varje anrop (p.3).

ROLL: referensbok. `bet365` ligger i oddset_value.ANCHOR_SOURCES (via
REFERENCE_BOOKS): aldrig en bok att hitta värde hos, aldrig ett ankare
(ANCHOR_BY_MARKET), skapar aldrig matchidentiteter. Den visas i Oddset-vyn
för jämförelse mot Svenska Spel och de skarpa referenserna.
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import re
import time
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import httpx

BASE = "https://www.betexplorer.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
           "Accept-Language": "en"}
CRAWL_DELAY_S = 3.0
SOURCE_TZ = ZoneInfo("Europe/Stockholm")
BOOKS = {"bet365": "bet365"}           # vår källnyckel → Betexplorers data-bookie
BET_TYPES = ("1x2", "ou", "ah")
PAIR_KEYS = {"ou": ("O", "U"), "ah": ("H", "A")}

# Våra ligor → Betexplorers ligasida. Varje sökväg är VERIFIERAD genom att
# fixtursidans matcher parades med våra matcher på lagnamn och avspark
# (2026-11-06). En liga utan belagd sida får inget: ingen koppling är bättre
# än fel koppling. Landslag ingår inte (kopplas bara på landskod, och
# Betexplorers landslagssidor är inte belagda).
LEAGUE_PATHS: dict[str, str] = {
    "allsvenskan": "/football/sweden/allsvenskan/",          # 8 av 8
    "superettan": "/football/sweden/superettan/",            # 8 av 8
    "eliteserien": "/football/norway/eliteserien/",          # 8 av 8
    "obosligaen": "/football/norway/obos-ligaen/",           # 8 av 8
    "mls": "/football/usa/mls/",                             # 15 av 15
    "premier_league": "/football/england/premier-league/",   # 10 av 10
    "championship": "/football/england/championship/",      # 12 av 12
    "serie_a": "/football/italy/serie-a/",                   # 10 av 10
    "la_liga": "/football/spain/laliga/",                    # 10 av 10
    "bundesliga": "/football/germany/bundesliga/",           # 9 av 9
    "ligue_1": "/football/france/ligue-1/",                  # 9 av 9
    "danish_superliga": "/football/denmark/superliga/",      # 6 av 6
    "belgian_pro_league": "/football/belgium/jupiler-pro-league/",  # 9 av 9
    "primeira_liga": "/football/portugal/liga-portugal/",    # 9 av 9
    "champions_league": "/football/europe/champions-league/",  # 18 av 18 (24–25/11)
    # Europa och Conference League: sidorna listar 26/11 men vi har inga
    # matcher där ännu, så sökvägen är inte belagd. Besta deild och Bolivia:
    # inga kommande matcher. Träningsmatcher och landslag: inte prövade.
}

# TAKT. Bara djupvarvet (var 30:e min), bara matcher inom DAYS_AHEAD dygn,
# och en match frågas igen först när dess intervall gått (närmare avspark =
# tätare). Passet stoppar NYA anrop efter BUDGET_S sekunder och efter
# MAX_FAILURES transportfel i rad. Tre anrop per match (1X2, Ö/U, AH).
DAYS_AHEAD = 7
BUDGET_S = 240.0
MAX_FAILURES = 3
REFRESH_MIN = ((3.0, 25), (24.0, 115), (None, 715))   # (timmar kvar ≤, minuter)
# Uppmätt 2026-11-06: ~3,7 s per anrop (Ö/U- och AH-svaren är ~1,2 MB), alltså
# ~22 matcher per pass. Behovet med intervallen ovan är ~40 matcher i timmen.

_ROW_SPLIT = re.compile(r"<tr[\s>]")
_FIXTURE_RE = re.compile(
    r'table-main__datetime">([^<]*)</td>\s*<td[^>]*>\s*<a href="([^"]+)"[^>]*>'
    r"\s*<span>([^<]*)</span>\s*-\s*<span>([^<]*)</span>")
_EVENT_ID_RE = re.compile(r"/([A-Za-z0-9]{8})/?$")
_CELL_RE = re.compile(r"<td[^>]*table-main__detail-odds[^>]*>")
_ATTR_ODD = re.compile(r'data-odd="([\d.]+)"')
_ATTR_CREATED = re.compile(r'data-created="(\d+),(\d+),(\d{4}),(\d+),(\d+)"')
_LINE_RE = re.compile(r'table-main__doubleparameter">([^<]*)<')
_TODAY = re.compile(r"^(Today|Tomorrow|Yesterday)\s+(\d\d):(\d\d)$")
_DATE = re.compile(r"^(\d\d)\.(\d\d)\.(\d{4})?\s+(\d\d):(\d\d)$")


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(y: int, mo: int, d: int, h: int, mi: int) -> dt.datetime:
    return dt.datetime(y, mo, d, h, mi, tzinfo=SOURCE_TZ)


def parse_start(text: str, now: dt.datetime) -> Optional[str]:
    """Fixtursidans avspark i UTC. `now` (UTC) avgör Today/Tomorrow och året
    när det saknas: närmaste datum som inte ligger mer än 60 dagar bakåt."""
    text = htmllib.unescape(text).replace("\xa0", " ").strip()
    local_now = now.astimezone(SOURCE_TZ)
    m = _TODAY.match(text)
    if m:
        shift = {"Today": 0, "Tomorrow": 1, "Yesterday": -1}[m.group(1)]
        day = local_now.date() + dt.timedelta(days=shift)
        return _iso(_local(day.year, day.month, day.day, int(m.group(2)), int(m.group(3))))
    m = _DATE.match(text)
    if not m:
        return None
    d, mo, h, mi = int(m.group(1)), int(m.group(2)), int(m.group(4)), int(m.group(5))
    if m.group(3):
        return _iso(_local(int(m.group(3)), mo, d, h, mi))
    t = _local(local_now.year, mo, d, h, mi)
    if t < local_now - dt.timedelta(days=60):
        t = _local(local_now.year + 1, mo, d, h, mi)
    return _iso(t)


def parse_fixtures(html: str, now: dt.datetime) -> list[dict]:
    """Fixtursidans matcher: {event_id, home, away, start}. En tom tidcell
    ärver raden ovanför inom samma tabell; en rubrikrad (ny omgång) nollställer.
    En sida utan fixturtabell ger ValueError — en sida utan data är ett
    källfel tills motsatsen är bevisad (transportregeln)."""
    if "table-main--leaguefixtures" not in html:
        raise ValueError("betexplorer: fixturtabellen saknas")
    out, carried = [], None
    for chunk in _ROW_SPLIT.split(html):
        if "<th" in chunk[:200]:
            carried = None
            continue
        m = _FIXTURE_RE.search(chunk)
        if not m:
            continue
        ev = _EVENT_ID_RE.search(m.group(2))
        if not ev:
            continue
        raw = htmllib.unescape(m.group(1)).replace("\xa0", " ").strip()
        start = parse_start(raw, now) if raw else carried
        carried = start
        if not start:
            continue
        out.append({"event_id": ev.group(1),
                    "home": htmllib.unescape(m.group(3)).strip(),
                    "away": htmllib.unescape(m.group(4)).strip(),
                    "start": start})
    return out


def _changed(cell: str, observed_at: str) -> Optional[str]:
    m = _ATTR_CREATED.search(cell)
    if not m:
        return None
    d, mo, y, h, mi = (int(x) for x in m.groups())
    try:
        t = _iso(_local(y, mo, d, h, mi))
    except ValueError:
        return None
    # En ändringstid efter vår observation är ett tolkningsfel (tidszon),
    # aldrig en framtida ändring — den sparas inte.
    return t if t <= observed_at else None


def _book_row(chunk_html: str, bookie: str) -> Optional[str]:
    for row in _ROW_SPLIT.split(chunk_html):
        if f'data-bookie="{bookie}"' in row:
            return row
    return None


def _cells(row: str, observed_at: str) -> list[tuple[Optional[float], Optional[str]]]:
    out = []
    for m in _CELL_RE.finditer(row):
        tag = m.group(0)
        odd = _ATTR_ODD.search(tag)
        price = float(odd.group(1)) if odd else None
        out.append((price if price and price > 1.0 else None,
                    _changed(tag, observed_at)))
    return out


def _line_value(text: str) -> Optional[float]:
    try:
        parts = [float(p.replace("+", "").strip())
                 for p in htmllib.unescape(text).split(",") if p.strip()]
    except ValueError:
        return None
    return round(sum(parts) / len(parts), 2) if parts else None


def parse_odds(body: str, bet_type: str, bookie: str, observed_at: str) -> Optional[dict]:
    """En boks priser ur ett /match-odds/-svar. None = boken saknas i svaret.

    1x2: {"odds": {1,X,2}, "changed": {tecken: UTC}} (ofullständig rad ⇒ None).
    ou/ah: {"lines": [{"line", k1, k2, "changed": {...}}]} med bara kompletta
    linor. Ett svar som inte är JSON med "odds" ger ValueError (källfel)."""
    try:
        data = json.loads(body)
        page = data["odds"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"betexplorer: oväntat svar ({exc})") from exc
    if not isinstance(page, str):
        raise ValueError("betexplorer: odds-fältet är inte HTML")
    if bet_type == "1x2":
        row = _book_row(page, bookie)
        if row is None:
            return None
        cells = _cells(row, observed_at)
        if len(cells) != 3 or any(p is None for p, _ in cells):
            return None
        signs = ("1", "X", "2")
        return {"odds": {s: p for s, (p, _) in zip(signs, cells)},
                "changed": {s: c for s, (_, c) in zip(signs, cells) if c}}
    k1, k2 = PAIR_KEYS[bet_type]
    lines, found = [], False
    for section in page.split("<tbody")[1:]:
        row = _book_row(section, bookie)
        if row is None:
            continue
        found = True
        lm = _LINE_RE.search(row)
        line = _line_value(lm.group(1)) if lm else None
        cells = _cells(row, observed_at)
        if line is None or len(cells) != 2 or any(p is None for p, _ in cells):
            continue
        (p1, c1), (p2, c2) = cells
        lines.append({"line": line, k1: p1, k2: p2,
                      "changed": {k: c for k, c in ((k1, c1), (k2, c2)) if c}})
    return {"lines": lines} if found else None


def refresh_minutes(start: str, now: dt.datetime) -> int:
    """Minsta tid mellan två frågor om samma match givet tid kvar till avspark."""
    try:
        t = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return REFRESH_MIN[-1][1]
    hours = (t - now).total_seconds() / 3600.0
    for limit, minutes in REFRESH_MIN:
        if limit is None or hours <= limit:
            return minutes
    return REFRESH_MIN[-1][1]


def refresh_due(start: str, asked_at: Optional[str], now: dt.datetime) -> bool:
    """Ska matchen frågas i det här passet? Aldrig frågad ⇒ ja."""
    if not asked_at:
        return True
    try:
        last = dt.datetime.fromisoformat(asked_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now - last).total_seconds() >= refresh_minutes(start, now) * 60


def main_line(lines: list[dict], k1: str, k2: str) -> Optional[dict]:
    """Huvudlinan = den mest balanserade (minst skillnad mellan priserna),
    samma princip som SBOBET; lika ⇒ den lägsta absoluta linan."""
    if not lines:
        return None
    return min(lines, key=lambda r: (abs(r[k1] - r[k2]), abs(r["line"])))


class Betexplorer:
    def __init__(self, timeout: float = 20.0,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS,
                                    follow_redirects=False)
        self._sleep, self._clock, self._now = sleep, clock, now
        self._last_call: Optional[float] = None
        self.calls = 0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Betexplorer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _polite(self) -> None:
        if self._last_call is not None:
            wait = CRAWL_DELAY_S - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()
        self.calls += 1

    def _observed(self, r: httpx.Response) -> str:
        """Hämtningstid EFTER anropet minus HTTP Age (CDN-cachen)."""
        now = self._now()
        try:
            age = max(0, int(r.headers.get("age") or 0))
        except ValueError:
            age = 0
        return _iso(now - dt.timedelta(seconds=age))

    def fixtures(self, path: str) -> dict:
        """En ligas fixtursida: {rows, observed_at}."""
        self._polite()
        r = self._client.get(f"{BASE}{path}fixtures/")
        observed = self._observed(r)
        r.raise_for_status()
        return {"rows": parse_fixtures(r.text, self._now()), "observed_at": observed}

    def odds(self, event_id: str, bet_type: str, bookie: str,
             referer: Optional[str] = None) -> dict:
        """En match och marknad: {parsed, observed_at}. parsed None = boken
        saknas i ett lyckat svar (en observation, inte ett källfel)."""
        self._polite()
        headers = {"X-Requested-With": "XMLHttpRequest",
                   "Accept": "application/json, text/javascript, */*; q=0.01"}
        if referer:
            headers["Referer"] = referer
        r = self._client.get(f"{BASE}/match-odds/{event_id}/0/{bet_type}/odds/",
                             params={"lang": "en"}, headers=headers)
        observed = self._observed(r)
        r.raise_for_status()
        return {"parsed": parse_odds(r.text, bet_type, bookie, observed),
                "observed_at": observed}
