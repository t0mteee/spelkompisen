"""Analys av en omgång: implicerad sannolikhet, värde, oddsrörelse, spikar.

Grundidéer
----------
* **Fair probability**: 1/odds normaliserat över de tre utfallen tar bort
  spelbolagets påslag (overround) och ger en marknadssannolikhet.
* **Värde (värdestreck)**: marknaden tror mer på utfallet än vad folket
  streckar.  value = fair_prob*100 - streck.  Stort positivt = värdestreck.
* **Oddsrörelse**: aktuellt odds jämfört med startodds.  Faller oddset
  (negativ drift) flödar pengar in -> stärkt utfall.  Din kärnsignal.
* **Spik (banker)**: hög fair_prob på ett utfall (klar favorit), gärna med
  fallande odds och brett folkstöd.

Allt uttrycks som dataklasser så att det enkelt serialiseras till JSON
för API:t/frontend.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

from .svenskaspel import Draw, Match, Outcome

SIGNS = ("1", "X", "2")


@dataclass
class OutcomeAnalysis:
    sign: str
    odds: Optional[float]
    start_odds: Optional[float]
    streck: Optional[int]
    streck_ref: Optional[int]
    fair_prob: Optional[float]        # 0..1, overround-justerad
    implied_prob: Optional[float]     # 1/odds (ojusterad)
    value: Optional[float]            # fair_prob*100 - streck  (procentenheter)
    odds_drift: Optional[float]       # odds - start_odds (negativ = fallande)
    odds_drift_pct: Optional[float]   # (start-odds)/start  >0 = oddset gått ner
    streck_drift: Optional[int]       # streck - streck_ref
    sharp_odds: Optional[float]       # sharp (Pinnacle m.fl.) odds, om hämtat
    sharp_prob: Optional[float]       # overround-justerad sannolikhet från sharp
    value_sharp: Optional[float]      # sharp_prob*100 - streck (sharps värde vs folket)
    edge_vs_ss: Optional[float]       # sharp_prob - ss_fair_prob (SS felprissättning)
    move_pct: Optional[float]         # (första-senaste)/första över egna snapshots; >0 = oddset ned
    move_from: Optional[float]        # odds vid första snapshot
    move_to: Optional[float]          # odds vid senaste snapshot
    move_points: Optional[int]        # antal snapshots
    tags: list[str]


@dataclass
class MatchAnalysis:
    event_number: int
    description: str
    league: str
    match_start: Optional[str]
    cancelled: bool
    outcomes: dict[str, OutcomeAnalysis]
    favourite: Optional[str]          # sign med högst fair_prob
    favourite_prob: Optional[float]
    spik_score: float                 # 0..100, hur bra spik matchen är
    open_score: float                 # 0..100, hur "öppen"/svår matchen är
    recommendation: str               # kort text
    speltyp: str                      # "spik"|"halvspik"|"lutar"|"gardera"|"avvakta"
    best_value_sign: Optional[str]
    prob_source: str                  # "odds" | "sharp" | "streck" | "none"
    has_sharp: bool = False
    sharp_bookmaker: Optional[str] = None
    sharp_confidence: Optional[float] = None


# --- trösklar (lätt att tweaka) ---
SPIK_PROB = 0.62          # fair_prob över detta = spik-kandidat
VALUE_MIN = 6.0           # procentenheter över streck för "värdestreck"-tag
DROP_MIN_PCT = 0.04       # oddsfall >= 4% = signifikant rörelse
HEAVY_FAVOURITE = 0.70    # mycket stark favorit
EDGE_MIN = 0.06           # sharp vs SS-sannolikhet: materiell felprissättning
MOVE_MIN = 0.05           # rörelse över egna snapshots >= 5% = signifikant

# spik-/öppen-score: kalibrering mot favoritens (overround-justerade) sannolikhet
SPIK_LO, SPIK_HI = 0.40, 0.78     # fair_prob -> spik-score 0..100
OPEN_HI, OPEN_LO = 0.55, 0.34     # fair_prob -> öppen-score (lågt = klar favorit)
# speltyps-etiketter (fair_prob för favoriten)
SPIK_PROB_LABEL = 0.52    # >= => "spik"  (≈ odds 1.65–1.75)
HALF_PROB_LABEL = 0.45    # >= => "halvspik"
OPEN_PROB_LABEL = 0.40    # <  => "gardera" (ingen klar favorit)


def _normalize_odds(odds: dict) -> dict[str, Optional[float]]:
    """1X2-odds -> overround-justerade sannolikheter (nyckel '1'/'X'/'2')."""
    inv = {}
    for s in SIGNS:
        o = odds.get(s)
        inv[s] = (1.0 / o) if o and o > 0 else None
    total = sum(v for v in inv.values() if v is not None)
    if not total or any(inv[s] is None for s in SIGNS):
        return {s: None for s in SIGNS}
    return {s: inv[s] / total for s in SIGNS}


def _fair_probs(outcomes: dict[str, Outcome]) -> tuple[dict[str, Optional[float]], str]:
    """Marknadssannolikhet per utfall + källa ('odds' | 'streck' | 'none').

    Primärt 1/odds normaliserat. Saknas odds (tidigt i veckan) faller vi tillbaka
    på folkets streck som grov proxy — sämre, men bättre än att gissa blint."""
    inv = {}
    for s in SIGNS:
        o = outcomes[s].odds
        inv[s] = (1.0 / o) if o and o > 0 else None
    total = sum(v for v in inv.values() if v is not None)
    if total and all(inv[s] is not None for s in SIGNS):
        return {s: inv[s] / total for s in SIGNS}, "odds"

    # fallback: streck
    streck = {s: outcomes[s].streck for s in SIGNS}
    stot = sum(v for v in streck.values() if v is not None)
    if stot:
        return {s: (streck[s] / stot if streck[s] is not None else None) for s in SIGNS}, "streck"
    return {s: None for s in SIGNS}, "none"


def analyze_outcome(o: Outcome, fair: Optional[float],
                    sharp_prob: Optional[float] = None,
                    sharp_odds: Optional[float] = None,
                    ss_fair: Optional[float] = None,
                    move: Optional[dict] = None) -> OutcomeAnalysis:
    implied = (1.0 / o.odds) if o.odds and o.odds > 0 else None
    value = (fair * 100 - o.streck) if (fair is not None and o.streck is not None) else None

    value_sharp = (sharp_prob * 100 - o.streck) if (sharp_prob is not None and o.streck is not None) else None
    edge_vs_ss = (sharp_prob - ss_fair) if (sharp_prob is not None and ss_fair is not None) else None

    # rörelse över egna snapshots: >0 = oddset har gått ned (stärkts)
    move_pct = move_from = move_to = None
    move_points = None
    if move and move.get("n", 0) >= 2 and move.get("first"):
        move_from, move_to, move_points = move["first"], move["last"], move["n"]
        move_pct = round((move_from - move_to) / move_from, 4)

    drift = drift_pct = None
    if o.odds is not None and o.start_odds is not None and o.start_odds > 0:
        drift = round(o.odds - o.start_odds, 3)
        drift_pct = round((o.start_odds - o.odds) / o.start_odds, 4)  # >0 = oddset ner

    streck_drift = (o.streck - o.streck_ref) if (o.streck is not None and o.streck_ref is not None) else None

    tags: list[str] = []
    if fair is not None and fair >= SPIK_PROB:
        tags.append("favorit")
    if value is not None and value >= VALUE_MIN:
        tags.append("värdestreck")
    if drift_pct is not None and drift_pct >= DROP_MIN_PCT:
        tags.append("fallande_odds")
    if drift_pct is not None and drift_pct <= -DROP_MIN_PCT:
        tags.append("stigande_odds")
    if streck_drift is not None and streck_drift <= -3:
        tags.append("folk_minskar")
    if value_sharp is not None and value_sharp >= VALUE_MIN:
        tags.append("sharp_värde")
    if edge_vs_ss is not None and edge_vs_ss >= EDGE_MIN:
        tags.append("ss_undervärderad")   # sharp tror mer än SS -> SS-odds för höga
    if edge_vs_ss is not None and edge_vs_ss <= -EDGE_MIN:
        tags.append("ss_övervärderad")
    if move_pct is not None and move_pct >= MOVE_MIN:
        tags.append("rörelse_ner")    # stärkts sedan vi började logga
    if move_pct is not None and move_pct <= -MOVE_MIN:
        tags.append("rörelse_upp")

    return OutcomeAnalysis(
        sign=o.sign,
        odds=o.odds,
        start_odds=o.start_odds,
        streck=o.streck,
        streck_ref=o.streck_ref,
        fair_prob=round(fair, 4) if fair is not None else None,
        implied_prob=round(implied, 4) if implied is not None else None,
        value=round(value, 1) if value is not None else None,
        odds_drift=drift,
        odds_drift_pct=drift_pct,
        streck_drift=streck_drift,
        sharp_odds=sharp_odds,
        sharp_prob=round(sharp_prob, 4) if sharp_prob is not None else None,
        value_sharp=round(value_sharp, 1) if value_sharp is not None else None,
        edge_vs_ss=round(edge_vs_ss, 4) if edge_vs_ss is not None else None,
        move_pct=move_pct,
        move_from=move_from,
        move_to=move_to,
        move_points=move_points,
        tags=tags,
    )


def analyze_match(m: Match, sharp: Optional[dict] = None,
                  move: Optional[dict] = None) -> MatchAnalysis:
    fair, source = _fair_probs(m.outcomes)
    sharp_probs = _normalize_odds(sharp["odds"]) if (sharp and sharp.get("odds")) else {s: None for s in SIGNS}
    sharp_o = (sharp.get("odds") if sharp else None) or {}
    has_sharp = any(sharp_probs[s] is not None for s in SIGNS)
    move = move or {}
    # värde är bara meningsfullt när vi har riktiga odds att jämföra streck mot
    oa = {s: analyze_outcome(
              m.outcomes[s],
              fair[s] if source == "odds" else None,
              sharp_prob=sharp_probs[s],
              sharp_odds=sharp_o.get(s),
              ss_fair=fair[s] if source == "odds" else None,
              move=move.get(s))
          for s in SIGNS}
    # sannolikhetsbas för favorit/öppenhet/spik: SS-odds > sharp > streck
    if source == "odds":
        basis_src, basis = "odds", fair
    elif has_sharp:
        basis_src, basis = "sharp", sharp_probs   # sharp fyller odds-lösa matcher
    else:
        basis_src, basis = source, fair           # "streck" eller "none"
    if basis_src != "odds":
        for s in SIGNS:
            oa[s].fair_prob = round(basis[s], 4) if basis[s] is not None else None

    probs = {s: oa[s].fair_prob for s in SIGNS if oa[s].fair_prob is not None}
    fav_sign = max(probs, key=probs.get) if probs else None
    fav_prob = probs[fav_sign] if fav_sign else None

    # spik-score: favoritens styrka. Kalibrerat så en typisk favorit på odds
    # ~1.65 (≈55% efter marginal) blir spik, inte gardering.
    spik = 0.0
    fav_value = None
    if fav_prob is not None:
        spik = max(0.0, min(1.0, (fav_prob - SPIK_LO) / (SPIK_HI - SPIK_LO))) * 100
        fav = oa[fav_sign]
        fav_value = fav.value_sharp if fav.value_sharp is not None else fav.value
        if fav.odds_drift_pct and fav.odds_drift_pct >= DROP_MIN_PCT:
            spik = min(100.0, spik + 8)        # marknaden stärker favoriten (vs startodds)
        if "rörelse_ner" in fav.tags:
            spik = min(100.0, spik + 8)        # stärks i våra egna snapshots (stark signal)
        if fav_value and fav_value > 0:        # undervärderad favorit (lågt streck) = bättre spik
            spik = min(100.0, spik + min(18.0, fav_value))
    if basis_src == "streck":
        spik *= 0.6    # streck-baserad favorit är en svagare signal (sharp är inte det)
    spik = round(spik, 1)

    # öppen-score: hur SVAG favoriten är (saknas klar favorit => öppen match).
    # En 55%-favorit är inte "öppen" även om X/2 delar på resten.
    open_score = 0.0
    if fav_prob is not None:
        open_score = round(max(0.0, min(1.0, (OPEN_HI - fav_prob) / (OPEN_HI - OPEN_LO))) * 100, 1)

    # speltyp = tydlig etikett som driver både badge och rekommendation
    if fav_prob is None:
        speltyp = "avvakta"
    elif fav_prob >= SPIK_PROB_LABEL:
        speltyp = "spik"
    elif fav_prob >= HALF_PROB_LABEL:
        speltyp = "halvspik"
    elif fav_prob < OPEN_PROB_LABEL:
        speltyp = "gardera"
    else:
        speltyp = "lutar"
    if basis_src == "streck" and speltyp == "spik":
        speltyp = "halvspik"    # utan odds är vi försiktigare
    # värdespik: kort odds men klart underspelad av folket (t.ex. 2.00-oddsare på 30%)
    if (basis_src != "streck" and speltyp in ("halvspik", "lutar")
            and fav_value is not None and fav_value >= 10 and fav_prob and fav_prob >= 0.42):
        speltyp = "värdespik"

    # spik-boost när sharp bekräftar SS-favoriten (bara relevant när basen är SS-odds)
    if basis_src == "odds" and has_sharp and fav_sign and sharp_probs.get(fav_sign) is not None:
        if sharp_probs[fav_sign] >= SPIK_PROB:
            spik = round(min(100.0, spik + 6), 1)

    # bästa värdetecknet — väg in sharp (value_sharp) när det finns
    def _eff(o: OutcomeAnalysis):
        return o.value_sharp if o.value_sharp is not None else o.value
    valued = {s: _eff(oa[s]) for s in SIGNS if _eff(oa[s]) is not None}
    best_value = max(valued, key=valued.get) if valued else None
    if best_value is not None and valued[best_value] < VALUE_MIN:
        best_value = None

    rec = _recommendation(speltyp, fav_sign, oa, basis_src, best_value)

    return MatchAnalysis(
        event_number=m.event_number,
        description=m.description,
        league=m.league,
        match_start=m.match_start,
        cancelled=m.cancelled,
        outcomes=oa,
        favourite=fav_sign,
        favourite_prob=fav_prob,
        spik_score=spik,
        open_score=open_score,
        recommendation=rec,
        speltyp=speltyp,
        best_value_sign=best_value,
        prob_source=basis_src,
        has_sharp=has_sharp,
        sharp_bookmaker=(sharp.get("bookmaker") if sharp else None),
        sharp_confidence=(sharp.get("confidence") if sharp else None),
    )


def _recommendation(speltyp, fav, oa, source="odds", best_value=None) -> str:
    if source == "none" or speltyp == "avvakta":
        return "Avvakta odds"
    lead = {"spik": f"Spik {fav}", "halvspik": f"Halvspik {fav}",
            "värdespik": f"Värdespik {fav} (underspelad)",
            "gardera": "Öppen match – gardera", "lutar": f"Lutar {fav}"}
    parts = [lead.get(speltyp, f"Lutar {fav}")]
    if best_value and best_value != fav:
        parts.append(f"värdetecken {best_value}")
    drops = [s for s in SIGNS if "fallande_odds" in oa[s].tags]
    if drops:
        parts.append("fallande odds: " + "/".join(drops))
    moved = [s for s in SIGNS if "rörelse_ner" in oa[s].tags]
    if moved:
        parts.append("rör sig ned: " + "/".join(moved))
    sharp_val = [s for s in SIGNS if "sharp_värde" in oa[s].tags]
    if sharp_val:
        parts.append("sharp-värde: " + "/".join(sharp_val))
    cheap = [s for s in SIGNS if "ss_undervärderad" in oa[s].tags]
    if cheap:
        parts.append("SS billigt: " + "/".join(cheap))
    text = ". ".join(parts)
    if source == "sharp":
        text += " · enbart sharp-odds"
    elif source == "streck":
        text += " · endast streck (inga odds)"
    return text


@dataclass
class DrawAnalysis:
    product: str
    draw_number: int
    state: str
    reg_close_time: Optional[str]
    fetched_at: str
    matches: list[MatchAnalysis]

    @property
    def spikar(self) -> list[MatchAnalysis]:
        return sorted(self.matches, key=lambda m: m.spik_score, reverse=True)


def analyze_draw(draw: Draw, sharp: Optional[dict[int, dict]] = None,
                 movement: Optional[dict[tuple[int, str], dict]] = None) -> DrawAnalysis:
    """sharp: {event_number: {odds:{1,X,2}, ...}} från cache.
    movement: {(event_number, sign): {first,last,n,...}} från snapshots."""
    sharp = sharp or {}
    movement = movement or {}

    def _move_for(ev: int) -> dict:
        return {s: movement[(ev, s)] for s in SIGNS if (ev, s) in movement}

    return DrawAnalysis(
        product=draw.product,
        draw_number=draw.draw_number,
        state=draw.state,
        reg_close_time=draw.reg_close_time,
        fetched_at=draw.fetched_at,
        matches=[analyze_match(m, sharp.get(m.event_number), _move_for(m.event_number))
                 for m in draw.matches],
    )


def analysis_to_dict(a: DrawAnalysis) -> dict:
    return {
        "product": a.product,
        "draw_number": a.draw_number,
        "state": a.state,
        "reg_close_time": a.reg_close_time,
        "fetched_at": a.fetched_at,
        "matches": [asdict(m) for m in a.matches],
    }
