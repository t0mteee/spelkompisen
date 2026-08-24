"""WP6: portföljvärdering för poolsystem.

Den gamla snabbformeln värderar varje rad separat och använder pott/(E[W]+1).
Här simuleras i stället matchutfallen. För varje faktiskt utfall räknas både
fältets utfallsberoende vinsttäthet och hur många av våra egna rader som delar
varje pott. Med W ~ Poisson(lambda) beräknas E[1/(W+k)] numeriskt, där k är
antalet egna vinstrader. Därmed samplas inte medvinnarna och Monte Carlo-bruset
kommer bara från matchutfallen.
"""
from __future__ import annotations

import hashlib
import itertools
import math
import random
from collections import Counter
from typing import Iterable, Optional


SIGNS = ("1", "X", "2")
DEFAULT_SIMULATIONS = 10_000
MAX_PORTFOLIO_ROWS = 5_000


def _poisson_binomial(probs: list[float]) -> list[float]:
    distribution = [1.0]
    for probability in probs:
        updated = [0.0] * (len(distribution) + 1)
        for correct, value in enumerate(distribution):
            updated[correct] += value * (1.0 - probability)
            updated[correct + 1] += value * probability
        distribution = updated
    return distribution


def _gauss_legendre(n: int = 24) -> tuple[tuple[float, float], ...]:
    """Noder/vikter på [-1, 1], skapade en gång utan extern numerikdependency."""
    pairs: list[tuple[float, float]] = []
    for index in range(1, (n + 1) // 2 + 1):
        root = math.cos(math.pi * (index - 0.25) / (n + 0.5))
        derivative = 0.0
        for _ in range(30):
            p0, p1 = 1.0, root
            for degree in range(2, n + 1):
                p0, p1 = p1, ((2 * degree - 1) * root * p1
                               - (degree - 1) * p0) / degree
            derivative = n * (root * p1 - p0) / (root * root - 1.0)
            next_root = root - p1 / derivative
            if abs(next_root - root) < 1e-15:
                root = next_root
                break
            root = next_root
        # Newtonsteget ovan lämnar p1/derivata vid den slutliga roten till
        # maskinprecision; vikten är symmetrisk.
        p0, p1 = 1.0, root
        for degree in range(2, n + 1):
            p0, p1 = p1, ((2 * degree - 1) * root * p1
                           - (degree - 1) * p0) / degree
        derivative = n * (root * p1 - p0) / (root * root - 1.0)
        weight = 2.0 / ((1.0 - root * root) * derivative * derivative)
        pairs.append((-root, weight))
        if abs(root) > 1e-14:
            pairs.append((root, weight))
    return tuple(sorted(pairs))


_GL24 = _gauss_legendre()


def expected_poisson_reciprocal(expected_winners: float,
                                own_winners: int) -> float:
    """E[1/(W+k)] för W~Poisson(expected_winners), k=own_winners.

    Identiteten E[1/(W+k)] = integral_0^1 x^(k-1)e^(lambda(x-1)) dx
    integreras efter en skalning som håller massan välupplöst även när lambda
    är flera miljoner. 24-punkts Gauss-Legendre ger nära maskinprecision i de
    intervall poolspelen använder. För k=1 används den slutna formen exakt.
    """
    lam = max(0.0, float(expected_winners))
    k = int(own_winners)
    if k < 1:
        raise ValueError("own_winners måste vara minst 1")
    if lam == 0.0:
        return 1.0 / k
    if k == 1:
        return -math.expm1(-lam) / lam

    scale = lam + k
    # Efter y=(lambda+k)(1-x) avtar integranden minst ungefär e^-y.
    # Svansen efter 40 bidrar mindre än 5e-18.
    upper = min(scale, 40.0)
    midpoint = upper / 2.0
    weighted = 0.0
    for node, weight in _GL24:
        y = midpoint * (node + 1.0)
        remaining = 1.0 - y / scale
        log_value = ((k - 1) * math.log(remaining)
                     - (lam / scale) * y)
        weighted += weight * math.exp(log_value)
    value = midpoint * weighted / scale
    return max(0.0, min(1.0 / k, value))


def materialize_system_rows(system, cap: int = MAX_PORTFOLIO_ROWS
                            ) -> Optional[list[list[str]]]:
    """Returnera de konkreta rader användaren faktiskt spelar, inom säker cap."""
    if getattr(system, "rows", None):
        rows = [list(row) for row in system.rows]
        return rows if len(rows) <= cap else None
    picks = getattr(system, "picks", None) or []
    total = 1
    for pick in picks:
        total *= len(pick.signs)
    if not picks or total > cap:
        return None
    return [list(row) for row in itertools.product(*[pick.signs for pick in picks])]


def _normalized(values: Iterable[float], fallback: tuple[float, ...]) -> tuple[float, ...]:
    vals = tuple(max(0.0, float(value or 0.0)) for value in values)
    total = sum(vals)
    if total <= 0:
        vals, total = fallback, sum(fallback)
    return tuple(value / total for value in vals)


def _probability_tables(analysis) -> tuple[list[tuple[float, ...]],
                                           list[tuple[float, ...]]]:
    fair_rows: list[tuple[float, ...]] = []
    folk_rows: list[tuple[float, ...]] = []
    for match in analysis.matches:
        fair = _normalized(
            (getattr(match.outcomes[sign], "fair_prob", None) for sign in SIGNS),
            (1 / 3, 1 / 3, 1 / 3),
        )
        folk = _normalized(
            ((getattr(match.outcomes[sign], "streck", None) or 0.0) / 100.0
             for sign in SIGNS),
            fair,
        )
        fair_rows.append(fair)
        folk_rows.append(folk)
    return fair_rows, folk_rows


def _row_masks(rows: list[list[str]], n_matches: int
               ) -> tuple[list[tuple[int, int, int]], int]:
    masks = [[0, 0, 0] for _ in range(n_matches)]
    for row_index, row in enumerate(rows):
        if len(row) != n_matches or any(sign not in SIGNS for sign in row):
            raise ValueError("Alla portföljrader måste ha ett giltigt tecken per match.")
        bit = 1 << row_index
        for match_index, sign in enumerate(row):
            masks[match_index][SIGNS.index(sign)] |= bit
    return [tuple(per_match) for per_match in masks], (1 << len(rows)) - 1


def _own_correct_counts(outcome: tuple[int, ...], masks: list[tuple[int, int, int]],
                        all_rows: int) -> list[int]:
    """Hammingfördelning för tusentals rader via Python-heltal som bitset."""
    groups = [all_rows] + [0] * len(outcome)
    for match_index, sign_index in enumerate(outcome):
        hit_mask = masks[match_index][sign_index]
        miss_mask = all_rows ^ hit_mask
        updated = [0] * len(groups)
        for correct in range(match_index + 1):
            group = groups[correct]
            updated[correct] |= group & miss_mask
            updated[correct + 1] |= group & hit_mask
        groups = updated
    return [group.bit_count() for group in groups]


def _weighted_percentile(values: list[tuple[float, float]], quantile: float) -> float:
    target = max(0.0, min(1.0, quantile)) * sum(weight for _, weight in values)
    cumulative = 0.0
    for value, weight in sorted(values):
        cumulative += weight
        if cumulative + 1e-15 >= target:
            return value
    return max(value for value, _ in values)


def _stable_seed(analysis, rows: list[list[str]], turnover: float,
                 jackpot: float, simulations: int) -> int:
    draw_number = getattr(analysis, "draw_number", "unknown")
    payload = (f"{draw_number}|{turnover:.2f}|{jackpot:.2f}|{simulations}|"
               + ";".join("".join(row) for row in rows))
    return int(hashlib.sha256(payload.encode()).hexdigest()[:16], 16)


def simulate_pool_portfolio(analysis, rows: list[list[str]], plan: dict,
                            turnover: float, row_price: float = 1.0,
                            jackpot: float = 0.0,
                            simulations: int = DEFAULT_SIMULATIONS,
                            kappa: float = 1.0,
                            kappa_by_tier: Optional[dict[int, float]] = None,
                            top_tier_kappa_by_x: Optional[dict[int, float]] = None,
                            seed: Optional[int] = None,
                            turnover_basis: str = "provided") -> dict:
    """Värdera ett helt poolsystem med utfallsberoende medvinnare.

    För kuponger med högst 3^8 möjliga utfall används full enumeration. För
    13 matcher används ett deterministiskt Monte Carlo-stickprov.

    Medvinnarkalibrering: `kappa_by_tier` (PH4-κ per vinstnivå, samma tabell
    som builder._row_expected_value och frontendens evalRows använder sedan
    2026-07-24) gör portföljvärderingen KONSISTENT med rad-EV:n — tidigare
    körde den okalibrerat 1,00 medan radvalet var κ-korrigerat, så samma
    system fick två olika sanningar (2026-07-28). κ ≥ 1 sänker EV och kan
    aldrig blåsa upp förväntningar (PH4:s ärlighetsargument). Skalära
    `kappa` är kvar som fallback för nivåer utan mätning och för tester.
    `top_tier_kappa_by_x` används endast på den exakta toppnivån och håller
    Radform v1:s portföljkort konsekvent med radvalet.
    """
    if not rows:
        raise ValueError("Portföljsimulering kräver minst en konkret rad.")
    if len(rows) > MAX_PORTFOLIO_ROWS:
        raise ValueError(f"Portföljen får innehålla högst {MAX_PORTFOLIO_ROWS} rader.")
    if turnover <= 0 or row_price <= 0:
        raise ValueError("Portföljsimulering kräver positiv omsättning och radinsats.")
    n_matches = len(analysis.matches)
    if n_matches < 1:
        raise ValueError("Portföljsimulering kräver minst en match.")
    if not plan or not plan.get("splits"):
        raise ValueError("Portföljsimulering kräver en vinstplan.")
    simulations = max(100, int(simulations))
    kappa = max(0.01, float(kappa))
    tier_kappa = {int(c): max(0.01, float(v))
                  for c, v in (kappa_by_tier or {}).items()}
    x_kappa = {int(count): max(0.01, float(value))
               for count, value in (top_tier_kappa_by_x or {}).items()}

    def _kappa(correct: int) -> float:
        return tier_kappa.get(correct, kappa)

    def _row_kappa(correct: int, encoded) -> float:
        if correct == top_tier and x_kappa:
            return x_kappa.get(min(encoded.count(1), 4), _kappa(correct))
        return _kappa(correct)

    jackpot = max(0.0, float(jackpot))
    fair, folk = _probability_tables(analysis)
    masks, all_rows = _row_masks(rows, n_matches)
    pools = {int(correct): turnover * plan["ratio"] * float(share)
             for correct, share in plan["splits"].items()}
    if any(correct < 0 or correct > n_matches for correct in pools):
        raise ValueError("Vinstplanens nivåer passar inte kupongens antal matcher.")
    top_tier = max(pools)
    pools[top_tier] += jackpot
    field_rows = turnover / row_price
    cost = len(rows) * row_price

    # Den gamla radvisa approximationen, beräknad på exakt samma normaliserade
    # sannolikheter, blir en rättvis jämförelse mot portföljvärderingen.
    analytical_by_tier = {correct: 0.0 for correct in pools}
    row_indexes = [[SIGNS.index(sign) for sign in row] for row in rows]
    for encoded in row_indexes:
        fair_hits = _poisson_binomial(
            [fair[i][sign_index] for i, sign_index in enumerate(encoded)])
        folk_hits = _poisson_binomial(
            [folk[i][sign_index] for i, sign_index in enumerate(encoded)])
        for correct, pool in pools.items():
            # samma κ som builder-EV:n — annars jämför vi mot en okalibrerad
            # variant som inte längre finns i drift
            dividend = pool / (
                field_rows * folk_hits[correct]
                * _row_kappa(correct, encoded) + 1.0)
            analytical_by_tier[correct] += fair_hits[correct] * min(pool, dividend)

    # Toppnivån kan räknas utan utfalls-MC. Dubblettrader grupperas så även
    # deras egen konkurrens hanteras korrekt.
    top_exact = 0.0
    for encoded, multiplicity in Counter(tuple(row) for row in row_indexes).items():
        fair_probability = math.prod(
            fair[i][sign_index] for i, sign_index in enumerate(encoded))
        folk_probability = math.prod(
            folk[i][sign_index] for i, sign_index in enumerate(encoded))
        reciprocal = expected_poisson_reciprocal(
            field_rows * folk_probability
            * _row_kappa(top_tier, encoded), multiplicity)
        top_exact += (fair_probability * pools[top_tier]
                      * multiplicity * reciprocal)

    seed = _stable_seed(analysis, rows, turnover, jackpot, simulations) if seed is None else int(seed)
    outcome_space = 3 ** n_matches
    exhaustive = outcome_space <= simulations
    scenarios: list[tuple[tuple[int, ...], float]] = []
    if exhaustive:
        for outcome in itertools.product(range(3), repeat=n_matches):
            weight = math.prod(fair[i][sign_index]
                               for i, sign_index in enumerate(outcome))
            if weight > 0:
                scenarios.append((outcome, weight))
        iterations = outcome_space
    else:
        rng = random.Random(seed)
        sampled: Counter[tuple[int, ...]] = Counter()
        for _ in range(simulations):
            outcome = []
            for probabilities in fair:
                draw = rng.random()
                outcome.append(0 if draw < probabilities[0]
                               else 1 if draw < probabilities[0] + probabilities[1]
                               else 2)
            sampled[tuple(outcome)] += 1
        scenarios = [(outcome, count / simulations)
                     for outcome, count in sampled.items()]
        iterations = simulations

    payout_distribution: list[tuple[float, float]] = []
    tier_returns = {correct: 0.0 for correct in pools}
    solo_return = 0.0
    for outcome, weight in scenarios:
        own_counts = _own_correct_counts(outcome, masks, all_rows)
        external_hits = _poisson_binomial(
            [folk[i][sign_index] for i, sign_index in enumerate(outcome)])
        total_payout = 0.0
        solo_payout = 0.0
        for correct, pool in pools.items():
            own = own_counts[correct]
            if not own:
                continue
            expected_external = (
                field_rows * external_hits[correct]
                * _row_kappa(correct, outcome))
            portfolio_share = min(
                pool,
                pool * own * expected_poisson_reciprocal(expected_external, own),
            )
            # Kontrafaktiskt facit: varje egen rad låtsas vara ensam. Skillnaden
            # isolerar hur mycket de egna raderna konkurrerar på lägre nivåer.
            solo_share = pool * own * expected_poisson_reciprocal(expected_external, 1)
            tier_returns[correct] += weight * portfolio_share
            total_payout += portfolio_share
            solo_payout += solo_share
        payout_distribution.append((total_payout, weight))
        solo_return += weight * solo_payout

    total_weight = sum(weight for _, weight in payout_distribution)
    mean_return = sum(value * weight for value, weight in payout_distribution) / total_weight
    variance = sum(weight * (value - mean_return) ** 2
                   for value, weight in payout_distribution) / total_weight
    stdev = math.sqrt(max(0.0, variance))
    probability_zero = sum(weight for value, weight in payout_distribution
                           if value < 0.005) / total_weight
    probability_profit = sum(weight for value, weight in payout_distribution
                             if value > cost + 1e-9) / total_weight
    analytical_return = sum(analytical_by_tier.values())
    own_drag = max(0.0, solo_return - mean_return)
    mc_error_90 = 0.0 if exhaustive else 1.645 * stdev / math.sqrt(iterations)

    percentiles = {
        f"p{int(q * 100):02d}": round(_weighted_percentile(payout_distribution, q), 2)
        for q in (0.05, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
    }
    return {
        "available": True,
        "method": "exhaustive" if exhaustive else "monte_carlo",
        "iterations": iterations,
        "unique_scenarios": len(scenarios),
        "seed": seed,
        "rows": len(rows),
        "matches": n_matches,
        "turnover": round(turnover, 2),
        "turnover_basis": turnover_basis,
        "jackpot": round(jackpot, 2),
        "kappa": round(kappa, 4),
        "kappa_by_tier": {str(c): round(v, 4)
                          for c, v in sorted(tier_kappa.items())} or None,
        "top_tier_kappa_by_x": {
            str(count): round(value, 4)
            for count, value in sorted(x_kappa.items())} or None,
        "cost": round(cost, 2),
        "mean_return": round(mean_return, 2),
        "net_ev": round(mean_return - cost, 2),
        "roi": round((mean_return - cost) / cost, 6),
        "stdev": round(stdev, 2),
        "mc_error_90": round(mc_error_90, 2),
        "probability_zero": round(probability_zero, 6),
        "probability_any_return": round(1.0 - probability_zero, 6),
        "probability_profit": round(probability_profit, 6),
        "percentiles": percentiles,
        "tier_returns": {str(correct): round(value, 2)
                         for correct, value in tier_returns.items()},
        "analytical_return": round(analytical_return, 2),
        "analytical_by_tier": {str(correct): round(value, 2)
                               for correct, value in analytical_by_tier.items()},
        "difference_vs_analytical": round(
            mean_return / analytical_return - 1.0, 6) if analytical_return else None,
        "top_tier": {
            "correct": top_tier,
            "analytical_return": round(analytical_by_tier[top_tier], 2),
            "poisson_exact_return": round(top_exact, 2),
            "difference": round(
                top_exact / analytical_by_tier[top_tier] - 1.0, 6
            ) if analytical_by_tier[top_tier] else None,
        },
        "own_competition_drag": round(own_drag, 2),
        "own_competition_drag_pct": round(
            own_drag / solo_return, 6) if solo_return else 0.0,
    }
