"""PH3: systemledger — frys byggarens konkreta förslag före spelstopp och
settla mot riktigt facit + riktig utdelning (pool_draw_settlement).

Benchmarkmatrisen är FÖRREGISTRERAD: ändra aldrig en befintlig config_key i
efterhand — lägg till nya nycklar om något nytt ska mätas. Dagens byggare är
champion; ingen policyändring promoveras på det material som valde den
(förregistrerad gate + out-of-time-fönster, se överlämningen 2026-07-24).

Frysning sker i snapshotvarvet med varvets PIT-färska draw-objekt (inga
extra API-anrop utom jackpot). Sena frysningar sparas men flaggas
`timely=0` — poolvarvets kadens är 30 min (5 min i tätläget), därav
horisonttoleranserna nedan. Bomben ingår inte (egen kolumnbyggare, ingen
1X2-EV-motor).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import random
from typing import Optional

from . import pool_settlement
from .analysis import DrawAnalysis, analyze_draw
from .builder import build_ev_system, ev_candidate_signs
from .storage import Storage
from .svenskaspel import Draw, family_of

# (minuter före spelstopp, timely-tolerans i minuter)
FREEZE_HORIZONS = {"h3": (180, 30), "m20": (20, 10)}
SETTLEMENT_VERSION = "counterfactual-v2"
CANCELLED_NOTE = "omgången inställd — ingen insats, inget facit"

# Förregistrerad gate (docs/ph3-gate-2026-07-26.md): en utmanare får inte
# promoveras till champion på mindre underlag än så här, oavsett hur bra deltat
# ser ut. FDR_Q matchar Oddset-sidans utforskande familj.
GATE_MIN_DRAWS = 40
FDR_Q = 0.10
BOOTSTRAP_ITERS = 2000

# GENERATION 2, förregistrerad 2026-08-05 (Samans beslut, se
# docs/historik-ui-2026-08-05.md). Full grid: fyra budgetar × tre riskprofiler.
#
# Budgetarna är radantal: radpriset är 1,00 kr för SAMTLIGA produkter, så
# budget i kronor = antal rader. 144 är en exakt Hamming-täckning (R 4-4-144),
# resten är tvåpotenser. Generation 1:s 50/256 valdes utan den kopplingen.
#
# Riskprofilen är EN axel: strategin sätter bara värdeviktens startpunkt
# 20/50/80 (samma regel som UI-reglaget), så `value_weight` är härledd ur
# `strategy` och inte en fri parameter. Därför bär nyckeln inte längre `vw`.
#
# Matrisstorleken kostar inget i tid — byggaren mättes till 0,12 s oberoende
# av budget, alltså ~15 s för hela matrisen per varv. Priset är statistiskt:
# 12 konfigurationer × 5 produkter = 60 utmanarjämförelser, där ~3 ser
# signifikanta ut av ren slump. Grinden använder därför BH-FDR över
# utmanarfamiljen (`challenger_fdr`), aldrig per grupp isolerat.
#
# GENERATION 1 (`ev50-medel-vw50` ★, `ev50-tuff-vw80`, `ev256-medel-vw50`) är
# PENSIONERAD. Dess rader ligger kvar under sina egna config_key:er och blandas
# aldrig in — en config_key ändras ALDRIG i efterhand. Championen där var
# dessutom felaktigt etiketterad: den registrerades som 50 kr medan appens
# byggare stod på 128 kr, så "champion = dagens byggare" var inte sant.
#
# (nyckelslug, byggarens strateginamn, värdevikt). Sluggen är ASCII så
# config_key förblir URL- och filnamnssäker; strategivärdet MÅSTE vara exakt
# `builder.STRATEGIES`-nyckeln ("säker" med ä), annars KeyError vid frysning.
RISK_PROFILES = (("saker", "säker", 0.2),
                 ("medel", "medel", 0.5),
                 ("tuff", "tuff", 0.8))
BUDGETS = (144.0, 256.0, 512.0, 1024.0)
CHAMPION_KEY = "b256-medel"
RETIRED_KEYS = ("ev50-medel-vw50", "ev50-tuff-vw80", "ev256-medel-vw50")

BENCHMARKS = tuple(
    {"key": f"b{int(budget)}-{slug}", "budget": budget,
     "strategy": strategy, "value_weight": weight,
     "primary": f"b{int(budget)}-{slug}" == CHAMPION_KEY}
    for budget in BUDGETS
    for slug, strategy, weight in RISK_PROFILES
)

# PH5 FORWARD, RESEARCH-ONLY (förregistrerat 2026-08-15 före omgång 4966).
#
# Historiken gav en lovande 5 000-raderssignal men passerade INTE grinden mot
# folk-/favoritrad. Därför får dessa nycklar samla äkta point-in-time-facit,
# men de ingår ALDRIG i `benchmarks_for`, championrapporten eller automatisk
# promotion. Fyra armar med samma radantal gör testet tolkningsbart.
PH5_FORWARD_START_DRAW = 4966

# EUROPATIPSET KOM MED 2026-08-18 (Samans beslut). Det var dessutom den
# produkt som PASSERADE den historiska grinden — mot folk-, favorit- OCH
# byggarslump på BÅDA budgetarna — medan Stryktipset föll. Att bara följa
# Stryktipset framåt var alltså att samla data på den svagare hypotesen.
#
# Kör hen på 5 000 som Stryktipset, inte på 4 096. Skälet är praktiskt: det är
# beloppet som faktiskt övervägs, och nycklarna är research-only och kan aldrig
# promoveras, så budgetvalet är inte ett urval på data i den mening
# beslutsregeln förbjuder. Men det betyder också att ett FRAMTIDA
# promotionsargument för Europatipset inte kan luta sig mot den här serien:
# förregistreringen pekade ut 4 096 som lägsta passerande budget, och den
# frågan får en egen grind.
PH5_FORWARD_PRODUCTS = ("stryktipset", "europatipset")
PH5_FORWARD_START_DRAW_BY_PRODUCT = {
    "stryktipset": 4966,
    # Europatipsets serie börjar på 2600, som är öppen med spelstopp
    # 2026-08-20 18:59 CEST och ännu inte har en enda frysning. Båda
    # horisonterna ligger alltså i framtiden — det är en äkta point-in-time-
    # start, inte bakfyllning. Ett system byggt efter facit vore falsk evidens.
    "europatipset": 2600,
}

# FOLKRAD ÄR AVSLUTAD 2026-08-18 — den var en dubblett, inte en kontroll.
#
# Uppmätt på omgång 4966: `favoritrad` och `folkrad` delade 4 576 av 5 000
# exakta rader vid h3 (91,5 %) och 4 503 av 5 000 vid m20 (90,1 %). Båda gav
# dessutom identiskt facit, 9 respektive 8 rätt. Det är väntat — poolfolkets
# streck ligger nära marknadens sannolikhet på teckennivå — men det betyder
# att "slå tre kontroller" i praktiken var "slå två". Till jämförelse delade
# `varderader` bara 1–2 % av raderna med dem och 12 % med byggarslump.
#
# Att blanda ihop dem till en kombinerad arm hade inte hjälpt: en blandning av
# två 91-procentigt identiska rankningar är samma rankning igen. Slotten går
# därför till `maxev`, som testar något ingen annan arm gör — byggarens EGEN
# balansknapp. Ordinarie medel kör `träffchans^1 × EV`; maxev kör ren EV utan
# träffchansdämpning (`value_weight=1.0`, k=0). Skiljer de sig i facit vet vi
# att knappen bär vikt; gör de inte det är den ett reglage utan verkan.
#
# De frysta folkrad-raderna från 4966 ligger kvar (append-once) och redovisas
# som en avslutad arm. De får inte blandas in i maxev-serien. Nyckeln står
# därför kvar i `PH5_RETIRED_CONFIGS`: översikten filtrerar bort config_key:er
# som inte hör till någon känd familj (för att en b1024-rad på ett 8-matchsspel
# inte ska se ut som en levande utmanare), och utan den här listan hade
# folkraden tystnat i stället för att redovisas som avslutad.
PH5_RETIRED_CONFIGS = (
    {"key": "ph5-v3-b5000-folkrad", "budget": 5000.0,
     "strategy": "folkrad", "value_weight": 0.0,
     "method": "folkrad"},
)
PH5_FORWARD_CONFIGS = (
    {"key": "ph5-v3-b5000-medel", "budget": 5000.0,
     "strategy": "medel", "value_weight": 0.5,
     "method": "varderader"},
    {"key": "ph5-v3-b5000-byggarslump", "budget": 5000.0,
     "strategy": "byggarslump", "value_weight": 0.5,
     "method": "byggarslump"},
    {"key": "ph5-v3-b5000-favoritrad", "budget": 5000.0,
     "strategy": "favoritrad", "value_weight": 0.0,
     "method": "favoritrad"},
    {"key": "ph5-v3-b5000-maxev", "budget": 5000.0,
     "strategy": "maxev", "value_weight": 1.0,
     "method": "maxev"},
)

# BUDGETTAK FÖR 8-MATCHSSPELEN (Samans beslut 2026-08-09).
#
# Budgeten är antal rader, och hur mycket en budget "är" beror på hur stort
# utfallsrummet är. Topptipset-spelen har 8 matcher, alltså 3^8 = 6 561
# möjliga rader: 1 024 rader köper då 15,6 % av HELA rummet. Det är inte
# längre ett radval utan en mattbombning, och spelen har dessutom bara EN
# vinstnivå (8 rätt) att fördela på. Samma 1 024 rader på ett 13-matchsspel
# är 1 024 / 1 594 323 = 0,06 % — en genuin selektion. Matrisen måste därför
# vara produktberoende; en gemensam budgetlista mätte olika saker i samma
# namn.
#
# ÄRLIGHETSNOT: uteslutningen gjordes EFTER att de första b1024-raderna var
# synliga (2–3 per produkt/horisont, alla från 2026-08-06 och framåt). Den
# vilar på utfallsrummets storlek och inte på deras ROI, men den är därmed
# inte en ren förregistrering, och de kvarvarande Topptipset-jämförelserna
# ska läsas med det i minnet. Se docs/db-atgarder.md 2026-08-09.
EIGHT_MATCH_PRODUCTS = frozenset(
    {"topptipset", "topptipsetstryk", "topptipsetextra"})
EIGHT_MATCH_MAX_BUDGET = 512.0


def benchmarks_for(product: str) -> tuple[dict, ...]:
    """Benchmarkfamiljen för EN produkt — enda källan till vad som mäts.

    Frysning, championrapport och översikt MÅSTE läsa samma familj, annars
    dyker en konfiguration upp i tabellen som varvet inte längre fryser.
    """
    if product in EIGHT_MATCH_PRODUCTS:
        return tuple(b for b in BENCHMARKS
                     if b["budget"] <= EIGHT_MATCH_MAX_BUDGET)
    return BENCHMARKS


def research_configs_for(product: str,
                         draw_number: Optional[int] = None) -> tuple[dict, ...]:
    """PH5:s separata forwardfamilj; aldrig en del av promotionsfamiljen."""
    if product not in PH5_FORWARD_PRODUCTS:
        return ()
    start = PH5_FORWARD_START_DRAW_BY_PRODUCT.get(
        product, PH5_FORWARD_START_DRAW)
    if draw_number is not None and draw_number < start:
        return ()
    return PH5_FORWARD_CONFIGS


def _parse(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _frozen(store: Storage, product: str, draw_number: int,
            horizon: str, key: str) -> bool:
    return store.conn.execute(
        "SELECT 1 FROM pool_system_ledger WHERE product=? AND draw_number=? "
        "AND horizon=? AND config_key=?",
        (product, draw_number, horizon, key)).fetchone() is not None


def _ph5_binary_rows(analysis: DrawAnalysis, n_rows: int,
                     method: str) -> list[list[str]]:
    """PH5:s folk-/favoritkontroll ur samma binära pool som historiken."""
    per_match: list[list[str]] = []
    for match in analysis.matches:
        ranked = sorted(
            ("1", "X", "2"),
            key=lambda sign: -float(
                match.outcomes[sign].fair_prob
                if match.outcomes[sign].fair_prob is not None else 1 / 3),
        )
        per_match.append(ranked[:2])

    def score(row: tuple[str, ...]) -> float:
        value = 1.0
        for match, sign in zip(analysis.matches, row):
            outcome = match.outcomes[sign]
            if method == "folkrad":
                total = sum(match.outcomes[s].streck or 0
                            for s in ("1", "X", "2")) or 1
                probability = max((outcome.streck or 0) / total, 0.001)
            else:
                probability = float(
                    outcome.fair_prob
                    if outcome.fair_prob is not None else 1 / 3)
            value *= probability
        return value

    rows = list(itertools.product(*per_match))
    rows.sort(key=score, reverse=True)
    return [list(row) for row in rows[:n_rows]]


def _ph5_control_rows(analysis: DrawAnalysis, config: dict,
                      horizon: str) -> list[list[str]]:
    """Bygg en deterministisk kontroll med samma 5 000-radersbudget."""
    row_price = analysis.row_price or 1.0
    target = max(1, int(config["budget"] / row_price))
    method = config["method"]
    if method in ("folkrad", "favoritrad"):
        return _ph5_binary_rows(analysis, target, method)
    if method == "maxev":
        # Samma byggare, enda skillnaden är balansknappen: k = 2·(1−vw), så
        # vw=1.0 ger k=0 och alltså ren EV utan träffchansdämpning. Den delar
        # kandidatuniversum och vinstplan med ordinarie medel, vilket är hela
        # poängen — skillnaden i facit ÄR knappens effekt.
        system = build_ev_system(
            analysis, "maxev", config["budget"], row_price=row_price,
            value_weight=1.0, plan=_prize_plan(analysis.product),
            jackpot=0.0)
        return [list(row) for row in system.rows]
    if method != "byggarslump":
        raise ValueError(f"okänd PH5-kontroll: {method}")
    signs, _universe = ev_candidate_signs(analysis, value_weight=0.5)
    pool = list(itertools.product(*(
        signs[match.event_number] for match in analysis.matches)))
    seed_text = (f"ph5-forward-v3|{analysis.product}|{analysis.draw_number}|"
                 f"{horizon}|{config['key']}")
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    return [list(row) for row in rng.sample(pool, min(target, len(pool)))]


def freeze_due(store: Storage, product: str, draw: Draw,
               sharp: Optional[dict] = None, movement: Optional[dict] = None,
               jackpot: Optional[float] = None,
               jackpot_source: str = "missing",
               now: Optional[dt.datetime] = None,
               code_version: str = "dev") -> dict:
    """Frys benchmarksystem för en öppen omgång vars horisontfönster öppnats.
    draw = varvets färska Draw-objekt (point-in-time)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    close = _parse(draw.reg_close_time)
    report = {"frozen": 0}
    if close is None or close <= now:
        return report
    due = [(hz, mins, tol) for hz, (mins, tol) in FREEZE_HORIZONS.items()
           if now >= close - dt.timedelta(minutes=mins)]
    if not due:
        return report
    plan = _prize_plan(product)
    analysis: Optional[DrawAnalysis] = None
    for horizon, minutes, tol in due:
        configs = (*benchmarks_for(product),
                   *research_configs_for(product, draw.draw_number))
        for bench in configs:
            if _frozen(store, product, draw.draw_number, horizon, bench["key"]):
                continue
            if analysis is None:
                analysis = analyze_draw(draw, sharp or {}, movement or {})
                turnover_used, basis = _valuation_turnover(
                    store, product, analysis.turnover or 0.0,
                    close_iso=close.isoformat())
                if turnover_used > (analysis.turnover or 0.0):
                    analysis.turnover = turnover_used
                jp = max(0.0, jackpot or 0.0)
            method = bench.get("method", "varderader")
            if method == "varderader":
                system = build_ev_system(
                    analysis, bench["strategy"], bench["budget"],
                    row_price=analysis.row_price or 1.0,
                    value_weight=bench["value_weight"], plan=plan, jackpot=jp)
                rows = system.rows
                n_rows = system.num_rows
                cost = system.cost
                build_note = system.note
            else:
                rows = _ph5_control_rows(analysis, bench, horizon)
                n_rows = len(rows)
                cost = n_rows * (analysis.row_price or 1.0)
                build_note = (f"PH5 forward research-only: {method}, "
                              f"{n_rows} frysta rader")
            if not rows:
                continue   # gick inte att bygga — nästa varv försöker igen
            if "method" in bench:
                research_target = max(
                    1, int(bench["budget"] / (analysis.row_price or 1.0)))
                if n_rows != research_target:
                    continue   # delsystem får inte se ut som ett giltigt test
            events_order = ",".join(
                str(match.event_number) for match in analysis.matches)
            rows_text = "\n".join(",".join(row) for row in rows)
            covered = sum(
                1 for match in analysis.matches
                if any(match.outcomes[s].fair_prob is not None
                       for s in ("1", "X", "2")))
            cutoff = close - dt.timedelta(minutes=minutes)
            lag = round((now - cutoff).total_seconds() / 60, 1)
            store.conn.execute(
                "INSERT INTO pool_system_ledger (product, draw_number, horizon, "
                "config_key, frozen_at, lag_min, timely, code_version, budget, "
                "strategy, value_weight, row_price, n_rows, cost_kr, "
                "events_order, rows_text, rows_hash, n_events_covered, "
                "turnover_used, turnover_basis, jackpot_used, jackpot_source, "
                "build_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (product, draw.draw_number, horizon, bench["key"], _iso(now),
                 lag, int(lag <= tol), code_version, bench["budget"],
                 bench["strategy"], bench["value_weight"],
                 analysis.row_price or 1.0, n_rows, cost,
                 events_order, rows_text,
                 hashlib.sha256(rows_text.encode()).hexdigest()[:16],
                 covered, turnover_used, basis, jp, jackpot_source, build_note))
            if not store._bulk:  # noqa: SLF001
                store.conn.commit()
            report["frozen"] += 1
    return report


def _valuation_turnover(store: Storage, product: str, current: float,
                        close_iso: str | None = None) -> tuple[float, str]:
    """Samma värderingshorisont som /api/system: prognostiserad slutomsättning
    om den är högre än live-omsättningen (annars glädje-EV tidigt i veckan)."""
    try:
        from .main import _projected_turnover
        projected = (_projected_turnover(product, current, close_iso=close_iso)
                     or current)
    except Exception:  # noqa: BLE001 — prognosfel får inte stoppa frysningen
        projected = current
    if projected > current:
        return projected, "projected"
    return current, "live"


def _prize_plan(product: str) -> Optional[dict]:
    try:
        from .main import PRIZE_PLANS
        return PRIZE_PLANS.get(product)
    except Exception:  # noqa: BLE001
        return None


def counterfactual_payout(
        correct_dist: dict[int, int],
        tiers: dict[int, tuple[Optional[int], Optional[float]]],
) -> tuple[Optional[float], float, bool, str]:
    """Räkna vad våra vinst-enheter hade fått efter egen utspädning.

    Svenska Spel publicerar vinnare + belopp per vinnare. Därmed kan den
    observerade nivåtpotten skattas som winners × amount. Om våra rader hade
    deltagit delas samma observerade pott på winners + own_winners. När
    officiella vinnare är noll är potten/rollovern inte identifierbar ur
    settlementpayloaden; då blir facitet uttryckligen ofullständigt och ROI
    får inte räknas som noll.
    """
    diluted = 0.0
    published = 0.0
    complete = True
    notes = []
    for correct, own_winners in correct_dist.items():
        if own_winners <= 0 or correct not in tiers:
            continue
        winners, amount = tiers[correct]
        if winners is None or amount is None:
            complete = False
            notes.append(f"{correct} rätt saknar vinnar-/beloppsdata")
            continue
        published += own_winners * amount
        if winners <= 0:
            complete = False
            notes.append(f"{correct} rätt hade 0 officiella vinnare (rullpott okänd)")
            continue
        observed_pool = winners * amount
        diluted += own_winners * observed_pool / (winners + own_winners)
    note = ("egen vinst utspädd mot observerad nivåtpottsproxy"
            if complete else "; ".join(notes))
    return (round(diluted, 2) if complete else None,
            round(published, 2), complete, note)


def settle_pending(store: Storage, now: Optional[dt.datetime] = None) -> dict:
    """Settla frysta system där omgångens facit finns i settlementlagret."""
    now = now or dt.datetime.now(dt.timezone.utc)
    rows = store.conn.execute(
        "SELECT l.product, l.draw_number, l.horizon, l.config_key, "
        "l.events_order, l.rows_text, l.cost_kr, s.draw_state "
        "FROM pool_system_ledger l JOIN pool_draw_settlement s "
        "ON s.product=l.product AND s.draw_number=l.draw_number "
        "WHERE l.settled_at IS NULL").fetchall()
    report = {"settled": 0, "unresolvable": 0, "cancelled": 0}
    for (product, draw_number, horizon, key, events_order, rows_text, cost,
         draw_state) in rows:
        # En INSTÄLLD omgång spelades aldrig: insatsen betalas tillbaka och
        # det finns ingenting att ha rätt på. Den är inte "oläsbar" — den är
        # inte en observation. Skiljs ut så att facitet inte räknar den som
        # ett misslyckat försök att rätta.
        if draw_state == pool_settlement.CANCELLED_STATE:
            store.conn.execute(
                "UPDATE pool_system_ledger SET settled_at=?, settle_note=? "
                "WHERE product=? AND draw_number=? AND horizon=? AND config_key=?",
                (_iso(now), CANCELLED_NOTE,
                 product, draw_number, horizon, key))
            report["cancelled"] += 1
            continue
        outcomes = dict(store.conn.execute(
            "SELECT event_number, outcome FROM pool_event_settlement "
            "WHERE product=? AND draw_number=?", (product, draw_number)))
        tiers = {int(r[0]): (r[1], r[2]) for r in store.conn.execute(
            "SELECT correct, winners, amount FROM pool_payout_tier "
            "WHERE product=? AND draw_number=? AND correct IS NOT NULL",
            (product, draw_number))}
        events = [int(e) for e in events_order.split(",")]
        note = None
        if any(outcomes.get(e) not in ("1", "X", "2") for e in events):
            # utfall saknas för någon match (extremfall) — märk, försök inte
            note = "utfall saknas för minst en match"
            store.conn.execute(
                "UPDATE pool_system_ledger SET settled_at=?, settle_note=? "
                "WHERE product=? AND draw_number=? AND horizon=? AND config_key=?",
                (_iso(now), note, product, draw_number, horizon, key))
            report["unresolvable"] += 1
            continue
        facit = [outcomes[e] for e in events]
        dist: dict[int, int] = {}
        for line in rows_text.split("\n"):
            signs = line.split(",")
            correct = sum(1 for sign, res in zip(signs, facit) if sign == res)
            dist[correct] = dist.get(correct, 0) + 1
        correct_max = max(dist) if dist else 0
        payout, published, payout_complete, payout_note = \
            counterfactual_payout(dist, tiers)
        roi = (round(payout / cost - 1.0, 4)
               if payout_complete and payout is not None and cost else None)
        store.conn.execute(
            "UPDATE pool_system_ledger SET settled_at=?, correct_max=?, "
            "correct_dist=?, payout_kr=?, published_payout_kr=?, "
            "payout_complete=?, settlement_version=?, roi=?, settle_note=? "
            "WHERE product=? AND draw_number=? AND horizon=? AND config_key=?",
            (_iso(now), correct_max,
             json.dumps(dist, sort_keys=True), payout, published,
             int(payout_complete), SETTLEMENT_VERSION, roi, payout_note,
             product, draw_number, horizon, key))
        report["settled"] += 1
    if rows and not store._bulk:  # noqa: SLF001
        store.conn.commit()
    return report


def _bench(key: str, stored: Optional[dict] = None) -> dict:
    """Konfigurationens parametrar — även för pensionerade nycklar.

    Gamla rader måste kunna visas med samma kolumner som nya. Parametrarna
    läses i första hand ur matrisen, annars ur den frysta raden själv
    (`budget`/`strategy`/`value_weight` lagras per frysning) — ALDRIG tolkade
    ur nyckelsträngen. Det var just den tolkningen som gjorde `ev50-tuff-vw80`
    oläsbar.
    """
    for bench in BENCHMARKS:
        if bench["key"] == key:
            return {**bench, "retired": False, "research": False,
                    "promotion_eligible": True, "method": "varderader"}
    for config in PH5_FORWARD_CONFIGS:
        if config["key"] == key:
            return {**config, "primary": False, "retired": False,
                    "research": True, "promotion_eligible": False}
    for config in PH5_RETIRED_CONFIGS:
        if config["key"] == key:
            return {**config, "primary": False, "retired": True,
                    "research": True, "promotion_eligible": False}
    stored = stored or {}
    return {"key": key, "budget": stored.get("budget"),
            "strategy": stored.get("strategy"),
            "value_weight": stored.get("value_weight"),
            "primary": False, "retired": True, "research": False,
            "promotion_eligible": False, "method": "legacy"}


def _paired_draw_roi(store: Storage, products: tuple[str, ...], horizon: str,
                     keys: tuple[str, ...]) -> dict[str, dict[tuple, float]]:
    """ROI per omgång för givna konfigurationer — bara utvärderbara rader.

    Parvis jämförelse kräver SAMMA omgångar: en utmanare som råkar sakna de
    dyra omgångarna ska inte kunna se bättre ut än championen av den orsaken.

    Nyckeln är (produkt, omgång), inte omgångsnumret ensamt. En familj som
    Topptipset har tre oberoende nummerserier — Dagens 4260, Extra 1856 och
    Stryk 975 — och utan produkten i nyckeln skulle två olika omgångar med
    samma nummer para ihop sig som om de vore samma.
    """
    out: dict[str, dict[tuple, float]] = {key: {} for key in keys}
    placeholders = ",".join("?" for _ in keys)
    marks_p = ",".join("?" for _ in products)
    for product, key, draw_number, cost, payout in store.conn.execute(
            f"SELECT product, config_key, draw_number, cost_kr, COALESCE(payout_kr, 0) "
            f"FROM pool_system_ledger WHERE product IN ({marks_p}) AND horizon=? "
            f"AND config_key IN ({placeholders}) AND timely=1 "
            f"AND correct_max IS NOT NULL AND payout_complete=1",
            (*products, horizon, *keys)):
        if cost:
            out[key][(product, int(draw_number))] = payout / cost - 1
    return out


def _signflip_p(diffs: list[float], key: tuple,
                iters: int = BOOTSTRAP_ITERS) -> Optional[float]:
    """Ensidigt p-värde för "utmanaren slår championen".

    Samma konvention som `oddset_ledger._bootstrap`: nollhypotesen centreras
    med teckenflip, inte med svansen i en fördelning som redan ligger runt det
    observerade medelvärdet. Under tre parade omgångar finns inget att testa.
    """
    if len(diffs) < 3:
        return None
    observed = sum(diffs) / len(diffs)
    if observed <= 0:
        return 1.0
    rng = random.Random(
        int(hashlib.sha1("|".join(map(str, key)).encode()).hexdigest()[:8], 16))
    null_means = []
    for _ in range(iters):
        flipped = [value * rng.choice((-1, 1)) for value in diffs]
        null_means.append(sum(flipped) / len(flipped))
    return round((1 + sum(m >= observed for m in null_means)) / (iters + 1), 4)


def _bh_pass(tests: list[dict]) -> set[tuple]:
    """Benjamini–Hochberg över HELA utmanarfamiljen.

    12 konfigurationer × 5 produkter ger 60 jämförelser; utan FDR ser ~3 av
    dem signifikanta ut av ren slump. Familjen är alla testbara utmanare, inte
    en produkt i taget — det är över hela matrisen selektionen sker.
    """
    ranked = sorted(((t["p_value"], t["key"]) for t in tests
                     if t["p_value"] is not None), key=lambda item: item[0])
    accepted = 0
    for rank, (p_value, _) in enumerate(ranked, 1):
        if p_value <= rank / len(ranked) * FDR_Q:
            accepted = rank
    return {key for _, key in ranked[:accepted]}


def champion_report(store: Storage) -> dict:
    """Per produkt × horisont: championen mot sin bästa utmanare.

    Svarar på de två frågor systemfacitet finns för — "vad ska jag spela?" och
    "ska jag ändra inställningar?" — i en rad. Jämförelsen är PARAD över samma
    omgångar och FDR-korrigerad över hela utmanarfamiljen.
    """
    rows, tests = [], []
    # SPELFAMILJ, inte produktslug. Topptipset Dagens/Stryk/Extra kör samma
    # benchmarkfamilj på samma spelform, så deras omgångar hör till samma
    # jämförelse. Att mäta dem var för sig delade underlaget i tre och gjorde
    # varje del för tunn för grinden. Pareringen sker på (produkt, omgång), så
    # de tre nummerserierna kan inte blandas ihop.
    families: dict[str, list[str]] = {}
    for (product,) in store.conn.execute(
            "SELECT DISTINCT product FROM pool_system_ledger ORDER BY product"):
        families.setdefault(family_of(product), []).append(product)
    for family, members in sorted(families.items()):
        # Utmanarfamiljen är SPELETS egen — och det krymper även FDR-familjen,
        # vilket är hela poängen: en budget vi aldrig skulle spela ska inte
        # stjäla en jämförelse. Snittet skyddar mot en framtida grupp där
        # medlemmarna inte delar benchmarkfamilj.
        gemensamma = set.intersection(*[
            {b["key"] for b in benchmarks_for(m) if not b["primary"]}
            for m in members])
        challengers = tuple(b["key"] for b in benchmarks_for(members[0])
                            if not b["primary"] and b["key"] in gemensamma)
        all_keys = (CHAMPION_KEY, *challengers)
        for horizon in FREEZE_HORIZONS:
            roi = _paired_draw_roi(store, tuple(members), horizon, all_keys)
            champion = roi[CHAMPION_KEY]
            if not champion:
                continue
            entry = {
                "product": family, "horizon": horizon,
                "horizon_minutes": FREEZE_HORIZONS[horizon][0],
                "champion_key": CHAMPION_KEY,
                "champion_n": len(champion),
                "champion_roi": round(sum(champion.values()) / len(champion), 4),
                "challengers": [],
            }
            for key in challengers:
                shared = sorted(set(champion) & set(roi[key]))
                if not shared:
                    continue
                diffs = [roi[key][d] - champion[d] for d in shared]
                test_key = (family, horizon, key)
                p_value = _signflip_p(diffs, test_key)
                entry["challengers"].append({
                    "config_key": key, "n_paired": len(shared),
                    "roi": round(sum(roi[key][d] for d in shared) / len(shared), 4),
                    "delta_roi": round(sum(diffs) / len(diffs), 4),
                    "p_value": p_value, "key": test_key,
                })
                tests.append({"p_value": p_value, "key": test_key})
            rows.append(entry)
    passed = _bh_pass(tests)
    for entry in rows:
        for challenger in entry["challengers"]:
            challenger["fdr_pass"] = challenger.pop("key") in passed
        entry["challengers"].sort(key=lambda c: -c["delta_roi"])
        best = entry["challengers"][0] if entry["challengers"] else None
        entry["best_challenger"] = best
        # Promotion kräver BÅDE FDR och det förregistrerade underlaget. Ett
        # positivt delta på tre omgångar är brus, inte ett skäl att byta.
        entry["promotable"] = bool(
            best and best["fdr_pass"] and best["delta_roi"] > 0
            and best["n_paired"] >= GATE_MIN_DRAWS)
    return {"champion_key": CHAMPION_KEY, "gate_min_draws": GATE_MIN_DRAWS,
            "fdr_q": FDR_Q, "rows": rows}


def _streck_at(store: Storage, product: str, draw_number: int,
               at: Optional[str]) -> dict[int, dict[str, dict]]:
    """Folkets procent och odds som de såg ut vid `at`.

    `snapshots` är en FÖRÄNDRINGSSERIE — den skriver bara när något ändras.
    Värdet vid en tidpunkt är alltså sista raden med `fetched_at <= at`, inte
    en rad som råkar ha den tidsstämpeln. Utan `at` returneras sista kända.
    """
    query = ("SELECT event_number, sign, streck, odds, fetched_at "
             "FROM snapshots WHERE product=? AND draw_number=?")
    args: list = [product, draw_number]
    if at:
        query += " AND fetched_at<=?"
        args.append(at)
    query += " ORDER BY fetched_at"
    out: dict[int, dict[str, dict]] = {}
    for event_number, sign, streck, odds, fetched_at in store.conn.execute(
            query, args):
        out.setdefault(int(event_number), {})[sign] = {
            "streck": streck, "odds": odds, "observed_at": fetched_at}
    return out


def _sharp_at(store: Storage, product: str, draw_number: int,
              at: Optional[str]) -> dict[int, dict[str, dict]]:
    """Sharp-oddset som senast observerats vid eller före en frysning."""
    query = ("SELECT event_number, sign, odds, fetched_at "
             "FROM sharp_snapshots WHERE product=? AND draw_number=?")
    args: list = [product, draw_number]
    if at:
        query += " AND fetched_at<=?"
        args.append(at)
    query += " ORDER BY fetched_at"
    out: dict[int, dict[str, dict]] = {}
    for event_number, sign, odds, fetched_at in store.conn.execute(query, args):
        out.setdefault(int(event_number), {})[sign] = {
            "odds": odds, "observed_at": fetched_at}
    return out


def system_detail(store: Storage, product: str, draw_number: int,
                  horizon: str, config_key: str) -> dict:
    """Ett fryst system mot facit, match för match.

    Syftet är mänsklig granskning: VAR missade förslaget, och hur såg folkets
    streck ut just då? Därför visas både strecket vid frysningen och vid
    spelstopp — rörelsen däremellan är ofta hela förklaringen.

    Ingen ny insamling behövs: raderna ligger i ledgern, utfallet i
    settlementlagret och strecken i `snapshots`.
    """
    row = store.conn.execute(
        "SELECT frozen_at, timely, lag_min, budget, strategy, value_weight, "
        "n_rows, cost_kr, events_order, rows_text, correct_max, correct_dist, "
        "payout_kr, payout_complete, roi, settle_note, turnover_used, "
        "turnover_basis FROM pool_system_ledger WHERE product=? AND "
        "draw_number=? AND horizon=? AND config_key=?",
        (product, draw_number, horizon, config_key)).fetchone()
    if row is None:
        return {"available": False}
    (frozen_at, timely, lag_min, budget, strategy, value_weight, n_rows,
     cost_kr, events_order, rows_text, correct_max, correct_dist, payout_kr,
     payout_complete, roi, settle_note, turnover_used, turnover_basis) = row

    order = [int(n) for n in (events_order or "").split(",") if n]
    rows = [line.split(",") for line in (rows_text or "").splitlines() if line]
    facit = {int(r[0]): {"description": r[1], "home": r[2], "away": r[3],
                         "outcome": r[4], "cancelled": bool(r[5]),
                         "streck_close": {"1": r[6], "X": r[7], "2": r[8]}}
             for r in store.conn.execute(
                 "SELECT event_number, description, home, away, outcome, "
                 "cancelled, streck_one, streck_x, streck_two "
                 "FROM pool_event_settlement WHERE product=? AND draw_number=?",
                 (product, draw_number))}
    at_freeze = _streck_at(store, product, draw_number, frozen_at)
    sharp_at_freeze = _sharp_at(store, product, draw_number, frozen_at)

    events = []
    ordered_outcomes = []
    for index, event_number in enumerate(order):
        sign_counts = {
            sign: sum(index < len(system_row) and system_row[index] == sign
                      for system_row in rows)
            for sign in ("1", "X", "2")
        }
        covered = [sign for sign in ("1", "X", "2") if sign_counts[sign]]
        info = facit.get(event_number, {})
        outcome = info.get("outcome")
        ordered_outcomes.append(outcome)
        frozen_signs = at_freeze.get(event_number, {})
        frozen_sharp = sharp_at_freeze.get(event_number, {})
        observed = [
            value.get("observed_at") for value in
            (*frozen_signs.values(), *frozen_sharp.values())
            if value.get("observed_at")
        ]
        events.append({
            "event_number": event_number,
            "description": info.get("description"),
            "home": info.get("home"), "away": info.get("away"),
            "outcome": outcome, "cancelled": info.get("cancelled"),
            "covered": covered,
            # `covered` säger bara om tecknet finns på MINST en rad. I ett
            # 5 000-raderssystem är det nästan alltid sant och döljer därför
            # modellens verkliga viktning. Antal/andel gör bl.a. X-bortfall
            # synligt utan att någon urvalsregel ändras i efterhand.
            "sign_counts": sign_counts,
            "sign_shares": {
                sign: (sign_counts[sign] / len(rows) if rows else None)
                for sign in ("1", "X", "2")
            },
            # Den enda frågan som spelar roll för facitet: täckte vi tecknet
            # som gick in? En enda missad match kapar hela systemets tak.
            "hit": None if not outcome else outcome in covered,
            "streck_at_freeze": {s: frozen_signs.get(s, {}).get("streck")
                                 for s in ("1", "X", "2")},
            "odds_at_freeze": {s: frozen_signs.get(s, {}).get("odds")
                               for s in ("1", "X", "2")},
            "sharp_odds_at_freeze": {
                s: frozen_sharp.get(s, {}).get("odds")
                for s in ("1", "X", "2")
            },
            "market_observed_at": max(observed) if observed else None,
            "streck_at_close": info.get("streck_close"),
            "x_omitted": sign_counts["X"] == 0,
            "x_thin": bool(rows) and 0 < sign_counts["X"] / len(rows) < 0.10,
            "x_was_outcome_but_omitted": (
                outcome == "X" and sign_counts["X"] == 0),
        })
    missed = [e for e in events if e["hit"] is False]
    facit_complete = bool(order) and all(
        outcome in ("1", "X", "2") for outcome in ordered_outcomes)
    stored_dist = json.loads(correct_dist) if correct_dist else None
    row_results = []
    calculated_dist: dict[int, int] = {}
    tiers = {int(r[0]): (r[1], r[2]) for r in store.conn.execute(
        "SELECT correct, winners, amount FROM pool_payout_tier "
        "WHERE product=? AND draw_number=? AND correct IS NOT NULL",
        (product, draw_number))}
    for index, signs in enumerate(rows, 1):
        correct = None
        if facit_complete:
            correct = sum(sign == outcome for sign, outcome in zip(
                signs, ordered_outcomes))
            calculated_dist[correct] = calculated_dist.get(correct, 0) + 1
        row_results.append({
            "index": index,
            "signs": "".join(signs),
            "correct": correct,
            "payout_kr": None if not facit_complete else 0.0,
        })
    if facit_complete:
        # Payouten är kontrafaktisk: lägg till systemets egna vinnande rader i
        # nämnaren på samma sätt som `counterfactual_payout`. Då summerar
        # radbeloppen till detaljens systemutdelning (avrundningsöre undantaget).
        for result in row_results:
            winners, amount = tiers.get(result["correct"], (None, None))
            own_winners = calculated_dist.get(result["correct"], 0)
            if winners is not None and winners > 0 and amount is not None \
                    and own_winners > 0:
                result["payout_kr"] = round(
                    winners * amount / (winners + own_winners), 2)
            else:
                result["payout_kr"] = 0.0
        row_results.sort(key=lambda result: (-result["correct"], result["index"]))
    bench = _bench(config_key, {"budget": budget, "strategy": strategy,
                                "value_weight": value_weight})
    return {
        "available": True, "product": product, "draw_number": draw_number,
        "horizon": horizon, "horizon_minutes": FREEZE_HORIZONS.get(
            horizon, (None, None))[0],
        "config_key": config_key, "budget": budget, "strategy": strategy,
        "value_weight": value_weight, "retired": bench["retired"],
        "research": bench["research"],
        "promotion_eligible": bench["promotion_eligible"],
        "method": bench["method"],
        "frozen_at": frozen_at, "timely": bool(timely), "lag_min": lag_min,
        "n_rows": n_rows, "cost_kr": cost_kr,
        "correct_max": correct_max,
        "correct_dist": stored_dist,
        "payout_kr": payout_kr,
        "payout_complete": (bool(payout_complete)
                            if payout_complete is not None else None),
        "roi": roi, "settle_note": settle_note,
        "turnover_used": turnover_used, "turnover_basis": turnover_basis,
        "events": events,
        "n_missed": len(missed),
        "missed_events": [e["event_number"] for e in missed],
        "x_summary": {
            "events": len(events),
            "omitted": sum(e["x_omitted"] for e in events),
            "thin": sum(e["x_thin"] for e in events),
            "x_outcomes": sum(e["outcome"] == "X" for e in events),
            "x_outcomes_omitted": sum(
                e["x_was_outcome_but_omitted"] for e in events),
            "row_share": (
                sum(e["sign_counts"]["X"] for e in events)
                / (len(events) * len(rows))
                if events and rows else None),
        },
        # Exakta rader hämtas bara när användaren öppnar EN frysning. Lägg
        # aldrig detta i `/api/pool/systems`: 5 000 × 13 tecken per arm gör
        # annars hela Historik tung på mobil.
        "facit_complete": facit_complete,
        "facit": "".join(ordered_outcomes) if facit_complete else None,
        "rows": row_results,
        "calculated_dist": calculated_dist if facit_complete else None,
        "audit_matches_stored": (
            {int(key): int(value) for key, value in (stored_dist or {}).items()}
            == calculated_dist if facit_complete and stored_dist is not None
            else None),
    }


def ph5_overview(store: Storage) -> dict:
    """Alla PH5-frysningar för den separata 5 000-testvyn.

    Ingen `rows_text` följer med här. Den exakta 5 000-raderskupongen hämtas
    först när användaren öppnar en testfrysning via `system_detail`.
    """
    configs = (*PH5_FORWARD_CONFIGS, *PH5_RETIRED_CONFIGS)
    keys = tuple(config["key"] for config in configs)
    marks = ",".join("?" for _ in keys)
    tests = []
    for row in store.conn.execute(
            "SELECT l.product, l.draw_number, l.horizon, l.config_key, "
            "l.frozen_at, l.timely, l.lag_min, l.n_rows, l.cost_kr, "
            "l.strategy, l.value_weight, l.settled_at, l.correct_max, "
            "l.correct_dist, l.payout_kr, l.payout_complete, l.roi, "
            "l.settle_note, COALESCE(s.reg_close_time,d.reg_close_time) "
            ", l.events_order, l.rows_text "
            "FROM pool_system_ledger l "
            "LEFT JOIN pool_draw_settlement s ON s.product=l.product "
            "AND s.draw_number=l.draw_number "
            "LEFT JOIN draws d ON d.product=l.product "
            "AND d.draw_number=l.draw_number "
            f"WHERE l.config_key IN ({marks}) "
            "ORDER BY COALESCE(s.reg_close_time,d.reg_close_time,l.frozen_at) "
            "DESC, l.product, l.draw_number DESC, l.horizon, l.config_key",
            keys):
        bench = _bench(row[3], {
            "budget": row[8], "strategy": row[9],
            "value_weight": row[10],
        })
        event_order = [int(value) for value in (row[19] or "").split(",")
                       if value]
        system_rows = [value.split(",") for value in
                       (row[20] or "").splitlines() if value]
        outcomes = {int(event_number): outcome for event_number, outcome in
                    store.conn.execute(
                        "SELECT event_number,outcome FROM pool_event_settlement "
                        "WHERE product=? AND draw_number=?",
                        (row[0], row[1]))}
        x_counts = [sum(index < len(system_row)
                        and system_row[index] == "X"
                        for system_row in system_rows)
                    for index in range(len(event_order))]
        x_omitted = sum(count == 0 for count in x_counts)
        x_outcomes = sum(outcomes.get(event_number) == "X"
                         for event_number in event_order)
        x_outcomes_omitted = sum(
            outcomes.get(event_number) == "X" and x_counts[index] == 0
            for index, event_number in enumerate(event_order))
        tests.append({
            "product": row[0], "draw_number": int(row[1]),
            "horizon": row[2],
            "horizon_minutes": FREEZE_HORIZONS.get(row[2], (None, None))[0],
            "config_key": row[3], "frozen_at": row[4],
            "timely": bool(row[5]), "lag_min": row[6],
            "n_rows": row[7], "cost_kr": row[8],
            "strategy": bench["strategy"],
            "value_weight": bench["value_weight"],
            "method": bench["method"], "retired": bench["retired"],
            "settled_at": row[11], "correct_max": row[12],
            "correct_dist": json.loads(row[13]) if row[13] else None,
            "payout_kr": row[14],
            "payout_complete": (
                bool(row[15]) if row[15] is not None else None),
            "roi": row[16], "settle_note": row[17], "close": row[18],
            "x_share": (
                sum(x_counts) / (len(event_order) * len(system_rows))
                if event_order and system_rows else None),
            "x_omitted_events": x_omitted,
            "x_outcomes": x_outcomes,
            "x_outcomes_omitted": x_outcomes_omitted,
        })

    active = [test for test in tests if not test["retired"]]
    model_tests = [test for test in active if test["method"] == "varderader"]
    evaluable = [test for test in active if test["timely"]
                 and test["correct_max"] is not None
                 and test["payout_complete"] is True]
    return {
        "available": bool(tests),
        "tests": tests,
        "summary": {
            "draws": len({(t["product"], t["draw_number"])
                          for t in active}),
            "freezes": len(active),
            "evaluated": len(evaluable),
            "methods": len(PH5_FORWARD_CONFIGS),
            "rows_per_test": 5000,
            "simulated_cost_kr": sum(t["cost_kr"] or 0 for t in evaluable),
            "simulated_payout_kr": sum(t["payout_kr"] or 0 for t in evaluable),
            "x_omitted_events": sum(t["x_omitted_events"] for t in active),
            "x_outcomes": sum(t["x_outcomes"] for t in active),
            "x_outcomes_omitted": sum(
                t["x_outcomes_omitted"] for t in active),
            "model_x_omitted_events": sum(
                t["x_omitted_events"] for t in model_tests),
            "model_x_outcomes": sum(t["x_outcomes"] for t in model_tests),
            "model_x_outcomes_omitted": sum(
                t["x_outcomes_omitted"] for t in model_tests),
        },
        "configs": [dict(config) for config in configs],
        "products": list(PH5_FORWARD_PRODUCTS),
        "horizons": {
            key: {"minutes": value[0], "tolerance_min": value[1]}
            for key, value in FREEZE_HORIZONS.items()
        },
    }


def summary(store: Storage) -> dict:
    """Champion-baseline per produkt × config × horisont.

    ROI-gaten använder enbart timely=1, lösbara rader med komplett
    kontrafaktisk utdelning. Sena/ofullständiga rader redovisas diagnostiskt.
    """
    out = []
    latest_by_group = {}
    for product, key, horizon, draw_number, frozen_at in store.conn.execute(
            "SELECT product, config_key, horizon, draw_number, frozen_at "
            "FROM pool_system_ledger ORDER BY frozen_at DESC"):
        latest_by_group.setdefault(
            (product, key, horizon),
            {"latest_product": product,
             "latest_draw_number": int(draw_number),
             "latest_frozen": frozen_at})
    for row in store.conn.execute(
            "SELECT product, config_key, horizon, COUNT(*) n, "
            "SUM(CASE WHEN settled_at IS NOT NULL AND correct_max IS NOT NULL "
            "THEN 1 ELSE 0 END) n_settled, "
            "SUM(CASE WHEN timely=1 THEN 1 ELSE 0 END) n_timely, "
            "SUM(CASE WHEN timely=1 AND correct_max IS NOT NULL "
            "AND payout_complete=1 THEN 1 ELSE 0 END) n_evaluable, "
            "SUM(CASE WHEN settled_at IS NOT NULL AND correct_max IS NULL "
            "AND COALESCE(settle_note,'')<>? THEN 1 ELSE 0 END) n_unresolvable, "
            "SUM(CASE WHEN settle_note=? THEN 1 ELSE 0 END) n_cancelled, "
            "SUM(CASE WHEN correct_max IS NOT NULL AND payout_complete=0 "
            "THEN 1 ELSE 0 END) n_payout_incomplete, "
            "SUM(CASE WHEN timely=1 AND correct_max IS NOT NULL "
            "AND payout_complete=1 THEN cost_kr ELSE 0 END) cost, "
            "SUM(CASE WHEN timely=1 AND correct_max IS NOT NULL "
            "AND payout_complete=1 THEN COALESCE(payout_kr,0) ELSE 0 END) payout, "
            "MAX(CASE WHEN timely=1 THEN correct_max END) best, "
            "MAX(budget) budget, MAX(strategy) strategy, "
            "MAX(value_weight) value_weight, MAX(frozen_at) latest_frozen "
            "FROM pool_system_ledger GROUP BY product, config_key, horizon "
            "ORDER BY product, config_key, horizon",
            (CANCELLED_NOTE, CANCELLED_NOTE)):
        (product, key, horizon, n, n_settled, n_timely, n_evaluable,
         n_unresolvable, n_cancelled, n_payout_incomplete, cost, payout, best,
         budget, strategy, value_weight, latest_frozen) = row
        if not any(b["key"] == key for b in benchmarks_for(product)) \
                and key not in RETIRED_KEYS \
                and not any(c["key"] == key
                            for c in research_configs_for(product)) \
                and not any(c["key"] == key for c in PH5_RETIRED_CONFIGS):
            # Utanför produktens familj (t.ex. b1024 på ett 8-matchsspel):
            # varvet fryser den inte längre, så den ska inte heller stå kvar
            # i tabellen och se ut som en levande utmanare. Pensionerade
            # nycklar är ett eget, redan hanterat fall.
            continue
        bench = _bench(key, {"budget": budget, "strategy": strategy,
                             "value_weight": value_weight})
        latest = latest_by_group.get((product, key, horizon), {})
        out.append({
            "product": product, "config_key": key, "horizon": horizon,
            "horizon_minutes": FREEZE_HORIZONS.get(horizon, (None, None))[0],
            # Parametrarna var förr inbakade i nyckelsträngen (`ev50-tuff-vw80`),
            # vilket läste som procent och veckonummer. De är egna fält nu.
            "budget": bench["budget"], "strategy": bench["strategy"],
            "value_weight": bench["value_weight"], "retired": bench["retired"],
            "research": bench["research"],
            "promotion_eligible": bench["promotion_eligible"],
            "method": bench["method"],
            "latest_frozen": latest_frozen,
            # Gör gruppsummeringen öppningsbar utan att skicka dess tunga
            # rows_text. Själva raderna hämtas först via detail-endpointen.
            "latest_product": latest.get("latest_product", product),
            "latest_draw_number": latest.get("latest_draw_number"),
            "n_frozen": n,
            "n_settled": n_settled, "n_timely": n_timely,
            "n_evaluable": n_evaluable, "n_unresolvable": n_unresolvable,
            "n_cancelled": n_cancelled,
            "n_payout_incomplete": n_payout_incomplete,
            # cost_kr är ACKUMULERAT över utvärderbara omgångar. Insatsen per
            # omgång är budgeten — att visa summan under rubriken "Insats" fick
            # Topptipsets 50 kr × 22 omgångar att se ut som ett 1 100-kronorsspel.
            "cost_kr": round(cost or 0, 2), "payout_kr": round(payout or 0, 2),
            "cost_per_draw_kr": (round(cost / n_evaluable, 2)
                                 if n_evaluable and cost else bench["budget"]),
            "roi": (round((payout or 0) / cost - 1, 4)
                    if n_evaluable and cost else None),
            "best_correct": best,
            "primary": bench["primary"],
        })
    recent = []
    for r in store.conn.execute(
            "SELECT l.product, l.draw_number, l.horizon, l.config_key, "
            "l.frozen_at, l.timely, l.n_rows, l.cost_kr, l.correct_max, "
            "l.payout_kr, l.published_payout_kr, l.payout_complete, "
            "l.settlement_version, l.roi, l.settle_note, "
            "COALESCE(s.reg_close_time, d.reg_close_time), "
            "l.budget, l.strategy, l.value_weight "
            "FROM pool_system_ledger l LEFT JOIN pool_draw_settlement s "
            "ON s.product=l.product AND s.draw_number=l.draw_number "
            "LEFT JOIN draws d "
            "ON d.product=l.product AND d.draw_number=l.draw_number "
            "ORDER BY l.frozen_at DESC LIMIT 200"):
        bench = _bench(r[3], {"budget": r[16], "strategy": r[17],
                              "value_weight": r[18]})
        recent.append({
            "product": r[0], "draw_number": r[1], "horizon": r[2],
            "horizon_minutes": FREEZE_HORIZONS.get(r[2], (None, None))[0],
            "config_key": r[3], "frozen_at": r[4], "timely": bool(r[5]),
            "n_rows": r[6], "cost_kr": r[7], "correct_max": r[8],
            "payout_kr": r[9], "published_payout_kr": r[10],
            "payout_complete": bool(r[11]) if r[11] is not None else None,
            "settlement_version": r[12], "roi": r[13], "settle_note": r[14],
            # Vilken omgång raden gäller går inte att läsa ur nyckeln — datumet
            # kommer ur omgångens spelstopp, inte ur frysningstiden. En öppen
            # omgång saknar ännu settlementrad och faller därför tillbaka på
            # draws — datumet ska synas redan när förslaget fryses.
            "close": r[15],
            "budget": bench["budget"], "strategy": bench["strategy"],
            "value_weight": bench["value_weight"], "retired": bench["retired"],
            "research": bench["research"],
            "promotion_eligible": bench["promotion_eligible"],
            "method": bench["method"],
        })
    return {"benchmarks": [dict(b) for b in BENCHMARKS],
            "research_configs": [dict(c) for c in PH5_FORWARD_CONFIGS],
            "champion_key": CHAMPION_KEY,
            "retired_keys": list(RETIRED_KEYS),
            "horizons": {k: {"minutes": v[0], "tolerance_min": v[1]}
                         for k, v in FREEZE_HORIZONS.items()},
            "groups": out, "recent": recent,
            "champion_report": champion_report(store)}
