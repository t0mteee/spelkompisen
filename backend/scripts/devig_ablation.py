"""Devig-ablation: power vs proportionell vs Shin på loggade sharp-1X2-flaggor.

Förregistrering och måttdefinitioner: docs/devig-ablation-2026-07-26.md —
läs den FÖRE resultaten. Ingen runtime-ändring; ren offline-läsning.

Körning: cd backend && .venv/bin/python -B scripts/devig_ablation.py
"""
from __future__ import annotations

import math
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.analysis import _power_probs   # noqa: E402 — ingen tredje kopia
from app.storage import Storage         # noqa: E402

SIGNS = ("1", "X", "2")
EDGE_LOG = 0.02
WINSOR = 0.20
SEED = 42
BOOT = 2000


def _proportional(inv: dict[str, float]) -> dict[str, float]:
    total = sum(inv.values())
    return {s: v / total for s, v in inv.items()}


def _shin(inv: dict[str, float]) -> dict[str, float]:
    booksum = sum(inv.values())

    def probs(z: float) -> dict[str, float]:
        return {s: (math.sqrt(z * z + 4 * (1 - z) * v * v / booksum) - z)
                / (2 * (1 - z)) for s, v in inv.items()}

    lo, hi = 0.0, 0.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if sum(probs(mid).values()) > 1.0:
            lo = mid
        else:
            hi = mid
    out = probs((lo + hi) / 2)
    total = sum(out.values())
    return {s: v / total for s, v in out.items()}


METHODS = {"power": _power_probs, "proportionell": _proportional, "shin": _shin}


def _trio_at(store: Storage, match_id: str, at: str) -> dict[str, float] | None:
    """Pinnacles 1X2-trio som den såg ut vid `at` (sista ändring ≤ at)."""
    trio = {}
    for sign in SIGNS:
        row = store.conn.execute(
            "SELECT odds FROM oddset_odds WHERE match_id=? AND source='pinnacle' "
            "AND market='1x2' AND sign=? AND fetched_at<=? "
            "ORDER BY fetched_at DESC LIMIT 1", (match_id, sign, at)).fetchone()
        if not row or not row[0]:
            return None
        trio[sign] = float(row[0])
    return trio


def _winsor(x: float) -> float:
    return max(-WINSOR, min(WINSOR, x))


def _cluster_ci(values: list[tuple[str, float]]) -> tuple[float, float, float]:
    """Winsoriserat snitt + 90 % kluster-bootstrap-KI (kluster = match)."""
    by_match: dict[str, list[float]] = {}
    for match_id, value in values:
        by_match.setdefault(match_id, []).append(_winsor(value))
    matches = sorted(by_match)
    mean = statistics.fmean(v for vs in by_match.values() for v in vs)
    rng = random.Random(SEED)
    boots = []
    for _ in range(BOOT):
        sample = [rng.choice(matches) for _ in matches]
        flat = [v for m in sample for v in by_match[m]]
        boots.append(statistics.fmean(flat))
    boots.sort()
    return mean, boots[int(0.05 * BOOT)], boots[int(0.95 * BOOT)]


def main() -> None:
    store = Storage()
    rows = [dict(r) for r in store.conn.execute(
        "SELECT match_id, sign, first_at, first_odds, first_fair, "
        "closing_fair, match_start FROM oddset_value_log "
        "WHERE tier='sharp' AND market='1x2' AND closing_fair IS NOT NULL "
        "AND first_odds IS NOT NULL")]
    cohort, dropped = [], 0
    for r in rows:
        first = _trio_at(store, r["match_id"], r["first_at"])
        close = _trio_at(store, r["match_id"], r["match_start"])
        if not first or not close:
            dropped += 1
            continue
        cohort.append({**r, "trio_first": first, "trio_close": close})
    print(f"kohort: {len(cohort)} flaggor ({dropped} exkluderade — trio "
          f"orekonstruerbar), {len({c['match_id'] for c in cohort})} matcher")

    # 1) Sanity-grind: rekonstruerad power-first mot lagrad first_fair
    diffs = []
    for c in cohort:
        inv = {s: 1 / v for s, v in c["trio_first"].items()}
        diffs.append(abs(_power_probs(inv)[c["sign"]] - (c["first_fair"] or 0)))
    diffs.sort()
    median = diffs[len(diffs) // 2] if diffs else float("nan")
    print(f"sanity: median |rekonstruerad − lagrad first_fair| = "
          f"{median * 100:.3f} pp ({'PASS' if median < 0.005 else 'FAIL'})")
    if median >= 0.005:
        print("SANITY FALLERAR — tolka inget nedan.")

    # 2+3) Överlevnad + close-EV per metod
    survives: dict[str, set[int]] = {name: set() for name in METHODS}
    for name, fn in METHODS.items():
        close_ev = []
        for i, c in enumerate(cohort):
            inv_f = {s: 1 / v for s, v in c["trio_first"].items()}
            inv_c = {s: 1 / v for s, v in c["trio_close"].items()}
            edge = fn(inv_f)[c["sign"]] * c["first_odds"] - 1
            if edge >= EDGE_LOG:
                survives[name].add(i)
            close_ev.append((c["match_id"],
                             fn(inv_c)[c["sign"]] * c["first_odds"] - 1))
        mean, lo, hi = _cluster_ci(close_ev)
        print(f"{name:<13} överlever {len(survives[name]):>3}/{len(cohort)} "
              f"({100 * len(survives[name]) / len(cohort):.0f} %) · "
              f"close-EV alla: {mean * 100:+.2f} % "
              f"[{lo * 100:+.2f}..{hi * 100:+.2f}]")

    # 4) Huvudjämförelse: överlever-alla mot bara-power (power-estimanden)
    all_three = survives["power"] & survives["proportionell"] & survives["shin"]
    power_only = survives["power"] - survives["proportionell"] - survives["shin"]

    def _close_power(idx: set[int]) -> list[tuple[str, float]]:
        out = []
        for i in idx:
            c = cohort[i]
            inv_c = {s: 1 / v for s, v in c["trio_close"].items()}
            out.append((c["match_id"],
                        _power_probs(inv_c)[c["sign"]] * c["first_odds"] - 1))
        return out

    for label, idx in (("överlever alla tre", all_three),
                       ("bara power", power_only)):
        if not idx:
            print(f"{label}: 0 flaggor")
            continue
        mean, lo, hi = _cluster_ci(_close_power(idx))
        print(f"{label}: {len(idx)} flaggor "
              f"({len({cohort[i]['match_id'] for i in idx})} matcher) · "
              f"close-EV {mean * 100:+.2f} % [{lo * 100:+.2f}..{hi * 100:+.2f}]")
    store.close()


if __name__ == "__main__":
    main()
