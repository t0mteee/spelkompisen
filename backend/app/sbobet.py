"""SBOBET — asiatisk bok, publika sidor utan inloggning, cookie eller nyckel.

Verifierat 2026-11-06 från serverns svenska IP (källgränsen i CLAUDE.md: en
publik sida som svarar med data utan utmaning eller session är öppen):

  GET https://www.sbobet.com/euro/football/<ÅÅÅÅ-MM-DD>
        -> HTML där sidans egen kod bär alla dagens matcher i ETT
           `onUpdate('od',[...])`-block: liga-id, lag, avspark, 1X2 och
           asiatiskt handikapp med pris i samma svar.

Sidan publicerar sex dagar framåt (dag 7 svarar 302). robots.txt tillåter
`/euro/` med `Crawl-delay: 5` och förbjuder `/en/data/` och `/en/rdata/` —
de interna dataadresserna används därför ALDRIG, och klienten väntar minst
CRAWL_DELAY_S mellan anrop. Svaren är `Cache-Control: no-cache, no-store`
utan Age-huvud: observationstiden är hämtningstiden EFTER varje anrop
(observationstidsregeln p.2–3).

FORMAT (uppmätt 2026-11-06, 186 matcher 8/11):
  matchrad   [1, <liga-id>, [<event-id>, 'Hemma', 'Borta', '<kod>', n,
              'MM/DD/ÅÅÅÅ HH:MM', ...], <live|tom>, [[n, n, []], <marknader>], n]
  marknad    [<marknads-id>, [<typ>, 0, <typ>, 0|1, <maxinsats>, <lina>, n], [priser]]
  typ 1      asiatiskt handikapp, två priser (hemma, borta). Linan är vad
             HEMMALAGET GER: +0,75 = hemma −0,75. Vi lagrar som Pinnacle,
             hemmalagets handikapp, alltså line = −lina.
  typ 5      1X2, tre priser.
  Avsparken är i GMT+8 (alla 45 parade matcher 6–8/11 låg exakt 8 h före UTC).
  Liganamn finns inte i blocket, bara id — därav LEAGUE_IDS.

MARGINAL (8/11): handikapp median 4,7 % (min 3,1 %), 1X2 median 15 %. 1X2
är alltså INTE skarpt; handikappet är bokens riktiga marknad. Avviggad 1X2
skilde sig från Smarkets med median 1,1 pp (45 matcher), samma nivå som
Pinnacle mot Smarkets.

ROLL: referenskälla. `sbobet` ligger i oddset_value.ANCHOR_SOURCES, alltså
aldrig en bok att hitta värde hos (den spelas inte från Sverige och dess
1X2-marginal hade gett skräpflaggor), och skapar aldrig matchidentiteter.
"""
from __future__ import annotations

import datetime as dt
import re
import time
from typing import Callable, Optional

import httpx

BASE = "https://www.sbobet.com/euro/football"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
           "Accept": "text/html"}
CRAWL_DELAY_S = 5.0          # robots.txt
DAYS_AHEAD = 6               # dag 0..5; dag 6 svarar 302 (uppmätt 2026-11-06)
SOURCE_TZ = dt.timezone(dt.timedelta(hours=8))
TYPE_AH, TYPE_1X2 = 1, 5

# Våra ligor → SBOBET:s liga-id. Varje id är VERIFIERAT genom att matcher med
# det id:t parades med våra matcher på båda lagnamnen och exakt avspark
# (2026-11-06, sidorna 6–11/11). En liga utan belagt id får inget: ingen
# koppling är bättre än fel koppling.
LEAGUE_IDS: dict[str, frozenset[int]] = {
    "allsvenskan": frozenset({25}),          # 8 av 8
    "superettan": frozenset({185}),          # 7 av 8
    "eliteserien": frozenset({44386}),       # 4 av 8 (söndagen ej publicerad)
    "obosligaen": frozenset({28588}),        # 8 av 8
    "mls": frozenset({23}),                  # 14 av 15
    "premier_league": frozenset({3}),        # 10 av 10
    "championship": frozenset({86}),         # 10 av 12
    "serie_a": frozenset({4}),               # 10 av 10
    "la_liga": frozenset({6}),               # 10 av 10
    "bundesliga": frozenset({5}),            # 9 av 9
    "ligue_1": frozenset({8}),               # 9 av 9
    "danish_superliga": frozenset({8322}),   # 6 av 6
    "belgian_pro_league": frozenset({41314}),  # 9 av 9
    "primeira_liga": frozenset({100989}),    # 9 av 9
    # Cuperna, Besta deild, Bolivia, träningsmatcher och landslag: inget belagt
    # id ännu (cupmatcherna 5/11 hade redan börjat när sidorna lästes).
}

_OD_RE = re.compile(r"onUpdate\('od',")
_EVENT_RE = re.compile(
    r"\[1,(\d+),\[(\d+),'((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)','[^']*',\d+,"
    r"'(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d)'")
_MARKET_RE = re.compile(
    r"\[(\d+),\[(\d+),\d+,\d+,\d+,(\d+),(-?[\d.]+),\d+\],\[([\d.,]+)\]\]")


def _unescape(name: str) -> str:
    return name.replace("\\'", "'").replace("\\\\", "\\")


def _utc_iso(month: str, day: str, year: str, hour: str, minute: str) -> str:
    local = dt.datetime(int(year), int(month), int(day), int(hour), int(minute),
                        tzinfo=SOURCE_TZ)
    return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_page(html: str) -> list[dict]:
    """Alla matcher i en datumsida. Live-matcher (fält 4 icke-tomt) hoppas över.

    Varje rad: {id, league_id, home, away, start, odds{1,X,2}|None,
    ah: [{line, H, A, max_bet}]} med handikappet i hemmalagets tecken.
    Ett tomt block (ingen match) ger [], ett saknat block ValueError — en
    sida utan data är ett källfel tills motsatsen är bevisad (transportregeln).
    """
    start = _OD_RE.search(html)
    if not start:
        raise ValueError("sbobet: od-blocket saknas")
    body = html[start.end():]
    heads = list(_EVENT_RE.finditer(body))
    out = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        chunk = body[head.end():end]
        # Efter matchhuvudet: `],<live>,[[` — live-blocket börjar med '['.
        after = chunk[chunk.find("]") + 1:] if "]" in chunk else ""
        if after.startswith(",["):
            continue                                    # pågående match
        odds, ah = None, []
        for m in _MARKET_RE.finditer(chunk):
            typ, max_bet, line = int(m.group(2)), int(m.group(3)), float(m.group(4))
            prices = [float(p) for p in m.group(5).split(",") if p]
            if any(p <= 1.0 for p in prices):
                continue
            if typ == TYPE_1X2 and len(prices) == 3 and odds is None:
                odds = dict(zip(("1", "X", "2"), prices))
            elif typ == TYPE_AH and len(prices) == 2:
                ah.append({"line": -line if line else 0.0, "H": prices[0],
                           "A": prices[1], "max_bet": max_bet})
        out.append({"id": head.group(2), "league_id": int(head.group(1)),
                    "home": _unescape(head.group(3)), "away": _unescape(head.group(4)),
                    "start": _utc_iso(*head.group(5, 6, 7, 8, 9)),
                    "odds": odds, "ah": ah})
    return out


def main_line(ah: list[dict]) -> Optional[dict]:
    """Huvudlinan = den mest balanserade (minst skillnad mellan priserna),
    samma princip som en boks huvudlina; lika ⇒ den lägsta absoluta linan."""
    if not ah:
        return None
    return min(ah, key=lambda r: (abs(r["H"] - r["A"]), abs(r["line"])))


class Sbobet:
    def __init__(self, timeout: float = 20.0,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self._client = httpx.Client(timeout=timeout, headers=HEADERS,
                                    follow_redirects=False)
        self._sleep, self._clock = sleep, clock
        self._last_call: Optional[float] = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Sbobet":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _polite(self) -> None:
        if self._last_call is not None:
            wait = CRAWL_DELAY_S - (self._clock() - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def day(self, date: dt.date) -> dict:
        """En datumsida: {date, rows, observed_at, published}. 302 betyder att
        dagen inte publiceras än — ett lyckat svar som INTE bevisar frånvaro."""
        self._polite()
        r = self._client.get(f"{BASE}/{date.isoformat()}")
        observed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if r.status_code in (301, 302):
            return {"date": date, "rows": [], "observed_at": observed, "published": False}
        r.raise_for_status()
        return {"date": date, "rows": parse_page(r.text), "observed_at": observed,
                "published": True}

    def week(self, today: Optional[dt.date] = None) -> list[dict]:
        """Datumsidorna dag 0..DAYS_AHEAD−1 (SBOBET:s datum i GMT+8). Slutar vid
        första opublicerade dagen: senare dagar publiceras inte heller."""
        today = today or dt.datetime.now(SOURCE_TZ).date()
        out = []
        for i in range(DAYS_AHEAD):
            page = self.day(today + dt.timedelta(days=i))
            out.append(page)
            if not page["published"]:
                break
        return out


def day_span_utc(date: dt.date) -> tuple[str, str]:
    """[start, slut) i UTC för en SBOBET-dag (GMT+8)."""
    start = dt.datetime(date.year, date.month, date.day, tzinfo=SOURCE_TZ)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (start.astimezone(dt.timezone.utc).strftime(fmt),
            (start + dt.timedelta(days=1)).astimezone(dt.timezone.utc).strftime(fmt))
