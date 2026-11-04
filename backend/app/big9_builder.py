"""Byggaren för ATG:s Big 9 — värderader, samma metod som `build_ev_system`.

Beslut driften-2026-10-24-big9-atg (val 0): standarden för Big 9 är byggaren
på samma budget, strategi medel, och hanterar Ö/U, Wild Card och 7–9 rätt.
Beslut 2026-10-24-sp96-ar-big9 (val 0): samma byggare är standarden för SP96
(nya Big 9) — `Big9Round.wildcard=False` (inget Wild Card, bara cellerna) och
vinstgrupperna 6–9 rätt ur `splits`; byggaren är oförändrad.

En Big 9-rad har per match EN cell av sex — 1X2 × Över/Under 2,5 — skriven
som två tecken (`1O`, `1U`, `XO`, `XU`, `2O`, `2U`), och i BIG9 exakt ett
Wild Card (`W`): matchen räknas som rätt oavsett utfall. Raden skrivs som nio
tokens med mellanslag, t.ex. `1O XU W 2O 1U 1O XO 2U 1O`. SP96 saknar Wild
Card: `1O XU 2U 2O 1U 1O XO 2U 1O`.

Metoden är `builder.build_ev_system`s (värderader), överförd till sex celler:
* Sannolikhet per cell (`p`): ATG:s 1X2- och Ö/U-odds devigas var för sig med
  power-metoden (`analysis._power_probs`). En Poissonmodell (total ur Ö/U,
  fördelning hemma/borta ur 1X2) ger sambandet mellan marknaderna, och
  tabellen anpassas sedan exakt till båda marknadernas sannolikheter (IPF).
  Saknas odds används folkets fördelning (som SvS-byggarens streckreserv).
* Folket (`q`): `betDistribution`, sex celler i procent, golv 0,001 (streck-
  golvet). Wild Card-andelen per match ger fältets träffchans
  w + (1 − w) · q(cell).
* Vinstpotter: omsättning × återbetalningsandel × vinstgrupp-andel (andelen
  läses ur ATG:s publicerade potter, annars 1 − uttag); rullad jackpot
  på toppgruppen. EV per rad = Σ P(k rätt) · pott_k / (fält · Q(k rätt) + 1)
  med Poisson-binomial för både oss och fältet, κ = 1 (ingen mätning finns),
  och 0 kr under minimiutdelningen (15 kr).
* Strategi medel: värdevikt 0,5 ⇒ score = P(rad)^1 · EV(rad).
* Kandidater: per match de bästa cellerna på p²/q (medel), de öppnaste
  matcherna utökas tills universumet når `UNIVERSE_CAP`; Wild Card (där spelet
  har det) prövas på varje match. Grovrankning på toppgruppen, full EV för de bästa
  `REFINE_CAP` (minst 2 × budgetens rader), därefter de bästa på score.
SvS-byggarens X-skydd (`pool-draw-risk-v1`) gäller inte: det kräver Pinnacles
total och är kalibrerat för 1X2-pooler.

FULLT SYSTEM (beslut 2026-11-04-big9-fullt-system, val 0): ATG tar bara fulla
system — "Spela enskilda utfall", valfri mängd av de sex cellerna per match —
inga reducerade urval och ingen radfil. `build_full_system` väljer därför en
cellmängd per match; raderna är hela korsprodukten och antalet (produkten av
mängdernas storlek) är högst budget / radpris. Samma sannolikheter, folk, potter
och score (P(rad)^k · EV(rad)) som `build_rows`; systemets värde är summan över
dess rader:
* Grovt: med toppgruppens utdelning ≈ pott / (fält · Q(rad)) faktoriserar
  summan till Π_match Σ_{c ∈ mängd} p_c^(k+1) / q_c, så för en given storlek
  per match är den bästa mängden de främsta cellerna på p^(k+1)/q. Varje
  maximal storleksvektor (ingen match kan växa inom budgeten) rankas så, och
  likaså med ren täckning (de främsta cellerna på p, värde Π Σ p) eftersom de
  lägre vinstgrupperna belönar täckning.
* Fullt: de bästa kandidaterna ur båda rankningarna (`SYSTEM_REFINE`, färre
  vid stor budget) värderas med full EV över alla rader; högst summa vinner.
`build_rows` (enskilda rader) står kvar för BIG9 med Wild Card och för
historikens nyckel `big9-varderader-v1-*`, men ger inget spelbart ATG-system.
"""
from __future__ import annotations

import heapq
import itertools
import math
from dataclasses import dataclass, field
from typing import Optional

from .analysis import _power_probs

VERSION = "big9-varderader-v1"
SYSTEM_VERSION = "big9-fullsystem-v1"
CELLS = ("1O", "1U", "XO", "XU", "2O", "2U")
WILDCARD = "W"
TOKENS = CELLS + (WILDCARD,)
WINNER_SIGN = {"home": "1", "tie": "X", "away": "2"}
GOALS_SIGN = {"over": "O", "under": "U"}
Q_FLOOR = 0.001
UNIVERSE_CAP = 60_000
REFINE_CAP = 4_000
MAX_GOALS = 15
SYSTEM_REFINE = 120          # kandidatsystem per grovrankning
SYSTEM_EVAL_ROWS = 160_000   # tak för fullt värderade rader per rankning


@dataclass
class Big9Match:
    number: int
    p: dict                      # cell → vår sannolikhet
    q: dict                      # cell → folkets andel
    wildcard_share: float = 0.0  # fältets Wild Card-andel på matchen
    p_source: str = "odds"


@dataclass
class Big9Round:
    product: str
    matches: list
    turnover: float              # värderingsomsättning (kr)
    row_price: float
    payout_ratio: float          # återbetalningsandel (annars 1 − uttag)
    splits: dict                 # vinstgrupp → andel
    jackpot: float = 0.0         # rullad jackpot på toppgruppen (kr)
    min_dividend: float = 15.0   # kr per rad
    wildcard: bool = True
    notes: list = field(default_factory=list)


@dataclass
class Big9System:
    rows: list
    n_rows: int
    cost: float
    note: str
    ev_total: float
    cells: Optional[list] = None     # fullt system: cellmängd per match


# ── sannolikheter ────────────────────────────────────────────────────────

def _poisson(lam: float) -> list[float]:
    out = [math.exp(-lam)]
    for k in range(1, MAX_GOALS + 1):
        out.append(out[-1] * lam / k)
    return out


def _over_prob(mu: float, limit: float) -> float:
    pmf = _poisson(mu)
    return 1.0 - sum(pmf[k] for k in range(int(math.floor(limit)) + 1))


def _solve_mu(p_over: float, limit: float) -> float:
    lo, hi = 0.05, 9.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if _over_prob(mid, limit) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _grid(lh: float, la: float) -> list[list[float]]:
    ph, pa = _poisson(lh), _poisson(la)
    return [[a * b for b in pa] for a in ph]


def _cell_table(lh: float, la: float, limit: float) -> dict:
    table = {c: 0.0 for c in CELLS}
    for h, row in enumerate(_grid(lh, la)):
        for a, value in enumerate(row):
            sign = "1" if h > a else "X" if h == a else "2"
            goals = "O" if h + a > limit else "U"
            table[sign + goals] += value
    total = sum(table.values())
    return {c: v / total for c, v in table.items()}


def _devig(odds: list) -> Optional[list[float]]:
    if any(not isinstance(o, (int, float)) or o <= 1.0 for o in odds):
        return None
    probs = _power_probs({str(i): 1.0 / o for i, o in enumerate(odds)})
    return [probs[str(i)] for i in range(len(odds))]


def cell_probabilities(odds: dict, limit: float = 2.5) -> Optional[dict]:
    """ATG:s odds → sannolikhet per cell, exakt på båda marknaderna."""
    if not isinstance(odds, dict):
        return None
    x12 = _devig([odds.get("home"), odds.get("tie"), odds.get("away")])
    ou = _devig([odds.get("over"), odds.get("under")])
    if x12 is None or ou is None:
        return None
    p1, px, p2 = x12
    p_over = ou[0]
    mu = _solve_mu(p_over, limit)
    lo, hi = 0.01, 0.99            # hemmalagets andel av målen
    for _ in range(60):
        share = (lo + hi) / 2
        t = _cell_table(mu * share, mu * (1 - share), limit)
        diff = (t["1O"] + t["1U"]) - (t["2O"] + t["2U"])
        if diff < p1 - p2:
            lo = share
        else:
            hi = share
    table = _cell_table(mu * share, mu * (1 - share), limit)
    targets_sign = {"1": p1, "X": px, "2": p2}
    targets_goal = {"O": p_over, "U": 1.0 - p_over}
    for _ in range(200):            # IPF: rader (1X2) och kolumner (Ö/U)
        for sign, target in targets_sign.items():
            cur = table[sign + "O"] + table[sign + "U"]
            if cur > 0:
                for g in "OU":
                    table[sign + g] *= target / cur
        for goal, target in targets_goal.items():
            cur = sum(table[s + goal] for s in "1X2")
            if cur > 0:
                for s in "1X2":
                    table[s + goal] *= target / cur
    total = sum(table.values())
    return {c: table[c] / total for c in CELLS}


def folk_distribution(bet_distribution: dict) -> Optional[dict]:
    if not isinstance(bet_distribution, dict):
        return None
    raw = {}
    for key, sign in WINNER_SIGN.items():
        cell = bet_distribution.get(key) or {}
        for gkey, goal in GOALS_SIGN.items():
            value = cell.get(gkey) if isinstance(cell, dict) else None
            if not isinstance(value, (int, float)) or value < 0:
                return None
            raw[sign + goal] = float(value)
    total = sum(raw.values())
    if total <= 0:
        return None
    return {c: max(raw[c] / total, Q_FLOOR) for c in CELLS}


# ── EV ───────────────────────────────────────────────────────────────────

def _poisson_binomial(probs: list[float]) -> list[float]:
    d = [1.0]
    for p in probs:
        nd = [0.0] * (len(d) + 1)
        for j, v in enumerate(d):
            nd[j] += v * (1.0 - p)
            nd[j + 1] += v * p
        d = nd
    return d


def _own_prob(m: Big9Match, token: str) -> float:
    return 1.0 if token == WILDCARD else m.p[token]


def _field_prob(m: Big9Match, token: str, wildcard_game: bool) -> float:
    """Fältets chans att vara rätt på matchen givet att vår token är rätt."""
    w = m.wildcard_share if wildcard_game else 0.0
    if token == WILDCARD:
        hit = sum(m.p[c] * m.q[c] for c in CELLS)
    else:
        hit = m.q[token]
    return w + (1.0 - w) * hit


def prize_pools(rnd: Big9Round) -> dict[int, float]:
    pools = {k: rnd.turnover * rnd.payout_ratio * share
             for k, share in rnd.splits.items()}
    if pools:
        pools[max(pools)] += max(0.0, rnd.jackpot)
    return pools


def _dividend(pool: float, others: float, minimum: float) -> float:
    div = min(pool, pool / (others + 1.0))
    return 0.0 if div < minimum else div


def row_ev(rnd: Big9Round, row: tuple, pools: Optional[dict] = None) -> float:
    pools = pools or prize_pools(rnd)
    field_units = rnd.turnover / rnd.row_price
    pf = _poisson_binomial([_own_prob(m, t) for m, t in zip(rnd.matches, row)])
    pk = _poisson_binomial([_field_prob(m, t, rnd.wildcard)
                            for m, t in zip(rnd.matches, row)])
    return sum(pf[k] * _dividend(pool, field_units * pk[k], rnd.min_dividend)
               for k, pool in pools.items())


# ── kandidater och urval ─────────────────────────────────────────────────

def _universe(sizes: list[int], wildcard: bool) -> int:
    if not wildcard:
        return math.prod(sizes)
    return sum(math.prod(s for j, s in enumerate(sizes) if j != w)
               for w in range(len(sizes)))


def candidate_cells(rnd: Big9Round, exponent: float) -> list[list[str]]:
    ranked = []
    for m in rnd.matches:
        ranked.append(sorted(CELLS, key=lambda c: (
            -(m.p[c] ** (exponent + 1.0)) / m.q[c], CELLS.index(c))))
    sizes = [2] * len(rnd.matches)
    order = sorted(range(len(rnd.matches)),
                   key=lambda i: (max(rnd.matches[i].p.values()), i))
    grown = True
    while grown:
        grown = False
        for i in order:
            if sizes[i] >= len(CELLS):
                continue
            trial = sizes[:]
            trial[i] += 1
            if _universe(trial, rnd.wildcard) > UNIVERSE_CAP:
                continue
            sizes = trial
            grown = True
            break
    return [ranked[i][:sizes[i]] for i in range(len(rnd.matches))]


def row_text(row: tuple) -> str:
    return " ".join(row)


def build_rows(rnd: Big9Round, budget: float, value_weight: float = 0.5) -> Big9System:
    if rnd.turnover <= 0:
        raise ValueError("Big 9-byggaren kräver en omsättning")
    if any(not m.p or not m.q for m in rnd.matches):
        raise ValueError("Big 9-byggaren kräver sannolikheter för alla matcher")
    target = max(1, int(round(budget / rnd.row_price, 6)))
    k = 2.0 * (1.0 - max(0.0, min(1.0, value_weight)))
    pools = prize_pools(rnd)
    top = max(pools)
    field_units = rnd.turnover / rnd.row_price
    cand = candidate_cells(rnd, k)
    n = len(rnd.matches)
    positions = range(n) if rnd.wildcard else (None,)
    refine_limit = max(REFINE_CAP, target * 2)
    heap: list = []
    universe = 0
    for w in positions:
        lists = [[WILDCARD] if i == w else cand[i] for i in range(n)]
        for row in itertools.product(*lists):
            universe += 1
            p_row = 1.0
            q_row = 1.0
            for m, t in zip(rnd.matches, row):
                p_row *= _own_prob(m, t)
                q_row *= _field_prob(m, t, rnd.wildcard)
            div = _dividend(pools[top], field_units * q_row, 0.0)
            item = ((p_row ** k) * p_row * div, row)
            if len(heap) < refine_limit:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)
    full = []
    for _coarse, row in heap:
        p_row = math.prod(_own_prob(m, t) for m, t in zip(rnd.matches, row))
        ev = row_ev(rnd, row, pools)
        full.append(((p_row ** k) * ev, ev, row))
    full.sort(key=lambda item: (item[0], item[2]), reverse=True)
    chosen = full[:target]
    rows = [row_text(row) for _s, _ev, row in chosen]
    ev_total = sum(ev for _s, ev, _row in chosen)
    cost = len(rows) * rnd.row_price
    odds_matches = sum(1 for m in rnd.matches if m.p_source == "odds")
    note = (f"{VERSION}: {len(rows)} rader à {rnd.row_price:.2f} kr ur {universe} "
            f"kandidater; odds på {odds_matches}/{n} matcher (övriga folkets "
            f"fördelning); EV {ev_total:.0f} kr mot insats {cost:.0f} kr")
    if rnd.notes:
        note += "; " + "; ".join(rnd.notes)
    return Big9System(rows=rows, n_rows=len(rows), cost=cost, note=note,
                      ev_total=ev_total)


# ── fullt system (ATG:s "enskilda utfall") ───────────────────────────────

def system_rows(cells: list) -> list[str]:
    """Cellmängd per match → hela korsprodukten som rader (CELLS-ordning)."""
    ordered = [[c for c in CELLS if c in chosen] for chosen in cells]
    return [row_text(row) for row in itertools.product(*ordered)]


def _size_vectors(n: int, cap: int) -> list[tuple[int, ...]]:
    """Alla maximala storleksvektorer: produkt ≤ cap och ingen match kan växa."""
    out: list[tuple[int, ...]] = []
    sizes = [1] * n

    def rec(i: int, prod: int) -> None:
        if i == n:
            if all(s == len(CELLS) or prod // s * (s + 1) > cap for s in sizes):
                out.append(tuple(sizes))
            return
        for s in range(1, len(CELLS) + 1):
            if prod * s > cap:
                break
            sizes[i] = s
            rec(i + 1, prod * s)
        sizes[i] = 1

    rec(0, 1)
    return out


def _coarse_systems(ranked: list[list[str]], values: list[list[float]],
                    vectors: list, keep: int) -> list[tuple]:
    """De `keep` bästa storleksvektorerna på Σ log(Σ värde över mängden)."""
    logs = []
    for vals in values:
        acc, cum = 0.0, []
        for v in vals:
            acc += v
            cum.append(math.log(acc) if acc > 0 else -math.inf)
        logs.append(cum)
    scored = ((sum(logs[i][s - 1] for i, s in enumerate(vec)), vec) for vec in vectors)
    best = heapq.nlargest(keep, scored)
    return [tuple(tuple(sorted(ranked[i][:s], key=CELLS.index))
                  for i, s in enumerate(vec)) for _score, vec in best]


def build_full_system(rnd: Big9Round, budget: float,
                      value_weight: float = 0.5) -> Big9System:
    """Ett fullt system: cellmängd per match, rader = korsprodukten ≤ budget."""
    if rnd.wildcard:
        raise ValueError("fullt system byggs bara för Big 9 utan Wild Card")
    if rnd.turnover <= 0:
        raise ValueError("Big 9-byggaren kräver en omsättning")
    if any(not m.p or not m.q for m in rnd.matches):
        raise ValueError("Big 9-byggaren kräver sannolikheter för alla matcher")
    cap = max(1, int(round(budget / rnd.row_price, 6)))
    k = 2.0 * (1.0 - max(0.0, min(1.0, value_weight)))
    pools = prize_pools(rnd)
    vectors = _size_vectors(len(rnd.matches), cap)
    keep = max(10, min(SYSTEM_REFINE, SYSTEM_EVAL_ROWS // cap))
    candidates: dict[tuple, None] = {}
    rankings = (lambda m, c: m.p[c] ** (k + 1.0) / m.q[c],   # värde (toppgruppen)
                lambda m, c: m.p[c])                         # täckning
    for metric in rankings:
        ranked, values = [], []
        for m in rnd.matches:
            order = sorted(CELLS, key=lambda c: (-metric(m, c), CELLS.index(c)))
            ranked.append(order)
            values.append([metric(m, c) for c in order])
        for system in _coarse_systems(ranked, values, vectors, keep):
            candidates.setdefault(system, None)
    cache: dict[tuple, tuple[float, float]] = {}

    def row_value(row: tuple) -> tuple[float, float]:
        hit = cache.get(row)
        if hit is None:
            p_row = math.prod(m.p[t] for m, t in zip(rnd.matches, row))
            ev = row_ev(rnd, row, pools)
            hit = cache[row] = ((p_row ** k) * ev, ev)
        return hit

    best = None
    for system in candidates:
        score = ev = 0.0
        for row in itertools.product(*system):
            s, e = row_value(row)
            score += s
            ev += e
        n_rows = math.prod(len(c) for c in system)
        item = (score, ev, n_rows, system)
        if best is None or item[:2] > best[:2] or (
                item[:2] == best[:2] and item[3] < best[3]):
            best = item
    _score, ev_total, n_rows, system = best
    cells = [list(c) for c in system]
    rows = system_rows(cells)
    cost = len(rows) * rnd.row_price
    n = len(rnd.matches)
    odds_matches = sum(1 for m in rnd.matches if m.p_source == "odds")
    form = "·".join(str(len(c)) for c in cells)
    note = (f"{SYSTEM_VERSION}: fullt system {form} = {len(rows)} rader à "
            f"{rnd.row_price:.2f} kr ur {len(candidates)} kandidatsystem; odds på "
            f"{odds_matches}/{n} matcher (övriga folkets fördelning); EV "
            f"{ev_total:.0f} kr mot insats {cost:.0f} kr")
    if rnd.notes:
        note += "; " + "; ".join(rnd.notes)
    return Big9System(rows=rows, n_rows=len(rows), cost=cost, note=note,
                      ev_total=ev_total, cells=cells)


def full_system_cells(rows: list[str], n_matches: int) -> Optional[list[list[str]]]:
    """Cellmängd per match om raderna är EXAKT hela korsprodukten, annars None.

    Raderna förutsätts unika och med `n_matches` tokens; de är då hela
    korsprodukten precis när antalet är produkten av mängdernas storlek."""
    sets = [set() for _ in range(n_matches)]
    for row in rows:
        tokens = row.split()
        if len(tokens) != n_matches:
            return None
        for i, token in enumerate(tokens):
            if token not in CELLS:
                return None
            sets[i].add(token)
    if math.prod(len(s) for s in sets) != len(rows):
        return None
    return [[c for c in CELLS if c in s] for s in sets]
