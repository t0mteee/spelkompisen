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
        return f"spik {m.favourite} ({p}), spik-score {m.spik_score:.0f}"
    base = f"öppen-score {m.open_score:.0f}"
    if m.best_value_sign:
        v = m.outcomes[m.best_value_sign].value
        base += f", värdetecken {m.best_value_sign} (+{v:.0f})"
    return base


# ---------- dimensionering mot budget ----------

def _size_to_budget(analysis: DrawAnalysis, cfg: StrategyConfig,
                    budget: float, row_price: float) -> dict[int, int]:
    """Returnera {event_number: antal_tecken} dimensionerat mot budget.

    Greedy: börja med spik överallt (1 rad). Uppgradera de öppnaste matcherna
    först till halv-, sedan helgardering, så länge radantalet ryms i budget."""
    target = max(1, int(budget / row_price))
    counts = {m.event_number: 1 for m in analysis.matches}
    order = [m for m in sorted(analysis.matches, key=lambda m: m.open_score, reverse=True)
             if not m.cancelled]
    rows = 1
    # Budgeten är ett tak som ska fyllas; strategierna skiljs åt av *hur* den
    # fylls (halv vs hel + värde), inte genom att kapa radantalet.
    # 1) Helgardera de öppnaste matcherna först om strategin tillåter — det ger
    #    tuff/medel högre varians (tröskeln full_open styr hur djärvt).
    if cfg.allow_full:
        for m in order:
            if m.open_score >= cfg.full_open and rows * 3 <= target:
                counts[m.event_number] = 3
                rows *= 3
    # 2) Halvgardera de öppnaste återstående tills budgeten (nästan) är fylld.
    for m in order:
        if counts[m.event_number] == 1 and rows * 2 <= target:
            counts[m.event_number] = 2
            rows *= 2
    # 3) Budget kvar? Uppgradera fler halvor till hel (mest öppna först).
    if cfg.allow_full:
        for m in order:
            if counts[m.event_number] == 2 and rows // 2 * 3 <= target:
                counts[m.event_number] = 3
                rows = rows // 2 * 3
    return counts


def _build_picks(analysis: DrawAnalysis, cfg: StrategyConfig,
                 counts: dict[int, int], value_weight: float = 0.5) -> list[MatchPick]:
    picks: list[MatchPick] = []
    for m in analysis.matches:
        c = counts.get(m.event_number, 1)
        if m.cancelled:
            c = 3  # avbruten match ger oftast återbetalning/halvgardering — täck brett
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
    counts = _size_to_budget(analysis, cfg, budget, row_price)
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
    counts = _size_to_budget(analysis, cfg, budget * expand, row_price)
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


def _poisson_binomial(probs: list[float]) -> list[float]:
    d = [1.0]
    for p in probs:
        nd = [0.0] * (len(d) + 1)
        for j, v in enumerate(d):
            nd[j] += v * (1.0 - p)
            nd[j + 1] += v * p
        d = nd
    return d


def build_ev_system(analysis: DrawAnalysis, strategy: str = "medel",
                    budget: float = 100.0, row_price: float = ROW_PRICE,
                    value_weight: float = 0.5, plan: Optional[dict] = None) -> System:
    """Ranka konkreta rader efter popularitetsjusterad EV och ta de bästa
    som ryms i budgeten. Kandidater = topp-2 tecken per match (topp-3 för de
    öppnaste så långt taket räcker), rankade i två steg: först toppnivå-EV,
    sedan full EV över alla vinstnivåer för de bästa."""
    turnover = analysis.turnover or 0.0
    if not plan or turnover <= 0:
        raise ValueError("EV-rankning kräver aktuell omsättning och vinstplan.")
    n = len(analysis.matches)
    target = max(1, int(budget / row_price))
    field = turnover / row_price
    pools = {c: turnover * plan["ratio"] * share for c, share in plan["splits"].items()}
    top_tier = max(pools)

    # p (marknadens sannolikhet) och q (folkets) per match och tecken
    def _pq(m: MatchAnalysis, s: str) -> tuple[float, float]:
        o = m.outcomes[s]
        p = o.fair_prob if o.fair_prob is not None else (1.0 / 3)
        q = (o.streck / 100.0) if o.streck else p
        return p, max(q, 0.001)

    # kandidattecken: topp-2 enligt teckenpoäng; utöka de öppnaste till 3
    cand: dict[int, list[str]] = {}
    universe = 1
    for m in analysis.matches:
        signs = list(SIGNS) if m.cancelled else _signs_by_score(m, value_weight)[:2]
        cand[m.event_number] = sorted(signs, key=SIGNS.index)
        universe *= len(signs)
    for m in sorted(analysis.matches, key=lambda x: x.open_score, reverse=True):
        if m.cancelled or len(cand[m.event_number]) == 3:
            continue
        if universe // 2 * 3 > EV_UNIVERSE_CAP:
            break
        cand[m.event_number] = list(SIGNS)
        universe = universe // 2 * 3

    ms = analysis.matches
    pq = {(m.event_number, s): _pq(m, s) for m in ms for s in SIGNS}

    # steg 1: enumerera kandidatrader med toppnivå-EV (p×pott/(fält×q+1))
    scored: list[tuple[float, float, float, tuple]] = []   # (ev1, p, q, rad)

    def _walk(i: int, p: float, q: float, acc: list[str]):
        if i == n:
            div = min(pools[top_tier], pools[top_tier] / (field * q + 1.0))
            scored.append((p * div, p, q, tuple(acc)))
            return
        ev = ms[i].event_number
        for s in cand[ev]:
            ps, qs = pq[(ev, s)]
            _walk(i + 1, p * ps, q * qs, acc + [s])

    _walk(0, 1.0, 1.0, [])
    scored.sort(key=lambda t: t[0], reverse=True)

    # steg 2: full EV (alla vinstnivåer) för de bästa kandidaterna
    refine = scored[:max(EV_REFINE_CAP, min(len(scored), target * 2))]
    full: list[tuple[float, tuple]] = []
    for _, _, _, row in refine:
        pf = _poisson_binomial([pq[(m.event_number, s)][0] for m, s in zip(ms, row)])
        pk = _poisson_binomial([pq[(m.event_number, s)][1] for m, s in zip(ms, row)])
        ev_total = 0.0
        for c, pool in pools.items():
            div = min(pool, pool / (field * pk[c] + 1.0))
            ev_total += pf[c] * div
        full.append((ev_total, row))
    full.sort(key=lambda t: t[0], reverse=True)
    chosen = full[:target]

    rows = [list(r) for _, r in chosen]
    ev_sum = sum(e for e, _ in chosen)
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

    return System(
        strategy=strategy, system_type="EV-topp", budget=budget,
        row_price=row_price, num_rows=len(rows), cost=round(cost, 2),
        picks=picks, rows=rows,
        rule=f"Så valdes raderna: alla {universe} möjliga rader med tecknen nedan rankades "
             f"efter EV = radens sannolikhet × förväntad utdelning (utdelningen stiger ju "
             f"färre andra som spelat raden). De {len(rows)} bästa behölls — bort åker både "
             f"folkrader (många delar potten) och rena skrällbomber (för osannolika).",
        note=f"Förv. utdelning ≈ {ev_sum:.0f} kr mot {cost:.0f} kr insats "
             f"(EV {ev_sum - cost:+.0f} kr) vid nuvarande omsättning/streck.",
    )


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
                       bounds_override: Optional[tuple] = None) -> System:
    """colors_override: {(event_number, tecken): 'blå'|'gul'} — användarens egna färger.
    bounds_override: (blo, bhi, glo, ghi) — användarens egna min/max-gränser.
    Utan overrides väljs båda automatiskt för max EV inom budgeten."""
    cfg = STRATEGIES[strategy]
    target = max(1, int(budget / row_price))

    # generösare grundsystem än budgeten — reduceringen skär ner kostnaden
    counts = _size_to_budget(analysis, cfg, budget * 6, row_price)
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
        pool_top = turnover * plan["ratio"] * plan["splits"][c_top]

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
    )


def system_to_dict(s: System) -> dict:
    d = asdict(s)
    return d
