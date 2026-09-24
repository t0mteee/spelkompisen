"""Testkatalogen för UI:t (Historik → Tester): EN rad per experiment.

Läser, beslutar inget — samma regel och samma statustrappa som `gater.py`:
samlar → underlag klart → granskad: stöd|ej stöd → infört|avslutad. Varje
cell ÄR en gater-rad (spårets egen statusfunktion, ingen omräkning här);
katalogen grupperar dem per experiment, lägger till syfte, version, öppna
kuponger och det senaste dokumenterade beslutet. Bara poolens spår — Oddsets
grindar bor i Labb (ytgränsen 2026-08-05).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .storage import Storage

# Vad varje experiment ska besvara, i en mening, och var beslutsregeln står.
# Ordningen är katalogens ordning: det man följer först överst.
CATALOG: tuple[dict, ...] = (
    {"id": "standard", "title": "Standardjämförelsen", "icon": "📋", "kind": "ph3",
     "purpose": "Slår någon av tolv utmanare (144–1 024 kr × säker/medel/tuff) eller "
                "Pinnacle-basen appens champion 256 kr medel? Parade omgångar, FDR över hela familjen.",
     "doc": "docs/ph3-gate-2026-07-26.md", "coupons": "benchmark"},
    {"id": "ph5", "title": "5 000-testet", "icon": "🧪", "kind": "research",
     "purpose": "Ger Värderader mer tillbaka än Max-EV, Favoritrad och Slumpurval på samma "
                "5 000 rader, samma omgång och samma frystid?",
     "doc": "docs/ph5-forward-2026-08-15.md", "coupons": "research"},
    {"id": "mathmax", "title": "Matematiskt max 39 366", "icon": "🧮", "kind": "research",
     "purpose": "Ett äkta M-system (3 spikar, 1 halv, 9 hela): tjänar EV medel eller EV högt "
                "mest på fulla garderingar?",
     "doc": "docs/maxtester-2026-08-29.md", "coupons": "research"},
    {"id": "reducedmax", "title": "Reducerat max 20 000", "icon": "✂️", "kind": "research",
     "purpose": "Största reducerade systemet som ryms i den externa radvägen: EV medel mot EV högt "
                "på 20 000 rader.",
     "doc": "docs/maxtester-2026-08-29.md", "coupons": "research"},
    {"id": "poolopt", "title": "Optimerare 256", "icon": "🔬", "kind": "research",
     "purpose": "Tre optimerade armar (träff, balans, X-kvot) à 256 rader mot championen på "
                "Topptipset-familjen. Kan bara nominera en PH3-utmanare, aldrig promoveras direkt.",
     "doc": "docs/poolopt-v1-forward-2026-09-02.md", "coupons": "research"},
    {"id": "poolstyrka", "title": "Poolstyrka", "icon": "🧬", "kind": "strength",
     "purpose": "Förbättrar 90 % Pinnacle + 10 % lagstyrka Pinnacles 1X2-prognos på poolmatcher? "
                "Logloss per horisont, aldrig systeminput.",
     "doc": "docs/pool-strength-forward-manifest-v2.json", "coupons": None},
    {"id": "total", "title": "Ö/U-totalen", "icon": "📏", "kind": "total",
     "purpose": "Bär Pinnacles huvudtotal information om oavgjort utöver X-priset? Först då vet vi "
                "om X-skyddet är en riskregel eller en modell.",
     "doc": "docs/pool-pit-total-v1-2026-09-02.md", "coupons": None},
    {"id": "ph4", "title": "Streckrörelse pit-v4", "icon": "📐", "kind": "ph4",
     "purpose": "Förbättrar streck och streckrörelse matchsannolikheterna över ren Pinnacle vid "
                "180 min? Topptipset skördad; Stryk/Europa samlar.",
     "doc": "docs/ph4-forward-status.json", "coupons": None},
    {"id": "max40", "title": "40 000-piloten", "icon": "🗃", "kind": "research", "archived": True,
     "purpose": "Avslutad pilot: 40 000 rankade enskilda rader. Ligger kvar för revision.",
     "doc": "docs/max40-forward-2026-08-26.md", "coupons": "research"},
)

# Senaste DOKUMENTERADE beslut per experiment — datum, utfall, källa. Bara
# avskrifter av det som står i respektive dokument; inget beslutas här.
DECISIONS: dict[str, dict] = {
    "ph4": {"date": "2026-09-02", "verdict": "granskad: ej stöd",
            "text": "Topptipset: streck + streckrörelse slår inte ren Pinnacle vid 180 min "
                    "(Δlogloss +0,013, KI90 täcker noll). Promotion nej; Stryk/Europa samlar "
                    "vidare under samma manifest. Omprövning kräver nytt manifest.",
            "doc": "docs/ph4-forward-status.json"},
    "max40": {"date": "2026-08-29", "verdict": "avslutad",
              "text": "Piloten rankade 40 000 enskilda rader och var reducerad, inte matematisk. "
                      "Ersatt av Matematiskt max 39 366 och Reducerat max 20 000.",
              "doc": "docs/max40-forward-2026-08-26.md"},
    "poolopt": {"date": "2026-09-24", "verdict": "avläst vid 40: ej passerad",
                "text": "Formell avläsning på de 40 första parade omgångarna per arm och "
                        "frystid: ingen cell har undre KI90 över noll för träff-Δ eller ROI-Δ, "
                        "så ingen utmanare föreslås. Sista avläsning vid 120 framåtomgångar; "
                        "inga avläsningar däremellan (Samans beslut 5aA).",
                "doc": "docs/poolopt-v1-avlasning-2026-09-24.md"},
    "standard": {"date": "2026-08-05", "verdict": "generation 2",
                 "text": "Matrisen byttes till 144/256/512/1024 kr × säker/medel/tuff med 256 kr "
                         "medel som champion; Pinnacle-basen tillkom 2026-09-02.",
                 "doc": "docs/db-atgarder.md"},
}

# Statustrappan i rangordning: katalogens rubrikstatus är den cell som kommit
# längst. `fel` vinner alltid — en trasig källa ska synas, inte döljas av en
# annan cells "samlar". `stoppad` (insamlingen står still, t.ex. poolstyrkan
# efter bytt modellversion) ligger strax under: ett stopp som ser ut som
# "samlar" är precis felet det ska synliggöra.
RANK = {"samlar": 0, "avslutsgräns nådd": 1, "underlag klart": 2, "ingen utmanare": 2,
        "promoterbar": 3, "granskad: ej stöd": 3, "granskad: stöd": 3,
        "kandidat": 2, "infört": 4, "avslutad": 5, "stoppad": 8, "fel": 9}


def _test_id(spar: str) -> str | None:
    for prefix, test_id in (("ph3-champion", "standard"), ("ph5-", "ph5"),
                            ("mathmax-", "mathmax"), ("reducedmax-", "reducedmax"),
                            ("poolopt-", "poolopt"), ("max40-", "max40"),
                            ("poolstyrka", "poolstyrka"), ("pit-total-", "total"),
                            ("ph4-pit-", "ph4")):
        if spar.startswith(prefix):
            return test_id
    return None


def _headline(cells: list[dict], archived: bool) -> str:
    if not cells:
        return "avslutad" if archived else "samlar"
    return max((c["status"] for c in cells), key=lambda s: RANK.get(s, 0))


def _progress(cells: list[dict]) -> dict | None:
    """Cellen som kommit längst mot sitt krav — rubrikens n/krav."""
    with_gate = [c for c in cells if c.get("n") is not None and c.get("krav")]
    if not with_gate:
        return None
    best = max(with_gate, key=lambda c: c["n"] / c["krav"])
    return {"n": best["n"], "krav": best["krav"], "namn": best["namn"]}


def _version(test: dict, cells: list[dict]) -> str | None:
    if test["kind"] == "research":
        return (cells[0]["spar"].split(" ")[0] if cells else None)
    if test["kind"] == "strength" and cells:
        namn = cells[0]["namn"]
        return namn[namn.find("(") + 1:namn.find(")")] if "(" in namn else None
    return {"total": "pit-total-v1", "ph4": "pit-v4", "ph3": "gen 2"}.get(test["kind"])


def _open_coupons(store: Storage) -> dict[str, int]:
    """Öppna (osettlade) frysningar per experiment, räknat på ledgerns nycklar."""
    from . import pool_system_ledger as psl
    families = {**{k: v for k, v in psl.RESEARCH_FAMILY_CONFIGS.items()},
                "max40": psl.MAX40_RETIRED_CONFIGS,
                "standard": (*psl.BENCHMARKS, *psl.RETIRED_BENCHMARKS, *psl.PROB_BASE_CHALLENGERS)}
    key_to_test = {}
    for test_id, configs in families.items():
        for config in configs:
            key_to_test.setdefault(config["key"], test_id)
    out: dict[str, int] = defaultdict(int)
    for key, n in store.conn.execute(
            "SELECT config_key, COUNT(*) FROM pool_system_ledger WHERE settled_at IS NULL "
            "GROUP BY config_key"):
        test_id = key_to_test.get(key)
        if test_id:
            out[test_id] += int(n)
    return dict(out)


def catalog(store: Storage, *, now: dt.datetime | None = None) -> dict:
    from . import gater
    rows: list[dict] = []
    for spar, loader in (("ph3-champion", lambda: gater._ph3_champion(store)),
                         ("research", lambda: gater._research(store)),
                         ("pit-total-v1", lambda: gater._pit_total(store)),
                         ("poolstyrka", lambda: gater._strength(store)),
                         ("ph4-pit-v4", lambda: gater._ph4_oot(store))):
        gater._safe(rows, spar, loader)
    by_test: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        test_id = _test_id(row["spar"])
        if test_id:
            by_test[test_id].append(row)
    open_counts = _open_coupons(store)
    tests = []
    for entry in CATALOG:
        cells = by_test.get(entry["id"], [])
        tests.append({
            **entry,
            "version": _version(entry, cells),
            "status": _headline(cells, bool(entry.get("archived"))),
            "progress": _progress(cells),
            "open_coupons": (open_counts.get(entry["id"], 0)
                             if entry.get("coupons") else None),
            "decision": DECISIONS.get(entry["id"]),
            "cells": cells,
        })
    stamp = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    return {"tests": tests, "generated_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "vocabulary": ["samlar", "underlag klart", "granskad: stöd", "granskad: ej stöd",
                           "infört", "avslutad"],
            "note": "avläsning av varje spårs egen grind — beslut fattas i respektive dokument"}
