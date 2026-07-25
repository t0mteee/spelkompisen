"""Altenar-drivna böcker (Betinia m.fl.) — publikt widget-API utan auth.

  GET /api/Widget/GetSportMenu  -> sporter/kategorier/champ-id:n
  GET /api/Widget/GetEvents     -> normaliserat: events→marketIds,
                                   markets (typeId 1 = "1x2") → oddIds,
                                   odds (typeId 1/2/3 = hemma/kryss/borta, decimalpris)

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


def _params(integration: str) -> dict:
    return {"culture": "sv-SE", "timezoneOffset": "-120", "integration": integration,
            "deviceType": "1", "numFormat": "en-GB", "countryCode": "SE"}


def league_events(champ_id: int, integration: str = "betinia",
                  timeout: float = 20.0, strict: bool = False) -> list[dict]:
    """Matcher + 1X2 för en liga. [{id, home, away, start, odds{'1','X','2'}}].
    Tom lista vid fel (best-effort — sidoböcker får aldrig fälla insamlingen)."""
    try:
        r = httpx.get(f"{BASE}/GetEvents",
                      params={**_params(integration), "champIds": champ_id,
                              "sportId": SOCCER, "eventCount": "50"},
                      headers=HEADERS, timeout=timeout)
        r.raise_for_status()
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
                # GetEvents — de kräver egen recon av Altenars eventvy.
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
