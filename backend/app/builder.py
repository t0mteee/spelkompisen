"""Radförslags-motor: bygger spelförslag från en analyserad omgång.

Begrepp
-------
* **Spik**: match där vi tar exakt ett tecken (hög tilltro).
* **Halvgardering**: två tecken på en match.
* **Helgardering**: alla tre tecken.
* **Rader** = produkten av antal tecken per match. Kostnad = rader × radpris.

Strategier
----------
* **säker** : många spikar, få (och försiktiga) garderingar -> få rader.
* **medel**  : balans; gardera de öppnare matcherna.
* **tuff**   : färre spikar, jaga värde, fler hel­garderingar -> fler rader, högre varians.

Systemtyper
-----------
* **matematiskt** : spela alla kombinationer av valda garderingar (dimensioneras
  så att radantalet håller sig inom budget).
* **reducerat**   : utgå från ett generösare gardering­sval (skulle bli för dyrt
  som fullt system) och *reducera* med ett villkor (färg-/villkorsreducering):
  behåll bara rader där antalet avvikelser från favorittecknet ligger i ett
  rimligt intervall. Ger bred täckning till lägre kostnad.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, asdict, field
from typing import Optional

from .analysis import DrawAnalysis, MatchAnalysis

SIGNS = ("1", "X", "2")
ROW_PRICE = 1.0  # Stryktipset: 1 kr/rad
COMPLEMENTARY_PREFERRED_QUALITY = 0.75
COMPLEMENTARY_FALLBACK_QUALITY = 0.60
COMPLEMENTARY_MIN_QUALITY = 0.55
MAX_MATH_MATCHES = 13
MAX_MATH_SPIKES = 3
MAX_MATH_HALF_GUARDS = 1
MAX_MATH_FULL_GUARDS = 9
MAX_MATH_ROWS = (3 ** MAX_MATH_FULL_GUARDS
                 * 2 ** MAX_MATH_HALF_GUARDS)
# SANNOLIKHETSBAS FÖR EV-RANKNINGEN (uppmätt 2026-09-02). `_rank_ev_rows`
# tog `fair_prob`, som är SvS-odds devigade när SvS-odds finns och Pinnacle
# bara som reserv — medan `ev_candidate_signs`, `_size_to_budget` och
# dubbelkupongen tar Pinnacle först. Samma byggare, två baser. PH4 pit-v4
# fällde streck och streckrörelse mot REN Pinnacle, men den arm som vann var
# alltså inte den som EV-byggaren kör. Uppmätt skillnad vid h3 där båda
# källorna observerats: 0,03–0,04 i L1-avstånd per match, ingen konsekvent
# riktning, överlapp 12–35 % av matcherna — liten, men aldrig mätt som
# radval. `prob_base="svs"` är byte-identisk med tidigare beteende och
# förblir standard; `"sharp"` mäts som PH3-utmanare under egen config_key.
PROB_BASES = ("svs", "sharp")
DRAW_RISK_VERSION = "pool-draw-risk-v1"
DRAW_RISK_TOTAL_MAX = 2.25
DRAW_RISK_X_MIN = 0.295
DRAW_RISK_X_STRONG = 0.32


@dataclass
class StrategyConfig:
    name: str
    min_open_for_half: float   # öppen-score som krävs för halvgardering
    full_open: float           # öppen-score som krävs för helgardering
    allow_full: bool
    value_bias: bool           # ta med värdetecken i garderingar


STRATEGIES: dict[str, StrategyConfig] = {
    "säker": StrategyConfig("säker", 58, 999, False, False),
    "medel": StrategyConfig("medel", 48, 66, True, False),
    "tuff": StrategyConfig("tuff", 38, 52, True, True),
}
# Värdevikten (EV-/värdereglaget) är en enda axel som frontend kopplar till
# strategin (säker -> låg, tuff -> hög), så reglaget och strategin inte krockar.


@dataclass
class MatchPick:
    event_number: int
    description: str
    role: str                  # "spik" | "halvgardering" | "helgardering"
    signs: list[str]           # valda tecken, t.ex. ["1"] eller ["1","X"]
    favourite: Optional[str]
    reason: str
    colors: Optional[dict] = None   # {tecken: "blå"|"gul"} vid färgreducering


@dataclass
class System:
    strategy: str
    system_type: str           # "matematiskt" | "reducerat"
    budget: float
    row_price: float
    num_rows: int
    cost: float
    picks: list[MatchPick]
    rows: list[list[str]] = field(default_factory=list)  # konkreta rader (om uträknade)
    rule: Optional[str] = None
    note: Optional[str] = None
    color_bounds: Optional[dict] = None   # {blo,bhi,glo,ghi,nb_max,ng_max} vid färgreducering
    jackpot: float = 0.0                  # jackpot som faktiskt styrde EV-radvalet
    portfolio_mc: Optional[dict] = None   # WP6: portföljrisk vid förväntad slutomsättning


# ---------- val av tecken per match ----------

def _signs_by_prob(m: MatchAnalysis) -> list[str]:
    pairs = [(s, m.outcomes[s].fair_prob if m.outcomes[s].fair_prob is not None else -1)
             for s in SIGNS]
    pairs.sort(key=lambda p: p[1], reverse=True)
    return [s for s, _ in pairs]


def _sign_score(m: MatchAnalysis, s: str, value_weight: float) -> float:
    """Tecknets attraktivitet = sannolikhet vägt mot värde (sannolikhet ÷ streck).

    value_weight 0 = ren sannolikhet (lågoddsare/favoriter, hög träffchans, lägre
    EV). Högre = mer värde/skräll (lägre chans men högre EV långsiktigt).

    Sharp (Pinnacle) används som sannolikhet/värde när det finns — den är skarpare
    än Svenska Spels odds. Tecken som marknaden *backar* (fallande odds, sharp ser
    dem som underprisade) får dessutom en bonus så att de inte petas bara för att
    folket råkar översträcka dem just nu."""
    o = m.outcomes[s]
    # bästa sannolikhetsestimatet: sharp först, annars SS-odds-baserad fair_prob
    p = o.sharp_prob if o.sharp_prob is not None else (o.fair_prob if o.fair_prob is not None else 0.0)
    ratio = (p / (o.streck / 100)) if (p and o.streck) else 1.0
    score = p * (ratio ** (3.0 * max(0.0, value_weight)))
    # marknaden backar tecknet -> håll kvar det (skala med värdevikten)
    tags = o.tags or []
    if any(t in tags for t in ("ss_undervärderad", "rörelse_ner", "fallande_odds")):
        score *= 1.0 + 0.15 * (1.0 + max(0.0, value_weight))
    if "rlm_go" in tags:      # smart pengar: sharp in medan folket lämnar
        score *= 1.25
    if "rlm_fade" in tags:    # folket in, sharp ut — straffa tecknet
        score *= 0.80
    return score


def _signs_by_score(m: MatchAnalysis, value_weight: float) -> list[str]:
    return sorted(SIGNS, key=lambda s: _sign_score(m, s, value_weight), reverse=True)


def _selection_probability(m: MatchAnalysis, sign: str) -> float:
    outcome = (getattr(m, "outcomes", {}) or {}).get(sign)
    if outcome is None:
        return 0.0
    sharp = getattr(outcome, "sharp_prob", None)
    value = sharp if sharp is not None else getattr(outcome, "fair_prob", None)
    return max(0.0, float(value or 0.0))


def draw_risk_values(probability: float,
                     total_line: Optional[float]) -> dict:
    """Rent kontrakt så ledger/UI kan auditera samma trösklar som byggaren."""
    try:
        total_line = float(total_line) if total_line is not None else None
    except (TypeError, ValueError):
        total_line = None
    low_total = total_line is not None and total_line <= DRAW_RISK_TOTAL_MAX
    protected = bool(
        probability >= DRAW_RISK_X_STRONG
        or (low_total and probability >= DRAW_RISK_X_MIN)
    )
    minimum_share = (min(0.20, max(0.10, probability / 2.0))
                     if protected else 0.0)
    return {
        "version": DRAW_RISK_VERSION,
        "protected": protected,
        "x_probability": probability or None,
        "total_line": total_line,
        "low_total": low_total,
        "minimum_x_share": minimum_share,
    }


def draw_risk_context(m: MatchAnalysis) -> dict:
    """Det frysta, gemensamma X-skyddet för alla automatiska byggare."""
    return draw_risk_values(
        _selection_probability(m, "X"),
        getattr(m, "total_line", None),
    )


def _pick_signs(m: MatchAnalysis, count: int, cfg: StrategyConfig,
                value_weight: float = 0.5,
                draw_risk: bool = True) -> list[str]:
    """Välj `count` tecken (sorterade 1/X/2), viktat mot värde enligt value_weight."""
    if count >= 3:
        return list(SIGNS)
    order = _signs_by_score(m, value_weight)
    if count == 1:
        return [order[0]]
    if draw_risk and draw_risk_context(m)["protected"]:
        non_draw = max(("1", "2"),
                       key=lambda sign: _selection_probability(m, sign))
        return sorted(("X", non_draw), key=SIGNS.index)
    return sorted(order[:2], key=SIGNS.index)


def _role(count: int) -> str:
    return {1: "spik", 2: "halvgardering", 3: "helgardering"}[count]


def _reason(m: MatchAnalysis, count: int,
            draw_risk: bool = True) -> str:
    context = (draw_risk_context(m) if draw_risk else
               {"protected": False})
    risk_text = ""
    if context["protected"]:
        total = (f", total {context['total_line']:g}"
                 if context["total_line"] is not None else "")
        risk_text = (f", X-skydd {context['x_probability']:.0%}{total}")
    if count == 1:
        p = f"{m.favourite_prob*100:.0f}%" if m.favourite_prob else "?"
        score = (f"{m.spik_score:.0f}"
                 if isinstance(m.spik_score, (int, float)) else "?")
        return f"spik {m.favourite} ({p}), spik-score {score}{risk_text}"
    score = (f"{m.open_score:.0f}"
             if isinstance(m.open_score, (int, float)) else "?")
    base = f"öppen-score {score}"
    if m.best_value_sign:
        outcome = m.outcomes.get(m.best_value_sign)
        # Analysen väljer sharp-värdet när det finns och faller annars tillbaka
        # till SvS-oddset. Förklaringstexten måste följa exakt samma regel.
        # Topptipset 4274 hade giltigt sharp-värde men saknade SvS-odds på två
        # matcher; den gamla direkta `.value`-formateringen fällde då hela PH3.
        v = getattr(outcome, "value_sharp", None)
        if v is None:
            v = getattr(outcome, "value", None)
        if isinstance(v, (int, float)):
            base += f", värdetecken {m.best_value_sign} ({v:+.0f})"
    return base + risk_text


# ---------- dimensionering mot budget ----------

def _size_to_budget(analysis: DrawAnalysis, cfg: StrategyConfig,
                    budget: float, row_price: float,
                    value_weight: float = 0.5,
                    draw_risk: bool = True) -> dict[int, int]:
    """Returnera {event_number: antal_tecken} dimensionerat mot budget.

    Värde/kostnads-girig: i varje steg uppgradera den match där NÄSTA tecken
    ger mest täckt sannolikhet per kostnadsökning, dvs maximera
    Δlog(täckt sannolikhet) / Δlog(antal rader). Det betyder att en match med
    klar favorit (litet 2:a-tecken) hellre SPIKAS — och budgeten läggs på
    matcher där garderingen täcker mer — i stället för att blint fördubbla
    kostnaden överallt. Tecknen som faktiskt tas väljs sedan av _pick_signs."""
    import math
    target = max(1, int(budget / row_price))
    counts = {m.event_number: 1 for m in analysis.matches}
    rows = 1
    if draw_risk:
        # X-skyddet ska få faktisk budgeteffekt även i vanliga M-/R-/
        # färgsystem, inte bara byta tecken om en annan heuristik råkar
        # halvgardera matchen. Om budgeten inte räcker till alla tas de
        # tydligaste riskerna först; vi överskrider aldrig användarens insats.
        protected = sorted(
            (m for m in analysis.matches
             if not m.cancelled and draw_risk_context(m)["protected"]),
            key=lambda match: (
                draw_risk_context(match)["x_probability"] or 0.0,
                -match.event_number),
            reverse=True,
        )
        for match in protected:
            if rows * 2 > target:
                break
            counts[match.event_number] = 2
            rows *= 2
    # Täckt sannolikhet för exakt 1/2/3 tecken. Draw-risk kan medvetet byta
    # den andra sidan när en match uppgraderas till halv, så en enkel prefix-
    # ordning är inte alltid samma sak som det faktiska slutvalet.
    coverage: dict[int, dict[int, float]] = {}
    for m in analysis.matches:
        if m.cancelled:
            continue
        coverage[m.event_number] = {
            count: sum(max(1e-4, _selection_probability(m, sign))
                       for sign in _pick_signs(
                           m, count, cfg, value_weight, draw_risk))
            for count in (1, 2, 3)
        }

    def _gain(ev: int) -> Optional[float]:
        c = counts[ev]
        cap = 3 if cfg.allow_full else 2
        if c >= cap:
            return None
        probabilities = coverage.get(ev)
        if not probabilities or c + 1 not in probabilities:
            return None
        cov = max(1e-4, probabilities[c])
        next_cov = max(cov, probabilities[c + 1])
        # effektivitet = täckningsvinst (log) per kostnadsökning (log)
        return math.log(next_cov / cov) / math.log((c + 1) / c)

    while True:
        best, best_eff = None, 0.0
        for ev in counts:
            if rows * (counts[ev] + 1) / counts[ev] > target:
                continue                       # ryms inte i budget
            eff = _gain(ev)
            if eff is not None and eff > best_eff:
                best, best_eff = ev, eff
        if best is None:
            break
        rows = int(round(rows * (counts[best] + 1) / counts[best]))
        counts[best] += 1
    return counts


def _build_picks(analysis: DrawAnalysis, cfg: StrategyConfig,
                 counts: dict[int, int], value_weight: float = 0.5,
                 draw_risk: bool = True) -> list[MatchPick]:
    picks: list[MatchPick] = []
    for m in analysis.matches:
        c = counts.get(m.event_number, 1)
        # STRUKEN MATCH: tidigare tvingades helgardering här ("täck brett" —
        # antagandet var återbetalning/halvgardering). Uppmätt mot
        # settlementlagret 2026-07-24 stämmer det inte: i 593 strukna event
        # vinner det mest streckade tecknet 52,8 % av gångerna, exakt som i
        # 75 514 ostrukna (52,1 %), och omgångar med struken match har INTE
        # fler toppvinnare per omsatt krona (Stryk 1,6 mot 1,6). Matcherna
        # avgörs alltså med riktigt resultat och räknas normalt — och även om
        # de HADE räknats rätt för alla vore helgardering slöseri, eftersom
        # ett enda tecken då räcker. Behandla dem som vanliga matcher.
        signs = _pick_signs(m, c, cfg, value_weight, draw_risk)
        picks.append(MatchPick(
            event_number=m.event_number,
            description=m.description,
            role=_role(len(signs)),
            signs=signs,
            favourite=m.favourite,
            reason=_reason(m, len(signs), draw_risk),
        ))
    return picks


def _num_rows(picks: list[MatchPick]) -> int:
    n = 1
    for p in picks:
        n *= len(p.signs)
    return n


# ---------- publika byggfunktioner ----------

def build_math_system(analysis: DrawAnalysis, strategy: str = "medel",
                      budget: float = 100.0, row_price: float = ROW_PRICE,
                      enumerate_rows: bool = False, value_weight: float = 0.5,
                      draw_risk: bool = True) -> System:
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(
        analysis, cfg, budget, row_price, value_weight, draw_risk)
    picks = _build_picks(
        analysis, cfg, counts, value_weight, draw_risk)
    n = _num_rows(picks)
    rows: list[list[str]] = []
    if enumerate_rows and n <= 100_000:
        rows = [list(combo) for combo in itertools.product(*[p.signs for p in picks])]
    return System(
        strategy=strategy, system_type="matematiskt", budget=budget,
        row_price=row_price, num_rows=n, cost=round(n * row_price, 2),
        picks=picks, rows=rows,
        note=f"{sum(1 for p in picks if p.role=='spik')} spikar, "
             f"{sum(1 for p in picks if p.role=='halvgardering')} halvgarderingar, "
             f"{sum(1 for p in picks if p.role=='helgardering')} helgarderingar",
    )


def build_max_math_system(analysis: DrawAnalysis, strategy: str = "medel",
                          row_price: float = ROW_PRICE,
                          value_weight: float = 0.5,
                          draw_risk: bool = True) -> System:
    """Bygg det förregistrerade matematiska 39 366-raderssystemet.

    Formen är 3 spikar, 1 halvgardering och 9 helgarderingar. Till skillnad
    från gamla 4H+9h köper den inte bredd utan ankare. Draw-risk-skyddade
    matcher får inte bli spikar när tre oskyddade alternativ finns.
    """
    if len(analysis.matches) != MAX_MATH_MATCHES:
        raise ValueError(
            f"matematiskt max kräver {MAX_MATH_MATCHES} matcher")

    cfg = STRATEGIES[strategy]

    def anchor_score(match: MatchAnalysis) -> float:
        scores = [max(1e-12, _sign_score(match, sign, value_weight))
                  for sign in SIGNS]
        # Tydlig etta i profilens egen score + hög faktisk sannolikhet. Ett
        # värdetecken får påverka, men kan inte ensamt göra en skräll till
        # samma typ av ankare som en sannolik favorit.
        best_sign = max(SIGNS, key=lambda sign: _sign_score(
            match, sign, value_weight))
        concentration = max(scores) / sum(scores)
        probability = _selection_probability(match, best_sign)
        return 0.55 * concentration + 0.45 * probability

    protected = [match for match in analysis.matches
                 if draw_risk and draw_risk_context(match)["protected"]]
    protected_events = {match.event_number for match in protected}
    unprotected = [match for match in analysis.matches
                   if match.event_number not in protected_events]
    spike_pool = unprotected if len(unprotected) >= MAX_MATH_SPIKES \
        else list(analysis.matches)
    spike_matches = sorted(
        spike_pool,
        key=lambda match: (anchor_score(match), -match.event_number),
        reverse=True,
    )[:MAX_MATH_SPIKES]
    spike_events = {match.event_number for match in spike_matches}
    remaining = [match for match in analysis.matches
                 if match.event_number not in spike_events]
    half_match = max(
        remaining,
        key=lambda match: (anchor_score(match), -match.event_number),
    )
    counts = {match.event_number: (
        1 if match.event_number in spike_events
        else 2 if match.event_number == half_match.event_number
        else 3
    ) for match in analysis.matches}
    picks = _build_picks(
        analysis, cfg, counts, value_weight, draw_risk)
    rows = [list(combo) for combo in itertools.product(
        *[pick.signs for pick in picks])]
    if len(rows) != MAX_MATH_ROWS:
        raise AssertionError(
            f"matematiskt max gav {len(rows)} i stället för {MAX_MATH_ROWS}")
    return System(
        strategy=strategy, system_type="matematiskt", budget=float(MAX_MATH_ROWS),
        row_price=row_price, num_rows=MAX_MATH_ROWS,
        cost=round(MAX_MATH_ROWS * row_price, 2), picks=picks, rows=rows,
        note=(f"Matematiskt max: {MAX_MATH_FULL_GUARDS} helgarderingar, "
              f"{MAX_MATH_HALF_GUARDS} halvgardering och "
              f"{MAX_MATH_SPIKES} spikar · {DRAW_RISK_VERSION}."),
    )


def build_reduced_system(analysis: DrawAnalysis, strategy: str = "medel",
                         budget: float = 100.0, row_price: float = ROW_PRICE,
                         expand: float = 4.0, value_weight: float = 0.5,
                         draw_risk: bool = True) -> System:
    """Reducerat system: ta ett generösare garderingsval (≈ budget×expand rader
    som fullt system) och reducera ner till budget med villkorsreducering.

    Villkor: behåll rader där antalet avvikelser från favorittecknet ligger i
    [lo, hi]. Det skär bort de mest osannolika kombinationerna (alla skrällar
    samtidigt) men behåller bredden — klassisk färg-/villkorsreducering."""
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(
        analysis, cfg, budget * expand, row_price, value_weight, draw_risk)
    picks = _build_picks(
        analysis, cfg, counts, value_weight, draw_risk)
    full_rows = _num_rows(picks)

    # favorittecken per match (för att räkna avvikelser)
    fav = {p.event_number: (p.favourite or p.signs[0]) for p in picks}

    if full_rows > 500_000:
        # för stort att räkna ut — backa till matematiskt inom budget
        return build_math_system(
            analysis, strategy, budget, row_price, draw_risk=draw_risk)

    sign_lists = [p.signs for p in picks]
    evs = [p.event_number for p in picks]
    target = max(1, int(budget / row_price))

    # generera rader med deras antal avvikelser
    scored: list[tuple[int, list[str]]] = []
    for combo in itertools.product(*sign_lists):
        dev = sum(1 for ev, s in zip(evs, combo) if s != fav[ev])
        scored.append((dev, list(combo)))

    # Ranka de mest sannolika (minst avvikelser) först; det gemensamma
    # X-golvet kan sedan byta in de högst rankade X-rader som krävs.
    scored.sort(key=lambda t: t[0])
    ranked = _EVRankedRows(
        rows=[(-float(dev), -float(index), tuple(row))
              for index, (dev, row) in enumerate(scored)],
        target=min(target, len(scored)), universe=full_rows,
        exponent=0.0, turnover=analysis.turnover or 0.0,
    )
    selected = _select_draw_risk_rows(analysis, ranked, draw_risk)
    rows = [list(row) for _score, _order, row in selected]
    max_dev = max(
        sum(1 for ev, sign in zip(evs, row) if sign != fav[ev])
        for row in rows) if rows else 0

    return System(
        strategy=strategy, system_type="reducerat", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(len(rows) * row_price, 2),
        picks=picks, rows=rows,
        rule=f"Prioritera rader med ≤ {max_dev} avvikelser från "
             f"favorittecknen (av {full_rows} möjliga i det fulla systemet)"
             + (f" och tillämpa {DRAW_RISK_VERSION}." if draw_risk else "."),
        note=f"Reducerat från {full_rows} -> {len(rows)} rader.",
    )


def _hamming(a: tuple, b: tuple) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def _greedy_cover(sign_lists: list[list[str]], radius: int) -> list[tuple]:
    """Minsta (greedy) mängd rader så att VARJE möjligt utfall ligger inom
    `radius` fel från någon spelad rad. Det ger R-systemets garanti."""
    universe = [tuple(c) for c in itertools.product(*sign_lists)]
    if radius <= 0:
        return universe                      # ingen reducering möjlig -> fullt
    if radius >= len(sign_lists):
        return [universe[0]]                  # en rad räcker
    uncovered = set(universe)
    chosen: list[tuple] = []
    while uncovered:
        best, best_cov = None, -1
        for cand in uncovered:               # kandidat ur otäckta = alltid framsteg
            cov = sum(1 for u in uncovered if _hamming(cand, u) <= radius)
            if cov > best_cov:
                best, best_cov = cand, cov
        chosen.append(best)
        uncovered = {u for u in uncovered if _hamming(best, u) > radius}
    return chosen


# R-system: tak på antal garderingskombinationer (håller covering snabb)
MAX_UNIVERSE = 1024


def _guard_priority(match: MatchAnalysis, draw_risk: bool = True) -> float:
    boost = (1000.0 if draw_risk
             and draw_risk_context(match)["protected"] else 0.0)
    return float(match.open_score or 0.0) + boost


def _pick_garderings_capped(analysis: DrawAnalysis, cfg: StrategyConfig,
                            max_universe: int = MAX_UNIVERSE,
                            draw_risk: bool = True) -> dict[int, int]:
    counts = {m.event_number: 1 for m in analysis.matches}
    universe = 1
    for m in sorted(
            analysis.matches,
            key=lambda match: _guard_priority(match, draw_risk),
            reverse=True):
        protected = draw_risk and draw_risk_context(m)["protected"]
        if m.cancelled or (not protected
                           and m.open_score < cfg.min_open_for_half):
            continue
        if universe * 2 > max_universe:
            break
        counts[m.event_number] = 2
        universe *= 2
        if cfg.allow_full and m.open_score >= cfg.full_open and universe // 2 * 3 <= max_universe:
            counts[m.event_number] = 3
            universe = universe // 2 * 3
    return counts


def build_guarantee_system(analysis: DrawAnalysis, strategy: str = "medel",
                           budget: float = 100.0, guarantee: int = 12,
                           row_price: float = ROW_PRICE,
                           value_weight: float = 0.5,
                           draw_risk: bool = True) -> System:
    """Reducerat R-system med garanti 'minst `guarantee` rätt' (av antalet
    matcher) förutsatt att alla dina tecken är rätt. Väljer garderingar efter
    strategi/öppenhet, krymper vid behov tills systemet ryms i budget."""
    cfg = STRATEGIES[strategy]
    n_matches = len(analysis.matches)
    guarantee = max(n_matches - 3, min(n_matches, int(guarantee)))
    target_rows = max(1, int(budget / row_price))
    counts = _pick_garderings_capped(
        analysis, cfg, draw_risk=draw_risk)

    # ordna garderingar efter minst öppen sist (dem droppar vi först om för dyrt)
    by_open = sorted(analysis.matches, key=lambda m: m.open_score)

    rows: list[tuple] = []
    picks: list[MatchPick] = []
    full_rows = 0
    while True:
        picks = _build_picks(
            analysis, cfg, counts, value_weight, draw_risk)
        gard = [p for p in picks if len(p.signs) > 1]
        full_rows = _num_rows(picks)
        if not gard:
            rows = [tuple(p.signs[0] for p in picks)]
            break
        radius = n_matches - guarantee   # tillåtna fel bland garderingar
        cover = _greedy_cover([p.signs for p in gard], radius)
        # bygg fulla rader: spikar fasta + täckta garderingskombinationer
        gard_ev = [p.event_number for p in gard]
        rows = []
        for combo in cover:
            cmap = dict(zip(gard_ev, combo))
            rows.append(tuple(cmap.get(p.event_number, p.signs[0]) for p in picks))
        if len(rows) <= target_rows:
            break
        # för dyrt -> droppa den minst öppna garderingen till spik
        dropped = False
        for m in by_open:
            if counts.get(m.event_number, 1) > 1:
                counts[m.event_number] = 1
                dropped = True
                break
        if not dropped:
            break

    rows_as_lists = [list(r) for r in rows]
    return System(
        strategy=strategy, system_type="reducerat (R-garanti)", budget=budget,
        row_price=row_price, num_rows=len(rows_as_lists),
        cost=round(len(rows_as_lists) * row_price, 2), picks=picks, rows=rows_as_lists,
        rule=f"Garanterar minst {guarantee} rätt om alla dina tecken är korrekta "
             f"(tillåter {n_matches - guarantee} miss bland garderingarna).",
        note=f"Reducerat från {full_rows} till {len(rows_as_lists)} rader.",
    )


# ---------- Svenska Spels egna R-system med 12-rättsgaranti ----------
# Namn: R [helgarderingar]-[halvgarderingar]-[rader]. Alla nedan garanterar
# minst 12 rätt om grundraden (spikarna) är rätt (radie-1-täckning).
SVS_R12: dict[str, dict] = {
    "R 4-0-9":   {"hel": 4, "halv": 0, "rows": 9},
    "R 0-7-16":  {"hel": 0, "halv": 7, "rows": 16},
    "R 3-3-24":  {"hel": 3, "halv": 3, "rows": 24},
    "R 4-4-144": {"hel": 4, "halv": 4, "rows": 144},
}

_HEL_SLOTS = ["1", "X", "2"]
_HALV_SLOTS = ["A", "B"]


def _ternary_hamming4() -> list[tuple]:
    """Perfekt [4,2] ternär Hamming-kod = 9 ord, radie-1-täckning av 3^4."""
    H = [(1, 0, 1, 1), (0, 1, 1, 2)]
    return [tuple(_HEL_SLOTS[d] for d in c)
            for c in itertools.product(range(3), repeat=4)
            if all(sum(H[r][i] * c[i] for i in range(4)) % 3 == 0 for r in range(2))]


def _binary_hamming7() -> list[tuple]:
    """Perfekt [7,4] binär Hamming-kod = 16 ord, radie-1-täckning av 2^7."""
    H = [[(j >> b) & 1 for j in range(1, 8)] for b in range(3)]
    return [tuple(_HALV_SLOTS[d] for d in c)
            for c in itertools.product(range(2), repeat=7)
            if all(sum(H[r][i] * c[i] for i in range(7)) % 2 == 0 for r in range(3))]


def _r12_index_cover(name: str, hel: int, halv: int) -> tuple[list[tuple], bool]:
    """Radie-1-täckning över garderingarnas slots. Returnerar (täckning, exakt?)
    där exakt=True betyder att radantalet matchar Svenska Spels."""
    if name == "R 4-0-9":
        return _ternary_hamming4(), True
    if name == "R 0-7-16":
        return _binary_hamming7(), True
    if name == "R 4-4-144":  # 9 (hel-Hamming) × 16 (fulla halv) = 144, exakt SvS
        full = [tuple(c) for c in itertools.product(*([_HALV_SLOTS] * 4))]
        return [tuple(list(h) + list(v)) for h in _ternary_hamming4() for v in full], True
    # övriga (R 3-3-24): greedy ger giltig 12-garanti men inte SvS minsta antal
    return _greedy_cover([_HEL_SLOTS] * hel + [_HALV_SLOTS] * halv, 1), False


def build_svs_rsystem(analysis: DrawAnalysis, name: str = "R 3-3-24",
                      strategy: str = "medel", row_price: float = ROW_PRICE,
                      value_weight: float = 0.5,
                      draw_risk: bool = True) -> System:
    """Bygg ett av Svenska Spels 12-rättsgaranti-R-system. Helgarderar de mest
    öppna matcherna, halvgarderar nästa, spikar resten — och genererar de
    faktiska raderna med 12-garantin verifierad."""
    cfg = STRATEGIES[strategy]
    if len(analysis.matches) != 13:
        raise ValueError("Svenska Spels R-system gäller bara 13-matchskuponger "
                         "(Stryktipset/Europatipset).")
    spec = SVS_R12[name]
    hel, halv = spec["hel"], spec["halv"]

    order = sorted(
        analysis.matches,
        key=lambda match: _guard_priority(match, draw_risk),
        reverse=True)
    hel_ms = order[:hel]
    halv_ms = order[hel:hel + halv]
    hel_ev = {m.event_number for m in hel_ms}
    halv_ev = {m.event_number for m in halv_ms}

    halv_signs: dict[int, list[str]] = {}
    picks: list[MatchPick] = []
    for m in analysis.matches:
        if m.event_number in hel_ev:
            picks.append(MatchPick(m.event_number, m.description, "helgardering",
                                   list(SIGNS), m.favourite,
                                   _reason(m, 3, draw_risk)))
        elif m.event_number in halv_ev:
            signs = _pick_signs(m, 2, cfg, value_weight, draw_risk)
            halv_signs[m.event_number] = signs
            picks.append(MatchPick(m.event_number, m.description, "halvgardering",
                                   signs, m.favourite,
                                   _reason(m, 2, draw_risk)))
        else:
            sign = _signs_by_score(m, value_weight)[0]
            picks.append(MatchPick(m.event_number, m.description, "spik",
                                   [sign], m.favourite,
                                   _reason(m, 1, draw_risk)))

    cover, exact = _r12_index_cover(name, hel, halv)
    rows: list[list[str]] = []
    for combo in cover:
        rowmap: dict[int, str] = {}
        for i, m in enumerate(hel_ms):
            rowmap[m.event_number] = combo[i]                     # "1"/"X"/"2"
        for j, m in enumerate(halv_ms):
            s = halv_signs[m.event_number]
            rowmap[m.event_number] = s[0] if combo[hel + j] == "A" else s[1]
        rows.append([rowmap.get(p.event_number, p.signs[0]) for p in picks])

    official = spec["rows"]
    note = (f"{hel} helgard., {halv} halvgard., {13 - hel - halv} spikar. "
            f"Välj systemet {name} på Svenska Spels systemkupong.")
    if not exact:
        note += (f" (Egna rader: {len(rows)} med samma 12-garanti; "
                 f"välj {name} på kupongen för exakt {official}.)")
    return System(
        strategy=strategy, system_type=f"Svenska Spel-system {name}", budget=0.0,
        row_price=row_price, num_rows=official, cost=round(official * row_price, 2),
        picks=picks, rows=rows,
        rule=f"{name}: garanterar minst 12 rätt om dina spikar är rätt.",
        note=note,
    )


# ---------- EV-toppade rader (poolspels-optimering) ----------
# Poolspels-teorin: värdet sitter i RADEN, inte i enskilda tecken. EV per rad =
# P(raden vinner) × utdelning, där utdelningen beror på hur många man delar med:
# pott / (fält × P_folk(raden) + 1). Bästa raderna är de där kvoten
# P_odds / P_folk är hög — rader folket inte spelar men marknaden tror på.

EV_UNIVERSE_CAP = 60_000     # max kandidatrader att enumerera
EV_REFINE_CAP = 4_000        # rader som får full vinstnivå-EV (Poisson-binomial)
TOPPTIPS_X_BALANCED_VERSION = "topptips-xbalans-v1"
TOPPTIPS_ROW_SHAPE_VERSION = "topptips-radform-v1"
TOPPTIPS_PRODUCTS = frozenset(
    {"topptipset", "topptipsetstryk", "topptipsetextra"})


def _prize_pools(turnover: float, plan: dict, jackpot: float = 0.0) -> dict[int, float]:
    """Vinstplanens potter; jackpot/rullpott tillhör endast toppnivån."""
    pools = {c: turnover * plan["ratio"] * share
             for c, share in plan["splits"].items()}
    if pools:
        pools[max(pools)] += max(0.0, jackpot)
    return pools


def _poisson_binomial(probs: list[float]) -> list[float]:
    d = [1.0]
    for p in probs:
        nd = [0.0] * (len(d) + 1)
        for j, v in enumerate(d):
            nd[j] += v * (1.0 - p)
            nd[j + 1] += v * p
        d = nd
    return d


def x_count_distribution(analysis: DrawAnalysis) -> list[float]:
    """Marknadens sannolikhet för exakt 0..n kryss i en omgång.

    Krysssannolikheten kommer från samma sharp-först-estimat som radbyggaren.
    Fördelningen används bara för portföljens spridning; en enskild rads EV
    räknas fortfarande med den ordinarie, popularitetsjusterade modellen.
    """
    probabilities = []
    for match in analysis.matches:
        outcome = match.outcomes["X"]
        probability = (outcome.sharp_prob if outcome.sharp_prob is not None
                       else outcome.fair_prob)
        probabilities.append(max(0.0, min(1.0, probability or (1.0 / 3.0))))
    return _poisson_binomial(probabilities)


def _largest_remainder_quotas(probabilities: list[float], target: int,
                              capacities: dict[int, int]) -> dict[int, int]:
    """Deterministiska heltalskvoter som summerar till target.

    Hamiltons största-rest-metod ger den närmaste heltalsfördelningen. Om en
    grupp saknar tillräckligt många kandidatrader fylls resten i de grupper
    som ligger längst under sin ideala kvot.
    """
    target = max(0, target)
    raw = {count: target * probability
           for count, probability in enumerate(probabilities)}
    quotas = {
        count: min(capacities.get(count, 0), int(raw.get(count, 0.0)))
        for count in capacities
    }
    remaining = target - sum(quotas.values())
    while remaining > 0:
        eligible = [count for count, capacity in capacities.items()
                    if quotas.get(count, 0) < capacity]
        if not eligible:
            break
        count = max(
            eligible,
            key=lambda item: (
                raw.get(item, 0.0) - quotas.get(item, 0),
                probabilities[item] if item < len(probabilities) else 0.0,
                -item,
            ),
        )
        quotas[count] = quotas.get(count, 0) + 1
        remaining -= 1
    return quotas


# κ-korrektion per produkt och nivå (PH4-analysen 2026-07-24, se
# docs/ph4-analys-2026-07-24.md). κ = faktiska medvinnare ÷ oberoende-
# förväntade, mätt på 7 754 avgjorda omgångar. κ > 1 betyder att folket
# klumpar ihop sig MER än oberoende-antagandet: fler delar potten och
# utdelningen blir lägre. Korrektionen SÄNKER därför EV och kan aldrig blåsa
# upp förväntningar. Värdena är 2024+-skattningarna (senaste regimen).
# Saknad produkt/nivå ⇒ 1,0, dvs. exakt det gamla beteendet.
KAPPA_VERSION = "kappa-ph4-2024plus"
KAPPA: dict[str, dict[int, float]] = {
    "stryktipset":     {13: 1.096, 12: 1.114, 11: 1.102, 10: 1.076},
    "europatipset":    {13: 1.070, 12: 1.064, 11: 1.063, 10: 1.048},
    "topptipset":      {8: 1.038},
    "topptipsetstryk": {8: 1.040},
    "topptipsetextra": {8: 1.022},
}

# `topptips-radform-v1`, tränad på utvecklingsdelen 2024-01-01–2026-08-23
# och därefter låst före holdoutkörningen. Absolut kappa per produkt och antal
# X i den EXAKTA raden; bucket 4 betyder fyra eller fler. Se
# docs/topptips-radform-v1-forregistrering.md och -resultat.md. Värdena får
# inte trimmas mot senare facit under samma versionsnamn.
TOPPTIPS_ROW_SHAPE_KAPPA: dict[str, dict[int, float]] = {
    "topptipset": {
        0: 1.0967540741273925, 1: 1.0130136309628786,
        2: 1.0249454407029754, 3: 1.0880232233410114,
        4: 1.120878592571974,
    },
    "topptipsetstryk": {
        0: 1.0988672804359232, 1: 1.014965487669936,
        2: 1.0269202874095322, 3: 1.0901196072010133,
        4: 1.1230382815750029,
    },
    "topptipsetextra": {
        0: 1.0798484236591475, 1: 0.9973987773064179,
        2: 1.0091466670505211, 3: 1.0712521524609957,
        4: 1.1036010805477432,
    },
}


def kappa_for(product: Optional[str], correct: int) -> float:
    """Medvinnarkorrektion för (produkt, rättnivå); 1,0 när mätning saknas."""
    return (KAPPA.get(product or "", {}) or {}).get(correct, 1.0)


def topptips_row_shape_kappa(product: str) -> dict[int, float]:
    """Returnera en kopia av den frysta v1-kartan för en Topptipsprodukt."""
    values = TOPPTIPS_ROW_SHAPE_KAPPA.get(product)
    if values is None:
        raise ValueError("Radform v1 gäller endast Topptipset-familjen.")
    return dict(values)


def _x_count_bucket(row: tuple[str, ...]) -> int:
    """0, 1, 2, 3 eller 4 där 4 betyder fyra eller fler kryss."""
    return min(row.count("X"), 4)


def _row_expected_value(pf: list[float], pk: list[float],
                        pools: dict[int, float], field: float,
                        product: Optional[str] = None) -> float:
    """Nuvarande analytiska rad-EV, separerad så utdelningsregeln kan testas.

    `pf[c]` är vår sannolikhet för exakt c rätt och `pk[c]` fältets motsvarande
    sannolikhet. WP6-portföljen jämför denna konservativa approximation med
    utfallsberoende medvinnare och konkurrens mellan egna rader.
    `product` aktiverar κ-korrektionen ovan; utan produkt gäller κ = 1.
    """
    total = 0.0
    for correct, pool in pools.items():
        expected_others = field * pk[correct] * kappa_for(product, correct)
        dividend = min(pool, pool / (expected_others + 1.0))
        total += pf[correct] * dividend
    return total


def ev_candidate_signs(analysis: DrawAnalysis,
                       value_weight: float = 0.5,
                       draw_risk: bool = True) -> tuple[dict[int, list[str]], int]:
    """Returnera EV-byggarens kandidattecken och exakta universumstorlek.

    Hjälpfunktionen är den enda källan till kandidatuniversumet. Den används
    både av produktionsbyggaren och PH5:s kontrollarm, så en ablation inte kan
    råka jämföra två olika radmängder.
    """
    cand: dict[int, list[str]] = {}
    universe = 1
    for m in analysis.matches:
        # Strukna matcher behandlas som vanliga (empirisk grund i _pick-koden
        # ovan): de avgörs med riktigt resultat och räknas normalt, så de ska
        # inte äta upp kandidatuniversumet med tvingad helgardering.
        if draw_risk and draw_risk_context(m)["protected"]:
            non_draw = max(("1", "2"),
                           key=lambda sign: _selection_probability(m, sign))
            signs = ["X", non_draw]
        else:
            signs = _signs_by_score(m, value_weight)[:2]
        cand[m.event_number] = sorted(signs, key=SIGNS.index)
        universe *= len(signs)
    for m in sorted(analysis.matches, key=lambda x: x.open_score, reverse=True):
        if len(cand[m.event_number]) == 3:
            continue
        if universe // 2 * 3 > EV_UNIVERSE_CAP:
            break
        cand[m.event_number] = list(SIGNS)
        universe = universe // 2 * 3
    return cand, universe


@dataclass
class _EVRankedRows:
    """Internt rankningsunderlag som kan materialiseras till ett system.

    Standardvägen fullrankar toppurvalet precis som tidigare. Dubbelvägen kan
    dessutom skapa ett bredare B-underlag utan att ändra A:s radval.
    """

    rows: list[tuple[float, float, tuple[str, ...]]]
    target: int
    universe: int
    exponent: float
    turnover: float


def _rank_ev_rows(analysis: DrawAnalysis, budget: float, row_price: float,
                  value_weight: float, plan: Optional[dict],
                  jackpot: float, *, refine_all: bool = False,
                  top_tier_kappa_by_x: Optional[dict[int, float]] = None,
                  full_universe: bool = False,
                  draw_risk: bool = True,
                  prob_base: str = "svs",
                  ) -> _EVRankedRows:
    """Ranka EV-kandidater en gång; används av både enkel- och dubbelkupong."""
    if prob_base not in PROB_BASES:
        raise ValueError(f"okänd sannolikhetsbas: {prob_base!r}")
    turnover = analysis.turnover or 0.0
    if not plan or turnover <= 0:
        raise ValueError("EV-rankning kräver aktuell omsättning och vinstplan.")
    n = len(analysis.matches)
    target = max(1, int(budget / row_price))
    field = turnover / row_price
    pools = _prize_pools(turnover, plan, jackpot)
    top_tier = max(pools)
    k = 2.0 * (1.0 - max(0.0, min(1.0, value_weight)))   # träffchans-exponent

    # p (marknadens sannolikhet) och q (folkets) per match och tecken
    def _pq(m: MatchAnalysis, s: str) -> tuple[float, float]:
        o = m.outcomes[s]
        if prob_base == "sharp" and o.sharp_prob is not None:
            p = o.sharp_prob
        else:
            p = o.fair_prob if o.fair_prob is not None else (1.0 / 3)
        q = (o.streck / 100.0) if o.streck else p
        return p, max(q, 0.001)

    # Vanliga system begränsas till högst EV_UNIVERSE_CAP kandidater. Stora
    # reducerade researchserier rankar däremot hela 3^13-rummet; annars väljer
    # armarna nästan hela samma lilla kandidatmängd och blir matematiskt
    # tvungna att överlappa.
    if full_universe:
        cand = {match.event_number: list(SIGNS) for match in analysis.matches}
        universe = 3 ** len(analysis.matches)
    else:
        # Kandidattecken: topp-2 enligt teckenpoäng; utöka de öppnaste till 3.
        # PH5 använder samma hjälpfunktion för sin byggarslump-kontroll.
        cand, universe = ev_candidate_signs(
            analysis, value_weight, draw_risk)

    ms = analysis.matches
    pq = {(m.event_number, s): _pq(m, s) for m in ms for s in SIGNS}

    # steg 1: enumerera kandidatrader med toppnivå-EV (p×pott/(fält×q+1))
    scored: list[tuple[float, float, float, tuple]] = []   # (ev1, p, q, rad)
    # Fulla 3^13 är 1 594 323 rader. Behåll bara de kandidater som kan nå
    # steg 2 i en min-heap; då ligger minnestoppen nära 80 000 rader i stället
    # för hela utfallsrummet. Standardvägen är byte-identisk med tidigare kod.
    refine_limit = max(EV_REFINE_CAP, min(universe, target * 2))
    coarse_top: list[tuple[float, float, float, tuple]] = []
    risk_requirements = {
        index: max(1, int(math.ceil(
            target * draw_risk_context(match)["minimum_x_share"])))
        for index, match in enumerate(ms)
        if (full_universe and draw_risk
            and draw_risk_context(match)["protected"])
    }
    risk_top: dict[int, list[tuple[float, float, float, tuple]]] = {
        index: [] for index in risk_requirements
    }
    # En gemensam reserv gör flera samtidiga golv genomförbara utan att
    # behöva fullvärdera hela 3^13-rummet. Högt antal skyddade X vinner
    # först; grovscore bryter lika.
    risk_joint_top: list[tuple[int, float, float, float, tuple]] = []

    def _walk(i: int, p: float, q: float, acc: list[str]):
        if i == n:
            div = min(pools[top_tier], pools[top_tier] / (field * q + 1.0))
            # grovranka på balans-scoren så spelbara rader inte filtreras bort
            item = ((p ** k) * p * div, p, q, tuple(acc))
            if full_universe and not refine_all:
                if len(coarse_top) < refine_limit:
                    heapq.heappush(coarse_top, item)
                elif item > coarse_top[0]:
                    heapq.heapreplace(coarse_top, item)
                for index, capacity in risk_requirements.items():
                    if acc[index] != "X":
                        continue
                    heap = risk_top[index]
                    if len(heap) < capacity:
                        heapq.heappush(heap, item)
                    elif item > heap[0]:
                        heapq.heapreplace(heap, item)
                if risk_requirements:
                    x_count = sum(acc[index] == "X"
                                  for index in risk_requirements)
                    joint = (x_count, *item)
                    if len(risk_joint_top) < target:
                        heapq.heappush(risk_joint_top, joint)
                    elif joint > risk_joint_top[0]:
                        heapq.heapreplace(risk_joint_top, joint)
            else:
                scored.append(item)
            return
        ev = ms[i].event_number
        for s in cand[ev]:
            ps, qs = pq[(ev, s)]
            _walk(i + 1, p * ps, q * qs, acc + [s])

    _walk(0, 1.0, 1.0, [])
    if full_universe and not refine_all:
        retained = {item[3]: item for item in coarse_top}
        for heap in risk_top.values():
            retained.update((item[3], item) for item in heap)
        retained.update((item[4], item[1:]) for item in risk_joint_top)
        scored = sorted(retained.values(), key=lambda t: t[0], reverse=True)
    else:
        scored.sort(key=lambda t: t[0], reverse=True)

    # steg 2: full EV (alla vinstnivåer) för de bästa kandidaterna;
    # välj på balans-score, rapportera ärlig EV
    refine = (scored if refine_all or risk_requirements else
              scored[:max(EV_REFINE_CAP, min(len(scored), target * 2))])
    full: list[tuple[float, float, tuple]] = []   # (score, ev_total, rad)
    single_exact_tier = len(pools) == 1 and top_tier == n
    product = getattr(analysis, "product", None)
    for _, p_row, q_row, row in refine:
        if single_exact_tier:
            # Topptipset betalar bara på exakt 8 rätt. Då är
            # Poisson-binomialens enda använda cell exakt produkterna p_row
            # och q_row som redan räknats ovan. Snabbvägen är matematiskt
            # identisk men gör 6 561-radersaudit/backtest praktiskt möjlig.
            pool = pools[top_tier]
            row_kappa = kappa_for(product, top_tier)
            if top_tier_kappa_by_x is not None:
                row_kappa = top_tier_kappa_by_x.get(
                    _x_count_bucket(row), row_kappa)
            expected_others = field * q_row * row_kappa
            dividend = min(pool, pool / (expected_others + 1.0))
            ev_total = p_row * dividend
        else:
            pf = _poisson_binomial(
                [pq[(m.event_number, s)][0] for m, s in zip(ms, row)])
            pk = _poisson_binomial(
                [pq[(m.event_number, s)][1] for m, s in zip(ms, row)])
            ev_total = _row_expected_value(
                pf, pk, pools, field, product)
        full.append(((p_row ** k) * ev_total, ev_total, row))
    full.sort(key=lambda t: t[0], reverse=True)

    return _EVRankedRows(
        rows=full, target=target, universe=universe, exponent=k,
        turnover=turnover,
    )


def _select_draw_risk_rows(
        analysis: DrawAnalysis, ranked: _EVRankedRows,
        draw_risk: bool = True,
) -> list[tuple[float, float, tuple[str, ...]]]:
    """Välj target rader med deterministiska, gemensamma X-minimigolv.

    En enda rad kan fylla flera matchers underskott. Därför skannas den redan
    totalordnade rankningen en gång och den högst rankade rad som hjälper
    minst ett kvarvarande golv tas. När alla golv är fyllda kompletteras med
    de högst rankade återstående raderna.
    """
    if not draw_risk:
        return ranked.rows[:ranked.target]
    protected = []
    for index, match in enumerate(analysis.matches):
        context = draw_risk_context(match)
        if context["protected"]:
            protected.append((
                index,
                max(1, int(math.ceil(
                    ranked.target * context["minimum_x_share"]))),
            ))
    if not protected:
        return ranked.rows[:ranked.target]

    deficits = {index: amount for index, amount in protected}
    chosen = []
    chosen_rows = set()
    ranked_with_order = list(enumerate(ranked.rows))
    # Fyll gemensamt: rader som hjälper flest fortfarande öppna golv går
    # först, med originalrankningen som stabil skiljare. När ett golv
    # fyllts räknas prioriteten om. Det sker högst en gång per skyddad
    # match och undviker att separata kvoter tillsammans äter hela budgeten.
    while any(deficit > 0 for deficit in deficits.values()):
        active = {index for index, deficit in deficits.items()
                  if deficit > 0}
        candidates = sorted(
            (entry for entry in ranked_with_order
             if entry[1][2] not in chosen_rows),
            key=lambda entry: (
                -sum(entry[1][2][index] == "X" for index in active),
                entry[0]),
        )
        progress = False
        satisfied_one = False
        for _rank, item in candidates:
            hits = [index for index in active if item[2][index] == "X"]
            if not hits:
                break
            chosen.append(item)
            chosen_rows.add(item[2])
            progress = True
            for index in hits:
                deficits[index] -= 1
                if deficits[index] == 0:
                    satisfied_one = True
            if satisfied_one or len(chosen) >= ranked.target:
                break
        if not progress or len(chosen) >= ranked.target:
            break
    if any(deficit > 0 for deficit in deficits.values()):
        raise ValueError(
            f"{DRAW_RISK_VERSION}: kandidatuniversumet kan inte fylla X-golvet")
    for item in ranked.rows:
        if item[2] in chosen_rows:
            continue
        chosen.append(item)
        if len(chosen) == ranked.target:
            break
    if len(chosen) != ranked.target:
        raise ValueError(
            f"{DRAW_RISK_VERSION}: fick {len(chosen)} av {ranked.target} rader")
    chosen.sort(key=lambda item: item[0], reverse=True)
    return chosen


def _rows_meet_draw_risk(
        analysis: DrawAnalysis,
        rows: list[tuple[float, float, tuple[str, ...]]],
        draw_risk: bool = True) -> bool:
    if not draw_risk or not rows:
        return True
    for index, match in enumerate(analysis.matches):
        context = draw_risk_context(match)
        if not context["protected"]:
            continue
        required = int(math.ceil(len(rows) * context["minimum_x_share"]))
        if sum(item[2][index] == "X" for item in rows) < required:
            return False
    return True


def _ev_system_from_rows(analysis: DrawAnalysis, strategy: str, budget: float,
                         row_price: float, jackpot: float,
                         ranked: _EVRankedRows,
                         chosen: list[tuple[float, float, tuple[str, ...]]],
                         complementary: bool = False,
                         draw_risk: bool = True) -> System:
    """Materialisera ett system från redan rankade konkreta rader."""
    ms = analysis.matches
    k = ranked.exponent

    rows = [list(r) for _, _, r in chosen]
    ev_sum = sum(e for _, e, _ in chosen)
    cost = len(rows) * row_price

    # picks-sammanfattning: vilka tecken som faktiskt används per match
    used: dict[int, list[str]] = {m.event_number: [] for m in ms}
    for r in rows:
        for m, s in zip(ms, r):
            if s not in used[m.event_number]:
                used[m.event_number].append(s)
    picks = [MatchPick(m.event_number, m.description, _role(len(used[m.event_number])),
                       sorted(used[m.event_number], key=SIGNS.index),
                       m.favourite, _reason(
                           m, len(used[m.event_number]), draw_risk))
             for m in ms]

    profile = ("max EV (skrälltungt)" if k < 0.4
               else "balans EV × träffchans" if k < 1.4 else "träffsäkra värderader")
    complement_note = (
        " Kupongen är en av två gemensamt optimerade varianter med skilda spikmatcher."
        if complementary else "")
    risk_matches = ([match for match in analysis.matches
                     if draw_risk_context(match)["protected"]]
                    if draw_risk else [])
    risk_note = (f" {DRAW_RISK_VERSION}: X-golv i {len(risk_matches)} "
                 "lågmåls-/hög-X-match(er)." if risk_matches else "")
    return System(
        strategy=strategy, system_type="värderader", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(cost, 2),
        picks=picks, rows=rows,
        # `.replace(",", " ")` byter tusentalsavgränsare mot mellanslag och får
        # DÄRFÖR bara röra jackpotbeloppet. Låter man den svepa hela strängen
        # försvinner de vanliga kommatecknen i brödtexten ("och, utom i max
        # EV-läget," → "och  utom i max EV-läget ").
        rule=(f"Så valdes raderna: alla {ranked.universe} möjliga rader rankades på "
              f"träffchans^{k:.1f} × EV — läge: {profile} (styrs av reglaget). "
              f"EV = radens sannolikhet × förväntad utdelning (utdelningen stiger ju färre "
              f"andra som spelat raden). Bort åker folkrader (många delar potten) och, "
              f"utom i max EV-läget, rena skrällbomber."
              + (f" Jackpot {jackpot:,.0f} kr ingår i toppnivåns radval."
                 if jackpot > 0 else "").replace(",", " ")
              + complement_note + risk_note),
        note=f"Förv. utdelning ≈ {ev_sum:.0f} kr mot {cost:.0f} kr insats "
             f"(EV {ev_sum - cost:+.0f} kr) vid {ranked.turnover:,.0f} kr omsättning "
             f"och nuvarande streck.".replace(",", " "),
        jackpot=max(0.0, jackpot),
    )


def _spike_details(chosen: list[tuple[float, float, tuple[str, ...]]],
                   matches: list[MatchAnalysis]) -> list[dict]:
    if not chosen:
        return []
    details = []
    for index, match in enumerate(matches):
        signs = {row[index] for _, _, row in chosen}
        if len(signs) == 1:
            details.append({
                "event_number": match.event_number,
                "description": match.description,
                "sign": next(iter(signs)),
            })
    return details


def _select_capped_rows(
        eligible: list[tuple[float, float, tuple[str, ...]]], target: int,
        caps: dict[tuple[int, str], int],
) -> Optional[list[tuple[float, float, tuple[str, ...]]]]:
    """Ta de bästa raderna utan att överskrida teckentaken i `caps`."""
    counts = {key: 0 for key in caps}
    selected = []
    for item in eligible:
        row = item[2]
        if any(row[index] == sign and counts[(index, sign)] >= cap
               for (index, sign), cap in caps.items()):
            continue
        selected.append(item)
        for index, sign in caps:
            if row[index] == sign:
                counts[(index, sign)] += 1
        if len(selected) == target:
            return selected
    return None


def _diversify_selected_rows(
        selected: list[tuple[float, float, tuple[str, ...]]],
        other: list[tuple[float, float, tuple[str, ...]]],
        eligible: list[tuple[float, float, tuple[str, ...]]],
        caps: dict[tuple[int, str], int], floor_score: float,
) -> tuple[list[tuple[float, float, tuple[str, ...]]], float]:
    """Byt bort exakta dubblettrader så långt kvalitetsgolvet tillåter.

    Högst två korstak används i praktiken. Kandidater grupperas därför efter
    sin takmask så varje byte kan hittas utan en dyr helskanning per rad.
    """
    chosen = list(selected)
    chosen_set = {item[2] for item in chosen}
    other_set = {item[2] for item in other}
    score = sum(item[0] for item in chosen)
    cap_keys = tuple(caps)
    counts = {
        key: sum(item[2][key[0]] == key[1] for item in chosen)
        for key in cap_keys
    }

    buckets: dict[int, list[tuple[float, float, tuple[str, ...]]]] = {}
    for item in eligible:
        if item[2] in chosen_set or item[2] in other_set:
            continue
        mask = sum((1 << pos) for pos, (index, sign) in enumerate(cap_keys)
                   if item[2][index] == sign)
        buckets.setdefault(mask, []).append(item)
    positions = {mask: 0 for mask in buckets}

    overlapping = sorted(
        (item for item in chosen if item[2] in other_set),
        key=lambda item: item[0])
    for old in overlapping:
        after = {
            key: counts[key] - int(old[2][key[0]] == key[1])
            for key in cap_keys
        }
        best = None
        best_mask = None
        for mask, items in buckets.items():
            pos = positions[mask]
            if pos >= len(items):
                continue
            if any(after[key] + int(bool(mask & (1 << bit))) > caps[key]
                   for bit, key in enumerate(cap_keys)):
                continue
            candidate = items[pos]
            if best is None or candidate[0] > best[0]:
                best, best_mask = candidate, mask
        if best is None:
            continue
        next_score = score - old[0] + best[0]
        if next_score < floor_score:
            continue
        chosen.remove(old)
        chosen.append(best)
        chosen_set.remove(old[2])
        chosen_set.add(best[2])
        for bit, key in enumerate(cap_keys):
            counts[key] = after[key] + int(bool(best_mask & (1 << bit)))
        positions[best_mask] += 1
        score = next_score

    chosen.sort(key=lambda item: item[0], reverse=True)
    return chosen, score


def _best_diversified_pair(
        primary: list[tuple[float, float, tuple[str, ...]]],
        alternative: list[tuple[float, float, tuple[str, ...]]],
        primary_eligible: list[tuple[float, float, tuple[str, ...]]],
        alternative_eligible: list[tuple[float, float, tuple[str, ...]]],
        primary_caps: dict[tuple[int, str], int],
        alternative_caps: dict[tuple[int, str], int], floor_score: float,
) -> tuple[list[tuple[float, float, tuple[str, ...]]],
           list[tuple[float, float, tuple[str, ...]]], float, float, int]:
    """Prova att avdubblera A, B och båda ordningsföljderna."""
    options = []

    a1, a1_score = _diversify_selected_rows(
        primary, alternative, primary_eligible, primary_caps, floor_score)
    options.append((a1, alternative, a1_score,
                    sum(item[0] for item in alternative)))
    b1, b1_score = _diversify_selected_rows(
        alternative, primary, alternative_eligible, alternative_caps,
        floor_score)
    options.append((primary, b1, sum(item[0] for item in primary), b1_score))

    b2, b2_score = _diversify_selected_rows(
        alternative, a1, alternative_eligible, alternative_caps, floor_score)
    options.append((a1, b2, a1_score, b2_score))
    a2, a2_score = _diversify_selected_rows(
        primary, b1, primary_eligible, primary_caps, floor_score)
    options.append((a2, b1, a2_score, b1_score))

    def _key(option):
        a_rows, b_rows, a_score, b_score = option
        overlap = len({item[2] for item in a_rows}
                      & {item[2] for item in b_rows})
        return (-overlap, min(a_score, b_score), a_score + b_score)

    chosen = max(options, key=_key)
    a_rows, b_rows, a_score, b_score = chosen
    overlap = len({item[2] for item in a_rows} & {item[2] for item in b_rows})
    return a_rows, b_rows, a_score, b_score, overlap


def build_complementary_ev_systems(
        analysis: DrawAnalysis, strategy: str = "medel",
        budget: float = 100.0, row_price: float = ROW_PRICE,
        value_weight: float = 0.5, plan: Optional[dict] = None,
        jackpot: float = 0.0,
        quality_floor: float = COMPLEMENTARY_MIN_QUALITY,
        cross_anchor_share: float = 0.50,
        max_overlap_share: float = 0.10,
        draw_risk: bool = True,
) -> tuple[System, Optional[System], dict]:
    """Bygg två portföljvarianter med ömsesidigt skilda spikmatcher.

    Enkelbyggaren är oförändrad. I det frivilliga dubbelläget byggs däremot A
    och B tillsammans: vardera spikar egna matcher och får använda den andra
    kupongens spiktecken på högst hälften av raderna. Exakta radkopior tas bort
    så långt det hårda kvalitetsgolvet tillåter. 75 procent är fortsatt det
    föredragna riktmärket; lägre resultat märks öppet i metadata och UI.
    """
    baseline_ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot,
        draw_risk=draw_risk)
    baseline_rows = _select_draw_risk_rows(
        analysis, baseline_ranked, draw_risk)
    baseline = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, baseline_ranked,
        baseline_rows, draw_risk=draw_risk)
    baseline_score = sum(item[0] for item in baseline_rows)
    metadata = {
        "available": False,
        "quality_floor": quality_floor,
        "preferred_quality_floor": COMPLEMENTARY_PREFERRED_QUALITY,
        "fallback_quality_floor": COMPLEMENTARY_FALLBACK_QUALITY,
        "below_preferred_quality": False,
        "cross_anchor_share": cross_anchor_share,
        "guard_share": 1.0 - cross_anchor_share,
        "max_overlap_share": max_overlap_share,
        "primary_spikes": _spike_details(baseline_rows, analysis.matches),
        "alternative_spikes": [],
        "row_overlap": None,
        "row_overlap_pct": None,
        "primary_quality_ratio": None,
        "alternative_quality_ratio": None,
        "quality_ratio": None,
        "cost_each": baseline.cost,
        "total_cost": round(baseline.cost * 2, 2),
    }
    if baseline_score <= 0 or not baseline_rows:
        metadata["reason"] = (
            "Kupongen saknar ett användbart rankningsunderlag för två varianter.")
        return baseline, None, metadata

    pair_ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot,
        refine_all=True, draw_risk=draw_risk)
    target = len(baseline_rows)
    cap = int(target * cross_anchor_share)

    # Välj ett möjligt ankare per match. Tecknet får vara marknadsfavoriten
    # eller byggarens värdetecken; det som ger bäst target-stort system vinner.
    candidates: list[tuple[float, float, int, str]] = []
    for index, match in enumerate(analysis.matches):
        if draw_risk and draw_risk_context(match)["protected"]:
            continue
        probability_sign = max(
            SIGNS, key=lambda sign: (
                match.outcomes[sign].sharp_prob
                if match.outcomes[sign].sharp_prob is not None
                else match.outcomes[sign].fair_prob) or 0.0)
        signs = dict.fromkeys(
            (probability_sign, _signs_by_score(match, value_weight)[0]))
        best = None
        for sign in signs:
            outcome = match.outcomes[sign]
            probability = (outcome.sharp_prob
                           if outcome.sharp_prob is not None
                           else outcome.fair_prob) or 0.0
            if probability < 0.35:
                continue
            eligible = [item for item in pair_ranked.rows
                        if item[2][index] == sign]
            if len(eligible) < target:
                continue
            anchored_score = sum(item[0] for item in eligible[:target])
            candidate = (anchored_score, probability, index, sign)
            if best is None or candidate > best:
                best = candidate
        if best is not None:
            candidates.append(best)
    candidates.sort(reverse=True)
    candidates = candidates[:9]
    if len(candidates) < 2:
        metadata["reason"] = (
            "Det finns inte två tillräckligt starka matcher att fördela som "
            "separata spikankare vid den valda insatsen.")
        return baseline, None, metadata

    desired_anchors = 2 if len(analysis.matches) >= 12 and target <= 512 else 1

    def find_pair(floor_ratio: float):
        floor_score = baseline_score * floor_ratio
        best = None
        for anchor_count in range(desired_anchors, 0, -1):
            groups = []
            for combo in itertools.combinations(candidates, anchor_count):
                indexes = {item[2] for item in combo}
                if len(indexes) != anchor_count:
                    continue
                fixed = tuple(sorted((item[2], item[3]) for item in combo))
                eligible = [item for item in pair_ranked.rows
                            if all(item[2][index] == sign
                                   for index, sign in fixed)]
                if len(eligible) < target:
                    continue
                if sum(item[0] for item in eligible[:target]) < floor_score:
                    continue
                groups.append((fixed, eligible))

            preliminary = []
            for left, right in itertools.combinations(groups, 2):
                left_fixed, left_eligible = left
                right_fixed, right_eligible = right
                if ({index for index, _ in left_fixed}
                        & {index for index, _ in right_fixed}):
                    continue
                left_caps = {key: cap for key in right_fixed}
                right_caps = {key: cap for key in left_fixed}
                left_rows = _select_capped_rows(
                    left_eligible, target, left_caps)
                right_rows = _select_capped_rows(
                    right_eligible, target, right_caps)
                if left_rows is None or right_rows is None:
                    continue
                left_score = sum(item[0] for item in left_rows)
                right_score = sum(item[0] for item in right_rows)
                if min(left_score, right_score) < floor_score:
                    continue
                left_events = {
                    item["event_number"]
                    for item in _spike_details(left_rows, analysis.matches)}
                right_events = {
                    item["event_number"]
                    for item in _spike_details(right_rows, analysis.matches)}
                if left_events & right_events:
                    continue
                overlap = len({item[2] for item in left_rows}
                              & {item[2] for item in right_rows})
                preliminary.append((
                    (-overlap, min(left_score, right_score),
                     left_score + right_score),
                    left_rows, right_rows, left_eligible, right_eligible,
                    left_caps, right_caps, left_fixed, right_fixed,
                ))

            # Avdubblering är dyrare än urvalet. Prova de 24 mest lovande
            # paren; det räcker för stabilitet men håller väntetiden rimlig.
            preliminary.sort(key=lambda item: item[0], reverse=True)
            for item in preliminary[:24]:
                (_, left_rows, right_rows, left_eligible, right_eligible,
                 left_caps, right_caps, left_fixed, right_fixed) = item
                result = _best_diversified_pair(
                    left_rows, right_rows, left_eligible, right_eligible,
                    left_caps, right_caps, floor_score)
                a_rows, b_rows, a_score, b_score, overlap = result
                if (not _rows_meet_draw_risk(
                        analysis, a_rows, draw_risk)
                        or not _rows_meet_draw_risk(
                            analysis, b_rows, draw_risk)):
                    continue
                if overlap > int(target * max_overlap_share):
                    continue
                a_details = _spike_details(a_rows, analysis.matches)
                b_details = _spike_details(b_rows, analysis.matches)
                if ({detail["event_number"] for detail in a_details}
                        & {detail["event_number"] for detail in b_details}):
                    continue
                key = (-overlap, min(a_score, b_score), a_score + b_score)
                if best is None or key > best[0]:
                    best = (key, a_rows, b_rows, a_score, b_score,
                            overlap, a_details, b_details, anchor_count,
                            left_fixed, right_fixed)
            if best is not None:
                break
        return best

    # Behåll 75 procent när det går. Den vanliga fallbacken är 60 procent;
    # 55 är bara sista skyddsnätet för snapshots precis på gränsen. De tre
    # separata stegen gör sökningen monoton trots 24-parstaket: en bredare
    # kandidatlista får aldrig tränga undan ett redan funnet starkare par.
    search_floors = (
        max(quality_floor, COMPLEMENTARY_PREFERRED_QUALITY),
        max(quality_floor, COMPLEMENTARY_FALLBACK_QUALITY),
        quality_floor,
    )
    best_pair = None
    for floor_ratio in dict.fromkeys(search_floors):
        best_pair = find_pair(floor_ratio)
        if best_pair is not None:
            break

    if best_pair is None:
        metadata["reason"] = (
            "Det gick inte att skapa två tydligt skilda kuponger över "
            f"minimikravet {quality_floor:.0%}. Prova en annan insats eller strategi.")
        return baseline, None, metadata

    (_, primary_rows, alternative_rows, primary_score, alternative_score,
     overlap, primary_details, alternative_details, anchor_count,
     primary_fixed, alternative_fixed) = best_pair

    def anchor_details(fixed):
        return [{
            "event_number": analysis.matches[index].event_number,
            "description": analysis.matches[index].description,
            "sign": sign,
        } for index, sign in fixed]

    primary_anchors = anchor_details(primary_fixed)
    alternative_anchors = anchor_details(alternative_fixed)
    primary = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, pair_ranked,
        primary_rows, complementary=True, draw_risk=draw_risk)
    alternative = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, pair_ranked,
        alternative_rows, complementary=True, draw_risk=draw_risk)
    primary_quality = primary_score / baseline_score
    alternative_quality = alternative_score / baseline_score
    metadata.update({
        "available": True,
        "primary_spikes": primary_anchors,
        "alternative_spikes": alternative_anchors,
        "primary_all_spikes": primary_details,
        "alternative_all_spikes": alternative_details,
        "row_overlap": overlap,
        "row_overlap_pct": round(overlap / target, 4) if target else 0.0,
        "primary_quality_ratio": round(primary_quality, 4),
        "alternative_quality_ratio": round(alternative_quality, 4),
        "quality_ratio": round(alternative_quality, 4),
        "below_preferred_quality": (
            min(primary_quality, alternative_quality)
            < COMPLEMENTARY_PREFERRED_QUALITY),
        "anchor_count_each": anchor_count,
        "baseline_changed": True,
        "reason": None,
    })
    return primary, alternative, metadata


def build_ev_system(analysis: DrawAnalysis, strategy: str = "medel",
                    budget: float = 100.0, row_price: float = ROW_PRICE,
                    value_weight: float = 0.5, plan: Optional[dict] = None,
                    jackpot: float = 0.0,
                    full_universe: bool = False,
                    draw_risk: bool = True,
                    prob_base: str = "svs") -> System:
    """Ranka konkreta rader efter EV **balanserat mot träffchans** och ta de
    bästa som ryms i budgeten.

    Ren EV-maximering väljer skrällrader som nästan aldrig går in — matematiskt
    rätt på oändlig sikt men ospelbart för 100–500 kr-insatser. Därför rankas
    raderna på score = P(rad)^k × EV(rad), där k styrs av EV-reglaget
    (value_weight): 1.0 → k=0 (ren EV, gamla beteendet), 0.5 → k=1 (balans,
    ≈ maximera P×EV ~ log-tillväxt), 0.0 → k=2 (träffsäkra värderader).
    EV rapporteras alltid ärligt oavsett ranking."""
    ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot,
        full_universe=full_universe, draw_risk=draw_risk,
        prob_base=prob_base)
    chosen = _select_draw_risk_rows(analysis, ranked, draw_risk)
    system = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, ranked,
        chosen, draw_risk=draw_risk)
    if prob_base != "svs":
        # Standardvägen lämnar noten byte-identisk; bara avvikande bas märks.
        system.note = (f"Sannolikhetsbas {prob_base} (Pinnacle först, SvS "
                       f"som reserv). {system.note or ''}").strip()
    return system


def _x_balanced_rows(analysis: DrawAnalysis, ranked: _EVRankedRows
                     ) -> tuple[list[tuple[float, float, tuple[str, ...]]],
                                dict[int, int]]:
    """Välj högst rankade rader inom marknadskalibrerade X-grupper."""
    groups: dict[int, list[tuple[float, float, tuple[str, ...]]]] = {}
    for item in ranked.rows:
        groups.setdefault(item[2].count("X"), []).append(item)
    quotas = _largest_remainder_quotas(
        x_count_distribution(analysis), ranked.target,
        {count: len(rows) for count, rows in groups.items()},
    )
    chosen = [item for count, rows in groups.items()
              for item in rows[:quotas.get(count, 0)]]
    # Presentationsordningen följer samma score som ordinarie byggare.
    chosen.sort(key=lambda item: item[0], reverse=True)
    return chosen, quotas


def build_topptips_x_balanced_system(
        analysis: DrawAnalysis, strategy: str = "medel",
        budget: float = 100.0, row_price: float = ROW_PRICE,
        value_weight: float = 0.5, plan: Optional[dict] = None,
        jackpot: float = 0.0, draw_risk: bool = True) -> System:
    """Researchkandidat: ordinarie EV inom marknadskalibrerade X-grupper.

    Topptipsets 3^8 = 6 561 utfall ryms helt. Därför kan samtliga rader
    fullrankas och portföljen få samma fördelning av antal X som marknadens
    sharp-först-sannolikheter implicerar. Funktionen ändrar inte
    `build_ev_system` och används inte av produktionsförslag utan ett separat
    beslut efter backtest/forwardtest.
    """
    if getattr(analysis, "product", None) not in TOPPTIPS_PRODUCTS:
        raise ValueError("X-balanserad v1 gäller endast Topptipset-familjen.")
    if len(analysis.matches) != 8:
        raise ValueError("X-balanserad v1 kräver exakt åtta matcher.")
    ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot,
        refine_all=True, draw_risk=draw_risk)
    chosen, quotas = _x_balanced_rows(analysis, ranked)
    if len(chosen) != ranked.target:
        raise ValueError(
            f"X-balanseringen gav {len(chosen)} av {ranked.target} rader.")
    system = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, ranked, chosen,
        draw_risk=draw_risk)
    quota_text = ", ".join(
        f"{count}X:{amount}" for count, amount in sorted(quotas.items())
        if amount)
    system.system_type = "x-balanserade-värderader"
    system.rule += (
        f" {TOPPTIPS_X_BALANCED_VERSION}: raderna fördelades efter marknadens "
        f"sannolikhet för antal kryss ({quota_text}); inom varje grupp valdes "
        "högst ordinarie EV-score.")
    return system


def build_topptips_row_shape_system(
        analysis: DrawAnalysis, kappa_by_x: dict[int, float],
        strategy: str = "medel", budget: float = 100.0,
        row_price: float = ROW_PRICE, value_weight: float = 0.5,
        plan: Optional[dict] = None, jackpot: float = 0.0,
        draw_risk: bool = True) -> System:
    """Researchkandidat med historiskt skattad medvinnareffekt per X-antal.

    Kandidaten ändrar inte matchernas sannolikheter och tvingar inte in ett
    visst antal X-rader. Skillnaden mot ordinarie byggare är att utdelningen
    för en rad räknas med en separat kappa för 0, 1, 2, 3 respektive 4+ X.
    Kartan måste tränas utanför den period där systemet utvärderas.
    """
    if getattr(analysis, "product", None) not in TOPPTIPS_PRODUCTS:
        raise ValueError("Radform v1 gäller endast Topptipset-familjen.")
    if len(analysis.matches) != 8:
        raise ValueError("Radform v1 kräver exakt åtta matcher.")
    missing = set(range(5)) - set(kappa_by_x)
    if missing or any(not (0.25 <= value <= 4.0)
                      for value in kappa_by_x.values()):
        raise ValueError(
            "Radform v1 kräver rimlig kappa för grupperna 0,1,2,3,4+.")
    ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot,
        refine_all=True, top_tier_kappa_by_x=kappa_by_x,
        draw_risk=draw_risk)
    chosen = _select_draw_risk_rows(analysis, ranked, draw_risk)
    system = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, ranked, chosen,
        draw_risk=draw_risk)
    kappa_text = ", ".join(
        f"{count if count < 4 else '4+'}X:{kappa_by_x[count]:.3f}"
        for count in range(5))
    system.system_type = "radformsjusterade-värderader"
    system.rule += (
        f" {TOPPTIPS_ROW_SHAPE_VERSION}: medvinnarprognosen justerades efter "
        f"antal X ({kappa_text}); {DRAW_RISK_VERSION} tillämpades separat.")
    return system


# ---------- färgreducering (villkorsreducering med min/max per färg) ----------
# Klassisk färgreducering: utmanartecken färgas BLÅ (näst bästa tecknet) och
# GUL (tredje tecknet/skrällen). Regeln "minst a, högst b blå rätt + minst c,
# högst d gula rätt" skär bort både folkraden (0 utmanare = alla spelar den)
# och skräll-bomberna (för många avvikelser = chanslös). Gränserna väljs
# automatiskt för att maximera total EV bland raderna som ryms i budgeten.


def build_color_system(analysis: DrawAnalysis, strategy: str = "medel",
                       budget: float = 100.0, row_price: float = ROW_PRICE,
                       value_weight: float = 0.5, plan: Optional[dict] = None,
                       colors_override: Optional[dict] = None,
                       bounds_override: Optional[tuple] = None,
                       jackpot: float = 0.0,
                       draw_risk: bool = True) -> System:
    """colors_override: {(event_number, tecken): 'blå'|'gul'} — användarens egna färger.
    bounds_override: (blo, bhi, glo, ghi) — användarens egna min/max-gränser.
    Utan overrides väljs båda automatiskt för max EV inom budgeten."""
    cfg = STRATEGIES[strategy]
    target = max(1, int(budget / row_price))

    # generösare grundsystem än budgeten — reduceringen skär ner kostnaden
    counts = _size_to_budget(
        analysis, cfg, budget * 6, row_price, value_weight, draw_risk)
    picks = _build_picks(
        analysis, cfg, counts, value_weight, draw_risk)
    while _num_rows(picks) > EV_UNIVERSE_CAP:      # håll enumereringen hanterbar
        for m in sorted(
                analysis.matches,
                key=lambda match: _guard_priority(match, draw_risk)):
            c = counts.get(m.event_number, 1)
            if c > 1:
                counts[m.event_number] = c - 1
                break
        else:
            break
        picks = _build_picks(
            analysis, cfg, counts, value_weight, draw_risk)
    full_rows = _num_rows(picks)
    if full_rows <= target:
        return build_math_system(analysis, strategy, budget, row_price,
                                 enumerate_rows=True, value_weight=value_weight,
                                 draw_risk=draw_risk)

    # färgsätt utmanartecknen: rank 2 -> blå, rank 3 -> gul (eller användarens egna)
    order = {m.event_number: _signs_by_score(m, value_weight) for m in analysis.matches}
    color_of: dict[tuple[int, str], str] = {}
    if colors_override is not None:
        valid = {(p.event_number, s) for p in picks for s in p.signs}
        color_of = {k: v for k, v in colors_override.items() if k in valid}
    else:
        for p in picks:
            ranked = [s for s in order[p.event_number] if s in p.signs]
            if len(ranked) >= 2:
                color_of[(p.event_number, ranked[1])] = "blå"
            if len(ranked) >= 3:
                color_of[(p.event_number, ranked[2])] = "gul"
    for p in picks:
        p.colors = {s: color_of[(p.event_number, s)] for s in p.signs
                    if (p.event_number, s) in color_of} or None

    # p/q per tecken + EV-grund (toppnivån); utan omsättning rankas på sannolikhet
    turnover = analysis.turnover or 0.0
    field = turnover / row_price if turnover > 0 else 0.0
    pool_top = 0.0
    if plan and turnover > 0:
        c_top = max(plan["splits"])
        pool_top = _prize_pools(turnover, plan, jackpot)[c_top]

    def _pq(ev: int, s: str) -> tuple[float, float]:
        o = next(m for m in analysis.matches if m.event_number == ev).outcomes[s]
        p = o.fair_prob if o.fair_prob is not None else (1.0 / 3)
        q = (o.streck / 100.0) if o.streck else p
        return p, max(q, 0.001)

    pq = {(p.event_number, s): _pq(p.event_number, s) for p in picks for s in p.signs}

    # enumerera fulla systemet, bucketa per (antal blå, antal gula)
    buckets: dict[tuple[int, int], list] = {}

    def _walk(i: int, nb: int, ng: int, pr: float, qr: float, acc: list[str]):
        if i == len(picks):
            ev1 = pr * (min(pool_top, pool_top / (field * qr + 1.0)) if pool_top else 1.0)
            buckets.setdefault((nb, ng), []).append((ev1, tuple(acc)))
            return
        p = picks[i]
        for s in p.signs:
            col = color_of.get((p.event_number, s))
            ps, qs = pq[(p.event_number, s)]
            _walk(i + 1, nb + (col == "blå"), ng + (col == "gul"),
                  pr * ps, qr * qs, acc + [s])

    _walk(0, 0, 0, 1.0, 1.0, [])
    nb_max = max(k[0] for k in buckets)
    ng_max = max(k[1] for k in buckets)
    protected_indexes = {
        index: draw_risk_context(match)["minimum_x_share"]
        for index, match in enumerate(analysis.matches)
        if draw_risk and draw_risk_context(match)["protected"]
    }
    bstat = {key: {
        "n": len(values),
        "ev": sum(value for value, _row in values),
        "x": {index: sum(row[index] == "X" for _value, row in values)
              for index in protected_indexes},
    } for key, values in buckets.items()}

    if bounds_override is not None:
        blo, bhi, glo, ghi = bounds_override
        blo, bhi = max(0, blo), min(nb_max, bhi)
        glo, ghi = max(0, glo), min(ng_max, ghi)
    else:
        # välj gränser (min/max blå, min/max gul) som maximerar EV inom budgeten
        best, best_ev = None, -1.0
        for blo_ in range(nb_max + 1):
            for bhi_ in range(blo_, nb_max + 1):
                for glo_ in range(ng_max + 1):
                    for ghi_ in range(glo_, ng_max + 1):
                        n = ev = 0.0
                        x_counts = {index: 0 for index in protected_indexes}
                        for (nb, ng), stats in bstat.items():
                            if blo_ <= nb <= bhi_ and glo_ <= ng <= ghi_:
                                n += stats["n"]; ev += stats["ev"]
                                for index in x_counts:
                                    x_counts[index] += stats["x"][index]
                        risk_ok = all(
                            x_counts[index] >= math.ceil(n * share)
                            for index, share in protected_indexes.items())
                        if n and n <= target and risk_ok and ev > best_ev:
                            best, best_ev = (blo_, bhi_, glo_, ghi_), ev
        if best is None:    # ingen färgregel ryms (t.ex. inga färger satta) -> ta bästa raderna rakt av
            allr = sorted((t for v in buckets.values() for t in v), key=lambda t: t[0], reverse=True)
            ranked = _EVRankedRows(
                rows=[(score, score, row) for score, row in allr],
                target=min(target, len(allr)), universe=full_rows,
                exponent=0.0, turnover=turnover)
            selected = _select_draw_risk_rows(
                analysis, ranked, draw_risk)
            rows = [list(row) for _score, _ev, row in selected]
            return System(
                strategy=strategy, system_type="färgreducerat", budget=budget,
                row_price=row_price, num_rows=len(rows), cost=round(len(rows) * row_price, 2),
                picks=picks, rows=rows,
                rule=f"Ingen färgregel rymde budgeten — tog de {len(rows)} bästa raderna (EV) av {full_rows}.",
                note=f"Kostnad {full_rows * row_price:.0f} kr → {len(rows) * row_price:.0f} kr.",
                color_bounds={"blo": 0, "bhi": nb_max, "glo": 0, "ghi": ng_max,
                              "nb_max": nb_max, "ng_max": ng_max},
                jackpot=max(0.0, jackpot),
            )
        blo, bhi, glo, ghi = best
    rows = [list(r) for (nb, ng), v in buckets.items() if blo <= nb <= bhi and glo <= ng <= ghi
            for _, r in v]

    blues = [f"{ev}:{s}" for (ev, s), c in sorted(color_of.items()) if c == "blå"]
    yells = [f"{ev}:{s}" for (ev, s), c in sorted(color_of.items()) if c == "gul"]
    rule = (f"Färgregel — BLÅ ({', '.join(blues)}): minst {blo}, högst {bhi} rätt"
            + (f" · GUL ({', '.join(yells)}): minst {glo}, högst {ghi} rätt" if yells else "")
            + f". Skär {full_rows} → {len(rows)} rader; bort åker folkraden "
              f"(för få utmanare) och skräll-bomberna (för många).")

    manual = colors_override is not None or bounds_override is not None
    return System(
        strategy=strategy, system_type="färgreducerat", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(len(rows) * row_price, 2),
        picks=picks, rows=rows, rule=rule,
        note=f"Kostnad {full_rows * row_price:.0f} kr → {len(rows) * row_price:.0f} kr. "
             + ("Egna färger/gränser." if manual
                else "Gränserna valda för max EV bland kvarvarande rader."),
        color_bounds={"blo": blo, "bhi": bhi, "glo": glo, "ghi": ghi,
                      "nb_max": nb_max, "ng_max": ng_max},
        jackpot=max(0.0, jackpot),
    )


def system_to_dict(s: System) -> dict:
    d = asdict(s)
    return d
