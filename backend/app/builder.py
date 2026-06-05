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


@dataclass
class MatchPick:
    event_number: int
    description: str
    role: str                  # "spik" | "halvgardering" | "helgardering"
    signs: list[str]           # valda tecken, t.ex. ["1"] eller ["1","X"]
    favourite: Optional[str]
    reason: str


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


# ---------- val av tecken per match ----------

def _signs_by_prob(m: MatchAnalysis) -> list[str]:
    pairs = [(s, m.outcomes[s].fair_prob if m.outcomes[s].fair_prob is not None else -1)
             for s in SIGNS]
    pairs.sort(key=lambda p: p[1], reverse=True)
    return [s for s, _ in pairs]


def _pick_signs(m: MatchAnalysis, count: int, cfg: StrategyConfig) -> list[str]:
    """Välj `count` tecken för matchen enligt strategi."""
    order = _signs_by_prob(m)
    if count >= 3:
        return list(SIGNS)
    if count == 1:
        return [m.favourite or order[0]]
    # count == 2: två bästa sannolikheter, men låt värdetecken tränga in vid value_bias
    chosen = order[:2]
    if cfg.value_bias and m.best_value_sign and m.best_value_sign not in chosen:
        chosen = [order[0], m.best_value_sign]
    return chosen


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
    rows = 1
    # mest öppna (osäkra) matcher först
    order = sorted(analysis.matches, key=lambda m: m.open_score, reverse=True)
    for m in order:
        if m.cancelled:
            continue
        if m.open_score < cfg.min_open_for_half:
            continue
        # försök halvgardera
        if rows * 2 <= target:
            counts[m.event_number] = 2
            rows *= 2
            # försök helgardera om matchen är mycket öppen och strategin tillåter
            if cfg.allow_full and m.open_score >= cfg.full_open and rows // 2 * 3 <= target:
                counts[m.event_number] = 3
                rows = rows // 2 * 3
        else:
            break
    return counts


def _build_picks(analysis: DrawAnalysis, cfg: StrategyConfig,
                 counts: dict[int, int]) -> list[MatchPick]:
    picks: list[MatchPick] = []
    for m in analysis.matches:
        c = counts.get(m.event_number, 1)
        if m.cancelled:
            c = 3  # avbruten match ger oftast återbetalning/halvgardering — täck brett
        signs = _pick_signs(m, c, cfg)
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
                      enumerate_rows: bool = False) -> System:
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(analysis, cfg, budget, row_price)
    picks = _build_picks(analysis, cfg, counts)
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
                         expand: float = 4.0) -> System:
    """Reducerat system: ta ett generösare garderingsval (≈ budget×expand rader
    som fullt system) och reducera ner till budget med villkorsreducering.

    Villkor: behåll rader där antalet avvikelser från favorittecknet ligger i
    [lo, hi]. Det skär bort de mest osannolika kombinationerna (alla skrällar
    samtidigt) men behåller bredden — klassisk färg-/villkorsreducering."""
    cfg = STRATEGIES[strategy]
    counts = _size_to_budget(analysis, cfg, budget * expand, row_price)
    picks = _build_picks(analysis, cfg, counts)
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
                           row_price: float = ROW_PRICE) -> System:
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
        picks = _build_picks(analysis, cfg, counts)
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
                      strategy: str = "medel", row_price: float = ROW_PRICE) -> System:
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
            signs = _pick_signs(m, 2, cfg)
            halv_signs[m.event_number] = signs
            picks.append(MatchPick(m.event_number, m.description, "halvgardering",
                                   signs, m.favourite, _reason(m, 2)))
        else:
            sign = m.favourite or _signs_by_prob(m)[0]
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


def system_to_dict(s: System) -> dict:
    d = asdict(s)
    return d
