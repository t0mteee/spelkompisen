"""Nolla ut xG som är en saknad mätning, och ta bort relegationsmatcher.

Upptäckt 2026-08-07 direkt efter xG-bakfyllningen, i dess egen utdata.

### 1. Falsk noll-xG

Sofascore rapporterar ibland 0.0 i stället för att utelämna xG — exakt samma
fel som kopplade bort providern som livekälla 2026-08-06 (Paide–SK Rapid
0,0/0,0 mot Flashscores 0,09/0,81). I modellen är skillnaden stor: effektiva
mål är 0,65·xG + 0,35·mål, så en falsk nolla gör en 2–2-match till 0,7–0,7.

Två objektiva kriterier (framåt i `_xg_is_measured`):
  * båda exakt 0,00 i en spelad match — signaturen för "statistiksektionen
    fanns men xG saknades";
  * ett lag som GJORDE MÅL har xG 0,00 — aritmetiskt omöjligt.

Ett mållöst lag med xG 0,00 är osannolikt men möjligt och lämnas orört: att
radera på osannolikhet i stället för omöjlighet vore att tycka till om datat.
Tre sådana rader finns kvar och redovisas av skriptet.

### 2. Relegationsmatcher i Bundesliga

Sofascore nästlar `Bundesliga, Relegation/Promotion Playoffs` under samma
uniqueTournament (35), så bakfyllningen tog med fyra playoff-matcher mot
SC Paderborn 07 och SV 07 Elversberg — lag som spelar i 2. Bundesliga och
omöjligt kan stå i Bundesligas tabell. De ger två lag med två matcher var i
fitten och hör inte hemma i ligan.

Ingen generell playoff-spärr införs: MLS slutspel spelas mellan MLS-lag och är
legitim ligadata. Diskriminatorn är inte verifierad för alla ligor, så den
frågan lämnas öppen i stället för att gissas.

Körning:
    .venv/bin/python -B scripts/stada_falsk_nollxg.py [--skarpt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage import Storage                               # noqa: E402

# Hårdkodat historiskt tillstånd, inte härlett ur dagens data: ett
# engångsskript ska beskriva vad som fanns när det skrevs.
RELEGATION = [
    ("bundesliga", "2025-05-22", "1 heidenheim", "sv 07 elversberg"),
    ("bundesliga", "2025-05-26", "sv 07 elversberg", "1 heidenheim"),
    ("bundesliga", "2026-05-21", "vfl wolfsburg", "paderborn 07"),
    ("bundesliga", "2026-05-25", "paderborn 07", "vfl wolfsburg"),
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skarpt", action="store_true")
    args = p.parse_args()

    store = Storage()
    try:
        falska = [dict(r) for r in store.conn.execute(
            "SELECT league, date, home, away, xg_h, xg_a, "
            "       final_home_score hg, final_away_score ag, provider "
            "FROM oddset_result_stats "
            "WHERE xg_h IS NOT NULL AND xg_a IS NOT NULL "
            "  AND ((xg_h = 0 AND xg_a = 0) "
            "    OR (final_home_score > 0 AND xg_h = 0) "
            "    OR (final_away_score > 0 AND xg_a = 0))")]
        print(f"FALSK xG ({len(falska)} rader — xG nollas, resultat behålls):")
        for r in falska:
            print(f"  {r['league']:14s} {r['date']}  {r['home']} - {r['away']}  "
                  f"{r['hg']}-{r['ag']}  xg {r['xg_h']}/{r['xg_a']}")

        osannolika = [dict(r) for r in store.conn.execute(
            "SELECT league, date, home, away, xg_h, xg_a, "
            "       final_home_score hg, final_away_score ag "
            "FROM oddset_result_stats "
            "WHERE ((xg_h = 0) != (xg_a = 0)) "
            "  AND NOT (final_home_score > 0 AND xg_h = 0) "
            "  AND NOT (final_away_score > 0 AND xg_a = 0)")]
        print(f"\nLÄMNAS ORÖRDA ({len(osannolika)} — osannolikt men möjligt, "
              f"laget gjorde inga mål):")
        for r in osannolika:
            print(f"  {r['league']:14s} {r['date']}  {r['home']} - {r['away']}  "
                  f"{r['hg']}-{r['ag']}  xg {r['xg_h']}/{r['xg_a']}")

        print(f"\nRELEGATION ({len(RELEGATION)} rader — tas bort helt):")
        for lg, d, h, a in RELEGATION:
            n = store.conn.execute(
                "SELECT COUNT(*) FROM oddset_results WHERE league=? AND date=? "
                "AND home=? AND away=?", (lg, d, h, a)).fetchone()[0]
            print(f"  {lg} {d}  {h} - {a}  ({n} resultatrad)")

        if not args.skarpt:
            print("\nTORRKÖRNING — kör om med --skarpt")
            return 0

        with store.conn:
            store.conn.execute(
                "UPDATE oddset_result_stats SET xg_h=NULL, xg_a=NULL "
                "WHERE xg_h IS NOT NULL AND xg_a IS NOT NULL "
                "  AND ((xg_h = 0 AND xg_a = 0) "
                "    OR (final_home_score > 0 AND xg_h = 0) "
                "    OR (final_away_score > 0 AND xg_a = 0))")
            store.conn.execute(
                "UPDATE oddset_results SET xg_h=NULL, xg_a=NULL "
                "WHERE xg_h = 0 AND xg_a = 0")
            for lg, d, h, a in RELEGATION:
                for table in ("oddset_result_stats", "oddset_results"):
                    store.conn.execute(
                        f"DELETE FROM {table} WHERE league=? AND date=? "
                        "AND home=? AND away=?", (lg, d, h, a))
        kvar = store.conn.execute(
            "SELECT COUNT(*) FROM oddset_result_stats WHERE xg_h = 0 AND xg_a = 0"
        ).fetchone()[0]
        print(f"\nKLART — {kvar} rader kvar med båda xG = 0")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
