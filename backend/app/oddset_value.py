"""Värde, steam, notiser och CLV-logg för Oddset-delen (Etapp 2 i docs/plan.md).

Metodregler (dyrt vunna i vm-projektet):
- Fair = power-devigad Pinnacle. AH/ÖU jämförs ENDAST när båda källorna har samma linje.
- Bara marknadspriser får logga CLV-flaggor; härledd 1X2 (P~) visas i UI men loggas ej.
- Edge = fair_prob × SvS-odds − 1 (EV per satsad krona).
- Steam = devigade sannolikhetsskift i procentenheter (jämförbart favorit/skräll).
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import pathlib
import random
import subprocess
from typing import Optional

from . import notify
from .analysis import _power_probs
from .storage import Storage


@functools.lru_cache(maxsize=1)
def _code_version() -> Optional[str]:
    """Kort git-hash — full reproducerbarhet (kolumnen git_hash). Som statistisk
    version är den för grov (en docs-commit fragmenterar facitet) — därför
    grupperas facitet på signal_version (fingeravtryck) i stället."""
    try:
        root = pathlib.Path(__file__).resolve().parents[2]
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001 — utan git funkar allt utom versionstaggen
        return None


def _fingerprint(prefix: str, params: dict) -> str:
    import hashlib
    raw = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    return f"{prefix}-{hashlib.sha1(raw.encode()).hexdigest()[:8]}"


def signal_versions(store: Storage) -> dict[str, str]:
    """Semantiska versioner per tier (granskningspunkt 5): byts ENDAST när
    prognos-/signalalgoritm, parametrar, T-kalibrering eller databehandling
    (DATA_VERSION) ändras — inte av docs/UI-commits. Sharp och modell har
    separata namnrymder (s-/m-prefix)."""
    from . import oddset_data, oddset_model
    cal = {}
    for lg in sorted(oddset_data.MODEL_LEAGUES):
        try:
            cal[lg] = (json.loads(store.meta_get(f"oddset_cal:{lg}") or "{}")).get("t")
        except ValueError:
            cal[lg] = None
    data_v = oddset_data.DATA_VERSION
    return {"sharp": _fingerprint("s", {**SHARP_PARAMS, "data": data_v}),
            "model": _fingerprint("m", {**oddset_model.MODEL_PARAMS,
                                        "cal_t": cal, "data": data_v,
                                        "price_max_age_min": PRICE_MAX_AGE_MIN,
                                        "price_presence": PRICE_PRESENCE_VERSION})}

EDGE_SHOW = 0.02       # visas i UI (grön markering)
EDGE_LOG = 0.02        # loggas i CLV-facitet (brett — facitet ska mäta även svansen)
PRICE_MAX_AGE_MIN = 45 # pris måste ha bekräftats i ett lyckat svar inom detta fönster
PRICE_PRESENCE_VERSION = "last-seen-available-v1"
Q_NOTIFY = 0.015       # push-notis på KVALITET q = edge/(odds−1) (Kelly-andelen):
                       # samma edge är mycket mer pålitlig på låga odds — ett litet
                       # fel i fair-sannolikheten blåser upp högoddsar-edges enormt.
                       # 0.015 ≈ edge 1,5 % @ 2.0, 3 % @ 3.0, 21 % @ 15.0.
STEAM_FLAG_PP = 3.5    # 🔥 markant (6h- eller 24h-skift)
STEAM_STRONG_PP = 6.0
STEAM_NOTIFY_PP = 5.0  # push på 6h-skiftet (snabb rörelse = träningsmatch-caset)

_MARKET_SIGNS = {"1x2": ("1", "X", "2"), "ah": ("H", "A"), "ou": ("O", "U"),
                 "cor": ("O", "U")}
MARKET_LABEL = {"1x2": "1X2", "ah": "AH", "ou": "Ö/U", "cor": "Hörnor"}

# Signal-relevanta parametrar för SHARP-tiern (devig + trösklar + linjeregel) —
# grunden för sharp-sidans signal_version. Notisvakten ingår INTE: den styr
# larm, inte vilka flaggor som väljs/värderas.
SHARP_PARAMS = {"devig": "power", "edge_log": EDGE_LOG,
                "same_line": True, "best_book": True,
                "price_max_age_min": PRICE_MAX_AGE_MIN,
                "price_presence": PRICE_PRESENCE_VERSION,
                "alt_lines": True}   # samma-linje via sharpens alt-linjer (2026-07-20)


def _devig(odds: dict, signs: tuple) -> Optional[dict[str, float]]:
    inv = {}
    for s in signs:
        o = odds.get(s)
        if not o or o <= 1.0:
            return None
        inv[s] = 1.0 / o
    return _power_probs(inv)


def attach_price_status(matches: list[dict],
                        now: Optional[dt.datetime] = None) -> None:
    """Stämpla varje marknad med fresh/age_minutes från observationslagret.

    Saknad provenance är avsiktligt inte färsk: en signal får hellre utebli än
    byggas på ett pris vars fortsatta närvaro inte kan bevisas.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    for match in matches:
        for markets in (match.get("odds") or {}).values():
            for market in markets.values():
                if not isinstance(market, dict):
                    continue
                seen = market.get("last_seen_at")
                try:
                    seen_at = dt.datetime.fromisoformat(seen.replace("Z", "+00:00"))
                    age = max(0.0, (now - seen_at).total_seconds() / 60)
                except (AttributeError, ValueError):
                    age = None
                market["age_minutes"] = round(age, 1) if age is not None else None
                market["fresh"] = bool(
                    market.get("available") and age is not None
                    and age <= PRICE_MAX_AGE_MIN)


def _alt_fair(alt_market: dict, line, signs: tuple,
              now: dt.datetime) -> Optional[dict[str, float]]:
    """Devigad fair från sharpens alt-linje på EXAKT bokens lina — färsk
    (≤ PRICE_MAX_AGE_MIN, available) annars None. Rent marknadspris, ingen
    modellhärledning; samma-linje-metodregeln uppfylls per konstruktion."""
    if line is None:
        return None
    slot = alt_market.get(int(round(float(line) * 1000)))
    if not slot or not slot.get("available"):
        return None
    try:
        seen = dt.datetime.fromisoformat(slot["last_seen_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return None
    if (now - seen).total_seconds() / 60 > PRICE_MAX_AGE_MIN:
        return None
    odds = {s: slot.get(s) for s in signs}
    if any(not o for o in odds.values()):
        return None
    return _devig(odds, signs)


def attach_value(matches: list[dict]) -> None:
    """Sätter m['value'] = {market: {sign: {edge, fair, odds, book}}} (in place).
    Fair = devigad Pinnacle; edge räknas mot BÄSTA odds bland övriga böcker
    (svenskaspel, expekt, ...) — posten säger vilken bok. AH/ÖU/hörnor kräver
    samma linje som sharpen. Startade matcher hoppas över (live-odds ljuger)."""
    now_dt = dt.datetime.now(dt.timezone.utc)
    attach_price_status(matches, now_dt)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in matches:
        val: dict = {}
        m["value"] = val
        if (m.get("start") or "9") <= now:
            continue
        odds = m.get("odds") or {}
        pin = odds.get("pinnacle") or {}
        books = {src: v for src, v in odds.items() if src != "pinnacle"}
        alt = m.get("sharp_alt") or {}
        for market, signs in _MARKET_SIGNS.items():
            p = pin.get(market)
            if not p or not p.get("fresh"):
                continue
            fair_main = _devig(p, signs)
            if not fair_main:
                continue
            for sign in signs:
                # bästa EDGE över böckerna: samma-linje-regeln uppfylls antingen
                # via huvudlinan eller via sharpens alt-linje på BOKENS lina —
                # båda är rena marknadspriser (steg-upp 2026-07-20). SvS först
                # så ties inte visas som sidobok.
                best = None   # (edge, bok, odds, fair, linje, via_alt)
                for bk in sorted(books, key=lambda b: b != "svenskaspel"):
                    s = books[bk].get(market)
                    if not s or not s.get("fresh") or not s.get(sign):
                        continue
                    via_alt = False
                    if market == "1x2" or p.get("line") == s.get("line"):
                        fair_here = fair_main
                    else:
                        fair_here = _alt_fair(alt.get(market) or {},
                                              s.get("line"), signs, now_dt)
                        via_alt = fair_here is not None
                    if not fair_here:
                        continue
                    edge = fair_here[sign] * s[sign] - 1.0
                    if best is None or edge > best[0]:
                        line = p.get("line") if market == "1x2" else s.get("line")
                        best = (edge, bk, s[sign], fair_here[sign], line, via_alt)
                if not best:
                    continue
                edge, bk, o, fp, line, via_alt = best
                entry = {
                    "edge": round(edge, 4), "fair": round(fp, 4),
                    "q": round(edge / max(o - 1.0, 0.01), 4),  # Kelly-kvalitet
                    "odds": o, "book": bk,
                    "line": line, "derived": bool(p.get("derived"))}
                if via_alt:
                    entry["alt_line"] = True
                val.setdefault(market, {})[sign] = entry


def _probs_at(pts: dict[str, list], signs: tuple, t: dt.datetime,
              oldest_ok_after: Optional[dt.datetime] = None) -> Optional[dict[str, float]]:
    """Devigade sannolikheter vid tidpunkt t ur punktserier {sign: [{'t','o'},...]}.
    oldest_ok_after: om serien är yngre än fönstret men äldsta punkten är äldre än
    denna gräns används den — skift över kortare tid är en STARKARE signal, och
    utan fallback är steam blind tills insamlingen samlat ett helt fönster."""
    odds = {}
    for s in signs:
        seq = pts.get(s) or []
        last = None
        for p in seq:
            if p["t"] <= t:
                last = p["o"]
            else:
                break
        if last is None and oldest_ok_after and seq and seq[0]["t"] <= oldest_ok_after:
            last = seq[0]["o"]
        if not last:
            return None
        odds[s] = last
    return _devig(odds, signs)


def attach_steam(matches: list[dict]) -> None:
    """Sätter m['steam'] = {sign: {'h6': pp, 'h24': pp}} ur Pinnacles 1X2-serie.
    Positivt = sannolikheten UPP (oddset kortas) sedan dess."""
    now = dt.datetime.now(dt.timezone.utc)
    signs = _MARKET_SIGNS["1x2"]
    for m in matches:
        current = ((m.get("odds") or {}).get("pinnacle") or {}).get("1x2") or {}
        if not current.get("fresh"):
            continue
        mv = ((m.get("movement") or {}).get("pinnacle") or {}).get("1x2") or {}
        pts = {}
        for s in signs:
            pl = []
            for p in (mv.get(s) or {}).get("pts") or []:
                try:
                    pl.append({"t": dt.datetime.fromisoformat(p["t"].replace("Z", "+00:00")),
                               "o": p["o"]})
                except ValueError:
                    pass
            pts[s] = pl
        cur = _probs_at(pts, signs, now)
        if not cur:
            continue
        steam: dict = {}
        for hours, key in ((6, "h6"), (24, "h24")):
            then = _probs_at(pts, signs, now - dt.timedelta(hours=hours),
                             oldest_ok_after=now - dt.timedelta(hours=hours / 2))
            if not then:
                continue
            for s in signs:
                pp = (cur[s] - then[s]) * 100
                if abs(pp) >= 0.05:
                    steam.setdefault(s, {})[key] = round(pp, 1)
        if steam:
            m["steam"] = steam


# --- CLV-logg + notiser (körs från oddset.collect) -----------------------------

def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def log_and_notify(store: Storage, matches: list[dict],
                   present: Optional[set] = None) -> dict:
    """Logga sharp-edges i CLV-facitet (first/best) och pusha notiser (ntfy).
    Härledd fair (P~) loggas ALDRIG — bara riktiga marknadspriser.

    present = notisvakten (WP2-mini): mängden (match_id, källa, marknad) som
    observerades i det aktuella lyckade insamlingsvarvet. En notis (inkl.
    🔔-historikposten) skapas BARA om både bokpriset och Pinnacle-priset för
    marknaden är närvarobekräftade — ett pris som försvunnit ur källans svar
    (suspenderat/plockat/källfel) kan inte larmas på. None = ingen vakt
    (bakåtkompatibelt för direktanrop); CLV-loggningen berörs inte (facitets
    färskhet hanteras av fulla WP2)."""
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    git = _code_version()
    vers = signal_versions(store)
    n_logged = n_pushed = n_gated = 0

    def _fresh(mid: str, book: Optional[str], market: str) -> bool:
        if present is None:
            return True
        return ((mid, book, market) in present
                and (mid, "pinnacle", market) in present)
    for m in matches:
        desc = f"{m['home']} – {m['away']}"
        for market, per_sign in (m.get("value") or {}).items():
            for sign, v in per_sign.items():
                if v["edge"] < EDGE_LOG or v.get("derived"):
                    continue
                store.oddset_log_flag({
                    "match_id": m["id"], "market": market, "sign": sign,
                    "line": v.get("line"), "league": m.get("league"),
                    "description": desc, "match_start": m.get("start"),
                    "at": at, "odds": v["odds"], "fair": v["fair"],
                    "edge": v["edge"], "book": v.get("book"),
                    "model_version": vers["sharp"], "git_hash": git})
                n_logged += 1
                if v.get("q", 0) >= Q_NOTIFY:
                    if not _fresh(m["id"], v.get("book"), market):
                        n_gated += 1   # priset ej sett i detta varv — larma inte
                        continue
                    key = f"oddset_ntfy_edge:{m['id']}:{market}:{sign}"
                    if not store.meta_get(key):
                        lt = f" {v['line']:+g}" if market == "ah" else \
                             f" {v['line']:g}" if market in ("ou", "cor") else ""
                        bok = {"svenskaspel": "SvS"}.get(v.get("book"),
                                                         (v.get("book") or "?").title())
                        title = f"Värde: {desc}"
                        msg = (f"{MARKET_LABEL[market]}{lt} {sign} @ {v['odds']:.2f} hos {bok}"
                               f" — fair {1 / v['fair']:.2f} (Pinnacle) = {_fmt_pct(v['edge'])} edge")
                        # trigga alltid (historiken i UI); pusha bara med NTFY_TOPIC
                        sent = notify.enabled() and notify.push(title, msg, tags="moneybag")
                        store.meta_set(key, json.dumps(
                            {"at": at, "title": title, "msg": msg, "sent": bool(sent)},
                            ensure_ascii=False))
                        n_pushed += bool(sent)
        # modellens forward-logg (amber-tier, market 'm1x2'): loggas för facit,
        # notifierar ALDRIG. Det här är vägen mot grönt — modellen får grön status
        # per liga först när dess loggade flaggor visar positiv close-EV över tid.
        # loggtröskel 2 % (lägre än UI-pillens 5 %): backtest v2 visade att just
        # 2–8 %-bandet var det intressanta i Allsvenskan — och fler loggade
        # flaggor ger snabbare facit (grönt-kriteriet kräver ≥50 stängda).
        # Även AH/ÖU forward-loggas (market mah/mou) — facit per marknad.
        md = m.get("model") or {}
        svs_all = (m.get("odds") or {}).get("svenskaspel") or {}
        model_flags = [("m1x2", None, sign, e, md.get("p", {}).get(sign),
                        (svs_all.get("1x2") or {}).get(sign))
                       for sign, e in (md.get("edges") or {}).items()]
        for market in ("ah", "ou"):
            mp = md.get(market)
            if not mp:
                continue
            sv = svs_all.get(market) or {}
            model_flags += [(f"m{market}", mp.get("line"), sd, e,
                             mp.get(f"p{sd}"), sv.get(sd))
                            for sd, e in (mp.get("edges") or {}).items()]
        for mkt, line, sign, e, fair, svs_odds in model_flags:
            if e is None or e < 0.02 or not svs_odds or fair is None:
                continue
            store.oddset_log_flag({
                "match_id": m["id"], "market": mkt, "sign": sign,
                "line": line, "league": m.get("league"), "description": desc,
                "match_start": m.get("start"), "at": at, "odds": svs_odds,
                "fair": fair, "edge": e, "book": "svenskaspel",
                "tier": "model", "model_version": vers["model"], "git_hash": git})
            n_logged += 1
        # snabb sharp-rörelse (6h) — boken kan hänga efter (träningsmatch-caset)
        for sign, sh in (m.get("steam") or {}).items():
            pp = sh.get("h6")
            if pp is None or abs(pp) < STEAM_NOTIFY_PP:
                continue
            if present is not None and (m["id"], "pinnacle", "1x2") not in present:
                n_gated += 1   # steam-siffran bygger på en serie som inte
                continue       # bekräftades i detta varv — larma inte
            key = f"oddset_ntfy_steam:{m['id']}:{sign}"
            if not store.meta_get(key):
                title = f"Steam: {desc}"
                msg = (f"Pinnacle har flyttat {sign} {pp:+.1f} pp på 6 h — "
                       f"kolla om SvS/andra böcker hängt med")
                sent = notify.enabled() and notify.push(title, msg, tags="fire")
                store.meta_set(key, json.dumps(
                    {"at": at, "title": title, "msg": msg, "sent": bool(sent)},
                    ensure_ascii=False))
                n_pushed += bool(sent)
    return {"logged": n_logged, "pushed": n_pushed, "gated": n_gated}


def closing_snapshot(store: Storage, row: dict) -> dict:
    """Rent marknadsfacit för en flagga/prediktion, utan att skriva i DB."""
    def _seen_after(row: dict, threshold: dt.datetime) -> bool:
        try:
            return dt.datetime.fromisoformat(
                row["last_seen_at"].replace("Z", "+00:00")) >= threshold
        except (AttributeError, ValueError):
            return False

    def _move_score(market: str, sign: str, delta: float) -> float:
        if market == "ah":
            return -delta if sign == "H" else delta
        return delta if sign == "O" else -delta

    # modell-flaggor (m1x2/mah/mou) stängs mot samma sharp-marknad utan m-prefix
    hist_market = (row["market"][1:] if row["market"].startswith("m")
                   else row["market"])
    signs = _MARKET_SIGNS.get(hist_market)
    if not signs:
        return {"fair": None, "odds": None, "note": "okänd sharp-marknad"}
    rows = store.oddset_history_before(
        row["match_id"], hist_market, row["match_start"])
    last: dict[str, dict] = {}
    for price in rows:
        last[price["sign"]] = price
    if len(last) < len(signs):
        return {"fair": None, "odds": None, "note": "ingen sharp-stängning"}
    if any(not price.get("available") for price in last.values()):
        return {"fair": None, "odds": None,
                "note": "sharp-stängning ej tillgänglig"}
    start = dt.datetime.fromisoformat(row["match_start"].replace("Z", "+00:00"))
    fresh_after = start - dt.timedelta(minutes=PRICE_MAX_AGE_MIN)
    if any(not _seen_after(price, fresh_after) for price in last.values()):
        return {"fair": None, "odds": None,
                "note": f"sharp-stängning äldre än {PRICE_MAX_AGE_MIN} min"}

    if hist_market == "1x2":
        target = last
        closing_line = line_delta = move_score = None
        note = None
    else:
        closing_lines = {last[s].get("line") for s in signs}
        if len(closing_lines) != 1 or None in closing_lines:
            return {"fair": None, "odds": None,
                    "note": "inkonsistent sharp-stängningslina"}
        closing_line = closing_lines.pop()
        flag_line = row.get("line")
        if flag_line is None:
            return {"fair": None, "odds": None, "note": "flagglina saknas"}
        line_delta = round(closing_line - flag_line, 4)
        move_score = round(_move_score(hist_market, row["sign"], line_delta), 4)
        target = {}
        target_key = int(round(float(flag_line) * 1000))
        for price in rows:
            line = price.get("line")
            if line is not None and int(round(float(line) * 1000)) == target_key:
                target[price["sign"]] = price
        same_line_fresh = (len(target) == len(signs)
                           and all(_seen_after(price, fresh_after)
                                   for price in target.values()))
        if not same_line_fresh:
            # alt-linjelagret: sharpens pris på FLAGGANS lina kan finnas där
            # även när huvudlinan flyttat — färskt exakt-line-close utan censur
            alt_target: dict[str, dict] = {}
            for price in store.oddset_sharp_alt_before(
                    row["match_id"], hist_market, row["match_start"]):
                if int(round(float(price["line"]) * 1000)) == target_key:
                    alt_target[price["sign"]] = price
            if (len(alt_target) == len(signs)
                    and all(price.get("available") for price in alt_target.values())
                    and all(_seen_after(price, fresh_after)
                            for price in alt_target.values())):
                target = alt_target
                same_line_fresh = True
        note = None if same_line_fresh else (
            "linje flyttad" if line_delta else
            f"sharp-stängning äldre än {PRICE_MAX_AGE_MIN} min")

    fair = (_devig({s: target[s]["odds"] for s in signs}, signs)
            if len(target) == len(signs) and note is None else None)
    if not fair:
        return {"fair": None, "odds": None,
                "note": note or "ingen sharp-stängning på flaggans lina",
                "closing_line": closing_line, "line_delta": line_delta,
                "line_move_score": move_score}
    return {"fair": round(fair[row["sign"]], 4),
            "odds": target[row["sign"]]["odds"], "note": None,
            "closing_line": closing_line, "line_delta": line_delta,
            "line_move_score": move_score}


def resolve_closings(store: Storage) -> int:
    """Stäng flaggor mot färsk Pinnacle-marknad strax före avspark."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = 0
    for flag in store.oddset_unresolved_closings(now):
        close = closing_snapshot(store, flag)
        store.oddset_set_closing(
            flag, close.get("fair"), close.get("odds"), close.get("note"),
            close.get("closing_line"), close.get("line_delta"),
            close.get("line_move_score"))
        n += 1
    return n


GREEN_MIN_N = 50          # grönt-kriterium v2 (granskningen 2026-07-13):
GREEN_CI_ALPHA = 0.10     # ≥50 stängda OCH undre 90 %-KI-gräns > 0 — KI via
WINSOR_EV = 0.20          # kluster-bootstrap per MATCH (flaggor i samma match är
                          # korrelerade); close-EV winsoriseras ±20 % så en enda
                          # högoddsare inte kan bära (eller sänka) hela snittet


def _cluster_ci(resolved: list[dict], iters: int = 1000,
                alpha: float = GREEN_CI_ALPHA) -> Optional[tuple[float, float]]:
    """Bootstrap-KI för snitt-close-EV med matchen som block (resampla matcher,
    inte flaggor). Deterministiskt seedad — rapporten ska inte fladdra."""
    by_match: dict[str, list[float]] = {}
    for r in resolved:
        by_match.setdefault(r["match_id"], []).append(r["close_ev_w"])
    clusters = list(by_match.values())
    if len(clusters) < 3:
        return None
    rng = random.Random(f"clv:{len(resolved)}:{len(clusters)}")
    means = []
    for _ in range(iters):
        sample = [v for c in rng.choices(clusters, k=len(clusters)) for v in c]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(len(means) * alpha / 2)]
    hi = means[min(len(means) - 1, int(len(means) * (1 - alpha / 2)))]
    return round(lo, 4), round(hi, 4)


def _tier_stats(trows: list[dict]) -> dict:
    resolved = [r for r in trows if r["close_ev"] is not None]
    moved = [r for r in trows if r.get("line_move_score") is not None
             and abs(r["line_move_score"]) > 1e-9]
    # ESTIMAND-REGEL (2026-07-24): huvudsiffran och konfidensintervallet måste
    # mäta SAMMA storhet. Tidigare rapporterades det owinsoriserade snittet
    # bredvid ett KI beräknat på det winsoriserade — intervallet kunde då
    # utesluta sitt eget medelvärde (observerat: snitt +6,6 % med KI
    # [+1,1..+4,1]). Nu är avg_close_ev det winsoriserade snittet, precis som
    # KI:t och grönt-kriteriet; det råa snittet redovisas separat som
    # avg_close_ev_raw så att svansarnas storlek fortfarande syns.
    avg_raw = (sum(r["close_ev"] for r in resolved) / len(resolved)) if resolved else None
    avg_w = (sum(r["close_ev_w"] for r in resolved) / len(resolved)) if resolved else None
    ci = _cluster_ci(resolved)
    avg_move = (sum(r["line_move_score"] for r in moved) / len(moved)) if moved else None

    # CENSURERINGSDIAGNOSTIK (2026-07-24). Facitet vägrar med rätta fabricera
    # close-EV när linjen flyttat och inget färskt pris finns på flaggans lina
    # — men då betingas snittet på "linjen stod still", vilket tar bort exakt
    # de fall CLV ska mäta. Vi kan inte hitta på EV för dem, men vi kan visa
    # hur stor censuren är och åt vilket håll den lutar: line_move_score > 0
    # betyder att linjen rörde sig MED selektionen (sannolikt en bra flagga
    # som faller ur snittet), < 0 att den rörde sig emot.
    censored = [r for r in trows
                if r["close_ev"] is None and r.get("line_move_score") is not None]
    cens_pos = sum(1 for r in censored if r["line_move_score"] > 0)
    closable = len(resolved) + len(censored)
    resolved_share = (len(resolved) / closable) if closable else None
    return {"n": len(trows), "n_resolved": len(resolved),
            "n_line_moved": len(moved),
            "n_line_moved_positive": sum(r["line_move_score"] > 0 for r in moved),
            "avg_line_move_score": round(avg_move, 4) if avg_move is not None else None,
            "avg_close_ev": round(avg_w, 4) if avg_w is not None else None,
            "avg_close_ev_raw": round(avg_raw, 4) if avg_raw is not None else None,
            "estimand": f"winsoriserad ±{int(WINSOR_EV * 100)} %",
            "n_censored": len(censored),
            "n_censored_favorable": cens_pos,
            "resolved_share": round(resolved_share, 3) if resolved_share else None,
            "ci": list(ci) if ci else None,
            # Grönt kräver nu även att facitet är representativt: är mer än
            # hälften av de stängbara flaggorna censurerade mäter snittet ett
            # icke-slumpmässigt urval och får inte ensamt ge grönt.
            "green_ready": bool(len(resolved) >= GREEN_MIN_N and ci and ci[0] > 0
                                and (resolved_share or 0) >= 0.5)}


def clv_report(store: Storage) -> dict:
    """Facit per tier: höll edgen till stängning? close_ev = closing_fair ×
    first_odds − 1. 'sharp' är den spelbara signalen; 'model' är forward-testet.
    Grönt-kriterium v2: n_resolved ≥ 50 OCH undre bootstrap-KI-gränsen > 0
    (kluster per match, winsoriserad EV) — per tier och per liga/marknad i
    'groups'. Positivt snitt ensamt räcker inte (brus, korrelation, extremodds)."""
    rows = store.oddset_clv_rows()
    for r in rows:
        if r["closing_fair"] is not None and r["first_odds"]:
            ev = r["closing_fair"] * r["first_odds"] - 1.0
            r["close_ev"] = round(ev, 4)
            r["close_ev_w"] = max(-WINSOR_EV, min(WINSOR_EV, ev))
        else:
            r["close_ev"] = None
    out = {"rows": rows}
    for tier in ("sharp", "model"):
        trows = [r for r in rows if (r.get("tier") or "sharp") == tier]
        out[tier] = _tier_stats(trows)
    # nedbrutet facit: liga × marknad × version inom tier (bara grupper med data)
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        key = ((r.get("tier") or "sharp"), r.get("league") or "?",
               r.get("market") or "?", r.get("model_version") or "-")
        groups.setdefault(key, []).append(r)
    out["groups"] = [
        {"tier": k[0], "league": k[1], "market": k[2], "version": k[3],
         **_tier_stats(v)}
        for k, v in sorted(groups.items()) if any(r["close_ev"] is not None for r in v)]
    # bakåtkompatibelt (UI:t före tier-uppdelningen)
    out["n"], out["n_resolved"] = out["sharp"]["n"], out["sharp"]["n_resolved"]
    out["avg_close_ev"] = out["sharp"]["avg_close_ev"]
    return out
