"""CLI för datainsamling och snabb analys utan att starta webservern.

Användning (från backend/ med aktiverat venv):
    python cli.py show              # visa analyserad aktuell omgång
    python cli.py spikar            # topp-spikar sorterade
    python cli.py snapshot          # hämta + spara snapshot i SQLite
    python cli.py history 4956 1 1  # oddshistorik draw=4956 event=1 sign=1

Tips: lägg 'snapshot' i en cron/launchd var 30:e min för att logga rörelse.
"""
from __future__ import annotations

import sys

from app.analysis import analyze_draw
from app.builder import (build_math_system, build_reduced_system,
                         build_guarantee_system, STRATEGIES)
from app import sharp_service
from app.storage import Storage
from app.svenskaspel import SvenskaSpel


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
    with SvenskaSpel() as ss:
        draw = ss.get_current_draw(product)
    if not draw:
        print("Ingen öppen omgång — hoppar över.")
        return
    store = Storage()
    try:
        rows = store.save_snapshot_if_changed(draw)
        n = len(store.snapshot_times(product, draw.draw_number))
    finally:
        store.close()
    if rows:
        print(f"Sparade {rows} ändrade rader för omgång {draw.draw_number}. "
              f"Totalt {n} snapshot-tillfällen lagrade.")
    else:
        print(f"Inget ändrat för omgång {draw.draw_number} — inget sparat.")
    # uppdatera även Pinnacle sharp (gratis) så 1X2 fångas när de öppnas
    try:
        res = sharp_service.collect_pinnacle(product, draw=draw, cache=True)
        print(f"Pinnacle: {len(res['hits'])} matcher med 1X2 cachade.")
    except Exception as e:  # noqa: BLE001
        print(f"Pinnacle-hämtning hoppades över: {e}")


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


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "show"
    valid = {"stryktipset", "europatipset", "topptipset"}
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
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
