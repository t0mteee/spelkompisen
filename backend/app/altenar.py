"""Altenar-drivna böcker (Betinia m.fl.) — publikt widget-API utan auth.

  GET /api/Widget/GetSportMenu  -> sporter/kategorier/champ-id:n
  GET /api/Widget/GetEvents     -> normaliserat: events→marketIds,
                                   markets (typeId 1 = "1x2") → oddIds,
                                   odds (typeId 1/2/3 = hemma/kryss/borta, decimalpris)
  GET /api/Widget/GetEventDetails -> alla marknader för en match, bland annat
                                     typeId 166 = totalt antal hörnor

integration = operatörens namn. Verifierat 2026-07-12: integration=betinia,
soccer sportId=66, champ-id:n Allsvenskan 3537, Eliteserien 3458, Superettan 4825.
Inofficiellt API — kan ändras utan förvarning.
"""
from __future__ import annotations

from typing import Optional

import httpx

BASE = "https://sb2frontend-altenar2.biahosted.com/api/Widget"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SOCCER = 66

# HTTP `Age` ur senaste lyckade svar (0 = huvudet saknas). Uppmätt 2026-07-26:
# Altenar svarar `cache-control: public,max-age=3` utan Age-huvud — fönstret är
# alltså ≤3 s i dag. Fältet läses defensivt (Pinnacle-mönstret) så
# observationstiden förblir ärlig om CDN-beteendet ändras.
last_age_s = 0


def _age_s(r) -> int:
    try:
        return max(0, int(r.headers.get("age") or 0))
    except (TypeError, ValueError):
        return 0


def _params(integration: str) -> dict:
    return {"culture": "sv-SE", "timezoneOffset": "-120", "integration": integration,
            "deviceType": "1", "numFormat": "en-GB", "countryCode": "SE"}


def _main_pair(pairs: list[tuple[float, float, float, bool]]) -> Optional[dict]:
    """Välj operatörens huvudlina, annars paret närmast jämna 2,0.

    Altenars oddsobjekt markerar huvudutfall med ``isMB``. Fallbacken gör
    parsern robust om markeringen försvinner men alternativa linor finns kvar.
    """
    if not pairs:
        return None
    a, b, line, _ = min(
        pairs, key=lambda pair: (
            not pair[3], abs(pair[0] - 2.0) + abs(pair[1] - 2.0)))
    return {"a": a, "b": b, "line": line}


def _corner_total(data: dict) -> Optional[dict]:
    """Normalisera huvudlinan för totalt antal hörnor ur GetEventDetails."""
    odds_by_id = {o["id"]: o for o in data.get("odds") or [] if o.get("id") is not None}
    by_line: dict[float, dict] = {}
    seen_markets: set[int] = set()
    for market in data.get("markets") or []:
        # Samma id förekommer även som Bet Builder-kopia. Den vanliga marknaden
        # är källan; id-spärren hindrar dubbelräkning om payloaden ändrar ordning.
        if market.get("typeId") != 166 or market.get("isBB") is True:
            continue
        market_id = market.get("id")
        if market_id in seen_markets:
            continue
        if market_id is not None:
            seen_markets.add(market_id)
        groups = market.get("desktopOddIds") or market.get("oddIds") or []
        odd_ids = [
            odd_id
            for group in groups
            for odd_id in (group if isinstance(group, list) else [group])
        ]
        for odd_id in odd_ids:
            odd = odds_by_id.get(odd_id)
            if (not odd or odd.get("oddStatus") not in (None, 0)
                    or not odd.get("price")):
                continue
            side = {12: "O", 13: "U"}.get(odd.get("typeId"))
            try:
                line = float(odd.get("sv"))
                price = round(float(odd["price"]), 4)
            except (TypeError, ValueError):
                continue
            if side:
                by_line.setdefault(line, {})[side] = price
                by_line[line][f"{side}_main"] = bool(odd.get("isMB"))

    pair = _main_pair([
        (values["O"], values["U"], line,
         bool(values.get("O_main") and values.get("U_main")))
        for line, values in by_line.items()
        if values.get("O") and values.get("U")
    ])
    if not pair:
        return None
    return {"O": pair["a"], "U": pair["b"], "line": pair["line"]}


def event_markets(event_id: str, integration: str = "betinia",
                  timeout: float = 20.0, strict: bool = False) -> dict:
    """Totalt antal hörnor (huvudlinan) för en match.

    GetEvents innehåller inte hörnmarknaden. Den publika eventdetaljen gör det,
    inklusive alternativa linor; endast Altenars markerade huvudlina returneras
    så att nuvarande lagring aldrig blandar tecken från olika linjer.
    """
    global last_age_s
    try:
        r = httpx.get(
            f"{BASE}/GetEventDetails",
            params={**_params(integration), "eventId": event_id},
            headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        last_age_s = _age_s(r)
        data = r.json()
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return {}
    corner = _corner_total(data)
    return {"cor": corner} if corner else {}


def league_events(champ_id: int, integration: str = "betinia",
                  timeout: float = 20.0, strict: bool = False) -> list[dict]:
    """Matcher + 1X2 för en liga. [{id, home, away, start, odds{'1','X','2'}}].
    Tom lista vid fel (best-effort — sidoböcker får aldrig fälla insamlingen)."""
    global last_age_s
    try:
        r = httpx.get(f"{BASE}/GetEvents",
                      params={**_params(integration), "champIds": champ_id,
                              "sportId": SOCCER, "eventCount": "50"},
                      headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        last_age_s = _age_s(r)
        data = r.json()
    except Exception:  # noqa: BLE001
        if strict:
            raise
        return []

    markets = {m["id"]: m for m in data.get("markets") or []}
    odds_by_id = {o["id"]: o for o in data.get("odds") or []}
    out: list[dict] = []
    for e in data.get("events") or []:
        name = e.get("name") or ""
        sep = " vs. " if " vs. " in name else " vs " if " vs " in name else None
        if not sep:
            continue
        home, away = (s.strip() for s in name.split(sep, 1))
        o1x2: dict[str, Optional[float]] = {"1": None, "X": None, "2": None}
        ou: dict = {}
        for mid in e.get("marketIds") or []:
            m = markets.get(mid)
            if not m:
                continue
            if m.get("typeId") == 1:               # typeId 1 = "1x2"
                for oid in m.get("oddIds") or []:
                    o = odds_by_id.get(oid)
                    if not o or not o.get("price"):
                        continue
                    sign = {1: "1", 2: "X", 3: "2"}.get(o.get("typeId"))
                    if sign:
                        o1x2[sign] = round(float(o["price"]), 3)
            elif m.get("typeId") == 18 and not ou:
                # TOTALT ANTAL MÅL (2026-07-25). Marknaden låg redan i svaret men
                # slängdes — loopen tog 1X2 och bröt. Det spelar roll: Expekts
                # deep-priser är IDENTISKA med SvS (samma Kambi-feed), medan
                # Altenar är en annan prismotor. Detta är alltså en genuint ny
                # prispunkt på mål, gratis, utan extra anrop. `sv` bär linjen och
                # typeId 12/13 är Över/Under. Hörnor och AH finns INTE i
                # GetEvents — de hämtas därför separat via GetEventDetails.
                sides = {}
                for oid in m.get("oddIds") or []:
                    o = odds_by_id.get(oid)
                    if not o or not o.get("price"):
                        continue
                    side = {12: "O", 13: "U"}.get(o.get("typeId"))
                    if side:
                        sides[side] = round(float(o["price"]), 3)
                try:
                    line = float(m.get("sv"))
                except (TypeError, ValueError):
                    line = None
                if line is not None and sides.get("O") and sides.get("U"):
                    ou = {**sides, "line": line}
        if o1x2["1"] or o1x2["2"]:
            row = {"id": str(e.get("id")), "home": home, "away": away,
                   "start": e.get("startDate"), "odds": o1x2}
            if ou:
                row["ou"] = ou
            out.append(row)
    return out
