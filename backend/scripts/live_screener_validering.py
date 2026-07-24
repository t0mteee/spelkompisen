"""Validering av LIVE-SCREENERN: förutsäger skottövervikt kommande mål?

Samans idé (2026-07-24): hitta matcher där det HÄNDER mer än ställningen
visar — "1-1 men ena laget har 3 xG och 20 skott" — och som därför är värda
att titta på liveodds för. Detta skript testar premissen, INTE någon
oddsjämförelse: frågan är helt enkelt om skottövervikt vid minut T förutsäger
mål under minuterna T..T+15.

VIKTIGT FYND FÖRE DETTA SKRIPT: Sofascores shotmap saknar xG helt för
Allsvenskan (29–31 skott per match, 0 med xG). Däremot finns MINUT och
SHOTTYP (goal/save/miss/block) — alltså "20 skott"-halvan av idén. Vi
approximerar därför chansskapande med skott viktade efter typ.

Metod (helt offline, inga odds behövs):
  * för varje match och varje kontrollminut T (15, 30, 45, 60, 75)
  * räkna skottvikt och mål per lag fram till T
  * "tryck" = skottvikt_diff − 2×måldiff  (ett lag som skjutit mycket men
    inte fått utdelning har högt tryck)
  * utfall = gjorde det trycksatta laget mål under T..T+15?
  * jämför träffrekvensen mot basraten för alla matcher i samma fönster

Körning: cd backend && .venv/bin/python -B scripts/live_screener_validering.py
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.oddset_data import _sofa_get  # noqa: E402

DB = ROOT / "data" / "stryktips.db"
LIGOR = ("Allsvenskan", "Superettan", "Eliteserien", "OBOS-ligaen")
CHECKPOINTS = (15, 30, 45, 60, 75)
WINDOW = 15
# Grov chansvikt per skottyp — shotmap saknar xG för svenska ligor.
VIKT = {"goal": 1.0, "save": 0.32, "miss": 0.12, "block": 0.10, "post": 0.35}
MAX_MATCHER = 220
PAUS = 0.25


def hamta_matcher(limit: int) -> list[int]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        marks = ",".join("?" * len(LIGOR))
        return [r[0] for r in conn.execute(
            f"SELECT DISTINCT event_id FROM oddset_sofa_team_event "
            f"WHERE home_score IS NOT NULL AND tournament_name IN ({marks}) "
            f"ORDER BY start_at DESC LIMIT ?", (*LIGOR, limit))]
    finally:
        conn.close()


def skott(event_id: int) -> list[dict] | None:
    try:
        data = _sofa_get(f"/event/{event_id}/shotmap")
    except Exception:  # noqa: BLE001 — 404 för matcher utan skottkarta
        return None
    out = []
    for s in data.get("shotmap") or []:
        minut = s.get("time")
        if minut is None:
            continue
        out.append({"min": int(minut), "hemma": bool(s.get("isHome")),
                    "typ": s.get("shotType") or "miss"})
    return out or None


def main() -> None:
    event_ids = hamta_matcher(MAX_MATCHER)
    print(f"hämtar skottkartor för {len(event_ids)} matcher …", flush=True)
    matcher = []
    for i, eid in enumerate(event_ids, 1):
        s = skott(eid)
        if s:
            matcher.append(s)
        if i % 40 == 0:
            print(f"  {i}/{len(event_ids)} ({len(matcher)} med skottdata)",
                  flush=True)
        time.sleep(PAUS)
    print(f"{len(matcher)} matcher med användbar skottkarta\n")
    if len(matcher) < 30:
        sys.exit("för lite data för slutsats")

    # basrate: hur ofta faller ett mål från ETT visst lag i ett 15-minutersfönster
    bas_traffar = bas_total = 0
    for s in matcher:
        for cp in CHECKPOINTS:
            for hemma in (True, False):
                bas_total += 1
                bas_traffar += any(
                    x["typ"] == "goal" and x["hemma"] is hemma
                    and cp < x["min"] <= cp + WINDOW for x in s)
    basrate = bas_traffar / bas_total
    print(f"BASRATE: ett givet lag gör mål i ett 15-min-fönster "
          f"{basrate*100:.1f} % av gångerna (n={bas_total})\n")

    # tryck-kvartiler
    obs = []
    for s in matcher:
        for cp in CHECKPOINTS:
            for hemma in (True, False):
                fore = [x for x in s if x["min"] <= cp]
                vikt = sum(VIKT.get(x["typ"], 0.1) for x in fore
                           if x["hemma"] is hemma)
                vikt_mot = sum(VIKT.get(x["typ"], 0.1) for x in fore
                               if x["hemma"] is not hemma)
                mal = sum(1 for x in fore
                          if x["typ"] == "goal" and x["hemma"] is hemma)
                mal_mot = sum(1 for x in fore
                              if x["typ"] == "goal" and x["hemma"] is not hemma)
                tryck = (vikt - vikt_mot) - 2.0 * (mal - mal_mot)
                traff = any(x["typ"] == "goal" and x["hemma"] is hemma
                            and cp < x["min"] <= cp + WINDOW for x in s)
                obs.append((tryck, traff))
    obs.sort(key=lambda t: t[0])
    k = len(obs) // 5
    print("TRYCK-KVINTILER (skottövervikt minus utdelning):")
    print(f"{'kvintil':<22}{'n':>6}{'mål i nästa 15 min':>22}{'mot basrate':>14}")
    for i, namn in enumerate(("Q1 lägst tryck", "Q2", "Q3", "Q4",
                              "Q5 högst tryck")):
        chunk = obs[i * k:(i + 1) * k if i < 4 else len(obs)]
        rate = sum(1 for _, t in chunk if t) / len(chunk)
        lyft = rate / basrate if basrate else 0
        print(f"  {namn:<20}{len(chunk):>6}{rate*100:>20.1f} %{lyft:>13.2f}×")

    hog = [t for tr, t in obs if tr >= statistics.quantiles(
        [x for x, _ in obs], n=10)[8]]
    if hog:
        print(f"\nTOPP 10 %% TRYCK: {sum(hog)/len(hog)*100:.1f} % mål i nästa "
              f"15 min (n={len(hog)}) = {sum(hog)/len(hog)/basrate:.2f}× basrate")


if __name__ == "__main__":
    main()
