"""Fryst reduceringsexperiment; enbart explicit testval, aldrig standard.

Girigt radval på marginalnytta för HELA kupongen: simulerad chans till
minst N, N−1, N−2 och N−3 rätt + en linjär EV-term. Fasta parametrar;
resultat, stängningsstreck och faktisk utdelning får inte ges till väljaren.
"""
import heapq
import math
import random
import threading

VERSION = "pool-portfolio-screen-v1"
SIGNS = ("1", "X", "2")
SAMPLES = 8192
SEED = 20260921
EV_FLOOR = 0.90
LEVEL_WEIGHTS = (0.4, 0.3, 0.2, 0.1)
EV_WEIGHT = 0.25
MANUAL_LOCK = threading.Lock()


def prepare(analysis, budget, row_price, value_weight, plan, jackpot):
    """Gemensam väljare för offline-replay och manuellt experimentval."""
    from . import builder
    if not analysis.matches or any(
            m.outcomes[s].fair_prob is None or m.outcomes[s].streck is None
            or m.outcomes[s].odds is None or m.outcomes[s].odds <= 1
            for m in analysis.matches for s in SIGNS):
        raise ValueError("Täckningstestet kräver kompletta SvS-odds och streck.")
    ranked = builder._rank_ev_rows(analysis, budget, row_price, value_weight,
                                  plan, jackpot, full_universe=budget >= 20000)
    baseline = builder._select_draw_risk_rows(analysis, ranked, True)
    raw = [[m.outcomes[s].fair_prob for s in SIGNS] for m in analysis.matches]
    probabilities = [[p / sum(ps) for p in ps] for ps in raw]
    extra = set()
    for row in sample_outcomes(probabilities, 1024, SEED+2):
        extra.add(row)
        for col in range(len(row)):
            for sign in SIGNS:
                extra.add(row[:col]+(sign,)+row[col+1:])
    existing = {r[2] for r in ranked.rows}
    pools = builder._prize_pools(analysis.turnover, plan, jackpot)
    candidates = list(ranked.rows)
    for row in sorted(extra-existing):
        ps = [raw[c][SIGNS.index(s)] for c,s in enumerate(row)]
        qs = [max((m.outcomes[s].streck or 0)/100,.001)
              for m,s in zip(analysis.matches,row)]
        ev = builder._row_expected_value(builder._poisson_binomial(ps),
            builder._poisson_binomial(qs),pools,analysis.turnover/row_price,analysis.product)
        candidates.append((math.prod(ps)**ranked.exponent*ev,ev,row))
    floors = {(i,"X"):builder.draw_risk_context(m)["minimum_x_share"]
              for i,m in enumerate(analysis.matches) if builder.draw_risk_context(m)["protected"]}
    chosen,audit = select_portfolio(candidates,baseline,probabilities,minimum_shares=floors)
    return ranked,baseline,chosen,audit,probabilities


def build_manual_test(analysis, strategy, budget, row_price, value_weight, plan, jackpot):
    from . import builder
    if (not math.isfinite(budget) or not 1 <= budget <= 512
            or len(analysis.matches) not in (8,13) or not plan
            or not analysis.turnover or analysis.turnover <= 0):
        raise ValueError("Täckningstest v1 kräver 8/13 matcher, omsättning och 1–512 kr.")
    ranked,baseline,chosen,audit,probabilities = prepare(
        analysis,budget,row_price,value_weight,plan,jackpot)
    system = builder._ev_system_from_rows(analysis,strategy,budget,row_price,jackpot,ranked,chosen)
    system.rule = ("Experiment: raderna väljs för kupongens samlade täckning av full pott "
                   "och upp till tre färre rätt, med ett rad-EV-golv. Kan sänka chansen "
                   "till full pott. Inte visat bättre lönsamhet än Standard.")
    system.note = ("Skyddet slog till: standardrader används ("+", ".join(audit["fallback"])+")."
                   if audit["fallback"] else "Täckningstest v1 · experiment, inte rekommenderad standard.")
    def top(rows):
        return sum(math.prod(probabilities[c][SIGNS.index(s)] for c,s in enumerate(r[2]))
                   for r in rows)
    audit.update(baseline_top_chance=top(baseline),selected_top_chance=top(chosen),
                 comparison="beräknat med samma matchsannolikheter, inte uppmätt resultat")
    return system,audit


def sample_outcomes(probabilities, count, seed):
    rng = random.Random(seed)
    if count < 1 or not probabilities:
        raise ValueError("tom simulering")
    for p in probabilities:
        if len(p) != 3 or any(not math.isfinite(x) or x < 0 for x in p) or abs(sum(p) - 1) > 1e-6:
            raise ValueError("ogiltiga sannolikheter")
    return [tuple(rng.choices(SIGNS, weights=p, k=1)[0] for p in probabilities)
            for _ in range(count)]


def _sample_index(samples):
    n = len(samples[0])
    masks = [{s: 0 for s in SIGNS} for _ in range(n)]
    for i, row in enumerate(samples):
        for col, sign in enumerate(row):
            masks[col][sign] |= 1 << i
    return masks, (1 << len(samples)) - 1


def _coverage(row, masks, all_bits, radius):
    # Bitset-DP: scenarier med exakt 0..radius fel; sedan kumulativt.
    counts = [all_bits] + [0] * radius
    for col, sign in enumerate(row):
        hit = masks[col][sign]
        miss = all_bits ^ hit
        counts = [counts[0] & hit] + [
            (counts[k] & hit) | (counts[k - 1] & miss)
            for k in range(1, radius + 1)]
    cumulative = 0
    result = []
    for bits in counts:
        cumulative |= bits
        result.append(cumulative)
    return tuple(result)


def evaluate_coverage(rows, probabilities, count=16384, seed=SEED + 1):
    samples = sample_outcomes(probabilities, count, seed)
    masks, all_bits = _sample_index(samples)
    radius = min(3, len(probabilities) - 1)
    covered = [0] * (radius + 1)
    for row in rows:
        for k, bits in enumerate(_coverage(row, masks, all_bits, radius)):
            covered[k] |= bits
    return {len(probabilities) - k: bits.bit_count() / count
            for k, bits in enumerate(covered)}


def select_portfolio(candidates, baseline, probabilities, *, seed=SEED,
                     samples=SAMPLES, minimum_shares=None):
    """candidates = (score, analytisk rad-EV, tecken). Retur (rader, audit).

    Samma antal unika rader som baseline. Underskrids 90 % av referensens
    summerade rad-EV eller befintliga teckengolv återgår HELA armen till
    referensen, och detta redovisas. EV-golvet är ett skydd, ingen ROI-garanti.
    """
    base_rows = [tuple(item[2]) for item in baseline]
    if not base_rows or len(set(base_rows)) != len(base_rows):
        raise ValueError("referensen måste innehålla unika rader")
    n = len(probabilities)
    if any(len(r) != n or any(s not in SIGNS for s in r) for r in base_rows):
        raise ValueError("ogiltig referensrad")
    by_row = {}
    for score, ev, row in [*candidates, *baseline]:
        row = tuple(row)
        if len(row) != n or any(s not in SIGNS for s in row) or not math.isfinite(ev) or ev < 0:
            raise ValueError("ogiltig kandidatrad")
        by_row[row] = (score, ev, row)
    ranked = sorted(by_row.values(), key=lambda v: (-v[0], v[2]))
    masks, all_bits = _sample_index(sample_outcomes(probabilities, samples, seed))
    radius = min(3, n - 1)
    covered = [0] * (radius + 1)
    base_ev = sum(v[1] for v in baseline)
    coverage = [_coverage(v[2], masks, all_bits, radius) for v in ranked]

    def gain(i):
        return (EV_WEIGHT * ranked[i][1] / max(base_ev, 1e-12)
                + sum(LEVEL_WEIGHTS[k] * (bits & ~covered[k]).bit_count() / samples
                      for k, bits in enumerate(coverage[i])))

    # Lazy greedy: gammal marginalnytta är en övre gräns när unionen växer.
    heap = [(-gain(i), i, 0) for i in range(len(ranked))]
    heapq.heapify(heap)
    chosen = []
    while len(chosen) < len(base_rows):
        _, i, stamp = heapq.heappop(heap)
        if stamp != len(chosen):
            heapq.heappush(heap, (-gain(i), i, len(chosen)))
            continue
        chosen.append(ranked[i])
        for k, bits in enumerate(coverage[i]):
            covered[k] |= bits
    reasons = []
    candidate_ev = sum(v[1] for v in chosen)
    if candidate_ev < EV_FLOOR * base_ev:
        reasons.append("EV-golv")
    for (col, sign), share in (minimum_shares or {}).items():
        if sum(v[2][col] == sign for v in chosen) < math.ceil(len(chosen) * share):
            reasons.append(f"teckengolv match {col + 1}")
    if reasons:
        chosen = baseline
    return chosen, {"version": VERSION, "seed": seed, "samples": samples,
                    "candidates": len(ranked), "fallback": reasons,
                    "baseline_row_ev": base_ev, "candidate_row_ev_before_guard": candidate_ev,
                    "selected_row_ev": sum(v[1] for v in chosen),
                    "changed_rows": len(set(v[2] for v in chosen) - set(base_rows))}
