"""`cli.py gater` — varje förregistrerad grind på ETT ställe. Läser, beslutar inget.

Bakgrund (granskningen 2026-09-02): projektet driver ett tiotal parallella
shadow-spår med varsin grind i varsin modul (V2.2-manifestet, blindtestets
BLIND_MIN_*, PH3:s GATE_MIN_DRAWS, sharp-CLV:s GREEN_MIN_N, poolstyrkans
manifest-gate, PH4:s out-of-time-krav …). Backloggen säger själv att den
billigaste modellförbättringen är att LÄSA mätningarna på sin kadens — men
skördedatumen stod obockade eftersom ingen kunde se alla grindar samtidigt.

Regler:
  * Varje rad kommer från spårets EGEN statusfunktion. Ingen tröskel, KI
    eller status räknas om här — då hade det blivit en parallell definition.
  * En trasig källa ger raden status `fel` i stället för att fälla rapporten:
    poängen är att se ALLA grindar, även när en modul ligger nere.
  * Statusbeslut (candidate/green) fattas på förregistrerad kadens i
    respektive ledger; det här är en avläsning, inte ett beslut.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Optional

from .storage import Storage


def _row(spar: str, namn: str, status: str, *, n=None, krav=None,
         dagar=None, dagar_krav=None, ci=None, anm: str = "") -> dict:
    return {"spar": spar, "namn": namn, "status": status, "n": n, "krav": krav,
            "dagar": dagar, "dagar_krav": dagar_krav, "ci": ci, "anm": anm}


def _safe(rows: list[dict], spar: str, loader: Callable[[], list[dict]]) -> None:
    try:
        got = loader()
        # Ett spår utan data är fortfarande ett spår: det ska synas som
        # "samlar 0", inte försvinna ur listan.
        rows.extend(got or [_row(spar, "inga data ännu", "samlar", n=0)])
    except Exception as exc:  # noqa: BLE001 — en nere modul får inte dölja de andra
        rows.append(_row(spar, "(kunde inte läsas)", "fel",
                         anm=f"{type(exc).__name__}: {exc}"[:120]))


# ── Oddset ──────────────────────────────────────────────────────────────

def _sharp_clv(store: Storage) -> list[dict]:
    from .oddset_value import GREEN_MIN_N, clv_report
    rep = clv_report(store)
    tier = rep["sharp"]
    out = [_row("sharp-clv", "sharp × alla (tier)",
                "grön" if tier["green_ready"] else
                "samlar" if tier["n_resolved"] < GREEN_MIN_N else "ej stöd",
                n=tier["n_resolved"], krav=GREEN_MIN_N, ci=tier["ci"],
                anm=f"close-EV {tier['avg_close_ev']}" if tier["avg_close_ev"] is not None else "")]
    groups = [g for g in rep["groups"] if g["tier"] == "sharp" and g["active"]
              and g["n_resolved"] >= 10]
    for g in sorted(groups, key=lambda g: -g["n_resolved"])[:12]:
        out.append(_row("sharp-clv", f"{g['league']} × {g['market']}",
                        "grön" if g["green_ready"] else
                        "samlar" if g["n_resolved"] < GREEN_MIN_N else "ej stöd",
                        n=g["n_resolved"], krav=GREEN_MIN_N, ci=g["ci"],
                        anm=f"close-EV {g['avg_close_ev']}"))
    return out


def _wp5_ledger(store: Storage) -> list[dict]:
    from .oddset_ledger import dashboard_summary
    rep = dashboard_summary(store)
    out = [_row("wp5-ledger", "prediktioner/captures", "samlar",
                n=rep["n_predictions"], anm=f"{rep['n_captures']} captures · "
                f"sharp {rep['current_versions'].get('sharp')}")]
    for g in rep["groups"]:
        out.append(_row("wp5-ledger", f"{g['league']} × {g['market']} (primär)",
                        g["status"], n=g["n_resolved"]))
    return out


def _v22(store: Storage) -> list[dict]:
    from .oddset_v22 import audit
    rep = audit(store)
    out = []
    for horizon, h in rep["horizons"].items():
        thin = [lg for lg, v in h["by_league"].items()
                if v["settled_eligible_unique_matches"] < h["training_min_per_league"]]
        ready = (h["settled_eligible_unique_matches"] >= h["training_min_matches"]
                 and h["span_days"] >= h["training_min_span_days"] and not thin)
        out.append(_row("v2.2", f"träningsgate {horizon}", "klar" if ready else "samlar",
                        n=h["settled_eligible_unique_matches"], krav=h["training_min_matches"],
                        dagar=h["span_days"], dagar_krav=h["training_min_span_days"],
                        anm=(f"under {h['training_min_per_league']}/liga: {', '.join(thin)}"
                             if thin else "alla ligor över per-liga-kravet")))
    out.append(_row("v2.2", f"identitet ({rep['shadow_version']})",
                    "ok" if rep["identity_max_abs"] < 1e-9 else "AVVIKER",
                    n=rep["rows"], anm=f"max|p_v22−p_sharp| = {rep['identity_max_abs']:.2e}"))
    return out


def _radar_blind(store: Storage) -> list[dict]:
    from .live_signal_ledger import facit
    rep = facit(store, limit=1)
    b = rep["blind_gate"]
    status = {"collecting": "samlar", "pass": "grön", "no_support": "ej stöd"}.get(
        b["status"], b["status"])
    return [_row("radar-blindtest", f"första signal/match ({rep['signal_version']})", status,
                 n=b["n_priced_settled"], krav=b["required_priced_settled"],
                 dagar=b["span_days"], dagar_krav=b["required_span_days"], ci=b["roi_ci90"],
                 anm=f"ROI över {b['roi_over']} · {b['n_match_days']}/{b['required_match_days']} matchdygn")]


# ── Pool ────────────────────────────────────────────────────────────────

def _ph3_champion(store: Storage) -> list[dict]:
    from .pool_system_ledger import champion_report
    rep = champion_report(store)
    out = []
    for r in rep["rows"]:
        best = r["best_challenger"]
        if r["promotable"]:
            status = "promoterbar"
        elif r["champion_n"] < rep["gate_min_draws"]:
            status = "samlar"
        else:
            status = "ingen utmanare"
        anm = (f"bästa {best['config_key']} Δ{best['delta_roi']:+.3f} "
               f"(n={best['n_paired']}, FDR {'✓' if best['fdr_pass'] else '✗'})"
               if best else "inga parade utmanare")
        out.append(_row("ph3-champion", f"{r['product']} {r['horizon_minutes']} min",
                        status, n=r["champion_n"], krav=rep["gate_min_draws"],
                        anm=f"champion ROI {r['champion_roi']:+.3f} · {anm}"))
    return out


def _research(store: Storage) -> list[dict]:
    from . import pool_system_ledger as psl
    out = []
    for spar, fn, doc in (("ph5-forward", psl.ph5_overview, "docs/ph5-forward-2026-08-15.md"),
                          ("mathmax-v1", psl.mathmax_overview, "docs/maxtester-2026-08-29.md"),
                          ("reducedmax-v1", psl.reducedmax_overview, "docs/maxtester-2026-08-29.md"),
                          ("max40 (avslutad)", psl.max40_overview, "docs/max40-forward-2026-08-26.md")):
        try:
            s = fn(store)["summary"]
            # `draws/freezes/evaluated` gäller AKTIVA nycklar; serierna
            # omnycklades 2026-08-31 (X-risk v1), så de startar om från noll
            # medan `all_*` bär hela serien inklusive pensionerade nycklar.
            out.append(_row(spar, "frysningar/facit (aktiva nycklar)", "samlar",
                            n=s["evaluated"], krav=None,
                            anm=f"aktiva: {s['draws']} omg · {s['freezes']} frysta · "
                                f"{s['evaluated']} facit — hela serien: {s['all_draws']} omg · "
                                f"{s['all_freezes']} frysta · {s['all_evaluated']} facit · grind i {doc}"))
        except Exception as exc:  # noqa: BLE001
            out.append(_row(spar, "(kunde inte läsas)", "fel", anm=str(exc)[:120]))
    return out


def _strength(store: Storage) -> list[dict]:
    from .pool_strength_shadow import report
    rep = report(store)
    gate = rep["gate"]
    out = [_row("poolstyrka", f"{rep['experiment']} ({rep['shadow_version']})",
                {"candidate": "kandidat", "samlar": "samlar"}.get(rep["status"], rep["status"]),
                n=rep["settled"], anm=f"{rep['captured']} captures · {rep['eligible']} eligible")]
    for horizon, h in rep["horizons"].items():
        represented = sum(n >= gate["minimum_settled_per_league"]
                          for n in h["league_counts"].values())
        out.append(_row("poolstyrka", f"horisont {horizon}",
                        "klar" if h["data_ready"] else "samlar",
                        n=h["settled"], krav=gate["minimum_settled_events_per_horizon"],
                        dagar=h["span_days"], dagar_krav=gate["minimum_span_days"],
                        anm=f"{represented}/{gate['minimum_represented_leagues']} ligor "
                            f"≥ {gate['minimum_settled_per_league']}"))
    return out


def _ph4_oot(store: Storage) -> list[dict]:
    # Samma beräkning som Historik → prognos använder; ingen egen SQL här.
    from .main import turnover_prognos
    rep = turnover_prognos()
    return [_row("ph4-pit-v4", f"out-of-time {product}",
                 "klar" if v["ph4_oot"] >= v["ph4_oot_krav"] else "samlar",
                 n=v["ph4_oot"], krav=v["ph4_oot_krav"])
            for product, v in rep.items() if isinstance(v, dict) and "ph4_oot" in v]


def report(store: Storage, *, now: Optional[dt.datetime] = None) -> dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    rows: list[dict] = []
    for spar, loader in (("sharp-clv", lambda: _sharp_clv(store)),
                         ("wp5-ledger", lambda: _wp5_ledger(store)),
                         ("v2.2", lambda: _v22(store)),
                         ("radar-blindtest", lambda: _radar_blind(store)),
                         ("ph3-champion", lambda: _ph3_champion(store)),
                         ("research", lambda: _research(store)),
                         ("poolstyrka", lambda: _strength(store)),
                         ("ph4-pit-v4", lambda: _ph4_oot(store))):
        _safe(rows, spar, loader)
    return {"checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "gates": rows,
            "note": "avläsning av varje spårs egen grind — beslut fattas i respektive ledger"}


def _frac(n, krav) -> str:
    if n is None:
        return "–"
    return f"{n}/{krav}" if krav is not None else str(n)


def _ci(ci) -> str:
    if not ci:
        return "–"
    lo, hi = ci
    return f"[{lo:+.3f}, {hi:+.3f}]"


def format_report(payload: dict) -> str:
    out = [f"GRINDAR — {payload['checked_at']} · {payload['note']}", ""]
    out.append(f"  {'spår':16} {'grind':38} {'status':14} {'n/krav':>10} {'dagar':>8} {'KI':20} anm")
    last = None
    for g in payload["gates"]:
        if g["spar"] != last:
            out.append("")
            last = g["spar"]
        out.append(f"  {g['spar']:16} {g['namn'][:38]:38} {g['status']:14} "
                   f"{_frac(g['n'], g['krav']):>10} {_frac(g['dagar'], g['dagar_krav']):>8} "
                   f"{_ci(g['ci']):20} {g['anm']}")
    fel = [g for g in payload["gates"] if g["status"] == "fel"]
    out += ["", f"  {len(payload['gates'])} grindar · {len(fel)} kunde inte läsas"]
    return "\n".join(out)
