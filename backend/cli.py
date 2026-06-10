"""CLI för datainsamling och snabb analys utan att starta webservern.

Användning (från backend/ med aktiverat venv):
    python cli.py show              # visa analyserad aktuell omgång
    python cli.py spikar            # topp-spikar sorterade
    python cli.py snapshot          # hämta + spara snapshot i SQLite
    python cli.py history 4956 1 1  # oddshistorik draw=4956 event=1 sign=1
    python cli.py backtest 25 stryktipset  # kalibrera modellen mot facit

Tips: lägg 'snapshot' i en cron/launchd var 30:e min för att logga rörelse.
"""
from __future__ import annotations

import sys

from app.analysis import analyze_draw
from app.builder import (build_math_system, build_reduced_system,
                         build_guarantee_system, STRATEGIES)
from app import sharp_service
from app.storage import Storage
from app.svenskaspel import SvenskaSpel, PRODUCTS


def _fmt_odds(o):
    return f"{o:.2f}" if o is not None else "  -  "


def cmd_show(product: str) -> None:
    with SvenskaSpel() as ss:
        draw = ss.get_current_draw(product)
    if not draw:
        print("Ingen öppen omgång.")
        return
    a = analyze_draw(draw)
    print(f"\n{product.capitalize()} omgång {a.draw_number}  ({a.state})  "
          f"stänger {a.reg_close_time}\n")
    print(f"{'#':>2} {'Match':<28} {'1':>14} {'X':>14} {'2':>14}  Rekommendation")
    print("-" * 110)
    for m in a.matches:
        cells = []
        for s in ("1", "X", "2"):
            o = m.outcomes[s]
            mark = ""
            if "fallande_odds" in o.tags:
                mark += "↓"
            if "värdestreck" in o.tags:
                mark += "★"
            cells.append(f"{_fmt_odds(o.odds)}/{(str(o.streck)+'%') if o.streck is not None else '-'}{mark}")
        print(f"{m.event_number:>2} {m.description[:28]:<28} "
              f"{cells[0]:>14} {cells[1]:>14} {cells[2]:>14}  {m.recommendation}")
    print("\n★ = värdestreck   ↓ = fallande odds (stärks)\n")


def cmd_spikar(product: str) -> None:
    with SvenskaSpel() as ss:
        draw = ss.get_current_draw(product)
    a = analyze_draw(draw)
    print(f"\nSpik-ranking (omgång {a.draw_number}):\n")
    for m in a.spikar:
        fav = m.favourite or "?"
        p = f"{m.favourite_prob*100:.0f}%" if m.favourite_prob else "-"
        print(f"  spik {m.spik_score:5.1f} | öppen {m.open_score:5.1f} | "
              f"M{m.event_number:>2} {m.description[:30]:<30} fav {fav} ({p})")
    print()


def cmd_snapshot(product: str) -> None:
    """Snapshotta ALLA öppna omgångar för spelet (topptipset kan ha flera) +
    cacha Pinnacle sharp för var och en."""
    with SvenskaSpel() as ss:
        opens = ss.open_draws(product)
        if not opens:
            print(f"{product}: ingen öppen omgång — hoppar över.")
            return
        for summ in opens:
            dn = summ["draw_number"]
            draw = ss.get_draw(dn, product)
            store = Storage()
            try:
                rows = store.save_snapshot_if_changed(draw)
            finally:
                store.close()
            sharp_n = 0
            try:
                res = sharp_service.collect_pinnacle(product, draw=draw, cache=True)
                sharp_n = len(res["hits"]) if res else 0
            except Exception:  # noqa: BLE001
                sharp_n = -1
            print(f"{product} omg {dn}: {rows} ändrade rader, sharp {sharp_n} matcher.")


def cmd_history(args: list[str]) -> None:
    draw_n, event_n = int(args[0]), int(args[1])
    sign = args[2] if len(args) > 2 else None
    store = Storage()
    try:
        rows = store.history("stryktipset", draw_n, event_n, sign)
    finally:
        store.close()
    if not rows:
        print("Ingen historik ännu — kör 'snapshot' några gånger först.")
        return
    for r in rows:
        print(f"  {r['fetched_at']}  {r['sign']}  odds {_fmt_odds(r['odds'])}  "
              f"streck {r['streck']}%")


def _print_system(s) -> None:
    print(f"\n{s.system_type.capitalize()} system | strategi: {s.strategy} | "
          f"budget {s.budget:.0f} kr")
    print(f"  Rader: {s.num_rows}   Kostnad: {s.cost:.0f} kr   ({s.note or ''})")
    if s.rule:
        print(f"  Reduceringsvillkor: {s.rule}")
    print(f"\n  {'#':>2} {'Match':<26} {'Roll':<14} Tecken")
    print("  " + "-" * 60)
    for p in s.picks:
        print(f"  {p.event_number:>2} {p.description[:26]:<26} {p.role:<14} "
              f"{'  '.join(p.signs)}   ({p.reason})")
    print()


def cmd_system(args: list[str], product: str) -> None:
    # rad <strategi> <budget> [reducerat]
    strategy = next((a for a in args if a in STRATEGIES), "medel")
    budget = next((float(a) for a in args if a.replace('.', '', 1).isdigit()), 100.0)
    reduced = "reducerat" in args or "red" in args
    # garanti: arg som "g12" eller "g11"
    guarantee = next((int(a[1:]) for a in args if a.startswith("g") and a[1:].isdigit()), 0)
    with SvenskaSpel() as ss:
        draw = ss.get_current_draw(product)
    if not draw:
        print("Ingen öppen omgång.")
        return
    store = Storage()
    try:
        sharp = store.get_sharp("stryktipset", draw.draw_number)
        movement = store.movement("stryktipset", draw.draw_number)
    finally:
        store.close()
    a = analyze_draw(draw, sharp, movement)
    if reduced and guarantee:
        s = build_guarantee_system(a, strategy, budget, guarantee=guarantee)
    elif reduced:
        s = build_reduced_system(a, strategy, budget)
    else:
        s = build_math_system(a, strategy, budget)
    _print_system(s)


def cmd_backtest(rest: list[str], product: str) -> None:
    """Kalibrera modellen mot avgjorda omgångar: backtest [antal] [produkt].

    Mäter (a) träffsäkerhet per värde-bucket (slår 'värdestreck' folkets streck?),
    (b) kryss-bias, (c) vinnar-kalibrering: faktiska vinnare på toppnivån vs
    oberoende-antagandets prognos (fält × Π folk-streck på facit-raden)."""
    import math
    from app.analysis import _fair_probs
    count = next((int(a) for a in rest if a.isdigit()), 25)
    SIGNS = ("1", "X", "2")
    BUCKETS = (("värde (kvot ≥1.08)", 1.08, 99.0),
               ("neutral (0.92–1.08)", 0.92, 1.08),
               ("överspelat (≤0.92)", 0.0, 0.92))
    rows: dict[str, list] = {b[0]: [] for b in BUCKETS}
    xs, kappas, done = [], [], 0

    with SvenskaSpel() as ss:
        ds = ss.list_draws(product)
        nr = (min(d["draw_number"] for d in ds) - 1) if ds else None
        tried = 0
        while nr and done < count and tried < count * 3:
            tried += 1
            res = ss.get_result(product, nr)
            this = nr
            nr -= 1
            if not res or not res.get("outcomes"):
                continue
            try:
                d = ss.get_draw(this, product)
            except Exception:  # noqa: BLE001 — enstaka 500 från SvS, hoppa
                continue
            facit, skip = res["outcomes"], set(res.get("cancelled") or [])
            row_q, kappa_ok = 1.0, True
            for m in d.matches:
                if m.event_number in skip or m.event_number not in facit:
                    kappa_ok = False
                    continue
                f = facit[m.event_number]
                probs, src = _fair_probs(m.outcomes)
                # bucket-statistik bara där riktiga odds finns (alla matcher har streck,
                # men SvS sätter inte odds på alla — hoppa över de odds-lösa)
                if src == "odds":
                    for s in SIGNS:
                        p, st = probs[s], m.outcomes[s].streck
                        if p is None or not st:
                            continue
                        ratio = p / (st / 100.0)
                        for name, lo, hi in BUCKETS:
                            if lo <= ratio < hi:
                                rows[name].append((p, st / 100.0, 1.0 if s == f else 0.0))
                                break
                        if s == "X":
                            xs.append((p, st / 100.0, 1.0 if s == f else 0.0))
                qf = m.outcomes[f].streck
                row_q *= (qf / 100.0) if qf else (probs[f] or 1 / 3)
            top = next((t for t in res["tiers"] if t["correct"] == len(d.matches)), None)
            turn = res.get("turnover") or d.net_sale
            if kappa_ok and top and turn and top.get("winners") is not None:
                pred = (turn / (d.row_price or 1.0)) * row_q
                kappas.append((this, top["winners"], pred))
            done += 1
            print(f"  omg {this} klar ({done}/{count})", end="\r")

    print(f"\n=== Backtest {product}: {done} avgjorda omgångar ===")
    print(f"{'bucket':22} {'n':>6} {'modell-P':>9} {'folk-Q':>8} {'träff%':>8}")
    for name, *_ in BUCKETS:
        r = rows[name]
        if not r:
            continue
        n = len(r)
        print(f"{name:22} {n:6d} {sum(x[0] for x in r)/n*100:8.1f}% "
              f"{sum(x[1] for x in r)/n*100:7.1f}% {sum(x[2] for x in r)/n*100:7.1f}%")
    if xs:
        n = len(xs)
        print(f"\nKryss (X): modell {sum(x[0] for x in xs)/n*100:.1f}% · "
              f"folket {sum(x[1] for x in xs)/n*100:.1f}% · träffade {sum(x[2] for x in xs)/n*100:.1f}% (n={n})")
    if kappas:
        logs = [math.log((a + 1) / (p + 1)) for _, a, p in kappas]
        kappa = math.exp(sum(logs) / len(logs))
        print(f"\nVinnar-kalibrering toppnivån (n={len(kappas)}): "
              f"faktiska vinnare ≈ {kappa:.2f} × oberoende-prognosen.")
        print("  κ > 1 ⇒ folket klumpar ihop sig på folkrader mer än oberoende "
              "streck antyder (utdelningen på folkrader överskattas av modellen).")
        worst = sorted(kappas, key=lambda t: abs(math.log((t[1] + 1) / (t[2] + 1))), reverse=True)[:3]
        for nr_, a, p in worst:
            print(f"  omg {nr_}: faktiskt {a} vinnare vs prognos {p:.1f}")


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "show"
    valid = set(PRODUCTS)   # alla slugs inkl topptipsetstryk/-extra
    product = next((a for a in args[1:] if a in valid), "stryktipset")
    rest = [a for a in args[1:] if a not in valid]
    if cmd == "show":
        cmd_show(product)
    elif cmd == "spikar":
        cmd_spikar(product)
    elif cmd == "snapshot":
        cmd_snapshot(product)
    elif cmd == "history":
        cmd_history(rest)
    elif cmd in ("rad", "system"):
        cmd_system(rest, product)
    elif cmd == "backtest":
        cmd_backtest(rest, product)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
