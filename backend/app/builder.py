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

import itertools
from dataclasses import dataclass, asdict, field
from typing import Optional

from .analysis import DrawAnalysis, MatchAnalysis

SIGNS = ("1", "X", "2")
ROW_PRICE = 1.0  # Stryktipset: 1 kr/rad
COMPLEMENTARY_PREFERRED_QUALITY = 0.75
COMPLEMENTARY_FALLBACK_QUALITY = 0.60
COMPLEMENTARY_MIN_QUALITY = 0.55


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


def _pick_signs(m: MatchAnalysis, count: int, cfg: StrategyConfig,
                value_weight: float = 0.5) -> list[str]:
    """Välj `count` tecken (sorterade 1/X/2), viktat mot värde enligt value_weight."""
    if count >= 3:
        return list(SIGNS)
    order = _signs_by_score(m, value_weight)
    if count == 1:
        return [order[0]]
    return sorted(order[:2], key=SIGNS.index)


def _role(count: int) -> str:
    return {1: "spik", 2: "halvgardering", 3: "helgardering"}[count]


def _reason(m: MatchAnalysis, count: int) -> str:
    if count == 1:
        p = f"{m.favourite_prob*100:.0f}%" if m.favourite_prob else "?"
        score = (f"{m.spik_score:.0f}"
                 if isinstance(m.spik_score, (int, float)) else "?")
        return f"spik {m.favourite} ({p}), spik-score {score}"
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
    return base


# ---------- dimensionering mot budget ----------

def _size_to_budget(analysis: DrawAnalysis, cfg: StrategyConfig,
                    budget: float, row_price: float,
                    value_weight: float = 0.5) -> dict[int, int]:
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
    # sannolikhet per tecken i pick-ordning (samma ordning som _pick_signs)
    probs: dict[int, list[float]] = {}
    for m in analysis.matches:
        if m.cancelled:
            continue
        order = _signs_by_score(m, value_weight)
        probs[m.event_number] = [max(1e-4, m.outcomes[s].fair_prob or 1e-4) for s in order]

    def _gain(ev: int) -> Optional[float]:
        c = counts[ev]
        cap = 3 if cfg.allow_full else 2
        if c >= cap:
            return None
        p = probs.get(ev)
        if not p or c >= len(p):
            return None
        cov = sum(p[:c])
        added = p[c]
        # effektivitet = täckningsvinst (log) per kostnadsökning (log)
        return math.log((cov + added) / cov) / math.log((c + 1) / c)

    rows = 1
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
                 counts: dict[int, int], value_weight: float = 0.5) -> list[MatchPick]:
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
        signs = _pick_signs(m, c, cfg, value_weight)
        picks.append(MatchPick(
            event_number=m.event_number,
            description=m.description,
            role=_role(len(signs)),
            signs=signs,
            favourite=m.favourite,
            reason=_reason(m, len(signs)),
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
                      enumerate_rows: bool = False, value_weight: float = 0.5) -> System:
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(analysis, cfg, budget, row_price, value_weight)
    picks = _build_picks(analysis, cfg, counts, value_weight)
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


def build_reduced_system(analysis: DrawAnalysis, strategy: str = "medel",
                         budget: float = 100.0, row_price: float = ROW_PRICE,
                         expand: float = 4.0, value_weight: float = 0.5) -> System:
    """Reducerat system: ta ett generösare garderingsval (≈ budget×expand rader
    som fullt system) och reducera ner till budget med villkorsreducering.

    Villkor: behåll rader där antalet avvikelser från favorittecknet ligger i
    [lo, hi]. Det skär bort de mest osannolika kombinationerna (alla skrällar
    samtidigt) men behåller bredden — klassisk färg-/villkorsreducering."""
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(analysis, cfg, budget * expand, row_price, value_weight)
    picks = _build_picks(analysis, cfg, counts, value_weight)
    full_rows = _num_rows(picks)

    # favorittecken per match (för att räkna avvikelser)
    fav = {p.event_number: (p.favourite or p.signs[0]) for p in picks}

    if full_rows > 500_000:
        # för stort att räkna ut — backa till matematiskt inom budget
        return build_math_system(analysis, strategy, budget, row_price)

    sign_lists = [p.signs for p in picks]
    evs = [p.event_number for p in picks]
    target = max(1, int(budget / row_price))

    # generera rader med deras antal avvikelser
    scored: list[tuple[int, list[str]]] = []
    for combo in itertools.product(*sign_lists):
        dev = sum(1 for ev, s in zip(evs, combo) if s != fav[ev])
        scored.append((dev, list(combo)))

    # behåll de mest sannolika (minst avvikelser) upp till budget
    scored.sort(key=lambda t: t[0])
    kept = scored[:target]
    max_dev = kept[-1][0] if kept else 0
    rows = [r for _, r in kept]

    return System(
        strategy=strategy, system_type="reducerat", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(len(rows) * row_price, 2),
        picks=picks, rows=rows,
        rule=f"Behåll rader med ≤ {max_dev} avvikelser från favorittecknen "
             f"(av {full_rows} möjliga i det fulla systemet).",
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


def _pick_garderings_capped(analysis: DrawAnalysis, cfg: StrategyConfig,
                            max_universe: int = MAX_UNIVERSE) -> dict[int, int]:
    counts = {m.event_number: 1 for m in analysis.matches}
    universe = 1
    for m in sorted(analysis.matches, key=lambda x: x.open_score, reverse=True):
        if m.cancelled or m.open_score < cfg.min_open_for_half:
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
                           row_price: float = ROW_PRICE, value_weight: float = 0.5) -> System:
    """Reducerat R-system med garanti 'minst `guarantee` rätt' (av antalet
    matcher) förutsatt att alla dina tecken är rätt. Väljer garderingar efter
    strategi/öppenhet, krymper vid behov tills systemet ryms i budget."""
    cfg = STRATEGIES[strategy]
    n_matches = len(analysis.matches)
    guarantee = max(n_matches - 3, min(n_matches, int(guarantee)))
    target_rows = max(1, int(budget / row_price))
    counts = _pick_garderings_capped(analysis, cfg)

    # ordna garderingar efter minst öppen sist (dem droppar vi först om för dyrt)
    by_open = sorted(analysis.matches, key=lambda m: m.open_score)

    rows: list[tuple] = []
    picks: list[MatchPick] = []
    full_rows = 0
    while True:
        picks = _build_picks(analysis, cfg, counts, value_weight)
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
                      value_weight: float = 0.5) -> System:
    """Bygg ett av Svenska Spels 12-rättsgaranti-R-system. Helgarderar de mest
    öppna matcherna, halvgarderar nästa, spikar resten — och genererar de
    faktiska raderna med 12-garantin verifierad."""
    cfg = STRATEGIES[strategy]
    if len(analysis.matches) != 13:
        raise ValueError("Svenska Spels R-system gäller bara 13-matchskuponger "
                         "(Stryktipset/Europatipset).")
    spec = SVS_R12[name]
    hel, halv = spec["hel"], spec["halv"]

    order = sorted(analysis.matches, key=lambda m: m.open_score, reverse=True)
    hel_ms = order[:hel]
    halv_ms = order[hel:hel + halv]
    hel_ev = {m.event_number for m in hel_ms}
    halv_ev = {m.event_number for m in halv_ms}

    halv_signs: dict[int, list[str]] = {}
    picks: list[MatchPick] = []
    for m in analysis.matches:
        if m.event_number in hel_ev:
            picks.append(MatchPick(m.event_number, m.description, "helgardering",
                                   list(SIGNS), m.favourite, _reason(m, 3)))
        elif m.event_number in halv_ev:
            signs = _pick_signs(m, 2, cfg, value_weight)
            halv_signs[m.event_number] = signs
            picks.append(MatchPick(m.event_number, m.description, "halvgardering",
                                   signs, m.favourite, _reason(m, 2)))
        else:
            sign = _signs_by_score(m, value_weight)[0]
            picks.append(MatchPick(m.event_number, m.description, "spik",
                                   [sign], m.favourite, _reason(m, 1)))

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


def kappa_for(product: Optional[str], correct: int) -> float:
    """Medvinnarkorrektion för (produkt, rättnivå); 1,0 när mätning saknas."""
    return (KAPPA.get(product or "", {}) or {}).get(correct, 1.0)


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
                       value_weight: float = 0.5) -> tuple[dict[int, list[str]], int]:
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
                  jackpot: float, *, refine_all: bool = False) -> _EVRankedRows:
    """Ranka EV-kandidater en gång; används av både enkel- och dubbelkupong."""
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
        p = o.fair_prob if o.fair_prob is not None else (1.0 / 3)
        q = (o.streck / 100.0) if o.streck else p
        return p, max(q, 0.001)

    # kandidattecken: topp-2 enligt teckenpoäng; utöka de öppnaste till 3.
    # PH5 använder samma hjälpfunktion för sin byggarslump-kontroll.
    cand, universe = ev_candidate_signs(analysis, value_weight)

    ms = analysis.matches
    pq = {(m.event_number, s): _pq(m, s) for m in ms for s in SIGNS}

    # steg 1: enumerera kandidatrader med toppnivå-EV (p×pott/(fält×q+1))
    scored: list[tuple[float, float, float, tuple]] = []   # (ev1, p, q, rad)

    def _walk(i: int, p: float, q: float, acc: list[str]):
        if i == n:
            div = min(pools[top_tier], pools[top_tier] / (field * q + 1.0))
            # grovranka på balans-scoren så spelbara rader inte filtreras bort
            scored.append(((p ** k) * p * div, p, q, tuple(acc)))
            return
        ev = ms[i].event_number
        for s in cand[ev]:
            ps, qs = pq[(ev, s)]
            _walk(i + 1, p * ps, q * qs, acc + [s])

    _walk(0, 1.0, 1.0, [])
    scored.sort(key=lambda t: t[0], reverse=True)

    # steg 2: full EV (alla vinstnivåer) för de bästa kandidaterna;
    # välj på balans-score, rapportera ärlig EV
    refine = (scored if refine_all else
              scored[:max(EV_REFINE_CAP, min(len(scored), target * 2))])
    full: list[tuple[float, float, tuple]] = []   # (score, ev_total, rad)
    for _, p_row, _, row in refine:
        pf = _poisson_binomial([pq[(m.event_number, s)][0] for m, s in zip(ms, row)])
        pk = _poisson_binomial([pq[(m.event_number, s)][1] for m, s in zip(ms, row)])
        ev_total = _row_expected_value(
            pf, pk, pools, field, getattr(analysis, "product", None))
        full.append(((p_row ** k) * ev_total, ev_total, row))
    full.sort(key=lambda t: t[0], reverse=True)

    return _EVRankedRows(
        rows=full, target=target, universe=universe, exponent=k,
        turnover=turnover,
    )


def _ev_system_from_rows(analysis: DrawAnalysis, strategy: str, budget: float,
                         row_price: float, jackpot: float,
                         ranked: _EVRankedRows,
                         chosen: list[tuple[float, float, tuple[str, ...]]],
                         complementary: bool = False) -> System:
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
                       m.favourite, _reason(m, len(used[m.event_number])))
             for m in ms]

    profile = ("max EV (skrälltungt)" if k < 0.4
               else "balans EV × träffchans" if k < 1.4 else "träffsäkra värderader")
    complement_note = (
        " Kupongen är en av två gemensamt optimerade varianter med skilda spikmatcher."
        if complementary else "")
    return System(
        strategy=strategy, system_type="värderader", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(cost, 2),
        picks=picks, rows=rows,
        rule=(f"Så valdes raderna: alla {ranked.universe} möjliga rader rankades på "
              f"träffchans^{k:.1f} × EV — läge: {profile} (styrs av reglaget). "
              f"EV = radens sannolikhet × förväntad utdelning (utdelningen stiger ju färre "
              f"andra som spelat raden). Bort åker folkrader (många delar potten) och, "
              f"utom i max EV-läget, rena skrällbomber."
              + (f" Jackpot {jackpot:,.0f} kr ingår i toppnivåns radval."
                 if jackpot > 0 else "") + complement_note).replace(",", " "),
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
) -> tuple[System, Optional[System], dict]:
    """Bygg två portföljvarianter med ömsesidigt skilda spikmatcher.

    Enkelbyggaren är oförändrad. I det frivilliga dubbelläget byggs däremot A
    och B tillsammans: vardera spikar egna matcher och får använda den andra
    kupongens spiktecken på högst hälften av raderna. Exakta radkopior tas bort
    så långt det hårda kvalitetsgolvet tillåter. 75 procent är fortsatt det
    föredragna riktmärket; lägre resultat märks öppet i metadata och UI.
    """
    baseline_ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot)
    baseline_rows = baseline_ranked.rows[:baseline_ranked.target]
    baseline = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, baseline_ranked,
        baseline_rows)
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
        refine_all=True)
    target = len(baseline_rows)
    cap = int(target * cross_anchor_share)

    # Välj ett möjligt ankare per match. Tecknet får vara marknadsfavoriten
    # eller byggarens värdetecken; det som ger bäst target-stort system vinner.
    candidates: list[tuple[float, float, int, str]] = []
    for index, match in enumerate(analysis.matches):
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
        primary_rows, complementary=True)
    alternative = _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, pair_ranked,
        alternative_rows, complementary=True)
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
                    jackpot: float = 0.0) -> System:
    """Ranka konkreta rader efter EV **balanserat mot träffchans** och ta de
    bästa som ryms i budgeten.

    Ren EV-maximering väljer skrällrader som nästan aldrig går in — matematiskt
    rätt på oändlig sikt men ospelbart för 100–500 kr-insatser. Därför rankas
    raderna på score = P(rad)^k × EV(rad), där k styrs av EV-reglaget
    (value_weight): 1.0 → k=0 (ren EV, gamla beteendet), 0.5 → k=1 (balans,
    ≈ maximera P×EV ~ log-tillväxt), 0.0 → k=2 (träffsäkra värderader).
    EV rapporteras alltid ärligt oavsett ranking."""
    ranked = _rank_ev_rows(
        analysis, budget, row_price, value_weight, plan, jackpot)
    return _ev_system_from_rows(
        analysis, strategy, budget, row_price, jackpot, ranked,
        ranked.rows[:ranked.target])


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
                       jackpot: float = 0.0) -> System:
    """colors_override: {(event_number, tecken): 'blå'|'gul'} — användarens egna färger.
    bounds_override: (blo, bhi, glo, ghi) — användarens egna min/max-gränser.
    Utan overrides väljs båda automatiskt för max EV inom budgeten."""
    cfg = STRATEGIES[strategy]
    target = max(1, int(budget / row_price))

    # generösare grundsystem än budgeten — reduceringen skär ner kostnaden
    counts = _size_to_budget(analysis, cfg, budget * 6, row_price, value_weight)
    picks = _build_picks(analysis, cfg, counts, value_weight)
    while _num_rows(picks) > EV_UNIVERSE_CAP:      # håll enumereringen hanterbar
        for m in sorted(analysis.matches, key=lambda x: x.open_score):
            c = counts.get(m.event_number, 1)
            if c > 1:
                counts[m.event_number] = c - 1
                break
        else:
            break
        picks = _build_picks(analysis, cfg, counts, value_weight)
    full_rows = _num_rows(picks)
    if full_rows <= target:
        return build_math_system(analysis, strategy, budget, row_price,
                                 enumerate_rows=True, value_weight=value_weight)

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
    bstat = {k: (len(v), sum(e for e, _ in v)) for k, v in buckets.items()}

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
                        for (nb, ng), (cnt, evs) in bstat.items():
                            if blo_ <= nb <= bhi_ and glo_ <= ng <= ghi_:
                                n += cnt; ev += evs
                        if n and n <= target and ev > best_ev:
                            best, best_ev = (blo_, bhi_, glo_, ghi_), ev
        if best is None:    # ingen färgregel ryms (t.ex. inga färger satta) -> ta bästa raderna rakt av
            allr = sorted((t for v in buckets.values() for t in v), key=lambda t: t[0], reverse=True)
            rows = [list(r) for _, r in allr[:target]]
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
