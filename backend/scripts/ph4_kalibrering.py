"""PH4 del A — kalibreringsanalyser på settlementlagret (final_only, läsande).

Tre frågor mot 13 års facit (inga rörelser behövs — bara slutstreck, utfall,
omsättning och faktiska vinnarantal):

1. FOLKETS KALIBRERING: är streck-andelen en bra sannolikhet? Reliability
   per produkt och streckband (favorit-/longshot-bias hos kollektivet).
2. κ PER PRODUKT OCH NIVÅ: faktiska vinnare ÷ oberoende-förväntade vinnare
   (fält × Poisson-binomial över folk-sannolikheten för rätt tecken).
   Exponeringsviktat med omgången som bootstrap-block (WP6b-metoden, nu på
   ~80× mer material). κ < 1 ⇒ utdelningarna är systematiskt HÖGRE än
   oberoende-antagandet ger ⇒ dagens EV är konservativ.
3. FOLKKORRELATION: κ på toppnivån uppdelat efter hur "folkigt" facit var
   (kvartiler av P_folk(facitraden)). Korrelerade streckare ger κ>1 på
   folkiga facit och κ<1 på skrällfacit — riktningen och storleken mäts.

Exkluderingar (räknas och redovisas): omgångar med saknat utfall/streck,
struken match (lottat utfall ≠ streckad marknad) eller omsättning ≤ 0.
Ingen skrivning; deterministisk bootstrap (fast seed).

Körning: cd backend && .venv/bin/python -B scripts/ph4_kalibrering.py
Utdata: docs/ph4-kalibrering-era-v2.json. Ursprunglig PH4-rapport skrivs inte
över; v2 lägger till ICKE överlappande före-2024/2024+ som tidskontroll.
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "stryktips.db"
OUT = ROOT.parent / "docs" / "ph4-kalibrering-era-v2.json"
PRODUCTS = ("stryktipset", "europatipset", "topptipset",
            "topptipsetstryk", "topptipsetextra")
BOOTSTRAP_N = 1000
SEED = 20260724


def poisson_binomial(qs: list[float]) -> list[float]:
    """P(antal rätt = m) för oberoende matcher med rätt-sannolikheter qs."""
    dist = [1.0]
    for q in qs:
        nxt = [0.0] * (len(dist) + 1)
        for m, p in enumerate(dist):
            nxt[m] += p * (1 - q)
            nxt[m + 1] += p * q
        dist = nxt
    return dist


def load_draws(conn: sqlite3.Connection, product: str) -> tuple[list[dict], dict]:
    """Kompletta omgångar: q per match (folkets normerade sannolikhet för
    facittecknet), fält, faktiska vinnare per nivå. Exkluderingar bokförs."""
    heads = conn.execute(
        "SELECT draw_number, net_sale, row_price, n_cancelled, reg_close_time "
        "FROM pool_draw_settlement WHERE product=?", (product,)).fetchall()
    events: dict[int, list] = {}
    for dn, outcome, cancelled, s1, sx, s2 in conn.execute(
            "SELECT draw_number, outcome, cancelled, streck_one, streck_x, "
            "streck_two FROM pool_event_settlement WHERE product=?", (product,)):
        events.setdefault(dn, []).append((outcome, cancelled, s1, sx, s2))
    tiers: dict[int, dict[int, int]] = {}
    for dn, correct, winners in conn.execute(
            "SELECT draw_number, correct, winners FROM pool_payout_tier "
            "WHERE product=? AND correct IS NOT NULL", (product,)):
        tiers.setdefault(dn, {})[int(correct)] = int(winners or 0)
    out, skipped = [], {"cancelled": 0, "missing": 0, "turnover": 0}
    for dn, net_sale, row_price, n_cancelled, close in heads:
        evs = events.get(dn) or []
        if n_cancelled or any(e[1] for e in evs):
            skipped["cancelled"] += 1   # lottat utfall — folk-q meningslös
            continue
        if not evs or any(e[0] not in ("1", "X", "2") or
                          e[2] is None or e[3] is None or e[4] is None
                          for e in evs):
            skipped["missing"] += 1
            continue
        if not net_sale or net_sale <= 0 or not row_price or row_price <= 0:
            skipped["turnover"] += 1
            continue
        qs, sel_shares = [], []
        for outcome, _, s1, sx, s2 in evs:
            tot = (s1 + sx + s2) or 1
            share = {"1": s1, "X": sx, "2": s2}[outcome] / tot
            qs.append(max(share, 1e-9))
            sel_shares.append((s1 / tot, sx / tot, s2 / tot, outcome))
        out.append({"draw": dn, "close": str(close or ""),
                    "field": net_sale / row_price, "qs": qs,
                    "shares": sel_shares, "winners": tiers.get(dn, {})})
    return out, skipped


def reliability(draws: list[dict]) -> list[dict]:
    """Streck-andel (bucketad per 5 pp) mot faktisk träffrekvens."""
    bins: dict[int, list] = {}
    for d in draws:
        for s1, sx, s2, outcome in d["shares"]:
            for sign, share in (("1", s1), ("X", sx), ("2", s2)):
                b = min(int(share * 100) // 5, 18)
                bins.setdefault(b, [0, 0.0, 0])
                row = bins[b]
                row[0] += 1
                row[1] += share
                row[2] += int(sign == outcome)
    return [{"bucket": f"{b*5}-{b*5+5}%", "n": n,
             "mean_share": round(sh / n, 4), "hit_rate": round(hits / n, 4)}
            for b, (n, sh, hits) in sorted(bins.items()) if n >= 50]


def kappa(draws: list[dict], rng: random.Random) -> dict:
    """κ per nivå med 90 % blockbootstrap (omgången som block)."""
    per_draw: list[dict[int, tuple[float, int]]] = []
    for d in draws:
        dist = poisson_binomial(d["qs"])
        row = {}
        for m, actual in d["winners"].items():
            if m < len(dist):
                row[m] = (d["field"] * dist[m], actual)
        per_draw.append(row)
    levels = sorted({m for row in per_draw for m in row}, reverse=True)

    def ratio(sample: list[dict], m: int):
        exp = sum(r[m][0] for r in sample if m in r)
        act = sum(r[m][1] for r in sample if m in r)
        return (act / exp) if exp > 0 else None

    out = {}
    for m in levels:
        point = ratio(per_draw, m)
        if point is None:
            continue
        boots = []
        for _ in range(BOOTSTRAP_N):
            sample = [per_draw[rng.randrange(len(per_draw))]
                      for _ in range(len(per_draw))]
            r = ratio(sample, m)
            if r is not None:
                boots.append(r)
        boots.sort()
        out[m] = {"kappa": round(point, 4),
                  "ci90": [round(boots[int(len(boots) * 0.05)], 4),
                           round(boots[int(len(boots) * 0.95)], 4)],
                  "n_draws": sum(1 for r in per_draw if m in r)}
    return out


def folk_correlation(draws: list[dict], rng: random.Random) -> list[dict]:
    """κ på toppnivån per kvartil av hur folklig facitraden var."""
    rows = []
    for d in draws:
        if not d["winners"]:
            continue
        top = max(d["winners"])
        dist = poisson_binomial(d["qs"])
        if top >= len(dist):
            continue
        p_folk = 1.0
        for q in d["qs"]:
            p_folk *= q
        rows.append((p_folk, d["field"] * dist[top], d["winners"][top]))
    if len(rows) < 40:
        return []
    rows.sort(key=lambda r: r[0])
    quarts = []
    k = len(rows) // 4
    labels = ["Q1 skrällfacit", "Q2", "Q3", "Q4 folkfacit"]
    for i in range(4):
        chunk = rows[i * k:(i + 1) * k if i < 3 else len(rows)]
        exp = sum(r[1] for r in chunk)
        act = sum(r[2] for r in chunk)
        boots = []
        for _ in range(BOOTSTRAP_N // 2):
            sample = [chunk[rng.randrange(len(chunk))] for _ in range(len(chunk))]
            e = sum(r[1] for r in sample)
            if e > 0:
                boots.append(sum(r[2] for r in sample) / e)
        boots.sort()
        quarts.append({
            "kvartil": labels[i], "n": len(chunk),
            "kappa_top": round(act / exp, 4) if exp > 0 else None,
            "ci90": [round(boots[int(len(boots) * 0.05)], 4),
                     round(boots[int(len(boots) * 0.95)], 4)] if boots else None})
    return quarts


def main() -> None:
    rng = random.Random(SEED)
    conn = sqlite3.connect(DB)
    report: dict = {"seed": SEED, "bootstrap_n": BOOTSTRAP_N, "products": {}}
    try:
        for product in PRODUCTS:
            draws, skipped = load_draws(conn, product)
            print(f"\n=== {product}: {len(draws)} kompletta omgångar "
                  f"(exkl {skipped}) ===")
            rel = reliability(draws)
            worst = max(rel, key=lambda r: abs(r["hit_rate"] - r["mean_share"]),
                        default=None)
            kap = kappa(draws, rng)
            corr = folk_correlation(draws, rng)
            # Icke överlappande era-split. Hela 2013–2026 mot 2024+ får inte
            # beskrivas som trend eftersom proverna överlappar.
            earlier = [d for d in draws if d["close"] < "2024-01-01"]
            recent = [d for d in draws if d["close"] >= "2024-01-01"]
            kap_earlier = kappa(earlier, rng) if len(earlier) >= 40 else {}
            kap_recent = kappa(recent, rng) if len(recent) >= 40 else {}
            report["products"][product] = {
                "n_draws": len(draws), "skipped": skipped,
                "reliability": rel, "kappa": kap,
                "kappa_before_2024": {"n_draws": len(earlier), **{
                    str(m): v for m, v in kap_earlier.items()}},
                "kappa_since_2024": {"n_draws": len(recent), **{
                    str(m): v for m, v in kap_recent.items()}},
                "folk_correlation": corr}
            for m, k in sorted(kap_earlier.items(), reverse=True):
                print(f"  κ({m} rätt, före 2024) = {k['kappa']} "
                      f"KI90 [{k['ci90'][0]}..{k['ci90'][1]}] "
                      f"({len(earlier)} omg)")
            for m, k in sorted(kap_recent.items(), reverse=True):
                print(f"  κ({m} rätt, 2024+) = {k['kappa']} "
                      f"KI90 [{k['ci90'][0]}..{k['ci90'][1]}] ({len(recent)} omg)")
            for m, k in sorted(kap.items(), reverse=True):
                print(f"  κ({m} rätt) = {k['kappa']} "
                      f"KI90 [{k['ci90'][0]}..{k['ci90'][1]}] ({k['n_draws']} omg)")
            if worst:
                print(f"  reliability störst avvikelse: {worst['bucket']} "
                      f"streck {worst['mean_share']} vs utfall {worst['hit_rate']}")
            for q in corr:
                print(f"  {q['kvartil']}: κ_top {q['kappa_top']} "
                      f"KI90 {q['ci90']}")
    finally:
        conn.close()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\nSkrev {OUT}")


if __name__ == "__main__":
    main()
