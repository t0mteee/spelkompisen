"""Auditera och bakfyll xG från Sofascore för redan kända resultat.

Bakgrund: före MODEL_DATA_VERSION 5 markerades ett event som `seen` även när
statistik-endpointen svarade 200 men ännu saknade xG. Nästa varv hoppade då
över eventet permanent. Djurgården–Västerås 2026-08-03 var bevisfallet:
lokalt NULL, hos källan senare 3,71–1,32.

Säkerhet:
  * torrkörning är standard;
  * skarp körning tar först en konsistent SQLite-backup;
  * bara event som matchar EXAKT EN redan känd xG-lucka på liga, verifierat
    alias, datum ±1 dygn och normaltidsresultat får hämtas;
  * existerande xG är write-once i Storage och skrivs aldrig över;
  * matchantalet ska vara oförändrat före/efter.

Körning:
    .venv/bin/python -B scripts/backfill_xg_ligor.py
    .venv/bin/python -B scripts/backfill_xg_ligor.py \
        --ligor allsvenskan,superettan,obosligaen --sasonger 1 --skarpt
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import oddset_data, oddset_model                       # noqa: E402
from app.oddset import norm_team                                # noqa: E402
from app.storage import Storage                                 # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "stryktips.db"
BACKUP_DIR = ROOT / "data" / "backups"
DEFAULT_BACKUP = "stryktips-2026-08-10-fore-xg-luckor.db"
# 30 event/sida. 14 täcker även en 380-matcherssäsong med marginal.
SIDOR_PER_SASONG = 14


def backup_database(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return False
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return True


def _coverage(store: Storage, liga: str) -> dict:
    rows = oddset_data.merged_results(store, liga)
    seasons = sorted({
        oddset_model.season_of(r.get("date") or "", liga) for r in rows
    } - {None})
    current = seasons[-1] if seasons else None
    current_rows = [r for r in rows
                    if oddset_model.season_of(r.get("date") or "", liga)
                    == current]
    complete = lambda r: r.get("xg_h") is not None and r.get("xg_a") is not None
    return {
        "liga": liga, "season": current,
        "current_n": len(current_rows),
        "current_xg": sum(complete(r) for r in current_rows),
        "all_n": len(rows), "all_xg": sum(complete(r) for r in rows),
    }


def audit(store: Storage, ligor: list[str]) -> list[dict]:
    return [_coverage(store, liga) for liga in ligor]


def _event_identity(event: dict) -> tuple[str, str, str, int | None, int | None]:
    date = dt.datetime.fromtimestamp(
        event["startTimestamp"], dt.timezone.utc).date().isoformat()
    hs, away_score = event.get("homeScore") or {}, event.get("awayScore") or {}
    return (
        date,
        norm_team((event.get("homeTeam") or {}).get("name") or ""),
        norm_team((event.get("awayTeam") or {}).get("name") or ""),
        hs.get("normaltime", hs.get("current")),
        away_score.get("normaltime", away_score.get("current")),
    )


def _target(event: dict, missing: list[dict], aliases: dict[str, str]):
    date, home, away, hg, ag = _event_identity(event)
    # Samma ordning som merged_results: ett namn som redan finns exakt i
    # resultatfacit är kanoniskt och får aldrig mappas bort av ett historiskt
    # alias. Det upptäckte bl.a. tre IFK Göteborg-luckor där den gamla länken
    # `ifk goteborg -> goteborg` annars förstörde en redan exakt identitet.
    canonical = {
        name for row in missing for name in (row.get("home"), row.get("away"))
        if name
    }
    home = home if home in canonical else aliases.get(home, home)
    away = away if away in canonical else aliases.get(away, away)
    try:
        event_day = dt.date.fromisoformat(date)
    except ValueError:
        return None
    hits = []
    for row in missing:
        try:
            close_day = dt.date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        if abs((event_day - close_day).days) > 1:
            continue
        if (home, away) != (row.get("home"), row.get("away")):
            continue
        if hg is None or ag is None or (int(hg), int(ag)) != (
                int(row["hg"]), int(row["ag"])):
            continue
        hits.append(row)
    return hits[0] if len(hits) == 1 else None


def backfill(store: Storage, liga: str, sasonger: int,
             sidor: int = SIDOR_PER_SASONG) -> dict:
    ut = oddset_data.SOFA_UT.get(liga)
    if not ut:
        return {"liga": liga, "fel": "saknar tournament-id i SOFA_UT"}
    before = _coverage(store, liga)
    missing = [r for r in oddset_data.merged_results(store, liga)
               if r.get("xg_h") is None or r.get("xg_a") is None]
    aliases = oddset_data._alias_map(store, liga)
    try:
        seasons = oddset_data._sofa_get(
            f"/unique-tournament/{ut}/seasons")["seasons"][:sasonger]
    except Exception as exc:                                  # noqa: BLE001
        return {"liga": liga, "fel": f"säsongslista: {exc}"}

    attempted, linked, pages, errors = 0, set(), 0, []
    for season in seasons:
        for page in range(sidor):
            try:
                events = oddset_data._sofa_get(
                    f"/unique-tournament/{ut}/season/{season['id']}"
                    f"/events/last/{page}").get("events") or []
            except Exception as exc:                          # noqa: BLE001
                status = getattr(getattr(exc, "response", None),
                                 "status_code", None)
                if status != 404:
                    errors.append(
                        f"{season.get('year')} s{page}: {type(exc).__name__}")
                break
            pages += 1
            if not events:
                break
            for event in events:
                target = _target(event, missing, aliases)
                if target is None:
                    continue
                key = (target["date"], target["home"], target["away"])
                linked.add(key)
                try:
                    attempted += int(oddset_data._ingest_event(
                        store, liga, event))
                except Exception as exc:                      # noqa: BLE001
                    errors.append(
                        f"event {event.get('id')}: {type(exc).__name__}")
            print(f"  {liga:18s} {season.get('year', ''):>7} sida {page:2d}: "
                  f"{len(events):2d} event, {len(linked)} luckor länkade",
                  flush=True)
            time.sleep(0.4)

    after = _coverage(store, liga)
    return {
        "liga": liga, "sasonger": [s.get("year") for s in seasons],
        "sidor": pages, "luckor_fore": before["all_n"] - before["all_xg"],
        "lankade": len(linked), "forsok": attempted,
        "matcher": f"{before['all_n']} → {after['all_n']}",
        "med_xg": f"{before['all_xg']} → {after['all_xg']}",
        "xg_tillagda": after["all_xg"] - before["all_xg"],
        "current_xg": f"{before['current_xg']}/{before['current_n']} → "
                       f"{after['current_xg']}/{after['current_n']}",
        "fel": errors[:10], "n_fel": len(errors),
    }


def _print_audit(rows: list[dict]) -> None:
    print("LIGA                 SENASTE     XG SENASTE   XG ALLA   LUCKOR ALLA")
    for row in rows:
        print(f"{row['liga']:20s} {str(row['season'] or '-'):10s} "
              f"{row['current_xg']:4d}/{row['current_n']:<4d} "
              f"{row['all_xg']:4d}/{row['all_n']:<4d} "
              f"{row['all_n'] - row['all_xg']:4d}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ligor", help="kommaseparerade ligonycklar")
    parser.add_argument("--sasonger", type=int, default=1,
                        help="antal säsonger från den senaste (default 1)")
    parser.add_argument("--sidor", type=int, default=SIDOR_PER_SASONG)
    parser.add_argument("--skarpt", action="store_true")
    parser.add_argument("--backup", default=DEFAULT_BACKUP)
    args = parser.parse_args()

    default = sorted(set(oddset_data.SOFA_UT) & oddset_data.MODEL_LEAGUES)
    ligor = ([x.strip() for x in args.ligor.split(",") if x.strip()]
             if args.ligor else default)
    unknown = [x for x in ligor if x not in oddset_data.SOFA_UT]
    if unknown:
        print(f"AVBRYTER — saknar verifierat Sofascore-id: {unknown}")
        return 2

    store = Storage()
    try:
        before = audit(store, ligor)
    finally:
        store.close()
    _print_audit(before)
    if not args.skarpt:
        print("\nTORRKÖRNING — ingen databas ändrad. Lägg till --skarpt.")
        return 0

    backup = BACKUP_DIR / args.backup
    fresh = backup_database(DB, backup)
    print(f"\nbackup: {backup.name} ({'skapad' if fresh else 'fanns redan'})")

    store = Storage()
    started = time.time()
    reports = []
    try:
        for liga in ligor:
            print(f"\n=== {liga} (ut={oddset_data.SOFA_UT[liga]})", flush=True)
            reports.append(backfill(store, liga, args.sasonger, args.sidor))
        integrity = store.conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        store.close()

    print(f"\n=== KLART på {(time.time() - started) / 60:.1f} min")
    for report in reports:
        if isinstance(report.get("fel"), str):
            print(f"{report['liga']:20s} FEL: {report['fel']}")
            continue
        print(f"{report['liga']:20s} +{report['xg_tillagda']:3d} xG  "
              f"matcher {report['matcher']}  senaste {report['current_xg']}  "
              f"fel {report['n_fel']}")
    print(f"integrity_check: {integrity}")
    if integrity != "ok" or any(
            r.get("matcher", "").split(" → ")[0] !=
            r.get("matcher", "").split(" → ")[-1]
            for r in reports if r.get("matcher")):
        print("AVBRYTER: integritet eller matchantal ändrades")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
