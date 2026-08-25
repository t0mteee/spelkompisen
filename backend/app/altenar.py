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

import concurrent.futures as cf
from typing import Optional

import httpx

BASE = "https://sb2frontend-altenar2.biahosted.com/api/Widget"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
SOCCER = 66
# Hur många liveligor som frågas samtidigt. Anropen är oberoende och
# CDN-cachade (max-age 3 s), men taket håller nere hur hårt vi trycker på
# källan i ett enda svep — artighet, inte prestandagräns.
LIVE_CHAMP_WORKERS = 8
# Altenars riktiga live-marknad för matchresultat. `typeId == 1` räcker
# INTE som identitet: providern skapar också syntetiska `isAlt`-marknader med
# samma typ-id för exempelvis "Fjärde målet". Där betyder utfall 7 "Ingen",
# inte kryss. Att läsa den som 1X2 gav Bodø/Glimt 21 % vinstchans vid 3–0 och
# gjorde en Topptipsrad med alla åtta aktuella tecken till bara 0,8 %.
LIVE_1X2_SPORT_MARKET_ID = 70472

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


def _live_rows(data: dict) -> list[dict]:
    """Normalisera GetLiveEvents utan att göra suspenderade odds spelbara.

    Livepayloaden bär både matchens 1X2 och Ö/U. Tidigare kastades 1X2 bort,
    trots att just den marknaden behövs när en redan inlämnad poolkupong
    rättas live och Kambi tillfälligt har stängt sitt eget 1X2.
    """
    markets = {m.get("id"): m for m in data.get("markets") or []}
    odds_by_id = {o.get("id"): o for o in data.get("odds") or []}
    out = []
    for event in data.get("events") or []:
        if event.get("status") != 1 or event.get("sportId") != SOCCER:
            continue
        name = event.get("name") or ""
        sep = " vs. " if " vs. " in name else " vs " if " vs " in name else None
        if not sep:
            continue
        home, away = (part.strip() for part in name.split(sep, 1))
        event_markets = [markets.get(mid) for mid in event.get("marketIds") or []]
        total_market = next((market for market in event_markets
                             if (market or {}).get("typeId") == 18), None)
        # Fail closed på den semantiska marknadsidentiteten. `typeId=1` finns
        # även på alternativa nästa-mål-/förlängningsmarknader; ett saknat
        # livepris är bättre än ett komplett men felmärkt 1X2-pris.
        one_x_two_market = next((market for market in event_markets
                                if (market or {}).get("typeId") == 1
                                and not (market or {}).get("isAlt")
                                and (market or {}).get("sportMarketId")
                                == LIVE_1X2_SPORT_MARKET_ID), None)
        status, total = "not_offered", None
        if total_market:
            sides = {}
            suspended = False
            for odd_id in total_market.get("oddIds") or []:
                odd = odds_by_id.get(odd_id) or {}
                side = {12: "O", 13: "U"}.get(odd.get("typeId"))
                if not side:
                    continue
                if odd.get("oddStatus") not in (None, 0) or not odd.get("price"):
                    suspended = True
                    continue
                try:
                    sides[side] = round(float(odd["price"]), 4)
                except (TypeError, ValueError):
                    continue
            try:
                line = float(total_market.get("sv"))
            except (TypeError, ValueError):
                line = None
            if line is not None and sides.get("O") and sides.get("U"):
                total, status = {**sides, "line": line}, "captured"
            elif suspended:
                status = "suspended"

        one_x_two_status, one_x_two = "not_offered", None
        if one_x_two_market:
            prices = {}
            suspended = False
            for odd_id in one_x_two_market.get("oddIds") or []:
                odd = odds_by_id.get(odd_id) or {}
                # På den riktiga matchresultatmarknaden är 1/2/3
                # hemma/kryss/borta. Typ 7 betyder "Ingen" på nästa
                # mål-marknaden och får aldrig översättas till kryss.
                sign = {1: "1", 2: "X", 3: "2"}.get(odd.get("typeId"))
                if not sign:
                    continue
                if odd.get("oddStatus") not in (None, 0) or not odd.get("price"):
                    suspended = True
                    continue
                try:
                    price = round(float(odd["price"]), 4)
                except (KeyError, TypeError, ValueError):
                    continue
                if price > 1.0:
                    prices[sign] = price
            if set(prices) == {"1", "X", "2"}:
                one_x_two, one_x_two_status = prices, "captured"
            elif suspended:
                one_x_two_status = "suspended"
        out.append({
            "id": str(event.get("id")), "home": home, "away": away,
            "start": event.get("startDate"), "status": status,
            "ou": total, "offers": [total] if total else [],
            "odds_status": one_x_two_status, "odds": one_x_two,
        })
    return out


def live_events(integration: str = "ninjacasinose", timeout: float = 12.0,
                strict: bool = False) -> list[dict]:
    """Alla pågående fotbollsmatcher hos en Altenar-operatör.

    Sportmenyn talar om exakt vilka fotbollsligor som har liveevent. Bara de
    ligorna frågas via den separata GetLiveEvents-vägen (CDN max-age 3 s i
    drift), så vi behöver varken gissa champ-id:n eller dra hela utbudet.
    """
    global last_age_s
    try:
        client = httpx.Client(timeout=timeout, headers=HEADERS)
        menu_response = client.get(
            f"{BASE}/GetSportMenu", params=_params(integration))
        menu_response.raise_for_status()
        menu = menu_response.json()
        soccer = next((sport for sport in menu.get("sports") or []
                       if sport.get("id") == SOCCER), {})
        soccer_categories = set(soccer.get("catIds") or [])
        soccer_champs = {
            champ_id
            for category in menu.get("categories") or []
            if category.get("id") in soccer_categories
            for champ_id in category.get("champIds") or []
        }
        live_champs = [
            int(champ["id"])
            for champ in menu.get("champs") or []
            if champ.get("hasLiveEvents") and champ.get("id") in soccer_champs
        ]
        # En lördagseftermiddag har Altenar ~85 fotbollsligor med liveevent, och
        # varje liga är ett eget anrop. Sekventiellt kostade det 7,7 s (uppmätt
        # 2026-08-22, 0,09 s per anrop) — hela fördröjningen i kupongernas
        # liverättning, som bara behöver pris på en handfull matcher.
        #
        # Anropen är oberoende, så de görs samtidigt. Antalet anrop är
        # OFÖRÄNDRAT — det är ordningen som ändras, inte trafiken — och
        # `LIVE_CHAMP_WORKERS` håller nere hur många som är i luften mot
        # källan samtidigt. Resultatet sätts in på champ-ligans egen plats så
        # att raden får samma ordning som förut; en parallell körning får
        # inte göra utdatan icke-deterministisk.
        def _champ_rows(champ_id: int):
            response = client.get(
                f"{BASE}/GetLiveEvents",
                params={**_params(integration), "champIds": champ_id,
                        "sportId": SOCCER, "eventCount": "50"})
            response.raise_for_status()
            return _age_s(response), _live_rows(response.json())

        per_champ: list[Optional[tuple]] = [None] * len(live_champs)
        if live_champs:
            with cf.ThreadPoolExecutor(
                    max_workers=min(LIVE_CHAMP_WORKERS, len(live_champs))) as pool:
                futures = {pool.submit(_champ_rows, champ_id): index
                           for index, champ_id in enumerate(live_champs)}
                for future in cf.as_completed(futures):
                    # Ett fel i EN liga ska falla som förut: hela anropet är
                    # antingen en observation eller inget, så undantaget får
                    # propagera till den befintliga hanteringen nedan.
                    per_champ[futures[future]] = future.result()
        rows = []
        ages = [_age_s(menu_response)]
        for entry in per_champ:
            if entry is None:
                continue
            age, champ_rows = entry
            ages.append(age)
            rows.extend(champ_rows)
        client.close()
        last_age_s = max(ages, default=0)
        return rows
    except Exception:  # noqa: BLE001
        try:
            client.close()
        except (NameError, UnboundLocalError):
            pass
        if strict:
            raise
        return []
