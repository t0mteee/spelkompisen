"""Beslutspaket för konsensus-gaten: två ankare + multi-devig i EN läsning.

Kör den förregistrerade veckoutvärderingen ur docs/tva-ankare-2026-07-25.md
och kompletterar med devig-ablationens konsensusmått
(docs/devig-ablation-2026-07-26.md) på SAMMA kohort, plus coverage-kostnaden.
Skriptet BESLUTAR ingenting och ändrar ingenting — det gör beslutet färdigt
att ta när volymkravet nås. En eventuell promotion är en medveten
signal_version-bump (en bump för ankarkrav + devigkonsensus tillsammans).

Körning: cd backend && .venv/bin/python -B scripts/tva_ankare_beslut.py
Kadens: veckovis (EVAL_INTERVAL_H-principen) — inte varje varv.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from devig_ablation import (  # noqa: E402 — samma implementation, ingen kopia
    METHODS, _cluster_ci, _trio_at)
from app.oddset_ledger import PRIMARY_LEAGUES   # noqa: E402
from app.oddset_value import EDGE_LOG           # noqa: E402
from app.storage import Storage                 # noqa: E402

COHORT_START = "2026-07-25"      # anchor2-serien börjar här (förregistrerat)
N_REQUIRED = 50                  # mätta OCH stängda 1X2 i primärgruppen
PROMOTE_MARGIN = 0.010           # survives_both ≥ pinnacle_only + 1,0 pp


def main() -> None:
    store = Storage()
    rows = [dict(r) for r in store.conn.execute(
        "SELECT * FROM oddset_value_log WHERE tier='sharp' AND market='1x2' "
        "AND first_at>=? AND anchor2_fair IS NOT NULL AND anchor2_edge IS NOT NULL",
        (COHORT_START,))]
    primary = [r for r in rows if r["league"] in PRIMARY_LEAGUES]
    closed = [r for r in primary if r["closing_fair"] is not None
              and r["first_odds"]]
    days = max(1e-9, (dt.datetime.now(dt.timezone.utc)
                      - dt.datetime.fromisoformat(
                          COHORT_START + "T00:00:00+00:00")).total_seconds()
               / 86400)
    print(f"KOHORT (first_at ≥ {COHORT_START}, primärgruppens ligor): "
          f"{len(primary)} mätta, {len(closed)} mätta+stängda "
          f"(krav {N_REQUIRED}) · takt {len(primary) / days:.1f} mätta/dygn")
    if len(closed) < N_REQUIRED:
        eta = (N_REQUIRED - len(closed)) / max(0.1, len(closed) / days)
        print(f"STATUS: SAMLAR — beslut om tidigast ~{eta:.0f} dygn. "
              f"Talen nedan är läge, inte underlag.")

    def ev(subset):
        vals = [(r["match_id"], r["closing_fair"] * r["first_odds"] - 1)
                for r in subset]
        return _cluster_ci(vals) if vals else (None, None, None)

    both = [r for r in closed if r["anchor2_edge"] >= EDGE_LOG]
    pin_only = [r for r in closed if r["anchor2_edge"] < EDGE_LOG]
    for label, subset in (("survives_both", both), ("pinnacle_only", pin_only)):
        mean, lo, hi = ev(subset)
        matches = len({r["match_id"] for r in subset})
        if mean is None:
            print(f"  {label:<14} 0 flaggor")
        else:
            print(f"  {label:<14} {len(subset):>3} flaggor/{matches:>3} matcher"
                  f" · close-EV {mean * 100:+.2f} % "
                  f"[{lo * 100:+.2f}..{hi * 100:+.2f}]")

    # Multi-devig på SAMMA kohort (rekonstruerade trion, devig-ablationens metod)
    consensus, power_only, dropped = [], [], 0
    for r in closed:
        first = _trio_at(store, r["match_id"], r["first_at"])
        if not first:
            dropped += 1
            continue
        inv = {s: 1 / v for s, v in first.items()}
        edges = {name: fn(inv)[r["sign"]] * r["first_odds"] - 1
                 for name, fn in METHODS.items()}
        if all(e >= EDGE_LOG for e in edges.values()):
            consensus.append(r)
        elif edges["power"] >= EDGE_LOG and not any(
                e >= EDGE_LOG for n, e in edges.items() if n != "power"):
            power_only.append(r)
    print(f"  devigkonsensus  {len(consensus)}/{len(closed)} överlever alla "
          f"tre metoder ({dropped} orekonstruerbara), "
          f"bara-power {len(power_only)}")
    for label, subset in (("konsensus", consensus), ("bara-power", power_only)):
        mean, lo, hi = ev(subset)
        if mean is not None:
            print(f"  {label:<14} close-EV {mean * 100:+.2f} % "
                  f"[{lo * 100:+.2f}..{hi * 100:+.2f}]")

    # Coverage-kostnad: vad ett kombinerat filter hade kostat i flaggvolym
    combo = [r for r in consensus if r["anchor2_edge"] >= EDGE_LOG]
    if closed:
        print(f"  COVERAGE: ankarkrav behåller {len(both)}/{len(closed)} "
              f"({100 * len(both) / len(closed):.0f} %), devigkonsensus "
              f"{len(consensus)}/{len(closed)} "
              f"({100 * len(consensus) / len(closed):.0f} %), båda "
              f"{len(combo)}/{len(closed)} "
              f"({100 * len(combo) / len(closed):.0f} %)")

    # Förregistrerad beslutsregel (verkställs bara vid n ≥ krav)
    if len(closed) >= N_REQUIRED:
        both_mean, both_lo, _ = ev(both)
        pin_mean, _, _ = ev(pin_only)
        if both_mean is None or pin_mean is None:
            print("BESLUT: otolkbart — en grupp är tom; eskalera manuellt.")
        elif both_lo is not None and both_lo > 0 and \
                both_mean >= pin_mean + PROMOTE_MARGIN:
            print("BESLUT ENLIGT REGEL 1: PROMOTERA gaten (kräv båda ankarna)."
                  " Medveten signal_version-bump + rad i docs/db-atgarder.md;"
                  " ta devigkonsensus i SAMMA bump om konsensussiffrorna ovan"
                  " står sig.")
        elif both_mean is not None and pin_mean is not None and \
                max(both_mean, pin_mean) <= 0:
            print("BESLUT ENLIGT REGEL 3: ESKALERA — +EV replikerar inte i "
                  "kohorten; frågan är signalens existens, inte ankarvalet.")
        else:
            print("BESLUT ENLIGT REGEL 2: BEHÅLL ett ankare — skillnaden "
                  "är < 1,0 pp eller åt fel håll. Positivt: devigtvetydighet "
                  "förklarar inte edgen, och flaggvolymen halveras inte.")
    store.close()


if __name__ == "__main__":
    main()
