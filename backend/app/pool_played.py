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
import math
import json
import random
from typing import Optional

from .storage import Storage

SIGNS = ("1", "X", "2")
# Samma hårda färskhetsgräns som liveblindtestet. Pinnacles per-matchup-cache
# är ofta flera minuter gammal; ett sådant pris är inte ett livepris bara för
# att vi hämtade det nu.
PINNACLE_LIVE_MAX_AGE_S = 90
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

# Fulltime-skyddsnätet är ett nät mot OKÄNDA statuskoder, aldrig ett bevis som
# får köra över en känd och korrekt status. SvS publicerade 2026-08-22 ett
# `Fulltime` 0–0 för Nottingham–Leeds (Stryktipset 4967, event 4) medan matchen
# stod i `statusId 6` = "Första halvlek", 43 minuter efter avspark — ensam bland
# omgångens tretton matcher. Nätet gjorde då sex spelade kuponger till "slut"
# med tecknet X, räknade bort matchen ur radantalet och slutade jaga livepris.
#
# Vetot är FYSIK, inte ännu en statuskod: ordinarie tid kräver 90 spelade
# minuter plus paus, alltså minst 105 minuter väggklocka. Marginalen är
# medvetet den fysiska miniminivån och INTE settlementets 130 — nätet ska
# stoppas när det är omöjligt, aldrig när det bara är osannolikt. Ett `Fulltime`
# publicerat under förlängning (Nijmegen–Olympiakos 2026-08-11) ligger långt
# efter gränsen och passerar precis som förut.
REGULATION_WALL_CLOCK_MIN = 105

# Spel EFTER ordinarie tid. Poolen avgörs på ordinarie tid, så här står tecknet
# redan fast trots att matchen inte är slut. Observerat 2026-08-11: statusId 20
# = "Första övertidsperioden" (Apollon Limassol–Brann, Topptipset 4260).
# Orden är skyddsnät för de koder vi ännu inte sett — SvS numrerar
# övertidsperioder, paus i förlängning och straffläggning var för sig, och en
# okänd kod får inte tyst göra en avgjord match "öppen" igen.
# 23 är INTE en övertidskod. Uppmätt 2026-08-12 på Topptipset 4261
# (D. Tolima–Independiente) betyder statusId 23 **Uppskjuten**. Den gissade
# serien 20–25 gjorde därmed en match som ALDRIG spelats till en match vars
# ordinarie tid var färdigspelad: `regulation_over` blev sann, kupongen
# redovisade matchen som avgjord och tecknet lästes ur ett resultat som inte
# fanns. Bara 20 ("Första övertidsperioden") är observerad; resten av serien
# var aldrig belagd och tas bort. Skyddsnätet mot okända övertidskoder ligger
# i ORDEN nedan, som SvS levererar i klartext bredvid koden.
EXTRA_TIME_STATUS_IDS = frozenset({20})
EXTRA_TIME_STATUS_WORDS = ("övertid", "overtid", "förläng", "forlang",
                           "straff", "extra time", "penalt")

# Matcher som aldrig spelas i sin planerade form. SvS stryker dem och lottar
# fram ett fastställt tecken, men FÖRST vid finalisering — fram till dess är
# tecknet okänt, inte avgjort. En uppskjuten match får därför varken räknas som
# klar (då hittar vi på ett tecken) eller hålla settlementets omprövning
# tillbaka (den blir aldrig "färdigspelad").
POSTPONED_STATUS_IDS = frozenset({23})
POSTPONED_STATUS_WORDS = ("uppskjut", "postpon", "inställ", "installd",
                          "flyttad", "abandon")


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


def _fulltime_can_be_real(match: dict,
                          now: Optional[dt.datetime] = None) -> bool:
    """Har det hunnit gå tillräckligt länge för att ett `Fulltime` ska KUNNA
    beskriva en spelad match?

    Ordinarie tid är 90 spelade minuter plus paus, alltså minst
    `REGULATION_WALL_CLOCK_MIN` minuter väggklocka från avspark. Ett `Fulltime`
    dessförinnan är omöjligt, inte bara osannolikt.

    Saknas eller är `matchStart` oläsbar lämnas skyddsnätet orört — vi vet då
    ingenting som motsäger det, och ett trasigt datum får aldrig göra en
    färdigspelad match öppen igen.
    """
    start = match.get("matchStart")
    try:
        stamp = dt.datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - stamp) >= dt.timedelta(minutes=REGULATION_WALL_CLOCK_MIN)


def match_finished(match: dict, now: Optional[dt.datetime] = None) -> bool:
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
        # även om SvS hunnit sätta en statuskod vi inte sett förut — men bara
        # när klockan tillåter det. Se REGULATION_WALL_CLOCK_MIN.
        or (has_fulltime and _fulltime_can_be_real(match, now)))


def match_postponed(match: dict) -> bool:
    """Är matchen uppskjuten/inställd, alltså aldrig spelad som planerat?

    Skilj den från både "pågår" och "klar". Den kommer att strykas och få ett
    lottat tecken av SvS, men det tecknet finns inte i payloaden förrän
    omgången finaliseras — så länge är utfallet OKÄNT och kupongen har den
    matchen öppen.
    """
    status_id = match.get("statusId")
    word = str(match.get("status") or "").casefold()
    return bool(
        (isinstance(status_id, int) and status_id in POSTPONED_STATUS_IDS)
        or any(needle in word for needle in POSTPONED_STATUS_WORDS))


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
    # En uppskjuten match spelas inte alls — den kan omöjligen vara i förlängning.
    if match_postponed(match):
        return False
    word = str(match.get("status") or "").casefold()
    return bool(
        (isinstance(status_id, int) and status_id in EXTRA_TIME_STATUS_IDS)
        or any(needle in word for needle in EXTRA_TIME_STATUS_WORDS))


def regulation_over(match: dict,
                    now: Optional[dt.datetime] = None) -> bool:
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
    return match_finished(match, now) or in_extra_time(match)


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
    # stället för 2–2 på exakt det sättet.
    #
    # SvS har dock också observerats lämna ett förifyllt `Fulltime` i en
    # PÅGÅENDE match. Då får det aldrig maskera den verkliga `Current`-
    # ställningen. Fulltime blir därför betrott först när matchklockan/statusen
    # säger att ordinarie tid faktiskt är över.
    fulltime_raw = results.get("Fulltime")
    current = results.get("Current")
    extra = in_extra_time(match)
    fulltime = fulltime_raw if regulation_over(match) else None
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
    prematch_probs = _event_probs(draw_event)
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
            # Uppskjuten: matchen spelas inte, men tecknet är ännu inte lottat
            # av SvS. Kortet ska kunna SÄGA det i stället för att bara låta
            # matchen stå öppen utan förklaring.
            "postponed": match_postponed(match),
            "sign_provisional": provisional,
            "status_text": match.get("status") or None,
            "event_number": draw_event.get("eventNumber"),
            "cancelled": bool(draw_event.get("cancelled")),
            "probs": prematch_probs,
            # Bevaras separat: `probs` byts mot livepris för matcher som rullar,
            # och prematchpriset är ankaret när livemarknaden är stängd.
            "prematch_probs": prematch_probs,
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


_MAX_GOALS = 9          # trunkering: P(fler än 9 mål av ett lag) är försumbar
_FULL_TIME_MIN = 90.0


def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _signs_from_lambdas(lam_home: float, lam_away: float,
                        lead_home: int = 0, lead_away: int = 0) -> dict:
    """P(1/X/2) för RESTEN av matchen ovanpå en befintlig ledning."""
    home = [_poisson_pmf(lam_home, k) for k in range(_MAX_GOALS)]
    away = [_poisson_pmf(lam_away, k) for k in range(_MAX_GOALS)]
    out = {"1": 0.0, "X": 0.0, "2": 0.0}
    for i, p_home in enumerate(home):
        for j, p_away in enumerate(away):
            final_home, final_away = lead_home + i, lead_away + j
            key = ("1" if final_home > final_away
                   else "2" if final_away > final_home else "X")
            out[key] += p_home * p_away
    total = sum(out.values()) or 1.0
    return {sign: value / total for sign, value in out.items()}


def _lambdas_from_prematch(prematch: dict) -> Optional[tuple[float, float]]:
    """Målintensiteter som återger MARKNADENS prematch-1X2 under Poisson.

    Ankaret är priset, inte en egen uppfattning om lagen: vi letar bara det
    (totalmål, hemmaandel) vars Poisson-1X2 ligger närmast det marknaden redan
    prissatt. Utan det steget vore siffran en fristående modellgissning, och
    projektet har tre gånger mätt att modell-edges utan marknadsankare blir
    systematiskt uppblåsta.
    """
    target = [prematch.get(sign) for sign in SIGNS]
    if any(value is None for value in target):
        return None
    best, best_err = None, None
    total = 1.6
    while total <= 4.21:
        share = 0.20
        while share <= 0.801:
            lam_home, lam_away = total * share, total * (1 - share)
            probs = _signs_from_lambdas(lam_home, lam_away)
            err = sum((probs[sign] - prematch[sign]) ** 2 for sign in SIGNS)
            if best_err is None or err < best_err:
                best, best_err = (lam_home, lam_away), err
            share += 0.02
        total += 0.1
    return best


def _minutes_played(state: dict, now: Optional[dt.datetime] = None) -> Optional[float]:
    """Spelad tid — Flashscores matchminut först, klocktid som reserv.

    Klocktiden sedan avspark vet inget om tillägg, avbrott eller hur lång
    pausen faktiskt blev, och den tickar vidare under paus som om det spelades.
    Flashscores `minute_at` läser stadiets egen klocka och fryser minuten i
    paus. Reserven finns kvar för matcher som inte går att länka.
    """
    minute = state.get("minute")
    if isinstance(minute, (int, float)):
        return float(minute)
    start = state.get("start")
    if not start:
        return None
    try:
        kickoff = dt.datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=dt.timezone.utc)
    elapsed = (now - kickoff).total_seconds() / 60.0
    # Halvtidspaus ligger i klocktiden men inte i speltiden.
    return max(0.0, elapsed - 15.0) if elapsed > 60 else max(0.0, elapsed)


def live_probs_from_score(state: dict,
                          now: Optional[dt.datetime] = None) -> Optional[dict]:
    """1X2 betingat på ställning och tid kvar, ankrat i prematchpriset.

    Används BARA när Kambi saknar öppen livemarknad. En stängd marknad är inte
    samma sak som okunskap: står matchen 2–0 i 75:e minuten är utfallet nästan
    givet, och att då redovisa "0 %–77 %" var att kasta bort både ställningen
    och det pris marknaden faktiskt satte före avspark.

    Siffran är en SKATTNING och märks som sådan (`probs_basis="modell"`). Den
    får aldrig gå in i värde, CLV, notiser eller systemförslag — den beskriver
    en kupong som redan är lämnad.
    """
    prematch, score = state.get("prematch_probs"), state.get("score")
    if not prematch or not score:
        return None
    parts = str(score).split("-")
    if len(parts) != 2:
        return None
    try:
        lead_home, lead_away = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    lambdas = _lambdas_from_prematch(prematch)
    if lambdas is None:
        return None
    played = _minutes_played(state, now)
    if played is None:
        return None
    remaining = max(0.0, _FULL_TIME_MIN - played) / _FULL_TIME_MIN
    # Ingen tid kvar ⇒ ställningen ÄR resultatet; ingen modell behövs.
    if remaining <= 0.0:
        sign = _sign_from_score(lead_home, lead_away)
        return {s: 1.0 if s == sign else 0.0 for s in SIGNS} if sign else None
    return _signs_from_lambdas(lambdas[0] * remaining, lambdas[1] * remaining,
                               lead_home, lead_away)


def attach_regulation_time(states: list[dict]) -> None:
    """Matchminut och ordinarie tid ur Flashscore — EN hämtning för båda.

    Två behov som delar samma länkning och samma dagsfeed, så de görs i ett
    svep: den riktiga matchminuten för pågående matcher (chansskattningen
    behöver tid kvar, och klocktid sedan avspark räknar tillägg och paus fel),
    och ordinarie tid för matcher i förlängning.

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
    pending = [state for state in states
               if state.get("sign_provisional") or state.get("in_progress")]
    if not pending:
        return
    from .flashscore import Flashscore, minute_at
    from .live_radar import _same_team
    try:
        with Flashscore() as source:
            rows, observed_at = source.matches()
            for state in pending:
                home, away = state.get("home"), state.get("away")
                if not (home and away):
                    continue
                hits = [row for row in rows
                        if _same_team(str(row.get("home") or ""), home)
                        and _same_team(str(row.get("away") or ""), away)]
                if len(hits) != 1:
                    continue          # tvetydigt eller olänkat: gissa aldrig
                row = hits[0]
                # RIKTIG matchminut i stället för klocktid sedan avspark.
                # Klockan vet inget om tillägg, avbrott eller hur lång pausen
                # blev; `minute_at` läser stadiets egen tid och FRYSER minuten
                # i paus i stället för att låta den ticka.
                minute = minute_at(row, observed_at)
                if minute is not None:
                    state["minute"] = minute
                    state["minute_source"] = "flashscore"
                if state.get("sign_provisional") and row.get("flashscore_id"):
                    summary, _ = source.summary(row["flashscore_id"])
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

    Källstegen är Kambi → Ninja → färsk Pinnacle. Först när alla tre saknar
    ett säkert, komplett 1X2 används den tydligt märkta skattningen från
    ställning + tid + prematchpris. Det här påverkar bara en redan inlämnad
    kupongs chansvy, aldrig tips, värde, CLV eller facit.
    """
    from . import altenar, kambi, pinnacle
    from .analysis import _power_probs
    running = [s for s in states if s.get("in_progress")]
    if not running:
        return

    def apply_price(state: dict, prices: Optional[dict], source: str) -> bool:
        if not prices or set(prices) != set(SIGNS):
            return False
        try:
            implied = {sign: 1 / float(prices[sign]) for sign in SIGNS
                       if float(prices[sign]) > 1.0}
        except (TypeError, ValueError, ZeroDivisionError):
            return False
        if set(implied) != set(SIGNS):
            return False
        state["probs"] = _power_probs(implied)
        state["probs_basis"] = "live"
        state["probs_source"] = source
        return True

    for state in running:
        state["probs_basis"] = "live"
        state["probs_source"] = None

    # 1. Svenska Spel/Kambi — behåller kontinuitet med tidigare liverättning.
    catalogue = kambi.live_events()      # ETT listanrop för hela statusvarvet
    prices_by_event: dict[str, dict] = {}
    unresolved = []
    for state in running:
        event = _live_event_for(catalogue, state)
        event_id = str(event["id"]) if event else None
        if event_id and event_id not in prices_by_event:
            prices_by_event[event_id] = kambi.live_1x2(event_id)
        prices = prices_by_event.get(event_id, {})
        if apply_price(state, prices, "svenskaspel"):
            continue
        unresolved.append(state)

    # 2. Ninja/Altenar — separat prismotor, live-CDN med max-age 3 s.
    if unresolved:
        try:
            ninja_events = altenar.live_events(
                integration="ninjacasinose", timeout=8.0, strict=True)
        except Exception:  # noqa: BLE001 — reservkälla får aldrig fälla vyn
            ninja_events = []
        still_unresolved = []
        for state in unresolved:
            event = _live_event_for(ninja_events, state)
            prices = (event or {}).get("odds")
            if ((event or {}).get("odds_status") == "captured"
                    and apply_price(state, prices, "ninja")):
                continue
            still_unresolved.append(state)
        unresolved = still_unresolved

    # 3. Pinnacle — endast per-matchup-pris med HTTP Age ≤90 s. Bulken används
    # för identiteten och som reserv bara när även den råkar vara lika färsk.
    if unresolved:
        try:
            with pinnacle.Pinnacle(timeout=8.0) as client:
                pinnacle_events = client.soccer_live_totals()
                fresh_by_event: dict[str, Optional[dict]] = {}
                still_unresolved = []
                for state in unresolved:
                    event = _live_event_for(pinnacle_events, state)
                    if not event:
                        still_unresolved.append(state)
                        continue
                    event_id = str(event.get("id"))
                    if event_id not in fresh_by_event:
                        fresh_by_event[event_id] = client.refresh_live_1x2(
                            event.get("matchup_ids") or [])
                    fresh = fresh_by_event[event_id]
                    prices = None
                    if (fresh and fresh.get("status") == "captured"
                            and int(fresh.get("age_s") or 0)
                            <= PINNACLE_LIVE_MAX_AGE_S):
                        prices = fresh.get("odds")
                    elif ((not fresh or fresh.get("status") != "captured")
                          and event.get("odds_status") == "captured"
                          and int(event.get("age_s") or 0)
                          <= PINNACLE_LIVE_MAX_AGE_S):
                        prices = event.get("odds")
                    if apply_price(state, prices, "pinnacle"):
                        continue
                    still_unresolved.append(state)
                unresolved = still_unresolved
        except Exception:  # noqa: BLE001 — sista reservkälla får inte fälla vyn
            pass

    for state in unresolved:
        # Stängd livemarknad är inte okunskap. Ställningen och marknadens eget
        # prematchpris finns kvar, och att kasta båda gav "0 %–77 %" på en
        # kupong där NK Celje ledde 2–0 i andra halvlek (2026-08-11).
        modelled = live_probs_from_score(state)
        if modelled:
            state["probs"] = modelled
            state["probs_basis"] = "modell"
            state["probs_source"] = "modell"
        else:
            state["probs"] = None
            state["probs_basis"] = "live_saknas"
            state["probs_source"] = None


def _parse_live_start(value) -> Optional[dt.datetime]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _same_live_start(state: dict, event: dict) -> bool:
    left = _parse_live_start(state.get("start"))
    right = _parse_live_start(event.get("start"))
    return bool(left and right and abs(left - right) <= dt.timedelta(minutes=30))


def _live_event_for(catalogue: list[dict], state: dict) -> Optional[dict]:
    """Entydig poolmatch → provider-event, alltid i samma orientering.

    Båda lagen går först. Ett kortnamn får accepteras i kontext när den andra
    sidan är strikt samma lag. Sista steget tillåter bara ett lag, och då är
    känd avspark på båda sidor, högst 30 minuters skillnad och exakt en
    kandidat obligatoriskt. Spegelvända event avslås eftersom 1 och 2 annars
    skulle byta betydelse.
    """
    from .live_radar import _same_team, _same_team_in_context
    home, away = state.get("home"), state.get("away")
    if not (home and away):
        return None

    def distinct(events: list[dict]) -> list[dict]:
        # Altenars samma event kan i princip förekomma under två menygrenar.
        # Samma provider-id två gånger är en kandidat, inte tvetydighet.
        by_id = {}
        for event in events:
            key = str(event.get("id")) if event.get("id") is not None else id(event)
            by_id[key] = event
        return list(by_id.values())

    direct = distinct([event for event in catalogue
                       if _same_team(event.get("home") or "", home)
                       and _same_team(event.get("away") or "", away)])
    if direct:
        return direct[0] if len(direct) == 1 else None

    contextual = []
    one_side = []
    for event in catalogue:
        home_same = _same_team(event.get("home") or "", home)
        away_same = _same_team(event.get("away") or "", away)
        if ((home_same and _same_team_in_context(
                event.get("away") or "", away))
                or (away_same and _same_team_in_context(
                    event.get("home") or "", home))):
            contextual.append(event)
        if ((home_same or away_same) and _same_live_start(state, event)):
            one_side.append(event)
    contextual = distinct(contextual)
    if contextual:
        return contextual[0] if len(contextual) == 1 else None
    one_side = distinct(one_side)
    return one_side[0] if len(one_side) == 1 else None


def _kambi_id_for(catalogue: list[dict], state: dict) -> Optional[str]:
    """Poolmatch → Kambis live-event via normaliserade lagnamn.

    Listan slås upp direkt i stället för via `oddset_matches`: poolerna
    innehåller Ettan, Elitettan och utländska serier som ligger helt utanför
    Oddsets tio ligor, så en Oddset-slagning tappade de flesta.

    Hemma/borta måste stämma på SAMMA sida — en spegelvänd träff kan vara ett
    returmöte, och ett pris på fel lag är värre än inget pris. Entydighet krävs.
    """
    event = _live_event_for(catalogue, state)
    return str(event["id"]) if event and event.get("id") is not None else None


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


def live_status(coupon: dict, states: list[dict],
                include_chance: bool = True) -> dict:
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
    decided = sum(1 for s in col_states if _decided(s))
    best_secure = 0
    secure_hist: dict[int, int] = {}
    possible_hist: dict[int, int] = {}
    per_row: list[tuple[int, int, int]] = []      # (radnr, säkra, möjliga)
    for n, row in enumerate(rows, start=1):
        secure = possible = 0
        for i in range(width):
            state = col_states[i]
            if not _decided(state):
                possible += 1        # okänd/struken/pågående kan ännu bli rätt
                continue
            hit = state.get("sign") == row[i]
            secure += int(hit)
            possible += int(hit)
        best_secure = max(best_secure, secure)
        secure_hist[secure] = secure_hist.get(secure, 0) + 1
        possible_hist[possible] = possible_hist.get(possible, 0) + 1
        per_row.append((n, secure, possible))
    # `best_secure` räknar bara resultat som står fast. Användaren vill
    # dessutom kunna se den intuitiva liverättningen: hur många rätt kupongen
    # har OM de aktuella ställningarna står sig. De två måtten får inte
    # blandas — det ena är facit hittills, det andra ett ögonblicksläge.
    current_cols = [i for i, state in enumerate(col_states)
                    if state and not state.get("cancelled")
                    and state.get("sign") in SIGNS]
    current_scores = [sum(row[i] == col_states[i].get("sign")
                          for i in current_cols)
                      for row in rows]
    current_best = max(current_scores) if current_scores else None
    current_best_rows = (sum(score == current_best for score in current_scores)
                         if current_best is not None else 0)
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
    out = {"n_events": width, "n_decided": decided,
           "all_decided": bool(width and decided == width),
           "best_secure": best_secure,
           "current_known": len(current_cols),
           "current_best": current_best,
           "current_best_rows": current_best_rows,
           "max_possible": max_possible,
           # Ingen rad kan nå ens den lägsta redovisade vinstnivån.
           "out_of_contention": bool(levels) and max_possible < min(levels),
           "secure_dist": dict(sorted(secure_hist.items(), reverse=True)),
           "alive_per_level": dict(sorted(alive.items(), reverse=True)),
           **alive_span,
           **_alive_rows(rows, per_row, col_states, width, levels),
           "matches": _match_rows(rows, col_states, events, width),
           "cheer": _cheer_per_match(rows, col_states, width, levels)}
    # Idag-kortet visar faktisk matchstatus och levande rader men ingen
    # oddsbaserad vinstchans. Den dyrare sannolikheten hör till detaljkortet i
    # Historik och får inte hålla grundläggande livestatus gisslan.
    if include_chance:
        out.update(_chance_per_level(rows, col_states, width, levels))
    return out




ALIVE_ROWS_MAX = 40     # längre listor läses inte; totalen redovisas ändå


def _alive_rows(rows: list[str], per_row: list[tuple[int, int, int]],
                col_states: list[Optional[dict]], width: int,
                levels: list[int]) -> dict:
    """VILKA rader som lever, inte bara hur många.

    Aggregatet "3 rader kvar till 12 rätt" går inte att agera på: kupongen har
    hundratals rader och siffran pekar inte ut någon av dem. Här får varje
    överlevande rad sitt radnummer, sina säkrade rätt och — det som faktiskt
    betyder något — vilka tecken den behöver i de matcher som ÄR KVAR.

    En rad räknas som levande om den fortfarande kan nå den LÄGSTA redovisade
    vinstnivån, samma tröskel som `out_of_contention`. Sorteringen är säkra
    rätt fallande, så de rader som kan nå toppnivån står först.

    Öppna kolumner är exakt `_decided()`s komplement: en struken match och ett
    obelagt förlängningstecken är öppna här också. Raden visas alltså med det
    tecken den BEHÖVER, aldrig med ett tecken vi gissat åt Svenska Spel.
    """
    if not rows or not levels or not width:
        return {}
    floor = min(levels)
    open_cols = [i for i in range(width) if not _decided(col_states[i])]
    alive = [(n, secure, possible) for n, secure, possible in per_row
             if possible >= floor]
    alive.sort(key=lambda r: (-r[1], r[0]))
    out = []
    for n, secure, possible in alive[:ALIVE_ROWS_MAX]:
        row = rows[n - 1]
        out.append({
            "n": n,
            "row": row,
            "secure": secure,
            "possible": possible,
            "open": [{"col": i + 1, "sign": row[i]} for i in open_cols],
        })
    return {"alive_rows": out,
            "alive_rows_total": len(alive),
            "alive_rows_open_cols": [i + 1 for i in open_cols]}


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
    """Står tecknet fast?

    En struken match är öppen tills SvS fastställt tecknet. Detsamma gäller
    ett förlängningstecken som bara härletts ur Current: ordinarie tid är då
    slut, men vilket pooltecken som faktiskt gäller är ännu inte belagt.
    """
    return bool(state and state.get("final") and not state.get("cancelled")
                and not state.get("sign_provisional"))


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
CHANCE_SAMPLES = 20000              # Monte Carlo när ingen exakt väg finns
# Att nå nivån L betyder att utfallet ligger inom Hamming-avstånd
# `secure + k - L` från någon rad. För de nivåer som betyder mest är det klotet
# LITET: med 13 matcher rymmer radie 0 en enda punkt, radie 1 tjugosju och
# radie 2 tvåhundratrettionio. Unionen av raderna klot går därför att räkna upp
# exakt, och det är BILLIGARE än att simulera — 3,1 miljoner kandidater mot
# Monte Carlos 20,5 miljoner för en 1024-raderskupong.
#
# Skälet att göra det är dock inte farten utan att simuleringen LJUG om
# toppnivån: 13 rätt kom aldrig upp i 20 000 dragningar och redovisades som
# exakt 0,0 % fast ingen match var avgjord. Monte Carlo kan inte skilja
# omöjligt från osannolikt, och det är precis toppnivån man tittar på.
CHANCE_BALL_MAX_CANDIDATES = 4_000_000
SIGN_DIGIT = {"1": 0, "X": 1, "2": 2}
# Fler oprissatta matcher än så ger ett intervall så brett att det inte säger
# något — då är noten ärligare än en gräns mellan 0 och 100 %.
CHANCE_MAX_UNPRICED = 2


def _round_chance(value: float) -> float:
    """Avrunda en chans utan att göra den liten men verkliga till NOLL.

    `round(x, 6)` skrev 3e-07 som 0.0, och UI:t visar `0%` för exakt noll och
    `<0,1%` för allt annat smått. Kupongen påstod alltså att 13 rätt var
    UTESLUTET medan samtliga tretton matcher ännu var oavgjorda. En liten chans
    och en omöjlig chans är inte samma sak, och skillnaden är hela poängen med
    den översta raden.

    Positiva värden behåller därför alltid minst tre värdesiffror.
    """
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return round(value, max(6, 2 - math.floor(math.log10(value))))


def _ball_size(width: int, radius: int) -> int:
    """Antal utfall inom Hamming-avstånd `radius` när varje match har tre tecken."""
    return sum(math.comb(width, d) * 2 ** d for d in range(radius + 1))


def _ball_union_probabilities(items, probs, levels) -> Optional[dict]:
    """Exakt P(bästa raden når nivån) via unionen av radernas Hamming-klot.

    En rad når nivån L exakt när utfallet avviker på högst `secure + k - L`
    matcher. Mängden sådana utfall är ett Hamming-klot runt radens
    teckenmönster, och nivåns sannolikhet är massan i UNIONEN av alla raders
    klot — därav att vikten skrivs på utfallets KOD, så att ett utfall som två
    rader båda täcker räknas en gång.

    Returnerar None när klotet inte ryms i budgeten, eller när någon
    sannolikhet är exakt noll: vikten räknas fram genom att dividera bort de
    tecken som byts ut, och en nolla i nämnaren stänger den vägen.
    """
    width = len(probs)
    if not width or not levels or not items:
        return None
    signs = ("1", "X", "2")
    if any(float(column.get(sign) or 0.0) <= 0.0
           for column in probs for sign in signs):
        return None

    radii = {level: [secure + width - level for _, secure in items]
             for level in levels}
    budget = sum(_ball_size(width, radius)
                 for level in levels for radius in radii[level]
                 if 0 <= radius < width)
    if budget > CHANCE_BALL_MAX_CANDIDATES:
        return None

    powers = [3 ** i for i in range(width)]
    hit: dict[int, float] = {}
    for level in levels:
        level_radii = radii[level]
        if any(radius >= width for radius in level_radii):
            hit[level] = 1.0            # klotet täcker hela utfallsrummet
            continue
        mass: dict[int, float] = {}
        for (pattern, _secure), radius in zip(items, level_radii):
            if radius < 0:
                continue                # raden kan inte nå nivån alls
            base_code = 0
            base_weight = 1.0
            for i in range(width):
                base_code += SIGN_DIGIT[pattern[i]] * powers[i]
                base_weight *= probs[i][pattern[i]]
            mass[base_code] = base_weight
            # Per match: vad de TVÅ andra tecknen gör med koden och vikten.
            # Räknas en gång per rad i stället för en gång per kandidat —
            # den innersta loopen går miljontals varv och ska inte slå upp
            # siffertabeller den redan känner.
            swaps = [[((SIGN_DIGIT[sign] - SIGN_DIGIT[pattern[i]]) * powers[i],
                       probs[i][sign])
                      for sign in signs if sign != pattern[i]]
                     for i in range(width)]
            for distance in range(1, radius + 1):
                for positions in itertools.combinations(range(width), distance):
                    stem = base_weight
                    for i in positions:
                        stem /= probs[i][pattern[i]]
                    for choice in itertools.product(
                            *[swaps[i] for i in positions]):
                        code = base_code
                        weight = stem
                        for delta, probability in choice:
                            code += delta
                            weight *= probability
                        mass[code] = weight
        hit[level] = sum(mass.values())
    return hit


def _hit_probabilities(groups, probs, levels) -> tuple[dict, str]:
    """P(bästa raden når nivån) över de PRISSATTA matchernas utfallsrum.

    `groups` är {teckenmönster över de prissatta kolumnerna: bästa säkrade
    antal rätt}. Raderna delar matcherna, så utfallen är beroende — därför
    räknas hela utfallsrummet i stället för en produkt av per-rad-chanser.
    """
    signs = ("1", "X", "2")
    hit = {lvl: 0.0 for lvl in levels}
    items = list(groups.items())

    # Koda varje teckenmönster med två bitmasker; 2 är läget där varken
    # 1- eller X-biten är satt. Antal rätt blir k minus Hamming-avståndet.
    # Det ger exakt samma poäng och samma slumpdragningar som den äldre
    # tecken-för-tecken-loopen, men slipper miljontals Python-jämförelser.
    compiled = []
    for pattern, secure in items:
        ones = sum(1 << i for i, sign in enumerate(pattern) if sign == "1")
        crosses = sum(1 << i for i, sign in enumerate(pattern) if sign == "X")
        compiled.append((ones, crosses, secure))

    def score_masks(ones: int, crosses: int) -> int:
        return max(
            secure + len(probs)
            - (((ones ^ row_ones) | (crosses ^ row_crosses)).bit_count())
            for row_ones, row_crosses, secure in compiled)

    def score(outcome: tuple) -> int:
        ones = sum(1 << i for i, sign in enumerate(outcome) if sign == "1")
        crosses = sum(1 << i for i, sign in enumerate(outcome) if sign == "X")
        return score_masks(ones, crosses)

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

    # Exakt uppräkning av radernas Hamming-klot när den ryms i budgeten.
    exact = _ball_union_probabilities(items, probs, levels)
    if exact is not None:
        return exact, "exakt"

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
    open_cols = [i for i in range(width) if not _decided(col_states[i])]
    priced_cols, priced_probs, unpriced_cols, unpriced_names = [], [], [], []
    live_used = modelled_used = 0
    live_source_counts: dict[str, int] = {}
    for i in open_cols:
        state = col_states[i] or {}
        # Current under förlängning kan bära förlängningsmål. Även ett gammalt
        # prematchpris vore då falsk precision för ett tecken vars facit ännu
        # inte är känt; redovisa i stället intervallet över 1/X/2.
        p = None if state.get("sign_provisional") else state.get("probs")
        if p and abs(sum(p.values()) - 1.0) <= 0.01:
            priced_cols.append(i)
            priced_probs.append(p)
            if state.get("probs_basis") == "live":
                live_used += 1
                source = state.get("probs_source") or "okänd"
                live_source_counts[source] = live_source_counts.get(source, 0) + 1
            elif state.get("probs_basis") == "modell":
                modelled_used += 1
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
                if _decided(state):
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
           "chance_live_matches": live_used,
           "chance_modelled_matches": modelled_used,
           "chance_live_source_counts": live_source_counts}
    if not unpriced_cols:
        out["chance_per_level"] = {lvl: _round_chance(hi[lvl]) for lvl in levels}
        return out
    out["chance_min_per_level"] = {lvl: _round_chance(lo[lvl]) for lvl in levels}
    out["chance_max_per_level"] = {lvl: _round_chance(hi[lvl]) for lvl in levels}
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


def coupon_detail(store: Storage, coupon_id: int) -> Optional[dict]:
    """Exakta sparade rader mot officiellt facit, bara för detaljvyn.

    Databasen bär `rows_text`, men matchnamn och officiella utfall hör hemma i
    settlementlagret. Slå ihop dem först när en kupong öppnas så att Historik
    inte blir tyngre för varje sparad kupong.
    """
    raw = store.conn.execute(
        "SELECT c.*, COALESCE(s.reg_close_time, d.reg_close_time) AS draw_close "
        "FROM pool_played_coupon c "
        "LEFT JOIN pool_draw_settlement s "
        "ON s.product=c.product AND s.draw_number=c.draw_number "
        "LEFT JOIN draws d "
        "ON d.product=c.product AND d.draw_number=c.draw_number "
        "WHERE c.id=?", (int(coupon_id),)).fetchone()
    if raw is None:
        return None
    coupon = dict(raw)
    rows = [row for row in (coupon.get("rows_text") or "").split("\n") if row]
    width = len(rows[0]) if rows else 0
    events_order = _coupon_events(coupon, width)

    event_rows = {int(row["event_number"]): dict(row) for row in store.conn.execute(
        "SELECT event_number, description, home, away, match_start, outcome, "
        "cancelled FROM pool_event_settlement WHERE product=? AND draw_number=?",
        (coupon["product"], coupon["draw_number"]))}
    events = []
    outcomes = []
    for col, event_number in enumerate(events_order, start=1):
        event = event_rows.get(event_number, {})
        outcome = event.get("outcome") if event.get("outcome") in SIGNS else None
        outcomes.append(outcome)
        events.append({
            "column": col, "event_number": event_number,
            "description": event.get("description"),
            "home": event.get("home"), "away": event.get("away"),
            "match_start": event.get("match_start"), "outcome": outcome,
            "cancelled": bool(event.get("cancelled")),
        })

    tiers = {}
    for tier in store.conn.execute(
            "SELECT tier_name, correct, winners, amount FROM pool_payout_tier "
            "WHERE product=? AND draw_number=? AND correct IS NOT NULL",
            (coupon["product"], coupon["draw_number"])):
        item = dict(tier)
        correct = int(item["correct"])
        tiers[correct] = {
            "name": item.get("tier_name"), "correct": correct,
            "winners": item.get("winners"), "amount": item.get("amount"),
        }

    facit_complete = bool(width and len(outcomes) == width
                          and all(outcome in SIGNS for outcome in outcomes))
    row_results = []
    computed_dist: dict[int, int] = {}
    for index, row in enumerate(rows, start=1):
        correct = (sum(sign == outcome for sign, outcome in zip(row, outcomes))
                   if facit_complete else None)
        if correct is not None:
            computed_dist[correct] = computed_dist.get(correct, 0) + 1
        tier = tiers.get(correct) if correct is not None else None
        amount = tier.get("amount") if tier else 0.0
        row_results.append({
            "index": index, "signs": row, "correct": correct,
            # `None` betyder publicerad nivå utan belopp; 0 betyder ingen
            # vinstnivå. Samma distinktion som i settle().
            "payout_kr": float(amount) if amount is not None else None,
            "prize_level": bool(tier),
        })
    row_results.sort(key=lambda item: (
        -(item["correct"] if item["correct"] is not None else -1), item["index"]))

    stored_dist = {}
    try:
        stored_dist = {int(k): int(v) for k, v in json.loads(
            coupon.get("correct_dist") or "{}").items()}
    except (TypeError, ValueError, AttributeError):
        pass
    public_coupon = {key: value for key, value in coupon.items()
                     if key not in {"rows_text", "events_order"}}
    return {
        "coupon": public_coupon, "events": events, "rows": row_results,
        "correct_dist": computed_dist if facit_complete else stored_dist,
        "tiers": [tiers[key] for key in sorted(tiers, reverse=True)],
        "facit_complete": facit_complete,
        "facit": "".join(outcome or "?" for outcome in outcomes),
        "audit_matches_stored": (not facit_complete or not stored_dist
                                  or computed_dist == stored_dist),
    }


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
