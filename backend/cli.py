"""CLI för datainsamling och snabb analys utan att starta webservern.

Användning (från backend/ med aktiverat venv):
    python cli.py show              # visa analyserad aktuell omgång
    python cli.py spikar            # topp-spikar sorterade
    python cli.py snapshot          # hämta + spara snapshot i SQLite
    python cli.py smart             # launchd-passet: oddset + poolspel med
                                    # snabbvarv nära avspark/spelstopp (A1)
    python cli.py oddset [light]    # ett oddset-varv (light = snabbvarvet)
    python cli.py v2audit [backfill] # PIT-dataset/coverage; backfill är ej promotion
    python cli.py history 4956 1 1  # oddshistorik draw=4956 event=1 sign=1
    python cli.py backtest 25 stryktipset  # kalibrera modellen mot facit

Launchd kör 'smart' var 30:e min (backend/scripts/snapshot.sh).
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


def cmd_snapshot(product: str) -> float | None:
    """Snapshotta ALLA öppna omgångar för spelet (topptipset kan ha flera) +
    cacha Pinnacle sharp + pusha ev. 🔥-notiser. Returnerar timmar till
    närmaste spelstopp (för den smarta förtätningen)."""
    import datetime as dt
    from app import notify, clv
    min_hrs: float | None = None
    with SvenskaSpel() as ss:
        opens = ss.open_draws(product)
        if not opens:
            # inga öppna omgångar — men lös ev. väntande CLV-facit för avgjorda
            store = Storage()
            try:
                clv.resolve(store, ss)
            finally:
                store.close()
            print(f"{product}: ingen öppen omgång — hoppar över.")
            return None
        for summ in opens:
            dn = summ["draw_number"]
            draw = ss.get_draw(dn, product)
            store = Storage()
            try:
                rows = store.save_snapshot_if_changed(draw)
                sharp_n = 0
                try:
                    res = sharp_service.collect_pinnacle(product, draw=draw, cache=True)
                    sharp_n = len(res["hits"]) if res else 0
                except Exception:  # noqa: BLE001
                    sharp_n = -1
                pushed = notify.check_movers(product, draw, store)
                clv.log_flags(product, draw, store)   # CLV-facit: logga gröna/sharp-flaggor
                clv.resolve(store, ss)                # + sätt stängning/facit där det går
            finally:
                store.close()
            if draw.reg_close_time:
                try:
                    close = dt.datetime.fromisoformat(draw.reg_close_time.replace("Z", "+00:00"))
                    if close.tzinfo is None:
                        close = close.replace(tzinfo=dt.timezone.utc)
                    hrs = (close - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
                    if hrs >= 0:
                        min_hrs = hrs if min_hrs is None else min(min_hrs, hrs)
                except (ValueError, TypeError):
                    pass
            extra = f", {pushed} notis(er)" if pushed else ""
            print(f"{product} omg {dn}: {rows} ändrade rader, sharp {sharp_n} matcher{extra}.")
    return min_hrs


# förtätning: när spelstopp närmar sig är sena oddsrörelser guld — snapshotta
# var 5:e minut i stället för launchd-intervallets var 30:e
DENSE_WITHIN_H = 2.0      # börja förtäta när någon omgång stänger inom 2 h
DENSE_SLEEP_S = 300       # 5 min mellan varven i tätläget
DENSE_BUDGET_S = 1500     # håll på i max 25 min, sedan tar nästa launchd-körning vid


def cmd_snapshot_smart(max_seconds: int = DENSE_BUDGET_S) -> None:
    """Snapshotta alla produkter; om någon öppen omgång stänger inom
    DENSE_WITHIN_H timmar: fortsätt var 5:e minut tills tidsbudgeten är slut."""
    import time
    start = time.time()
    while True:
        min_hrs: float | None = None
        for product in PRODUCTS:
            try:
                h = cmd_snapshot(product)
            except Exception as e:  # noqa: BLE001 — en produkt får inte stoppa resten
                print(f"{product}: FEL {e}")
                h = None
            if h is not None:
                min_hrs = h if min_hrs is None else min(min_hrs, h)
        if min_hrs is None or min_hrs > DENSE_WITHIN_H:
            break
        if time.time() - start + DENSE_SLEEP_S > max_seconds:
            break
        print(f"-- spelstopp om {min_hrs:.1f} h -> tätläge, ny mätning om {DENSE_SLEEP_S // 60} min --")
        time.sleep(DENSE_SLEEP_S)


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


def _winner_kappa(samples: list[tuple[int, float, float]],
                  confidence: float = 0.90,
                  bootstrap: int = 10_000,
                  seed: int = 20260716) -> tuple[float, float, float]:
    """Skatta faktisk/prognostiserad vinnartäthet med omgången som block.

    Under W_i ~ Poisson(kappa * lambda_i) är sum(W)/sum(lambda) MLE. En
    icke-parametrisk bootstrap över hela omgångar ger ett robustare intervall
    än Poisson-standardfel när poolspelarnas rader är överdispersa/klustrade.
    """
    import random

    valid = [(float(actual), float(predicted))
             for _, actual, predicted in samples
             if actual is not None and actual >= 0 and predicted > 0]
    if not valid:
        raise ValueError("κ kräver minst en omgång med positiv prognos.")
    estimate = sum(a for a, _ in valid) / sum(p for _, p in valid)
    if len(valid) == 1 or bootstrap <= 0:
        return estimate, estimate, estimate

    rng = random.Random(seed)
    n = len(valid)
    draws = []
    for _ in range(bootstrap):
        sample = [valid[rng.randrange(n)] for _ in range(n)]
        denom = sum(p for _, p in sample)
        if denom > 0:
            draws.append(sum(a for a, _ in sample) / denom)
    draws.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = draws[max(0, int(alpha * len(draws)))]
    hi = draws[min(len(draws) - 1, int((1.0 - alpha) * len(draws)))]
    return estimate, lo, hi


def cmd_backtest(rest: list[str], product: str) -> None:
    """Kalibrera modellen mot avgjorda omgångar: backtest [antal] [produkt].

    Mäter (a) träffsäkerhet per värde-bucket (slår 'värdestreck' folkets streck?),
    (b) kryss-bias, (c) vinnar-kalibrering: faktiska vinnare på toppnivån vs
    oberoende-antagandets prognos (fält × Π folk-streck på facit-raden)."""
    import httpx
    from app.analysis import _fair_probs
    count = next((int(a) for a in rest if a.isdigit()), 25)
    SIGNS = ("1", "X", "2")
    BUCKETS = (("värde (kvot ≥1.08)", 1.08, 99.0),
               ("neutral (0.92–1.08)", 0.92, 1.08),
               ("överspelat (≤0.92)", 0.0, 0.92))
    rows: dict[str, list] = {b[0]: [] for b in BUCKETS}
    xs, kappas, done = [], [], 0
    odds_matches = calibration_matches = 0

    with SvenskaSpel() as ss:
        ds = ss.list_draws(product)
        nr = (min(d["draw_number"] for d in ds) - 1) if ds else None
        tried = 0
        while nr and done < count and tried < count * 3:
            tried += 1
            try:
                res = ss.get_result(product, nr)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 509):
                    print(f"\n  Källans hastighetsgräns nådd efter {done} omgångar; "
                          "rapporterar delurvalet utan fler anrop.")
                    break
                raise
            this = nr
            nr -= 1
            if not res or not res.get("outcomes"):
                continue
            try:
                d = ss.get_draw(this, product)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 509):
                    print(f"\n  Källans hastighetsgräns nådd efter {done} omgångar; "
                          "rapporterar delurvalet utan fler anrop.")
                    break
                continue
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
                calibration_matches += 1
                # bucket-statistik bara där riktiga odds finns (alla matcher har streck,
                # men SvS sätter inte odds på alla — hoppa över de odds-lösa)
                if src == "odds":
                    odds_matches += 1
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
                if qf is None or qf <= 0:
                    kappa_ok = False
                else:
                    row_q *= qf / 100.0
            top = next((t for t in res["tiers"] if t["correct"] == len(d.matches)), None)
            turn = res.get("turnover") or d.net_sale
            if kappa_ok and top and turn and top.get("winners") is not None:
                pred = (turn / (d.row_price or 1.0)) * row_q
                kappas.append((this, top["winners"], pred))
            done += 1
            print(f"  omg {this} klar ({done}/{count})", end="\r")

    print(f"\n=== Backtest {product}: {done} avgjorda omgångar ===")
    coverage = odds_matches / calibration_matches if calibration_matches else 0.0
    print(f"Historisk odds-täckning: {odds_matches}/{calibration_matches} matcher "
          f"({coverage:.1%}).")
    if coverage < 0.80:
        print("  OBS: värde-/X-tabellen är endast diagnostik vid denna täckning; "
              "κ använder separata slutstreck och påverkas inte.")
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
        kappa, lo, hi = _winner_kappa(kappas)
        actual_total = sum(a for _, a, _ in kappas)
        predicted_total = sum(p for _, _, p in kappas)
        print(f"\nVinnar-kalibrering toppnivån (n={len(kappas)}): "
              f"κ̂={kappa:.2f}, 90 % blockbootstrap [{lo:.2f}..{hi:.2f}].")
        print(f"  Summa faktiska vinnare {actual_total:.0f} mot prognos "
              f"{predicted_total:.1f}; κ̂ = Σ faktiska / Σ prognos.")
        if len(kappas) < 30:
            print("  Under 30 kompletta omgångar ⇒ endast diagnostik, inget runtime-beslut.")
        elif lo <= 1.0 <= hi:
            print("  Intervallet innehåller 1,00 ⇒ ingen säker produktkorrektion ännu.")
        else:
            direction = "underskattar" if kappa > 1 else "överskattar"
            print(f"  Oberoendemodellen {direction} vinnartätheten systematiskt.")
        worst = sorted(kappas, key=lambda t: abs(t[1] - t[2]) / max(1.0, t[2]), reverse=True)[:3]
        for nr_, a, p in worst:
            print(f"  omg {nr_}: faktiskt {a} vinnare vs prognos {p:.1f}")


def cmd_fdbacktest(rest: list[str]) -> None:
    """Backtesta BESLUTSREGELN (grön kvot ≥1.08 / röd ≤0.92) mot football-data.co.uk.

    Översättning till fasta odds: Pinnacle (sharp, devigad med power) spelar
    rollen som 'marknaden' och B365 (soft, rekreationspengar) som 'folket'.
    Kvot = P_sharp / P_soft. Mäter träff% och ROI om man satsar 1 enhet till
    soft-oddset på gröna tecken — exakt analogen till att spela värdetecken."""
    import csv
    import io
    from pathlib import Path
    import httpx
    from app.analysis import _power_probs

    seasons = [a for a in rest if a.isdigit() and len(a) == 4] or ["2324", "2425"]
    divs = ("E0", "E1", "D1", "SP1", "I1", "F1")
    cache = Path("data/fd")
    cache.mkdir(parents=True, exist_ok=True)
    SIGNMAP = {"1": "H", "X": "D", "2": "A"}
    BUCKETS = (("grön (kvot ≥1.08)", 1.08, 99.0),
               ("neutral (0.92–1.08)", 0.92, 1.08),
               ("röd (≤0.92)", 0.0, 0.92))
    stats = {b[0]: {"n": 0, "hit": 0, "pnl": 0.0, "ps": 0.0, "pb": 0.0} for b in BUCKETS}
    matches = 0

    with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"},
                      follow_redirects=True) as client:
        for se in seasons:
            for dv in divs:
                f = cache / f"{se}_{dv}.csv"
                if not f.exists():
                    r = client.get(f"https://www.football-data.co.uk/mmz4281/{se}/{dv}.csv")
                    if r.status_code != 200:
                        print(f"  {se}/{dv}: kunde inte hämtas ({r.status_code})")
                        continue
                    f.write_bytes(r.content)
                for row in csv.DictReader(io.StringIO(f.read_text(errors="replace"))):
                    ftr = (row.get("FTR") or "").strip()
                    if ftr not in ("H", "D", "A"):
                        continue
                    # stängning mot stängning i första hand, annars pre-close-paret
                    def _odds(pre, close):
                        try:
                            o = {s: float(row.get(close.replace("?", k)) or 0)
                                 for s, k in SIGNMAP.items()}
                            if all(v > 1 for v in o.values()):
                                return o
                            o = {s: float(row.get(pre.replace("?", k)) or 0)
                                 for s, k in SIGNMAP.items()}
                            return o if all(v > 1 for v in o.values()) else None
                        except (ValueError, TypeError):
                            return None
                    sharp = _odds("PS?", "PSC?")
                    soft = _odds("B365?", "B365C?")
                    if not sharp or not soft:
                        continue
                    matches += 1
                    p_sharp = _power_probs({s: 1.0 / o for s, o in sharp.items()})
                    p_soft = _power_probs({s: 1.0 / o for s, o in soft.items()})
                    for s in ("1", "X", "2"):
                        ratio = p_sharp[s] / p_soft[s] if p_soft[s] else None
                        if not ratio:
                            continue
                        for name, lo, hi in BUCKETS:
                            if lo <= ratio < hi:
                                st = stats[name]
                                won = SIGNMAP[s] == ftr
                                st["n"] += 1
                                st["hit"] += won
                                st["pnl"] += (soft[s] - 1.0) if won else -1.0
                                st["ps"] += p_sharp[s]
                                st["pb"] += p_soft[s]
                                break

    print(f"\n=== football-data-backtest: {matches} matcher "
          f"({', '.join(seasons)} · {', '.join(divs)}) ===")
    print("Satsar 1 enhet till SOFT-oddset (B365) på varje tecken i bucketen:")
    print(f"{'bucket':22} {'n':>6} {'sharp-P':>8} {'soft-P':>8} {'träff%':>7} {'ROI':>8}")
    for name, *_ in BUCKETS:
        st = stats[name]
        if not st["n"]:
            continue
        print(f"{name:22} {st['n']:6d} {st['ps']/st['n']*100:7.1f}% "
              f"{st['pb']/st['n']*100:7.1f}% {st['hit']/st['n']*100:6.1f}% "
              f"{st['pnl']/st['n']*100:+7.1f}%")
    print("\nTolkning: neutral-bucketens ROI ≈ bokens marginal (baslinjen, ca −5 till −7 %)."
          "\nGrön klart över baslinjen + träff% över soft-P = beslutsregeln hittar riktigt"
          "\nvärde; röd klart under = överspelade tecken är gift. I poolspel finns ingen"
          "\nbokmarginal att äta upp — där räcker det att slå folket.")


def cmd_modeldata() -> None:
    """Tvinga uppdatering av modellens dataunderlag (resultat/xG/Elo) + visa fit
    och identitets-granskningen (namn som inte kanoniserats, kvarvarande
    datum-dubbletter) — förslag i stället för tysta beslut."""
    from app import oddset_data, oddset_model
    store = Storage()
    try:
        rep = oddset_data.refresh_all(store, force=True)
        print("data:", rep)
        for lg in sorted(oddset_data.MODEL_LEAGUES):
            audit: dict = {}
            res = oddset_data.merged_results(store, lg, audit=audit)
            n_xg = sum(1 for r in res if r.get("xg_h") is not None)
            fit = oddset_model.fit_league(res)
            print(f"{lg}: {len(res)} resultat ({n_xg} med xG)", end="")
            if fit:
                top = sorted(fit["teams"].items(),
                             key=lambda kv: -kv[1]["att"] / kv[1]["def"])[:3]
                print(f" · hemmafördel {fit['home_adv']} · bäst: "
                      + ", ".join(f"{t} (a{v['att']}/f{v['def']})" for t, v in top))
            else:
                print(" · för lite data för fit")
            for link in audit.get("fuzzy_links", []):
                print(f"    ⚠ overifierad fuzzy-länk: '{link['source_name']}' → "
                      f"'{link['target_name']}' (likhet {link['sim']}, "
                      f"{link['matches']} matcher, verified={link['verified']}) "
                      f"→ lägg i TEAM_ALIAS/meta oddset_alias:{lg} efter kontroll")
            for link in audit.get("rejected_links", []):
                print(f"    ✗ verifierat skilda lag: '{link['source_name']}' ≠ "
                      f"'{link['target_name']}' (likhet {link['sim']}, "
                      f"{link['matches']} matcher, verified={link['verified']})")
            for u in audit.get("unmatched", []):
                print(f"    ⚠ okopplat namn: '{u['name']}' — förslag '{u['suggestion']}' "
                      f"(likhet {u['sim']}, {u.get('matches', 1)} matcher) "
                      f"→ lägg i TEAM_ALIAS/meta oddset_alias:{lg} efter kontroll")
            for d in audit.get("date_dups", []):
                print(f"    ⚠ datum-dubblett kvar: {d['pair']} {d['dates']} ({d['note']})")
    finally:
        store.close()


def _print_oddset_report(rep: dict) -> None:
    for key, st in rep["leagues"].items():
        print(f"{key:14} pinnacle={st['pinnacle']:3d} kambi={st['kambi']:3d} "
              f"nya rader={st['saved_rows']}")
    v = rep.get("value")
    if v:
        gated = f", {v['gated']} stoppade av notisvakten" if v.get("gated") else ""
        print(f"värde: {v.get('logged', 0)} loggade, {v.get('pushed', 0)} pushade, "
              f"{v.get('closings', 0)} stängda{gated}")
    for err in rep["errors"]:
        print(f"  ⚠ {err}")


def cmd_oddset(deep: bool = True) -> float | None:
    """Hämta odds för Oddset-ligorna (Pinnacle + Kambi + sidoböcker).
    deep=False = snabbvarv (A1): bara ligor med avspark inom snabbfönstret,
    Pinnacle + böckernas 1X2 + SvS-deep för 3h-matcherna. Returnerar timmar
    till nästa avspark."""
    from app import oddset
    store = Storage()
    try:
        leagues = None if deep else oddset.fast_leagues(store)
        if not deep and not leagues:
            return oddset.hours_to_next_start(store)
        rep = oddset.collect(store, leagues=leagues, deep=deep)
        _print_oddset_report(rep)
        return oddset.hours_to_next_start(store)
    finally:
        store.close()


def cmd_smart(max_seconds: int = DENSE_BUDGET_S) -> None:
    """Ett launchd-pass (backlog A1): fullt oddset-varv + poolspels-snapshots,
    därefter snabbvarv var 4:e min så länge någon oddset-match startar inom
    FAST_WITHIN_H (Pinnacle + bok-1X2 + SvS-deep för 3h-matcher) och/eller
    tätvarv var 5:e min när ett poolspel stänger inom DENSE_WITHIN_H — tills
    tidsbudgeten (~25 min) är slut och nästa launchd-körning tar vid."""
    import time
    from app import oddset
    start = time.time()
    try:
        odd_h = cmd_oddset(deep=True)
    except Exception as e:  # noqa: BLE001
        print(f"oddset: FEL {e}")
        odd_h = None
    odd_at = time.time()

    def _pools() -> float | None:
        mh = None
        for product in PRODUCTS:
            try:
                h = cmd_snapshot(product)
            except Exception as e:  # noqa: BLE001 — en produkt får inte stoppa resten
                print(f"{product}: FEL {e}")
                h = None
            if h is not None:
                mh = h if mh is None else min(mh, h)
        return mh

    pool_h = _pools()
    pool_at = time.time()

    while True:
        # klockan tickar mellan varven — räkna ner utan nya anrop
        odd_left = None if odd_h is None else odd_h - (time.time() - odd_at) / 3600
        pool_left = None if pool_h is None else pool_h - (time.time() - pool_at) / 3600
        odd_hot = odd_left is not None and odd_left <= oddset.FAST_WITHIN_H
        pool_hot = pool_left is not None and 0 <= pool_left <= DENSE_WITHIN_H
        if not odd_hot and not pool_hot:
            break
        sleep_s = oddset.FAST_SLEEP_S if odd_hot else DENSE_SLEEP_S
        if time.time() - start + sleep_s > max_seconds:
            break
        why = " + ".join((["avspark om %.1f h" % odd_left] if odd_hot else [])
                         + (["spelstopp om %.1f h" % pool_left] if pool_hot else []))
        print(f"-- {why} -> nytt varv om {sleep_s // 60} min --")
        time.sleep(sleep_s)
        if odd_hot:
            try:
                odd_h = cmd_oddset(deep=False)
            except Exception as e:  # noqa: BLE001
                print(f"oddset: FEL {e}")
            odd_at = time.time()
        if pool_hot:
            pool_h = _pools()
            pool_at = time.time()


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
    elif cmd == "snapshot-smart":
        secs = next((int(a) for a in rest if a.isdigit()), None)
        cmd_snapshot_smart(secs if secs is not None else 1500)
    elif cmd == "history":
        cmd_history(rest)
    elif cmd in ("rad", "system"):
        cmd_system(rest, product)
    elif cmd == "backtest":
        cmd_backtest(rest, product)
    elif cmd == "fdbacktest":
        cmd_fdbacktest(rest)
    elif cmd == "oddset":
        cmd_oddset(deep="light" not in rest)
    elif cmd == "smart":
        secs = next((int(a) for a in rest if a.isdigit()), None)
        cmd_smart(secs if secs is not None else DENSE_BUDGET_S)
    elif cmd == "modeldata":
        cmd_modeldata()
    elif cmd == "v2audit":
        from app import oddset_v2
        store = Storage()
        try:
            if "backfill" in rest:
                print("features:", oddset_v2.backfill_features(store))
            print(oddset_v2.format_audit(oddset_v2.audit(store)))
        finally:
            store.close()
    elif cmd == "oddsetbacktest":
        import json as _json
        from app import oddset_backtest
        use_xg = "xg" in rest
        pool = "pool" in rest
        lgs = [a for a in (rest or []) if a not in ("xg", "pool")] \
            or ["allsvenskan", "eliteserien"]
        store = Storage()
        try:
            temperatures = {}
            for lg in lgs:
                try:
                    temperatures[lg] = float(_json.loads(
                        store.meta_get(f"oddset_cal:{lg}") or "{}"
                    ).get("t") or 1.0)
                except (ValueError, TypeError):
                    temperatures[lg] = 1.0
        finally:
            store.close()
        for lg in lgs:
            extra = ("superettan",) if pool and lg == "allsvenskan" else ()
            preds = oddset_backtest.run_league(lg, use_store_xg=use_xg,
                                               pool_extra=extra)
            tag = (" +xG" if use_xg else "") + (" +pool" if extra else "")
            oddset_backtest.print_report(
                lg + tag, oddset_backtest.report(
                    preds, temperature=temperatures[lg]))
    elif cmd == "oddsetcalibrate":
        import datetime as _dt
        import json as _json
        from app import oddset_backtest
        store = Storage()
        try:
            for lg, extra in (("allsvenskan", ("superettan",)), ("eliteserien", ())):
                preds = oddset_backtest.run_league(lg, use_store_xg=True,
                                                   pool_extra=extra)
                t, ll, ll1 = oddset_backtest.fit_temperature(preds)
                store.meta_set(f"oddset_cal:{lg}", _json.dumps(
                    {"t": t, "logloss": ll, "logloss_t1": ll1, "n": len(preds),
                     "at": _dt.datetime.now(_dt.timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ")}))
                print(f"{lg}: T={t} (logloss {ll} vs {ll1} vid T=1, n={len(preds)}) — sparad")
        finally:
            store.close()
    elif cmd == "xgbackfill":
        from app import oddset_data
        store = Storage()
        try:
            print("backfill:", oddset_data.xg_backfill(store))
        finally:
            store.close()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
