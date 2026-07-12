"""Värde, steam, notiser och CLV-logg för Oddset-delen (Etapp 2 i docs/plan.md).

Metodregler (dyrt vunna i vm-projektet):
- Fair = power-devigad Pinnacle. AH/ÖU jämförs ENDAST när båda källorna har samma linje.
- Bara marknadspriser får logga CLV-flaggor; härledd 1X2 (P~) visas i UI men loggas ej.
- Edge = fair_prob × SvS-odds − 1 (EV per satsad krona).
- Steam = devigade sannolikhetsskift i procentenheter (jämförbart favorit/skräll).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from . import notify
from .analysis import _power_probs
from .storage import Storage

EDGE_SHOW = 0.02       # visas i UI (grön markering)
EDGE_LOG = 0.02        # loggas i CLV-facitet
EDGE_NOTIFY = 0.03     # push-notis
STEAM_FLAG_PP = 3.5    # 🔥 markant (6h- eller 24h-skift)
STEAM_STRONG_PP = 6.0
STEAM_NOTIFY_PP = 5.0  # push på 6h-skiftet (snabb rörelse = träningsmatch-caset)

_MARKET_SIGNS = {"1x2": ("1", "X", "2"), "ah": ("H", "A"), "ou": ("O", "U"),
                 "cor": ("O", "U")}
MARKET_LABEL = {"1x2": "1X2", "ah": "AH", "ou": "Ö/U", "cor": "Hörnor"}


def _devig(odds: dict, signs: tuple) -> Optional[dict[str, float]]:
    inv = {}
    for s in signs:
        o = odds.get(s)
        if not o or o <= 1.0:
            return None
        inv[s] = 1.0 / o
    return _power_probs(inv)


def attach_value(matches: list[dict]) -> None:
    """Sätter m['value'] = {market: {sign: {edge, fair, odds, book}}} (in place).
    Fair = devigad Pinnacle; edge räknas mot BÄSTA odds bland övriga böcker
    (svenskaspel, expekt, ...) — posten säger vilken bok. AH/ÖU/hörnor kräver
    samma linje som sharpen. Startade matcher hoppas över (live-odds ljuger)."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in matches:
        val: dict = {}
        m["value"] = val
        if (m.get("start") or "9") <= now:
            continue
        odds = m.get("odds") or {}
        pin = odds.get("pinnacle") or {}
        books = {src: v for src, v in odds.items() if src != "pinnacle"}
        for market, signs in _MARKET_SIGNS.items():
            p = pin.get(market)
            if not p:
                continue
            fair = _devig(p, signs)
            if not fair:
                continue
            for sign in signs:
                best = None   # (bok, odds) — SvS först så ties inte visas som sidobok
                for bk in sorted(books, key=lambda b: b != "svenskaspel"):
                    bo = books[bk]
                    s = bo.get(market)
                    if not s or not s.get(sign):
                        continue
                    if market != "1x2" and p.get("line") != s.get("line"):
                        continue   # olika linjer = inte jämförbart
                    if best is None or s[sign] > best[1]:
                        best = (bk, s[sign])
                if not best:
                    continue
                edge = fair[sign] * best[1] - 1.0
                val.setdefault(market, {})[sign] = {
                    "edge": round(edge, 4), "fair": round(fair[sign], 4),
                    "odds": best[1], "book": best[0],
                    "line": p.get("line"), "derived": bool(p.get("derived"))}


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


def log_and_notify(store: Storage, matches: list[dict]) -> dict:
    """Logga sharp-edges i CLV-facitet (first/best) och pusha notiser (ntfy).
    Härledd fair (P~) loggas ALDRIG — bara riktiga marknadspriser."""
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_logged = n_pushed = 0
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
                    "edge": v["edge"], "book": v.get("book")})
                n_logged += 1
                if v["edge"] >= EDGE_NOTIFY:
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
                "tier": "model"})
            n_logged += 1
        # snabb sharp-rörelse (6h) — boken kan hänga efter (träningsmatch-caset)
        for sign, sh in (m.get("steam") or {}).items():
            pp = sh.get("h6")
            if pp is None or abs(pp) < STEAM_NOTIFY_PP:
                continue
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
    return {"logged": n_logged, "pushed": n_pushed}


def resolve_closings(store: Storage) -> int:
    """Sätt stängning (devigad Pinnacle strax före avspark) på loggade flaggor
    vars match startat. AH/ÖU kräver samma linje som vid flaggan."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = 0
    for f in store.oddset_unresolved_closings(now):
        # modell-flaggor (m1x2/mah/mou) stängs mot samma sharp-marknad utan m-prefix
        hist_market = f["market"][1:] if f["market"].startswith("m") else f["market"]
        signs = _MARKET_SIGNS[hist_market]
        rows = store.oddset_history_before(f["match_id"], hist_market, f["match_start"])
        # senaste (odds, line) per tecken före avspark
        last: dict[str, dict] = {}
        for r in rows:                      # rows i tidsordning
            last[r["sign"]] = r
        if len(last) < len(signs):
            store.oddset_set_closing(f["match_id"], f["market"], f["sign"],
                                     None, None, "ingen sharp-stängning")
            n += 1
            continue
        if f["market"] != "1x2" and any(r.get("line") != f["line"] for r in last.values()):
            store.oddset_set_closing(f["match_id"], f["market"], f["sign"],
                                     None, None, "linje flyttad")
            n += 1
            continue
        fair = _devig({s: last[s]["odds"] for s in signs}, signs)
        if not fair:
            continue
        store.oddset_set_closing(f["match_id"], f["market"], f["sign"],
                                 round(fair[f["sign"]], 4), last[f["sign"]]["odds"], None)
        n += 1
    return n


def clv_report(store: Storage) -> dict:
    """Facit per tier: höll edgen till stängning? close_ev = closing_fair ×
    first_odds − 1. 'sharp' är den spelbara signalen; 'model' är forward-testet
    som avgör om/när modellen får grön status."""
    rows = store.oddset_clv_rows()
    for r in rows:
        if r["closing_fair"] is not None and r["first_odds"]:
            r["close_ev"] = round(r["closing_fair"] * r["first_odds"] - 1.0, 4)
        else:
            r["close_ev"] = None
    out = {"rows": rows}
    for tier in ("sharp", "model"):
        trows = [r for r in rows if (r.get("tier") or "sharp") == tier]
        resolved = [r for r in trows if r["close_ev"] is not None]
        avg = (sum(r["close_ev"] for r in resolved) / len(resolved)) if resolved else None
        out[tier] = {"n": len(trows), "n_resolved": len(resolved),
                     "avg_close_ev": round(avg, 4) if avg is not None else None}
    # bakåtkompatibelt (UI:t före tier-uppdelningen)
    out["n"], out["n_resolved"] = out["sharp"]["n"], out["sharp"]["n_resolved"]
    out["avg_close_ev"] = out["sharp"]["avg_close_ev"]
    return out
