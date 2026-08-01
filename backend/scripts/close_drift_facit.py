"""Close-drift-facit v1: förutspår våra signaler sharpens drift till close?

Förregistrering: docs/close-drift-facit-2026-07-26.md — läs den FÖRE
resultaten. Ren offline-läsning av prediction-ledgern; ingen runtime-ändring.

Körning: cd backend && .venv/bin/python -B scripts/close_drift_facit.py
"""
from __future__ import annotations

import pathlib
import random
import statistics
import sys
from typing import Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import oddset_ledger     # noqa: E402
from app.storage import Storage   # noqa: E402

MARKETS = ("1x2", "ah", "ou")
CHAIN = {"h3": "h24", "m20": "h3"}     # målhorisont -> prediktorkälla
DEAD_PP = 0.0025                       # |d| < 0,25 pp = flat
MOMENTUM_ACT = 0.005                   # |m| >= 0,5 pp aktiverar P1
WINSOR = 0.05                          # signerad drift ±5 pp
SEED, BOOT = 42, 2000
GATE_MIN_MATCHES = 30


def _rows(store: Storage, signal_version: Optional[str] = None) -> dict:
    """Läs exakt en sharp-regim; version ingår även i minnesnyckeln."""
    signal_version = (signal_version or
                      oddset_ledger.prediction_versions(store)["sharp"][
                          "signal_version"])
    out: dict[tuple, dict] = {}
    for r in store.conn.execute(
            "SELECT signal_version,match_id,market,line_key,sign,horizon,fair_prob, "
            "closing_fair, eligible, captured_at, match_start "
            "FROM oddset_prediction_log "
            "WHERE tier='sharp' AND fair_source='pinnacle' "
            "AND fair_available=1 AND fair_fresh=1 "
            "AND signal_version=? AND market IN (?,?,?)",
            (signal_version, *MARKETS)):
        out[(r["signal_version"], r["match_id"], r["market"],
             r["line_key"], r["sign"], r["horizon"])] = dict(r)
    return out


def _ci(values: list[tuple[str, float]], transform=lambda v: v):
    """Snitt + 90 % kluster-bootstrap (kluster = match)."""
    by_match: dict[str, list[float]] = {}
    for match_id, value in values:
        by_match.setdefault(match_id, []).append(transform(value))
    matches = sorted(by_match)
    mean = statistics.fmean(v for vs in by_match.values() for v in vs)
    rng = random.Random(SEED)
    boots = []
    for _ in range(BOOT):
        sample = [rng.choice(matches) for _ in matches]
        boots.append(statistics.fmean(
            v for m in sample for v in by_match[m]))
    boots.sort()
    return mean, boots[int(0.05 * BOOT)], boots[int(0.95 * BOOT)]


def _established_missing(store: Storage, match_id: str,
                         at: str) -> Optional[dict[str, int]]:
    """Etablerad frånvaro per sida enligt senaste capture ≤ at (PIT)."""
    cap = store.conn.execute(
        "SELECT captured_at,provider FROM oddset_absence_capture WHERE match_id=? "
        "AND captured_at<=? AND status='observed' "
        "ORDER BY confirmed DESC,captured_at DESC,"
        "CASE provider WHEN 'sofascore' THEN 0 WHEN 'flashscore' THEN 1 ELSE 2 END "
        "LIMIT 1",
        (match_id, at)).fetchone()
    if not cap:
        return None
    counts = {"home": 0, "away": 0}
    for side, appearances in store.conn.execute(
            "SELECT side, appearances FROM oddset_absence_player "
            "WHERE match_id=? AND captured_at=? AND provider=?",
            (match_id, cap[0], cap[1])):
        if side in counts and (appearances is None or appearances >= 5):
            counts[side] += 1
    return counts


def _report_cell(label: str, samples: list[tuple[str, float, float]]) -> None:
    """samples: (match_id, riktningsträff 0/1 på icke-flata, signerad drift)."""
    nonflat = [(m, hit) for m, hit, _ in samples if hit is not None]
    signed = [(m, drift) for m, _, drift in samples]
    matches = len({m for m, _, _ in samples})
    if not samples:
        print(f"  {label:<28} 0 aktiva")
        return
    line = f"  {label:<28} n={len(samples):>4} ({matches:>3} matcher)"
    if nonflat:
        hit, lo, hi = _ci(nonflat)
        gate = "GATE-PASS" if (lo > 0.5 and matches >= GATE_MIN_MATCHES) else ""
        line += (f" · träff {hit * 100:.1f} % [{lo * 100:.1f}..{hi * 100:.1f}]"
                 f" (flata borträknade: {len(samples) - len(nonflat)}) {gate}")
    if signed:
        mean, lo, hi = _ci(signed, transform=lambda v: max(-WINSOR, min(WINSOR, v)))
        line += (f" · drift i prediktorns riktning {mean * 100:+.2f} pp "
                 f"[{lo * 100:+.2f}..{hi * 100:+.2f}]")
    print(line)


def main() -> None:
    store = Storage()
    version = oddset_ledger.prediction_versions(store)["sharp"]["signal_version"]
    rows = _rows(store, version)
    total_active = 0

    print(f"Sharp-version: {version}")
    print("P1 MOMENTUM (fortsätter sharpens drift?)")
    for market in MARKETS:
        for target, source in CHAIN.items():
            samples, line_switch = [], 0
            for key, row in rows.items():
                row_version, match_id, mkt, line_key, sign, horizon = key
                if mkt != market or horizon != target:
                    continue
                if not row["eligible"] or row["closing_fair"] is None:
                    continue
                src = rows.get((row_version, match_id, mkt, line_key, sign,
                                source))
                if src is None:
                    # samma selektion saknas i källhorisonten (ofta linjebyte)
                    line_switch += 1
                    continue
                m = row["fair_prob"] - src["fair_prob"]
                if abs(m) < MOMENTUM_ACT:
                    continue
                d = row["closing_fair"] - row["fair_prob"]
                hit = None if abs(d) < DEAD_PP else float((d > 0) == (m > 0))
                signed = d if m > 0 else -d
                samples.append((match_id, hit, signed))
            total_active += len(samples)
            _report_cell(f"{market} {source}→{target}", samples)
            if line_switch:
                print(f"    ({line_switch} selektioner utan samma lina i "
                      f"källhorisonten — exkluderade)")

    print("P2 FRÅNVARO-NYHET (1X2, tecken 1/2; drift mot drabbat lag?)")
    for target, source in CHAIN.items():
        samples = []
        for key, row in rows.items():
            row_version, match_id, mkt, line_key, sign, horizon = key
            if mkt != "1x2" or horizon != target or sign not in ("1", "2"):
                continue
            if not row["eligible"] or row["closing_fair"] is None:
                continue
            src = rows.get((row_version, match_id, mkt, line_key, sign,
                            source))
            if src is None:
                continue
            before = _established_missing(store, match_id, src["captured_at"])
            after = _established_missing(store, match_id, row["captured_at"])
            if before is None or after is None:
                continue
            delta = {s: after[s] - before[s] for s in ("home", "away")}
            hit_side = [s for s in ("home", "away") if delta[s] > 0]
            if len(hit_side) != 1:
                continue           # ingen nyhet, eller båda sidor — exkluderas
            # frånvaro hemma => '1' förutspås falla (d<0) och '2' stiga (d>0)
            predicted_up = (hit_side[0] == "home") == (sign == "2")
            d = row["closing_fair"] - row["fair_prob"]
            hit = None if abs(d) < DEAD_PP else float((d > 0) == predicted_up)
            samples.append((match_id, hit, d if predicted_up else -d))
        total_active += len(samples)
        _report_cell(f"1x2 frånvaro {source}→{target}", samples)

    n_cor = store.conn.execute(
        "SELECT COUNT(*) FROM oddset_prediction_log WHERE tier='sharp' "
        "AND market='cor' AND closing_fair IS NOT NULL "
        "AND signal_version=?", (version,)).fetchone()[0]
    print(f"(hörnor: {n_cor} stängda rader — för tunt, ingår ej i v1)")
    print(f"SANITY: {total_active} aktiva selektioner totalt "
          f"({'PASS' if total_active >= 100 else 'SAMLAR — tolka inte'} "
          f"enligt förregistreringens krav ≥ 100)")
    store.close()


if __name__ == "__main__":
    main()
