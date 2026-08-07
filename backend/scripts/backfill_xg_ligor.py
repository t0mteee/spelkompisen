"""Bakfyll xG/hörnor från Sofascore för valda ligor.

Bakgrund (Saman 2026-08-07): powerrank-v2 räknar bara på matcher med xG, och
Premier League, Serie A, La Liga och Bundesliga hade NOLL — trots att deras
tournament-id:n redan står i `SOFA_UT`. Orsaken var att ligorna var
`research_only` när insamlingen kördes, inte att providern saknar data.

Varför en bakfyllning är tillåten HÄR men inte för priser och signaler: ett
avgjort matchresultat och dess xG är settlade fakta som inte ändrar sig.
Observationstidsregeln gäller mätningar där tidpunkten är en del av
mätningen — prisobservationer, live-signaler, presence. Samma väg användes
redan för de nordiska ligorna och MLS.

Säkerhet:
  * `oddset_save_result` är FÖRST-VINNER för xG/hörnor (DB-åtgärd
    2026-08-01), så körningen kan bara FYLLA luckor — aldrig skriva över ett
    värde som redan är modellindata i en pågående mätserie.
  * `_ingest_event` hoppar över event med `oddset_sofa_seen`-markör, så
    skriptet är idempotent och kan avbrytas och köras om.
  * Ingen liga läggs till i MODEL_LEAGUES/FIT_POOLS här. Det ändrar
    `MODEL_PARAMS["pools"]` och därmed modellens signal_version — eget beslut.

Körning:
    .venv/bin/python -B scripts/backfill_xg_ligor.py \
        --ligor premier_league,serie_a,la_liga,bundesliga --sasonger 3
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import oddset_data                                   # noqa: E402
from app.storage import Storage                               # noqa: E402

# 30 event per sida; 14 sidor täcker en 380-matchers säsong med marginal.
SIDOR_PER_SASONG = 14


def _tackning(store: Storage, liga: str) -> tuple[int, int]:
    """(matcher, matcher med xG) för en liga — samma join som audit-vyn."""
    row = store.conn.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN s.xg_h IS NOT NULL THEN 1 ELSE 0 END) x "
        "FROM oddset_results r LEFT JOIN oddset_result_stats s "
        "  ON s.league=r.league AND s.date=r.date "
        " AND s.home=r.home AND s.away=r.away "
        "WHERE r.league=?", (liga,)).fetchone()
    return int(row["n"] or 0), int(row["x"] or 0)


def backfill(store: Storage, liga: str, sasonger: int,
             sidor: int = SIDOR_PER_SASONG) -> dict:
    ut = oddset_data.SOFA_UT.get(liga)
    if not ut:
        return {"liga": liga, "fel": "saknar tournament-id i SOFA_UT"}
    fore_n, fore_xg = _tackning(store, liga)
    try:
        seasons = oddset_data._sofa_get(
            f"/unique-tournament/{ut}/seasons")["seasons"][:sasonger]
    except Exception as exc:                                  # noqa: BLE001
        return {"liga": liga, "fel": f"säsongslista: {exc}"}

    nya, sidor_hamtade, fel = 0, 0, []
    for s in seasons:
        for sida in range(sidor):
            try:
                evs = oddset_data._sofa_get(
                    f"/unique-tournament/{ut}/season/{s['id']}"
                    f"/events/last/{sida}").get("events") or []
            except Exception as exc:                          # noqa: BLE001
                # 404 på en sida bortom säsongens slut är väntat och inte ett
                # fel; allt annat noteras men stoppar bara den säsongen.
                status = getattr(getattr(exc, "response", None),
                                 "status_code", None)
                if status != 404:
                    fel.append(f"{s['year']} s{sida}: {type(exc).__name__}")
                break
            sidor_hamtade += 1
            if not evs:
                break
            for e in evs:
                try:
                    nya += oddset_data._ingest_event(store, liga, e)
                except Exception as exc:                      # noqa: BLE001
                    fel.append(f"{s['year']} event {e.get('id')}: "
                               f"{type(exc).__name__}")
            print(f"  {liga:18s} {s['year']:>6s} sida {sida:2d}: "
                  f"{len(evs):2d} event, {nya} nya totalt", flush=True)
            time.sleep(0.4)          # artighet mellan sidhämtningar
    efter_n, efter_xg = _tackning(store, liga)
    return {"liga": liga, "sasonger": [s["year"] for s in seasons],
            "sidor": sidor_hamtade, "nya_event": nya,
            "matcher": f"{fore_n} → {efter_n}",
            "med_xg": f"{fore_xg} → {efter_xg}",
            "xg_tillagda": efter_xg - fore_xg,
            "fel": fel[:5], "n_fel": len(fel)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ligor", required=True,
                   help="kommaseparerade ligonycklar ur SOFA_UT")
    p.add_argument("--sasonger", type=int, default=3,
                   help="antal säsonger bakåt inkl. innevarande (default 3)")
    p.add_argument("--sidor", type=int, default=SIDOR_PER_SASONG)
    args = p.parse_args()

    ligor = [x.strip() for x in args.ligor.split(",") if x.strip()]
    okanda = [x for x in ligor if x not in oddset_data.SOFA_UT]
    if okanda:
        print(f"okända ligor (saknar verifierat tournament-id): {okanda}")
        print("Lägg ALDRIG till ett id utan att verifiera sporten — se "
              "SOFA_UT-kommentaren om handbolls-id:t 1420.")
        return 2

    store = Storage()
    start = time.time()
    rapport = []
    try:
        for liga in ligor:
            print(f"\n=== {liga} (ut={oddset_data.SOFA_UT[liga]})", flush=True)
            rapport.append(backfill(store, liga, args.sasonger, args.sidor))
    finally:
        store.close()

    print(f"\n=== KLART på {(time.time() - start) / 60:.1f} min")
    for r in rapport:
        if r.get("fel") and r.get("n_fel"):
            print(f"{r['liga']:18s} {r.get('xg_tillagda', 0):+5d} xG  "
                  f"matcher {r.get('matcher')}  ({r['n_fel']} fel: {r['fel']})")
        else:
            print(f"{r['liga']:18s} {r.get('xg_tillagda', 0):+5d} xG  "
                  f"matcher {r.get('matcher')}  med_xg {r.get('med_xg')}"
                  f"{'  FEL: ' + r['fel'] if isinstance(r.get('fel'), str) else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
