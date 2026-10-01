"""Nivåer och validering av poolförslag (beslut 9 och 12, designens 5.2).

256 kr för alla poolspel (Stryktipset, Europatipset och Topptipset-familjen);
512, 5 000, 20 000 och 39 366 kr bara för Stryktipset och Europatipset.
Radpriset är 1 kr för alla produkter, så nivån i kronor = högsta radantal.

Två format:
* `rows`    — lista av strängar, ett tecken (1/X/2) per match i omgångens
              matchordning, högst nivån rader och inga dubbletter.
* `msystem` — bara 39 366: per match en mängd tecken; exakt 3 matcher med
              1 tecken, 1 med 2 och 9 med 3 (= 2 · 3^9 = 39 366 rader).
"""
from __future__ import annotations

import hashlib
import itertools
from typing import Iterable, Optional

from ..svenskaspel import GAME_GROUPS, PRODUCTS

RADPRIS_KR = 1.0
SIGNS = ("1", "X", "2")
NIVA_ALLA = 256
MSYSTEM_NIVA = 39366
NIVAER_STORA = (256, 512, 5000, 20000, 39366)
# Stryktipset och Europatipset — läses ur spelgrupperna, ingen egen lista.
STORA_PRODUKTER = tuple(GAME_GROUPS["stryktipset"]) + tuple(GAME_GROUPS["europatipset"])
# Topptipset-familjen: Dagens, Stryk och Extra.
TOPPTIPSET_FAMILJ = tuple(GAME_GROUPS["topptipset"])
# M-systemets form: {antal tecken per match: antal matcher}.
MSYSTEM_FORM = {1: 3, 2: 1, 3: 9}
MOTIVERING_MAX = 500


class Ogiltigt(ValueError):
    """Ett förslag som inte får frysas som giltigt. Meddelandet är orsaken."""


def nivaer_for(product: str) -> tuple[int, ...]:
    if product in STORA_PRODUKTER:
        return NIVAER_STORA
    if product in TOPPTIPSET_FAMILJ:
        return (NIVA_ALLA,)
    return ()


def produkter() -> tuple[str, ...]:
    return tuple(p for p in PRODUCTS if nivaer_for(p))


def antal_matcher(product: str) -> int:
    return int(PRODUCTS[product]["matches"])


def format_for(level: int) -> str:
    return "msystem" if int(level) == MSYSTEM_NIVA else "rows"


def rows_hash(rows: Iterable[str]) -> str:
    """Ordningsoberoende hash: samma radmängd ger samma hash."""
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()[:16]


def expandera(tecken: list[str]) -> list[str]:
    """M-systemets tecken per match → alla rader (kartesisk produkt)."""
    return ["".join(row) for row in itertools.product(*tecken)]


def _norm_mangd(value, index: int) -> str:
    if not isinstance(value, str) or not value:
        raise Ogiltigt(f"match {index + 1}: tecknen måste vara en icke-tom sträng")
    if any(ch not in SIGNS for ch in value):
        raise Ogiltigt(f"match {index + 1}: ogiltigt tecken i {value!r} (bara 1, X, 2)")
    if len(set(value)) != len(value):
        raise Ogiltigt(f"match {index + 1}: dubblerat tecken i {value!r}")
    return "".join(s for s in SIGNS if s in value)


def validera(product: str, level: int, forslag: dict,
             n_matches: Optional[int] = None) -> dict:
    """Validera ETT förslag för en nivå. Returnerar normaliserad form:
    {format, rows (lista av strängar), tecken (msystem) | None, n_rows,
    cost_kr, rows_hash, motivering}. Kastar `Ogiltigt` med tydlig orsak."""
    if product not in PRODUCTS:
        raise Ogiltigt(f"okänd produkt {product!r}")
    try:
        level = int(level)
    except (TypeError, ValueError):
        raise Ogiltigt(f"nivån {level!r} är inte ett heltal") from None
    if level not in nivaer_for(product):
        raise Ogiltigt(f"nivån {level} kr finns inte för {product} "
                       f"(tillåtna: {', '.join(map(str, nivaer_for(product)))})")
    if not isinstance(forslag, dict):
        raise Ogiltigt("förslaget måste vara ett JSON-objekt")
    n_matches = n_matches or antal_matcher(product)
    fmt = forslag.get("format")
    expected = format_for(level)
    if fmt != expected:
        raise Ogiltigt(f"nivån {level} kr kräver format {expected!r}, fick {fmt!r}")
    motivering = forslag.get("motivering_kort")
    if motivering is not None and not isinstance(motivering, str):
        raise Ogiltigt("motivering_kort måste vara text")
    motivering = (motivering or "")[:MOTIVERING_MAX] or None

    if fmt == "rows":
        rows = forslag.get("rows")
        if not isinstance(rows, list) or not rows:
            raise Ogiltigt("rows måste vara en icke-tom lista")
        if len(rows) * RADPRIS_KR > level:
            raise Ogiltigt(f"{len(rows)} rader kostar {len(rows) * RADPRIS_KR:.0f} kr "
                           f"— över nivån {level} kr")
        seen: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, str):
                raise Ogiltigt(f"rad {index + 1} är inte en sträng")
            if len(row) != n_matches:
                raise Ogiltigt(f"rad {index + 1} har {len(row)} tecken, "
                               f"omgången har {n_matches} matcher")
            bad = [ch for ch in row if ch not in SIGNS]
            if bad:
                raise Ogiltigt(f"rad {index + 1} har ogiltigt tecken {bad[0]!r} "
                               f"(bara 1, X, 2)")
            if row in seen:
                raise Ogiltigt(f"rad {index + 1} ({row}) är en dubblett")
            seen.add(row)
        return {"format": "rows", "rows": list(rows), "tecken": None,
                "n_rows": len(rows), "cost_kr": len(rows) * RADPRIS_KR,
                "rows_hash": rows_hash(rows), "motivering": motivering}

    tecken = forslag.get("tecken")
    if not isinstance(tecken, list) or len(tecken) != n_matches:
        raise Ogiltigt(f"tecken måste vara en lista med {n_matches} matcher")
    norm = [_norm_mangd(value, index) for index, value in enumerate(tecken)]
    form: dict[int, int] = {}
    for value in norm:
        form[len(value)] = form.get(len(value), 0) + 1
    if form != MSYSTEM_FORM:
        raise Ogiltigt(
            "M-systemet ska ha exakt 3 spikar, 1 halvgardering och 9 "
            f"helgarderingar; fick {form.get(1, 0)} spikar, {form.get(2, 0)} "
            f"halv- och {form.get(3, 0)} helgarderingar")
    n_rows = 1
    for value in norm:
        n_rows *= len(value)
    if n_rows * RADPRIS_KR > level:
        raise Ogiltigt(f"M-systemet ger {n_rows} rader — över nivån {level} kr")
    return {"format": "msystem", "rows": None, "tecken": norm, "n_rows": n_rows,
            "cost_kr": n_rows * RADPRIS_KR,
            "rows_hash": rows_hash(expandera(norm)), "motivering": motivering}
