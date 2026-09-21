#!/usr/bin/env python3
"""Read-only täckningsrapport för poolens sharp-serier: pit-v4 (1X2) och
pit-total-v1 (Ö/U). Svarar på frågan ur planen 2026-09-13 (del A): VAR och
VARFÖR saknar poolmatcher Pinnacle vid frysningarna, och löser den senare
20-minutersobservationen luckorna från 180 min på SAMMA omgångar?

Felklasser för 1X2 som aldrig får blandas (`total_eligible=0` och "ingen
rad" är olika saker, precis som här):

  ok              sharp_eligible=1 i pit-v4 vid horisonten.
  aldrig_matchad  vi frågade Pinnacle vid as-of, matcharen hittade ingen match,
                  och hittade aldrig någon före spelstopp heller. Antingen
                  listade Pinnacle inte matchen, eller så fällde poolmatcharen
                  (`pinnacle.match`) ett korrekt par. Rapporten spelar upp
                  matcharen OFFLINE mot Oddset-sidans sparade Pinnacle-namn
                  (`oddset_matches`, `pin:`-rader) för att skilja de två.
  listad_sent     not_listed vid as-of men matchad senare, före spelstopp.
  tvetydig        flera kandidater/orienteringar; inga odds kopplas (pool-name-v2).
  ingen_1x2       Pinnacle listade matchen men utan moneyline.
  capture_sen     matchad, men observationen ligger utanför horisontens
                  tolerans (pit-v4:s timing-regel, `TIMING_TOLERANCE_MIN`).
  ingen_capture   ingen observation alls före as-of — vi frågade aldrig.
  pit_byggd_fore_capture  en tidsriktig capture FINNS i presence-ledgern men
                  pit-v4-raden byggdes innan den skrevs (bygget körs på första
                  ticken efter as-of; den tvingade Pinnacle-hämtningen kommer
                  efter as-of och backdateras av CDN-Age) och byggs aldrig om.

Totalen bedöms BARA där 1X2 var ok: total_ok · total_saknas (Pinnacle lästes,
ingen total) · total_ogiltig (linje utan giltiga odds) · ingen_rad (as-of före
pit-total-v1:s fönster) · rad_saknas (as-of efter fönstret men ingen rad —
byggaren körde inte).

Ändrar ingenting: databasen öppnas read-only och bara rapportfilerna skrivs.
Ingen bakfyllning, inga alias läggs till — matcharen är en del av pit-v4:s
datagenererande process, så en ändring där kräver ny featureversion.

  backend/.venv/bin/python scripts/pool_tackning_rapport.py [--sedan 2026-08-15] [--out docs/pool-tackning-ÅÅÅÅ-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import pool_system_ledger as psl  # noqa: E402
from app.oddset import _team_sim, norm_team  # noqa: E402
from app.odds_provider import is_side_market  # noqa: E402
from app.pinnacle import COMBINED_MIN, HOME_AWAY_MIN, Pinnacle, _best_side  # noqa: E402
from app.pool_dataset import (FEATURE_START_AT, FEATURE_VERSION, HORIZONS,  # noqa: E402
                              TIMING_TOLERANCE_MIN, TOTAL_FEATURE_START_AT,
                              TOTAL_FEATURE_VERSION, _iso, _parse)

MATCHED = ("matched", "derived")
CLASSES = ("ok", "aldrig_matchad", "listad_sent", "tvetydig", "ingen_1x2", "capture_sen",
           "odds_ofullstandiga", "ingen_capture", "pit_byggd_fore_capture")
TOTAL_CLASSES = ("total_ok", "total_saknas", "total_ogiltig", "ingen_rad", "rad_saknas")
# Forwardtesternas startomgångar: PH5/maxtesterna (Stryk/Europa) och poolopt
# (Topptipset-familjen). Delmängden är det testerna faktiskt frös på.
FORWARD_START = {**psl.PH5_FORWARD_START_DRAW_BY_PRODUCT,
                 **psl.POOLOPT_FORWARD_START_DRAW_BY_PRODUCT}


def _load_captures(conn, product, draw):
    out: dict[int, list] = defaultdict(list)
    for event, fetched_at, status, odds_ok in conn.execute(
            "SELECT event_number, fetched_at, status, odds_complete FROM pool_market_capture "
            "WHERE product=? AND draw_number=? AND source='sharp' AND fetched_at>=? "
            "ORDER BY fetched_at", (product, draw, FEATURE_START_AT)):
        out[int(event)].append((fetched_at, status, bool(odds_ok)))
    return out


def _load_oddset(conn):
    """Oddsets egna rader: `svs:` ger liga för SvS-namnen, `pin:` bär Pinnacles
    råa namn — det enda vi har sparat av Pinnacles namnform för en match."""
    first_pin = dict(conn.execute(
        "SELECT match_id, MIN(fetched_at) FROM oddset_odds WHERE source='pinnacle' GROUP BY match_id"))
    by_date: dict[str, list] = defaultdict(list)
    pin: list[tuple] = []
    for mid, league, home, away, start, kambi_id, pinnacle_id in conn.execute(
            "SELECT id, league, home, away, start, kambi_id, pinnacle_id FROM oddset_matches WHERE start IS NOT NULL"):
        when = _parse(start)
        if when is None:
            continue
        by_date[when.date().isoformat()].append((when, home, away, league))
        if str(mid).startswith("pin:") or pinnacle_id:
            pin.append((when, home, away, league, kambi_id, first_pin.get(mid)))
    return by_date, pin


def _league(by_date, home, away, match_start):
    """Liga via Oddsets rader (SvS- eller Pinnacle-namn) samma dygn ±1, båda
    lagen ≥ 0,6 i Oddsets egen namnlikhet. Bara etikett, aldrig identitet."""
    when = _parse(match_start)
    if when is None:
        return "okänd"
    best = (0.0, "utanför Oddset")
    for delta in (0, -1, 1):
        for start, oh, oa, league in by_date.get((when + dt.timedelta(days=delta)).date().isoformat(), ()):
            if abs((start - when).total_seconds()) > 3 * 3600:
                continue
            score = min(_team_sim(home, oh), _team_sim(away, oa))
            if score >= 0.6 and score > best[0]:
                best = (score, league)
    return best[1]


def _replay(pin_client, pin_rows, home, away, match_start, close_iso):
    """Vad vet vi om en match poolmatcharen aldrig fann?

    Oddset-sidans `pin:`-rad bevisar att Pinnacle listade matchen, och dess
    första Pinnacle-odds säger NÄR. Bär raden `kambi_id` har Kambis namn
    ersatt Pinnacles (`oddset_upsert_match(prefer_names=True)`), så
    Pinnacles namnform är okänd och ingen replay är meningsfull. Bara olänkade
    rader bär Pinnacles råa namn; där spelas `pinnacle.match` upp offline."""
    when = _parse(match_start)
    if when is None:
        return {"utfall": "okänd avspark"}
    cands = []
    for start, ph, pa, league, kambi_id, first_odds in pin_rows:
        if is_side_market(ph, pa):
            continue
        if abs((start - when).total_seconds()) > 2 * 3600:
            continue
        score = min(_team_sim(home, ph), _team_sim(away, pa))
        if score >= 0.5:
            cands.append((score, ph, pa, league, start, kambi_id, first_odds))
    if not cands:
        return {"utfall": "ingen Pinnacle-rad hos Oddset"}
    score, ph, pa, league, start, kambi_id, first_odds = max(cands, key=lambda c: c[0])
    out = {"pinnacle": f"{ph.strip()} - {pa.strip()}", "liga": league,
           "pinnacle_first_odds": first_odds}
    close = _parse(close_iso)
    if len(cands) > 1:
        return {**out, "utfall": "flera möjliga Oddset-par — manuell kontroll"}
    if score < 0.8:
        return {**out, "utfall": "svag namnledtråd — identitet ej belagd"}
    if not first_odds:
        return {**out, "utfall": "Pinnacle-id sparat men pristid saknas"}
    if first_odds and close and _parse(first_odds) > close:
        return {**out, "utfall": "Pinnacle listade efter spelstopp"}
    if kambi_id:
        return {**out, "utfall": "listad före spelstopp, Pinnacles namnform ej sparad"}
    index = [{"home": ph, "away": pa, "start": _iso(start),
              "odds": {"1": 2.0, "X": 3.3, "2": 3.5}, "odds_source": "pinnacle", "total": None}]
    hit = pin_client.match(home, away, None, None, index, match_start)
    sides = (round(_best_side([home], ph), 3), round(_best_side([away], pa), 3))
    return {**out, "utfall": "träffar i replay, orsak okänd" if hit else "möjligt par avvisat — verifiera identiteten",
            "sidor": sides, "kombinerat": round(sum(sides) / 2, 3),
            "tröskel": f"sida ≥ {HOME_AWAY_MIN}, kombinerat ≥ {COMBINED_MIN}"}


def classify(conn, draws, by_date, pin_rows, pin_client):
    records = []
    for product, draw, close_iso in draws:
        close = _parse(close_iso)
        if close is None:
            continue
        events = conn.execute(
            "SELECT event_number, home, away, match_start, cancelled FROM pool_event_settlement "
            "WHERE product=? AND draw_number=? ORDER BY event_number", (product, draw)).fetchall()
        caps = _load_captures(conn, product, draw)
        pit = {(h, int(e)): (int(elig or 0), lag) for h, e, elig, lag in conn.execute(
            "SELECT horizon, event_number, sharp_eligible, sharp_lag_min FROM pool_pit_match_features "
            "WHERE product=? AND draw_number=? AND feature_version=?", (product, draw, FEATURE_VERSION))}
        tot = {(h, int(e)): (int(elig or 0), line, p_over) for h, e, elig, line, p_over in conn.execute(
            "SELECT horizon, event_number, total_eligible, line, p_over FROM pool_pit_total_features "
            "WHERE product=? AND draw_number=? AND feature_version=?", (product, draw, TOTAL_FEATURE_VERSION))}
        for event, home, away, match_start, cancelled in events:
            event = int(event)
            league = _league(by_date, home, away, match_start)
            seq = caps.get(event, [])
            for horizon, minutes in HORIZONS.items():
                asof_dt = close - dt.timedelta(minutes=minutes)
                asof = _iso(asof_dt)
                cap = None
                for point in seq:
                    if point[0] <= asof:
                        cap = point
                    else:
                        break
                if pit.get((horizon, event), (0, None))[0]:
                    cls = "ok"
                elif cap is None:
                    cls = "ingen_capture"
                elif cap[1] == "ambiguous":
                    cls = "tvetydig"
                elif cap[1] == "not_listed":
                    later = next((p for p in seq if p[1] in MATCHED and p[0] <= close_iso), None)
                    cls = "listad_sent" if later and later[0] > asof else "aldrig_matchad"
                elif cap[1] == "no_moneyline":
                    cls = "ingen_1x2"
                elif cap[1] in MATCHED:
                    lag = (asof_dt - _parse(cap[0])).total_seconds() / 60
                    if lag > TIMING_TOLERANCE_MIN[horizon]:
                        cls = "capture_sen"
                    elif not cap[2]:
                        cls = "odds_ofullstandiga"
                    else:
                        cls = "pit_byggd_fore_capture"
                else:
                    cls = f"status_{cap[1]}"
                total_cls = None
                if cls == "ok":
                    t = tot.get((horizon, event))
                    if t is None:
                        total_cls = "ingen_rad" if asof < TOTAL_FEATURE_START_AT else "rad_saknas"
                    elif t[0] and t[2] is not None:
                        total_cls = "total_ok"
                    elif t[0]:
                        total_cls = "total_ogiltig"
                    else:
                        total_cls = "total_saknas"
                rec = {"product": product, "draw": int(draw), "event": event, "home": home,
                       "away": away, "start": match_start, "cancelled": bool(cancelled),
                       "league": league, "horizon": horizon, "asof": asof, "cls": cls,
                       "total": total_cls,
                       "forward": int(draw) >= FORWARD_START.get(product, 10**9)}
                if cls == "aldrig_matchad" and horizon == "m20":
                    rec["replay"] = _replay(pin_client, pin_rows, home, away, match_start, close_iso)
                records.append(rec)
    return records


def observation_windows(conn, draws):
    """Per familj × horisont: har omgången någon sharp-capture på den sida av
    as-of som pit-v4 kan räkna ([as-of − tolerans, as-of]) respektive bara på
    den sida `horizon_window_open` tvingar fram ((as-of, as-of + tolerans])?
    Plus observationskadens: distinkta sharp-captures per produkt och dygn."""
    windows = defaultdict(Counter)
    days = defaultdict(set)
    per_day = defaultdict(set)
    for product, draw, close_iso in draws:
        close = _parse(close_iso)
        if close is None:
            continue
        family = "topptipset" if product.startswith("topptipset") else product
        times = [r[0] for r in conn.execute(
            "SELECT DISTINCT fetched_at FROM pool_market_capture WHERE product=? AND draw_number=? "
            "AND source='sharp' AND fetched_at>=?", (product, draw, FEATURE_START_AT))]
        for t in times:
            per_day[(product, t[:10])].add(t)
            days[product].add(t[:10])
        for horizon, minutes in HORIZONS.items():
            asof = close - dt.timedelta(minutes=minutes)
            tol = dt.timedelta(minutes=TIMING_TOLERANCE_MIN[horizon])
            before = any(_iso(asof - tol) <= t <= _iso(asof) for t in times)
            after = any(_iso(asof) < t <= _iso(asof + tol) for t in times)
            windows[(family, horizon)]["omgångar"] += 1
            windows[(family, horizon)]["före as-of (räknas)"] += before
            windows[(family, horizon)]["bara efter as-of (räknas inte)"] += (after and not before)
            windows[(family, horizon)]["ingen i fönstret"] += (not before and not after)
    cadence = {}
    for product, ds in days.items():
        counts = [len(per_day[(product, d)]) for d in ds]
        counts.sort()
        cadence[product] = {"dygn": len(counts), "median_per_dygn": counts[len(counts) // 2],
                            "max_per_dygn": counts[-1]}
    return windows, cadence


def summarize(records):
    per_ph = defaultdict(Counter)
    per_ph_fw = defaultdict(Counter)
    per_league = defaultdict(Counter)
    total_ph = defaultdict(Counter)
    trans = Counter()
    by_key = {}
    for r in records:
        per_ph[(r["product"], r["horizon"])][r["cls"]] += 1
        if r["forward"]:
            per_ph_fw[(r["product"], r["horizon"])][r["cls"]] += 1
        if r["horizon"] == "m20":
            per_league[r["league"]][r["cls"]] += 1
        if r["total"]:
            total_ph[(r["product"], r["horizon"])][r["total"]] += 1
        by_key[(r["product"], r["draw"], r["event"], r["horizon"])] = r["cls"]
    for (product, draw, event, horizon), cls in by_key.items():
        if horizon == "h3":
            trans[(cls, by_key.get((product, draw, event, "m20"), "saknas"))] += 1
    # Omgångsnivå: kompletta omgångar per horisont (alla matcher ok / total_ok)
    draws_ok = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))   # (product,h) -> draw -> [n, ok, total_ok]
    for r in records:
        cell = draws_ok[(r["product"], r["horizon"])][r["draw"]]
        cell[0] += 1
        cell[1] += r["cls"] == "ok"
        cell[2] += r["total"] == "total_ok"
    complete = {}
    for key, draws in draws_ok.items():
        n = len(draws)
        complete[key] = {"omgångar": n,
                         "alla_1x2": sum(1 for v in draws.values() if v[1] == v[0]),
                         "alla_total": sum(1 for v in draws.values() if v[2] == v[0])}
    never = [r for r in records if r["cls"] == "aldrig_matchad" and r["horizon"] == "m20"]
    replay = Counter(r["replay"]["utfall"] for r in never)
    unique = {}
    for r in never:
        unique.setdefault((norm_team(r["home"]), norm_team(r["away"]), (r["start"] or "")[:10]), r["replay"]["utfall"])
    replay_unique = Counter(unique.values())
    return {"per_product_horizon": per_ph, "per_product_horizon_forward": per_ph_fw,
            "per_league_m20": per_league, "total_per_product_horizon": total_ph,
            "h3_to_m20": trans, "complete_draws": complete, "never_matched_m20": never,
            "replay_outcomes": replay, "replay_outcomes_unique": replay_unique,
            "unique_never_matched": len(unique)}


def _pct(n, d):
    return f"{100 * n / d:.0f} %" if d else "–"


def markdown(summary, records, sedan, generated_at, windows, cadence):
    hz = list(HORIZONS)
    products = sorted({r["product"] for r in records})
    n_draws = len({(r["product"], r["draw"]) for r in records})
    out = [f"# Pooltäckning: 1X2 och Ö/U från Pinnacle vid frysningarna",
           "",
           f"Genererad {generated_at} av `backend/scripts/pool_tackning_rapport.py` (read-only). "
           f"Omfattar {n_draws} sluträttade omgångar med spelstopp från {sedan}, alla tre horisonter "
           f"({', '.join(f'{h}={m} min' for h, m in HORIZONS.items())}). Klasserna definieras i skriptets docstring.",
           "",
           "## 1X2-täckning per produkt och horisont (andel matcher `ok`)", "",
           "| produkt | " + " | ".join(hz) + " | vanligaste lucka vid m20 |",
           "|---|" + "---|" * (len(hz) + 1)]
    for p in products:
        cells = []
        for h in hz:
            c = summary["per_product_horizon"][(p, h)]
            n = sum(c.values())
            cells.append(f"{c['ok']}/{n} ({_pct(c['ok'], n)})")
        m20 = summary["per_product_horizon"][(p, "m20")]
        gaps = [(k, v) for k, v in m20.items() if k != "ok"]
        top = max(gaps, key=lambda kv: kv[1]) if gaps else ("–", 0)
        out.append(f"| {p} | " + " | ".join(cells) + f" | {top[0]} ({top[1]}) |")
    out += ["", "### Samma sak för forwardtesternas omgångar (det testerna faktiskt frös på)", "",
            "| produkt | " + " | ".join(hz) + " |", "|---|" + "---|" * len(hz)]
    for p in products:
        cells = []
        for h in hz:
            c = summary["per_product_horizon_forward"].get((p, h), Counter())
            n = sum(c.values())
            cells.append(f"{c['ok']}/{n} ({_pct(c['ok'], n)})" if n else "–")
        out.append(f"| {p} | " + " | ".join(cells) + " |")
    out += ["", "## Felklasser per produkt vid 180 min och 20 min", "",
            "| produkt | horisont | " + " | ".join(CLASSES) + " |",
            "|---|---|" + "---|" * len(CLASSES)]
    for p in products:
        for h in ("h3", "m20"):
            c = summary["per_product_horizon"][(p, h)]
            out.append(f"| {p} | {h} | " + " | ".join(str(c.get(k, 0)) for k in CLASSES) + " |")
    out += ["", "## Löser 20-minutersobservationen luckorna från 180 min? (samma match, samma omgång)", "",
            "| klass vid 180 min | → klass vid 20 min | matcher |", "|---|---|---|"]
    for (a, b), n in sorted(summary["h3_to_m20"].items(), key=lambda kv: (kv[0][0] == "ok", -kv[1])):
        out.append(f"| {a} | {b} | {n} |")
    out += ["", "## Observationsfönstret: på vilken sida av as-of hamnar sharp-capturen?", "",
            "pit-v4 räknar bara en capture i [as-of − tolerans, as-of]. Före insamlingsfixen "
            "2026-09-14 tvingades hämtningarna först efter as-of och ordinarie hämtningar "
            "utanför fönstret nådde bara första produkten. Sedan fixen är fönstret symmetriskt "
            "och indexet delas mellan produkterna. Tabellen mäter de faktiska observationerna; "
            "ett datumfilter på spelstopp kan fortfarande omfatta horisonter före driftsättningen.", "",
            "| familj | horisont | omgångar | capture före as-of (räknas) | bara efter as-of (räknas inte) | ingen i fönstret |",
            "|---|---|---|---|---|---|"]
    for (family, horizon), c in sorted(windows.items(), key=lambda kv: (kv[0][0], list(HORIZONS).index(kv[0][1]))):
        n = c["omgångar"]
        out.append(f"| {family} | {horizon} | {n} | {c['före as-of (räknas)']} ({_pct(c['före as-of (räknas)'], n)}) | "
                   f"{c['bara efter as-of (räknas inte)']} | {c['ingen i fönstret']} |")
    out += ["", "| produkt | dygn med sharp-capture | distinkta sharp-observationer per dygn (median) | max |",
            "|---|---|---|---|"]
    for product, c in sorted(cadence.items()):
        out.append(f"| {product} | {c['dygn']} | {c['median_per_dygn']} | {c['max_per_dygn']} |")
    out += ["", "## Ö/U-total där 1X2 var ok (pit-total-v1, fönster från "
            f"{TOTAL_FEATURE_START_AT})", "",
            "| produkt | horisont | " + " | ".join(TOTAL_CLASSES) + " |",
            "|---|---|" + "---|" * len(TOTAL_CLASSES)]
    for p in products:
        for h in hz:
            c = summary["total_per_product_horizon"].get((p, h))
            if not c:
                continue
            out.append(f"| {p} | {h} | " + " | ".join(str(c.get(k, 0)) for k in TOTAL_CLASSES) + " |")
    out += ["", "## Kompletta omgångar (alla matcher ok) — det grindarna räknar", "",
            "| produkt | horisont | omgångar | alla matcher 1X2 ok | alla matcher total ok |",
            "|---|---|---|---|---|"]
    for p in products:
        for h in hz:
            c = summary["complete_draws"].get((p, h))
            if c:
                out.append(f"| {p} | {h} | {c['omgångar']} | {c['alla_1x2']} | {c['alla_total']} |")
    out += ["", "## Luckor per liga vid 20 min (liga via Oddsets `svs:`-rader)", "",
            "| liga | matcher | ok | aldrig_matchad | listad_sent | tvetydig | ingen_1x2 | capture_sen | ingen_capture |",
            "|---|---|---|---|---|---|---|---|---|"]
    for league, c in sorted(summary["per_league_m20"].items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        out.append(f"| {league} | {n} | {c['ok']} | {c['aldrig_matchad']} | {c['listad_sent']} | "
                   f"{c['tvetydig']} | {c['ingen_1x2']} | {c['capture_sen']} | {c['ingen_capture']} |")
    never = summary["never_matched_m20"]
    out += ["", f"## Aldrig matchade vid 20 min: {len(never)} rader, {summary['unique_never_matched']} unika matcher "
            "(Stryk/Topptipset Stryk och Europa/Topptipset Extra delar matcher)", "",
            "Replayen kör `pinnacle.match` offline med Pinnacle-namnen som Oddset-sidan sparade för "
            "en möjlig match (±2 h). Fuzzy-likhet är en sökledtråd, inte identitetsbevis. "
            "Hörn-/kort-event utesluts, liksom automatiska slutsatser vid flera kandidater. "
            "Även svs:-rader med sparat Pinnacle-id räknas; deras råa Pinnacle-namn kan saknas. "
            "`ingen Pinnacle-rad hos Oddset` betyder "
            "att vi inte kan avgöra om Pinnacle listade den (ligan följs inte av Oddset, eller så "
            "listades den aldrig). `listad före spelstopp, Pinnacles namnform ej sparad` betyder att "
            "Pinnacle bevisligen listade matchen i tid men att Oddset-raden bär Kambis namn, så vi vet "
            "inte vilket namn poolmatcharen avvisade.", "",
            "| utfall | rader | unika matcher |", "|---|---|---|"]
    for k, v in summary["replay_outcomes"].most_common():
        out.append(f"| {k} | {v} | {summary['replay_outcomes_unique'].get(k, 0)} |")
    out += ["", "| produkt | omgång | match | liga | utfall | Pinnacle-namn | sidor | kombinerat |",
            "|---|---|---|---|---|---|---|---|"]
    for r in sorted(never, key=lambda r: (r["product"], r["draw"], r["event"])):
        rp = r["replay"]
        out.append(f"| {r['product']} | {r['draw']} | {r['event']}. {r['home']} – {r['away']} | {r['league']} | "
                   f"{rp['utfall']} | {rp.get('pinnacle', '–')}"
                   f"{' (odds hos Oddset från ' + rp['pinnacle_first_odds'][:10] + ')' if rp.get('pinnacle_first_odds') else ''} | "
                   f"{'/'.join(str(s) for s in rp['sidor']) if rp.get('sidor') else '–'} | {rp.get('kombinerat', '–')} |")
    out += ["", f"Poolmatcharens trösklar: sida ≥ {HOME_AWAY_MIN}, kombinerat ≥ {COMBINED_MIN} "
            "(`app/pinnacle.py`). Matcharen ingår i pit-v4:s datagenererande process: en ändring "
            "(alias, suffixstrippning, sänkt tröskel) gäller bara framåt och kräver ny featureversion "
            "eller ett explicit beslut om att pit-v4:s presence får ändra mening. Ingen historik bakfylls.", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "backend" / "data" / "stryktips.db"))
    ap.add_argument("--sedan", default="2026-08-15")
    ap.add_argument("--out", default=None, help="filprefix (utan ändelse)")
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    prefix = Path(args.out) if args.out else ROOT / "docs" / f"pool-tackning-{now.date().isoformat()}"
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    draws = conn.execute(
        "SELECT product, draw_number, reg_close_time FROM pool_draw_settlement "
        "WHERE reg_close_time >= ? ORDER BY reg_close_time", (args.sedan,)).fetchall()
    by_date, pin_rows = _load_oddset(conn)
    records = classify(conn, draws, by_date, pin_rows, Pinnacle())
    windows, cadence = observation_windows(conn, draws)
    summary = summarize(records)
    generated_at = _iso(now)
    md = markdown(summary, records, args.sedan, generated_at, windows, cadence)
    Path(f"{prefix}.md").write_text(md, encoding="utf-8")
    payload = {"generated_at": generated_at, "since": args.sedan, "feature_version": FEATURE_VERSION,
               "total_feature_version": TOTAL_FEATURE_VERSION, "n_records": len(records),
               "per_product_horizon": {f"{p}:{h}": dict(c) for (p, h), c in summary["per_product_horizon"].items()},
               "per_product_horizon_forward": {f"{p}:{h}": dict(c) for (p, h), c in summary["per_product_horizon_forward"].items()},
               "total_per_product_horizon": {f"{p}:{h}": dict(c) for (p, h), c in summary["total_per_product_horizon"].items()},
               "h3_to_m20": {f"{a}→{b}": n for (a, b), n in summary["h3_to_m20"].items()},
               "complete_draws": {f"{p}:{h}": v for (p, h), v in summary["complete_draws"].items()},
               "per_league_m20": {k: dict(v) for k, v in summary["per_league_m20"].items()},
               "replay_outcomes": dict(summary["replay_outcomes"]),
               "replay_outcomes_unique": dict(summary["replay_outcomes_unique"]),
               "unique_never_matched": summary["unique_never_matched"],
               "observation_windows": {f"{f}:{h}": dict(c) for (f, h), c in windows.items()},
               "cadence": cadence,
               "never_matched_m20": summary["never_matched_m20"]}
    Path(f"{prefix}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(md)
    print(f"\nSkrev {prefix}.md och {prefix}.json")


if __name__ == "__main__":
    main()
