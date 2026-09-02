"""Tystnadsdetektion för Oddset-varvet, liveradarn och pooltick-jobbet.

Helt lokal, inga externa anrop. `pool_health` larmar när en poolprodukt slutat
samlas; det här är motsvarigheten för de tre launchd-drivna processer vars
TYSTNAD historiskt upptäckts av att Saman såg något konstigt i UI:t
(Topptipset Dagens tyst 2026-08-04→09, AWS-DNS 302 varv utan att någon såg).

Vad som får bevisa liv (observationstidsregeln, CLAUDE.md):
  * `oddset_source_health_log` — append-only, en rad per kontroll. Den ENDA
    tabellen som skiljer "vi frågade och fick tomt" från "vi frågade aldrig".
  * varvens `meta`-stämplar (`oddset_last_run`, `pool_tick_last_run`).
Snapshots duger INTE: `snapshots`/`sharp_snapshots` skrivs bara vid
prisförändring, så en lugn marknad ser ut som en död insamlare.

Beslut 2026-09-02 (Saman): larmen visas i UI:t (Idag) och `/api/health`,
aldrig som ntfy-notis.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .live_radar import LIVE_SOURCES
from .pool_health import _at, _iso

# Basvarvet går på fasta :00/:30. 45 min = ett missat varv plus halva nästa.
# Snabbvarven (var 4:e min inom 3 h före avspark) stämplar samma nyckel, så
# tröskeln kan aldrig sättas under basintervallet utan falska larm nattetid.
ODDSET_RUN_MAX_MIN = 45
# `pool_tick_last_run` stämplas BARA efter ett lyckat pool-BASVARV (var 30:e
# min, tätare inom 2 h före spelstopp) — inte per femminuterstick och inte
# alls när alla produkter misslyckas. Därför 45 min som för Oddset-varvet.
# Femminutersjobbets eget liv bevisas av livekällornas rader (live-tick kör
# i varje tick), så en separat tick-gräns vore dubbelräkning.
POOL_BASE_MAX_MIN = 45
# live-tick kör i varje pooltick och skriver hälsorad även utan livematch
# (uppmätt 318 kontroller/källa/dygn 2026-09-02), så 20 min är fyra ticks.
LIVE_RADAR_MAX_MIN = 20
# Värde/modell/CLV kräver högst 45 min gammal bekräftelse (WP2-prisregeln).
# En kärnkälla utan kontroll — eller utan ett enda lyckat svar — på tre
# basvarv är därför död i praktiken, oavsett vad latest-state-tabellen säger.
SOURCE_SILENT_MAX_MIN = 90
LOOKBACK_H = 24


def core_sources() -> tuple[str, ...]:
    """Källor vars tystnad bryter värde/CLV: ankaret, SvS och BOOKS.

    Smarkets (dold, samlas bara för promotionsregeln) och Matchbook (skugga
    med gles ligatäckning) är diagnostik och larmar inte — ett larm på en
    källa ingen agerar på är brus, och brus är det som får riktiga larm att
    ignoreras. Lazy import: `oddset` är tungt och får inte dras in av health.
    """
    from .oddset import BOOKS
    return ("pinnacle", "svenskaspel") + tuple(b["key"] for b in BOOKS)


def _issue(issues: list[dict], source: str, kind: str, message: str) -> None:
    issues.append({"level": "error", "source": source, "kind": kind,
                   "message": message})


def _age_min(now: dt.datetime, then: dt.datetime) -> int:
    return int((now - then).total_seconds() // 60)


def _check_source(issues: list[dict], now: dt.datetime, source: str,
                  rows: list[dict], max_min: int, label: str) -> dict:
    """`rows` är källans kontroller i fönstret, nyast först."""
    if not rows:
        _issue(issues, source, f"{label}_never",
               f"inte kontrollerad på {LOOKBACK_H} h")
        return {"source": source, "last_checked": None, "last_ok": None}
    latest = _at(rows[0]["checked_at"])
    latest_ok = next((_at(r["checked_at"]) for r in rows if r["ok"]), None)
    age = _age_min(now, latest)
    if age > max_min:
        _issue(issues, source, f"{label}_silent",
               f"senast kontrollerad {_iso(latest)} — {age} min sedan "
               f"(gräns {max_min})")
    elif latest_ok is None or _age_min(now, latest_ok) > max_min:
        # Varvet frågar, men källan har inte gett ett enda lyckat svar på
        # hela fönstret: transportfel, blockering eller trasig parse.
        err = next((r["error"] for r in rows if r.get("error")), None)
        _issue(issues, source, f"{label}_failing",
               f"kontrolleras men inget lyckat svar på {max_min} min"
               + (f" ({err})" if err else ""))
    return {"source": source, "last_checked": _iso(latest),
            "last_ok": latest_ok and _iso(latest_ok)}


def report(store, *, now: Optional[dt.datetime] = None) -> dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    issues: list[dict] = []
    runs: dict[str, Optional[str]] = {}

    for key, label, max_min in (("oddset_last_run", "oddset-varv", ODDSET_RUN_MAX_MIN),
                                ("pool_tick_last_run", "pool-basvarv", POOL_BASE_MAX_MIN)):
        at = _at(store.meta_get(key))
        runs[key] = at and _iso(at)
        if at is None:
            _issue(issues, label, "run_never", f"`{key}` har aldrig stämplats")
        elif _age_min(now, at) > max_min:
            _issue(issues, label, "run_stale",
                   f"senaste körning {_iso(at)} — {_age_min(now, at)} min sedan "
                   f"(gräns {max_min})")

    since = _iso(now - dt.timedelta(hours=LOOKBACK_H))
    by_source: dict[str, list[dict]] = {}
    for r in store.oddset_source_health_history(since=since, limit=50000):
        by_source.setdefault(r["source"], []).append(r)

    sources = [_check_source(issues, now, src,
                             [r for r in by_source.get(src, []) if r["scope"] != "live"],
                             SOURCE_SILENT_MAX_MIN, "source")
               for src in core_sources()]
    live = [_check_source(issues, now, src,
                          [r for r in by_source.get(src, []) if r["scope"] == "live"],
                          LIVE_RADAR_MAX_MIN, "live")
            for src in LIVE_SOURCES]

    return {
        "status": "error" if issues else "ok",
        "checked_at": _iso(now),
        "issues": issues,
        "runs": runs,
        "sources": sources,
        "live": live,
    }


def format_report(payload: dict) -> str:
    out = ["ODDSETHÄLSA — varv, kärnkällor och liveradar (tystnadsdetektion)", ""]
    for key, value in (payload.get("runs") or {}).items():
        out.append(f"  {key:20} {value or 'aldrig'}")
    for row in (payload.get("sources") or []) + (payload.get("live") or []):
        out.append(f"  {row['source']:14} kontroll {row['last_checked'] or 'aldrig':20} "
                   f"lyckad {row['last_ok'] or 'aldrig'}")
    issues = payload.get("issues") or []
    if not issues:
        out += ["", "  ✓ ingen tystnad upptäckt"]
    else:
        out += ["", "  FEL:"] + [f"    ✗ {i['source']}: {i['message']}" for i in issues]
    return "\n".join(out)
