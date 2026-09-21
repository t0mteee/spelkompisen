"""Isolerat reduceringsexperiment. Ingen import från produktionens byggväg.

Girigt radval på marginalnytta för HELA kupongen: simulerad chans till
minst N, N−1, N−2 och N−3 rätt + en linjär EV-term. Fasta parametrar;
resultat, stängningsstreck och faktisk utdelning får inte ges till väljaren.
"""
import heapq
import math
import random

VERSION = "pool-portfolio-screen-v1"
SIGNS = ("1", "X", "2")
SAMPLES = 8192
SEED = 20260921
EV_FLOOR = 0.90
LEVEL_WEIGHTS = (0.4, 0.3, 0.2, 0.1)
EV_WEIGHT = 0.25


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
