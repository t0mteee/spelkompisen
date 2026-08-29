"""Rent läsande änd-till-änd-hälsa för poolinsamlingen.

Källhälsan kan säga att ett anrop lyckades, men Topptipset-felet 2026-08-04
visade att fel anropsväg kan göra det grönt samtidigt som en hel produkt inte
samlas. Den här kontrollen mäter därför artefakterna som faktiskt behövs:
färska snapshots per öppen omgång, komplett systemfrysning när en horisont
passerat och omprövning av spelade kuponger när deras retry-tid löpt ut.

Ingen nätverkstrafik och inga skrivningar sker här. Rapporten kan därför visas
i UI, köras från ``cli.py kallhalsa`` och testas på en isolerad databas.
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from .pool_system_ledger import (FREEZE_HORIZONS, benchmarks_for,
                                 research_families_for)
from .svenskaspel import PRODUCTS

NORMAL_MAX_AGE_MIN = 45
DENSE_MAX_AGE_MIN = 15
DENSE_WITHIN_H = 2.0
FREEZE_GRACE_MIN = 15
SETTLEMENT_GRACE_MIN = 20


def _at(value) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _issue(issues: list[dict], level: str, product: str, kind: str,
           message: str, draw_number: Optional[int] = None) -> None:
    issues.append({"level": level, "product": product, "kind": kind,
                   "draw_number": draw_number, "message": message})


def report(store, *, now: Optional[dt.datetime] = None,
           products: Optional[Iterable[str]] = None) -> dict:
    """Kontrollera poolens observerade slutprodukter utan externa anrop."""
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    chosen = tuple(products or PRODUCTS.keys())
    issues: list[dict] = []
    product_rows: list[dict] = []
    window_start = now - dt.timedelta(hours=6)
    window_end = now + dt.timedelta(days=14)

    for product in chosen:
        draws = []
        for row in store.conn.execute(
                "SELECT draw_number, reg_close_time FROM draws "
                "WHERE product=? AND reg_close_time IS NOT NULL "
                "ORDER BY draw_number DESC LIMIT 100", (product,)):
            close = _at(row[1])
            # DB:n innehåller både +02:00 och Z. Jämför därför tolkade tider,
            # aldrig ISO-strängarna lexikografiskt.
            if close and window_start <= close <= window_end:
                draws.append({"draw_number": int(row[0]), "close": close})
        draws.sort(key=lambda d: d["close"])
        open_draws = [d for d in draws if d["close"] > now]
        nearest = open_draws[0] if open_draws else None
        latest = store.conn.execute(
            "SELECT MAX(fetched_at) FROM pool_draw_snapshot WHERE product=?",
            (product,)).fetchone()[0]
        latest_at = _at(latest)
        max_age = (DENSE_MAX_AGE_MIN if nearest and
                   (nearest["close"] - now).total_seconds() / 3600 <= DENSE_WITHIN_H
                   else NORMAL_MAX_AGE_MIN)

        if open_draws and latest_at is None:
            _issue(issues, "error", product, "no_snapshots",
                   "öppna omgångar finns men produkten har inga snapshots")
        elif open_draws and (now - latest_at).total_seconds() > max_age * 60:
            age = int((now - latest_at).total_seconds() // 60)
            _issue(issues, "error", product, "stale_snapshots",
                   f"senaste snapshot är {age} min gammal (gräns {max_age} min)")

        for draw in open_draws:
            draw_latest = store.conn.execute(
                "SELECT MAX(fetched_at) FROM pool_draw_snapshot "
                "WHERE product=? AND draw_number=?",
                (product, draw["draw_number"])).fetchone()[0]
            if draw_latest is None:
                _issue(issues, "error", product, "draw_missing",
                       "öppen omgång saknar helt pool-snapshot",
                       draw["draw_number"])

        # Kontrollera även nyss stängda omgångar: båda horisonterna ska vara
        # frysta när deras nominella tid plus ett helt tätvarv har passerat.
        benchmark_keys = tuple(b["key"] for b in benchmarks_for(product))
        for draw in draws:
            research_families = research_families_for(
                product, draw["draw_number"])
            for horizon, (minutes, timely_tol) in FREEZE_HORIZONS.items():
                due = draw["close"] - dt.timedelta(minutes=minutes)
                horizon_label = ("3 timmar" if horizon == "h3" else
                                 "20 minuter" if horizon == "m20" else horizon)
                # h3 ligger utanför tvåtimmars-förtätningen och får därför
                # komma vid nästa 30-minutersbasvarv. Den gamla fasta
                # 15-minutersgränsen gav ett falskt rött fönster innan ett
                # helt tillåtet h3-varv hunnit ske. m20 behåller 15 min.
                grace = max(FREEZE_GRACE_MIN, timely_tol)
                if now < due + dt.timedelta(minutes=grace):
                    continue
                def _count(keys: tuple[str, ...]) -> int:
                    if not keys:
                        return 0
                    marks = ",".join("?" for _ in keys)
                    return store.conn.execute(
                        "SELECT COUNT(DISTINCT config_key) FROM pool_system_ledger "
                        "WHERE product=? AND draw_number=? AND horizon=? "
                        f"AND config_key IN ({marks})",
                        (product, draw["draw_number"], horizon, *keys),
                    ).fetchone()[0]

                count = _count(benchmark_keys)
                if count < len(benchmark_keys):
                    closed = draw["close"] <= now
                    level = "warning" if closed else "error"
                    message = (f"{horizon_label} före spelstopp: {count} av "
                               f"{len(benchmark_keys)} testsystem sparades"
                               if closed else
                               f"{horizon} har {count}/{len(benchmark_keys)} "
                               "frysta system")
                    _issue(issues, level, product, "freeze_incomplete", message,
                           draw["draw_number"])
                for family, configs in research_families.items():
                    research_keys = tuple(c["key"] for c in configs)
                    research_count = _count(research_keys)
                    if research_count < len(research_keys):
                        closed = draw["close"] <= now
                        level = "warning" if closed else "error"
                        family_label = {
                            "ph5": "PH5",
                            "mathmax": "matematiska 41 472-testet",
                            "reducedmax": "reducerade 20 000-testet",
                        }.get(family, family)
                        message = (
                            f"{horizon_label} före spelstopp: {research_count} "
                            f"av {len(research_keys)} system i {family_label} sparades"
                            if closed else
                            f"{horizon} har {research_count}/{len(research_keys)} "
                            f"frysta system i {family_label}")
                        _issue(
                            issues, level, product,
                            f"{family}_freeze_incomplete",
                            message,
                            draw["draw_number"])

        # Scanhintet ska aldrig ligga bakom en omgång som redan observerats.
        if not PRODUCTS.get(product, {}).get("listing", True):
            # `seed_hint` är numera scanANKARET och sänks avsiktligt till
            # lägsta öppna omgång. Här ska det RÅA, monotona högstavärdet
            # jämföras; annars blir ett friskt ankare ett permanent rött larm.
            hint = store.stored_seed(product)
            observed = store.conn.execute(
                "SELECT MAX(draw_number) FROM draws WHERE product=?",
                (product,)).fetchone()[0]
            if observed is not None and (hint is None or hint < int(observed)):
                _issue(issues, "error", product, "seed_behind",
                       f"scanhint {hint or 'saknas'} ligger bakom observerad omgång {observed}")

        product_rows.append({
            "product": product,
            "open_draws": len(open_draws),
            "next_draw": nearest and nearest["draw_number"],
            "next_close": nearest and _iso(nearest["close"]),
            "latest_snapshot": latest_at and _iso(latest_at),
            "max_age_minutes": max_age,
        })

    # En retry-tid är ett löfte från settlementmaskinen. Har den passerat med
    # mer än ett varv utan nytt facit är det en änd-till-änd-lucka, oavsett om
    # själva SvS-anropet senast såg grönt ut.
    for row in store.conn.execute(
            "SELECT c.product, c.draw_number, MAX(l.retry_after) retry_after "
            "FROM pool_played_coupon c "
            "LEFT JOIN pool_draw_settlement s ON s.product=c.product "
            " AND s.draw_number=c.draw_number "
            "LEFT JOIN pool_backfill_log l ON l.product=c.product "
            " AND l.draw_number=c.draw_number "
            "WHERE c.settled_at IS NULL AND s.draw_number IS NULL "
            "GROUP BY c.product, c.draw_number"):
        retry = _at(row[2])
        if retry and now > retry + dt.timedelta(minutes=SETTLEMENT_GRACE_MIN):
            _issue(issues, "error", row[0], "settlement_overdue",
                   f"omprövningstiden passerade {_iso(retry)} utan facit",
                   int(row[1]))

    return {
        "status": "error" if any(i["level"] == "error" for i in issues)
        else "ok",
        "checked_at": _iso(now),
        "issues": issues,
        "products": product_rows,
    }


def format_report(payload: dict) -> str:
    out = ["POOLHÄLSA — snapshots, frysningar och settlement", ""]
    for row in payload.get("products") or []:
        latest = row.get("latest_snapshot") or "aldrig"
        next_text = (f"nästa {row['next_draw']} stänger {row['next_close']}"
                     if row.get("next_draw") else "ingen öppen omgång")
        out.append(f"  {row['product']:18} {next_text} · snapshot {latest}")
    issues = payload.get("issues") or []
    errors = [issue for issue in issues if issue.get("level") == "error"]
    warnings = [issue for issue in issues if issue.get("level") == "warning"]
    if not issues:
        out += ["", "  ✓ inga änd-till-änd-luckor upptäckta"]
    if errors:
        out += ["", "  FEL:"]
        for issue in errors:
            draw = f" omg {issue['draw_number']}" if issue.get("draw_number") else ""
            out.append(f"    ✗ {issue['product']}{draw}: {issue['message']}")
    if warnings:
        out += ["", "  HISTORISKA BORTFALL:"]
        for issue in warnings:
            draw = f" omg {issue['draw_number']}" if issue.get("draw_number") else ""
            out.append(f"    ! {issue['product']}{draw}: {issue['message']}")
    return "\n".join(out)
