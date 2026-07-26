"""Close-drift-facit v2: reversering (forward), linjeflytt, frånvaro-bredd.

Förregistrering: docs/close-drift-facit-v2-2026-07-26.md — läs FÖRE resultat.
Ren offline-läsning; ingen runtime-ändring. Körs på veckokadens (a-spåret
ackumulerar forward-data och rapporterar SAMLAR tills ≥ 100 aktiva).

Körning: cd backend && .venv/bin/python -B scripts/close_drift_facit_v2.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from close_drift_facit import (  # noqa: E402 — samma estimand, ingen kopia
    CHAIN, DEAD_PP, MOMENTUM_ACT, _ci, _established_missing, _rows)
from app.storage import Storage   # noqa: E402

FORWARD_START = "2026-07-26T21:00:00Z"     # (a): kohort efter förregistreringen
GATE_MIN_MATCHES = 30


def _report(label: str, samples: list[tuple[str, float]], n_needed: int = 0,
            null_at: float = 0.5) -> None:
    matches = len({m for m, _ in samples})
    if not samples or (n_needed and len(samples) < n_needed):
        print(f"  {label:<30} n={len(samples)} — SAMLAR"
              + (f" (krav {n_needed})" if n_needed else ""))
        return
    hit, lo, hi = _ci(samples)
    gate = ("GATE-PASS" if lo > null_at and matches >= GATE_MIN_MATCHES
            else "")
    print(f"  {label:<30} n={len(samples):>4} ({matches:>3} matcher) · "
          f"{hit * 100:.1f} % [{lo * 100:.1f}..{hi * 100:.1f}] {gate}")


def main() -> None:
    store = Storage()
    rows = _rows(store)

    print(f"(a) REVERSERING — forward-kohort (captured_at > {FORWARD_START})")
    for market in ("ah", "ou", "1x2"):
        tag = "" if market != "1x2" else " (utforskande)"
        samples = []
        for key, row in rows.items():
            match_id, mkt, line_key, sign, horizon = key
            if mkt != market or horizon != "h3":
                continue
            if (row["captured_at"] <= FORWARD_START or not row["eligible"]
                    or row["closing_fair"] is None):
                continue
            src = rows.get((match_id, mkt, line_key, sign, "h24"))
            if src is None:
                continue
            m = row["fair_prob"] - src["fair_prob"]
            if abs(m) < MOMENTUM_ACT:
                continue
            d = row["closing_fair"] - row["fair_prob"]
            if abs(d) < DEAD_PP:
                continue
            samples.append((match_id, float((d > 0) != (m > 0))))  # reversering
        _report(f"{market} h24→h3 reversering{tag}", samples, n_needed=100)

    print("(b) LINJEFLYTT h24→h3 — fortsätter close-linan åt samma håll?")
    rep_sign = {"ah": "H", "ou": "O"}
    for market in ("ah", "ou"):
        cont, flat = [], 0
        seen: set[str] = set()
        for r in store.conn.execute(
                "SELECT t.match_id, s.line_key AS lk24, t.line_key AS lk3, "
                "t.line AS line3, t.closing_line AS cl "
                "FROM oddset_prediction_log t JOIN oddset_prediction_log s "
                "ON s.match_id=t.match_id AND s.market=t.market "
                "AND s.sign=t.sign AND s.horizon='h24' AND s.tier='sharp' "
                "AND s.fair_source='pinnacle' "
                "WHERE t.tier='sharp' AND t.fair_source='pinnacle' "
                "AND t.market=? AND t.sign=? AND t.horizon='h3' "
                "AND t.closing_line IS NOT NULL AND t.line IS NOT NULL "
                "AND t.line_key IS NOT NULL AND s.line_key IS NOT NULL "
                "AND s.line_key != t.line_key",
                (market, rep_sign[market])):
            if r["match_id"] in seen:
                continue           # en flytt per match × marknad
            seen.add(r["match_id"])
            move = r["lk3"] - r["lk24"]
            close_move = r["cl"] - r["line3"]
            if close_move == 0:
                flat += 1
                continue
            cont.append((r["match_id"],
                         float((close_move > 0) == (move > 0))))
        print(f"  {market}: {len(cont)} flyttade vidare till close, "
              f"{flat} stilla vid close")
        _report(f"{market} fortsättningsandel", cont)

    print("(c) FRÅNVARO, brett fönster (UTFORSKANDE — kräver forward-replikering)")
    for target, source in CHAIN.items():
        samples = []
        for key, row in rows.items():
            match_id, mkt, line_key, sign, horizon = key
            if mkt != "1x2" or horizon != target or sign not in ("1", "2"):
                continue
            if not row["eligible"] or row["closing_fair"] is None:
                continue
            base = store.conn.execute(
                "SELECT captured_at FROM oddset_absence_capture "
                "WHERE match_id=? AND captured_at>=datetime(?, '-72 hours') "
                "AND captured_at<=datetime(?, '-6 hours') "
                "ORDER BY captured_at ASC LIMIT 1",
                (match_id, row["match_start"], row["captured_at"])).fetchone()
            if not base:
                continue
            before = _established_missing(store, match_id, base[0])
            after = _established_missing(store, match_id, row["captured_at"])
            if before is None or after is None:
                continue
            delta = {s: after[s] - before[s] for s in ("home", "away")}
            hit_side = [s for s in ("home", "away") if delta[s] > 0]
            if len(hit_side) != 1:
                continue
            predicted_up = (hit_side[0] == "home") == (sign == "2")
            d = row["closing_fair"] - row["fair_prob"]
            if abs(d) < DEAD_PP:
                continue
            samples.append((match_id, float((d > 0) == predicted_up)))
        _report(f"1x2 frånvaro brett →{target}", samples)
    store.close()


if __name__ == "__main__":
    main()
