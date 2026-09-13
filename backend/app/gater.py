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

Statusorden (2026-09-13) är EN trappa för alla spår, så att mätbar volym
aldrig ser ut som ett beslut:
  samlar → underlag klart → granskad: stöd | ej stöd → infört | avslutad.
  `underlag klart` betyder bara att den förregistrerade prövningen får köras.
  `granskad` kräver en sparad artefakt (PH4: `docs/ph4-forward-status.json`),
  aldrig en omräkning här. `aggregat` är information utan beslutsvärde —
  grönt beslutas per signalgrupp, aldrig per tier. `fel` = kunde inte läsas.
  Researchraderna räknar OBEROENDE, PARADE omgångar (`research_gate`), aldrig
  kuponger: fyra metoder × två frystider på en omgång är åtta kuponger.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable, Optional

from .storage import Storage

# Skördeartefakten från `scripts/ph4_ablationer.py`. Finns den, är PH4 granskad
# för de produkter som hade tillräckligt underlag vid skörden — oavsett hur
# många omgångar räknaren visar i dag. Omprövning kräver nytt manifest.
PH4_STATUS_PATH = Path(__file__).resolve().parents[2] / "docs" / "ph4-forward-status.json"


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
    # Tier-summan visas som INFORMATION: grönt beslutas per liga × marknad ×
    # version (CLAUDE.md), så ett grönt aggregat är aldrig ett beslut.
    out = [_row("sharp-clv", "sharp × alla (tier)", "aggregat",
                n=tier["n_resolved"], krav=GREEN_MIN_N, ci=tier["ci"],
                anm="beslut per liga × marknad, aldrig per tier"
                    + (f" · close-EV {tier['avg_close_ev']}"
                       if tier["avg_close_ev"] is not None else ""))]
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
        out.append(_row("v2.2", f"träningsgate {horizon}",
                        "underlag klart" if ready else "samlar",
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
    """En rad per produkt/familj × frystid (× arm för poolopt): parade
    oberoende omgångar mot familjens egen grind, bortfall per orsak."""
    from . import pool_system_ledger as psl
    out = []
    for family in ("ph5", "mathmax", "reducedmax", "poolopt", "max40"):
        try:
            rep = psl.research_gate(store, family)
        except Exception as exc:  # noqa: BLE001
            out.append(_row(family, "(kunde inte läsas)", "fel", anm=str(exc)[:120]))
            continue
        spar = (rep["version"] or family) + (" (avslutad)" if rep["closed"] else "")
        if not rep["cells"]:
            out.append(_row(spar, "inga frysningar ännu",
                            "avslutad" if rep["closed"] else "samlar",
                            n=0, krav=rep["required"], anm=f"grind i {rep['doc']}"))
            continue
        for c in rep["cells"]:
            namn = f"{c['unit']} {c['horizon_minutes']} min"
            if c["arm"]:
                namn += f" · {c['arm_label']}"
            bortfall = ", ".join(f"{k} {v}" for k, v in c["dropout"].items() if v) or "inget"
            anm = (f"{c['forward_draws']} frysta omg · {c['settled_draws']} rättade · "
                   f"{c['open_draws']} öppna · bortfall: {bortfall}")
            if c["note"]:
                anm += f" · {c['note']}"
            if rep["end_after_forward_draws"]:
                anm += f" · avslut vid {rep['end_after_forward_draws']} frysta omg"
            anm += f" · prövning enligt {rep['doc']}"
            out.append(_row(spar, namn, c["status"], n=c["paired_draws"],
                            krav=rep["required"], anm=anm))
    return out


def _pit_total(store: Storage) -> list[dict]:
    from .pool_dataset import total_gate
    rep = total_gate(store)
    out = []
    for horizon, h in rep["horizons"].items():
        status = ("underlag klart" if h["complete"] >= rep["required_complete_draws"]
                  else "samlar")
        anm = (f"{h['observed']} Topptipsomgångar observerade · "
               f"{h['eligible_rows']}/{h['rows']} matcher med total")
        if h["other_observed"]:
            anm += f" · 13-matchsspel {h['other_observed']} omg (utanför grinden)"
        anm += f" · skörd enligt {rep['doc']}"
        out.append(_row(rep["feature_version"], f"total på alla 8 · {horizon}", status,
                        n=h["complete"], krav=rep["required_complete_draws"], anm=anm))
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
                        "underlag klart" if h["data_ready"] else "samlar",
                        n=h["settled"], krav=gate["minimum_settled_events_per_horizon"],
                        dagar=h["span_days"], dagar_krav=gate["minimum_span_days"],
                        anm=f"{represented}/{gate['minimum_represented_leagues']} ligor "
                            f"≥ {gate['minimum_settled_per_league']}"))
    return out


def _ph4_harvest() -> Optional[dict]:
    """Skördeartefakten, om den finns: vilka produkter som var granskade och hur."""
    try:
        d = json.loads(PH4_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    gate = d.get("promotion_gate") or {}
    candidate = gate.get("candidate")
    harvested_n = {}
    for product, p in (d.get("products") or {}).items():
        try:
            harvested_n[product] = p["forward"][candidate]["n_eval_draws"]
        except (KeyError, TypeError):
            pass
    return {"checks": gate.get("checks") or {}, "candidate": candidate,
            "harvested_at": d.get("harvested_at"), "harvested_n": harvested_n,
            "artifact": PH4_STATUS_PATH.name}


def _ph4_oot(store: Storage) -> list[dict]:
    # Samma beräkning som Historik → prognos använder; ingen egen SQL här.
    from .main import turnover_prognos
    rep = turnover_prognos()
    harvest = _ph4_harvest()
    out = []
    for product, v in rep.items():
        if not (isinstance(v, dict) and "ph4_oot" in v):
            continue
        status = "underlag klart" if v["ph4_oot"] >= v["ph4_oot_krav"] else "samlar"
        anm = ""
        check = (harvest["checks"].get(product) if harvest else None) or {}
        if check.get("enough_forward_draws"):
            status = "granskad: stöd" if check.get("ci_entirely_better") else "granskad: ej stöd"
            n_then = harvest["harvested_n"].get(product)
            anm = (f"skördad {(harvest['harvested_at'] or 'datum saknas')[:10]}"
                   + (f" vid {n_then} omg" if n_then is not None else "")
                   + f" · kandidat {harvest['candidate']} · {harvest['artifact']}"
                   " · omprövning kräver nytt manifest")
        out.append(_row("ph4-pit-v4", f"out-of-time {product}", status,
                        n=v["ph4_oot"], krav=v["ph4_oot_krav"], anm=anm))
    return out


def report(store: Storage, *, now: Optional[dt.datetime] = None) -> dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    rows: list[dict] = []
    for spar, loader in (("sharp-clv", lambda: _sharp_clv(store)),
                         ("wp5-ledger", lambda: _wp5_ledger(store)),
                         ("v2.2", lambda: _v22(store)),
                         ("radar-blindtest", lambda: _radar_blind(store)),
                         ("ph3-champion", lambda: _ph3_champion(store)),
                         ("research", lambda: _research(store)),
                         ("pit-total-v1", lambda: _pit_total(store)),
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
    out.append(f"  {'spår':20} {'grind':38} {'status':18} {'n/krav':>10} {'dagar':>8} {'KI':20} anm")
    last = None
    for g in payload["gates"]:
        if g["spar"] != last:
            out.append("")
            last = g["spar"]
        out.append(f"  {g['spar'][:20]:20} {g['namn'][:38]:38} {g['status']:18} "
                   f"{_frac(g['n'], g['krav']):>10} {_frac(g['dagar'], g['dagar_krav']):>8} "
                   f"{_ci(g['ci']):20} {g['anm']}")
    fel = [g for g in payload["gates"] if g["status"] == "fel"]
    out += ["", f"  {len(payload['gates'])} grindar · {len(fel)} kunde inte läsas",
            "  status: samlar → underlag klart → granskad: stöd|ej stöd → infört|avslutad · "
            "aggregat = information, inget beslut"]
    return "\n".join(out)
