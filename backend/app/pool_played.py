"""Spårning av VERKLIGT spelade kuponger — facit och livestatus.

Två saker som PH3-ledgern inte kan ge:

1. **Riktigt facit.** Ledgern fryser kontrafaktiska benchmarksystem som aldrig
   lämnades in, och späder därför deras vinst mot observerad nivåpott. En kupong
   Saman faktiskt spelat ligger redan i potten — SvS publicerade belopp per
   vinnare inkluderar honom. Utdelningen är alltså `antal egna rader på nivån ×
   publicerat belopp`, RAKT. Att återanvända utspädningen här hade gett för låg
   siffra; att använda den här formeln i ledgern hade gett för hög.
2. **Livestatus för reducerade system.** SvS eget draw-API bär matchresultat
   under omgången (`match.result` med `sportEventResultType == "Current"`, plus
   `status`/`statusId`), så vi kan räkna rätt-så-långt per rad och se vilka
   rader som fortfarande kan nå en vinstnivå — utan någon ny datakälla.

FACIT ≠ LIVESTATUS (granskningsfix F4 2026-07-26): draw-payloadens
Current-score är enbart livevy. Slutfacit tas ALLTID ur settlementlagret
(`pool_event_settlement.outcome` per eventNumber — samma kanon som PH3):
Current-score kan avvika från pooltecknet (förlängning i cupmatch), och en
struken match får sitt tecken FASTSTÄLLT av SvS — den är aldrig "rätt för
alla rader". Radernas tecken paras alltid mot eventNumber via kupongens
`events_order`, aldrig positionsvis mot payloadordningen.

Ingenting här lägger spel. Knappen bokför bara att användaren själv har lämnat
in kupongen.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import random
from typing import Optional

from .storage import Storage

SIGNS = ("1", "X", "2")
# v2 (2026-07-26): facit ur pool_event_settlement (officiellt outcome per
# eventNumber) i stället för draw-payloadens Current-score; events_order-join;
# hård breddvakt. v1 hann aldrig settla en kupong i drift.
SETTLEMENT_VERSION = "played-v2"

# SvS-statusar: matchen är färdigspelad och tecknet står fast.
# 31 = "Slut", 33 = "Slut efter straffläggning". 33 saknades och gjorde två
# FÄRDIGSPELADE cupmatcher till "pågående" i live-rättningen 2026-08-08
# (Barnsley–Wigan och Preston–Huddersfield i Stryktipset 4965): kortet sa
# 8/13 avgjorda när det var 10/13, och påstod att fem matcher rullade när
# det bara var tre.
# 32 = "Slut efter förlängning", observerad 2026-08-11 (Apollon Limassol–Brann).
# Samma lucka som 33 ("Slut efter straffläggning") som fälldes 2026-08-08:
# matchen räddades bara av att ett publicerat Fulltime också räknas som slut.
FINISHED_STATUS_IDS = frozenset({31, 32, 33})
FINISHED_STATUS_WORDS = frozenset({"slut", "ended", "finished", "avslutad"})

# Spel EFTER ordinarie tid. Poolen avgörs på ordinarie tid, så här står tecknet
# redan fast trots att matchen inte är slut. Observerat 2026-08-11: statusId 20
# = "Första övertidsperioden" (Apollon Limassol–Brann, Topptipset 4260).
# Orden är skyddsnät för de koder vi ännu inte sett — SvS numrerar
# övertidsperioder, paus i förlängning och straffläggning var för sig, och en
# okänd kod får inte tyst göra en avgjord match "öppen" igen.
EXTRA_TIME_STATUS_IDS = frozenset({20, 21, 22, 23, 24, 25})
EXTRA_TIME_STATUS_WORDS = ("övertid", "overtid", "förläng", "forlang",
                           "straff", "extra time", "penalt")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows_hash(rows: list[str]) -> str:
    """Identitet för kupongen: exakt raduppsättning i exakt ordning."""
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()[:16]


def normalize_rows(rows) -> list[str]:
    """Ta emot ['1','X','2'] per rad ELLER '1X2...' och returnera strängrader."""
    out = []
    for row in rows or []:
        text = "".join(row) if isinstance(row, (list, tuple)) else str(row)
        text = "".join(ch for ch in text.upper() if ch in ("1", "X", "2"))
        if text:
            out.append(text)
    return out


def record(store: Storage, payload: dict) -> dict:
    """Bokför en spelad kupong. Idempotent per (produkt, omgång, radhash)."""
    rows = normalize_rows(payload.get("rows"))
    if not rows:
        raise ValueError("kupongen saknar rader")
    width = {len(r) for r in rows}
    if len(width) != 1:
        raise ValueError("raderna har olika antal tecken")
    row_price = float(payload.get("row_price") or 1.0)
    events = payload.get("events_order") or list(range(1, rows[0].__len__() + 1))
    digest = rows_hash(rows)
    store.conn.execute(
        "INSERT OR IGNORE INTO pool_played_coupon("
        "product, draw_number, played_at, label, build_kind, strategy, "
        "value_weight, budget, row_price, n_rows, cost_kr, events_order, "
        "rows_text, rows_hash, code_version, note) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (payload["product"], int(payload["draw_number"]), _now(),
         payload.get("label"), payload.get("build_kind"),
         payload.get("strategy"), payload.get("value_weight"),
         payload.get("budget"), row_price, len(rows),
         round(len(rows) * row_price, 2),
         json.dumps(list(events)), "\n".join(rows), digest,
         payload.get("code_version"), payload.get("note")))
    store._commit()
    row = store.conn.execute(
        "SELECT * FROM pool_played_coupon WHERE product=? AND draw_number=? "
        "AND rows_hash=?",
        (payload["product"], int(payload["draw_number"]), digest)).fetchone()
    return dict(row) if row else {}


def forget(store: Storage, coupon_id: int) -> bool:
    """Ta bort en felaktigt bokförd kupong (bara innan den settlats)."""
    cur = store.conn.execute(
        "DELETE FROM pool_played_coupon WHERE id=? AND settled_at IS NULL",
        (int(coupon_id),))
    store._commit()
    return cur.rowcount > 0


def _sign_from_score(home, away) -> Optional[str]:
    try:
        h, a = int(home), int(away)
    except (TypeError, ValueError):
        return None
    return "1" if h > a else ("2" if a > h else "X")


def _minus_overtime(current: Optional[dict],
                    overtime: Optional[dict]) -> Optional[dict]:
    """Ordinarie tid = `Current` minus förlängningens mål.

    `Overtime` bär MÅLEN i förlängningen, inte ställningen — verifierat på
    Apollon Limassol–Brann 2026-08-11: Fulltime 1–2, Overtime 1–2, Current 2–4.
    Ger exakt ordinarie tid de gånger SvS publicerar Overtime innan Fulltime.
    """
    if not (current and overtime):
        return None
    try:
        home = int(current["home"]) - int(overtime["home"])
        away = int(current["away"]) - int(overtime["away"])
    except (KeyError, TypeError, ValueError):
        return None
    # Negativt vore ett fältmissförstånd, inte ett resultat.
    return {"home": str(home), "away": str(away)} if home >= 0 and away >= 0 else None


def match_finished(match: dict) -> bool:
    """Är matchen färdigspelad så att tecknet står fast?

    EN definition, tre användare: livekortets `final`, settlementens
    omprövningstid (`pool_settlement._retry_after`) och breddvakten. Skriv
    aldrig en parallell — det var just en parallell statuslista som gjorde två
    straffavgjorda cupmatcher till "pågående" 2026-08-08.
    """
    status_id = match.get("statusId")
    status_word = str(match.get("status") or "").casefold()
    has_fulltime = any(res.get("sportEventResultType") == "Fulltime"
                       for res in (match.get("result") or []))
    return bool(
        (isinstance(status_id, int) and status_id in FINISHED_STATUS_IDS)
        or status_word in FINISHED_STATUS_WORDS
        or str(match.get("sportEventStatus") or "").casefold() == "ended"
        # Ett publicerat Fulltime-resultat betyder att ordinarie tid är spelad,
        # även om SvS hunnit sätta en statuskod vi inte sett förut.
        or has_fulltime)


def in_extra_time(match: dict) -> bool:
    """Spelas matchen förlängning eller straffar JUST NU?

    Avgörs på STATUS, inte på `match_finished`. Ett publicerat `Fulltime`
    betyder bara att ordinarie tid är klar — Nijmegen–Olympiakos bar Fulltime
    1–1 mitt i första övertidsperioden 2026-08-11, alltså tvärtemot antagandet
    att Fulltime aldrig publiceras under pågående match. Tecknet står då fast
    OCH matchen rullar vidare, och kortet ska kunna säga båda delarna.

    En avslutad straffmatch bär däremot ordet "straffläggning" i sin slutstatus
    utan att något spelas; den är färdig, inte pågående.
    """
    status_id = match.get("statusId")
    if isinstance(status_id, int) and status_id in FINISHED_STATUS_IDS:
        return False
    if str(match.get("status") or "").casefold().startswith("slut"):
        return False
    word = str(match.get("status") or "").casefold()
    return bool(
        (isinstance(status_id, int) and status_id in EXTRA_TIME_STATUS_IDS)
        or any(needle in word for needle in EXTRA_TIME_STATUS_WORDS))


def regulation_over(match: dict) -> bool:
    """Är ORDINARIE tid färdigspelad, så att pooltecknet står fast?

    Detta är INTE samma fråga som `match_finished`, och skillnaden är hela
    poängen. En cupmatch i förlängning är inte färdigspelad — men dess
    ordinarie tid är avgjord, och det är ordinarie tid som avgör kupongen.

    Apollon Limassol–Brann (Topptipset 4260, 2026-08-11) satt i förlängning med
    ordinarie tid 2–3. Utan den här skillnaden räknades matchen som helt öppen:
    kupongen påstod att den ännu kunde bli 1, X eller 2, och chansmotorn jagade
    ett livepris som per definition inte finns — Kambis 1X2-marknad för
    ordinarie tid är stängd när ordinarie tid är slut. Resultatet blev noten
    "saknar odds" på en match som hade odds hela vägen.
    """
    return match_finished(match) or in_extra_time(match)


def event_state(draw_event: dict) -> dict:
    """{'sign': '1'|'X'|'2'|None, 'final': bool, 'score': '1-0'|None}.

    `sign` är tecknet SÅ LÅNGT — under pågående match är det preliminärt, och
    `final` säger om det står fast. Ett pågående 0–0 ger sign 'X' med
    final=False; det är information, inte ett facit.
    """
    match = draw_event.get("match") or {}
    results = {res.get("sportEventResultType"): res
               for res in (match.get("result") or [])}
    # `Fulltime` är poolens EGEN definition av tecknet: resultatet efter
    # ordinarie tid. `Current` är bara "ställningen nu" och kan i cupmatcher
    # bära förlängning eller straffar — Barnsley–Wigan 2026-08-08 hade
    # Fulltime 1–1 men Penalties 6–5, och Montreal–Atlanta 2024 blev "6-7" i
    # stället för 2–2 på exakt det sättet. Fulltime vinner därför när den
    # finns; den publiceras aldrig under pågående match (verifierat: matcher
    # i spel bär bara Current och Halftime).
    fulltime = results.get("Fulltime")
    current = results.get("Current")
    extra = in_extra_time(match)
    # Under förlängning bär `Current` ordinarie tids resultat bara tills ett mål
    # görs i förlängningen — då tickar den vidare och beskriver inte längre det
    # som avgör kupongen. Halvlekssummorna är immuna mot det och går därför före
    # när SvS publicerat dem. Fulltime slår allt när den finns.
    # Ordinarie tid, i fallande tillförlitlighet. `Overtime` är MÅLEN i
    # förlängningen (uppmätt: Fulltime 1–2 + Overtime 1–2 = Current 2–4), så
    # Current minus Overtime ger ordinarie tid exakt när Fulltime dröjer.
    regulation = fulltime or _minus_overtime(current, results.get("Overtime"))
    basis = regulation or current
    # Under förlängning bär `Current` ordinarie tid PLUS förlängningsmålen, och
    # ingenting i den löpande payloaden isolerar ordinarie tid. Uppmätt hela
    # vägen på Apollon Limassol–Brann 2026-08-11: ordinarie tid 1–2, Overtime
    # 1–2, Current 2–4. Kl. 21:07 stod Current i 2–3 (1–2 plus ett mål i
    # förlängningen), och `Halftime` gick inte att låna som ankare — SvS skrev
    # om den till 2–3 och sedan 2–4 mitt i matchen och rättade den till 0–1
    # först i slutdatan. `Overtime` publiceras inte förrän matchen är slut.
    # Tecknet är alltså OKÄNT under förlängning, inte bara osäkert: hade
    # ordinarie tid stått 2–2 och hemmalaget gjort mål i förlängningen skulle
    # Current visa 3–2 och kupongen påstå "1" när rätt tecken är "X".
    provisional = bool(extra and regulation is None)
    sign = _sign_from_score((basis or {}).get("home"), (basis or {}).get("away"))
    # POOLREGELN (Saman 2026-08-11): poolspelen fastställs på ordinarie 90
    # minuter, så en match i förlängning ÄR klar för kupongen även om matchen
    # inte är det. Osäkerhet om vilket resultatet är får inte avgöra frågan om
    # matchen är avgjord — den bärs av `sign_provisional` i stället.
    final = regulation_over(match)
    # Visad ställning följer tecknet: efter en straffläggning ska kortet visa
    # 1–1, inte 6–5, eftersom det är 1–1 som avgör kupongen.
    score = (f"{basis['home']}-{basis['away']}"
             if basis and basis.get("home") is not None else None)
    return {"sign": sign, "final": final, "score": score,
            # Ordinarie tid är slut men matchen rullar vidare. UI:t ska kunna
            # säga "förlängning" i stället för att visa matchen som öppen.
            "extra_time": extra,
            "sign_provisional": provisional,
            "status_text": match.get("status") or None,
            "event_number": draw_event.get("eventNumber"),
            "cancelled": bool(draw_event.get("cancelled")),
            "probs": _event_probs(draw_event),
            "home": _participant(match, "home"),
            "away": _participant(match, "away"),
            "start": match.get("matchStart"),
            # Startad men inte klar ⇒ SvS statiska prematch-odds beskriver inte
            # längre matchen. Flaggan styr om livepris måste hämtas — och under
            # förlängning finns inget att hämta: Kambi stänger 1X2 för ordinarie
            # tid när ordinarie tid är slut. Därför `regulation_over` här och
            # `match_finished` i `final`; det är hela skillnaden mellan "går att
            # prissätta" och "tecknet är känt".
            "in_progress": bool(score) and not (final or extra),
            "description": (draw_event.get("description")
                            or " - ".join(
                                p for p in (_participant(match, "home"),
                                            _participant(match, "away")) if p)
                            or None)}


def _participant(match: dict, side: str) -> Optional[str]:
    for p in (match.get("participants") or []):
        if p.get("type") == side:
            return p.get("name")
    return None


def _event_probs(draw_event: dict) -> Optional[dict]:
    """Overroundfri 1X2-sannolikhet ur SvS-oddsen, annars streck.

    Samma prioritetsordning och power-devig som analysvyn — chansen på
    kupongen får aldrig räknas på en annan sannolikhet än den vi visar. Utan
    både odds och streck returneras None; en gissad likafördelning hade sett ut
    som information.
    """
    from .analysis import _power_probs
    odds = draw_event.get("odds") or {}
    keys = {"1": "one", "X": "x", "2": "two"}
    inv = {}
    for sign, key in keys.items():
        value = _decimal(odds.get(key))
        if value and value > 1.0:
            inv[sign] = 1.0 / value
    if len(inv) == 3:
        return _power_probs(inv)
    folk = draw_event.get("svenskaFolket") or {}
    streck = {}
    for sign, key in keys.items():
        value = _decimal(folk.get(key))
        if value is not None:
            streck[sign] = max(0.001, value)
    if len(streck) == 3 and sum(streck.values()) > 0:
        total = sum(streck.values())
        return {sign: value / total for sign, value in streck.items()}
    return None


def attach_regulation_time(states: list[dict]) -> None:
    """Belägg ordinarie tid för förlängningsmatcher via Flashscore.

    SvS publicerar varken `Fulltime` eller `Overtime` medan förlängningen
    pågår, och `Current` bär förlängningsmålen. CSKA 1948 Sofia–Panathinaikos
    stod i Current 1–2 i andra övertidsperioden medan ordinarie tid var 1–1 —
    alltså X och inte 2, vilket är skillnaden mellan 1 och 7 kvarvarande rader
    på en 256-radars Topptipsetkupong.

    Flashscores per-match-feed (`df_sur`) bär ordinarie tids ställning och
    lästes rätt i det fallet. Den används bara som KOMPLETTERING när SvS inte
    har publicerat ordinarie tid; SvS `Fulltime` vinner alltid när den finns.

    Ett källfel får aldrig ändra ett tecken: allt som misslyckas lämnar
    matchen märkt som obelagd, och radantalet redovisas då som spann.
    """
    pending = [state for state in states if state.get("sign_provisional")]
    if not pending:
        return
    from .flashscore import Flashscore
    from .live_radar import _same_team
    try:
        with Flashscore() as source:
            rows, _ = source.matches()
            for state in pending:
                home, away = state.get("home"), state.get("away")
                if not (home and away):
                    continue
                hits = {row.get("flashscore_id") for row in rows
                        if _same_team(str(row.get("home") or ""), home)
                        and _same_team(str(row.get("away") or ""), away)}
                hits.discard(None)
                if len(hits) != 1:
                    continue          # tvetydigt eller olänkat: gissa aldrig
                summary, _ = source.summary(hits.pop())
                _apply_regulation(state, summary)
    except Exception:                 # noqa: BLE001 — källfel är inte ett facit
        return


def _apply_regulation(state: dict, summary: Optional[dict]) -> None:
    """Skriv ordinarie tid från Flashscore om den är konsistent med SvS.

    Mål kan bara TILLKOMMA i förlängningen, så ordinarie tid får aldrig ligga
    över den ställning SvS redan visar. Ett högre värde betyder att vi läst
    fel fält, och då rörs tecknet inte.
    """
    if not summary:
        return
    home, away = summary.get("home_score"), summary.get("away_score")
    if home is None or away is None:
        return
    current = str(state.get("score") or "").split("-")
    if len(current) == 2:
        try:
            if int(home) > int(current[0]) or int(away) > int(current[1]):
                return
        except ValueError:
            return
    sign = _sign_from_score(home, away)
    if sign is None:
        return
    state["sign"] = sign
    state["score"] = f"{home}-{away}"
    state["sign_provisional"] = False
    state["regulation_source"] = "flashscore"


def attach_live_odds(store: Storage, states: list[dict]) -> None:
    """Byt prematch-sannolikheten mot LIVEpris för matcher som redan rullar.

    SvS pooldata bär statiska prematch-odds hela omgången. AIK–Örgryte låg
    0–2 i halvtid med 1,55 på AIK (≈60 %) medan Kambis livepris stod i 9,00
    (≈8 %) — en kupongchans räknad på det förra är inte ungefär rätt, den är
    fel. Matcher som INTE startat rör vi inte; där är prematch rätt pris.

    Hittas inget öppet livepris nollas sannolikheten i stället för att falla
    tillbaka på prematch. Chansberäkningen visar då ingen siffra alls, vilket
    är sanningen: vi vet inte.
    """
    from . import kambi
    from .analysis import _power_probs
    running = [s for s in states if s.get("in_progress")]
    if not running:
        return
    catalogue = kambi.live_events()      # ETT anrop för hela omgången
    for state in running:
        state["probs_basis"] = "live"
        event_id = _kambi_id_for(catalogue, state)
        prices = kambi.live_1x2(event_id) if event_id else {}
        if len(prices) == 3:
            state["probs"] = _power_probs({s: 1 / o for s, o in prices.items()})
        else:
            state["probs"] = None
            state["probs_basis"] = "live_saknas"


def _kambi_id_for(catalogue: list[dict], state: dict) -> Optional[str]:
    """Poolmatch → Kambis live-event via normaliserade lagnamn.

    Listan slås upp direkt i stället för via `oddset_matches`: poolerna
    innehåller Ettan, Elitettan och utländska serier som ligger helt utanför
    Oddsets tio ligor, så en Oddset-slagning tappade de flesta.

    Hemma/borta måste stämma på SAMMA sida — en spegelvänd träff kan vara ett
    returmöte, och ett pris på fel lag är värre än inget pris. Entydighet krävs.
    """
    from .live_radar import _same_team
    home, away = state.get("home"), state.get("away")
    if not (home and away):
        return None
    # `_same_team` och inte strikt `norm_team`-likhet: SvS och Kambi skiljer sig
    # på föreningssuffix (`Kristiansund` mot `Kristiansund BK`), svensk genitiv
    # och de observerade aliasen. Spärrarna mot U23/B-lag och prefixkrockar
    # följer med på köpet.
    hits = {row["id"] for row in catalogue
            if _same_team(row["home"], home) and _same_team(row["away"], away)}
    return hits.pop() if len(hits) == 1 else None


def _decimal(value) -> Optional[float]:
    """SvS skickar svenska decimaler som strängar ("5,50")."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _coupon_events(coupon: dict, width: int) -> list[int]:
    """Kupongens eventNumber per kolumn. Default 1..N när inget sparats."""
    try:
        events = [int(e) for e in json.loads(coupon.get("events_order") or "[]")]
    except (TypeError, ValueError):
        events = []
    return events if len(events) == width else list(range(1, width + 1))


def live_status(coupon: dict, states: list[dict]) -> dict:
    """Rätt-så-långt per rad + vilka rader som fortfarande kan nå varje nivå.

    Det här är svaret på "följa reducerade system live": för varje rad räknas
    säkra träffar (avgjorda matcher) och möjliga träffar (säkra + de som ännu
    inte är avgjorda). En rad kan nå nivå k om möjliga ≥ k.

    LIVEVY, aldrig facit. Tecknen paras mot eventNumber via kupongens
    `events_order` (payloadordningen är inget kontrakt), en kolumn utan
    matchande event räknas som oavgjord i stället för att tyst trunkeras, och
    en struken match är oavgjord tills SvS fastställt tecknet i settlementet.
    """
    rows = (coupon.get("rows_text") or "").split("\n")
    width = len(rows[0]) if rows and rows[0] else 0
    events = _coupon_events(coupon, width)
    by_event: dict[int, dict] = {}
    for i, state in enumerate(states):
        number = state.get("event_number")
        by_event[int(number) if number is not None else i + 1] = state
    col_states = [by_event.get(events[i]) for i in range(width)]
    decided = sum(1 for s in col_states
                  if s and s.get("final") and not s.get("cancelled"))
    best_secure = 0
    secure_hist: dict[int, int] = {}
    possible_hist: dict[int, int] = {}
    for row in rows:
        secure = possible = 0
        for i in range(width):
            state = col_states[i]
            if state is None or state.get("cancelled") or not state.get("final"):
                possible += 1        # okänd/struken/pågående kan ännu bli rätt
                continue
            hit = state.get("sign") == row[i]
            secure += int(hit)
            possible += int(hit)
        best_secure = max(best_secure, secure)
        secure_hist[secure] = secure_hist.get(secure, 0) + 1
        possible_hist[possible] = possible_hist.get(possible, 0) + 1
    alive = {level: sum(n for p, n in possible_hist.items() if p >= level)
             for level in range(max(1, width - 3), width + 1)}
    levels = sorted(alive, reverse=True)
    # En match i förlängning är avgjord för poolen, men om varken Fulltime
    # eller Overtime publicerats är tecknet läst ur Current och kan bära ett
    # förlängningsmål. Då är radantalet inte ett faktum utan ett spann:
    # CSKA–Panathinaikos stod i Current 1–2 medan ordinarie tid var 1–1, och
    # kortet påstod 7 rader kvar till 8 rätt när det rätta svaret var 1.
    unproven = [i for i in range(width)
                if (col_states[i] or {}).get("sign_provisional")]
    alive_span = _alive_span(rows, col_states, width, levels, unproven)
    # Bästa NÅBARA antal rätt. Ren aritmetik — den kräver inga odds och finns
    # därför även när en livemarknad är avstängd. Utan den visade kortet bara
    # en tabell med streck när kupongen inte längre kunde nå någon vinstnivå,
    # och Saman fick räkna ut det själv ur "bäst 4 rätt" och 5 kvarvarande.
    max_possible = max(possible_hist) if possible_hist else 0
    return {"n_events": width, "n_decided": decided,
            "all_decided": bool(width and decided == width),
            "best_secure": best_secure,
            "max_possible": max_possible,
            # Ingen rad kan nå ens den lägsta redovisade vinstnivån.
            "out_of_contention": bool(levels) and max_possible < min(levels),
            "secure_dist": dict(sorted(secure_hist.items(), reverse=True)),
            "alive_per_level": dict(sorted(alive.items(), reverse=True)),
            **alive_span,
            "matches": _match_rows(rows, col_states, events, width),
            "cheer": _cheer_per_match(rows, col_states, width, levels),
            **_chance_per_level(rows, col_states, width, levels)}


SIGNS = ("1", "X", "2")


def _alive_span(rows: list[str], col_states: list[Optional[dict]], width: int,
                levels: list[int], unproven: list[int]) -> dict:
    """Radantal per nivå som ett SPANN över obelagda förlängningstecken.

    Matchen är avgjord — poolen fastställs på ordinarie tid — men vilket
    tecknet är vet vi inte förrän SvS publicerar `Fulltime` eller `Overtime`.
    Att då redovisa siffran för Currents tecken är att presentera en gissning
    som ett faktum. Spannet säger i stället vad vi faktiskt vet: radantalet
    ligger mellan de här gränserna oavsett hur ordinarie tid slutade.
    """
    if not unproven or not levels or not rows:
        return {}
    lo = {level: None for level in levels}
    hi = {level: 0 for level in levels}
    for combo in itertools.product(SIGNS, repeat=len(unproven)):
        pinned = dict(zip(unproven, combo))
        counts = {level: 0 for level in levels}
        for row in rows:
            possible = 0
            for j in range(width):
                if j in pinned:
                    possible += int(row[j] == pinned[j])
                    continue
                state = col_states[j]
                possible += (int(state.get("sign") == row[j])
                             if _decided(state) else 1)
            for level in levels:
                if possible >= level:
                    counts[level] += 1
        for level in levels:
            lo[level] = counts[level] if lo[level] is None else min(lo[level], counts[level])
            hi[level] = max(hi[level], counts[level])
    return {
        "alive_min_per_level": dict(sorted(lo.items(), reverse=True)),
        "alive_max_per_level": dict(sorted(hi.items(), reverse=True)),
        "alive_unproven": [
            (col_states[i] or {}).get("description") or f"match {i + 1}"
            for i in unproven
        ],
    }


def _decided(state: Optional[dict]) -> bool:
    """Står tecknet fast? Struken match är oavgjord tills SvS fastställt den."""
    return bool(state and state.get("final") and not state.get("cancelled"))


def _match_rows(rows: list[str], col_states: list[Optional[dict]],
                events: list[int], width: int) -> list[dict]:
    """Matcherna i kupongordning med ställning, tecken och kupongens egna val.

    Det här är liverättningens vänsterhalva: utan den syns bara aggregat, och
    Saman kunde inte se VILKEN match som gått åt vilket håll — bara att antalet
    levande rader sjunkit.
    """
    out = []
    for i in range(width):
        state = col_states[i] or {}
        played = {sign: sum(1 for row in rows if row[i] == sign)
                  for sign in SIGNS}
        decided = _decided(state)
        out.append({
            "col": i + 1,
            "event": events[i] if i < len(events) else i + 1,
            "home": state.get("home"), "away": state.get("away"),
            "description": state.get("description"),
            "start": state.get("start"),
            "score": state.get("score"), "sign": state.get("sign"),
            "final": decided,
            "cancelled": bool(state.get("cancelled")),
            "extra_time": bool(state.get("extra_time")),
            "sign_provisional": bool(state.get("sign_provisional")),
            "status_text": state.get("status_text"),
            "in_progress": bool(state.get("in_progress")),
            # Kupongens egna tecken i den här matchen, och hur många rader som
            # träffade när tecknet väl står fast.
            "row_signs": {sign: n for sign, n in played.items() if n},
            "rows_hit": played.get(state.get("sign")) if decided else None,
        })
    return out


def _cheer_per_match(rows: list[str], col_states: list[Optional[dict]],
                     width: int, levels: list[int]) -> list[dict]:
    """Per kvarvarande match: hur många rader lever om den slutar 1, X eller 2.

    Svaret på "vilket resultat ska jag heja på". `alive` räknas mot den lägsta
    redovisade vinstnivån och `top` mot alla rätt — ett tecken kan mycket väl
    hålla flest rader vid liv och samtidigt döda jackpotchansen, och då ska
    båda synas i stället för ett hopslaget mått som döljer valet.
    """
    if not levels or not rows or not width:
        return []
    top, floor = max(levels), min(levels)
    out = []
    for i in range(width):
        if _decided(col_states[i]):
            continue
        counts = {sign: {"alive": 0, "top": 0} for sign in SIGNS}
        for row in rows:
            # Möjliga rätt över ALLA andra kolumner — oberoende av tecknet vi
            # prövar, så det räknas en gång per rad i stället för tre.
            base = 0
            for j in range(width):
                if j == i:
                    continue
                state = col_states[j]
                base += (int(state.get("sign") == row[j]) if _decided(state)
                         else 1)
            for sign in SIGNS:
                possible = base + int(row[i] == sign)
                if possible >= floor:
                    counts[sign]["alive"] += 1
                if possible >= top:
                    counts[sign]["top"] += 1
        state = col_states[i] or {}
        best = max(SIGNS, key=lambda s: (counts[s]["top"], counts[s]["alive"]))
        # Alla tre tecknen lika bra = matchen avgör ingenting för kupongen.
        matters = len({(c["alive"], c["top"]) for c in counts.values()}) > 1
        # Topptipset har åtta matcher men BARA 8 rätt delar potten, så
        # `alive` mot golvnivån är 256 för varenda tecken och säger ingenting.
        # På Stryktipset ger 10 rätt pengar och då bär samma kolumn verklig
        # information. UI:t ska visa den bara när den skiljer tecknen åt.
        alive_varies = len({c["alive"] for c in counts.values()}) > 1
        out.append({
            "col": i + 1,
            "description": state.get("description"),
            "signs": counts,
            "best": best if matters else None,
            "alive_varies": alive_varies,
            "floor_level": floor, "top_level": top,
        })
    return out


CHANCE_EXACT_MAX_COMBOS = 60000     # 3^10; över det blir uppräkningen dyr
CHANCE_SAMPLES = 20000              # Monte Carlo när uppräkning är för dyr
# Fler oprissatta matcher än så ger ett intervall så brett att det inte säger
# något — då är noten ärligare än en gräns mellan 0 och 100 %.
CHANCE_MAX_UNPRICED = 2


def _hit_probabilities(groups, probs, levels) -> tuple[dict, str]:
    """P(bästa raden når nivån) över de PRISSATTA matchernas utfallsrum.

    `groups` är {teckenmönster över de prissatta kolumnerna: bästa säkrade
    antal rätt}. Raderna delar matcherna, så utfallen är beroende — därför
    räknas hela utfallsrummet i stället för en produkt av per-rad-chanser.
    """
    signs = ("1", "X", "2")
    hit = {lvl: 0.0 for lvl in levels}
    items = list(groups.items())

    def score(outcome: tuple) -> int:
        return max(secure + sum(1 for i, s in enumerate(pattern) if s == outcome[i])
                   for pattern, secure in items)

    if not probs:
        best = max(groups.values())
        return {lvl: (1.0 if best >= lvl else 0.0) for lvl in levels}, "avgjord"

    combos = 3 ** len(probs)
    if combos <= CHANCE_EXACT_MAX_COMBOS and combos * len(items) <= 4_000_000:
        for combo in itertools.product(signs, repeat=len(probs)):
            weight = 1.0
            for i, sign in enumerate(combo):
                weight *= probs[i][sign]
            best = score(combo)
            for lvl in levels:
                if best >= lvl:
                    hit[lvl] += weight
        return hit, "exakt"

    rng = random.Random(20260802)        # fast frö: samma svar vid omladdning
    for _ in range(CHANCE_SAMPLES):
        combo = tuple(rng.choices(signs, weights=[p["1"], p["X"], p["2"]])[0]
                      for p in probs)
        best = score(combo)
        for lvl in levels:
            if best >= lvl:
                hit[lvl] += 1.0 / CHANCE_SAMPLES
    return hit, "simulerad"


def _chance_per_level(rows: list[str], col_states: list[Optional[dict]],
                      width: int, levels: list[int]) -> dict:
    """Chans per vinstnivå givet oddsen på kvarvarande matcher.

    Saknar en kvarvarande match pris — Kambi stänger 1X2-marknaden i sekunder
    vid farliga lägen — beräknades tidigare INGENTING alls, och hela
    chanskolumnen slocknade på varenda kupong. Det var korrekt så till vida
    att ingen sannolikhet fabricerades, men det kastade också bort allt vi
    faktiskt visste om de övriga matcherna.

    Nu betingas beräkningen i stället på de oprissatta matchernas utfall: en
    körning per kombination, och resultatet redovisas som ett INTERVALL
    (`chance_min_per_level`/`chance_max_per_level`). Det påstår ingenting om
    hur den oprissatta matchen går — bara att chansen ligger mellan de här
    gränserna oavsett. Fler än `CHANCE_MAX_UNPRICED` oprissatta matcher ger
    ett intervall så brett att det inte säger något, och då lämnas noten kvar.
    """
    if not rows or not width or not levels:
        return {}
    open_cols = [i for i in range(width)
                 if not (col_states[i] and col_states[i].get("final")
                         and not col_states[i].get("cancelled"))]
    priced_cols, priced_probs, unpriced_cols, unpriced_names = [], [], [], []
    live_used = 0
    for i in open_cols:
        state = col_states[i] or {}
        p = state.get("probs")
        if p and abs(sum(p.values()) - 1.0) <= 0.01:
            priced_cols.append(i)
            priced_probs.append(p)
            if state.get("probs_basis") == "live":
                live_used += 1
        else:
            unpriced_cols.append(i)
            # Ställningen MÅSTE med. Intervallet spänner över alla utfall den
            # oprissatta matchen kan få, så underkanten är noll även när
            # matchen i praktiken är avgjord: NK Celje ledde 2–0 i andra
            # halvlek och kortet visade "0 %–73 %" utan att avslöja att
            # underkanten förutsätter att en tvåmålsledning går förlorad.
            name = state.get("description") or f"match {i + 1}"
            if state.get("score"):
                name = f"{name} ({state['score']})"
            unpriced_names.append(name)

    if len(unpriced_cols) > CHANCE_MAX_UNPRICED:
        return {"chance_note": _unpriced_note(col_states, unpriced_cols,
                                              unpriced_names)}

    # Bästa säkrade antal rätt per teckenmönster över de PRISSATTA kolumnerna,
    # för varje tänkt utfall i de oprissatta.
    signs = ("1", "X", "2")
    lo = {lvl: 1.0 for lvl in levels}
    hi = {lvl: 0.0 for lvl in levels}
    basis = "avgjord"
    for pinned in itertools.product(signs, repeat=len(unpriced_cols)):
        groups: dict[tuple, int] = {}
        for row in rows:
            secure = 0
            for i in range(width):
                state = col_states[i]
                if state and state.get("final") and not state.get("cancelled"):
                    secure += int(state.get("sign") == row[i])
            for k, col in enumerate(unpriced_cols):
                secure += int(row[col] == pinned[k])
            pattern = tuple(row[i] for i in priced_cols)
            groups[pattern] = max(groups.get(pattern, 0), secure)
        hit, basis = _hit_probabilities(groups, priced_probs, levels)
        for lvl in levels:
            lo[lvl] = min(lo[lvl], hit[lvl])
            hi[lvl] = max(hi[lvl], hit[lvl])

    out = {"chance_basis": basis, "chance_open_matches": len(open_cols),
           "chance_live_matches": live_used}
    if not unpriced_cols:
        out["chance_per_level"] = {lvl: round(hi[lvl], 6) for lvl in levels}
        return out
    out["chance_min_per_level"] = {lvl: round(lo[lvl], 6) for lvl in levels}
    out["chance_max_per_level"] = {lvl: round(hi[lvl], 6) for lvl in levels}
    out["chance_unpriced"] = unpriced_names
    return out


def _unpriced_note(col_states, cols, names) -> str:
    """Förklara varför ingen chans visas — med matchnamn, inte "en match".

    "saknar odds" var fel ord om en match som rullar: den HAR odds hela vägen,
    men Kambis livemarknad är stängd just då. Ordet fick Saman att leta efter
    en insamlingslucka som inte fanns (2026-08-11).
    """
    joined = ", ".join(names)
    if any((col_states[i] or {}).get("extra_time") for i in cols):
        return (f"{joined} spelar förlängning — ordinarie tid avgör kupongen "
                "och publiceras när matchen är slut")
    if any((col_states[i] or {}).get("in_progress") for i in cols):
        return f"{joined} har stängd livemarknad just nu"
    return f"{joined} saknar spelbart pris"


def _mark_incomplete(store: Storage, coupon: dict, note: str) -> dict:
    store.conn.execute(
        "UPDATE pool_played_coupon SET settled_at=?, payout_complete=0, "
        "settle_note=? WHERE id=?", (_now(), note, coupon["id"]))
    store._commit()
    return {"settled": True, "complete": False, "payout_kr": None,
            "roi": None, "reason": note}


def settle(store: Storage, coupon: dict, tiers: dict[int, tuple]) -> dict:
    """Slutfacit ur settlementlagret + PUBLICERADE belopp (vi var i potten).

    Facit = `pool_event_settlement.outcome` per eventNumber — samma kanon som
    PH3-ledgern. Draw-payloadens Current-score används ALDRIG här (den kan
    avvika efter förlängning, och strukna matcher får sitt tecken fastställt).
    tiers: {antal_rätt: (vinnare, belopp_per_vinnare)}. Saknas beloppet för en
    nivå vi träffat blir facitet uttryckligen ofullständigt; ROI får då INTE
    räknas som noll.
    """
    rows = (coupon.get("rows_text") or "").split("\n")
    width = len(rows[0]) if rows and rows[0] else 0
    events = _coupon_events(coupon, width)
    outcomes = {int(number): outcome for number, outcome in store.conn.execute(
        "SELECT event_number, outcome FROM pool_event_settlement "
        "WHERE product=? AND draw_number=?",
        (coupon["product"], coupon["draw_number"]))}
    if not outcomes:
        return {"settled": False,
                "reason": "settlementlagret saknar omgången än"}
    if len(outcomes) != width:
        # Hård breddvakt — settla aldrig tyst på fel antal matcher.
        return _mark_incomplete(
            store, coupon,
            f"breddfel: kupongen har {width} tecken/rad men omgången "
            f"{len(outcomes)} matcher")
    missing = sorted(e for e in events if outcomes.get(e) not in SIGNS)
    if missing:
        # Samma kanonregel som PH3: utfall saknas => aldrig "rätt för alla".
        return _mark_incomplete(
            store, coupon,
            "officiellt utfall saknas för match "
            + ",".join(str(e) for e in missing))
    facit = [outcomes[e] for e in events]
    dist: dict[int, int] = {}
    for row in rows:
        correct = sum(1 for sign, res in zip(row, facit) if sign == res)
        dist[correct] = dist.get(correct, 0) + 1
    payout = 0.0
    complete = True
    notes = []
    for correct, n_rows in dist.items():
        if correct not in tiers:
            continue                    # nivån ger ingen utdelning
        winners, amount = tiers[correct]
        if amount is None:
            complete = False
            notes.append(f"{correct} rätt saknar belopp")
            continue
        payout += n_rows * float(amount)
    cost = float(coupon.get("cost_kr") or 0.0)
    roi = ((payout - cost) / cost) if (complete and cost > 0) else None
    correct_max = max(dist) if dist else 0
    store.conn.execute(
        "UPDATE pool_played_coupon SET settled_at=?, correct_max=?, "
        "correct_dist=?, payout_kr=?, payout_complete=?, roi=?, settle_note=? "
        "WHERE id=?",
        (_now(), correct_max, json.dumps(dist),
         round(payout, 2) if complete else None, int(complete), roi,
         "; ".join(notes) or SETTLEMENT_VERSION, coupon["id"]))
    store._commit()
    return {"settled": True, "payout_kr": round(payout, 2) if complete else None,
            "roi": roi, "complete": complete,
            "correct_max": correct_max, "correct_dist": dist}


def open_coupons(store: Storage) -> list[dict]:
    return [dict(r) for r in store.conn.execute(
        "SELECT c.*, COALESCE(s.reg_close_time, d.reg_close_time) AS draw_close "
        "FROM pool_played_coupon c "
        "LEFT JOIN pool_draw_settlement s "
        "ON s.product=c.product AND s.draw_number=c.draw_number "
        "LEFT JOIN draws d "
        "ON d.product=c.product AND d.draw_number=c.draw_number "
        "WHERE c.settled_at IS NULL ORDER BY c.played_at DESC")]


def all_coupons(store: Storage, limit: int = 100) -> list[dict]:
    return [dict(r) for r in store.conn.execute(
        "SELECT c.*, COALESCE(s.reg_close_time, d.reg_close_time) AS draw_close "
        "FROM pool_played_coupon c "
        "LEFT JOIN pool_draw_settlement s "
        "ON s.product=c.product AND s.draw_number=c.draw_number "
        "LEFT JOIN draws d "
        "ON d.product=c.product AND d.draw_number=c.draw_number "
        "ORDER BY c.played_at DESC LIMIT ?",
        (int(limit),))]


def summary(store: Storage) -> dict:
    """Ärligt sammandrag: bara kompletta facit ingår i ROI."""
    rows = [r for r in all_coupons(store, 1000)]
    done = [r for r in rows if r["settled_at"] and r["payout_complete"]]
    spent = sum(float(r["cost_kr"] or 0) for r in done)
    won = sum(float(r["payout_kr"] or 0) for r in done)
    return {"n_coupons": len(rows), "n_settled": len(done),
            "n_open": sum(1 for r in rows if not r["settled_at"]),
            "spent_kr": round(spent, 2), "won_kr": round(won, 2),
            "roi": round((won - spent) / spent, 4) if spent > 0 else None,
            "note": ("ROI räknas bara på kuponger med komplett publicerad "
                     "utdelning; öppna och ofullständiga hålls utanför.")}
