"""PH0 — läsande käll- och coverage-audit för poolspelshistoriken (2026-07-24).

Del A (lokalt): PIT-coverage ur data/stryktips.db — per produkt och omgång
  senaste observerade snapshot (SvS respektive sharp) före T−24 h, T−3 h,
  T−20 min och före själva spelstoppet, med lagg i minuter.
Del B (API): sondering av äldre /draws/{nr} och /draws/{nr}/result per
  produkt: hur långt bak endpoints svarar, vilka fält som finns (odds,
  startOdds, svenskaFolket, currentNetSale, distribution/vinnare/utdelning,
  cancelled) samt hur rate limiting beter sig. Throttlad, enbart GET.

Kör:  cd backend && .venv/bin/python -B scripts/ph0_kallaudit.py \
          [--skip-api] [--delay 0.35] [--out ../docs/ph0-kallaudit-2026-07-24.json]

Metodregler (överlämningen 2026-07-24): detta är kohortinventering — inga
modell- eller DB-ändringar. API-bakfyllda omgångar är `final_only` och får
aldrig påstås ha odds-/streckrörelser; `draws.state` i lokala tabellen är
INTE settlement-facit (uppdateras inte efter avgörande).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.svenskaspel import API_VER, BASE, PRODUCTS, SvenskaSpel  # noqa: E402

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "stryktips.db"
HORIZONS = {"h24": 24 * 60, "h3": 3 * 60, "m20": 20, "close": 0}
# Fib-avstånd bakåt från senaste kända omgång — täcker dagliga produkter
# ~1,5 år och veckoprodukter många år utan att spränga requestbudgeten.
PROBE_OFFSETS = (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987)
MAX_REQUESTS_PER_PRODUCT = 120


def _parse_ts(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


# --- Del A: lokal PIT-coverage --------------------------------------------------

def local_coverage() -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now = dt.datetime.now(dt.timezone.utc)
    out: dict = {"db": str(DB_PATH), "generated_at": now.isoformat(), "products": {}}
    try:
        for product in PRODUCTS:
            closes = {
                int(r["draw_number"]): _parse_ts(r["reg_close_time"])
                for r in conn.execute(
                    "SELECT draw_number, reg_close_time FROM draws WHERE product=?",
                    (product,))
            }
            per_draw = []
            for table, key in (("snapshots", "svs"), ("sharp_snapshots", "sharp")):
                for r in conn.execute(
                        f"SELECT draw_number, COUNT(*) AS n FROM {table} "
                        "WHERE product=? GROUP BY draw_number", (product,)):
                    n = int(r["draw_number"])
                    row = next((d for d in per_draw if d["draw_number"] == n), None)
                    if row is None:
                        row = {"draw_number": n}
                        per_draw.append(row)
                    row[f"{key}_rows"] = int(r["n"])
            for row in per_draw:
                n = row["draw_number"]
                close = closes.get(n)
                row["reg_close_time"] = close.isoformat() if close else None
                row["passed"] = bool(close and close <= now)
                for table, key in (("snapshots", "svs"), ("sharp_snapshots", "sharp")):
                    stamps = sorted({
                        s for (v,) in conn.execute(
                            f"SELECT DISTINCT fetched_at FROM {table} "
                            "WHERE product=? AND draw_number=?", (product, n))
                        if (s := _parse_ts(v))
                    })
                    row[f"{key}_points"] = len(stamps)
                    if not stamps or not close:
                        continue
                    row[f"{key}_first"] = stamps[0].isoformat()
                    lags = {}
                    for hz, minutes in HORIZONS.items():
                        cutoff = close - dt.timedelta(minutes=minutes)
                        before = [s for s in stamps if s <= cutoff]
                        lags[hz] = round(
                            (cutoff - before[-1]).total_seconds() / 60, 1) \
                            if before else None
                    row[f"{key}_lag_min"] = lags
            per_draw.sort(key=lambda r: r["draw_number"])
            passed = [r for r in per_draw if r.get("passed")]

            def _lag_stats(rows: list[dict], src: str, hz: str) -> dict:
                lags = [r[f"{src}_lag_min"][hz] for r in rows
                        if r.get(f"{src}_lag_min", {}).get(hz) is not None]
                lags.sort()
                return {
                    "n": len(lags),
                    "n_lag_le_45m": sum(1 for v in lags if v <= 45),
                    "n_lag_le_6h": sum(1 for v in lags if v <= 360),
                    "median_lag_min": lags[len(lags) // 2] if lags else None,
                }
            out["products"][product] = {
                "draws_observed": len(per_draw),
                "draws_passed": len(passed),
                "horizons": {
                    src: {hz: _lag_stats(passed, src, hz) for hz in HORIZONS}
                    for src in ("svs", "sharp")
                },
                "per_draw": per_draw,
            }
    finally:
        conn.close()
    return out


# --- Del B: API-sondering -------------------------------------------------------

class Prober:
    """Räknar requests, throttlar och bokför alla icke-404-fel."""

    def __init__(self, svs: SvenskaSpel, delay: float):
        self.svs = svs
        self.delay = delay
        self.requests = 0
        self.errors: list[dict] = []

    def get(self, path: str) -> Optional[dict]:
        self.requests += 1
        time.sleep(self.delay)
        try:
            return self.svs._get_or_none(path)   # noqa: SLF001 — medveten intern
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            self.errors.append({"path": path, "status": status})
            if status == 429:   # backa och försök EN gång till
                time.sleep(5.0)
                try:
                    return self.svs._get_or_none(path)  # noqa: SLF001
                except httpx.HTTPStatusError as exc2:
                    self.errors.append(
                        {"path": path, "status": exc2.response.status_code})
            return None
        except httpx.HTTPError as exc:
            self.errors.append({"path": path, "status": f"transport: {exc}"})
            return None


def _raw_draw(data: Optional[dict]) -> Optional[dict]:
    if not data:
        return None
    raw = (data.get("draws") or [None])[0] if data.get("draws") else data.get("draw")
    return raw if raw and raw.get("drawNumber") else None


def inspect_draw(raw: dict) -> dict:
    events = raw.get("drawEvents") or []

    def count(pred) -> int:
        return sum(1 for e in events if pred(e))
    return {
        "state": raw.get("drawState"),
        "reg_close_time": raw.get("regCloseTime"),
        "n_events": len(events),
        "n_odds": count(lambda e: (e.get("odds") or {}).get("one")),
        "n_start_odds": count(lambda e: (e.get("startOdds") or {}).get("one")),
        "n_streck": count(lambda e: (e.get("svenskaFolket") or {}).get("one")),
        "n_cancelled": count(lambda e: e.get("cancelled")),
        "has_net_sale": bool(raw.get("currentNetSale")),
        "row_price": raw.get("rowPrice"),
    }


def inspect_result(data: Optional[dict]) -> Optional[dict]:
    if not data:
        return None
    result = data.get("result")
    if isinstance(result, list):
        result = result[0] if result else None
    if not result:
        return None
    tiers = result.get("distribution") or []
    events = result.get("events") or []
    return {
        "n_tiers": len(tiers),
        "tiers_complete": all(
            t.get("winners") is not None and t.get("amount") is not None
            for t in tiers) if tiers else False,
        "n_outcomes": sum(1 for e in events if e.get("outcome") in ("1", "X", "2")),
        "n_cancelled": sum(1 for e in events if e.get("cancelled")),
        "has_turnover": bool(result.get("currentNetSale")),
    }


def probe_product(prober: Prober, product: str, latest: int) -> dict:
    slug = PRODUCTS[product]["slug"]

    def fetch(n: int) -> tuple[Optional[dict], Optional[dict]]:
        draw = _raw_draw(prober.get(f"/draw/{API_VER}/{slug}/draws/{n}"))
        res = prober.get(f"/draw/{API_VER}/{slug}/draws/{n}/result") if draw else None
        return draw, res

    start_requests = prober.requests
    samples: list[dict] = []
    hits: list[int] = []
    misses: list[int] = []
    for offset in PROBE_OFFSETS:
        n = latest - offset
        if n < 1 or prober.requests - start_requests > MAX_REQUESTS_PER_PRODUCT - 20:
            break
        draw, res = fetch(n)
        if draw is None:
            misses.append(n)
            samples.append({"draw_number": n, "found": False})
            continue
        hits.append(n)
        samples.append({"draw_number": n, "found": True,
                        "draw": inspect_draw(draw),
                        "result": inspect_result(res)})
    # binärsök äldsta åtkomliga omgång mellan djupaste miss och äldsta träff
    oldest_known = min(hits) if hits else latest
    boundary_note = None
    deeper_misses = [m for m in misses if m < oldest_known]
    if not deeper_misses:
        boundary_note = (
            f"alla sonderade nummer ned till {oldest_known} svarar — "
            "gränsen ligger djupare än sonderingsbudgeten")
    else:
        lo, hi = max(deeper_misses), oldest_known
        while hi - lo > 1 and \
                prober.requests - start_requests < MAX_REQUESTS_PER_PRODUCT:
            mid = (lo + hi) // 2
            draw = _raw_draw(prober.get(f"/draw/{API_VER}/{slug}/draws/{mid}"))
            if draw is None:
                lo = mid
            else:
                hi = mid
        oldest_known = hi
        # enstaka luckor kan finnas — verifiera att result också svarar där
        draw, res = fetch(oldest_known)
        samples.append({"draw_number": oldest_known, "found": draw is not None,
                        "draw": inspect_draw(draw) if draw else None,
                        "result": inspect_result(res), "boundary": True})
    return {
        "latest_probed_from": latest,
        "oldest_accessible": oldest_known,
        "boundary_note": boundary_note,
        "n_requests": prober.requests - start_requests,
        "samples": samples,
    }


def api_audit(delay: float) -> dict:
    conn = sqlite3.connect(DB_PATH)
    latest = {
        product: row[0] if (row := conn.execute(
            "SELECT MAX(draw_number) FROM draws WHERE product=?",
            (product,)).fetchone()) else None
        for product in PRODUCTS
    }
    conn.close()
    out: dict = {"products": {}, "rate_limit_events": [], "transport_errors": []}
    with SvenskaSpel() as svs:
        prober = Prober(svs, delay)
        for product, top in latest.items():
            if not top:
                out["products"][product] = {"error": "ingen lokal omgång att utgå från"}
                continue
            print(f"  sonderar {product} bakåt från {top} …", flush=True)
            out["products"][product] = probe_product(prober, product, int(top))
        out["total_requests"] = prober.requests
        out["rate_limit_events"] = [e for e in prober.errors
                                    if e.get("status") == 429]
        out["other_errors"] = [e for e in prober.errors
                               if e.get("status") != 429]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-api", action="store_true")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--out", default=str(
        Path(__file__).resolve().parents[2] / "docs" /
        "ph0-kallaudit-2026-07-24.json"))
    args = ap.parse_args()

    report: dict = {"local": None, "api": None}
    print("Del A: lokal PIT-coverage …", flush=True)
    report["local"] = local_coverage()
    for product, data in report["local"]["products"].items():
        print(f"  {product}: {data['draws_observed']} observerade, "
              f"{data['draws_passed']} passerade", flush=True)
    if not args.skip_api:
        print("Del B: API-sondering …", flush=True)
        report["api"] = api_audit(args.delay)
        print(f"  totalt {report['api']['total_requests']} requests, "
              f"{len(report['api']['rate_limit_events'])} × 429", flush=True)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Skrev {args.out}", flush=True)


if __name__ == "__main__":
    main()
